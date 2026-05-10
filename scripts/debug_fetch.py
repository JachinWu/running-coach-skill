import sys
import os
import json
import datetime
from pathlib import Path

# Add the scripts directory to sys.path to import garmin
script_dir = Path(__file__).resolve().parent
sys.path.append(str(script_dir))

import garmin

def debug():
    print("--- Initializing Garmin API ---")
    api = garmin.init_api()
    if not api:
        print("Failed to initialize API. Check .env and credentials.")
        return

    today = datetime.date.today().isoformat()
    print(f"\n--- Raw Training Status for {today} ---")
    _, status, error = garmin.safe_api_call(api.get_training_status, today)
    if error:
        print(f"Error fetching status: {error}")
    else:
        # Print a sanitized version (omitting potential device IDs or sensitive IDs if any)
        print(json.dumps(status, indent=2, ensure_ascii=False))

    print("\n--- Comprehensive Daily Stats (Last 3 Days) ---")
    stats = garmin.get_comprehensive_daily_stats(api, 3)
    print(json.dumps(stats, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    debug()
