import json
import datetime
import asyncio
import logging
from pathlib import Path
from typing import Optional, List, Dict, Any, Callable, Coroutine

try:
    from . import garmin
except ImportError:
    import garmin

logger = logging.getLogger(__name__)

# Paths
SKILL_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = SKILL_DIR / "data"
GUARDRAIL_STATE_FILE = DATA_DIR / "guardrail_state.json"

async def get_today_summary(api) -> str:
    """Import logic from bot_bridge to avoid circular import if possible, 
    but here we just need a simple check."""
    loop = asyncio.get_event_loop()
    workout = await loop.run_in_executor(None, garmin.get_today_scheduled_workout, api)
    if workout is None:
        return "今日為休息日"
    return "有課表"

def load_guardrail_state() -> dict:
    """Load the last reported guardrail state."""
    if GUARDRAIL_STATE_FILE.exists():
        try:
            with open(GUARDRAIL_STATE_FILE, "r") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load guardrail state: {e}")
    return {}

def save_guardrail_state(state: dict) -> None:
    """Save the current guardrail state."""
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        with open(GUARDRAIL_STATE_FILE, "w") as f:
            json.dump(state, f)
    except Exception as e:
        logger.error(f"Failed to save guardrail state: {e}")

async def run_hrv_guardrail_check(
    api, 
    send_message_func: Callable[[str], Coroutine[Any, Any, None]]
):
    """Check HRV status and proactively alert if recovery is poor.
    
    This is the 'HRV Dynamic Guardrail' feature.
    """
    try:
        loop = asyncio.get_event_loop()
        recovery = await loop.run_in_executor(None, garmin.get_hrv_and_recovery, api)
        
        if recovery.get("type") != "hrv":
            return # Skip if HRV data not available

        current_status = recovery.get("status", "unknown").lower()
        last_state = load_guardrail_state()
        
        today_str = datetime.date.today().isoformat()
        last_date = last_state.get("last_check_date")
        last_status = last_state.get("last_status")

        # Alert if status is poor/unbalanced AND (it changed OR we haven't checked today)
        is_risky = current_status in ("low", "unbalanced", "poor")
        status_changed = current_status != last_status
        new_day = today_str != last_date

        if is_risky and (status_changed or new_day):
            # Compose alert
            weekly_avg = recovery.get("weekly_avg", "N/A")
            last_night = recovery.get("last_night", "N/A")
            
            status_cn = {
                "low": "偏低",
                "unbalanced": "不平衡",
                "poor": "差"
            }.get(current_status, current_status.upper())

            # Fetch today's workout for context
            workout_info = await get_today_summary(api)
            has_workout = "今日為休息日" not in workout_info
            
            alert_text = (
                f"🛡️ *HRV 智能守護者預警*\n\n"
                f"偵測到您的恢復狀態不佳：\n"
                f"• 狀態：*{status_cn}*\n"
                f"• 昨夜 HRV：{last_night} ms\n"
                f"• 週平均：{weekly_avg} ms\n\n"
            )

            if has_workout:
                alert_text += (
                    "⚠️ *偵測到今日已有課表安排。*\n"
                    "由於 HRV 顯著下降，建議將今日訓練強度下修為 *Zone 2 恢復跑*，或是直接改為 *完全休息*，避免過度訓練導致傷病。\n\n"
                    "💡 您可以回覆「幫我調整今日課表」來獲得具體建議。"
                )
            else:
                alert_text += (
                    "✅ 今日剛好是休息日，請務必好好放鬆，確保睡眠品質，讓身體重新平衡。"
                )

            await send_message_func(alert_text)
            
            # Update state
            save_guardrail_state({
                "last_check_date": today_str,
                "last_status": current_status
            })
            logger.info(f"HRV Guardrail alert sent: {current_status}")
        else:
            # If not risky, just update the date so we don't spam or re-check unnecessarily
            if new_day or status_changed:
                save_guardrail_state({
                    "last_check_date": today_str,
                    "last_status": current_status
                })
                
    except Exception as e:
        logger.error(f"Error in HRV Guardrail check: {e}")
