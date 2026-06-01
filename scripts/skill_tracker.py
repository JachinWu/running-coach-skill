"""skill_tracker.py — Aggregate historical Training Effect (TE) data to track runner skills."""

import logging
from typing import Dict, Any, List
from pathlib import Path
import json

# Try to import garmin from same directory
try:
    from . import garmin
except ImportError:
    import garmin

logger = logging.getLogger(__name__)

def calculate_level_info(te: float) -> Dict[str, Any]:
    """
    Calculates level and progress information based on a non-linear formula.
    Formula: Level = floor((TE / 100)^0.7) + 1
    Returns: Dict containing 'level', 'current_xp', 'next_level_xp', and 'progress_pct'.
    """
    # Inverse formula to find XP required for a specific level:
    # XP = 100 * (Level - 1)^(1/0.7)
    
    level = int((te / 100) ** 0.7) + 1
    
    xp_for_current_level = 100 * ((level - 1) ** (1 / 0.7)) if level > 1 else 0
    xp_for_next_level = 100 * (level ** (1 / 0.7))
    
    xp_in_level = te - xp_for_current_level
    xp_needed_for_level = xp_for_next_level - xp_for_current_level
    
    progress_pct = min(100.0, max(0.0, (xp_in_level / xp_needed_for_level) * 100))
    
    return {
        "level": level,
        "current_xp": round(te, 1),
        "xp_in_level": round(xp_in_level, 1),
        "xp_needed_for_level": round(xp_needed_for_level, 1),
        "progress_pct": round(progress_pct, 1)
    }

def get_skill_levels(api) -> Dict[str, Dict[str, Any]]:
    """
    Aggregates historical TE from activities to determine skill levels.
    Categories: 基礎有氧, 節奏, 馬拉松配速跑, 最大攝氧量, 無氧
    Returns: Dict mapping category name to a level info dict.
    """
    history = garmin.get_multi_year_activity_history(api, years=3)
    
    raw_scores = {
        "基礎有氧": 0.0,
        "節奏": 0.0,
        "馬拉松配速跑": 0.0,
        "最大攝氧量": 0.0,
        "無氧": 0.0
    }
    
    for year, quarters in history.items():
        for q, cats in quarters.items():
            raw_scores["基礎有氧"] += cats.get("基礎", 0.0) + cats.get("恢復", 0.0)
            raw_scores["節奏"] += cats.get("高強度", 0.0) * 0.4
            raw_scores["馬拉松配速跑"] += cats.get("高強度", 0.0) * 0.4
            raw_scores["最大攝氧量"] += cats.get("高強度", 0.0) * 0.2
            raw_scores["無氧"] += cats.get("無氧", 0.0)
            
    # Calculate level info for each skill
    skills = {}
    for key, te in raw_scores.items():
        skills[key] = calculate_level_info(te)
        
    return skills

def get_skill_icons() -> Dict[str, str]:
    """Returns icons for the skill categories."""
    return {
        "基礎有氧": "🌱",
        "節奏": "⏱️",
        "馬拉松配速跑": "🏃",
        "最大攝氧量": "🫁",
        "無氧": "⚡"
    }

if __name__ == "__main__":
    # This requires a live API to test properly, but we can mock or check logic.
    print("Skill Tracker Module Loaded.")
