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
except ImportError:
    import garmin
    import athlete_profile
    import visualizer
    import hrv_guardrail

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


# ---------------------------------------------------------------------------
# Command Logic Handlers
# ---------------------------------------------------------------------------

async def get_today_summary(api) -> str:
    """Logic for /today command, providing context for the Dynamic Guardrail."""
    loop = asyncio.get_event_loop()
    workout = await loop.run_in_executor(None, garmin.get_today_scheduled_workout, api)
    recovery = await loop.run_in_executor(None, garmin.get_hrv_and_recovery, api)
    
    today_label = datetime.date.today().strftime("%Y/%m/%d")
    
    # Format recovery info
    recovery_info = ""
    rtype = recovery.get("type", "unavailable")
    if rtype == "hrv":
        status_cn = {"balanced": "平衡", "low": "低", "unbalanced": "不平衡", "poor": "差"}.get(recovery.get("status", "").lower(), recovery.get("status"))
        recovery_info = f"昨夜 HRV: {recovery.get('last_night', 'N/A')} ms (週平均: {recovery.get('weekly_avg', 'N/A')} ms, 狀態: {status_cn})"
    elif rtype == "body_battery":
        recovery_info = f"Body Battery: {recovery.get('level', 'N/A')}%"
    else:
        recovery_info = "恢復數據暫不可用"

    if workout is None:
        return f"📅 {today_label}\n今日為休息日。☕\n[恢復狀態]: {recovery_info}"
    elif isinstance(workout, dict) and "error" in workout:
        return f"❌ 查詢失敗：{workout['error']}"
    else:
        name = workout.get("title") or workout.get("workoutName") or "未命名課表"
        description = workout.get("description", "")
        return (
            f"📅 今日課表 ({today_label})\n"
            f"🏃 課表內容: {name}\n"
            f"📝 詳情: {description}\n"
            f"❤️ [恢復狀態]: {recovery_info}"
        )

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
                f"🏃 <b>{sport}</b>: {data['runs_count']}次 | {data['total_distance_km']}km | {data['total_duration_min']}分 | {hr_line}"
            )
    sport_summary_text = "\n".join(sport_texts) if sport_texts else "• 過去 7 天無運動紀錄"

    # 2. Format recovery and load metrics
    latest_load = latest_metrics.get('training_load', 0)
    latest_ratio = round(latest_metrics.get('load_ratio', 0) * 100)
    latest_hrv = latest_metrics.get('hrv', 0)
    latest_bb = latest_metrics.get('body_battery', 0)
    
    # 3. Format upcoming schedule
    schedule_texts = []
    for item in upcoming:
        d_obj = datetime.date.fromisoformat(item["date"])
        d_str = d_obj.strftime("%m/%d")
        weekday_cn = ["一", "二", "三", "四", "五", "六", "日"][d_obj.weekday()]

        w = item["workout"]
        if w:
            name = escape_html(
                w.get("title") or w.get("workoutName") or "未命名課表"
            )
            schedule_texts.append(f"• {d_str} ({weekday_cn}): {name}")
        else:
            schedule_texts.append(f"• {d_str} ({weekday_cn}): 休息 ☕")
    schedule_text = "\n".join(schedule_texts)

    caption = (
        f"📊 <b>綜合訓練週報</b>\n\n"
        f"{sport_summary_text}\n\n"
        f"❤️ 昨夜 HRV：{latest_hrv} ms\n"
        f"🔋 Body Battery：{latest_bb}%\n"
        f"📈 最新負荷：{latest_load} (負荷比: {latest_ratio}%)\n\n"
        f"📅 <b>接下來課表</b>\n"
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
                "使用方式：<code>/goal set YYYY-MM-DD 距離 [賽事名稱]</code>\n"
                "範例：<code>/goal set 2026-11-01 42 台北馬拉松</code>"
            )
        try:
            race_date_str = args[0]
            datetime.date.fromisoformat(race_date_str)  # validate format
            dist_km = athlete_profile.parse_distance(args[1])
            race_name = " ".join(args[2:]) if len(args) > 2 else ""
        except (ValueError, IndexError) as e:
            return f"❌ 輸入格式有誤：{escape_html(str(e))}"

        goal = athlete_profile.save_goal(race_date_str, dist_km, race_name)
        days = athlete_profile.get_days_remaining(race_date_str)
        dist_str = athlete_profile.format_distance(dist_km)
        display_name = race_name or dist_str
        return (
            f"🎯 <b>賽事目標已儲存！</b>\n\n"
            f"• 賽事：{escape_html(display_name)}\n"
            f"• 距離：{escape_html(dist_str)}\n"
            f"• 日期：{escape_html(race_date_str)}\n"
            f"• 距今：<b>{days} 天</b>\n"
            f"• 訓練階段：{escape_html(athlete_profile.get_training_phase_name(days))}"
        )
    else:
        # show
        goal = athlete_profile.load_goal()
        if not goal or not goal.get("race_date"):
            return (
                "📭 尚未設定賽事目標。\n\n"
                "使用 <code>/goal set YYYY-MM-DD 距離</code> 設定\n"
                "例：<code>/goal set 2026-11-01 42</code>"
            )

        days = athlete_profile.get_days_remaining(goal["race_date"])
        dist_str = athlete_profile.format_distance(goal["race_distance_km"])
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
            f"• 訓練階段：{escape_html(athlete_profile.get_training_phase_name(days))}"
        )

# ---------------------------------------------------------------------------
# Background Polling Logic
# ---------------------------------------------------------------------------

async def run_post_run_polling(
    get_api_func: Callable[[], Any],
    send_message_func: Callable[[str, Optional[Any], Optional[str]], Coroutine[Any, Any, Optional[int]]],
    poll_interval: int = 900
):
    """Periodically check for new Garmin activities and trigger analysis.
    
    Args:
        get_api_func: Function that returns an authenticated Garmin API object.
        send_message_func: Async function to send a message (text, keyboard, session_id). 
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
                    await send_message_func(text, None, None)
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

                            session_id = uuid.uuid4().hex
                            prompt = await compose_analysis_prompt(api, activity)
                            
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
                                # Send analysis and associate session
                                await send_message_func(header + output, None, session_id)
                                
                                # Send RPE follow-up and associate with the SAME session
                                rpe_text = "*教練詢問*：這趟跑起來體感如何？請點選 RPE 強度（1 最輕鬆，10 全力）："
                                rpe_keyboard = get_rpe_keyboard_data(activity_id)
                                await send_message_func(rpe_text, rpe_keyboard, session_id)
                                
                                last_known_id = activity_id
                                save_last_activity_id(activity_id)
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

async def compose_analysis_prompt(api, activity: Dict[str, Any]) -> str:
    """Compose a detailed prompt for Gemini analysis based on activity data."""
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

    # Fetch Recovery Data for Dynamic Guardrail
    loop = asyncio.get_event_loop()
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
        f"{recovery_text}\n"
        f"{goal_text}\n"
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
