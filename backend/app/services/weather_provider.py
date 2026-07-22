"""Weather provider abstractions and concrete implementations for CineQueue."""

from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass
import logging
import time
from typing import Any
from urllib.parse import quote
import httpx

logger = logging.getLogger(__name__)


@dataclass
class WeatherData:
    conditions: str
    temperature_f: float
    temperature_c: float
    high_f: float | None = None
    low_f: float | None = None
    precipitation_probability: int | None = None
    significant_alert: str | None = None
    retrieved_at: str = ""
    location_used: str = ""
    provider_name: str = "unknown"
    status: str = "success"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class WeatherProvider(ABC):
    """Abstract base class for weather data providers."""

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Name identifier of the weather provider."""
        ...

    @abstractmethod
    async def fetch_weather(self, location: str) -> WeatherData | None:
        """Fetch current weather for a city or ZIP code. Return None on failure."""
        ...


class WttrInWeatherProvider(WeatherProvider):
    """Weather provider using wttr.in JSON interface."""

    @property
    def provider_name(self) -> str:
        return "wttr.in"

    async def fetch_weather(self, location: str) -> WeatherData | None:
        loc_str = location.strip()
        if not loc_str:
            return None
        encoded_loc = quote(loc_str)
        try:
            async with httpx.AsyncClient(timeout=4.0) as client:
                res = await client.get(f"https://wttr.in/{encoded_loc}?format=j1")
                if res.status_code == 200:
                    data = res.json()
                    curr = data.get("current_condition", [{}])[0]
                    area_info = data.get("nearest_area", [{}])[0]
                    weather_days = data.get("weather", [])

                    temp_f_val = float(curr.get("temp_F", 0))
                    temp_c_val = float(curr.get("temp_C", 0))
                    desc_list = curr.get("weatherDesc", [{}])
                    desc = desc_list[0].get("value", "Clear") if desc_list else "Clear"

                    area_name = area_info.get("areaName", [{}])[0].get("value", loc_str)
                    region = area_info.get("region", [{}])[0].get("value", "")
                    location_label = f"{area_name}, {region}".strip(", ") if region else area_name

                    high_f = None
                    low_f = None
                    precip_prob = None

                    if weather_days:
                        today_forecast = weather_days[0]
                        high_f = float(today_forecast.get("maxtempF", temp_f_val))
                        low_f = float(today_forecast.get("mintempF", temp_f_val))
                        hourly = today_forecast.get("hourly", [])
                        if hourly:
                            chance_rain = max([int(h.get("chanceofrain", 0)) for h in hourly], default=0)
                            precip_prob = chance_rain

                    return WeatherData(
                        conditions=desc,
                        temperature_f=temp_f_val,
                        temperature_c=temp_c_val,
                        high_f=high_f,
                        low_f=low_f,
                        precipitation_probability=precip_prob,
                        significant_alert=None,
                        retrieved_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                        location_used=location_label,
                        provider_name=self.provider_name,
                        status="success",
                    )
        except Exception as e:
            logger.warning(f"WttrInWeatherProvider failed for '{loc_str}': {e}")
            return None


class OpenMeteoWeatherProvider(WeatherProvider):
    """Weather provider using Open-Meteo Geocoding & Forecast APIs."""

    @property
    def provider_name(self) -> str:
        return "open-meteo"

    async def fetch_weather(self, location: str) -> WeatherData | None:
        loc_str = location.strip()
        if not loc_str:
            return None
        try:
            async with httpx.AsyncClient(timeout=4.0) as client:
                geo_res = await client.get(
                    "https://geocoding-api.open-meteo.com/v1/search",
                    params={"name": loc_str, "count": 1},
                )
                if geo_res.status_code != 200:
                    return None

                results = geo_res.json().get("results")
                if not results:
                    return None

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
                        "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max",
                        "temperature_unit": "fahrenheit",
                        "wind_speed_unit": "mph",
                        "timezone": "auto",
                    },
                )
                if wx_res.status_code == 200:
                    data = wx_res.json()
                    current = data.get("current", {})
                    daily = data.get("daily", {})

                    temp_f = float(current.get("temperature_2m", 0.0))
                    temp_c = round((temp_f - 32) * 5 / 9, 1)
                    wcode = current.get("weather_code", 0)

                    high_f = float(daily.get("temperature_2m_max", [temp_f])[0]) if daily.get("temperature_2m_max") else None
                    low_f = float(daily.get("temperature_2m_min", [temp_f])[0]) if daily.get("temperature_2m_min") else None
                    precip = int(daily.get("precipitation_probability_max", [0])[0]) if daily.get("precipitation_probability_max") else None

                    code_map = {
                        0: "Clear sky", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
                        45: "Foggy", 51: "Light drizzle", 61: "Rain", 63: "Moderate rain",
                        65: "Heavy rain", 71: "Snow", 80: "Rain showers", 95: "Thunderstorm",
                    }
                    desc = code_map.get(wcode, "Weather")
                    alert = "Thunderstorm Warning" if wcode == 95 else None

                    return WeatherData(
                        conditions=desc,
                        temperature_f=temp_f,
                        temperature_c=temp_c,
                        high_f=high_f,
                        low_f=low_f,
                        precipitation_probability=precip,
                        significant_alert=alert,
                        retrieved_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                        location_used=loc_display,
                        provider_name=self.provider_name,
                        status="success",
                    )
        except Exception as e:
            logger.warning(f"OpenMeteoWeatherProvider failed for '{loc_str}': {e}")
            return None
