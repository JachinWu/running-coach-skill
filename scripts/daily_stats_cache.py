import sqlite3
import json
from pathlib import Path
from typing import List, Dict, Any

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "daily_stats.db"

def _init_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS daily_stats (
                date TEXT PRIMARY KEY,
                data TEXT NOT NULL,
                last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.commit()

def get_cached_stats(dates: List[str]) -> Dict[str, Dict[str, Any]]:
    _init_db()
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        placeholders = ','.join('?' for _ in dates)
        cursor.execute(f'SELECT date, data FROM daily_stats WHERE date IN ({placeholders})', dates)
        return {row[0]: json.loads(row[1]) for row in cursor.fetchall()}

def save_stats(stats_list: List[Dict[str, Any]]) -> None:
    _init_db()
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        for stats in stats_list:
            if 'date' in stats:
                cursor.execute('''
                    INSERT OR REPLACE INTO daily_stats (date, data)
                    VALUES (?, ?)
                ''', (stats['date'], json.dumps(stats)))
        conn.commit()
