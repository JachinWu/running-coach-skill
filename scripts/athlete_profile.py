"""athlete_profile.py — Persistent athlete memory for the running coach.

Stores personal bests, injuries, progress milestones, and coaching notes.
Used by both the Telegram bot and the Gemini CLI running-coach skill.
"""

import json
import datetime
import copy
from pathlib import Path
from typing import Optional, Dict

# Import daniels_formula for VDOT calculations
try:
    import daniels_formula
    import daniels_periodization
except ImportError:
    # Handle cases where path might need adjustment
    import sys
    sys.path.append(str(Path(__file__).resolve().parent))
    import daniels_formula
    import daniels_periodization

DATA_DIR: Path = Path(__file__).resolve().parent.parent / "data"
PROFILE_FILE: Path = DATA_DIR / "athlete_profile.json"

# ---------------------------------------------------------------------------
# Default profile schema
# ---------------------------------------------------------------------------
DEFAULT_PROFILE: dict = {
    "personal_bests": {
        "5k":             [],  # List of {"time": str, "date": str, "race": str}
        "10k":            [],
        "half_marathon":  [],
        "marathon":       [],
    },
    "vdot": None,
    "training_paces": {},  # {"E": "5:30", "M": "4:45", ...}
    "training_level": "WHITE", # WHITE, RED, BLUE, GOLD
    "target_race_date": None,  # ISO date string
    "current_phase": "I",      # I, II, III, IV
    "last_activity_date": None, # ISO date string of last Garmin activity
    "target_race_distance_km": 42.195,
    "target_race_name": "",
    "physiology_history": [],  # List of {"date": str, "vo2max": float/None, "lthr": int/None, "lt_pace": str/None}
    "injuries": [],
    "health_notes": [],
    "progress_milestones": [],
    "coaching_notes": [],
    "long_term_insights": [],  # List of {"date": str, "category": str, "content": str}
    "activity_feedback": [],   # List of {"activity_id": str, "date": str, "rpe": int, "pain_level": int, "pain_area": str, "notes": str}
    "last_updated": None,
}


# ---------------------------------------------------------------------------
# Core read / write
# ---------------------------------------------------------------------------

def load_profile() -> dict:
    """Load the athlete profile from disk, returning defaults if missing.

    Returns:
        Full athlete profile dict.
    """
    if not PROFILE_FILE.exists():
        return copy.deepcopy(DEFAULT_PROFILE)
    try:
        with open(PROFILE_FILE, "r", encoding="utf-8") as f:
            stored = json.load(f)
        
        # Start with a fresh deep copy of defaults
        merged = copy.deepcopy(DEFAULT_PROFILE)
        
        # Deep merge for dictionary keys like personal_bests
        if "personal_bests" in stored:
            merged["personal_bests"].update(stored["personal_bests"])
        
        # Simple update for other top-level keys
        for key, value in stored.items():
            if key != "personal_bests":
                merged[key] = value
        
        # Migration: If VDOT is missing but PBs exist, trigger a refresh
        if merged.get("vdot") is None:
            if _refresh_vdot_logic(merged):
                # Save the updated profile with VDOT
                save_profile(merged)

        return merged
    except (json.JSONDecodeError, IOError):
        return copy.deepcopy(DEFAULT_PROFILE)


def save_profile(profile: dict) -> None:
    """Persist the athlete profile to disk.

    Args:
        profile: Full athlete profile dict to save.
    """
    DATA_DIR.mkdir(exist_ok=True)
    profile["last_updated"] = datetime.date.today().isoformat()
    with open(PROFILE_FILE, "w", encoding="utf-8") as f:
        json.dump(profile, f, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# VDOT & Pace Management
# ---------------------------------------------------------------------------

def _parse_time_to_seconds(time_str: str) -> int:
    """Convert time string (HH:MM:SS or MM:SS) to total seconds."""
    parts = time_str.split(":")
    if len(parts) == 3:
        return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
    elif len(parts) == 2:
        return int(parts[0]) * 60 + int(parts[1])
    return 0


def _refresh_vdot_logic(profile: dict) -> bool:
    """Internal logic to recalculate VDOT and paces for a profile dict.
    Returns True if changes were made.
    """
    pbs = profile.get("personal_bests", {})
    max_vdot = 0.0
    
    distance_map = {
        "5k": 5000,
        "10k": 10000,
        "half_marathon": 21097.5,
        "marathon": 42195
    }
    
    for dist, entries in pbs.items():
        if not entries:
            continue
        
        # Use the latest PB entry for that distance
        latest_pb = entries[-1]
        try:
            seconds = _parse_time_to_seconds(latest_pb["time"])
            if seconds > 0:
                dist_m = distance_map.get(dist, 0)
                vdot = daniels_formula.calculate_vdot(dist_m, seconds)
                if vdot > max_vdot:
                    max_vdot = vdot
        except Exception:
            continue
            
    if max_vdot > 0:
        profile["vdot"] = max_vdot
        profile["training_paces"] = daniels_formula.calculate_paces(max_vdot)
        return True
    return False


def refresh_vdot_and_paces() -> dict:
    """Recalculate VDOT and paces based on the best current PB.

    Returns:
        Updated profile dictionary.
    """
    profile = load_profile()
    if _refresh_vdot_logic(profile):
        save_profile(profile)
    return profile


# ---------------------------------------------------------------------------
# Activity Feedback (RPE / Pain) helpers
# ---------------------------------------------------------------------------

def add_activity_feedback(
    activity_id: str, 
    rpe: int, 
    pain_level: int = 0, 
    pain_area: str = "", 
    notes: str = "",
    date: Optional[str] = None
) -> dict:
    """Record subjective feedback for a specific activity.

    Args:
        activity_id: Garmin activity ID.
        rpe:         Rate of Perceived Exertion (1-10).
        pain_level:  Self-reported pain level (0-10).
        pain_area:   Description of pain area (e.g. 'Right Achilles').
        notes:       Optional qualitative notes.
        date:        ISO date of the feedback (defaults to today).

    Returns:
        The newly added feedback entry.
    """
    profile = load_profile()
    
    if "activity_feedback" not in profile:
        profile["activity_feedback"] = []
        
    entry = {
        "activity_id": str(activity_id),
        "date": date or datetime.date.today().isoformat(),
        "rpe": rpe,
        "pain_level": pain_level,
        "pain_area": pain_area,
        "notes": notes,
    }
    
    # Update existing if same activity_id, otherwise append
    existing_index = -1
    for i, f in enumerate(profile["activity_feedback"]):
        if f.get("activity_id") == str(activity_id):
            existing_index = i
            break
            
    if existing_index >= 0:
        profile["activity_feedback"][existing_index] = entry
    else:
        profile["activity_feedback"].append(entry)
        
    # Sort and keep latest 50 activities
    profile["activity_feedback"].sort(key=lambda x: x.get("date", ""), reverse=True)
    profile["activity_feedback"] = profile["activity_feedback"][:50]
    
    save_profile(profile)
    return entry


def get_recent_feedback(limit: int = 5) -> list:
    """Return the most recent activity feedback entries."""
    profile = load_profile()
    return profile.get("activity_feedback", [])[:limit]


# ---------------------------------------------------------------------------
# PB helpers
# ---------------------------------------------------------------------------

_DISTANCE_ALIASES: dict[str, str] = {
    "5k": "5k", "5km": "5k",
    "10k": "10k", "10km": "10k",
    "half": "half_marathon", "hm": "half_marathon",
    "21k": "half_marathon", "21km": "half_marathon",
    "half_marathon": "half_marathon",
    "marathon": "marathon", "fm": "marathon",
    "42k": "marathon", "42km": "marathon", "full": "marathon",
}


def normalize_distance(raw: str) -> Optional[str]:
    """Normalize a distance string to a profile key.

    Args:
        raw: Distance string (e.g. '10k', 'half', 'marathon').

    Returns:
        Canonical key ('5k', '10k', 'half_marathon', 'marathon'), or None if unrecognized.
    """
    return _DISTANCE_ALIASES.get(raw.lower().strip())


def update_pb(distance: str, time: str, date: Optional[str] = None, race: Optional[str] = None) -> dict:
    """Record a new personal best for a given distance (appends to history).

    Args:
        distance: Distance key or alias (e.g. '10k', 'half').
        time:     Finish time string (e.g. '47:32', '1:52:10').
        date:     ISO date of the achievement (defaults to today).
        race:     Optional race name.

    Returns:
        Updated PB entry dict.

    Raises:
        ValueError: If the distance is not recognized.
    """
    key = normalize_distance(distance)
    if not key:
        raise ValueError(f"未知距離：{distance}。支援：5k / 10k / half_marathon / marathon")

    profile = load_profile()
    entry = {
        "time": time,
        "date": date or datetime.date.today().isoformat(),
        "race": race,
    }
    
    if key not in profile["personal_bests"]:
        profile["personal_bests"][key] = []
        
    profile["personal_bests"][key].append(entry)
    
    # Sort by date so history is chronological
    profile["personal_bests"][key].sort(key=lambda x: x.get("date", ""))
    
    save_profile(profile)
    
    # Auto-refresh VDOT and paces after updating PB
    refresh_vdot_and_paces()
    
    return entry


# ---------------------------------------------------------------------------
# Physiology helpers
# ---------------------------------------------------------------------------

def add_physiology_record(vo2max: Optional[float] = None, lthr: Optional[int] = None, lt_pace: Optional[str] = None, date: Optional[str] = None) -> dict:
    """Record a new physiological metric (VO2Max or Lactate Threshold).

    Args:
        vo2max:  VO2 Max value (e.g. 54.0).
        lthr:    Lactate Threshold Heart Rate (e.g. 170).
        lt_pace: Lactate Threshold Pace (e.g. '4:30').
        date:    ISO date of the record (defaults to today).

    Returns:
        Newly added physiology entry dict.
    """
    profile = load_profile()
    
    if "physiology_history" not in profile:
        profile["physiology_history"] = []
        
    entry = {
        "date": date or datetime.date.today().isoformat(),
        "vo2max": vo2max,
        "lthr": lthr,
        "lt_pace": lt_pace
    }
    profile["physiology_history"].append(entry)
    
    # Sort chronologically and keep the last 30 records
    profile["physiology_history"].sort(key=lambda x: x.get("date", ""))
    profile["physiology_history"] = profile["physiology_history"][-30:]
    
    save_profile(profile)
    return entry


# ---------------------------------------------------------------------------
# Injury helpers
# ---------------------------------------------------------------------------

def add_injury(description: str, notes: str = "", start_date: Optional[str] = None) -> dict:
    """Record a new injury or physical complaint.

    Args:
        description: Short description (e.g. '左膝髂脛束症候群').
        notes:       Optional additional context.
        start_date:  ISO date the injury started (defaults to today).

    Returns:
        Newly added injury entry dict.
    """
    profile = load_profile()
    entry = {
        "id": len(profile["injuries"]) + 1,
        "description": description,
        "start_date": start_date or datetime.date.today().isoformat(),
        "status": "active",   # 'active' | 'recovering' | 'resolved'
        "notes": notes,
        "resolved_date": None,
    }
    profile["injuries"].append(entry)
    save_profile(profile)
    return entry


def resolve_injury(injury_id: int, notes: str = "") -> Optional[dict]:
    """Mark an injury as resolved.

    Args:
        injury_id: The 'id' field of the injury to resolve.
        notes:     Optional resolution notes.

    Returns:
        Updated injury entry, or None if not found.
    """
    profile = load_profile()
    for injury in profile["injuries"]:
        if injury.get("id") == injury_id:
            injury["status"] = "resolved"
            injury["resolved_date"] = datetime.date.today().isoformat()
            if notes:
                injury["notes"] += f" | 恢復：{notes}"
            save_profile(profile)
            return injury
    return None


def get_active_injuries(profile: Optional[dict] = None) -> list:
    """Return all injuries with status 'active' or 'recovering'.

    Args:
        profile: Optional pre-loaded profile dict (to avoid double file read).

    Returns:
        List of active/recovering injury dicts.
    """
    p = profile or load_profile()
    return [i for i in p["injuries"] if i.get("status") in ("active", "recovering")]


# ---------------------------------------------------------------------------
# General note helpers
# ---------------------------------------------------------------------------

def add_coaching_note(note: str) -> None:
    """Append a free-form coaching note (for agent observations).

    Args:
        note: Note text to record.
    """
    profile = load_profile()
    profile["coaching_notes"].append({
        "date": datetime.date.today().isoformat(),
        "note": note,
    })
    # Keep only the latest 30 notes to avoid unbounded growth
    profile["coaching_notes"] = profile["coaching_notes"][-30:]
    save_profile(profile)


def add_milestone(description: str) -> None:
    """Record a training milestone or achievement.

    Args:
        description: Milestone description (e.g. '首次完成 30km long run').
    """
    profile = load_profile()
    profile["progress_milestones"].append({
        "date": datetime.date.today().isoformat(),
        "description": description,
    })
    save_profile(profile)


def add_long_term_insight(content: str, category: str = "general") -> None:
    """Record a long-term insight about the athlete (e.g. preferences, habits).

    Args:
        content:  The insight content.
        category: Insight category (e.g. 'preference', 'habit', 'weather').
    """
    profile = load_profile()
    if "long_term_insights" not in profile:
        profile["long_term_insights"] = []
        
    profile["long_term_insights"].append({
        "date": datetime.date.today().isoformat(),
        "category": category,
        "content": content,
    })
    # Limit to latest 20 insights if not using vector DB
    profile["long_term_insights"] = profile["long_term_insights"][-20:]
    save_profile(profile)


def get_long_term_insights(profile: Optional[dict] = None) -> list:
    """Return all stored long-term insights.

    Args:
        profile: Optional pre-loaded profile dict.

    Returns:
        List of insight dicts.
    """
    p = profile or load_profile()
    return p.get("long_term_insights", [])


# ---------------------------------------------------------------------------
# Training Management (Levels, Phases, Goals)
# ---------------------------------------------------------------------------

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
            try:
                return float(key[: -len(suffix)])
            except ValueError:
                continue
    try:
        return float(key)
    except ValueError:
        raise ValueError(f"無法解析距離：{raw}")


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


def get_training_phase_name(days_remaining: int) -> str:
    """Determine the current training phase name based on days until race.

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


def load_goal() -> Optional[dict]:
    """Load the saved race goal from the athlete profile.

    Returns:
        Goal dict, or None if no goal has been set.
    """
    profile = load_profile()
    if not profile.get("target_race_date"):
        return None

    return {
        "race_date": profile.get("target_race_date"),
        "race_distance_km": profile.get("target_race_distance_km", 42.195),
        "race_name": profile.get("target_race_name", ""),
    }


def save_goal(race_date: str, race_distance_km: float, race_name: str = "") -> dict:
    """Persist a race goal to the athlete profile.

    Args:
        race_date: ISO-format date string (YYYY-MM-DD).
        race_distance_km: Race distance in kilometres.
        race_name: Optional human-readable name for the race.

    Returns:
        The saved goal dict.
    """
    profile = load_profile()

    profile["target_race_date"] = race_date
    profile["target_race_distance_km"] = race_distance_km
    profile["target_race_name"] = race_name

    # Save directly first to ensure custom fields are there
    save_profile(profile)

    # Let athlete_profile handle the phase recalculation logic
    update_training_settings(target_race_date=race_date)

    return {
        "race_date": race_date,
        "race_distance_km": race_distance_km,
        "race_name": race_name,
    }


def get_days_remaining(race_date_str: str) -> int:
    """Calculate days from today until the race date.

    Args:
        race_date_str: ISO date string (YYYY-MM-DD).

    Returns:
        Number of days remaining (negative if race has passed).
    """
    race_date = datetime.date.fromisoformat(race_date_str)
    return (race_date - datetime.date.today()).days


def get_effective_vdot(profile: Optional[dict] = None) -> tuple[float, float]:
    """Calculate effective VDOT adjusted for detraining.
    
    Returns:
        tuple: (base_vdot, effective_vdot)
    """
    p = profile or load_profile()
    base_vdot = p.get("vdot") or 0.0
    if base_vdot <= 0:
        return 0.0, 0.0
        
    last_date_str = p.get("last_activity_date")
    if not last_date_str:
        return base_vdot, base_vdot
        
    try:
        last_date = datetime.date.fromisoformat(last_date_str)
        days_missed = (datetime.date.today() - last_date).days
        multiplier = daniels_periodization.get_detraining_vdot_multiplier(days_missed)
        return base_vdot, round(base_vdot * multiplier, 2)
    except Exception:
        return base_vdot, base_vdot


def update_training_settings(
    level: Optional[str] = None,
    target_race_date: Optional[str] = None
) -> dict:
    """Update training level, target race date, and recalculate current phase.

    Args:
        level: 'WHITE', 'RED', 'BLUE', or 'GOLD'.
        target_race_date: ISO date string of the goal race.

    Returns:
        Updated profile dict.
    """
    profile = load_profile()
    if level:
        profile["training_level"] = level.upper()
    
    if target_race_date:
        profile["target_race_date"] = target_race_date

    # Recalculate Phase based on target race date
    if profile.get("target_race_date"):
        try:
            trd = datetime.date.fromisoformat(profile["target_race_date"])
            profile["current_phase"] = daniels_periodization.calculate_current_phase(trd)
        except Exception:
            pass

    save_profile(profile)
    return profile


# ---------------------------------------------------------------------------
# Summary formatter (for display in Telegram / Gemini context)
# ---------------------------------------------------------------------------

def format_profile_summary(profile: Optional[dict] = None, include_insights: bool = True) -> str:
    """Return a human-readable Markdown summary of the athlete profile.

    Args:
        profile: Optional pre-loaded profile dict.
        include_insights: Whether to include the long-term insights section.

    Returns:
        Formatted Markdown string.
    """
    p = profile or load_profile()
    lines = ["## 🏅 運動員個人檔案\n"]

    # Training Context (Level & Phase)
    level_code = p.get("training_level", "WHITE")
    phase = p.get("current_phase", "I")
    target = p.get("target_race_date")
    
    level_map = {"WHITE": "入門", "RED": "中階", "BLUE": "進階", "GOLD": "菁英"}
    level_display = level_map.get(level_code, level_code)
    
    level_info = daniels_periodization.get_level_info(level_code)
    phase_info = daniels_periodization.get_phase_advice(phase)
    
    lines.append(f"### 🏃‍♂️ 訓練狀態：**{level_display} 級別**")
    lines.append(f"• **當前週期**：Phase {phase} ({phase_info['name']})")
    if target:
        try:
            trd = datetime.date.fromisoformat(target)
            days_left = (trd - datetime.date.today()).days
            lines.append(f"• **目標賽事**：{target} (剩餘 {days_left} 天)")
        except Exception:
            pass
    lines.append(f"• **級別特性**：{level_info['description']} (週跑量上限 {level_info['max_weekly_km']}km)")
    lines.append("")

    # Daniels VDOT & Paces
    base_vdot, effective_vdot = get_effective_vdot(p)
    paces = p.get("training_paces", {})
    
    if effective_vdot > 0:
        vdot_display = f"**{effective_vdot}**"
        if effective_vdot < base_vdot:
            vdot_display += f" (⚠️ 體能衰減中，原始: {base_vdot})"
            # Recalculate paces based on effective VDOT for display
            paces = daniels_formula.calculate_paces(effective_vdot)
            
        lines.append(f"### 📈 丹尼爾斯跑力 (VDOT: {vdot_display})")
        if paces:
            lines.append("```")
            lines.append("| 區間 | 說明 | 參考配速 (/km) |")
            lines.append("| :--- | :--- | :--- |")
            lines.append(f"|  E   | 輕鬆跑 (Easy)     | {paces.get('E', 'N/A'):>8} |")
            lines.append(f"|  M   | 馬拉松 (Marathon) | {paces.get('M', 'N/A'):>8} |")
            lines.append(f"|  T   | 乳酸閾值 (Threshold)| {paces.get('T', 'N/A'):>8} |")
            lines.append(f"|  I   | 間歇訓練 (Interval) | {paces.get('I', 'N/A'):>8} |")
            lines.append(f"|  R   | 無氧反覆 (Repetition)| {paces.get('R', 'N/A'):>8} |")
            lines.append("```")
        lines.append("")

    # Recent activity feedback (RPE)
    feedback = p.get("activity_feedback", [])
    if feedback:
        lines.append("### 📊 近期訓練體感 (RPE)")
        for f in feedback[:3]: # Show latest 3
            pain_str = f" | 痛感: {f['pain_level']} ({f['pain_area']})" if f.get("pain_level", 0) > 0 else ""
            lines.append(f"• {f['date']}: RPE {f['rpe']}{pain_str}")
        lines.append("")

    # PBs
    pb = p.get("personal_bests", {})
    pb_lines = []
    labels = {"5k": "5 km", "10k": "10 km", "half_marathon": "半馬", "marathon": "全馬"}
    for key, label in labels.items():
        entries = pb.get(key, [])
        if entries:
            # Sort just to be safe, though they should be sorted
            sorted_entries = sorted(entries, key=lambda x: x.get("date", ""))
            # Show the history (last 3 entries) to see progression
            history_strs = []
            for e in sorted_entries[-3:]:
                race_note = f"（{e['race']}）" if e.get("race") else ""
                history_strs.append(f"{e['time']} ({e.get('date', '')}{race_note})")
            
            pb_lines.append(f"• {label} 進步史：{' ➔ '.join(history_strs)}")
            
    if pb_lines:
        lines.append("### 🏆 個人最佳成績 (PB)\n" + "\n".join(pb_lines))
    else:
        lines.append("### 🏆 個人最佳成績 (PB)\n• 尚未記錄")

    # Physiology History
    physio = p.get("physiology_history", [])
    if physio:
        lines.append("\n### 🧬 生理指標發展趨勢 (最新 3 筆)")
        for record in physio[-3:]:
            metrics = []
            if record.get("vo2max"): metrics.append(f"VO2Max: {record['vo2max']}")
            if record.get("lthr"): metrics.append(f"LTHR: {record['lthr']} bpm")
            if record.get("lt_pace"): metrics.append(f"閾值配速: {record['lt_pace']} /km")
            
            if metrics:
                lines.append(f"• {record.get('date', '未知日期')}：{', '.join(metrics)}")

    # Active injuries
    active = get_active_injuries(p)
    if active:
        lines.append("\n### ⚠️ 目前傷況")
        for i in active:
            lines.append(f"• [{i['status'].upper()}] {i['description']}（{i['start_date']}）")
            if i.get("notes"):
                lines.append(f"  → {i['notes']}")

    # Recent milestones
    milestones = p.get("progress_milestones", [])[-3:]
    if milestones:
        lines.append("\n### 🌟 近期里程碑")
        for m in milestones:
            lines.append(f"• {m['date']}：{m['description']}")

    # Recent coaching notes
    notes = p.get("coaching_notes", [])[-3:]
    if notes:
        lines.append("\n### 📝 教練備忘")
        for n in notes:
            lines.append(f"• {n['date']}：{n['note']}")

    # Long-term insights
    if include_insights:
        insights = p.get("long_term_insights", [])
        if insights:
            lines.append("\n### 💡 長期特質與偏好")
            for i in insights:
                category_tag = f"[{i['category'].upper()}] " if i.get("category") != "general" else ""
                lines.append(f"• {category_tag}{i['content']}")

    lines.append(f"\n*最後更新：{p.get('last_updated', '未知')}*")
    return "\n".join(lines)


if __name__ == "__main__":
    import sys
    if "--show" in sys.argv:
        print(format_profile_summary())
    else:
        print("Athlete Profile Module. Use --show to display summary.")
