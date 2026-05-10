import sys
import os
import json
from unittest.mock import MagicMock

# Add scripts to path
sys.path.append(os.path.abspath(".gemini/skills/running-coach/scripts"))

import garmin

def test_null_safety():
    print("Testing get_comprehensive_daily_stats with NULL/None data...")
    
    # Mock API
    mock_api = MagicMock()
    
    # 1. Mock get_activities_by_date to return some activities with null types
    mock_api.get_activities_by_date.return_value = [
        {
            "startTimeLocal": "2026-05-08 10:00:00",
            "distance": 5000,
            "duration": 1800,
            "activityType": None, # This should trigger the error if not handled
            "averageHR": 150
        }
    ]
    
    # 2. Mock get_hrv_data to return None or missing summary
    mock_api.get_hrv_data.return_value = {"hrvSummary": None}
    
    # 3. Mock get_stats to return None
    mock_api.get_stats.return_value = None
    
    # 4. Mock get_training_status to return mostly nulls
    mock_api.get_training_status.return_value = {
        "mostRecentTrainingStatus": None,
        "dailyTrainingLoadAcute": None
    }

    try:
        # We need to monkeypatch safe_api_call because it uses real logic
        # Actually, let's just test if our logic inside get_comprehensive_daily_stats handles it
        # I'll manually run the loop logic with mocked results
        
        days = 1
        activities_list = garmin.get_daily_activities_list(mock_api, days)
        print(f"  get_daily_activities_list success: {activities_list}")
        
        stats = garmin.get_comprehensive_daily_stats(mock_api, days)
        print(f"  get_comprehensive_daily_stats success: {stats}")
        
    except Exception as e:
        print(f"❌ FAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    test_null_safety()
