import json
import requests
import logging
import datetime
import urllib.parse
from typing import Dict, Any, Optional
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm

logger = logging.getLogger(__name__)


def generate_activity_chart(api, activity: Dict[str, Any], output_path: str = "activity_chart.png") -> Optional[str]:
    """Generates a highly customized Matplotlib chart for a single activity.
    
    Returns the path to the generated image, or None if failed.
    """
    try:
        activity_id = activity["activityId"]
        activity_name = activity.get("activityName", "跑步活動")
        start_time_local = activity.get("startTimeLocal", "")
        
        avg_hr = activity.get("averageHR", 0)
        max_hr = activity.get("maxHR", 0)
        avg_speed = activity.get("averageSpeed", 0)
        max_speed = activity.get("maxSpeed", 0)
        avg_cadence = activity.get("averageRunningCadenceInStepsPerMinute", 0)
        max_cadence = activity.get("maxRunningCadenceInStepsPerMinute", 0)
        
        # Official values
        elev_gain = activity.get("elevationGain", 0)
        elev_loss = activity.get("elevationLoss", 0)
        
        owner_name = activity.get("ownerFullName", "")
        avatar_url = activity.get("ownerProfileImageUrlSmall", "")
        load_val = activity.get("activityTrainingLoad", 0)
        aerobic_te = activity.get("aerobicTrainingEffect", 0)
        anaerobic_te = activity.get("anaerobicTrainingEffect", 0)
        total_steps = activity.get("steps", 0)
        calories = activity.get("calories", 0)

        avatar_img = None
        if avatar_url:
            from PIL import Image
            from io import BytesIO
            try:
                resp = requests.get(avatar_url, timeout=10)
                if resp.status_code == 200:
                    avatar_img = Image.open(BytesIO(resp.content))
            except Exception as e:
                logger.warning(f"Failed to download avatar: {e}")

        # Fetch Detailed Telemetry and Splits
        details = api.get_activity_details(activity_id)
        splits = api.get_activity_splits(activity_id)
        
        descriptors = details.get("metricDescriptors", [])
        metrics = details.get("activityDetailMetrics", [])
        laps = splits.get("lapDTOs", [])

        if not metrics:
            logger.warning(f"No metrics found for activity {activity_id}")
            return None

        # Map metric indices
        idx_map = {desc.get("key"): desc.get("metricsIndex") for desc in descriptors}
        dist_idx = idx_map.get("sumDistance")
        hr_idx = idx_map.get("directHeartRate")
        speed_idx = idx_map.get("directSpeed")
        # Preference: directDoubleCadence for SPM
        cadence_idx = idx_map.get("directDoubleCadence") or idx_map.get("directRunCadence")
        elev_idx = idx_map.get("directElevation")

        distances, paces, heart_rates, cadences, elevations = [], [], [], [], []
        
        def ms_to_pace_float(ms):
            if not ms or ms <= 0: return None
            p = 1000 / ms / 60
            return p if p <= 15 else None

        for row in metrics:
            try:
                data_list = row.get('metrics', [])
                if not data_list: continue

                d = data_list[dist_idx] if dist_idx is not None else None
                s = data_list[speed_idx] if speed_idx is not None else None
                h = data_list[hr_idx] if hr_idx is not None else None
                c = data_list[cadence_idx] if cadence_idx is not None else None
                e = data_list[elev_idx] if elev_idx is not None else None
                
                if d is None: continue
                
                p = ms_to_pace_float(s)
                # Fix Cadence if only single-foot reported
                if cadence_idx == idx_map.get("directRunCadence") and c is not None and c < 100:
                    c = c * 2

                distances.append(d / 1000.0)
                paces.append(p)
                heart_rates.append(h)
                cadences.append(c)
                elevations.append(e)
            except Exception: continue

        # --- Plotting ---
        font_path = "/data/data/com.termux/files/home/workspace/NotoSansTC-VariableFont_wght.ttf"
        try:
            prop_black = fm.FontProperties(fname=font_path, weight=900)
            prop_bold = fm.FontProperties(fname=font_path, weight=700)
            prop_reg = fm.FontProperties(fname=font_path, weight=400)
        except:
            prop_black = fm.FontProperties(weight='black')
            prop_bold = fm.FontProperties(weight='bold')
            prop_reg = fm.FontProperties()
        
        BG_COLOR, TEXT_COLOR, AXIS_COLOR = "#FAFAF7", "#2B2B2B", "#78716C"
        PACE_COLOR, HR_COLOR, CAD_COLOR = "#2F80ED", "#FF4D4F", "#FFB020"
        ELEV_COLOR, ELEV_TEXT_COLOR = "#D6D3D1", "#57534E"
        
        TITLE_SIZE, LABEL_SIZE, TICK_SIZE, INFO_SIZE = 32, 26, 26, 22

        plt.rcParams['axes.unicode_minus'] = False
        fig, ax_pace = plt.subplots(figsize=(19, 11), dpi=100, facecolor=BG_COLOR)
        ax_pace.set_facecolor(BG_COLOR)
        ax_shared = ax_pace.twinx()
        
        def filter_series(x_data, y_data):
            f_x, f_y = [], []
            for x, y in zip(x_data, y_data):
                if y is not None:
                    f_x.append(x); f_y.append(y)
            return f_x, f_y

        # 1. Pace Plot (Y1)
        p_x, p_y = filter_series(distances, paces)
        if p_y:
            ax_pace.plot(p_x, p_y, color=PACE_COLOR, linewidth=2.5, label='Pace', zorder=10)
            ax_pace.invert_yaxis()
            ax_pace.set_ylabel('配速', color=TEXT_COLOR, fontproperties=prop_black, fontsize=LABEL_SIZE, labelpad=40)
            valid_p = [v for v in p_y if 3 < v < 15]
            if valid_p:
                ax_pace.set_ylim(min(max(valid_p) + 0.5, 10.0), min(valid_p) - 0.5)

            import matplotlib.ticker as ticker
            def pace_formatter(x, pos):
                try:
                    m = int(x); s = int((x - m) * 60)
                    return f"{m}:{s:02d}"
                except: return ""
            ax_pace.yaxis.set_major_formatter(ticker.FuncFormatter(pace_formatter))

        # 2. Shared Metrics (Y2)
        h_x, h_y = filter_series(distances, heart_rates)
        c_x, c_y = filter_series(distances, cadences)
        e_x, e_y = filter_series(distances, elevations)
        
        y2_min = 60
        metrics_vals = (h_y if h_y else []) + (c_y if c_y else [])
        y2_max = max(metrics_vals) + 20 if metrics_vals else 200
        ax_shared.set_ylim(y2_min, y2_max)
        
        # Laps Targets
        if max(distances) > 0:
            current_dist = 0
            for lap in laps:
                l_dist = lap.get("distance", 0) / 1000.0
                p_l, p_h = lap.get("targetPaceLow"), lap.get("targetPaceHigh")
                if p_l and p_h:
                    ax_pace.axhspan(1000/p_l/60, 1000/p_h/60, xmin=current_dist/max(distances), xmax=(current_dist+l_dist)/max(distances), color=PACE_COLOR, alpha=0.1, zorder=1)
                hr_l, hr_h = lap.get("targetHeartRateLow"), lap.get("targetHeartRateHigh")
                if hr_l and hr_h:
                    ax_shared.axhspan(hr_l, hr_h, xmin=current_dist/max(distances), xmax=(current_dist+l_dist)/max(distances), color=HR_COLOR, alpha=0.08, zorder=1)
                current_dist += l_dist

        # Elevation Fill
        if e_y:
            e_min_d, e_max_d = min(e_y), max(e_y)
            e_range_d = e_max_d - e_min_d if e_max_d != e_min_d else 1.0
            t_min, t_max = y2_min, y2_min + 0.25 * (y2_max - y2_min)
            e_norm = [t_min + ((v - e_min_d) / e_range_d) * (t_max - t_min) for v in e_y]
            ax_shared.fill_between(e_x, e_norm, y2_min, color=ELEV_COLOR, alpha=0.5, label='Elevation', zorder=2)
        
        if h_y: ax_shared.plot(h_x, h_y, color=HR_COLOR, linewidth=3, alpha=0.9, label='HR', zorder=5)
        if c_y: ax_shared.plot(c_x, c_y, color=CAD_COLOR, linewidth=2, alpha=0.9, label='Cadence', zorder=4)

        ax_shared.set_ylabel('心率/步頻', color=TEXT_COLOR, fontproperties=prop_black, fontsize=LABEL_SIZE, labelpad=20)

        # X-axis Custom Ticks
        ax_pace.set_xlabel('距離（km）', color=TEXT_COLOR, fontproperties=prop_black, fontsize=LABEL_SIZE, labelpad=15)
        if distances:
            max_dist = max(distances)
            ax_pace.set_xlim(0, max_dist)
            ticks = [float(i) for i in range(0, int(max_dist) + 1, 2)]
            if max_dist > ticks[-1] + 0.1: ticks.append(max_dist)
            else: ticks[-1] = max_dist
            ax_pace.set_xticks(ticks)
            ax_pace.set_xticklabels([str(int(t)) if t == int(t) else f"{t:.3f}" for t in ticks])

        # Formatting Spines & Ticks
        for ax in [ax_pace, ax_shared]:
            for spine in ax.spines.values():
                spine.set_color(AXIS_COLOR); spine.set_linewidth(2)
            ax.tick_params(colors=TEXT_COLOR, length=10, width=2)
            for label in ax.get_xticklabels() + ax.get_yticklabels():
                label.set_fontproperties(prop_bold); label.set_fontsize(TICK_SIZE); label.set_color(TEXT_COLOR)

        # Summary Statistics Label (Top Left)
        def fmt_p(s):
            if not s or s <= 0: return "0:00"
            p = 1000 / s / 60; m = int(p); sec = int((p-m)*60)
            return f"{m}:{sec:02d}"

        summary_ax = ax_pace.inset_axes([0.01, 0.75, 0.4, 0.25], facecolor='none')
        summary_ax.axis('off')
        summary_ax.text(0, 0.8, f"配速 {fmt_p(avg_speed)} / {fmt_p(max_speed)}", color=PACE_COLOR, fontproperties=prop_bold, fontsize=INFO_SIZE)
        summary_ax.text(0, 0.6, f"心率 {int(avg_hr)} / {int(max_hr)} bpm, 消耗 {int(calories)} 大卡", color=HR_COLOR, fontproperties=prop_bold, fontsize=INFO_SIZE)
        summary_ax.text(0, 0.4, f"步頻 {int(avg_cadence)} / {int(max_cadence)} spm, 步數 {int(total_steps)}", color=CAD_COLOR, fontproperties=prop_bold, fontsize=INFO_SIZE)
        summary_ax.text(0, 0.2, f"累計升降 {int(elev_gain)} / {int(elev_loss)} m", color=ELEV_TEXT_COLOR, fontproperties=prop_bold, fontsize=INFO_SIZE)

        # Enhanced Title
        import re
        clean_name = re.sub(r'[^\x00-\x7F\u4e00-\u9fa5\u3000-\u303f\uff00-\uffef]', '', activity_name).strip()
        try:
            dt_obj = datetime.strptime(start_time_local, "%Y-%m-%d %H:%M:%S")
            formatted_time = dt_obj.strftime("%Y-%m-%d %H:%M")
        except: formatted_time = start_time_local
            
        title_str = f"{clean_name} / 負荷 {int(load_val)} / 有氧 {aerobic_te} 無氧 {anaerobic_te} / {formatted_time}"
        fig.suptitle(title_str, color=TEXT_COLOR, fontsize=TITLE_SIZE, fontproperties=prop_black, y=0.97)
        
        # Outer Branding (Avatar + Name)
        if owner_name:
            brand_ax = fig.add_axes([0.01, 0.02, 0.25, 0.07], facecolor='none')
            brand_ax.axis('off')
            if avatar_img:
                av_ax = brand_ax.inset_axes([0, 0, 0.3, 1])
                av_ax.imshow(avatar_img); av_ax.axis('off')
                brand_ax.text(0.32, 0.5, owner_name, color=TEXT_COLOR, fontproperties=prop_bold, fontsize=INFO_SIZE, verticalalignment='center')
            else:
                brand_ax.text(0.05, 0.5, owner_name, color=TEXT_COLOR, fontproperties=prop_bold, fontsize=INFO_SIZE, verticalalignment='center')

        plt.subplots_adjust(top=0.92, bottom=0.15, left=0.08, right=0.92)
        ax_pace.grid(False); ax_shared.grid(False)
        
        plt.savefig(output_path, dpi=100, facecolor=fig.get_facecolor())
        plt.close(fig)
        return output_path
    except Exception as e:
        logger.error(f"Failed to generate activity chart: {e}")
        return None


def get_weekly_chart_url(daily_data: list) -> str:
    """Generate a QuickChart Short URL for the weekly comprehensive report.

    Args:
        daily_data: List of dicts [{'date': '...', 'distance_km': ..., 'hrv': ..., 'runs': [{'distance': ..., 'te': ...}], ...}, ...]

    Returns:
        Short URL string pointing to the chart image.
    """
    def format_date(date_str):
        d = datetime.datetime.strptime(date_str, "%Y-%m-%d")
        weekday_cn = ["一", "二", "三", "四", "五", "六", "日"][d.weekday()]
        return f"{d.month}/{d.day} ({weekday_cn})"

    labels = [format_date(d['date']) for d in daily_data]
    hrv_values = [d.get('hrv', 0) for d in daily_data]
    bb_values = [d.get('body_battery', 0) for d in daily_data]
    load_ratios = [round(d.get('load_ratio', 0) * 100) for d in daily_data]
    total_dist = round(sum(d.get('distance_km', 0) for d in daily_data), 1)

    recovery_color = "rgba(148, 148, 148, 1)"
    base_color = "rgba(101, 217, 232, 1)"
    high_aerobic_color = "rgba(253, 157, 57, 1)"
    anaerobic_color = "rgba(169, 141, 252, 1)"
    lr_color = "rgba(249, 53, 77, 1)"
    bb_color = "rgba(26, 118, 211, 1)"
    hrv_color = "rgba(12, 150, 64, 1)"

    te_categories = [
        {"label": "恢復", "color": recovery_color, "patterns": ["RECOVERY"]},
        {"label": "基礎", "color": base_color, "patterns": ["BASE"]},
        {"label": "高強度", "color": high_aerobic_color, "patterns": [
            "TEMPO", "THRESHOLD", "VO2MAX", "HIGH_AEROBIC"]},
        {"label": "無氧", "color": anaerobic_color, "patterns": ["ANAEROBIC"]},
    ]

    category_series = {cat["label"]: [0.0] *
                       len(daily_data) for cat in te_categories}
    for i, day in enumerate(daily_data):
        runs = day.get("runs", [])
        if not runs and day.get("distance_km", 0) > 0:
            category_series["基礎"][i] = day["distance_km"]
            continue

        for run in runs:
            dist = run.get("distance", 0)
            te = str(run.get("te", "UNKNOWN")).upper()
            for cat in te_categories:
                if any(p in te for p in cat["patterns"]):
                    category_series[cat["label"]][i] = round(
                        category_series[cat["label"]][i] + dist, 2)
                    break

    datasets = []
    # 1. Bar datasets (Order 10 - Bottom layer)
    for cat in te_categories:
        datasets.append({
            "type": "bar",
            "label": cat["label"],
            "data": category_series[cat["label"]],
            "backgroundColor": cat["color"],
            "stack": "stack0",
            "yAxisID": "y1",
            "order": 10,
            "datalabels": {"display": False}
        })

    # 2. Line datasets (Order 5 - Middle layer)
    line_configs = [
        {"label": "負荷比 (%)", "color": lr_color,
         "data": load_ratios, "dash": [5, 5]},
        {"label": "HRV (ms)", "color": hrv_color,
         "data": hrv_values, "dash": [5, 5]},
        {"label": "Body Battery", "color": bb_color,
            "data": bb_values, "dash": [5, 5]}
    ]

    for cfg in line_configs:
        datasets.append({
            "type": "line",
            "label": cfg["label"],
            "data": cfg["data"],
            "borderColor": cfg["color"],
            "pointBackgroundColor": cfg["color"],
            "fill": False,
            "yAxisID": "y2",
            "pointRadius": 3,
            "borderDash": cfg["dash"],
            "order": 5,
            "datalabels": {
                "display": True,
                "color": cfg["color"],
                "align": "top",
                "offset": 2,
                "font": {"size": 10, "weight": "bold"},
                "backgroundColor": "rgba(255, 255, 255, 0.8)",
                "borderRadius": 2,
                "padding": 1
            }
        })

    # 3. Legend Text (Order 1 - Top layer)
    legend_labels = [
        {"text": "--- 負荷比 (%)     ", "color": lr_color,
         "y": 26, "key": "LEG_0"},
        {"text": "--- Body Battery", "color": bb_color, "y": 18, "key": "LEG_1"},
        {"text": "--- HRV (ms)      ", "color": hrv_color,
         "y": 10, "key": "LEG_2"}
    ]

    for i, leg in enumerate(legend_labels):
        datasets.append({
            "type": "line",
            "label": f"_text_{i}",
            "data": [None] * (len(daily_data) - 1) + [leg["y"]],
            "yAxisID": "y2",
            "fill": False,
            "showLine": False,
            "pointRadius": 0,
            "order": 1,  # Lowest order = Topmost layer
            "datalabels": {
                "display": True,
                "align": "right",
                "anchor": "end",
                "offset": -65,  # Adjusting slightly for better centering
                "formatter": leg["key"],
                "color": leg["color"],
                "backgroundColor": "rgba(255, 255, 255, 0.8)",
                "font": {"size": 10, "weight": "bold"}
            }
        })

    chart_config = {
        "type": "bar",
        "data": {"labels": labels, "datasets": datasets},
        "options": {
            "title": {"display": True, "text": f"週報: 訓練與恢復趨勢 (總計: {total_dist} km)", "fontSize": 16},
            "legend": {
                "position": "bottom",
                "labels": {
                    "fontSize": 10,
                    "filter": "FILTER_PLACEHOLDER"
                }
            },
            "scales": {
                "xAxes": [{"stacked": True}],
                "yAxes": [
                    {"id": "y1", "type": "linear", "position": "left", "stacked": True, "ticks": {
                        "beginAtZero": True}, "scaleLabel": {"display": True, "labelString": "里程 (km)"}},
                    {"id": "y2", "type": "linear", "position": "right", "stacked": False, "ticks": {"beginAtZero": True, "max": 120},
                        "scaleLabel": {"display": True, "labelString": "狀態指標"}, "gridLines": {"drawOnChartArea": False}}
                ]
            },
            "plugins": {
                # "datalabels": {"display": False}
            }
        }
    }

    # Stringify and inject raw functions
    config_str = json.dumps(chart_config)
    config_str = config_str.replace(
        '"FILTER_PLACEHOLDER"', "function(item) { return ['恢復', '基礎', '高強度', '無氧'].includes(item.text); }")
    for leg in legend_labels:
        config_str = config_str.replace(
            f'"{leg["key"]}"', f"function() {{ return '{leg['text']}'; }}")

    try:
        response = requests.post(
            "https://quickchart.io/chart/create",
            json={
                "chart": config_str,
                "backgroundColor": "#F0F0F0",
                "width": 600,
                "height": 400,
                "format": "png"
            },
            timeout=15
        )
        if response.status_code == 200:
            return response.json().get("url")
        else:
            logger.error(
                f"QuickChart API error: {response.status_code} - {response.text}")
    except Exception as e:
        logger.error(f"Failed to call QuickChart API: {e}")

    # Fallback to long URL if short URL fails
    encoded_config = urllib.parse.quote(config_str)
    return f"https://quickchart.io/chart?c={encoded_config}&backgroundColor=%23F0F0F0&width=600&height=400&format=png"
