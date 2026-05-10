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
        return 0.95
    elif days_missed <= 28:
        return 0.92
    else:
        # Long term break, significant drop
        return 0.85

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
