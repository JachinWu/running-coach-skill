import json
import requests
import logging
import datetime
import urllib.parse

logger = logging.getLogger(__name__)


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
