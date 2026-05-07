"""athlete_profile.py — Persistent athlete memory for the running coach.

Stores personal bests, injuries, progress milestones, and coaching notes.
Used by both the Telegram bot and the Gemini CLI running-coach skill.
"""

import json
import datetime
from pathlib import Path
from typing import Optional

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
    "physiology_history": [],  # List of {"date": str, "vo2max": float/None, "lthr": int/None, "lt_pace": str/None}
    "injuries": [],
    "health_notes": [],
    "progress_milestones": [],
    "coaching_notes": [],
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
        return dict(DEFAULT_PROFILE)
    try:
        with open(PROFILE_FILE, "r", encoding="utf-8") as f:
            stored = json.load(f)
        # Merge with defaults to handle schema additions gracefully
        merged = dict(DEFAULT_PROFILE)
        merged.update(stored)
        return merged
    except (json.JSONDecodeError, IOError):
        return dict(DEFAULT_PROFILE)


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


# ---------------------------------------------------------------------------
# Summary formatter (for display in Telegram / Gemini context)
# ---------------------------------------------------------------------------

def format_profile_summary(profile: Optional[dict] = None) -> str:
    """Return a human-readable Markdown summary of the athlete profile.

    Args:
        profile: Optional pre-loaded profile dict.

    Returns:
        Formatted Markdown string.
    """
    p = profile or load_profile()
    lines = ["## 🏅 運動員個人檔案\n"]

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

    lines.append(f"\n*最後更新：{p.get('last_updated', '未知')}*")
    return "\n".join(lines)


if __name__ == "__main__":
    import sys
    if "--show" in sys.argv:
        print(format_profile_summary())
    else:
        print("Athlete Profile Module. Use --show to display summary.")
