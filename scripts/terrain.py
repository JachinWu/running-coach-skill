"""terrain.py — Utilities for Normalized Graded Pace (NGP) and elevation analysis."""

import math
from typing import Optional

def get_minetti_factor(grade: float) -> float:
    """
    Calculate the energy cost factor based on Alberto Minetti (2002).
    Cr = 155.4i^5 - 30.4i^4 - 43.3i^3 + 46.3i^2 + 19.5i + 3.6
    
    Args:
        grade: Decimal grade (e.g., 0.1 for 10% incline, -0.05 for 5% decline).
        
    Returns:
        Difficulty factor relative to flat ground (Cr_grade / Cr_flat).
    """
    # Cr_flat = 3.6 J/kg/m
    i = grade
    cr = 155.4*i**5 - 30.4*i**4 - 43.3*i**3 + 46.3*i**2 + 19.5*i + 3.6
    
    # Factor is how much harder/easier it is than flat
    factor = cr / 3.6
    
    # Safety constraints: 
    # 1. Minetti's formula is most accurate between -45% and +45%.
    # 2. In extreme declines, energy cost increases again (braking), 
    #    which Minetti captures, but we cap it for stability.
    return max(0.5, min(factor, 5.0))

def get_ngp_speed(avg_speed_ms: float, total_elevation_gain_m: float, total_distance_m: float) -> float:
    """
    Calculate Normalized Graded Pace speed (m/s).
    
    Args:
        avg_speed_ms: Actual average speed in m/s.
        total_elevation_gain_m: Total ascent in meters.
        total_distance_m: Total distance in meters.
        
    Returns:
        The equivalent speed on flat ground (m/s).
    """
    if total_distance_m <= 0:
        return avg_speed_ms
        
    # Calculate average positive grade
    # Note: This is a simplification since we don't have the full elevation profile.
    # On a loop or point-to-point, we use elevation gain to estimate the "work" done.
    avg_grade = total_elevation_gain_m / total_distance_m
    
    factor = get_minetti_factor(avg_grade)
    
    # NGP Speed = Actual Speed * Factor
    # (If it's uphill, factor > 1, so NGP speed > Actual speed)
    return avg_speed_ms * factor

def pace_to_ms(pace_str: str) -> float:
    """Convert 'M:SS' pace to m/s."""
    try:
        m, s = map(int, pace_str.split(':'))
        seconds_per_km = m * 60 + s
        return 1000.0 / seconds_per_km
    except:
        return 0.0

def ms_to_pace(ms: float) -> str:
    """Convert m/s to 'M:SS' pace."""
    if ms <= 0: return "0:00"
    seconds_per_km = 1000.0 / ms
    m = int(seconds_per_km // 60)
    s = int(seconds_per_km % 60)
    return f"{m}:{s:02d}"

if __name__ == "__main__":
    # Test case: 8:00 pace (2.083 m/s) on 10% grade
    speed_ms = pace_to_ms("8:00")
    # 10% grade means 100m gain over 1000m distance
    ngp = get_ngp_speed(speed_ms, 100, 1000)
    print(f"Actual: 8:00/km (10% grade) -> NGP: {ms_to_pace(ngp)}/km")
    
    # Test case: 4:00 pace (4.167 m/s) on flat
    ngp_flat = get_ngp_speed(pace_to_ms("4:00"), 0, 1000)
    print(f"Actual: 4:00/km (Flat) -> NGP: {ms_to_pace(ngp_flat)}/km")
