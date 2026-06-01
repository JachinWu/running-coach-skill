"""gear_manager.py — Manage running shoe performance metrics and efficiency tracking."""

import sqlite3
import os
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple

# Setup paths
SKILL_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = SKILL_DIR / "data"
DB_PATH = DATA_DIR / "gear_metrics.db"

def init_db():
    """Initialize the gear metrics database."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Create activities table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS shoe_activities (
        activity_id TEXT PRIMARY KEY,
        shoe_nickname TEXT,
        date TEXT,
        distance_km REAL,
        avg_hr REAL,
        ngp_speed_ms REAL,
        efficiency_index REAL,
        FOREIGN KEY (shoe_nickname) REFERENCES shoes (nickname)
    )
    ''')
    
    conn.commit()
    conn.close()

def record_shoe_activity(
    activity_id: str,
    nickname: str,
    date: str,
    dist_km: float,
    avg_hr: float,
    ngp_speed_ms: float
) -> Dict[str, Any]:
    """Record a run activity for a specific shoe and return its metrics."""
    init_db()
    
    # Efficiency Index = NGP (m/s) / Average HR
    # Higher is better (more speed per heartbeat)
    efficiency_index = 0.0
    if (avg_hr or 0) > 0:
        efficiency_index = round((ngp_speed_ms or 0) / avg_hr, 6)
        
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    try:
        cursor.execute('''
        INSERT OR REPLACE INTO shoe_activities 
        (activity_id, shoe_nickname, date, distance_km, avg_hr, ngp_speed_ms, efficiency_index)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (activity_id, nickname, date, dist_km, avg_hr, ngp_speed_ms, efficiency_index))
        conn.commit()
    finally:
        conn.close()
        
    return {
        "efficiency_index": efficiency_index,
        "ngp_speed_ms": ngp_speed_ms
    }

def get_shoe_stats(nickname: str) -> Dict[str, Any]:
    """Calculate aggregate statistics for a specific shoe."""
    init_db()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    try:
        # Get average efficiency and total counts
        cursor.execute('''
        SELECT 
            AVG(efficiency_index), 
            COUNT(activity_id), 
            SUM(distance_km)
        FROM shoe_activities
        WHERE shoe_nickname = ? AND efficiency_index > 0
        ''', (nickname,))
        
        row = cursor.fetchone()
        avg_efficiency = (row[0] or 0.0) if row else 0.0
        count = (row[1] or 0) if row else 0
        sql_total_km = (row[2] or 0.0) if row else 0.0
        
        # Priority: If athlete_profile has a matching shoe, use its cumulative mileage
        # as it includes historical data before the SQL DB was introduced.
        total_km = sql_total_km
        shoe_model = nickname  # Default to nickname if model not found
        try:
            from . import athlete_profile
            profile = athlete_profile.load_profile()
            for s in profile.get("shoes", []):
                if s["nickname"] == nickname:
                    total_km = max(total_km, s.get("current_km", 0.0))
                    shoe_model = s.get("model", nickname)
                    break
        except Exception:
            # Fallback to standalone import if package-style fails
            try:
                import athlete_profile
                profile = athlete_profile.load_profile()
                for s in profile.get("shoes", []):
                    if s["nickname"] == nickname:
                        total_km = max(total_km, s.get("current_km", 0.0))
                        shoe_model = s.get("model", nickname)
                        break
            except Exception:
                pass
        
        # Get trend (compare last 3 runs vs historical average)
        cursor.execute('''
        SELECT AVG(efficiency_index)
        FROM (
            SELECT efficiency_index FROM shoe_activities
            WHERE shoe_nickname = ? AND efficiency_index > 0
            ORDER BY date DESC
            LIMIT 3
        )
        ''', (nickname,))
        row_recent = cursor.fetchone()
        recent_avg = (row_recent[0] or 0.0) if row_recent else 0.0
        
        return {
            "nickname": nickname,
            "model": shoe_model,
            "avg_efficiency": round(avg_efficiency, 6),
            "recent_avg": round(recent_avg, 6),
            "activity_count": count,
            "total_km": round(total_km, 2),
            "deviation_pct": round(((recent_avg / avg_efficiency) - 1) * 100, 2) if avg_efficiency > 0 else 0.0
        }
    finally:
        conn.close()

def get_shoe_for_activity(activity_id: str) -> Optional[str]:
    """Retrieve the shoe nickname associated with a specific activity ID."""
    if not activity_id:
        return None
        
    init_db()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute('SELECT shoe_nickname FROM shoe_activities WHERE activity_id = ?', (str(activity_id),))
        row = cursor.fetchone()
        return row[0] if row else None
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"Error fetching shoe for activity {activity_id}: {e}")
        return None
    finally:
        conn.close()

if __name__ == "__main__":
    init_db()
    print("Gear database initialized.")
