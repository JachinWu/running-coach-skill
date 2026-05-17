"""bot_bridge.py — Bridge between Telegram bot handlers and running coach logic.

This module encapsulates the high-level logic for handling bot commands and 
background tasks related to the running coach, allowing for easier integration 
with different bot frameworks or agents.
"""

import os
import json
import datetime
import asyncio
import logging
import re
import uuid
from pathlib import Path
from typing import Optional, List, Dict, Any, Callable, Coroutine

# Import sibling modules
try:
    from . import garmin
    from . import athlete_profile
    from . import visualizer
    from . import hrv_guardrail
    from . import weather
    from . import performance_vdot
except ImportError:
    import garmin
    import athlete_profile
    import visualizer
    import hrv_guardrail
    import weather
    import performance_vdot

import requests
import tempfile
import shutil

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Paths and Persistence
# ---------------------------------------------------------------------------
SKILL_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = SKILL_DIR / "data"
LAST_ACTIVITY_FILE = DATA_DIR / "last_activity.json"
MORNING_STATE_FILE = DATA_DIR / "morning_state.json"

def load_morning_state() -> dict:
    """Load the last morning routine alert state."""
    if MORNING_STATE_FILE.exists():
        try:
            with open(MORNING_STATE_FILE, "r") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load morning state: {e}")
    return {}

def save_morning_state(state: dict) -> None:
    """Save the current morning routine alert state."""
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        with open(MORNING_STATE_FILE, "w") as f:
            json.dump(state, f)
    except Exception as e:
        logger.error(f"Failed to save morning state: {e}")

def load_last_activity_id() -> Optional[str]:
    """Load the last processed activity ID from disk."""
    if LAST_ACTIVITY_FILE.exists():
        try:
            with open(LAST_ACTIVITY_FILE, "r") as f:
                data = json.load(f)
                return data.get("last_activity_id")
        except Exception as e:
            logger.error(f"Failed to load last activity ID: {e}")
    return None

def save_last_activity_id(activity_id: str) -> None:
    """Save the last processed activity ID to disk."""
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        with open(LAST_ACTIVITY_FILE, "w") as f:
            json.dump(
                {
                    "last_activity_id": activity_id,
                    "updated_at": datetime.datetime.now().isoformat(),
                },
                f,
            )
    except Exception as e:
        logger.error(f"Failed to save last activity ID: {e}")

# ---------------------------------------------------------------------------
# Formatting Helpers
# ---------------------------------------------------------------------------

def escape_html(text: str) -> str:
    """Escape HTML special characters."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

def escape_markdown(text: str) -> str:
    """Escape special characters for Telegram MarkdownV2."""
    # Note: We are using Markdown (not V2) in send_message_robust usually, 
    # but telegram's parse_mode='Markdown' also has issues with certain chars.
    # For 'Markdown', escaping is simpler than V2.
    chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
    for char in chars:
        text = text.replace(char, f'\\{char}')
    return text

def speed_to_pace(speed_ms: float) -> str:
    """Convert speed in m/s to pace (min:sec) per km."""
    if not speed_ms or speed_ms <= 0:
        return "0:00"
    total_seconds = 1000 / speed_ms
    minutes = int(total_seconds // 60)
    seconds = int(total_seconds % 60)
    return f"{minutes}:{seconds:02d}"

# ---------------------------------------------------------------------------
# Activity Feedback (RPE) Helpers
# ---------------------------------------------------------------------------

def get_rpe_keyboard_data(activity_id: str) -> List[List[Dict[str, str]]]:
    """Generate the structure for an RPE selection inline keyboard.
    
    Returns a list of rows, each containing dicts with 'text' and 'callback_data'.
    """
    return [
        [
            {"text": "1 (極輕鬆)", "callback_data": f"rpe:{activity_id}:1"},
            {"text": "2", "callback_data": f"rpe:{activity_id}:2"},
            {"text": "3", "callback_data": f"rpe:{activity_id}:3"},
        ],
        [
            {"text": "4 (舒服)", "callback_data": f"rpe:{activity_id}:4"},
            {"text": "5", "callback_data": f"rpe:{activity_id}:5"},
            {"text": "6", "callback_data": f"rpe:{activity_id}:6"},
        ],
        [
            {"text": "7 (吃力)", "callback_data": f"rpe:{activity_id}:7"},
            {"text": "8", "callback_data": f"rpe:{activity_id}:8"},
            {"text": "9", "callback_data": f"rpe:{activity_id}:9"},
            {"text": "10 (力竭)", "callback_data": f"rpe:{activity_id}:10"},
        ],
    ]


def get_shoe_selection_keyboard(activity_id: str) -> List[List[Dict[str, str]]]:
    """Generate inline keyboard for selecting which shoes were used for an activity."""
    profile = athlete_profile.load_profile()
    active_shoes = [s for s in profile.get("shoes", []) if s.get("status") == "active"]
    
    if not active_shoes:
        return []
        
    keyboard = []
    # 2 shoes per row
    row = []
    for shoe in active_shoes:
        nickname = shoe["nickname"]
        # callback format: shoe:activity_id:nickname
        row.append({"text": nickname, "callback_data": f"shoe:{activity_id}:{nickname}"})
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    
    # Add a "None/Other" option
    keyboard.append([{"text": "其他 / 未記錄", "callback_data": f"shoe:{activity_id}:none"}])
    return keyboard


def is_highlight_activity(activity: Dict[str, Any]) -> tuple[bool, str]:
    """Check if the activity qualifies as a 'highlight' (Long Run, High TE, etc.)."""
    # 1. Check Distance (> 15km)
    dist_km = activity.get("distance", 0) / 1000.0
    if dist_km >= 15:
        return True, f"完成了 {dist_km:.1f} km 的長距離訓練"

    # 2. Check Training Effect (TE >= 4.5)
    ae_te = activity.get("aerobicTrainingEffect", 0)
    an_te = activity.get("anaerobicTrainingEffect", 0)
    
    # Ensure they are numbers before comparing
    try:
        if (isinstance(ae_te, (int, float)) and ae_te >= 4.5) or \
           (isinstance(an_te, (int, float)) and an_te >= 4.5):
            return True, "完成了一場高品質、高強度的訓練"
    except (TypeError, ValueError):
        pass

    return False, ""


# ---------------------------------------------------------------------------
# Command Logic Handlers
# ---------------------------------------------------------------------------

def get_tsb_analysis(atl: float, ctl: float) -> tuple[float, str, str]:
    """Calculate TSB and return status and advice.
    TSB = CTL - ATL (Chronic Training Load - Acute Training Load)
    """
    tsb = round(ctl - atl, 1)
    if tsb > 5:
        return tsb, "🟢 恢復良好 (Fresh)", "體力充沛，適合進行高品質或長距離訓練。"
    elif tsb >= -10:
        return tsb, "🟡 狀態平穩 (Neutral)", "體能維持中，可按計畫執行訓練。"
    elif tsb >= -30:
        return tsb, "🟢 訓練產出期 (Optimal)", "目前處於高效訓練區，雖有疲勞但體能進步最快。"
    else:
        return tsb, "🔴 疲勞過度 (Overreaching)", "疲勞累積過高，建議降低強度或增加休息，嚴防受傷。"

async def get_today_summary(api) -> str:
    """Logic for /today command, providing context for the Dynamic Guardrail."""
    loop = asyncio.get_event_loop()
    workout = await loop.run_in_executor(None, garmin.get_today_scheduled_workout, api)
    recovery = await loop.run_in_executor(None, garmin.get_hrv_and_recovery, api)
    
    # Fetch TSB data (using comprehensive stats for latest day)
    stats = await loop.run_in_executor(None, garmin.get_comprehensive_daily_stats, api, 1)
    
    today_label = datetime.date.today().strftime("%Y/%m/%d")
    
    # 1. Recovery info (HRV/BB)
    hrv_part = ""
    if recovery.get("hrv"):
        hrv = recovery["hrv"]
        status_cn = {"balanced": "平衡", "low": "低", "unbalanced": "不平衡", "poor": "差"}.get(
            hrv.get("status", "").lower(), hrv.get("status", "未知")
        )
        hrv_part = f"昨夜 HRV: {hrv.get('last_night', 'N/A')} ms ({status_cn})"
    
    bb_part = ""
    if recovery.get("body_battery"):
        bb = recovery["body_battery"]
        bb_val = bb.get("highest") or bb.get("most_recent") or "N/A"
        bb_part = f"Body Battery: {bb_val}%"
    
    recovery_info = " | ".join(filter(None, [hrv_part, bb_part])) or "恢復數據暫不可用"

    # 2. TSB & Risk Analysis
    tsb_info = ""
    risk_warning = ""
    if stats and isinstance(stats[0], dict) and "training_load" in stats[0] and "chronic_load" in stats[0]:
        atl = stats[0]["training_load"]
        ctl = stats[0]["chronic_load"]
        tsb, tsb_status, tsb_advice = get_tsb_analysis(atl, ctl)
        tsb_info = f"\n📈 TSB: {tsb} ({tsb_status})\n💡 建議: {tsb_advice}"
        
        # Risk assessment: Combine TSB with injury history
        profile = athlete_profile.load_profile()
        active_injuries = athlete_profile.get_active_injuries(profile)
        recent_feedback = athlete_profile.get_recent_feedback(limit=3)
        
        max_pain = max([f.get("pain_level", 0) for f in recent_feedback] or [0])
        
        if tsb < -30 or (tsb < -20 and max_pain > 3) or active_injuries:
            risk_warning = "\n\n⚠️ **【風險預警】**\n"
            if tsb < -30:
                risk_warning += "• 訓練壓力平衡 (TSB) 進入危險區，受傷風險大幅增加。\n"
            if max_pain > 3:
                risk_warning += f"• 近期有不適感 (疼痛等級: {max_pain})，請務必保守。\n"
            if active_injuries:
                risk_warning += f"• 尚有未痊癒傷病：{', '.join([i['description'] for i in active_injuries])}\n"
            risk_warning += "👉 **建議：今日改為 E 跑、交叉訓練或徹底休息。**"

    if workout is None:
        return f"📅 {today_label}\n今日為休息日。☕\n[恢復狀態]: {recovery_info}{tsb_info}{risk_warning}"
    elif isinstance(workout, dict) and "error" in workout:
        return f"❌ 查詢失敗：{workout['error']}"
    else:
        name = workout.get("title") or workout.get("workoutName") or "未命名課表"
        description = workout.get("description", "")
        return (
            f"📅 今日課表 ({today_label})\n"
            f"🏃 課表內容: {name}\n"
            f"📝 詳情: {description}\n\n"
            f"❤️ [恢復狀態]: {recovery_info}{tsb_info}{risk_warning}"
        )

async def get_status_summary(api) -> str:
    """Logic for /status command."""
    loop = asyncio.get_event_loop()
    weekly = await loop.run_in_executor(None, garmin.get_weekly_summary, api)
    recovery = await loop.run_in_executor(None, garmin.get_hrv_and_recovery, api)
    upcoming = await loop.run_in_executor(None, garmin.get_upcoming_schedule, api)

    # Weekly block
    if "error" in weekly:
        week_text = f"📊 **過去 7 天訓練摘要**\n❌ 查詢失敗：{weekly['error']}"
    else:
        week_text = f"📊 **過去 7 天訓練摘要**"
        summary_data = weekly.get("summary", {})
        if not summary_data:
            week_text += "\n• 過去 7 天無運動紀錄"
        else:
            for act_name, data in summary_data.items():
                hr_line = f"{data['avg_hr']} bpm" if data["avg_hr"] > 0 else "N/A"
                week_text += (
                    f"\n🏃 **{act_name}**"
                    f"\n  • 次數：{data['runs_count']} 次"
                    f"\n  • 里程：{data['total_distance_km']} km"
                    f"\n  • 時間：{data['total_duration_min']} 分鐘"
                    f"\n  • 平均心率：{hr_line}"
                )

    # Schedule block
    schedule_text = "\n\n📅 **接下來課表**"
    if upcoming and isinstance(upcoming[0], dict) and "error" in upcoming[0]:
        schedule_text += f"\n❌ 查詢失敗：{upcoming[0]['error']}"
    else:
        for item in upcoming:
            d_obj = datetime.date.fromisoformat(item["date"])
            d_str = d_obj.strftime("%m/%d")
            weekday_cn = ["一", "二", "三", "四", "五", "六", "日"][d_obj.weekday()]

            w = item["workout"]
            if w:
                name = (
                    w.get("title") or w.get("workoutName") or "未命名課表"
                )
                schedule_text += f"\n• {d_str} ({weekday_cn}): {name}"
            else:
                schedule_text += f"\n• {d_str} ({weekday_cn}): 休息 ☕"

    # Recovery block
    hrv_part = ""
    if recovery.get("hrv"):
        hrv = recovery["hrv"]
        raw_status = hrv.get("status", "unknown").lower()
        status_emoji_map = {
            "balanced": "✅",
            "low": "⚠️",
            "unbalanced": "⚠️",
            "poor": "❌",
        }
        status_cn_map = {
            "balanced": "平衡",
            "low": "低",
            "unbalanced": "不平衡",
            "poor": "差",
        }
        emoji = status_emoji_map.get(raw_status, "📊")
        status_cn = status_cn_map.get(raw_status, raw_status.upper())
        hrv_part = (
            f"\n\n❤️ **HRV 恢復狀態** {emoji}\n"
            f"• 昨夜 HRV：{hrv.get('last_night', 'N/A')} ms\n"
            f"• 週平均 HRV：{hrv.get('weekly_avg', 'N/A')} ms\n"
            f"• 狀態：{status_cn}"
        )

    bb_part = ""
    if recovery.get("body_battery"):
        bb = recovery["body_battery"]
        level = bb.get("highest") or bb.get("most_recent") or 0
        if level >= 70:
            bb_emoji, advice = "🔋✅", "狀態良好，可進行高強度訓練"
        elif level >= 40:
            bb_emoji, advice = "🔋⚠️", "中等恢復，建議輕鬆訓練"
        else:
            bb_emoji, advice = "🔋❌", "恢復不足，建議今日休息"
        bb_part = f"\n\n{bb_emoji} **Body Battery：{level}%**\n• {advice}"

    recovery_text = hrv_part + bb_part
    if not recovery_text:
        recovery_text = f"\n\n⚠️ {recovery.get('error', '恢復數據不可用')}"

    return week_text + schedule_text + recovery_text

async def get_recovery_data(api) -> dict:
    """Fetch HRV and recovery data from Garmin."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, garmin.get_hrv_and_recovery, api)

async def get_morning_routine_data(api) -> dict:
    """Aggregate data for the morning proactive push message.
    
    Includes:
    - Today's workout summary
    - Recovery status (HRV/Body Battery)
    - Weather & AQI forecast
    """
    loop = asyncio.get_event_loop()
    
    # 1. Fetch Today's Summary (Workout + Recovery)
    summary = await get_today_summary(api)
    
    # 2. Fetch Weather & AQI
    # We use wrap in run_in_executor because these are blocking requests
    weather_data = await loop.run_in_executor(None, weather.get_weather_forecast)
    aqi_data = await loop.run_in_executor(None, weather.get_aqi)
    env_summary = weather.format_weather_summary(weather_data, aqi_data)
    
    # 3. Determine if recovery is risky (for buttons)
    recovery = await loop.run_in_executor(None, garmin.get_hrv_and_recovery, api)
    is_risky = False
    if recovery.get("type") == "hrv":
        is_risky = recovery.get("status", "").lower() in ("low", "unbalanced", "poor")
    elif recovery.get("type") == "body_battery":
        is_risky = (recovery.get("level") or 100) < 40

    return {
        "summary": summary,
        "env_summary": env_summary,
        "is_risky": is_risky,
        "recovery": recovery
    }

async def delete_today_workout(api) -> bool:
    """Delete today's scheduled workout from Garmin."""
    loop = asyncio.get_event_loop()
    today_str = datetime.date.today().isoformat()
    return await loop.run_in_executor(None, garmin.delete_workout_on_date, api, today_str)

async def get_workout_details_for_today(api) -> Optional[dict]:
    """Fetch details of today's scheduled workout."""
    loop = asyncio.get_event_loop()
    workout = await loop.run_in_executor(None, garmin.get_today_scheduled_workout, api)
    if workout and workout.get("workoutId"):
        return await loop.run_in_executor(None, api.get_workout_by_id, workout["workoutId"])
    return None

async def upload_and_replace_workout(api, workout_json: dict) -> bool:
    """Upload a workout and replace today's schedule."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, garmin.upload_and_replace_workout, api, workout_json)


async def get_weekly_report_data(api) -> dict:
    """Logic for /report command (Integrated with /status info).
    
    Returns:
        Dict with 'caption' and 'photo_path' (temp file), or 'error'.
    """
    loop = asyncio.get_event_loop()
    # Fetch comprehensive data for past 7 days for the chart
    daily_list = await loop.run_in_executor(None, garmin.get_comprehensive_daily_stats, api, 7)
    
    if daily_list and isinstance(daily_list[0], dict) and "error" in daily_list[0]:
        return {"error": daily_list[0]["error"]}

    # Fetch sport-specific summaries (次数, 里程, 时间, 心率)
    weekly_summary = await loop.run_in_executor(None, garmin.get_weekly_summary, api)
    
    # Fetch upcoming schedule
    upcoming = await loop.run_in_executor(None, garmin.get_upcoming_schedule, api)

    chart_url = visualizer.get_weekly_chart_url(daily_list)
    
    # Download the chart to a temp file
    temp_dir = tempfile.mkdtemp()
    photo_path = os.path.join(temp_dir, "weekly_report.png")
    
    try:
        def download():
            response = requests.get(chart_url, timeout=20)
            if response.status_code == 200:
                with open(photo_path, "wb") as f:
                    f.write(response.content)
                return True
            return False

        success = await loop.run_in_executor(None, download)
        if not success:
            shutil.rmtree(temp_dir, ignore_errors=True)
            return {"error": "無法從 QuickChart 下載綜合圖表圖片"}
            
    except Exception as e:
        shutil.rmtree(temp_dir, ignore_errors=True)
        return {"error": f"下載圖表發生錯誤: {e}"}

    # Find latest valid metrics (non-zero load/hrv/bb) for the top summary
    latest_metrics = daily_list[-1]
    for d in reversed(daily_list):
        if d.get('training_load', 0) > 0 or d.get('hrv', 0) > 0 or d.get('body_battery', 0) > 0:
            latest_metrics = d
            break

    # 1. Format sport-specific summaries
    sport_texts = []
    if "summary" in weekly_summary:
        for sport, data in weekly_summary["summary"].items():
            hr_line = f"{data['avg_hr']} bpm" if data["avg_hr"] > 0 else "N/A"
            sport_texts.append(
                f"🏃 **{sport}**: {data['runs_count']}次 | {data['total_distance_km']}km | {data['total_duration_min']}分 | {hr_line}"
            )
    sport_summary_text = "\n".join(sport_texts) if sport_texts else "• 過去 7 天無運動紀錄"

    # 2. Format recovery and load metrics
    latest_load = latest_metrics.get('training_load', 0)
    latest_ctl = latest_metrics.get('chronic_load', 0)
    latest_ratio = round(latest_metrics.get('load_ratio', 0) * 100)
    latest_hrv = latest_metrics.get('hrv', 0)
    latest_bb = latest_metrics.get('body_battery', 0)
    
    tsb = round(latest_ctl - latest_load, 1)
    
    # 3. Format upcoming schedule
    schedule_texts = []
    for item in upcoming:
        d_obj = datetime.date.fromisoformat(item["date"])
        d_str = d_obj.strftime("%m/%d")
        weekday_cn = ["一", "二", "三", "四", "五", "六", "日"][d_obj.weekday()]

        w = item["workout"]
        if w:
            name = (
                w.get("title") or w.get("workoutName") or "未命名課表"
            )
            schedule_texts.append(f"• {d_str} ({weekday_cn}): {name}")
        else:
            schedule_texts.append(f"• {d_str} ({weekday_cn}): 休息 ☕")
    schedule_text = "\n".join(schedule_texts)

    caption = (
        f"📊 **綜合訓練週報**\n\n"
        f"{sport_summary_text}\n\n"
        f"❤️ 昨夜 HRV：{latest_hrv} ms\n"
        f"🔋 Body Battery：{latest_bb}%\n"
        f"📈 訓練負荷：{latest_load} (TSB: {tsb} | 負荷比: {latest_ratio}%)\n\n"
        f"📅 **接下來課表**\n"
        f"{schedule_text}"
    )
    
    return {
        "caption": caption,
        "photo_path": photo_path,
        "temp_dir": temp_dir
    }


async def recommend_training_level(api) -> dict:
    """Analyze past 4 weeks of running data and recommend a training level.

    Returns:
        Dict with 'avg_weekly_km' and 'recommended_level'.
    """
    loop = asyncio.get_event_loop()
    # Fetch 28 days (4 weeks) of daily stats
    daily_list = await loop.run_in_executor(None, garmin.get_comprehensive_daily_stats, api, 28)

    if not daily_list or (isinstance(daily_list[0], dict) and "error" in daily_list[0]):
        return {"error": daily_list[0].get("error", "無法獲取數據") if daily_list else "無數據"}

    total_km = sum(d.get("distance_km", 0) for d in daily_list)
    avg_weekly_km = round(total_km / 4, 1)

    # Recommendation logic:
    # < 35 km/週 ➔ 入門 (WHITE)
    # 35 ~ 65 km/週 ➔ 中階 (RED)
    # 65 ~ 95 km/週 ➔ 進階 (BLUE)
    # > 95 km/週 ➔ 菁英 (GOLD)

    if avg_weekly_km < 35:
        level_code = "WHITE"
        level_name = "入門"
    elif avg_weekly_km < 65:
        level_code = "RED"
        level_name = "中階"
    elif avg_weekly_km < 95:
        level_code = "BLUE"
        level_name = "進階"
    else:
        level_code = "GOLD"
        level_name = "菁英"

    return {
        "avg_weekly_km": avg_weekly_km,
        "recommended_level_code": level_code,
        "recommended_level_name": level_name
    }


async def get_profile_summary(include_insights: bool = True) -> str:
    """Logic for /profile command."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, athlete_profile.format_profile_summary, None, include_insights)

async def get_goal_summary(subcommand: str, args: List[str]) -> str:
    """Logic for /goal command."""
    if subcommand == "set":
        if len(args) < 2:
            return (
                "❌ 格式錯誤。\n\n"
                "使用方式：`/goal set YYYY-MM-DD 距離 [賽事名稱] [目標時間]`\n"
                "範例：`/goal set 2026-12-20 42 台北馬拉松 03:30:00`"
            )
        try:
            race_date_str = args[0]
            datetime.date.fromisoformat(race_date_str)  # validate format
            dist_km = athlete_profile.parse_distance(args[1])
            
            # Handle variable args for name and time
            # Check if last arg is a time format
            target_time = None
            if len(args) >= 4 and ":" in args[-1]:
                target_time = args[-1]
                race_name = " ".join(args[2:-1])
            else:
                race_name = " ".join(args[2:]) if len(args) > 2 else ""
        except (ValueError, IndexError) as e:
            return f"❌ 輸入格式有誤：{str(e)}"

        goal = athlete_profile.save_goal(race_date_str, dist_km, race_name, target_time)
        days = athlete_profile.get_days_remaining(race_date_str)
        dist_str = athlete_profile.format_distance(dist_km)
        display_name = race_name or dist_str
        time_msg = f"\n• 目標時間：{target_time}" if target_time else ""
        return (
            f"🎯 **賽事目標已儲存！**\n\n"
            f"• 賽事：{display_name}\n"
            f"• 距離：{dist_str}\n"
            f"• 日期：{race_date_str}{time_msg}\n"
            f"• 距今：**{days} 天**\n"
            f"• 訓練階段：{athlete_profile.get_training_phase_name(days)}"
        )
    else:
        # show
        goal = athlete_profile.load_goal()
        if not goal or not goal.get("race_date"):
            return (
                "📭 尚未設定賽事目標。\n\n"
                "使用 `/goal set YYYY-MM-DD 距離` 設定\n"
                "例：`/goal set 2026-11-01 42`"
            )

        days = athlete_profile.get_days_remaining(goal["race_date"])
        dist_str = athlete_profile.format_distance(goal["race_distance_km"])
        display_name = goal.get("race_name") or dist_str

        if days < 0:
            countdown = f"⏰ 賽事已於 {abs(days)} 天前結束"
        elif days == 0:
            countdown = "🏁 **今日就是比賽日！全力以赴！**"
        else:
            countdown = f"⏰ 距離賽事還有 **{days} 天**"

        summary = (
            f"🎯 **賽事目標**\n\n"
            f"• 賽事：{display_name}\n"
            f"• 距離：{dist_str}\n"
            f"• 日期：{goal['race_date']}\n\n"
            f"{countdown}\n"
            f"• 訓練階段：{athlete_profile.get_training_phase_name(days)}"
        )

        # --- Add Goal Projection ---
        profile = athlete_profile.load_profile()
        projection = performance_vdot.calculate_goal_projection(profile)
        if projection and projection.get("status") != "expired":
            summary += "\n\n📈 **目標達成預測**\n"
            if projection.get("status") == "no_target_time":
                summary += "• 目前尚未設定「目標時間」，預估無法進行精準達標預測。請使用 `/setup` 或 `/goal set` 補充。"
            else:
                summary += (
                    f"• 目標跑力 (Target VDOT): {projection['target_vdot']}\n"
                    f"• 目前跑力 (Current VDOT): {projection['current_vdot']}\n"
                    f"• VDOT 差距: {projection['vdot_gap']}\n"
                    f"• 達成難度: {projection['difficulty']}\n"
                    f"• 建議：{projection['suggestion']}"
                )
        
        return summary


async def handle_achievements(api) -> tuple[str, Optional[str]]:
    """Handle /achievements command.
    
    Returns:
        tuple (text_response, photo_path)
    """
    loop = asyncio.get_event_loop()
    
    # 1. Fetch multi-year history and generate QoQ chart
    try:
        history = await loop.run_in_executor(None, garmin.get_multi_year_activity_history, api)
        photo_path = "tmp/achievements_qoq.png"
        chart_success = await loop.run_in_executor(None, visualizer.generate_qoq_chart, history, photo_path)
        if not chart_success:
            photo_path = None
    except Exception as e:
        logger.error(f"Failed to generate achievement chart: {e}")
        photo_path = None

    # 2. Textual summary: Shoe Lifespan
    profile = athlete_profile.load_profile()
    shoes = profile.get("shoes", [])
    active_shoes = [s for s in shoes if s.get("status") == "active"]
    
    shoe_text = ""
    if active_shoes:
        shoe_text = "\n\n👟 **跑鞋壽命管理**\n"
        for s in active_shoes:
            curr = s.get("current_km", 0)
            target = s.get("target_km", 500)
            pct = (curr / target) * 100 if target > 0 else 0
            
            # Health indicator
            indicator = "🟢"
            if pct > 95: indicator = "🔴 建議更換"
            elif pct > 80: indicator = "🟡 接近壽命"
            
            shoe_text += f"• {s['nickname']}: {curr:.1f} / {target} km ({pct:.1f}%) {indicator}\n"

    # 3. Overall stats summary (Total Mileage)
    total_km = 0
    for y_data in history.values():
        for q_data in y_data.values():
            total_km += sum(q_data.values())

    response = (
        "🏆 **個人成就看板**\n\n"
        f"📊 **長期數據：跨年度季度對比 (QoQ)**\n"
        f"• 歷史總跑量：{total_km:,.1f} km\n"
        f"• 數據包含年度：{', '.join(map(str, sorted(history.keys())))}"
        f"{shoe_text}"
    )
    
    return response, photo_path


# ---------------------------------------------------------------------------
# Background Polling Logic
# ---------------------------------------------------------------------------

async def run_post_run_polling(
    get_api_func: Callable[[], Any],
    send_message_func: Callable[[str, Optional[Any], Optional[str], Optional[str]], Coroutine[Any, Any, Optional[int]]],
    poll_interval: int = 900
):
    """Periodically check for new Garmin activities and trigger analysis.
    
    Args:
        get_api_func: Function that returns an authenticated Garmin API object.
        send_message_func: Async function to send a message (text, keyboard, session_id, photo_path). 
                           Returns message_id if successful.
        poll_interval: Seconds between checks.
    """
    last_known_id = load_last_activity_id()
    logger.info(f"Post-run polling task started. Last known ID: {last_known_id}")
    
    while True:
        try:
            api = get_api_func()
            if not api:
                logger.warning("Garmin API not available, skipping check.")
            else:
                # 1. Check HRV Guardrail (Proactive recovery alert)
                async def send_simple(text: str):
                    await send_message_func(text, None, None, None)
                await hrv_guardrail.run_hrv_guardrail_check(api, send_simple)

                # 2. Check for new activities (Post-run analysis)
                loop = asyncio.get_event_loop()
                activity = await loop.run_in_executor(None, garmin.get_latest_activity, api)

                if activity:
                    activity_id = str(activity.get("activityId", ""))
                    if activity_id != last_known_id:
                        act_type = activity.get("activityType", {}).get("typeKey", "")
                        if act_type in ("running", "treadmill_running"):
                            # Update last activity date in profile
                            profile = athlete_profile.load_profile()
                            profile["last_activity_date"] = activity.get("startTimeLocal", "")[:10]
                            athlete_profile.save_profile(profile)

                            workout_detail = await match_activity_with_workout(api, activity)
                            session_id = uuid.uuid4().hex
                            prompt = await compose_analysis_prompt(api, activity, workout_detail)
                            
                            # Execute Gemini CLI with session_id
                            cmd = ["gemini", "--skip-trust", "--approval-mode", "yolo", "--session-id", session_id, "-p", prompt]
                            process = await asyncio.create_subprocess_exec(
                                *cmd,
                                stdin=asyncio.subprocess.DEVNULL,
                                stdout=asyncio.subprocess.PIPE,
                                stderr=asyncio.subprocess.PIPE,
                            )
                            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=180.0)
                            output = stdout.decode().strip()
                            
                            if output:
                                date_str = activity.get("startTimeLocal", "")[:10]
                                dist_km = round(activity.get("distance", 0) / 1000, 2)
                                dur_min = round(activity.get("duration", 0) / 60, 1)
                                avg_hr = activity.get("averageHR", "N/A")
                                
                                header = (
                                    f"🏃 *跑後自動分析* — {date_str}\n"
                                    f"📏 {dist_km} km ｜ ⏱ {dur_min} 分 ｜ ❤️ {avg_hr} bpm\n\n"
                                )

                                # --- Match Workout and Generate Activity Chart ---
                                chart_path = None
                                try:
                                    workout_detail = await match_activity_with_workout(api, activity)
                                    # Save to a temporary location
                                    temp_chart = os.path.join(tempfile.gettempdir(), f"chart_{activity_id}.png")
                                    chart_path = await loop.run_in_executor(None, visualizer.generate_activity_chart, api, activity, temp_chart, workout_detail)
                                except Exception as e:
                                    logger.error(f"Failed to generate post-run chart: {e}")

                                # Highlight detection for FB Post collaboration
                                is_highlight, reason = is_highlight_activity(activity)
                                highlight_keyboard = None
                                if is_highlight:
                                    highlight_keyboard = [[{"text": "✨ 生成 FB 貼文草稿", "callback_data": f"gen_fb_post:{activity_id}"}]]

                                # Send analysis and associate session
                                await send_message_func(header + output, highlight_keyboard, session_id, chart_path)
                                
                                # Send RPE follow-up and associate with the SAME session
                                rpe_text = "*教練詢問*：這趟跑起來體感如何？請點選 RPE 強度（1 最輕鬆，10 全力）："
                                rpe_keyboard = get_rpe_keyboard_data(activity_id)
                                await send_message_func(rpe_text, rpe_keyboard, session_id, None)

                                # --- New: Shoe Selection ---
                                shoe_keyboard = get_shoe_selection_keyboard(activity_id)
                                if shoe_keyboard:
                                    shoe_text = "*教練詢問*：這趟訓練是穿哪雙跑鞋呢？點選即可自動累計里程："
                                    await send_message_func(shoe_text, shoe_keyboard, session_id, None)
                                
                            last_known_id = activity_id
                            save_last_activity_id(activity_id)
                            logger.info(f"New activity processed: {activity_id}")

                            # --- Performance-Driven VDOT Logic ---
                            try:
                                session_vdot = performance_vdot.calculate_session_vdot(activity, profile)
                                if session_vdot:
                                    performance_vdot.update_vdot_tracking(session_vdot)
                                    logger.info(f"Session VDOT recorded: {session_vdot['vdot_est']} (conf: {session_vdot['confidence']})")
                                    
                                    # Check for trend
                                    vdot_trend = performance_vdot.analyze_vdot_trend()
                                    if vdot_trend:
                                        v_msg = (
                                            f"📈 *教練觀察：跑力進化偵測*\n\n"
                                            f"數據顯示您最近的訓練表現已超越目前的設定：\n"
                                            f"• 目前 VDOT: {vdot_trend['current_vdot']}\n"
                                            f"• 數據偵測值: *{vdot_trend['avg_vdot']}*\n\n"
                                            f"💡 {vdot_trend['reason']}\n"
                                            f"為了確保配速精準，**請問您最近的體感如何？**"
                                        )
                                        v_keyboard = [
                                            [{"text": "🔵 體感穩定，按數據調升", "callback_data": f"vdot_upgrade:full:{vdot_trend['avg_vdot']}"}],
                                            [{"text": "🟡 那是全力拚搏 (調升減半)", "callback_data": f"vdot_upgrade:half:{vdot_trend['avg_vdot']}"}],
                                            [{"text": "🔴 數據異常/心率飄移", "callback_data": "vdot_upgrade:skip"}]
                                        ]
                                        await send_message_func(v_msg, v_keyboard, session_id, None)
                            except Exception as ve:
                                logger.error(f"Performance VDOT calculation failed: {ve}")
                        else:
                            logger.info(f"New activity {activity_id} is {act_type}, skipping.")
        except Exception as e:
            logger.error(f"Polling error: {e}")
            
        await asyncio.sleep(poll_interval)

async def search_personalized_memory(query: str) -> str:
    """Search for relevant athlete history using contextual-memory or fallback to local JSON.
    
    Args:
        query: The search query (e.g. current activity highlights or athlete concerns).
        
    Returns:
        Formatted string of relevant insights.
    """
    # 1. Try Vector Search (contextual-memory skill)
    skill_search_script = SKILL_DIR.parent / "contextual-memory" / "scripts" / "search_memory.py"
    
    if skill_search_script.exists():
        try:
            import subprocess
            cmd = ["python3", str(skill_search_script), "--query", query, "--type", "running-coach", "--top", "3"]
            result = subprocess.run(cmd, capture_output=True, text=True, check=False)
            if result.returncode == 0 and result.stdout.strip() and "Top" in result.stdout:
                # Clean up output to be more prompt-friendly
                output = result.stdout.strip()
                return f"\n[相關長期記憶 (向量檢索)]:\n{output}\n"
        except Exception as e:
            logger.warning(f"Vector search failed: {e}. Falling back to JSON.")

    # 2. Fallback: Local JSON insights from athlete_profile
    insights = athlete_profile.get_long_term_insights()
    if insights:
        # Simple keyword matching for basic "fallback" retrieval
        query_words = set(re.findall(r'\w+', query.lower()))
        relevant = []
        for i in insights:
            content = i.get("content", "")
            if any(word in content.lower() for word in query_words) or len(relevant) < 3:
                relevant.append(f"• {i.get('date', '')} [{i.get('category', 'general')}]: {content}")
        
        if relevant:
            return f"\n[相關長期記憶 (JSON 回退)]:\n" + "\n".join(relevant[:5]) + "\n"
            
    return ""

async def match_activity_with_workout(api, activity: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Match an activity with today's scheduled workout based on name."""
    loop = asyncio.get_event_loop()
    workout_item = await loop.run_in_executor(None, garmin.get_today_scheduled_workout, api)
    
    if not workout_item or (isinstance(workout_item, dict) and "error" in workout_item):
        return None
        
    act_name = activity.get("activityName", "")
    workout_name = workout_item.get("title") or workout_item.get("workoutName") or ""
    
    # Strip emojis and common prefixes/suffixes for matching
    def clean_name(name):
        # Strip emojis
        name = re.sub(r'[^\x00-\x7F\u4e00-\u9fa5\u3000-\u303f\uff00-\uffef]', '', name)
        return name.strip().lower()
        
    c_act = clean_name(act_name)
    c_work = clean_name(workout_name)
    
    if c_work and c_work in c_act:
        workout_id = workout_item.get("workoutId")
        if workout_id:
            return await loop.run_in_executor(None, garmin.get_workout_details, api, workout_id)
            
    return None


async def compose_analysis_prompt(api, activity: Dict[str, Any], workout_detail: Optional[Dict[str, Any]] = None) -> str:
    """Compose a detailed prompt for Gemini analysis based on activity data."""
    loop = asyncio.get_event_loop()
    
    activity_id = str(activity.get("activityId", ""))
    dist_km = round(activity.get("distance", 0) / 1000, 2)
    dur_min = round(activity.get("duration", 0) / 60, 1)
    avg_hr = activity.get("averageHR", "N/A")
    max_hr = activity.get("maxHR", "N/A")
    avg_speed = activity.get("averageSpeed", 0)
    max_speed = activity.get("maxSpeed", 0)
    
    # Dynamics (List API keys)
    cadence = activity.get("averageRunningCadence") or activity.get("averageRunningCadenceInStepsPerMinute") or activity.get("averageRunCadence", "N/A")
    stride = activity.get("avgStrideLength") or activity.get("strideLength", "N/A")
    
    te_label = activity.get("trainingEffectLabel", "N/A")
    ae_te = activity.get("aerobicTrainingEffect", "N/A")
    an_te = activity.get("anaerobicTrainingEffect", "N/A")

    name = activity.get("activityName", "跑步活動")
    date_str = activity.get("startTimeLocal", "")[:10]

    avg_pace_str = speed_to_pace(avg_speed)
    max_pace_str = speed_to_pace(max_speed)

    # Workout Target info
    workout_target_text = ""
    if workout_detail:
        flat_steps = garmin.flatten_workout_steps(workout_detail)
        workout_target_text = "\n[預定課表目標]:\n"
        for i, step in enumerate(flat_steps):
            t_type = step.get("targetType", {}).get("workoutTargetTypeKey")
            v1 = step.get("targetValueOne")
            v2 = step.get("targetValueTwo")
            note = step.get("description", "") or step.get("note", "")
            
            target_desc = "無目標"
            if t_type == "pace.zone":
                p1, p2 = speed_to_pace(v1), speed_to_pace(v2)
                # Ensure correct order for range
                target_desc = f"配速 {p1} ~ {p2}"
            elif t_type == "heart.rate.zone":
                target_desc = f"心率 {int(min(v1, v2))} ~ {int(max(v1, v2))} bpm"
            
            workout_target_text += f"  - 步驟 {i+1}: {target_desc} ({note})\n"

    # Fetch Weather Data based on Coordinates
    weather_text = ""
    heat_factor = 1.0
    lat = activity.get("startLatitude")
    lon = activity.get("startLongitude")
    if lat is not None and lon is not None:
        try:
            obs = await loop.run_in_executor(None, weather.get_weather_by_coords, lat, lon)
            if obs:
                weather_text = (
                    f"環境狀況 (觀測站: {obs['station_name']}):\n"
                    f"• 氣溫: {obs['temp']}°C, 濕度: {obs['humidity']}%\n"
                    f"• 風速: {obs['wind_speed']} m/s, 距離起點: {obs['distance_km']} km\n"
                )
                try:
                    t = float(obs['temp'])
                    h = float(obs.get('humidity', 50.0))
                    heat_factor = performance_vdot.get_heat_adjustment_factor(t, h)
                except: pass
        except Exception as we:
            logger.warning(f"Failed to fetch weather for coordinates {lat}, {lon}: {we}")

    # Fetch Recovery Data for Dynamic Guardrail
    recovery = await loop.run_in_executor(None, garmin.get_hrv_and_recovery, api)
    recovery_text = ""
    rtype = recovery.get("type", "unavailable")
    if rtype == "hrv":
        recovery_text = f"昨夜 HRV: {recovery.get('last_night', 'N/A')} ms (狀態: {recovery.get('status', 'unknown')})"
    elif rtype == "body_battery":
        recovery_text = f"Body Battery: {recovery.get('level', 'N/A')}%"

    # Fetch Race Goal
    goal = athlete_profile.load_goal()
    goal_text = ""
    if goal and goal.get("race_date"):
        days = athlete_profile.get_days_remaining(goal["race_date"])
        dist_str = athlete_profile.format_distance(goal["race_distance_km"])
        goal_text = f"近期賽事目標: {goal.get('race_name', dist_str)} ({dist_str}), 日期: {goal['race_date']} (距今 {days} 天, 階段: {athlete_profile.get_training_phase_name(days)})"

    prompt = (
        f"請作為跑步教練，分析以下這場剛完成的活動數據：\n\n"
        f"活動名稱: {name} ({date_str})\n"
        f"距離: {dist_km} km\n"
        f"時間: {dur_min} 分鐘\n"
        f"平均配速: {avg_pace_str}\n"
        f"平均心率: {avg_hr} bpm (Max: {max_hr})\n"
        f"訓練效果: {te_label} (Aerobic: {ae_te}, Anaerobic: {an_te})\n"
        f"平均步頻: {cadence} spm\n"
        f"平均步幅: {stride} m\n"
        f"{workout_target_text}\n"
        f"{weather_text}\n"
        f"{recovery_text}\n"
        f"{goal_text}\n"
        f"跑力修正係數 (Heat Factor): {heat_factor:.3f} (1.0 代表理想氣候，越高代表環境壓力越大)\n\n"
        "分析指令：\n"
        "1. **科學化評價**：根據配速、心率與環境壓力 (Heat Factor) 給予評價。如果 Heat Factor > 1.02，請務必強調「考慮到熱壓力，您的表現優於帳面數據」。\n"
        "2. **體感對標**：推測跑者的體感 (RPE)，並給予針對性的恢復或調整建議。\n"
        "3. **互動引導**：在結尾用語音或溫暖的語氣，引導跑者分享當下的心情或任何異常的體感（如：腿感、疲勞度）。\n"
        "請保持專業、鼓勵且具有『共同學習』的特質，字數約 150-200 字。"
    )


    # Try to fetch laps for context
    try:
        laps_text = ""
        splits_data = await loop.run_in_executor(None, api.get_activity_splits, int(activity_id))
        laps = splits_data.get("lapDTOs", [])
        if laps:
            laps_text = "\n  [分段 (Laps) 資料]:\n"
            for lap in laps:
                lap_idx = lap.get("lapIndex", 0)
                l_dist = lap.get("distance", 0) / 1000.0
                l_dur = lap.get("duration", 0) / 60.0
                l_speed = lap.get("averageSpeed", 0)
                l_hr = lap.get("averageHR", "N/A")
                l_cadence = lap.get("averageRunCadence", "N/A")
                l_stride = lap.get("strideLength", "N/A")
                l_pace = speed_to_pace(l_speed)
                laps_text += f"    - L{lap_idx}: {l_dist:.2f}km | {l_dur:.1f}分 | 配速 {l_pace}/km | 心率 {l_hr} | 步頻 {l_cadence} | 步幅 {l_stride}\n"
            prompt += laps_text
    except Exception as e:
        logger.warning(f"Could not fetch laps for activity {activity_id}: {e}")

    # Add athlete profile context (exclude insights here to avoid duplication)
    profile_summary = await get_profile_summary(include_insights=False)
    prompt += f"\n[跑者個人檔案與近期狀態]:\n{profile_summary}\n"
    
    # Add Long-term Personalized Memory (This becomes the ONLY source for insights in the prompt)
    memory_query = f"{name} {dist_km}km {te_label} {recovery_text}"
    memory_context = await search_personalized_memory(memory_query)
    prompt += memory_context

    prompt += (
        "\n請針對本次跑感、強度、恢復狀況以及與目標賽事的關聯，提供具體分析與下一次訓練的動態建議。\n"
        "特別注意：請務必根據「長期記憶」中提到的跑者偏好或過往病史進行個性化提醒（例如：避免在特定痛點復發時衝強度）。\n"
        "如果分析中發現了值得記錄為「長期特質」的新發現（例如：發現跑者在雨天配速反而更穩、或某種補給策略很有效），請在回覆結尾主動詢問跑者是否要將此特質記錄到長期記憶中（例如：『教練發現您...，是否需要教練幫您記錄下來呢？』）。請勿輸出任何 shell script 或程式碼指令。"
    )
    return prompt
