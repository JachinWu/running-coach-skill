"""race_goal.py — Persistent race goal management for the running coach bot."""

import json
import datetime
from pathlib import Path
from typing import Optional

DATA_DIR: Path = Path(__file__).resolve().parent.parent / "data"
GOAL_FILE: Path = DATA_DIR / "race_goal.json"

# Standard race distances in km
STANDARD_DISTANCES: dict[str, float] = {
    "5k": 5.0,
    "5km": 5.0,
    "10k": 10.0,
    "10km": 10.0,
    "hm": 21.0975,
    "half": 21.0975,
    "21k": 21.0975,
    "21km": 21.0975,
    "fm": 42.195,
    "full": 42.195,
    "42k": 42.195,
    "42km": 42.195,
    "marathon": 42.195,
}


def parse_distance(raw: str) -> float:
    """Parse a distance string into km as a float.

    Accepts shorthand (e.g. '42k', 'hm', 'marathon') or a plain number.

    Args:
        raw: Distance string from user input.

    Returns:
        Distance in kilometres as float.

    Raises:
        ValueError: If the string cannot be parsed.
    """
    key = raw.lower().strip()
    if key in STANDARD_DISTANCES:
        return STANDARD_DISTANCES[key]
    # Strip trailing 'k' or 'km' and parse as float
    for suffix in ("km", "k"):
        if key.endswith(suffix):
            return float(key[: -len(suffix)])
    return float(key)


def load_goal() -> Optional[dict]:
    """Load the saved race goal from disk.

    Returns:
        Goal dict, or None if no goal has been set.
    """
    if not GOAL_FILE.exists():
        return None
    try:
        with open(GOAL_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return None


def save_goal(race_date: str, race_distance_km: float, race_name: str = "") -> dict:
    """Persist a race goal to disk.

    Args:
        race_date: ISO-format date string (YYYY-MM-DD).
        race_distance_km: Race distance in kilometres.
        race_name: Optional human-readable name for the race.

    Returns:
        The saved goal dict.
    """
    DATA_DIR.mkdir(exist_ok=True)
    goal: dict = {
        "race_date": race_date,
        "race_distance_km": race_distance_km,
        "race_name": race_name,
        "set_at": datetime.date.today().isoformat(),
    }
    with open(GOAL_FILE, "w", encoding="utf-8") as f:
        json.dump(goal, f, ensure_ascii=False, indent=2)
    return goal


def get_days_remaining(goal: dict) -> int:
    """Calculate days from today until the race date.

    Args:
        goal: Goal dict containing 'race_date' key.

    Returns:
        Number of days remaining (negative if race has passed).
    """
    race_date = datetime.date.fromisoformat(goal["race_date"])
    return (race_date - datetime.date.today()).days


def format_distance(km: float) -> str:
    """Return a human-readable distance label.

    Args:
        km: Distance in kilometres.

    Returns:
        Formatted label string (e.g. '全程馬拉松 (42.195 km)').
    """
    labels: dict[float, str] = {
        42.195: "全程馬拉松 (42.195 km)",
        21.0975: "半程馬拉松 (21.0975 km)",
        10.0: "10 km",
        5.0: "5 km",
    }
    return labels.get(km, f"{km} km")


def get_training_phase(days_remaining: int) -> str:
    """Determine the current training phase based on days until race.

    Args:
        days_remaining: Days from today to race day.

    Returns:
        Emoji + phase name string.
    """
    if days_remaining > 90:
        return "🌱 基礎期"
    if days_remaining > 56:
        return "📈 建量期"
    if days_remaining > 28:
        return "⚡ 強化期"
    if days_remaining > 14:
        return "📉 減量期"
    return "🏁 賽前調整期"
