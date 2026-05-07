import sys
import datetime
from garmin import init_api

def get_recent_runs(days=14):
    """取得最近的跑步紀錄並印出摘要"""
    api = init_api()
    if not api:
        print("❌ 無法登入 Garmin")
        return
    
    end_date = datetime.date.today()
    start_date = end_date - datetime.timedelta(days=days)
    
    print(f"🔄 正在獲取從 {start_date} 到 {end_date} 的活動紀錄...\n")
    activities = api.get_activities_by_date(start_date.isoformat(), end_date.isoformat())
    
    # 過濾出跑步紀錄
    runs = [a for a in activities if a.get('activityType', {}).get('typeKey') == 'running']
    
    if not runs:
        print(f"ℹ️ 近 {days} 天內沒有跑步紀錄。")
        return

    print(f"📊 近 {days} 天的跑步紀錄摘要:")
    print("-" * 60)
    for r in runs:
        activity_id = r.get("activityId")
        date_str = r.get("startTimeLocal", "").split(" ")[0]
        name = r.get("activityName", "未命名")
        distance = r.get("distance", 0) / 1000.0
        duration = r.get("duration", 0) / 60.0
        avg_hr = r.get("averageHR", 0)
        max_hr = r.get("maxHR", 0)
        avg_speed = r.get("averageSpeed", 0)
        max_speed = r.get("maxSpeed", 0)
        
        # Training Effect
        te_label = r.get("trainingEffectLabel", "N/A")
        ae_te = r.get("aerobicTrainingEffect", 0.0)
        an_te = r.get("anaerobicTrainingEffect", 0.0)
        
        # Dynamics
        cadence = r.get("averageRunningCadenceInStepsPerMinute", 0)
        stride = r.get("avgStrideLength", 0)

        # 轉換配速
        def speed_to_pace(speed_ms):
            if not speed_ms or speed_ms <= 0:
                return "0:00"
            pace_sec = 1000 / speed_ms
            return f"{int(pace_sec // 60)}:{int(pace_sec % 60):02d}"

        avg_pace_str = speed_to_pace(avg_speed)
        max_pace_str = speed_to_pace(max_speed)
        
        print(f"📅 {date_str} | 🏃 {name}")
        print(f"   [基礎] 距離: {distance:.2f} km | 時間: {duration:.1f} 分 | 均速: {avg_pace_str} /km")
        print(f"   [強度] 心率: {avg_hr} (最高 {max_hr}) | 最快配速: {max_pace_str} /km")
        print(f"   [成效] 標籤: {te_label} | 有氧 TE: {ae_te} | 無氧 TE: {an_te}")
        print(f"   [動態] 步頻: {cadence} spm | 步幅: {stride} cm")
        
        # Fetch Laps
        try:
            splits_data = api.get_activity_splits(activity_id)
            laps = splits_data.get("lapDTOs", [])
            if laps:
                print("   [分段 (Laps)]")
                for lap in laps:
                    lap_idx = lap.get("lapIndex", 0)
                    l_dist = lap.get("distance", 0) / 1000.0
                    l_dur = lap.get("duration", 0) / 60.0
                    l_speed = lap.get("averageSpeed", 0)
                    l_hr = lap.get("averageHR", 0)
                    l_max_hr = lap.get("maxHR", 0)
                    l_cadence = lap.get("averageRunCadence", 0)
                    l_stride = lap.get("strideLength", 0)
                    l_pace = speed_to_pace(l_speed)
                    print(f"      L{lap_idx}: {l_dist:.2f} km | {l_dur:.1f} 分 | {l_pace} /km | HR {l_hr} | Cadence {l_cadence} | Stride {l_stride:.0f}cm")
        except Exception as e:
            print(f"   (無法獲取分段資料: {e})")
        
        print("-" * 60)

if __name__ == "__main__":
    days = 14
    if len(sys.argv) > 1:
        try:
            days = int(sys.argv[1])
        except ValueError:
            pass
    get_recent_runs(days)
