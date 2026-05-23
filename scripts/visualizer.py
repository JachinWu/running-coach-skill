import json
import requests
import logging
import datetime
import urllib.parse
import os
from pathlib import Path
from typing import Dict, Any, Optional
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm

logger = logging.getLogger(__name__)


import numpy as np

from PIL import Image, ImageEnhance, ImageDraw

def generate_radar_chart(scores: Dict[str, float], genre: str, output_path: str = "radar_chart.png", bg_image_path: Optional[str] = None) -> Optional[str]:
    """Generates a professional radar chart for runner combat metrics with optional background."""
    try:
        labels = list(scores.keys())
        values = list(scores.values())
        num_vars = len(labels)

        angles = np.linspace(0, 2 * np.pi, num_vars, endpoint=False).tolist()
        values += values[:1]
        angles += angles[:1]
        labels += labels[:1]

        font_path = Path(__file__).resolve().parents[4] / "NotoSansTC-VariableFont_wght.ttf"
        try:
            prop_bold = fm.FontProperties(fname=font_path, weight=700)
            prop_black = fm.FontProperties(fname=font_path, weight=900)
        except:
            prop_bold = fm.FontProperties(weight='bold')
            prop_black = fm.FontProperties(weight='black')

        # Colors for the chart - adjust for visibility if bg is present
        BG_COLOR = "#FAFAF7" if not bg_image_path else "none"
        PRIMARY_COLOR = "#2F80ED"
        AXIS_COLOR = "#78716C" if not bg_image_path else "#FFFFFF"
        TEXT_COLOR = "#2B2B2B" if not bg_image_path else "#FFFFFF"

        fig, ax = plt.subplots(figsize=(10, 10), subplot_kw=dict(polar=True), dpi=100)
        fig.set_facecolor(BG_COLOR)
        ax.set_facecolor(BG_COLOR)

        plt.xticks(angles[:-1], labels[:-1], color=TEXT_COLOR, fontproperties=prop_bold, fontsize=20)
        ax.set_rscale('linear')
        plt.yticks([20, 40, 60, 80, 100], ["20", "40", "60", "80", "100"], color=AXIS_COLOR, size=12)
        plt.ylim(0, 100)

        ax.plot(angles, values, color=PRIMARY_COLOR, linewidth=4, linestyle='solid', zorder=10)
        ax.fill(angles, values, color=PRIMARY_COLOR, alpha=0.35, zorder=5)

        plt.title(f"當前流派：{genre}", fontproperties=prop_black, size=28, color=TEXT_COLOR, y=1.1)

        for angle, val, label in zip(angles[:-1], values[:-1], labels[:-1]):
            ax.text(angle, val + 10, f"{int(val)}", ha='center', va='center', fontproperties=prop_bold, fontsize=18, color=PRIMARY_COLOR)

        ax.spines['polar'].set_color(AXIS_COLOR)
        ax.spines['polar'].set_linewidth(2)
        ax.grid(color=AXIS_COLOR, linestyle='--', alpha=0.6)

        plt.tight_layout()
        
        # Save the radar part
        # Use a more robust temporary path
        import tempfile
        fd, temp_chart_path = tempfile.mkstemp(suffix=".png", prefix="radar_only_")
        os.close(fd)
        
        plt.savefig(temp_chart_path, dpi=100, transparent=True)
        plt.close(fig)

        # Handle Background Blending with Pillow
        if bg_image_path and os.path.exists(bg_image_path):
            bg = Image.open(bg_image_path).convert("RGBA")
            bg = bg.resize((1000, 1000), Image.Resampling.LANCZOS)
            
            # 1. Darken Background for readability
            enhancer = ImageEnhance.Brightness(bg)
            bg = enhancer.enhance(0.4) # 40% brightness
            
            # 2. Paste Radar Chart
            radar = Image.open(temp_chart_path).convert("RGBA")
            bg.paste(radar, (0, 0), radar)
            
            bg.save(output_path)
            if os.path.exists(temp_chart_path):
                os.remove(temp_chart_path)
        else:
            # Re-generate with normal background if no bg provided
            if os.path.exists(temp_chart_path):
                img = Image.open(temp_chart_path).convert("RGBA")
                # Add white background
                white_bg = Image.new("RGBA", img.size, "#FAFAF7")
                combined = Image.alpha_composite(white_bg, img)
                combined.save(output_path)
                os.remove(temp_chart_path)
            else:
                return None
                
        return output_path
    except Exception as e:
        logger.error(f"Failed to generate radar chart: {e}")
        return None


def generate_activity_chart(api, activity: Dict[str, Any], output_path: str = "activity_chart.png", workout_detail: Dict[str, Any] = None) -> Optional[str]:
    """Generates a highly customized Matplotlib chart for a single activity.
    
    Returns the path to the generated image, or None if failed.
    """
    try:
        activity_id = activity["activityId"]
        activity_name = activity.get("activityName", "跑步活動")
        # ... (rest of the code remains similar until Laps Targets)
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
        font_path = Path(__file__).resolve().parents[4] / "NotoSansTC-VariableFont_wght.ttf"
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
            ax_pace.set_ylabel('配速', color=TEXT_COLOR, fontproperties=prop_black, fontsize=LABEL_SIZE, labelpad=0)
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
        
        # Laps/Workout Targets Alignment
        if max(distances) > 0:
            flat_steps = []
            if workout_detail:
                try:
                    from . import garmin
                except ImportError:
                    import garmin
                flat_steps = garmin.flatten_workout_steps(workout_detail)

            current_dist = 0
            # Use the larger of metric distance or sum of laps to avoid clipping
            total_laps_dist = sum(lap.get("distance", 0) for lap in laps) / 1000.0
            max_total_dist = max(max(distances), total_laps_dist)
            
            if flat_steps:
                step_idx = 0
                step_accum_dist = 0
                step_accum_time = 0
                
                for lap in laps:
                    l_dist = lap.get("distance", 0) / 1000.0
                    l_time = lap.get("duration", 0) # Garmin lap duration is usually in seconds
                    
                    if step_idx >= len(flat_steps):
                        # Use lap's own targets if available
                        p_l, p_h = lap.get("targetPaceLow"), lap.get("targetPaceHigh")
                        hr_l, hr_h = lap.get("targetHeartRateLow"), lap.get("targetHeartRateHigh")
                    else:
                        step = flat_steps[step_idx]
                        t_type = step.get("targetType", {}).get("workoutTargetTypeKey")
                        v1 = step.get("targetValueOne")
                        v2 = step.get("targetValueTwo")
                        
                        p_l, p_h = None, None
                        hr_l, hr_h = None, None
                        if t_type == "pace.zone" and v1 and v2:
                            p_l, p_h = min(v1, v2), max(v1, v2)
                        elif t_type == "heart.rate.zone" and v1 and v2:
                            hr_l, hr_h = min(v1, v2), max(v1, v2)
                            
                        # Update progress in current step
                        step_accum_dist += l_dist
                        step_accum_time += l_time
                        
                        # Determine if we move to next step
                        cond = step.get("endCondition", {})
                        c_type = cond.get("conditionTypeKey")
                        c_val = step.get("endConditionValue", 0)
                        
                        move_next = False
                        if c_type == "time":
                            if step_accum_time >= c_val - 2: move_next = True
                        elif c_type == "distance":
                            if step_accum_dist >= (c_val / 1000.0) - 0.01: move_next = True
                        else:
                            move_next = True # Triggered by lap button or other
                            
                        if move_next:
                            step_idx += 1
                            step_accum_dist = 0
                            step_accum_time = 0

                    # Plot this lap
                    if l_dist > 0:
                        x_start = current_dist / max_total_dist
                        x_end = (current_dist + l_dist) / max_total_dist
                        if p_l and p_h and p_l > 0 and p_h > 0:
                            ax_pace.axhspan(1000/p_l/60, 1000/p_h/60, xmin=x_start, xmax=x_end, color=PACE_COLOR, alpha=0.1, zorder=1)
                        if hr_l and hr_h and hr_l > 0 and hr_h > 0:
                            ax_shared.axhspan(hr_l, hr_h, xmin=x_start, xmax=x_end, color=HR_COLOR, alpha=0.08, zorder=1)
                    
                    current_dist += l_dist
            else:
                # Fallback to Laps if no workout detail matched
                for lap in laps:
                    l_dist = lap.get("distance", 0) / 1000.0
                    p_l, p_h = lap.get("targetPaceLow"), lap.get("targetPaceHigh")
                    hr_l, hr_h = lap.get("targetHeartRateLow"), lap.get("targetHeartRateHigh")
                    
                    if l_dist > 0:
                        x_start = current_dist / max_total_dist
                        x_end = (current_dist + l_dist) / max_total_dist
                        if p_l and p_h and p_l > 0 and p_h > 0:
                            ax_pace.axhspan(1000/p_l/60, 1000/p_h/60, xmin=x_start, xmax=x_end, color=PACE_COLOR, alpha=0.1, zorder=1)
                        if hr_l and hr_h and hr_l > 0 and hr_h > 0:
                            ax_shared.axhspan(hr_l, hr_h, xmin=x_start, xmax=x_end, color=HR_COLOR, alpha=0.08, zorder=1)
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
            
        title_str = f"{clean_name} / 負荷 {int(load_val)} / 有氧 {aerobic_te:.1f} 無氧 {anaerobic_te:.1f} / {formatted_time}"
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


def get_weekly_chart_url(daily_data: list, title_prefix: str = "週報") -> str:
    """Generate a QuickChart Short URL for the weekly comprehensive report.

    Args:
        daily_data: List of dicts [{'date': '...', 'distance_km': ..., 'hrv': ..., 'runs': [{'distance': ..., 'te': ...}], ...}, ...]
        title_prefix: Optional prefix for the chart title (default: "週報").

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

    title_text = f"{title_prefix}: " if title_prefix else ""
    full_title = f"{title_text}訓練與恢復趨勢 (總計: {total_dist} km)"

    chart_config = {
        "type": "bar",
        "data": {"labels": labels, "datasets": datasets},
        "options": {
            "title": {"display": True, "text": full_title, "fontSize": 16},
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


def generate_qoq_chart(quarterly_data: Dict[int, Dict[int, Dict[str, float]]], output_path: str = "tmp/qoq_chart.png") -> Optional[str]:
    """Generate a clustered-stacked bar chart for Year-over-Year Quarterly comparison (QoQ).
    
    Args:
        quarterly_data: {year: {q_num: {cat: distance}}}
        output_path: Path to save the image.
        
    Returns:
        The output path string if successful, else None.
    """
    try:
        import matplotlib.pyplot as plt
        import matplotlib.font_manager as fm
        import numpy as np
        
        # 1. Setup Font with specific sizes
        font_path = Path(__file__).resolve().parents[4] / "NotoSansTC-VariableFont_wght.ttf"
        
        def get_prop(size, weight='normal'):
            if font_path.exists():
                return fm.FontProperties(fname=str(font_path), size=size, weight=weight)
            else:
                return fm.FontProperties(size=size, weight=weight)

        prop_title = get_prop(32, weight='bold')
        prop_axes = get_prop(26)
        prop_ticks = get_prop(26)
        prop_bar = get_prop(22)
        prop_legend = get_prop(26)

        # 2. Colors and Data Constants
        TE_COLORS = {
            "恢復": "#949494",
            "基礎": "#65D9E8",
            "高強度": "#FD9D39",
            "無氧": "#A98DFC"
        }
        TE_ORDER = ["恢復", "基礎", "高強度", "無氧"]
        
        years = sorted(quarterly_data.keys())
        if not years:
            return None
            
        # We want to show at most last 3 years
        years = years[-3:]
        n_years = len(years)
        
        # Alpha values based on relative year index
        # If n_years=3: 0 (3 years ago) -> 0.3, 1 (last year) -> 0.6, 2 (this year) -> 1.0
        # If n_years=1: 0 (this year) -> 1.0
        alphas = [0.3, 0.6, 1.0]
        if n_years == 2:
            alphas = [0.6, 1.0]
        elif n_years == 1:
            alphas = [1.0]
            
        quarters = ["Q1", "Q2", "Q3", "Q4"]
        n_qs = len(quarters)
        
        # 3. Plotting Setup
        fig, ax = plt.subplots(figsize=(18, 12), dpi=100)
        fig.set_facecolor("#FAFAF7")
        ax.set_facecolor("#FAFAF7")
        
        width = 0.22 
        x = np.arange(n_qs)
        offsets = np.linspace(-width, width, n_years) if n_years > 1 else [0]
        
        # 4. Draw Bars
        for i, year in enumerate(years):
            bottoms = np.zeros(n_qs)
            alpha = alphas[i]
            
            for cat in TE_ORDER:
                values = []
                for q in range(1, 5):
                    val = quarterly_data.get(year, {}).get(q, {}).get(cat, 0.0)
                    values.append(val)
                
                ax.bar(x + offsets[i], values, width, bottom=bottoms, 
                       color=TE_COLORS[cat], alpha=alpha, edgecolor='white', linewidth=0.5)
                
                bottoms += np.array(values)
            
            # Add year labels above bars
            for q_idx, total in enumerate(bottoms):
                if total > 0:
                    ax.text(x[q_idx] + offsets[i], total + 5, f"{year}", 
                            ha='center', va='bottom', fontproperties=prop_bar, color="#57534E")

        # 5. Formatting
        ax.set_xticks(x)
        ax.set_xticklabels(quarters, fontproperties=prop_ticks)
        ax.set_ylabel("累積里程 (km)", fontproperties=prop_axes)
        ax.tick_params(axis='both', which='major', labelsize=26)
        
        # Ensure tick labels use the font
        for label in ax.get_xticklabels():
            label.set_fontproperties(prop_ticks)
        for label in ax.get_yticklabels():
            label.set_fontproperties(prop_ticks)
            
        ax.set_title("年度季度趨勢對比 (QoQ Performance Analysis)", fontproperties=prop_title, pad=40)
        
        # Category Legend
        cat_handles = [plt.Rectangle((0,0),1,1, color=TE_COLORS[cat]) for cat in TE_ORDER]
        cat_legend = ax.legend(cat_handles, TE_ORDER, loc='upper left', bbox_to_anchor=(1, 1), 
                               title="訓練效果 (TE)", prop=prop_legend)
        plt.setp(cat_legend.get_title(), fontproperties=prop_legend)
        
        ax.grid(axis='y', linestyle='--', alpha=0.3, color="#D6D3D1")
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        
        plt.tight_layout()
        plt.savefig(output_path, dpi=150)
        plt.close()
        return output_path
    except Exception as e:
        logger.error(f"Failed to generate QoQ chart: {e}")
        return None
