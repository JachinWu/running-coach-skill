"""
daniels_periodization.py — Constants and logic for Daniels' Training Phases and Levels.
Includes VDOT adjustment for breaks in training (detraining).
"""

import datetime
from typing import Dict, Any, Optional

# 1. Training Levels (跑量級別)
# Based on Daniels' Running Formula Color-coded programs
LEVELS = {
    "WHITE": {
        "description": "入門級別，建立習慣",
        "days_per_week": (3, 4),
        "max_weekly_km": 30,
        "intensity_focus": ["E"],
    },
    "RED": {
        "description": "中階級別，規律訓練",
        "days_per_week": (4, 5),
        "max_weekly_km": 50,
        "intensity_focus": ["E", "T", "R"],
    },
    "BLUE": {
        "description": "進階級別，目標賽事",
        "days_per_week": (5, 6),
        "max_weekly_km": 80,
        "intensity_focus": ["E", "M", "T", "I", "R"],
    },
    "GOLD": {
        "description": "菁英級別，追求極限",
        "days_per_week": (6, 7),
        "max_weekly_km": 120,
        "intensity_focus": ["E", "M", "T", "I", "R"],
    }
}

# 2. Training Phases (週期定義)
# Typical breakdown for a 24-week plan (shortened if necessary)
PHASES = {
    "I": {
        "name": "🌱 基礎期 (> 18 週)",
        "description": "建立有氧基礎，以 E 跑為主。",
        "focus_paces": ["E"],
        "max_t_percent": 0.0,
        "max_i_percent": 0.0,
    },
    "II": {
        "name": "📈 進展期 (12~18 週)",
        "description": "加入 R 跑提升經濟性。",
        "focus_paces": ["E", "R"],
        "max_t_percent": 0.0,
        "max_i_percent": 0.0,
    },
    "III": {
        "name": "⚡ 巔峰期 (4~12 週)",
        "description": "巔峰期，加入 I 跑與 T 跑。",
        "focus_paces": ["E", "I", "T", "R"],
        "max_t_percent": 0.10,
        "max_i_percent": 0.08,
    },
    "IV": {
        "name": "📉 減量調整期 (≤ 4 週)",
        "description": "減量與專項速度，迎接比賽。",
        "focus_paces": ["E", "T", "M"],
        "max_t_percent": 0.10,
        "max_i_percent": 0.05,
    }
}

# 3. Detraining Multipliers (停練衰減係數)
# Based on Daniels' suggestions for VDOT adjustment after breaks.
# Key is the number of days missed.
def get_detraining_vdot_multiplier(days_missed: int) -> float:
    """
    Returns the multiplier for VDOT based on days of missed training.
    Values are approximate based on Daniels' Running Formula guidelines.
    """
    if days_missed <= 5:
        return 1.0
    elif days_missed <= 7:
        return 0.99
    elif days_missed <= 14:
        return 0.97
    elif days_missed <= 21:
        # Interpolated from Daniels' tables (approx 3-5% drop)
        return 0.95
    elif days_missed <= 28:
        return 0.92
    elif days_missed <= 56:
        # Significant drop after 1-2 months
        return 0.88
    else:
        # Long term break, significant drop (base building required)
        return 0.85

class DetrainingProtocol:
    """
    Daniels' Return to Training Protocols after an interruption.
    Calculates required days and intensity for each recovery stage.
    """
    def __init__(self, days_missed: int):
        self.days_missed = days_missed
        self.vdot_multiplier = get_detraining_vdot_multiplier(days_missed)
        
    def get_recovery_plan(self) -> Dict[str, Any]:
        """
        Returns a structured plan for returning to training.
        """
        if self.days_missed <= 5:
            return {"status": "normal", "advice": "無須特殊調整，按計畫繼續。"}
            
        elif self.days_missed <= 28:
            # Protocol for 6-28 days missed:
            # Stage 1: Length = missed days. All E runs, 50-75% volume.
            # Stage 2: Length = missed days. Add some T runs, 75-100% volume.
            stage1_days = self.days_missed
            return {
                "status": "realign",
                "vdot_adj": self.vdot_multiplier,
                "stages": [
                    {
                        "name": "第一階段：重新適應",
                        "duration_days": stage1_days,
                        "volume_percent": 60,
                        "intensity": "全 E 跑 (Easy)",
                        "vdot": "調整後 VDOT"
                    },
                    {
                        "name": "第二階段：恢復強度",
                        "duration_days": stage1_days,
                        "volume_percent": 80,
                        "intensity": "增加少量 T 跑 (Tempo)",
                        "vdot": "調整後 VDOT"
                    }
                ],
                "total_recovery_days": stage1_days * 2,
                "advice": f"偵測到中斷 {self.days_missed} 天。建議執行為期 {stage1_days * 2} 天的恢復程序，優先重建基礎有氧能力與韌帶強度。"
            }
            
        else:
            # Over 28 days missed: Significant detraining
            # Usually requires 4+ weeks of Base Building (Phase I)
            return {
                "status": "reset",
                "vdot_adj": self.vdot_multiplier,
                "advice": f"中斷訓練已達 {self.days_missed} 天。有氧能力已顯著衰減，建議放棄當前週期，重新進行 4 週的 Phase I 基礎期訓練，以確保安全回歸。",
                "recommended_phase": "I"
            }

def calculate_current_phase(target_date: datetime.date) -> str:
    """
    Calculates the current phase (I, II, III, IV) based on distance to race.
    Based on standard Daniels' 24-week countdown logic.
    """
    today = datetime.date.today()
    days_left = (target_date - today).days
    
    if days_left <= 0:
        return "IV" # Race day or after
    
    if days_left > 126: # > 18 weeks
        return "I"
    elif days_left > 84: # 12~18 weeks
        return "II"
    elif days_left > 28: # 4~12 weeks
        return "III"
    else: # <= 4 weeks
        return "IV"

def get_phase_advice(phase_key: str) -> Dict[str, Any]:
    return PHASES.get(phase_key, PHASES["I"])

def get_level_info(level_key: str) -> Dict[str, Any]:
    return LEVELS.get(level_key.upper(), LEVELS["WHITE"])

# 4. Recovery Navigator Logic (智慧補課/跳過決策)
class RecoveryDecision:
    """決策結果容器"""
    def __init__(self, action: str, reason: str, adjustment: str):
        self.action = action      # "SKIP", "CATCH_UP", "ADJUST", "REST"
        self.action_cn = {
            "SKIP": "直接跳過",
            "CATCH_UP": "適度補課",
            "ADJUST": "降強度執行",
            "REST": "完全休息"
        }.get(action, action)
        self.reason = reason      # 決策原因
        self.adjustment = adjustment # 具體調整內容 (例如：Zone 2 30min)

def resolve_missed_workout(
    missed_workout: Dict[str, Any],
    recovery_status: Dict[str, Any],
    today_scheduled: Optional[Dict[str, Any]] = None
) -> RecoveryDecision:
    """
    根據 Daniels 原則與恢復數據，決定如何處理「昨日漏掉的課表」。
    
    邏輯優先級：
    1. 若恢復差 (HRV Low/Poor or BB < 40) -> 不補課，今日亦建議降強度或休息。
    2. 若昨日是 E 跑 (Easy) -> 直接跳過，不影響週期。
    3. 若昨日是 Q 跑 (Quality: T/I/R/M) 且恢復好 -> 考慮今日補課 (若今日原定休息或也是 E)。
    4. 若今日已有重要 Q 跑 -> 絕對不補課，以今日為主。
    """
    
    # 恢復狀態評估
    hrv_status = recovery_status.get("status", "balanced").lower()
    bb_level = recovery_status.get("bb_level", 100)
    
    is_recovery_poor = hrv_status in ("low", "unbalanced", "poor") or bb_level < 40
    is_recovery_excellent = hrv_status == "balanced" and bb_level > 80

    # 課表屬性
    missed_name = (missed_workout.get("title") or missed_workout.get("workoutName") or "").upper()
    is_q_run = any(q in missed_name for q in ["TEMPO", "THRESHOLD", "INTERVAL", "REPETITION", "MARATHON", "T 跑", "I 跑", "R 跑", "M 跑"])

    # 今日課表屬性
    today_name = (today_scheduled.get("title") or today_scheduled.get("workoutName") or "") if today_scheduled else "休息"
    today_is_q = any(q in today_name.upper() for q in ["TEMPO", "THRESHOLD", "INTERVAL", "REPETITION", "MARATHON", "T 跑", "I 跑", "R 跑", "M 跑"])

    # --- 決策分支 ---
    
    if is_recovery_poor:
        return RecoveryDecision(
            "REST",
            "偵測到恢復數據顯著下滑（HRV 異常或能量儲備低）。",
            "不要補課。建議今日也改為完全休息或極輕鬆的 Zone 1 散步，優先讓身體恢復。"
        )

    if not is_q_run:
        return RecoveryDecision(
            "SKIP",
            "昨日漏掉的是基礎 E 跑，這類訓練旨在累積里程，漏掉一次對週期影響較小。",
            "直接跳過。按原計畫執行今日課表即可，切勿為了補里程而疲勞累積。"
        )

    # 針對漏掉 Q 跑的處理
    if today_is_q:
        return RecoveryDecision(
            "SKIP",
            f"昨日漏掉了重要訓練 ({missed_name})，但今日已有另一項重要訓練 ({today_name})。",
            "直接跳過昨日。兩項高品質訓練連續執行風險過高，請以今日計畫為主。"
        )
    
    if is_recovery_excellent:
        return RecoveryDecision(
            "CATCH_UP",
            "昨日漏掉了高品質訓練，且今晨恢復狀態極佳。",
            f"今日可嘗試補回昨日的 {missed_name}。若原定今日有 E 跑，請將其取消，兩者不併行。"
        )
    
    # 預設：恢復一般，且是 Q 跑
    return RecoveryDecision(
        "ADJUST",
        "昨日漏掉高品質訓練，目前恢復狀態中等。",
        "不補原課表。今日可進行比原定稍微長一點點的 E 跑（增加 15-20 分鐘），或將昨日 Q 跑的總量減半執行。"
    )
