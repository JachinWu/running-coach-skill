"""character_card.py — Compose the high-fidelity Runner Character Card."""

import os
import logging
import tempfile
import shutil
import math
import re
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple

from PIL import Image, ImageDraw, ImageFont, ImageEnhance, ImageOps, ImageFilter

try:
    # Package-style imports
    from . import athlete_profile
    from . import image_generator
    from . import context_engine
    from . import skill_tracker
    from . import garmin
    from . import gear_manager
except (ImportError, ValueError):
    # Standalone execution imports
    import athlete_profile
    import image_generator
    import context_engine
    import skill_tracker
    import garmin
    import gear_manager

logger = logging.getLogger(__name__)

# Paths
SCRIPTS_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPTS_DIR.parent
WORKSPACE_ROOT = SKILL_DIR.parents[2]
FONT_DIR = WORKSPACE_ROOT / "fonts"
ASSETS_DIR = SKILL_DIR / "assets"
ICON_DIR = ASSETS_DIR / "icons"
TRAIT_DIR = ASSETS_DIR / "traits"

# =========================
# Fonts
# =========================
try:
    oblique_font = ImageFont.truetype(str(FONT_DIR / 'DejaVuSans-Oblique.ttf'), 32)
    genre_font = ImageFont.truetype(str(FONT_DIR / 'NotoSansTC-Black.ttf'), 64)
    rarity_font = ImageFont.truetype(str(FONT_DIR / 'DejaVuSansMono-BoldOblique.ttf'), 120)
    sub_font = ImageFont.truetype(str(FONT_DIR / 'DejaVuSans.ttf'), 32)
    activity_title_font = ImageFont.truetype(str(FONT_DIR / 'NotoSansTC-Black.ttf'), 22)
    info_title_font = ImageFont.truetype(str(FONT_DIR / 'DejaVuSans-Oblique.ttf'), 22)
    info_data_font = ImageFont.truetype(str(FONT_DIR / 'NotoSansTC-Regular.ttf'), 22)
    slogan_font = ImageFont.truetype(str(FONT_DIR / 'NotoSansTC-Light.ttf'), 18)
    footer_font = ImageFont.truetype(str(FONT_DIR / 'DejaVuSans-Oblique.ttf'), 18)
    number_font = ImageFont.truetype(str(FONT_DIR / 'DejaVuSans-Bold.ttf'), 80)
    emoji_font = ImageFont.truetype(str(FONT_DIR / 'NotoColorEmoji-Regular.ttf'), 22)
except:
    oblique_font = ImageFont.load_default()
    genre_font = ImageFont.load_default()
    rarity_font = ImageFont.load_default()
    sub_font = ImageFont.load_default()
    activity_title_font = ImageFont.load_default()
    info_title_font = ImageFont.load_default()
    info_data_font = ImageFont.load_default()
    slogan_font = ImageFont.load_default()
    footer_font = ImageFont.load_default()
    number_font = ImageFont.load_default()
    emoji_font = ImageFont.load_default()

# =========================
# Bottom Info Panels
# =========================
def info_panel(canvas, x, y, w, h, title, lines, title_font=sub_font, data_font=info_data_font, line_spacing=42):
    panel = Image.new('RGBA', canvas.size, (0, 0, 0, 0))
    pd = ImageDraw.Draw(panel)

    pd.rounded_rectangle(
        [x, y, x+w, y+h],
        radius=14,
        fill=(0, 0, 0, 128),
        outline=(255, 255, 255, 80),
        width=2
    )

    canvas_alpha = Image.alpha_composite(canvas, panel)
    d = ImageDraw.Draw(canvas_alpha)

    d.text((x+20, y+18), title, fill='white', font=title_font)

    yy = y + 65
    for line in lines:
        d.text((x+20, yy), line, fill=(220, 220, 220), font=data_font)
        yy += line_spacing

    return canvas_alpha

def draw_text_with_shadow(draw, position, text, font, fill="white", shadow=(0, 0, 0, 220), offset=(1, 1), anchor=None, **kwargs):
    """Draws text with a slight shadow for better readability."""
    x, y = position
    draw.text((x + offset[0], y + offset[1]), text, font=font, fill=shadow, anchor=anchor, **kwargs)
    draw.text(position, text, font=font, fill=fill, anchor=anchor, **kwargs)

def remove_emojis(text: str) -> str:
    """Removes emojis and special symbols from text for a cleaner look."""
    return re.sub(r'[^\w\s\-\(\)\.,:：]', '', text).strip()

def get_level_color(level: int) -> str:
    """Return color hex based on level tier."""
    if level >= 51: return "#E5E4E2" # Platinum
    if level >= 26: return "#FFD700" # Gold
    if level >= 11: return "#C0C0C0" # Silver
    return "#CD7F32" # Bronze

def draw_icon(canvas, x, y, size, icon_name, category="icons", fallback_emoji=""):
    """Draws a PNG icon or a fallback emoji."""
    icon_path = (TRAIT_DIR if category == "traits" else ICON_DIR) / f"{icon_name}.png"

    if icon_path.exists():
        try:
            with Image.open(icon_path) as icon:
                icon = icon.convert("RGBA")
                icon.thumbnail((size, size), Image.Resampling.LANCZOS)
                canvas.paste(icon, (x, y), icon)
                return True
        except Exception as e:
            logger.warning(f"Failed to load icon {icon_name}: {e}")

    # Fallback to emoji
    if fallback_emoji:
        draw = ImageDraw.Draw(canvas)
        draw.text((x, y), fallback_emoji, font=emoji_font)
        return True
    return False

def calculate_dynamic_traits(daily_list: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    """Analyze recent activities to determine runner traits."""
    traits = []
    if not daily_list:
        return traits

    # 1. Morning vs Night Runner
    morning_count = 0
    night_count = 0
    total_runs = 0

    for day in daily_list:
        start_time = day.get("start_time") # Expecting "HH:MM:SS" or similar
        if not start_time: continue

        total_runs += 1
        hour = int(start_time.split(":")[0])
        if hour < 9: morning_count += 1
        elif hour >= 19: night_count += 1

    if total_runs > 0:
        if morning_count / total_runs > 0.6:
            traits.append({"name": "晨跑愛好者", "icon": "morning", "emoji": "🌅"})
        elif night_count / total_runs > 0.6:
            traits.append({"name": "夜跑武士", "icon": "night", "emoji": "🌙"})

    # 2. Terrain Preference
    total_elev = sum(d.get("elevation_gain", 0) for d in daily_list)
    total_dist = sum(d.get("distance_km", 0) for d in daily_list)

    if total_dist > 0:
        elev_ratio = total_elev / total_dist
        if elev_ratio > 15: # 15m per km
            traits.append({"name": "山地靈羊", "icon": "mountain", "emoji": "🏔️"})
        elif elev_ratio < 3:
            traits.append({"name": "平地飛人", "icon": "flat", "emoji": "🏃‍♂️"})

    # 3. Consistency
    active_days = sum(1 for d in daily_list if d.get("distance_km", 0) > 0)
    if active_days >= 20: # Over 28 days
        traits.append({"name": "紀律達人", "icon": "discipline", "emoji": "⚖️"})

    return traits[:3] # Max 3 traits

def get_rarity(vdot: float) -> str:
    """Determine card rarity based on VDOT."""
    if vdot >= 55: return "SSR"
    if vdot >= 45: return "SR"
    if vdot >= 35: return "S"
    return "N"

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
    consistency = min(
        100, (min(100, (frequency_days / 6.0) * 50) + (consistency_score / 2.0)))

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

def draw_radar(draw, center, radius, labels, values,
               line_color=(80, 170, 255),
               fill_color=(80, 170, 255, 80)):

    cx, cy = center
    count = len(labels)

    # Background circle
    draw.rounded_rectangle(
        [cx - radius - 20, cy - radius - 20, cx + radius + 20, cy + radius + 20],
        radius=radius + 20,
        fill=(0, 0, 0, 64)
    )

    # Grid
    for r in range(1, 6):
        rr = radius * r / 5
        pts = []
        for i in range(count):
            angle = math.pi * 2 * i / count - math.pi / 2
            x = cx + rr * math.cos(angle)
            y = cy + rr * math.sin(angle)
            pts.append((x, y))
        draw.polygon(pts, outline=(255, 255, 255, 80))

    # Axis
    for i, label in enumerate(labels):
        angle = math.pi * 2 * i / count - math.pi / 2
        x = cx + radius * math.cos(angle)
        y = cy + radius * math.sin(angle)

        draw.line((cx, cy, x, y), fill=(255, 255, 255, 100), width=1)
        draw.text((x-20, y-10), label, fill='white', font=info_data_font)

    # Data polygon
    data_pts = []
    for i, value in enumerate(values):
        angle = math.pi * 2 * i / count - math.pi / 2
        rr = radius * value / 100
        x = cx + rr * math.cos(angle)
        y = cy + rr * math.sin(angle)
        data_pts.append((x, y))

    draw.polygon(data_pts, fill=fill_color, outline=line_color, width=4)

    for pt in data_pts:
        draw.ellipse([
            pt[0]-6, pt[1]-6,
            pt[0]+6, pt[1]+6
        ], fill='white')

def generate_character_card(api, activity: Dict[str, Any], output_path: str = "tmp/character_card.png") -> tuple[Optional[str], Optional[str]]:
    """
    Generates the complete Runner Character Card with Original Background and High-Contrast Data Panels.
    """
    try:
        # 1. Gather Data
        profile = athlete_profile.load_profile()
        vdot = profile["vdot_history"][-1]["vdot_est"]
        rarity = get_rarity(vdot)

        daily_list = garmin.get_comprehensive_daily_stats(api, 28)
        total_dist = sum(d.get("distance_km", 0) for d in daily_list)
        avg_weekly_dist = total_dist / 4.0
        activities_count = sum(1 for d in daily_list if d.get("distance_km", 0) > 0)
        curr_elev = activity.get("elevationGain", 0)
        hrv_values = [d.get("hrv", 0) for d in daily_list if d.get("hrv", 0) > 0]
        avg_hrv = sum(hrv_values) / len(hrv_values) if hrv_values else 0
        hrv_stability = min(1.0, avg_hrv / 80.0) if avg_hrv > 0 else 0.5

        scores = calculate_radar_scores(
            weekly_dist_km=avg_weekly_dist,
            vdot=vdot,
            frequency_days=int(activities_count / 4.0 * 7),
            total_elev_gain=curr_elev * 4,
            hrv_stability=hrv_stability
        )

        # New: Dynamic Traits
        traits_list = calculate_dynamic_traits(daily_list)
        trait_labels = [f"• {t['name']}" for t in traits_list]
        while len(trait_labels) < 3:
            trait_labels.append("• 探索中...")

        # New: Gear Info
        # 1. Try metadata (from manual selection in Telegram)
        # 2. Try database (for historical or re-generated cards)
        shoe_nickname = activity.get("metadata", {}).get("shoe_nickname")
        if not shoe_nickname:
            shoe_nickname = gear_manager.get_shoe_for_activity(activity.get("activityId"))

        shoe_nickname = shoe_nickname or "預設跑鞋"
        gear_stats = gear_manager.get_shoe_stats(shoe_nickname)
        display_name = gear_stats.get("model", shoe_nickname)
        gear_info = [
            f"   {display_name} ({int(gear_stats['total_km'])}km | EI:{gear_stats['avg_efficiency']*1000:.1f}pt)"
        ]

        genre = determine_genre(scores)
        genre_zh = genre.split("｜")[0]
        genre_en = genre.split("｜")[1] if "｜" in genre else ""
        genre_des = {
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
        slogan = genre_des.get(genre, "跑步不只是運動，而是一種生活態度。")

        # Background
        temp_dir = tempfile.mkdtemp()
        bg_raw_path = os.path.join(temp_dir, "bg_raw.jpg")

        card_type = profile.get("character_card_type", "MaleAnime")
        image_url = image_generator.generate_genre_background(genre, bg_raw_path, card_type=card_type)

        card_w, card_h = 1200, 1600

        with Image.open(bg_raw_path) as img:
            # Correct Orientation
            img = ImageOps.exif_transpose(img)
            # Force Fit to 1200x1600
            bg_processed = ImageOps.fit(img.convert("RGBA"), (card_w, card_h), method=Image.Resampling.LANCZOS, centering=(0.5, 0.5))
            canvas = bg_processed.copy()

        # Subtle gradient only at extreme top for title readability
        top_gradient = Image.new('RGBA', (card_w, 400), (0, 0, 0, 0))
        tg_draw = ImageDraw.Draw(top_gradient)
        for y in range(0, 400):
            alpha = int((1 - y / 400) * 160)
            tg_draw.line([(0, y), (card_w, y)], fill=(0, 0, 0, alpha))
        canvas.paste(top_gradient, (0, 0), top_gradient)

        # 3. Draw Section
        draw = ImageDraw.Draw(canvas)

        # Card Border
        padding = 24
        border_color = (255, 255, 255, 180)

        draw.rounded_rectangle(
            [padding, padding, card_w - padding, card_h - padding],
            radius=20,
            outline=border_color,
            width=3
        )

        # Titles
        draw.text((60, 50), 'RUNNER CARD', fill=(200, 255, 200), font=oblique_font)
        draw_text_with_shadow(draw, (60, 90), genre_zh, genre_font)
        draw_text_with_shadow(draw, (60, 180), genre_en.upper(), sub_font, fill=(160, 255, 120))
        draw_text_with_shadow(draw, (60, 210), slogan, slogan_font, fill="#DDDDDD")

        rarity = get_rarity(vdot)
        rarity_colors = {"N": "#AAAAAA", "S": "#2F80ED", "SR": "#A98DFC", "SSR": "#FFD700"}
        draw_text_with_shadow(draw, (card_w - 70, 70), rarity, rarity_font, fill=rarity_colors.get(rarity, (220, 255, 50)), anchor="ra")

        # 4. Middle Section Radar Chart
        radar_layer = Image.new('RGBA', canvas.size, (0, 0, 0, 0))
        radar_draw = ImageDraw.Draw(radar_layer)

        draw_radar(
            radar_draw,
            center=(270, 950),
            radius=180,
            labels=list(scores.keys()),
            values=list(scores.values())
        )

        radar_layer = radar_layer.filter(ImageFilter.GaussianBlur(0.5))
        canvas = Image.alpha_composite(canvas, radar_layer)

        # VDOT
        draw = ImageDraw.Draw(canvas)
        vdot_val = f"{vdot:.1f}" if vdot > 0 else "🔒"
        draw_text_with_shadow(draw, (card_w - 70, 760), vdot_val, font=number_font, fill=(220, 255, 50), anchor="ra")
        draw_text_with_shadow(draw, (card_w - 70, 850), "VDOT", font=sub_font, fill="white", anchor="ra")

        recovery = garmin.get_hrv_and_recovery(api)
        hrv = recovery.get("hrv", {}).get("last_night", "🔒") if recovery.get("hrv") else "🔒"
        bb = recovery.get("body_battery", {}).get("highest", "🔒") if recovery.get("body_battery") else "🔒"
        if len(daily_list) >= 2:
            prev_stats = daily_list[-2]
            tsb = round(prev_stats.get("chronic_load", 0) - prev_stats.get("training_load", 0), 1) if prev_stats.get("chronic_load") is not None else "🔒"
        else:
            tsb = "🔒"

        draw_text_with_shadow(draw, (card_w - 70, 910), f"HRV: {hrv} ms", font=sub_font, anchor="ra")
        draw_text_with_shadow(draw, (card_w - 70, 955), f"Body Battery: {bb}%", font=sub_font, anchor="ra")
        draw_text_with_shadow(draw, (card_w - 70, 1000), f"TSB: {tsb}", font=sub_font, anchor="ra")

        # 5. Bottom Row
        act_name_raw = activity.get("activityName", "跑步活動")
        act_name = remove_emojis(act_name_raw) # Remove emojis

        act_time_raw = activity.get("startTimeLocal", "")
        if len(act_time_raw) >= 16:
            act_time_str = act_time_raw[:16]
        else:
            import datetime
            act_time_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

        dist_km = round(activity.get("distance", 0) / 1000, 2)
        dur_min = round(activity.get("duration", 0) / 60, 1)
        avg_speed = activity.get("averageSpeed", 0)
        avg_pace = f"{int(16.6667 / avg_speed)}:{(16.6667 / avg_speed % 1 * 60):02.0f}" if avg_speed > 0 else "N/A"
        ae_te = f"{activity.get('aerobicTrainingEffect', 0.0):.1f}"
        an_te = f"{activity.get('anaerobicTrainingEffect', 0.0):.1f}"

        canvas = info_panel(canvas,
            60, 1180, 230, 300,
            'TRAITS',
            trait_labels
        )

        # Draw Trait Icons
        tx, ty = 80, 1245
        for t in traits_list:
            draw_icon(canvas, tx, ty, 32, t['icon'], category="traits", fallback_emoji=t['emoji'])
            ty += 42

        canvas = info_panel(canvas,
            325, 1180, 460, 300,
            act_name,
            [
                f"日期: {act_time_str}",
                f"距離: {dist_km} km",
                f"時間: {dur_min} min",
                f"配速: {avg_pace}/km",
                f"HR: {activity.get('averageHR', '🔒')} bpm",
                f"TE: {ae_te} 有氧 / {an_te} 無氧",
            ] + gear_info,
            title_font=activity_title_font,
            line_spacing=30
        )

        # Draw Shoe Icon
        draw_icon(canvas, 345, 1455, 25, "shoe", fallback_emoji="👟")

        skill_x, skill_y = 820, 1180
        canvas = info_panel(canvas,
            skill_x, skill_y, 320, 300,
            'SKILL',
            []
        )

        draw = ImageDraw.Draw(canvas)
        skills_info = skill_tracker.get_skill_levels(api)
        skill_icons_map = skill_tracker.get_skill_icons()

        sx, sy = skill_x + 20, skill_y + 55
        for name, info in list(skills_info.items()):
            level = info["level"]
            progress = info["progress_pct"]
            level_color = get_level_color(level)
            
            # Draw Icon
            icon_slug = name.lower().replace(" ", "_") # Simplified slug
            emoji = skill_icons_map.get(name, "⭐")
            draw_icon(canvas, sx, sy, 30, icon_slug, fallback_emoji=emoji)
            
            draw.text((sx + 50, sy), f"{name} Lv.{level}", font=info_data_font, fill='white')
            
            # Progress Bar
            bar_w, bar_h = 280, 41
            draw.rounded_rectangle([sx, sy + 35, sx + bar_w, sy + bar_h], radius=14, fill=(255, 255, 255, 60))
            draw.rounded_rectangle([sx, sy + 35, sx + int(progress / 100 * bar_w), sy + bar_h], radius=14, fill=level_color)
            sy += 45

        # Footer
        draw = ImageDraw.Draw(canvas)
        draw.text((60, 1520), 'RUN TO YOUR FREEDOM.', fill=(180, 255, 180), font=footer_font)
        draw.text((card_w - 80, 1520), 'EVERY STEP COUNTS.', fill='white', font=footer_font, anchor="ra")
        
        # 6. Final Save
        canvas = canvas.convert("RGB")
        canvas.save(output_path, "PNG")
        shutil.rmtree(temp_dir, ignore_errors=True)
        return output_path, image_url

    except Exception as e:
        logger.error(f"Failed to generate character card: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return None, None
