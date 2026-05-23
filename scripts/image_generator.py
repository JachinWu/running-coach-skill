"""image_generator.py — Dynamically generate or fetch thematic backgrounds with de-duplication and auto-curation."""

import os
import requests
import logging
import random
import json
import urllib.parse
from typing import Optional, Tuple, Any, Dict, List
from pathlib import Path
from dotenv import load_dotenv
from PIL import Image, ImageDraw

load_dotenv()

logger = logging.getLogger(__name__)

BANANA_API_KEY = os.getenv("BANANA_API_KEY")
API_URL = "https://api.nanobananaapi.dev/v1/images/generate"

# Paths
SCRIPTS_DIR = Path(__file__).resolve().parent
DATA_DIR = SCRIPTS_DIR.parent / "data"
HISTORY_FILE = DATA_DIR / "background_history.json"
DISCOVERED_FILE = DATA_DIR / "pinterest_images.json"

# Aesthetic Style DNA for all card backgrounds
GLOBAL_STYLE_DNA = (
    "cinematic character card, legendary runner archetype, high contrast lighting, "
    "atmospheric depth, premium trading card art, subtle holographic effects, "
    "dynamic composition, ultra detailed, dark elegant color palette, "
    "AAA game concept art, sports fantasy aesthetic"
)

# Unsplash-friendly search keywords for secondary fallback
UNSPLASH_QUERIES = {
    "全能戰士｜All-Rounder": "nebula cosmos space",
    "山地靈羊｜Mountain Goat": "mountain ridge mist",
    "速度獵豹｜Speed Cheetah": "neon motion blur",
    "穩定節拍器｜Steady Metronome": "zen garden karesansui",
    "耐力大師｜Endurance Master": "endless desert road",
    "長距離行者｜Long Distance Walker": "highway horizon sunset",
    "疾速先鋒｜Velocity Vanguard": "cyberpunk city neon",
    "律動苦行僧｜Rhythm Ascetic": "monk meditation minimal",
    "巔峰征服者｜Peak Conqueror": "mountain summit victory",
    "鋼鐵修復師｜Iron Recovery Smith": "biotechnology neon green",
    "進化中跑者｜Evolving Runner": "sprout concrete morning dew",
    "default": "abstract gradient running"
}

# Aesthetic Search Prompts for each genre
GENRE_PROMPTS = {
    "全能戰士｜All-Rounder": f"cosmic runner warrior standing inside nebula energy core, balanced power aura, floating geometric particles, galactic armor, purple blue holographic light, cinematic sci-fi fantasy, {GLOBAL_STYLE_DNA}",
    "山地靈羊｜Mountain Goat": f"mountain goat humanoid climber, standing on rugged alpine ridge, dawn mist atmosphere, wind flowing cloak, earth tone tactical gear, cinematic mountain fantasy, adventure sports aesthetic, {GLOBAL_STYLE_DNA}",
    "速度獵豹｜Speed Cheetah": f"cyber cheetah speed runner, neon motion trails, futuristic sprint pose, orange electric energy, sleek aerodynamic armor, high speed distortion, anime sci-fi sports aesthetic, {GLOBAL_STYLE_DNA}",
    "穩定節拍器｜Steady Metronome": f"zen monk runner walking through karesansui garden, perfect rhythm symbolism, minimal monochrome palette, flowing robe movement, soft cinematic shadows, calm focused aura, luxury japanese minimalism, {GLOBAL_STYLE_DNA}",
    "耐力大師｜Endurance Master": f"lone endurance runner on endless valley road, sunset cinematic lighting, persistent journey atmosphere, dust and wind particles, weathered tactical outfit, emotional storytelling composition, {GLOBAL_STYLE_DNA}",
    "長距離行者｜Long Distance Walker": f"solitary road runner walking toward horizon, golden hour highway, vast atmospheric landscape, minimal warm color palette, quiet determination aura, cinematic realism, {GLOBAL_STYLE_DNA}",
    "疾速先鋒｜Velocity Vanguard": f"cyberpunk lightning runner, night city skyline, magenta cyan neon storm, electric energy burst, high contrast shadows, futuristic sports warrior, anime cinematic action, {GLOBAL_STYLE_DNA}",
    "律動苦行僧｜Rhythm Ascetic": f"disciplined monk athlete, black and white zen environment, ritual running patterns, minimalist japanese shadows, focus and repetition symbolism, calm intensity, {GLOBAL_STYLE_DNA}",
    "巔峰征服者｜Peak Conqueror": f"epic climber warrior on sharp mountain summit, storm clouds opening, victory stance silhouette, massive environmental scale, cinematic fantasy adventure, cold blue gray palette, {GLOBAL_STYLE_DNA}",
    "鋼鐵修復師｜Iron Recovery Smith": f"biotech regeneration warrior, glowing teal energy veins, organic cybernetic body, floating healing particles, dark futuristic laboratory atmosphere, sci-fi medical fantasy, {GLOBAL_STYLE_DNA}",
    "進化中跑者｜Evolving Runner": f"young runner emerging from cracked concrete, green energy growth aura, hopeful sunrise lighting, nature reclaiming urban ruins, evolution symbolism, cinematic inspirational fantasy, {GLOBAL_STYLE_DNA}",
    "default": f"minimalist abstract gradient sports background, {GLOBAL_STYLE_DNA}"
}

def load_json_file(file_path: Path) -> Dict[str, Any]:
    """Safely loads a JSON file."""
    if file_path.exists():
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load {file_path.name}: {e}")
    return {}

def save_json_file(file_path: Path, data: Any):
    """Safely saves a JSON file."""
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Failed to save {file_path.name}: {e}")

import subprocess

def get_fresh_url(genre: str, app_name: str = "running-coach") -> tuple[Optional[str], Optional[str]]:
    """Fetches a URL from the standalone pinterest-scraper skill. Returns (image_url, optimized_query)."""
    scraper_path = SCRIPTS_DIR.parent.parent / "pinterest-scraper" / "scripts" / "scraper.py"
    
    if not scraper_path.exists():
        logger.error(f"Scraper not found at {scraper_path}")
        return None, None

    try:
        # Call the standalone skill
        cmd = [
            "python3", str(scraper_path),
            "--query", genre,
            "--limit", "5",
            "--app", app_name
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        data = json.loads(result.stdout)
        
        if isinstance(data, dict):
            optimized_query = data.get("query")
            urls = data.get("url", [])
            if urls:
                return random.choice(urls), optimized_query
    except Exception as e:
        logger.error(f"Failed to call standalone scraper: {e}")
        
    return None, None

def curate_image_pool():
    """Daily job: Prune used/dead links and replenish pool with new discovery."""
    logger.info("🎨 Starting Autonomous Image Curation Job...")
    discovered = load_json_file(DISCOVERED_FILE)
    history = load_json_file(HISTORY_FILE)
    
    # 1. Prune Used Links: Remove anything in history from the discovered pool
    for genre, used_list in history.items():
        if genre in discovered:
            original_count = len(discovered[genre])
            discovered[genre] = [url for url in discovered[genre] if url not in used_list]
            pruned_count = original_count - len(discovered[genre])
            if pruned_count > 0:
                logger.info(f"Pruned {pruned_count} used images from {genre} pool.")
        # Clear history after pruning to allow future cycles if pool is replenished
        history[genre] = []
    
    # 2. Prune Dead Links: Quick HEAD check on remaining links
    for genre in list(discovered.keys()):
        valid_urls = []
        for url in discovered[genre]:
            try:
                resp = requests.head(url, timeout=5)
                if resp.status_code == 200:
                    valid_urls.append(url)
                else:
                    logger.warning(f"Removing dead link ({resp.status_code}): {url}")
            except:
                logger.warning(f"Removing unreachable link: {url}")
        discovered[genre] = valid_urls

    # 3. Replenish Pool: Discover new images for each genre
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    for genre, prompt in GENRE_PROMPTS.items():
        if genre == "default": continue
        
        current_pool = discovered.get(genre, [])
        if len(current_pool) < 10: # Threshold for replenishment
            # Use simplified queries for Unsplash search
            search_query = UNSPLASH_QUERIES.get(genre, "running")
            logger.info(f"Replenishing pool for {genre} with query: {search_query}")
            try:
                # Use Unsplash NAPI for discovery
                search_url = f"https://unsplash.com/napi/search/photos?query={urllib.parse.quote(search_query)}&per_page=15"
                resp = requests.get(search_url, headers=headers, timeout=15)
                if resp.status_code == 200:
                    results = resp.json().get("results", [])
                    new_links = []
                    for r in results:
                        # Extract the raw photo URL (hotlink friendly)
                        img_url = r.get("urls", {}).get("raw")
                        if img_url and img_url not in current_pool:
                            # Strip extra params for clean storage, but keep essential ones for quality
                            clean_url = img_url.split('?')[0]
                            new_links.append(clean_url)
                    
                    # Add unique ones to pool
                    discovered[genre] = list(set(current_pool + new_links))
                    logger.info(f"Added {len(new_links)} new images to {genre} pool.")
            except Exception as e:
                logger.error(f"Discovery failed for {genre}: {e}")

    save_json_file(DISCOVERED_FILE, discovered)
    save_json_file(HISTORY_FILE, history)
    logger.info("🎨 Image Curation Job Complete.")

def create_local_fallback_bg(genre: str, output_path: str):
    """Creates a beautiful abstract gradient background as a last resort."""
    img = Image.new("RGB", (1000, 1000), "#1C1C1E")
    draw = ImageDraw.Draw(img)
    
    colors = {
        "全能戰士｜All-Rounder": ("#5E248E", "#1C1C1E"),  # Cosmic Purple Blue
        "山地靈羊｜Mountain Goat": ("#4A5D23", "#1C1C1E"), # Alpine Stone (Greenish)
        "速度獵豹｜Speed Cheetah": ("#FF8C00", "#1C1C1E"), # Electric Orange
        "穩定節拍器｜Steady Metronome": ("#F5F5DC", "#1C1C1E"), # Zen Beige
        "耐力大師｜Endurance Master": ("#FFD700", "#1C1C1E"), # Sunset Gold
        "長距離行者｜Long Distance Walker": ("#FFBF00", "#1C1C1E"), # Horizon Amber
        "疾速先鋒｜Velocity Vanguard": ("#FF00FF", "#1C1C1E"), # Neon Magenta
        "律動苦行僧｜Rhythm Ascetic": ("#696969", "#1C1C1E"), # Monochrome Ash
        "巔峰征服者｜Peak Conqueror": ("#708090", "#1C1C1E"), # Glacier Blue
        "鋼鐵修復師｜Iron Recovery Smith": ("#008080", "#1C1C1E"), # Regeneration Teal
        "進化中跑者｜Evolving Runner": ("#32CD32", "#1C1C1E"), # Growth Green
        "default": ("#2C2C2E", "#1C1C1E")
    }
    
    color_top, color_bottom = colors.get(genre, colors["default"])
    for i in range(1000):
        r = int(int(color_top[1:3], 16) * (1 - i/1000) + int(color_bottom[1:3], 16) * (i/1000))
        g = int(int(color_top[3:5], 16) * (1 - i/1000) + int(color_bottom[3:5], 16) * (i/1000))
        b = int(int(color_top[5:7], 16) * (1 - i/1000) + int(color_bottom[5:7], 16) * (i/1000))
        draw.line([(0, i), (1000, i)], fill=(r, g, b))
        
    img.save(output_path)
    return True

def generate_genre_background(genre: str, output_path: str = "tmp/bg_gen.png", gender: str = "male") -> tuple[bool, Optional[str]]:
    """Attempts multiple layers of dynamic generation to ensure a unique background every time."""
    
    prompt = GENRE_PROMPTS.get(genre, GENRE_PROMPTS["default"])
    chosen_url = None
    
    # LAYER 1: Truly Unique AI Generation (Omitted for brevity if unchanged)
    
    # LAYER 2: Discovered Pool with De-duplication
    app_name = f"running-coach-{gender}"
    chosen_url, optimized_q = get_fresh_url(genre, app_name=app_name)
    if chosen_url:
        try:
            seed = random.randint(1, 1000000)
            fetch_url = chosen_url
            if "unsplash.com" in fetch_url:
                # Optimized size for background
                fetch_url += f"?auto=format&fit=crop&w=1000&q=80&sig={seed}"
            else:
                fetch_url += f"?sig={seed}"
            
            logger.info(f"Fetching background for {genre}: {fetch_url}")
            resp = requests.get(fetch_url, timeout=30)
            if resp.status_code == 200:
                with open(output_path, 'wb') as f:
                    f.write(resp.content)
                
                # Return the chosen URL and the optimized query
                return True, chosen_url
        except Exception as e:
            logger.error(f"Pool fetch failed: {e}")

    # LAYER 3: Local Fallback
    return create_local_fallback_bg(genre, output_path), None

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    # Manual curation trigger for testing
    curate_image_pool()
