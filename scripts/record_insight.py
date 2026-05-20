"""record_insight.py — Smart integration script for recording athlete insights.

This script ensures that any new insight is recorded in the local JSON profile
(Source of Truth) and, if available, synced to the contextual-memory vector DB.
"""

import sys
import os
import argparse
from pathlib import Path

# Setup paths
SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS_DIR))

import athlete_profile

def record_insight(content: str, category: str = "general"):
    """Record an insight to both local JSON and vector memory (if available)."""
    
    # 1. Always save to local JSON (Athlete Profile)
    print(f"📦 Saving to local profile (JSON)...")
    athlete_profile.add_long_term_insight(content, category)
    
    # 2. Try to sync to Contextual Memory (Vector DB)
    # The running-coach skill is at .gemini/skills/running-coach
    # The contextual-memory skill is at .gemini/skills/contextual-memory
    skill_add_script = SCRIPTS_DIR.parent.parent / "contextual-memory" / "scripts" / "add_memory.py"
    
    if skill_add_script.exists():
        print(f"🧠 Syncing to Contextual Memory (Vector)...")
        try:
            import subprocess
            # Use 'project' type for coach insights, category can be the one passed
            cmd = [
                "python3", str(skill_add_script),
                "--content", content,
                "--type", "running-coach",
                "--category", category
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, check=False)
            if result.returncode == 0:
                print(f"✅ Vector sync successful.")
            else:
                print(f"⚠️ Vector sync returned error: {result.stderr.strip()}")
        except Exception as e:
            print(f"❌ Failed to sync to vector memory: {e}")
    else:
        print(f"ℹ️ Contextual-memory skill not found. Skipping vector sync.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Record an athlete insight.")
    parser.add_argument("content", help="The insight content to record.")
    parser.add_argument("--category", default="general", help="Category (e.g., preference, habit, injury).")
    
    args = parser.parse_args()
    record_insight(args.content, args.category)
