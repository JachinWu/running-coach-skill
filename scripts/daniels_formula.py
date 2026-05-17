import math
from typing import Dict, Tuple

def calculate_vdot(distance_meters: float, time_seconds: float) -> float:
    """
    Calculate VDOT based on race distance and time using Daniels' formula.
    VO2 = -4.60 + 0.182258 * V + 0.000104 * V^2
    %VO2max = 0.8 + 0.1894393 * e^(-0.012778 * t) + 0.2989558 * e^(-0.1932605 * t)
    VDOT = VO2 / %VO2max
    """
    t_min = time_seconds / 60.0
    v = distance_meters / t_min
    
    vo2 = -4.60 + 0.182258 * v + 0.000104 * pow(v, 2)
    percent_vo2max = (
        0.8 
        + 0.1894393 * math.exp(-0.012778 * t_min) 
        + 0.2989558 * math.exp(-0.1932605 * t_min)
    )
    
    return round(vo2 / percent_vo2max, 2)

def get_velocity_for_vdot_percent(vdot: float, percent: float) -> float:
    """
    Find the velocity (m/min) that corresponds to a certain percentage of VDOT.
    Using quadratic formula on: 0.000104 * V^2 + 0.182258 * V - (4.60 + target_vo2) = 0
    """
    target_vo2 = vdot * percent
    # a*V^2 + b*V + c = 0
    a = 0.000104
    b = 0.182258
    c = -(4.60 + target_vo2)
    
    # V = (-b + sqrt(b^2 - 4ac)) / 2a
    v = (-b + math.sqrt(pow(b, 2) - 4 * a * c)) / (2 * a)
    return v

def pace_to_str(velocity_m_per_min: float) -> str:
    """Convert velocity (m/min) to pace string (min:sec / km)."""
    if velocity_m_per_min <= 0:
        return "N/A"
    pace_min_float = 1000.0 / velocity_m_per_min
    minutes = int(pace_min_float)
    seconds = int(round((pace_min_float - minutes) * 60))
    if seconds == 60:
        minutes += 1
        seconds = 0
    return f"{minutes}:{seconds:02d}"

def calculate_paces(vdot: float) -> Dict[str, str]:
    """
    Calculate E, M, T, I, R pace zones based on VDOT.
    Percentages based on typical Daniels' tables:
    E: ~62-70% (using 66% as representative)
    M: ~80%
    T: 88%
    I: 97.5%
    R: 110%
    """
    zones = {
        "E": 0.66,
        "M": 0.80,
        "T": 0.88,
        "I": 0.975,
        "R": 1.10
    }
    
    paces = {}
    for zone, percent in zones.items():
        v = get_velocity_for_vdot_percent(vdot, percent)
        paces[zone] = pace_to_str(v)
        
    return paces

def estimate_vdot_from_run(
    distance_meters: float, 
    time_seconds: float, 
    avg_hr: float, 
    max_hr: float, 
    rest_hr: float
) -> float:
    """
    Estimate VDOT from a submaximal run.
    Relies on the linear relationship between %HRR and %VO2max.
    VO2_actual = -4.60 + 0.182258 * V + 0.000104 * V^2
    %VO2max approx= %HRR = (avg_hr - rest_hr) / (max_hr - rest_hr)
    VDOT_est = VO2_actual / %VO2max
    """
    if max_hr <= rest_hr or avg_hr <= rest_hr:
        return 0.0
        
    t_min = time_seconds / 60.0
    v = distance_meters / t_min
    
    # Calculate VO2 for this velocity
    vo2_actual = -4.60 + 0.182258 * v + 0.000104 * pow(v, 2)
    
    # Calculate intensity as % of Heart Rate Reserve
    percent_hrr = (avg_hr - rest_hr) / (max_hr - rest_hr)
    
    # Daniels notes that %HRR is a very good proxy for %VO2max
    if percent_hrr <= 0.4: # Too low intensity for reliable estimation
        return 0.0
        
    vdot_est = vo2_actual / percent_hrr
    return round(vdot_est, 2)

def calculate_time_for_vdot(distance_meters: float, vdot: float) -> float:
    """
    Find the finish time (in seconds) for a given distance and VDOT.
    Uses binary search since both VO2 and %VO2max depend on time.
    """
    if vdot <= 0:
        return 0.0
        
    # Search range: 1 minute to 1000 minutes
    low = 60.0
    high = 60000.0
    
    for _ in range(50): # 50 iterations for high precision
        mid_t = (low + high) / 2
        est_vdot = calculate_vdot(distance_meters, mid_t)
        
        if est_vdot < vdot:
            # Too slow, need less time
            high = mid_t
        else:
            # Too fast, need more time
            low = mid_t
            
    return round(mid_t, 1)

if __name__ == "__main__":
    # Quick test: 5K in 20:00 should be approx VDOT 50.5
    vdot_5k = calculate_vdot(5000, 1200)
    print(f"VDOT for 5K in 20:00: {vdot_5k}")
    paces = calculate_paces(vdot_5k)
    print(f"Paces: {paces}")
