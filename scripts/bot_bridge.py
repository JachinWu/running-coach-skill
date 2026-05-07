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
from pathlib import Path
from typing import Optional, List, Dict, Any, Callable, Coroutine

# Import sibling modules
try:
    from . import garmin
    from . import race_goal
    from . import athlete_profile
except ImportError:
    import garmin
    import race_goal
    import athlete_profile

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Paths and Persistence
# ---------------------------------------------------------------------------
SKILL_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = SKILL_DIR / "data"
LAST_ACTIVITY_FILE = DATA_DIR / "last_activity.json"

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

def speed_to_pace(speed_ms: float) -> str:
    """Convert speed in m/s to pace (min:sec) per km."""
    if not speed_ms or speed_ms <= 0:
        return "0:00"
    total_seconds = 1000 / speed_ms
    minutes = int(total_seconds // 60)
    seconds = int(total_seconds % 60)
    return f"{minutes}:{seconds:02d}"

# ---------------------------------------------------------------------------
# Command Logic Handlers
# ---------------------------------------------------------------------------

async def get_today_summary(api) -> str:
    """Logic for /today command."""
    loop = asyncio.get_event_loop()
    workout = await loop.run_in_executor(None, garmin.get_today_scheduled_workout, api)
    
    today_label = datetime.date.today().strftime("%Y/%m/%d")
    if workout is None:
        return f"📅 <b>{today_label}</b>\n\n✅ 今日為休息日，好好恢復！"
    elif isinstance(workout, dict) and "error" in workout:
        return f"❌ 查詢失敗：{escape_html(workout['error'])}"
    else:
        name = escape_html(
            workout.get("title") or workout.get("workoutName") or "未命名課表"
        )
        description = workout.get("description", "")
        text = f"📅 <b>今日課表 ({today_label})</b>\n\n🏃 <b>{name}</b>"
        if description:
            if len(description) > 300:
                description = description[:300] + "..."
            text += f"\n\n📝 {escape_html(description)}"
        return text

async def get_status_summary(api) -> str:
    """Logic for /status command."""
    loop = asyncio.get_event_loop()
    weekly = await loop.run_in_executor(None, garmin.get_weekly_summary, api)
    recovery = await loop.run_in_executor(None, garmin.get_hrv_and_recovery, api)
    upcoming = await loop.run_in_executor(None, garmin.get_upcoming_schedule, api)

    # Weekly block
    if "error" in weekly:
        week_text = f"📊 <b>過去 7 天訓練摘要</b>\n❌ 查詢失敗：{escape_html(weekly['error'])}"
    else:
        week_text = f"📊 <b>過去 7 天訓練摘要</b>"
        summary_data = weekly.get("summary", {})
        if not summary_data:
            week_text += "\n• 過去 7 天無運動紀錄"
        else:
            for act_name, data in summary_data.items():
                hr_line = f"{data['avg_hr']} bpm" if data["avg_hr"] > 0 else "N/A"
                week_text += (
                    f"\n🏃 <b>{act_name}</b>"
                    f"\n  • 次數：{data['runs_count']} 次"
                    f"\n  • 里程：{data['total_distance_km']} km"
                    f"\n  • 時間：{data['total_duration_min']} 分鐘"
                    f"\n  • 平均心率：{hr_line}"
                )

    # Schedule block
    schedule_text = "\n\n📅 <b>接下來課表</b>"
    if upcoming and isinstance(upcoming[0], dict) and "error" in upcoming[0]:
        schedule_text += f"\n❌ 查詢失敗：{escape_html(upcoming[0]['error'])}"
    else:
        for item in upcoming:
            d_obj = datetime.date.fromisoformat(item["date"])
            d_str = d_obj.strftime("%m/%d")
            weekday_cn = ["一", "二", "三", "四", "五", "六", "日"][d_obj.weekday()]

            w = item["workout"]
            if w:
                name = escape_html(
                    w.get("title") or w.get("workoutName") or "未命名課表"
                )
                schedule_text += f"\n• {d_str} ({weekday_cn}): {name}"
            else:
                schedule_text += f"\n• {d_str} ({weekday_cn}): 休息 ☕"

    # Recovery block
    rtype = recovery.get("type", "unavailable")
    if rtype == "hrv":
        raw_status = recovery.get("status", "unknown").lower()
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

        recovery_text = (
            f"\n\n❤️ <b>HRV 恢復狀態</b> {emoji}\n"
            f"• 昨夜 HRV：{recovery.get('last_night', 'N/A')} ms\n"
            f"• 週平均 HRV：{recovery.get('weekly_avg', 'N/A')} ms\n"
            f"• 狀態：{status_cn}"
        )
    elif rtype == "body_battery":
        level: int = recovery.get("level") or 0
        if level >= 70:
            bb_emoji, advice = "🔋✅", "狀態良好，可進行高強度訓練"
        elif level >= 40:
            bb_emoji, advice = "🔋⚠️", "中等恢復，建議輕鬆訓練"
        else:
            bb_emoji, advice = "🔋❌", "恢復不足，建議今日休息"
        recovery_text = f"\n\n{bb_emoji} <b>Body Battery：{level}%</b>\n• {advice}"
    else:
        recovery_text = (
            f"\n\n⚠️ {escape_html(recovery.get('error', '恢復數據不可用'))}"
        )

    return week_text + schedule_text + recovery_text

async def get_profile_summary() -> str:
    """Logic for /profile command."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, athlete_profile.format_profile_summary)

async def get_goal_summary(subcommand: str, args: List[str]) -> str:
    """Logic for /goal command."""
    if subcommand == "set":
        if len(args) < 2:
            return (
                "❌ 格式錯誤。\n\n"
                "使用方式：<code>/goal set YYYY-MM-DD 距離 [賽事名稱]</code>\n"
                "範例：<code>/goal set 2026-11-01 42 台北馬拉松</code>"
            )
        try:
            race_date_str = args[0]
            datetime.date.fromisoformat(race_date_str)  # validate format
            distance_km = race_goal.parse_distance(args[1])
            race_name = " ".join(args[2:]) if len(args) > 2 else ""
        except (ValueError, IndexError) as e:
            return f"❌ 輸入格式有誤：{escape_html(str(e))}"

        goal = race_goal.save_goal(race_date_str, distance_km, race_name)
        days = race_goal.get_days_remaining(goal)
        dist_str = race_goal.format_distance(distance_km)
        display_name = race_name or dist_str
        return (
            f"🎯 <b>賽事目標已儲存！</b>\n\n"
            f"• 賽事：{escape_html(display_name)}\n"
            f"• 距離：{escape_html(dist_str)}\n"
            f"• 日期：{escape_html(race_date_str)}\n"
            f"• 距今：<b>{days} 天</b>\n"
            f"• 訓練階段：{escape_html(race_goal.get_training_phase(days))}"
        )
    else:
        # show
        goal = race_goal.load_goal()
        if not goal or not goal.get("race_date"):
            return (
                "📭 尚未設定賽事目標。\n\n"
                "使用 <code>/goal set YYYY-MM-DD 距離</code> 設定\n"
                "例：<code>/goal set 2026-11-01 42</code>"
            )

        days = race_goal.get_days_remaining(goal)
        dist_str = race_goal.format_distance(goal["race_distance_km"])
        display_name = goal.get("race_name") or dist_str

        if days < 0:
            countdown = f"⏰ 賽事已於 {abs(days)} 天前結束"
        elif days == 0:
            countdown = "🏁 <b>今日就是比賽日！全力以赴！</b>"
        else:
            countdown = f"⏰ 距離賽事還有 <b>{days} 天</b>"

        return (
            f"🎯 <b>賽事目標</b>\n\n"
            f"• 賽事：{escape_html(display_name)}\n"
            f"• 距離：{escape_html(dist_str)}\n"
            f"• 日期：{escape_html(goal['race_date'])}\n\n"
            f"{countdown}\n"
            f"• 訓練階段：{escape_html(race_goal.get_training_phase(days))}"
        )

# ---------------------------------------------------------------------------
# Background Polling Logic
# ---------------------------------------------------------------------------

async def run_post_run_polling(
    get_api_func: Callable[[], Any],
    send_message_func: Callable[[str], Coroutine[Any, Any, None]],
    poll_interval: int = 900
):
    """Periodically check for new Garmin activities and trigger analysis.
    
    Args:
        get_api_func: Function that returns an authenticated Garmin API object.
        send_message_func: Async function to send a message to the user.
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
                loop = asyncio.get_event_loop()
                activity = await loop.run_in_executor(None, garmin.get_latest_activity, api)

                if activity:
                    activity_id = str(activity.get("activityId", ""))
                    if activity_id != last_known_id:
                        act_type = activity.get("activityType", {}).get("typeKey", "")
                        if act_type in ("running", "treadmill_running"):
                            prompt = await compose_analysis_prompt(api, activity)
                            
                            # Execute Gemini CLI
                            cmd = ["gemini", "--skip-trust", "--approval-mode", "yolo", "-p", prompt]
                            process = await asyncio.create_subprocess_exec(
                                *cmd,
                                stdin=asyncio.subprocess.DEVNULL,
                                stdout=asyncio.subprocess.PIPE,
                                stderr=asyncio.subprocess.PIPE,
                            )
                            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=180.0)
                            output = stdout.decode().strip()
                            # (Optional: clean ANSI codes if the wrapper doesn't)
                            
                            if output:
                                date_str = activity.get("startTimeLocal", "")[:10]
                                dist_km = round(activity.get("distance", 0) / 1000, 2)
                                dur_min = round(activity.get("duration", 0) / 60, 1)
                                avg_hr = activity.get("averageHR", "N/A")
                                
                                header = (
                                    f"🏃 *跑後自動分析* — {date_str}\n"
                                    f"📏 {dist_km} km ｜ ⏱ {dur_min} 分 ｜ ❤️ {avg_hr} bpm\n\n"
                                )
                                await send_message_func(header + output)
                                
                                last_known_id = activity_id
                                save_last_activity_id(activity_id)
                        else:
                            logger.info(f"New activity {activity_id} is {act_type}, skipping.")
        except Exception as e:
            logger.error(f"Polling error: {e}")
            
        await asyncio.sleep(poll_interval)

async def compose_analysis_prompt(api, activity: Dict[str, Any]) -> str:
    """Compose a detailed prompt for Gemini analysis based on activity data."""
    activity_id = str(activity.get("activityId", ""))
    dist_km = round(activity.get("distance", 0) / 1000, 2)
    dur_min = round(activity.get("duration", 0) / 60, 1)
    avg_hr = activity.get("averageHR", "N/A")
    max_hr = activity.get("maxHR", "N/A")
    avg_speed = activity.get("averageSpeed", 0)
    max_speed = activity.get("maxSpeed", 0)
    cadence = activity.get("averageRunCadence", "N/A")
    stride = activity.get("strideLength", "N/A")
    te_label = activity.get("trainingEffectLabel", "N/A")
    ae_te = activity.get("aerobicTrainingEffect", "N/A")
    an_te = activity.get("anaerobicTrainingEffect", "N/A")

    name = activity.get("activityName", "跑步活動")
    date_str = activity.get("startTimeLocal", "")[:10]

    avg_pace_str = speed_to_pace(avg_speed)
    max_pace_str = speed_to_pace(max_speed)

    # Try to fetch laps for context
    laps_text = ""
    try:
        loop = asyncio.get_event_loop()
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
    except Exception as e:
        logger.warning(f"Could not fetch laps for activity {activity_id}: {e}")

    prompt = (
        f"我剛完成一次跑步訓練（{date_str}）：\n"
        f"  名稱: {name}\n"
        f"  距離: {dist_km} km\n"
        f"  時間: {dur_min} 分鐘\n"
        f"  平均心率: {avg_hr} bpm (最高 {max_hr} bpm)\n"
        f"  平均配速: {avg_pace_str} /km (最快 {max_pace_str} /km)\n"
        f"  平均步頻: {cadence} spm | 步幅: {stride} cm\n"
        f"  訓練成效(Garmin判定): {te_label} (有氧 TE: {ae_te}, 無氧 TE: {an_te})\n"
        f"{laps_text}\n"
        "請以跑步教練的角度，根據以上進階數據給我專業分析與建議。\n"
        "注意：請檢查這份數據是否打破了我的 PB（個人最佳成績）或達成了重要里程碑。如果是的話，請務必先使用 `python scripts/update_profile.py` 將新紀錄寫入我的個人檔案，再給我回覆！"
    )
    return prompt
