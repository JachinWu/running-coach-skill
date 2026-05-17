"""performance_vdot.py — Logic for tracking training-driven VDOT improvements."""

import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List

try:
    from . import daniels_formula
    from . import athlete_profile
    from . import weather
    from . import terrain
except ImportError:
    import daniels_formula
    import athlete_profile
    import weather
    import terrain

# Threshold for proposing a VDOT update
VDOT_UPDATE_THRESHOLD = 0.5 
# Minimum number of consistent sessions before proposing
MIN_SESSIONS = 3

def get_heat_adjustment_factor(temp: float, humidity: float = 50.0) -> float:
    """Calculate a performance adjustment factor based on heat and humidity.
    
    Reference: Simplified adjustments based on dew point or temperature thresholds.
    Returns a multiplier (e.g., 1.02 for 2% slower potential).
    """
    # Performance starts to decline significantly above 15°C (60°F)
    if temp <= 15:
        return 1.0
    
    # Simple linear approximation: ~0.5% to 1% performance loss per 3°C above 15°C
    # High humidity (>70%) adds extra stress
    adjustment = (temp - 15) * 0.003
    if humidity > 70:
        adjustment += (humidity - 70) * 0.001
        
    return 1.0 + adjustment

def calculate_session_vdot(activity: Dict[str, Any], profile: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Estimate VDOT for a single running session and determine confidence."""
    
    # Extract metrics
    dist_m = activity.get("distance", 0)
    dur_s = activity.get("duration", 0)
    avg_hr = activity.get("averageHR")
    elev_gain = activity.get("elevationGain") or activity.get("totalAscent", 0)
    
    # Calculate NGP speed if elevation data is present
    avg_speed_ms = dist_m / dur_s if dur_s > 0 else 0
    ngp_speed_ms = terrain.get_ngp_speed(avg_speed_ms, elev_gain, dist_m)
    
    # Try to fetch weather for environment adjustment
    start_lat = activity.get("startLatitude")
    start_lon = activity.get("startLongitude")
    weather_data = None
    heat_factor = 1.0
    
    if start_lat and start_lon:
        weather_data = weather.get_weather_by_coords(start_lat, start_lon)
        if weather_data and weather_data.get("temp"):
            try:
                temp = float(weather_data["temp"])
                hum = float(weather_data.get("humidity", 50.0))
                heat_factor = get_heat_adjustment_factor(temp, hum)
            except (ValueError, TypeError):
                pass

    # Physiology needs max and rest HR for HRR calculation
    max_hr = 190 # Default if unknown
    rest_hr = 50 # Default if unknown
    
    physio = profile.get("physiology_history", [])
    if physio:
        latest = physio[-1]
        if latest.get("max_hr"): max_hr = latest["max_hr"]
        if latest.get("rest_hr"): rest_hr = latest["rest_hr"]
    
    if not avg_hr or dist_m < 3000: # Ignore very short runs
        return None
        
    # Use NGP distance for VDOT estimation (speed * duration)
    ngp_dist_m = ngp_speed_ms * dur_s
    
    vdot_est = daniels_formula.estimate_vdot_from_run(
        ngp_dist_m, dur_s, avg_hr, max_hr, rest_hr
    )
    
    if vdot_est <= 0:
        return None
        
    # Apply heat adjustment: if it's hot, the "potential" VDOT is higher than measured
    vdot_est = round(vdot_est * (heat_factor ** 0.5), 2)
    
    # Confidence scoring
    confidence = 0.5
    
    # 1. Intensity: E-runs (60-80% HRR) are most reliable for estimation
    percent_hrr = (avg_hr - rest_hr) / (max_hr - rest_hr)
    if 0.60 <= percent_hrr <= 0.80:
        confidence += 0.3
    
    # 2. Duration: Longer runs (steady state) are better
    if dur_s > 1800: # > 30 mins
        confidence += 0.2
        
    return {
        "activity_id": activity.get("activityId"),
        "date": activity.get("startTimeLocal", "")[:10],
        "vdot_est": vdot_est,
        "confidence": round(confidence, 2),
        "terrain": {
            "elevation_gain": elev_gain,
            "ngp_pace": terrain.ms_to_pace(ngp_speed_ms),
            "actual_pace": terrain.ms_to_pace(avg_speed_ms)
        },
        "weather": {
            "temp": weather_data.get("temp") if weather_data else None,
            "humidity": weather_data.get("humidity") if weather_data else None,
            "heat_factor": round(heat_factor, 3)
        } if weather_data else None
    }

def update_vdot_tracking(session_data: Dict[str, Any]):
    """Store the session VDOT in the athlete profile for trend analysis."""
    profile = athlete_profile.load_profile()
    
    if "vdot_history" not in profile:
        profile["vdot_history"] = []
        
    profile["vdot_history"].append(session_data)
    # Keep last 20 sessions
    profile["vdot_history"] = profile["vdot_history"][-20:]
    
    athlete_profile.save_profile(profile)

def analyze_vdot_trend() -> Optional[Dict[str, Any]]:
    """Analyze recent session VDOTs and propose an update if a trend is found."""
    profile = athlete_profile.load_profile()
    history = profile.get("vdot_history", [])
    current_vdot = profile.get("vdot", 0.0)
    
    if len(history) < MIN_SESSIONS or current_vdot == 0:
        return None
        
    # Filter for high confidence sessions
    reliable_sessions = [s for s in history if s.get("confidence", 0) >= 0.7]
    if len(reliable_sessions) < MIN_SESSIONS:
        return None
        
    # Calculate weighted average of recent VDOTs
    avg_vdot = sum(s["vdot_est"] for s in reliable_sessions[-MIN_SESSIONS:]) / MIN_SESSIONS
    
    diff = avg_vdot - current_vdot
    
    if diff >= VDOT_UPDATE_THRESHOLD:
        return {
            "current_vdot": current_vdot,
            "proposed_vdot": round(avg_vdot, 1),
            "avg_vdot": round(avg_vdot, 2),
            "improvement": round(diff, 1),
            "reason": f"近期 {len(reliable_sessions[-MIN_SESSIONS:])} 次高品質訓練顯示您的體能有顯著進步。"
        }
    elif diff <= -VDOT_UPDATE_THRESHOLD * 2: # More conservative on down-ranking
         return {
            "current_vdot": current_vdot,
            "proposed_vdot": round(avg_vdot, 1),
            "avg_vdot": round(avg_vdot, 2),
            "improvement": round(diff, 1),
            "reason": f"近期訓練數據顯示體能略有下滑，建議暫時下修 VDOT 以確保訓練強度適中。"
        }
        
    return None

def calculate_goal_projection(profile: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Compare current VDOT with target VDOT based on race goal."""
    current_vdot = profile.get("vdot")
    goal_date_str = profile.get("target_race_date")
    goal_dist_km = profile.get("target_race_distance_km")
    goal_time_str = profile.get("target_race_time")
    
    if not all([current_vdot, goal_date_str, goal_dist_km]):
        return None
        
    try:
        # 1. Calculate Target VDOT (if goal time exists)
        goal_dist_m = goal_dist_km * 1000
        target_vdot = 0.0
        if goal_time_str:
            goal_time_s = athlete_profile._parse_time_to_seconds(goal_time_str)
            target_vdot = daniels_formula.calculate_vdot(goal_dist_m, goal_time_s)
        
        # 2. Calculate Gap and Weeks
        race_date = datetime.date.fromisoformat(goal_date_str)
        days_remaining = (race_date - datetime.date.today()).days
        weeks_remaining = days_remaining / 7.0
        
        if weeks_remaining <= 0:
            return {
                "status": "expired",
                "days_ago": abs(days_remaining)
            }
            
        result = {
            "current_vdot": round(current_vdot, 2),
            "weeks_remaining": round(weeks_remaining, 1),
            "status": "no_target_time"
        }

        if target_vdot > 0:
            vdot_gap = target_vdot - current_vdot
            weekly_required_gain = vdot_gap / weeks_remaining if weeks_remaining > 0 else vdot_gap
            
            # 3. Assess Difficulty (Empirical benchmarks)
            suggestion = ""
            if weekly_required_gain > 0.3:
                difficulty = "🔥🔥 高難度 (挑戰極大)"
                status = "at_risk"
                suggestion = f"目標極具挑戰性。建議優先確保不受傷，並嘗試微調目標時間或延長備賽期。"
            elif weekly_required_gain > 0.1:
                difficulty = "📈 中等 (需穩定執行計畫)"
                status = "on_track"
                suggestion = f"目前進度穩定。維持每週提升 {round(weekly_required_gain, 2)} VDOT 即可達標。"
            elif weekly_required_gain > 0:
                difficulty = "✅ 良好 (按部就班即可)"
                status = "secure"
                suggestion = f"進度領先！繼續保持目前節奏，穩定發揮即可順利達標。"
            else:
                difficulty = "👑 卓越 (已超越目標能力)"
                status = "achieved"
                # Calculate potential time based on current VDOT
                potential_seconds = daniels_formula.calculate_time_for_vdot(goal_dist_m, current_vdot)
                potential_time = athlete_profile._format_seconds_to_time(potential_seconds)
                suggestion = f"您的實力已超越目標！建議縮短完賽目標至 {potential_time} 以發揮最大潛能。"
                
            result.update({
                "target_vdot": round(target_vdot, 2),
                "vdot_gap": round(vdot_gap, 2),
                "weekly_required_gain": round(weekly_required_gain, 3),
                "difficulty": difficulty,
                "status": status,
                "suggestion": suggestion
            })
            
        return result
    except Exception:
        return None

if __name__ == "__main__":
    # Test logic
    trend = analyze_vdot_trend()
    if trend:
        print(f"Proposed Update: {trend}")
    else:
        print("No significant VDOT trend detected.")
