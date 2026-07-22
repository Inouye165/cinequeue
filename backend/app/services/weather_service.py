import logging
import time
from urllib.parse import quote
import httpx

logger = logging.getLogger(__name__)

# In-memory cache for weather results: {location_key: (timestamp, weather_report_string)}
_WEATHER_CACHE: dict[str, tuple[float, str]] = {}
_CACHE_TTL_SECONDS = 900  # 15 minutes


class WeatherService:
    @staticmethod
    async def get_weather_report(location: str | None) -> str | None:
        """Fetch current weather report for a given city or zipcode.
        
        Returns a concise summary string or None if location is empty or fetch fails.
        Cached for 15 minutes per location.
        """
        if not location or not location.strip():
            return None

        loc_str = location.strip()
        cache_key = loc_str.lower()
        now = time.time()

        if cache_key in _WEATHER_CACHE:
            cached_time, cached_report = _WEATHER_CACHE[cache_key]
            if now - cached_time < _CACHE_TTL_SECONDS:
                return cached_report

        encoded_loc = quote(loc_str)

        # Primary source: wttr.in JSON format
        try:
            async with httpx.AsyncClient(timeout=4.0) as client:
                res = await client.get(f"https://wttr.in/{encoded_loc}?format=j1")
                if res.status_code == 200:
                    data = res.json()
                    curr = data.get("current_condition", [{}])[0]
                    area_info = data.get("nearest_area", [{}])[0]

                    temp_f = curr.get("temp_F", "")
                    temp_c = curr.get("temp_C", "")
                    desc_list = curr.get("weatherDesc", [{}])
                    desc = desc_list[0].get("value", "") if desc_list else ""
                    humidity = curr.get("humidity", "")
                    wind_mph = curr.get("windspeedMiles", "")

                    area_name = area_info.get("areaName", [{}])[0].get("value", loc_str)
                    region = area_info.get("region", [{}])[0].get("value", "")
                    location_label = f"{area_name}, {region}".strip(", ") if region else area_name

                    parts = []
                    if temp_f:
                        parts.append(f"{temp_f}°F ({temp_c}°C)")
                    if desc:
                        parts.append(desc)
                    if humidity:
                        parts.append(f"{humidity}% humidity")
                    if wind_mph:
                        parts.append(f"wind {wind_mph} mph")

                    details_str = ", ".join(parts)
                    report = f"{location_label} — {details_str}"
                    _WEATHER_CACHE[cache_key] = (now, report)
                    return report
        except Exception as e:
            logger.warning(f"Failed to fetch weather from wttr.in for '{loc_str}': {e}")

        # Fallback: Open-Meteo API
        try:
            async with httpx.AsyncClient(timeout=4.0) as client:
                geo_res = await client.get(
                    "https://geocoding-api.open-meteo.com/v1/search",
                    params={"name": loc_str, "count": 1},
                )
                if geo_res.status_code == 200:
                    results = geo_res.json().get("results")
                    if results:
                        place = results[0]
                        lat = place.get("latitude")
                        lon = place.get("longitude")
                        place_name = place.get("name", loc_str)
                        admin1 = place.get("admin1", "")
                        loc_display = f"{place_name}, {admin1}".strip(", ")

                        wx_res = await client.get(
                            "https://api.open-meteo.com/v1/forecast",
                            params={
                                "latitude": lat,
                                "longitude": lon,
                                "current": "temperature_2m,relative_humidity_2m,wind_speed_10m,weather_code",
                                "temperature_unit": "fahrenheit",
                                "wind_speed_unit": "mph",
                            },
                        )
                        if wx_res.status_code == 200:
                            current = wx_res.json().get("current", {})
                            temp = current.get("temperature_2m")
                            rh = current.get("relative_humidity_2m")
                            wind = current.get("wind_speed_10m")
                            wcode = current.get("weather_code", 0)

                            code_map = {
                                0: "Clear sky",
                                1: "Mainly clear",
                                2: "Partly cloudy",
                                3: "Overcast",
                                45: "Foggy",
                                51: "Light drizzle",
                                61: "Rain",
                                63: "Moderate rain",
                                65: "Heavy rain",
                                71: "Snow",
                                80: "Rain showers",
                                95: "Thunderstorm",
                            }
                            desc = code_map.get(wcode, "Weather")
                            report = f"{loc_display} — {temp}°F, {desc}, {rh}% humidity, wind {wind} mph"
                            _WEATHER_CACHE[cache_key] = (now, report)
                            return report
        except Exception as e:
            logger.warning(f"Failed to fetch weather from Open-Meteo fallback for '{loc_str}': {e}")

        return None
