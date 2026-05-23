"""performance_radar.py — Logic for Runner Combat Radar and Genre Evolution."""

from typing import Dict, Any, List, Tuple
import math

def calculate_radar_scores(
    weekly_dist_km: float,
    vdot: float,
    frequency_days: int,
    total_elev_gain: float,
    hrv_stability: float,  # 0.0 to 1.0
    consistency_score: float = 85.0  # Placeholder for plan execution rate
) -> Dict[str, float]:
    """Calculate 0-100 scores for the five radar dimensions."""
    
    # 1. Endurance (Base on 80km/week as 100)
    endurance = min(100, (weekly_dist_km / 80.0) * 100)
    
    # 2. Speed (Base on VDOT 65 as 100, VDOT 30 as 0)
    speed = min(100, max(0, (vdot - 30) / (65 - 30) * 100))
    
    # 3. Consistency (Base on 6 days/week + consistency_score)
    consistency = min(100, (min(100, (frequency_days / 6.0) * 50) + (consistency_score / 2.0)))
    
    # 4. Terrain (Base on 1000m elevation gain as 100)
    terrain = min(100, (total_elev_gain / 1000.0) * 100)
    
    # 5. Resilience (Base on HRV stability and workload safety)
    resilience = min(100, hrv_stability * 100)
    
    return {
        "耐力": round(endurance, 1),
        "速度": round(speed, 1),
        "一致性": round(consistency, 1),
        "地形適應": round(terrain, 1),
        "恢復力": round(resilience, 1)
    }

def determine_genre(scores: Dict[str, float]) -> str:
    """Determine the runner's genre based on radar scores."""
    vals = list(scores.values())
    max_val = max(vals)
    min_val = min(vals)
    avg_val = sum(vals) / len(vals)
    
    # 1. All-Rounder (Low deviation)
    if all(abs(v - avg_val) < 15 for v in vals):
        return "全能戰士｜All-Rounder"
    
    # 2. Specializations
    if scores["地形適應"] >= 85:
        return "山地靈羊｜Mountain Goat"
    
    if scores["速度"] >= 85 and scores["耐力"] < 70:
        return "速度獵豹｜Speed Cheetah"
        
    if scores["一致性"] >= 90 and scores["恢復力"] >= 80:
        return "穩定節拍器｜Steady Metronome"
    
    if scores["耐力"] >= 85 and scores["速度"] < 75:
        return "耐力大師｜Endurance Master"
        
    # Default to the highest dimension
    highest_dim = max(scores, key=scores.get)
    dim_to_genre = {
        "耐力": "長距離行者｜Long Distance Walker",
        "速度": "疾速先鋒｜Velocity Vanguard",
        "一致性": "律動苦行僧｜Rhythm Ascetic",
        "地形適應": "巔峰征服者｜Peak Conqueror",
        "恢復力": "鋼鐵修復師｜Iron Recovery Smith"
    }
    return dim_to_genre.get(highest_dim, "進化中跑者｜Evolving Runner")

GENRE_PROMPTS = {
    "全能戰士｜All-Rounder": "各項能力均衡，具備極高潛力，建議尋找專屬突破維度。",
    "山地靈羊｜Mountain Goat": "極強地形適應力，山徑即主場，建議加強核心穩定性。",
    "速度獵豹｜Speed Cheetah": "瞬時速度極高，VO2 Max 出色，建議增加低強度恢復跑比例。",
    "穩定節拍器｜Steady Metronome": "訓練一致性極高，恢復節奏優秀，是長期進步的核心型跑者。",
    "耐力大師｜Endurance Master": "耐力基礎深厚，建議加入間歇課表提升巡航速度。",
    "長距離行者｜Long Distance Walker": "有氧基礎穩定，建議加入 Tempo 訓練提升速耐力。",
    "疾速先鋒｜Velocity Vanguard": "高速輸出能力驚人，需重視恢復與防護管理。",
    "律動苦行僧｜Rhythm Ascetic": "穩定節奏能維持長期身心平衡，是高度自律型跑者。",
    "巔峰征服者｜Peak Conqueror": "擅長極限地形挑戰，建議加強下肢穩定與下降控制。",
    "鋼鐵修復師｜Iron Recovery Smith": "恢復效率極高，能承受高密度訓練，但仍需監控疲勞訊號。",
    "進化中跑者｜Evolving Runner": "正處於關鍵成長階段，建議跟隨長期計畫探索自身特長。"
}

if __name__ == "__main__":
    # Test case
    test_scores = calculate_radar_scores(
        weekly_dist_km=45,
        vdot=48.5,
        frequency_days=5,
        total_elev_gain=350,
        hrv_stability=0.88
    )
    print(f"Scores: {test_scores}")
    print(f"Genre: {determine_genre(test_scores)}")
