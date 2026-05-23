"""race_pacer.py — Logic for calculating race pacing blueprints from GPX files."""

import gpxpy
import gpxpy.gpx
import math
from typing import List, Dict, Any, Optional
try:
    from . import terrain
    from . import daniels_formula
except ImportError:
    import terrain
    import daniels_formula

def calculate_race_blueprint(
    gpx_path: str, 
    target_ngp_pace: str, 
    split_km: float = 1.0,
    weather_factor: float = 1.0,
    max_hr: Optional[int] = None,
    rest_hr: Optional[int] = None,
    vdot: Optional[float] = None
) -> Dict[str, Any]:
    """
    Parses a GPX file and calculates elevation-adjusted pacing for each split.
    
    Args:
        gpx_path: Path to the .gpx file.
        target_ngp_pace: Target effort in "M:SS" (e.g., "5:00").
        split_km: Distance for each split in kilometers.
        weather_factor: Multiplier for pace due to heat (e.g., 1.02 = 2% slower).
        max_hr, rest_hr: For heart rate range calculation.
        vdot: Current athlete VDOT to calculate intensity.
        
    Returns:
        A dictionary containing the blueprint data and summary.
    """
    with open(gpx_path, 'r') as gpx_file:
        gpx = gpxpy.parse(gpx_file)

    # Base speed from target pace
    base_speed_ms = terrain.pace_to_ms(target_ngp_pace)
    if base_speed_ms <= 0:
        raise ValueError(f"Invalid target pace: {target_ngp_pace}")

    # 1. Apply Weather Factor (Heat/Humidity)
    # If weather_factor = 1.02, speed = base_speed / 1.02 (slower)
    adjusted_target_speed_ms = base_speed_ms / weather_factor
    adjusted_target_pace = terrain.ms_to_pace(adjusted_target_speed_ms)

    # 2. Calculate Intensity & Expected HR
    expected_hr = None
    if max_hr and rest_hr and vdot:
        # VO2 = -4.60 + 0.182258 * V + 0.000104 * V^2 (V in m/min)
        v_m_min = base_speed_ms * 60.0
        vo2 = -4.60 + 0.182258 * v_m_min + 0.000104 * (v_m_min ** 2)
        intensity = vo2 / vdot # %VO2max
        
        # Expected HR = Rest + (Max - Rest) * Intensity
        # Note: Daniels suggests %VO2max and %HRR are very close.
        # However, for E-pace, intensity might be slightly lower than HRR.
        # We'll use a +/- 3 bpm range.
        hr_val = rest_hr + (max_hr - rest_hr) * intensity
        expected_hr = f"{int(hr_val - 3)}-{int(hr_val + 3)}"

    splits = []
    last_point = None
    
    # Accumulated stats for the current split
    split_dist = 0.0
    split_gain = 0.0
    split_loss = 0.0
    
    for track in gpx.tracks:
        for segment in track.segments:
            for point in segment.points:
                if last_point:
                    dist = point.distance_3d(last_point)
                    elev_diff = point.elevation - last_point.elevation
                    
                    split_dist += dist
                    if elev_diff > 0:
                        split_gain += elev_diff
                    else:
                        split_loss += abs(elev_diff)
                    
                    if split_dist >= split_km * 1000:
                        grade = (split_gain - split_loss) / split_dist
                        factor = terrain.get_minetti_factor(grade)
                        
                        # NGP_speed = actual_speed * factor
                        actual_speed = adjusted_target_speed_ms / factor
                        
                        splits.append({
                            "km": len(splits) + 1,
                            "distance_m": round(split_dist, 1),
                            "gain_m": round(split_gain, 1),
                            "loss_m": round(split_loss, 1),
                            "grade_pct": round(grade * 100, 2),
                            "suggested_pace": terrain.ms_to_pace(actual_speed),
                            "factor": round(factor, 3),
                            "expected_hr": expected_hr
                        })
                        
                        split_dist = 0.0
                        split_gain = 0.0
                        split_loss = 0.0
                
                last_point = point
    
    if split_dist > 0:
        grade = (split_gain - split_loss) / split_dist
        factor = terrain.get_minetti_factor(grade)
        actual_speed = adjusted_target_speed_ms / factor
        splits.append({
            "km": len(splits) + 1,
            "distance_m": round(split_dist, 1),
            "gain_m": round(split_gain, 1),
            "loss_m": round(split_loss, 1),
            "grade_pct": round(grade * 100, 2),
            "suggested_pace": terrain.ms_to_pace(actual_speed),
            "factor": round(factor, 3),
            "expected_hr": expected_hr
        })

    total_dist = sum(s["distance_m"] for s in splits) / 1000.0
    total_gain = sum(s["gain_m"] for s in splits)
    total_loss = sum(s["loss_m"] for s in splits)
    
    total_seconds = 0
    for s in splits:
        pace_parts = s["suggested_pace"].split(":")
        sec = int(pace_parts[0]) * 60 + int(pace_parts[1])
        total_seconds += (sec * (s["distance_m"] / 1000.0))
        
    hours = int(total_seconds // 3600)
    minutes = int((total_seconds % 3600) // 60)
    seconds = int(total_seconds % 60)
    estimated_time = f"{hours:02d}:{minutes:02d}:{seconds:02d}" if hours > 0 else f"{minutes:02d}:{seconds:02d}"

    return {
        "splits": splits,
        "summary": {
            "total_distance_km": round(total_dist, 2),
            "total_gain_m": round(total_gain, 1),
            "total_loss_m": round(total_loss, 1),
            "target_ngp_pace": target_ngp_pace,
            "adjusted_target_pace": adjusted_target_pace,
            "weather_factor": weather_factor,
            "estimated_total_time": estimated_time
        }
    }

def format_blueprint_markdown(data: Dict[str, Any]) -> str:
    """Formats the blueprint data into a readable Markdown table."""
    s = data["summary"]
    weather_note = ""
    if s['weather_factor'] > 1.0:
        weather_note = f"\n⚠️ **環境補正**：偵測到溫濕度壓力，配速已自動下修 {round((s['weather_factor']-1)*100, 1)}%（原 {s['target_ngp_pace']} → 補正後 {s['adjusted_target_pace']}）。"

    output = [
        f"🏁 **賽事配速藍圖 (Race Blueprint)**",
        f"• 總距離：{s['total_distance_km']} km",
        f"• 總爬升/下降：+{s['total_gain_m']} / -{s['total_loss_m']} m",
        f"• 目標體感配速 (NGP)：{s['target_ngp_pace']} /km",
        f"• 預估完賽時間：**{s['estimated_total_time']}**",
        weather_note,
        "",
        "| 公里 | 坡度 | 爬升/下降 | 建議配速 | 預期心率 |",
        "| :--- | :--- | :--- | :--- | :--- |"
    ]
    
    for split in data["splits"]:
        grade_str = f"{split['grade_pct']}%"
        elev_str = f"+{split['gain_m']}/-{split['loss_m']}"
        hr_str = split.get("expected_hr", "--")
        output.append(f"| {split['km']} | {grade_str} | {elev_str} | **{split['suggested_pace']}** | {hr_str} |")
        
    output.append("\n💡 *註 1：建議配速已根據坡度與環境補正，維持穩定的體感負荷。*")
    output.append("💡 *註 2：預期心率為穩定狀態下的估計值，賽事後半段可能因心率飄移 (Cardiac Drift) 而上升。*")
    return "\n".join(output)
