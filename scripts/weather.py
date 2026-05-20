"""weather.py — Fetch weather and AQI data for Taiwan using CWA and MOENV APIs."""

import os
import requests
import logging
import urllib3
import math
from typing import Optional, Dict, Any, List
from pathlib import Path
from dotenv import load_dotenv

# Suppress InsecureRequestWarning
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Path setup
env_path = Path(__file__).resolve().parents[4] / ".env"
load_dotenv(dotenv_path=env_path)

logger = logging.getLogger(__name__)

# API Keys
CWA_API_KEY = os.getenv("CWA_API_KEY")
MOENV_API_KEY = os.getenv("MOENV_API_KEY")

# Default location
DEFAULT_LOCATION = "桃園市"
DEFAULT_SITENAME = "桃園"

def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate the great-circle distance between two points on Earth."""
    R = 6371.0 # Earth radius in km
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

def get_weather_by_coords(lat: float, lon: float) -> Optional[Dict[str, Any]]:
    """Fetch real-time weather observation from the nearest CWA station.
    
    API: O-A0003-001 (Station Observations)
    """
    if not CWA_API_KEY:
        logger.warning("CWA_API_KEY not found in environment.")
        return None

    url = "https://opendata.cwa.gov.tw/api/v1/rest/datastore/O-A0003-001"
    params = {
        "Authorization": CWA_API_KEY,
        "format": "JSON"
    }

    try:
        response = requests.get(url, params=params, timeout=15, verify=False)
        response.raise_for_status()
        data = response.json()
        
        records = data.get("records", {})
        stations = records.get("Station") or records.get("location") or records.get("station")
        
        if not stations and isinstance(records, list):
            stations = records
            
        if not stations:
            logger.warning(f"No stations found in CWA response. Data keys: {data.keys()}")
            return None

        nearest_station = None
        min_distance = float('inf')

        for s in stations:
            geoinfo = s.get("GeoInfo", {})
            coords_list = geoinfo.get("Coordinates", [])
            s_lat, s_lon = 0.0, 0.0
            
            if isinstance(coords_list, list):
                for c in coords_list:
                    if c.get("CoordinateName") == "WGS84":
                        try:
                            s_lat = float(c.get("StationLatitude") or 0)
                            s_lon = float(c.get("StationLongitude") or 0)
                        except (ValueError, TypeError):
                            continue
                        break
            
            if s_lat == 0 or s_lon == 0:
                try:
                    s_lat = float(s.get("lat") or geoinfo.get("Latitude") or 0)
                    s_lon = float(s.get("lon") or geoinfo.get("Longitude") or 0)
                except (ValueError, TypeError):
                    continue
            
            if s_lat == 0 or s_lon == 0: continue
            
            dist = haversine(lat, lon, s_lat, s_lon)
            if dist < min_distance:
                min_distance = dist
                nearest_station = s

        if nearest_station:
            elements = nearest_station.get("WeatherElement", {})
            return {
                "station_name": nearest_station.get("StationName"),
                "temp": elements.get("AirTemperature"),
                "humidity": elements.get("RelativeHumidity"),
                "wind_speed": elements.get("WindSpeed"),
                "distance_km": round(min_distance, 2),
                "obs_time": nearest_station.get("ObsTime", {}).get("DateTime")
            }
        return None
    except Exception as e:
        logger.error(f"Failed to fetch weather by coordinates: {e}")
        return None

def get_weather_forecast(location_name: str = DEFAULT_LOCATION) -> Optional[Dict[str, Any]]:
    """Fetch weather forecast from CWA (Central Weather Administration).
    
    API: F-C0032-001 (36-hour forecast)
    """
    if not CWA_API_KEY:
        logger.warning("CWA_API_KEY not found in environment.")
        return None

    url = "https://opendata.cwa.gov.tw/api/v1/rest/datastore/F-C0032-001"
    params = {
        "Authorization": CWA_API_KEY,
        "locationName": location_name,
        "format": "JSON"
    }

    try:
        response = requests.get(url, params=params, timeout=10, verify=False)
        response.raise_for_status()
        data = response.json()
        
        if not data.get("success") == "true":
            logger.error(f"CWA API error: {data.get('message')}")
            return None

        records = data.get("records", {}).get("location", [])
        if not records:
            return None
        
        elements = records[0].get("weatherElement", [])
        result = {}
        for el in elements:
            name = el.get("elementName")
            value = el.get("time", [{}])[0].get("parameter", {}).get("parameterName")
            if name == "Wx":
                result["condition"] = value
            elif name == "PoP":
                result["pop"] = value
            elif name == "MinT":
                result["min_temp"] = value
            elif name == "MaxT":
                result["max_temp"] = value
            elif name == "CI":
                result["comfort"] = value
        
        return result
    except Exception as e:
        logger.error(f"Failed to fetch weather from CWA: {e}")
        return None

def get_aqi(sitename: str = DEFAULT_SITENAME) -> Optional[Dict[str, Any]]:
    """Fetch AQI from MOENV (Ministry of Environment).
    
    API: aq_p_432 (Real-time AQI)
    """
    if not MOENV_API_KEY:
        logger.warning("MOENV_API_KEY not found in environment.")
        return None

    url = "https://data.moenv.gov.tw/api/v2/aqx_p_432"
    params = {
        "api_key": MOENV_API_KEY,
        "format": "JSON",
        "offset": 0,
        "limit": 1000,
        "language": "zh"
    }

    try:
        response = requests.get(url, params=params, timeout=10, verify=False)
        response.raise_for_status()
        records = response.json()
        
        if not isinstance(records, list):
            if isinstance(records, dict):
                records = records.get("records", [])

        for record in records:
            if record.get("sitename") == sitename:
                return {
                    "aqi": record.get("aqi"),
                    "status": record.get("status"),
                    "pm2.5": record.get("pm2.5"),
                    "o3": record.get("o3"),
                    "publishtime": record.get("publishtime")
                }
        
        return None
    except Exception as e:
        logger.error(f"Failed to fetch AQI from MOENV: {e}")
        return None

def format_weather_summary(weather: Optional[Dict[str, Any]], aqi: Optional[Dict[str, Any]]) -> str:
    """Format weather and AQI into a user-friendly string."""
    lines = []
    
    if weather:
        cond = weather.get("condition", "未知")
        pop = weather.get("pop", "0")
        min_t = weather.get("min_temp", "--")
        max_t = weather.get("max_temp", "--")
        
        emoji = "🌤️"
        if "雨" in cond: emoji = "🌧️"
        elif "雲" in cond: emoji = "☁️"
        elif "晴" in cond: emoji = "☀️"
        
        lines.append(f"{emoji} **今日天氣預報**")
        lines.append(f"• 狀況：{cond}")
        lines.append(f"• 氣溫：{min_t}°C - {max_t}°C")
        lines.append(f"• 降雨機率：{pop}%")
    
    if aqi:
        val = aqi.get("aqi", "N/A")
        status = aqi.get("status", "未知")
        
        aqi_emoji = "🟢"
        try:
            aqi_val = int(val)
            if aqi_val > 150: aqi_emoji = "🔴"
            elif aqi_val > 100: aqi_emoji = "🟠"
            elif aqi_val > 50: aqi_emoji = "🟡"
        except: pass
        
        if lines: lines.append("")
        lines.append(f"{aqi_emoji} **空氣品質 (AQI)**")
        lines.append(f"• 指數：{val} ({status})")
    
    return "\n".join(lines) if lines else "⚠️ 無法取得天氣與 AQI 資訊。"

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    w = get_weather_forecast()
    a = get_aqi()
    print(format_weather_summary(w, a))
