#!/usr/bin/env python3
"""image_generator.py — Dynamically generate or fetch thematic backgrounds with de-duplication and auto-curation."""
import os
import logging
import random
import requests
import json
import subprocess
import sys
from pathlib import Path
from PIL import Image, ImageDraw
from typing import Optional

logger = logging.getLogger(__name__)

# Paths
WORKSPACE_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
SKILLS_PARENT_DIR = Path(__file__).resolve().parent.parent.parent.parent
COACH_DATA_DIR = SKILLS_PARENT_DIR / "skills" / "running-coach" / "data"
KEYWORDS_JSON = COACH_DATA_DIR / "archetype_keywords.json"
SCRAPER_SCRIPT = SKILLS_PARENT_DIR / "skills" / "pinterest-scraper" / "scripts" / "scraper.py"

def get_archetype_images(archetype_name: str, limit: int = 1, card_type: str = "MaleAnime"):
    """
    Fetches archetype images using the pinterest-scraper.
    If the scraper optimizes the query, the archetype_keywords.json is updated.
    """
    if not KEYWORDS_JSON.exists():
        print(f"Error: {KEYWORDS_JSON} not found.", file=sys.stderr)
        return None

    with open(KEYWORDS_JSON, "r", encoding="utf-8") as f:
        keywords_map = json.load(f)

    if card_type not in keywords_map:
        print(f"Error: Card type '{card_type}' not found in configuration.", file=sys.stderr)
        return None

    type_map = keywords_map[card_type]
    if archetype_name not in type_map:
        print(f"Error: Archetype '{archetype_name}' not found in configuration for {card_type}.", file=sys.stderr)
        return None

    original_query = type_map[archetype_name]
    print(f"[*] Fetching images for {archetype_name} ({card_type}): {original_query}")
    
    # Execute scraper
    cmd = [
        "python3", str(SCRAPER_SCRIPT),
        "--query", original_query,
        "--limit", str(limit),
        "--app", "running-coach"
    ]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        output = json.loads(result.stdout)
        
        returned_query = output.get("query")
        urls = output.get("url", [])
        
        # Auto-Update logic: If the scraper returned a different query, it was optimized.
        if returned_query and returned_query != original_query:
            print(f"[*] Optimized keyword detected for '{archetype_name}' ({card_type}):")
            print(f"    From: {original_query[:50]}...")
            print(f"    To:   {returned_query[:50]}...")
            
            keywords_map[card_type][archetype_name] = returned_query
            with open(KEYWORDS_JSON, "w", encoding="utf-8") as f:
                json.dump(keywords_map, f, indent=2, ensure_ascii=False)
            print("[+] archetype_keywords.json updated successfully.")
            
        return urls

    except subprocess.CalledProcessError as e:
        print(f"Error calling scraper: {e.stderr}", file=sys.stderr)
    except json.JSONDecodeError:
        print(f"Error parsing scraper output: {result.stdout}", file=sys.stderr)
    except Exception as e:
        print(f"Unexpected error: {e}", file=sys.stderr)
        
    return None

def create_local_fallback_bg(genre: str, output_path: str):
    """Creates a beautiful abstract gradient background as a last resort."""
    img = Image.new("RGB", (1000, 1400), "#1C1C1E")
    draw = ImageDraw.Draw(img)
    
    colors = {
        "全能戰士｜All-Rounder": ("#5E248E", "#1C1C1E"),
        "山地靈羊｜Mountain Goat": ("#4A5D23", "#1C1C1E"),
        "速度獵豹｜Speed Cheetah": ("#FF8C00", "#1C1C1E"),
        "穩定節拍器｜Steady Metronome": ("#F5F5DC", "#1C1C1E"),
        "耐力大師｜Endurance Master": ("#FFD700", "#1C1C1E"),
        "長距離行者｜Long Distance Walker": ("#FFBF00", "#1C1C1E"),
        "疾速先鋒｜Velocity Vanguard": ("#FF00FF", "#1C1C1E"),
        "律動苦行僧｜Rhythm Ascetic": ("#696969", "#1C1C1E"),
        "巔峰征服者｜Peak Conqueror": ("#708090", "#1C1C1E"),
        "鋼鐵修復師｜Iron Recovery Smith": ("#008080", "#1C1C1E"),
        "進化中跑者｜Evolving Runner": ("#32CD32", "#1C1C1E"),
        "default": ("#2C2C2E", "#1C1C1E")
    }
    
    color_top, color_bottom = colors.get(genre, colors["default"])
    for i in range(1400):
        r = int(int(color_top[1:3], 16) * (1 - i/1400) + int(color_bottom[1:3], 16) * (i/1400))
        g = int(int(color_top[3:5], 16) * (1 - i/1400) + int(color_bottom[3:5], 16) * (i/1400))
        b = int(int(color_top[5:7], 16) * (1 - i/1400) + int(color_bottom[5:7], 16) * (i/1400))
        draw.line([(0, i), (1000, i)], fill=(r, g, b))
        
    img.save(output_path)

def generate_genre_background(genre: str, output_path: str = "tmp/bg_gen.png", card_type: str = "MaleAnime") -> Optional[str]:
    """Attempts multiple layers of dynamic generation to ensure a unique background every time."""

    image_urls = get_archetype_images(genre, card_type=card_type) or []
    for url in image_urls:
        try:
            seed = random.randint(1, 1000000)
            if "unsplash.com" in url:
                # Optimized size for background
                fetch_url = f"{url}?auto=format&fit=crop&w=1000&q=80&sig={seed}"
            else:
                fetch_url = f"{url}?sig={seed}"

            logger.info(f"Fetching background for {genre}: {fetch_url}")
            resp = requests.get(fetch_url, timeout=30)
            if resp.status_code == 200:
                with open(output_path, 'wb') as f:
                    f.write(resp.content)
                return url
        except Exception as e:
            logger.error(f"Pool fetch failed: {e}")

    # Local Fallback
    create_local_fallback_bg(genre, output_path)
    return None

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 image_generator.py <archetype_name> [limit] [card_type]")
        sys.exit(1)
        
    name = sys.argv[1]
    limit_val = int(sys.argv[2]) if len(sys.argv) > 2 else 1
    card_type_val = sys.argv[3] if len(sys.argv) > 3 else "MaleAnime"
    
    images = get_archetype_images(name, limit_val, card_type=card_type_val)
    if images:
        print(json.dumps(images, indent=2))
    else:
        sys.exit(1)
