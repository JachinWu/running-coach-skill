import os
import sys
import json
import datetime
from datetime import date
from getpass import getpass
from pathlib import Path

from dotenv import load_dotenv
env_path = Path(__file__).resolve().parents[4] / ".env"
load_dotenv(dotenv_path=env_path)

from garminconnect import (
    Garmin,
    GarminConnectAuthenticationError,
    GarminConnectConnectionError,
    GarminConnectTooManyRequestsError,
)

from garminconnect.workout import (
    RunningWorkout,
    WorkoutSegment,
    create_cooldown_step,
    create_interval_step,
    create_recovery_step,
    create_repeat_group,
    create_warmup_step,
)


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------

def print_tokens_for_user(api: Garmin) -> None:
    """將產生的 Token 印出，方便使用者更新到 .env 的 GARMIN_TOKENS 變數。"""
    print("\n" + "="*60)
    print("🚀 登入成功！請將以下內容更新至 .env 的 GARMIN_TOKENS 變數中")
    print("="*60)
    try:
        tokens_json = api.client.dumps()
        print(f"GARMIN_TOKENS='{tokens_json}'")
    except Exception as e:
        print(f"❌ 讀取 Token 發生錯誤: {e}")
    print("="*60 + "\n")


def safe_api_call(api_method, *args, **kwargs):
    """Safe API call wrapper with comprehensive error handling."""
    try:
        result = api_method(*args, **kwargs)
        return True, result, None
    except GarminConnectAuthenticationError as e:
        return False, None, f"Authentication error: {e}"
    except GarminConnectTooManyRequestsError as e:
        return False, None, f"Rate limit exceeded: {e}"
    except GarminConnectConnectionError as e:
        error_str = str(e)
        if "400" in error_str:
            return False, None, "Not available (400) — feature may not be enabled for your account"
        if "401" in error_str:
            return False, None, "Authentication required (401) — please re-authenticate"
        if "403" in error_str:
            return False, None, "Access denied (403) — account may not have permission"
        if "404" in error_str:
            return False, None, "Not found (404) — endpoint may have moved"
        if "429" in error_str:
            return False, None, "Rate limit (429) — please wait before retrying"
        if "500" in error_str:
            return False, None, "Server error (500) — Garmin servers are having issues"
        return False, None, f"Connection error: {e}"
    except Exception as e:
        return False, None, f"Unexpected error: {e}"


def get_credentials() -> tuple[str, str]:
    """從環境變數或互動式輸入取得 Garmin 帳號密碼。"""
    try:
        email = os.getenv("GARMIN_EMAIL") or input("Email: ").strip()
        password = os.getenv("GARMIN_PASSWORD") or getpass("Password: ")
        return email, password
    except Exception as e:
        print("❌ 錯誤: 請確認已設定 GARMIN_EMAIL 和 GARMIN_PASSWORD")
        raise e


def init_api() -> Garmin | None:
    """初始化並回傳已驗證的 Garmin API 物件。

    登入優先順序：
    1. 環境變數 GARMIN_TOKENS (JSON 字串，長度 >512 會自動以 client.loads() 載入)
    2. 環境變數 GARMIN_EMAIL / GARMIN_PASSWORD 帳密登入
    """
    # 1. Token 登入
    garmin_tokens_env = os.getenv("GARMIN_TOKENS")
    if garmin_tokens_env:
        try:
            garmin = Garmin()
            garmin.login(tokenstore=garmin_tokens_env)
            print("✅ 使用 Token 登入成功！")
            return garmin
        except GarminConnectTooManyRequestsError as err:
            print(f"⚠️ Rate limit: {err}")
            sys.exit(1)
        except Exception as e:
            print(f"⚠️ Token 失效或無法解析，將改用帳密重新登入: {e}")
    else:
        print("ℹ️ 未設定 GARMIN_TOKENS，將使用帳密登入")

    # 2. 帳密登入
    email, password = get_credentials()
    while True:
        try:
            garmin = Garmin(
                email=email,
                password=password,
                prompt_mfa=lambda: input("MFA code: ").strip(),
            )
            garmin.login()
            print("Login successful.")
            print_tokens_for_user(garmin)
            return garmin
        except GarminConnectTooManyRequestsError as err:
            print(f"Rate limit: {err}")
            sys.exit(1)
        except GarminConnectAuthenticationError:
            print("Wrong credentials — please try again.")
            email, password = get_credentials()
            continue
        except GarminConnectConnectionError as err:
            print(f"Connection error: {err}")
            return None
        except Exception as e:
            print(f"❌ 登入失敗: {e}")
            return None


# ---------------------------------------------------------------------------
# Display helpers
# ---------------------------------------------------------------------------

def display_user_info(api: Garmin) -> None:
    """顯示使用者基本資訊。"""
    success, full_name, error = safe_api_call(api.get_full_name)
    if success:
        print(f"👤 使用者: {full_name}")
    else:
        print(f"get_full_name failed: {error}")


def display_daily_stats(api: Garmin) -> None:
    """顯示今日基本數據。"""
    today = date.today().isoformat()
    success, summary, error = safe_api_call(api.get_user_summary, today)
    if success and summary:
        print(f"\n📊 今日數據 ({today}):")
        print(f"步數: {summary.get('totalSteps') or 0}")
        print(f"距離: {(summary.get('totalDistanceMeters') or 0) / 1000:.2f} km")
        print(f"卡路里: {summary.get('totalKilocalories') or 0}")
    else:
        print(f"無法取得今日數據: {error}")


# ---------------------------------------------------------------------------
# Workout upload
# ---------------------------------------------------------------------------

class WorkoutFactory:
    """將教練產生的 JSON 課表轉換為 Garmin RunningWorkout 物件。"""

    @staticmethod
    def parse_duration(val) -> float:
        """處理時間(秒)或距離(公尺)，統一回傳 float。"""
        return float(val)

    @staticmethod
    def parse_pace_to_ms(pace_str: str) -> float:
        """將配速字串 (e.g. '4:45') 轉換為公尺/秒 (m/s)。"""
        if not pace_str:
            return 0.0
        parts = pace_str.split(':')
        mins = int(parts[0])
        secs = int(parts[1]) if len(parts) > 1 else 0
        total_seconds_per_km = mins * 60 + secs
        if total_seconds_per_km == 0:
            return 0.0
        return 1000.0 / total_seconds_per_km

    @staticmethod
    def create_step_from_json(step_data: dict, order_idx: int) -> dict:
        """根據 type 建立對應的 Garmin step 字典，並套用 target 與備註。"""
        step_type_key = step_data.get('type', 'interval')
        duration = WorkoutFactory.parse_duration(step_data.get('duration', 0))

        # Garmin watch display: warmup=熱身, cooldown=緩和, recovery=恢復, interval=跑步
        # WARNING: Use 'recovery' ONLY for passive rest breaks inside repeat groups.
        # ALL primary running segments (easy run, tempo, long run) must use 'interval'
        # so the watch displays "跑步" (Run), not "恢復".
        type_id_map = {"warmup": 1, "cooldown": 2, "recovery": 3, "interval": 4}

        step = {
            "type": "ExecutableStepDTO",
            "stepOrder": order_idx,
            "stepType": {
                "stepTypeId": type_id_map.get(step_type_key, 4),
                "stepTypeKey": step_type_key,
                "displayOrder": 1,
            },
            "description": step_data.get('note') or step_data.get('description'),
            "endCondition": {
                "conditionTypeId": 2,
                "conditionTypeKey": "time",
                "displayOrder": 2,
                "displayable": True,
            },
            "endConditionValue": float(duration),
            "targetType": {
                "workoutTargetTypeId": 1,
                "workoutTargetTypeKey": "no.target",
                "displayOrder": 1,
            }
        }

        # 距離條件
        if step_data.get('duration_type') == 'distance':
            step["endCondition"] = {
                "conditionTypeId": 1,
                "conditionTypeKey": "distance",
                "displayOrder": 3,
                "displayable": True,
            }

        # 心率目標
        if 'target_heartrate' in step_data:
            hr_str = str(step_data['target_heartrate'])
            if '~' in hr_str:
                v1, v2 = hr_str.split('~')
                target_one, target_two = float(v1), float(v2)
            else:
                target_one = float(hr_str) - 5
                target_two = float(hr_str) + 5
            step["targetType"] = {
                "workoutTargetTypeId": 4,
                "workoutTargetTypeKey": "heart.rate.zone",
                "displayOrder": 4,
            }
            step["targetValueOne"] = target_one
            step["targetValueTwo"] = target_two

        # 配速目標
        elif 'target_pace' in step_data:
            pace_str = str(step_data['target_pace'])
            if '~' in pace_str:
                p_slow, p_fast = pace_str.split('~')
                t1 = WorkoutFactory.parse_pace_to_ms(p_slow)
                t2 = WorkoutFactory.parse_pace_to_ms(p_fast)
                target_one, target_two = min(t1, t2), max(t1, t2)
            else:
                spd = WorkoutFactory.parse_pace_to_ms(pace_str)
                target_one, target_two = spd * 0.9, spd * 1.1
            step["targetType"] = {
                "workoutTargetTypeId": 6,
                "workoutTargetTypeKey": "pace.zone",
                "displayOrder": 6,
            }
            step["targetValueOne"] = target_one
            step["targetValueTwo"] = target_two

        return step

    @staticmethod
    def generate_workout_dict(json_data: dict) -> dict:
        """將 JSON 課表轉為 Garmin API 接受的字典格式。"""
        garmin_steps = []
        current_order = 1

        for step in json_data['steps']:
            if step['type'] == 'repeat':
                sub_steps = [
                    WorkoutFactory.create_step_from_json(sub, i + 1)
                    for i, sub in enumerate(step['steps'])
                ]
                garmin_steps.append({
                    "type": "RepeatGroupDTO",
                    "stepOrder": current_order,
                    "stepType": {
                        "stepTypeId": 6,
                        "stepTypeKey": "repeat",
                        "displayOrder": 1,
                    },
                    "numberOfIterations": step['iterations'],
                    "workoutSteps": sub_steps,
                    "numberOfSteps": len(sub_steps)
                })
            else:
                garmin_steps.append(
                    WorkoutFactory.create_step_from_json(step, current_order)
                )
            current_order += 1

        return {
            "workoutName": json_data['workoutName'],
            "description": json_data.get('note') or json_data.get('description'),
            "sportType": {
                "sportTypeId": 1,
                "sportTypeKey": "running",
                "displayOrder": 1,
            },
            "workoutSegments": [
                {
                    "segmentOrder": 1,
                    "sportType": {
                        "sportTypeId": 1,
                        "sportTypeKey": "running",
                        "displayOrder": 1,
                    },
                    "workoutSteps": garmin_steps,
                }
            ],
        }


def upload_and_replace_workout(client: Garmin, workout_json: dict) -> bool:
    """上傳課表至 Garmin Connect，若當日已有排程則先刪除再重新排程。"""
    target_date = workout_json.get('date')
    if not target_date:
        print(f"❌ {workout_json.get('workoutName')} 缺少日期資訊")
        return False

    print(f"\n📅 處理目標日: {target_date} | 課表: {workout_json.get('workoutName')}")

    try:
        # 階段 A: 清理當日舊課表
        year, month, _ = target_date.split('-')
        calendar_data = client.get_scheduled_workouts(int(year), int(month))
        for item in calendar_data.get('calendarItems', []):
            if item.get('date') == target_date and item.get('itemType') == 'workout':
                old_id = item.get('workoutId')
                print(f"  🗑️ 發現既有課表 (ID:{old_id})，執行刪除...")
                client.delete_workout(old_id)

        # 階段 B: 上傳新課表 (使用字典格式)
        workout_dict = WorkoutFactory.generate_workout_dict(workout_json)
        upload_response = client.upload_workout(workout_dict)
        new_id = upload_response.get("workoutId")
        print(f"  🚀 課表上傳成功！(新 ID: {new_id})")

        # 階段 C: 排程
        client.schedule_workout(new_id, target_date)
        print(f"  ✅ 成功排程至 Garmin 日曆：{target_date}")
        return True

    except Exception as e:
        print(f"  ❌ 同步失敗: {e}")
        import traceback
        traceback.print_exc()
        return False


# ---------------------------------------------------------------------------
# Query helpers (used by Telegram bot handlers)
# ---------------------------------------------------------------------------

def get_today_scheduled_workout(api: Garmin) -> dict | None:
    """Get today's scheduled workout from Garmin Connect.

    Args:
        api: Authenticated Garmin API object.

    Returns:
        Workout dict if scheduled, None if rest day, or dict with 'error' key on failure.
    """
    today = date.today()
    success, calendar_data, error = safe_api_call(
        api.get_scheduled_workouts, today.year, today.month
    )
    if not success:
        return {"error": error}

    today_str = today.isoformat()
    for item in (calendar_data or {}).get("calendarItems", []):
        if item.get("date") == today_str and item.get("itemType") == "workout":
            return item
    return None


def get_weekly_summary(api: Garmin) -> dict:
    """Get running statistics for the past 7 days (including today).

    Args:
        api: Authenticated Garmin API object.

    Returns:
        Dict with summary (grouped by activity type), start_date, end_date, or 'error' key.
    """
    today = date.today()
    start_date = today - datetime.timedelta(days=6)
    success, activities, error = safe_api_call(
        api.get_activities_by_date,
        start_date.isoformat(),
        today.isoformat(),
    )
    if not success:
        return {"error": error}

    summary_by_type = {}
    
    for activity in (activities or []):
        # Fix: ensure activityType is a dict before calling .get()
        activity_type_obj = activity.get("activityType") or {}
        act_type = activity_type_obj.get("typeKey", "")
        
        if "running" in act_type:
            key = "跑步"
        elif "swimming" in act_type:
            key = "游泳"
        elif "cycling" in act_type:
            key = "自行車"
        else:
            continue
            
        if key not in summary_by_type:
            summary_by_type[key] = {
                "runs_count": 0,
                "total_distance_km": 0.0,
                "total_duration_min": 0.0,
                "hr_values": []
            }
            
        summary_by_type[key]["runs_count"] += 1
        summary_by_type[key]["total_distance_km"] += activity.get("distance", 0) / 1000.0
        summary_by_type[key]["total_duration_min"] += activity.get("duration", 0) / 60.0
        if activity.get("averageHR", 0) > 0:
            summary_by_type[key]["hr_values"].append(activity.get("averageHR", 0))

    final_summary = {}
    for key, data in summary_by_type.items():
        avg_hr = round(sum(data["hr_values"]) / len(data["hr_values"]), 1) if data["hr_values"] else 0.0
        final_summary[key] = {
            "runs_count": data["runs_count"],
            "total_distance_km": round(data["total_distance_km"], 2),
            "total_duration_min": round(data["total_duration_min"], 1),
            "avg_hr": avg_hr,
        }

    return {
        "summary": final_summary,
        "start_date": start_date.isoformat(),
        "end_date": today.isoformat(),
    }


def get_daily_activities_list(api: Garmin, days: int = 7) -> list:
    """Get a list of daily running distances for the past N days.

    Args:
        api: Authenticated Garmin API object.
        days: Number of days to look back.

    Returns:
        List of dicts: [{'date': 'YYYY-MM-DD', 'distance_km': 5.2, 'duration_min': 30}, ...]
    """
    today = date.today()
    start_date = today - datetime.timedelta(days=days-1)
    success, activities, error = safe_api_call(
        api.get_activities_by_date,
        start_date.isoformat(),
        today.isoformat(),
    )
    
    if not success:
        return [{"error": error}]

    # Pre-populate with 0.0 for all days
    daily_data = {}
    for i in range(days):
        d = (start_date + datetime.timedelta(days=i)).isoformat()
        daily_data[d] = {"distance_km": 0.0, "duration_min": 0.0, "runs": []}

    for activity in (activities or []):
        # Fix: ensure activityType is a dict before calling .get()
        activity_type_obj = activity.get("activityType") or {}
        act_type = activity_type_obj.get("typeKey", "")
        if "running" in act_type:
            d_str = activity.get("startTimeLocal", "")[:10]
            if d_str in daily_data:
                dist = activity.get("distance", 0) / 1000.0
                dur = activity.get("duration", 0) / 60.0
                te = activity.get("trainingEffectLabel", "UNKNOWN")
                
                daily_data[d_str]["distance_km"] += dist
                daily_data[d_str]["duration_min"] += dur
                daily_data[d_str]["runs"].append({
                    "distance": round(dist, 2),
                    "te": te
                })

    result = []
    for d_str in sorted(daily_data.keys()):
        result.append({
            "date": d_str,
            "distance_km": round(daily_data[d_str]["distance_km"], 2),
            "duration_min": round(daily_data[d_str]["duration_min"], 1),
            "runs": daily_data[d_str]["runs"]
        })
    return result


def get_comprehensive_daily_stats(api: Garmin, days: int = 7) -> list:
    """Fetch multiple metrics (mileage, load, hrv, bb) for the past N days.

    Args:
        api: Authenticated Garmin API object.
        days: Number of days to look back.

    Returns:
        List of dicts with daily metrics.
    """
    today = date.today()
    start_date = today - datetime.timedelta(days=days-1)
    
    # 1. Fetch running activities for distance
    activities_list = get_daily_activities_list(api, days)
    if activities_list and isinstance(activities_list[0], dict) and "error" in activities_list[0]:
        return activities_list

    # Map for easy lookup
    data_map = {d["date"]: d for d in activities_list}
    for d in data_map.values():
        d.update({"hrv": 0, "body_battery": 0, "training_load": 0, "load_ratio": 0})

    # 2. Fetch other metrics day by day (Careful with API rate limits)
    # Note: training_status and stats usually contain the data we need.
    for i in range(days):
        target_date = (start_date + datetime.timedelta(days=i)).isoformat()
        
        # HRV
        _, hrv_data, _ = safe_api_call(api.get_hrv_data, target_date)
        if hrv_data:
            # Fix: ensure hrvSummary is a dict before calling .get()
            summary = hrv_data.get("hrvSummary") or {}
            data_map[target_date]["hrv"] = summary.get("lastNightAvg") or summary.get("lastNight") or 0
        
        # Training Load & Body Battery from stats
        _, stats, _ = safe_api_call(api.get_stats, target_date)
        if stats:
            # We use max BB as the daily recovery indicator
            data_map[target_date]["body_battery"] = stats.get("bodyBatteryHighestValue") or 0
            
        # Training Load (Acute) - training_status usually has the most recent one.
        # To get historical, we might need a different endpoint, but let's try get_training_status.
        _, status, _ = safe_api_call(api.get_training_status, target_date)
        if status:
            # Garmin API can be inconsistent with where these fields are located
            # Try top-level first
            acute_load = status.get("dailyTrainingLoadAcute") or status.get("acuteTrainingLoad")
            chronic_load = status.get("dailyTrainingLoadChronic") or status.get("chronicTrainingLoad")
            load_ratio = status.get("acuteChronicLoadRatio") or status.get("loadRatio")
            
            # Try mostRecentTrainingStatus if not found
            if not acute_load or not load_ratio or not chronic_load:
                # Fix: ensure mr_status is a dict
                mr_status = status.get("mostRecentTrainingStatus") or {}
                acute_load = acute_load or mr_status.get("dailyTrainingLoadAcute") or mr_status.get("acuteTrainingLoad")
                chronic_load = chronic_load or mr_status.get("dailyTrainingLoadChronic") or mr_status.get("chronicTrainingLoad")
                load_ratio = load_ratio or mr_status.get("acuteChronicLoadRatio") or mr_status.get("loadRatio")
                
            # If still not found, try nested DTOs (common in older API versions)
            if not acute_load or not load_ratio or not chronic_load:
                mr_status = status.get("mostRecentTrainingStatus") or {}
                latest_data_map = mr_status.get("latestTrainingStatusData") or {}
                for device_data in latest_data_map.values():
                    if device_data and device_data.get("primaryTrainingDevice"):
                        # Fix: ensure load_dto is a dict
                        load_dto = device_data.get("acuteTrainingLoadDTO") or {}
                        acute_load = acute_load or load_dto.get("dailyTrainingLoadAcute")
                        chronic_load = chronic_load or load_dto.get("dailyTrainingLoadChronic")
                        load_ratio = load_ratio or load_dto.get("acuteChronicLoadRatio")
                        break

            # Fallback calculation if the device API doesn't provide the ratio directly
            if not load_ratio and acute_load and chronic_load:
                try:
                    acute_val = float(acute_load)
                    chronic_val = float(chronic_load)
                    if chronic_val > 0:
                        load_ratio = acute_val / chronic_val
                except (ValueError, TypeError):
                    pass

            if acute_load:
                data_map[target_date]["training_load"] = acute_load
            if load_ratio:
                data_map[target_date]["load_ratio"] = load_ratio

    return [data_map[d] for d in sorted(data_map.keys())]


def get_upcoming_schedule(api: Garmin) -> list:
    """Get scheduled workouts from today until the coming Sunday.

    Args:
        api: Authenticated Garmin API object.

    Returns:
        List of dicts containing date and workout info (or None if rest day).
    """
    today = date.today()
    days_until_sunday = (6 - today.weekday()) % 7
    coming_sunday = today + datetime.timedelta(days=days_until_sunday)

    # Fetch workouts for current month
    success, calendar_data, error = safe_api_call(
        api.get_scheduled_workouts, today.year, today.month
    )
    if not success:
        return [{"error": error}]

    items = (calendar_data or {}).get("calendarItems", [])

    # If Sunday falls in next month, fetch that month too
    if coming_sunday.month != today.month:
        success2, calendar_data2, _ = safe_api_call(
            api.get_scheduled_workouts, coming_sunday.year, coming_sunday.month
        )
        if success2:
            items.extend((calendar_data2 or {}).get("calendarItems", []))

    schedule = []
    curr = today
    while curr <= coming_sunday:
        d_str = curr.isoformat()
        workout = next(
            (item for item in items if item.get("date") == d_str and item.get("itemType") == "workout"),
            None
        )
        schedule.append({"date": d_str, "workout": workout})
        curr += datetime.timedelta(days=1)

    return schedule


def get_hrv_and_recovery(api: Garmin) -> dict:
    """Get HRV status, falling back to Body Battery as recovery indicator.

    Args:
        api: Authenticated Garmin API object.

    Returns:
        Dict with 'type' key ('hrv', 'body_battery', or 'unavailable') plus
        relevant recovery metrics.
    """
    today = date.today().isoformat()

    # Try HRV first
    success, hrv_data, _ = safe_api_call(api.get_hrv_data, today)
    if success and hrv_data:
        summary = hrv_data.get("hrvSummary", {})
        return {
            "type": "hrv",
            "weekly_avg": summary.get("weeklyAvg"),
            "last_night": summary.get("lastNightAvg") or summary.get("lastNight"),
            "status": summary.get("status", "unknown"),
        }

    # Fallback: Body Battery
    success, bb_data, error = safe_api_call(api.get_body_battery, today, today)
    if success and bb_data:
        latest = bb_data[-1] if isinstance(bb_data, list) else bb_data
        level = (
            latest.get("charged")
            or latest.get("bodyBatteryLevel")
            or latest.get("level")
        )
        return {"type": "body_battery", "level": level}

    return {"type": "unavailable", "error": "HRV 和 Body Battery 數據均不可用"}


def get_latest_activity(api: Garmin) -> dict | None:
    """Get the most recent activity (today or yesterday) for post-run detection.

    Args:
        api: Authenticated Garmin API object.

    Returns:
        Most recent activity dict, or None if no activities found.
    """
    today = date.today()
    yesterday = today - datetime.timedelta(days=1)
    success, activities, _ = safe_api_call(
        api.get_activities_by_date,
        yesterday.isoformat(),
        today.isoformat(),
    )
    if not success or not activities:
        return None
    return sorted(activities, key=lambda x: x.get("startTimeLocal", ""), reverse=True)[0]


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    """主程式：直接上傳單一課表至 Garmin Connect。

    Usage:
        python garmin.py --workout-json '{"date": "YYYY-MM-DD", "workoutName": "...", "steps": [...]}'
    """
    import argparse
    parser = argparse.ArgumentParser(description="直接上傳課表至 Garmin Connect")
    parser.add_argument("--workout-json", type=str, required=True,
                        help="課表 JSON 字串，需包含 date、workoutName、steps")
    args = parser.parse_args()

    print("--- 初始化 Garmin API ---")
    api = init_api()
    if not api:
        print("程式終止：無法建立連線")
        return

    try:
        workout_data = json.loads(args.workout_json)
    except json.JSONDecodeError as e:
        print(f"❌ 無法解析 JSON: {e}")
        return

    upload_and_replace_workout(api, workout_data)


if __name__ == "__main__":
    main()
