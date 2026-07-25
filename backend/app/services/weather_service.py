"""Weather service orchestrating caching, provider fallback, and structured output."""

import logging
import time
from typing import Any

from app.services.weather_provider import (
    OpenMeteoWeatherProvider,
    WeatherData,
    WeatherProvider,
    WttrInWeatherProvider,
)

logger = logging.getLogger(__name__)

# Cache structure: {location_key: (timestamp, WeatherData)}
_WEATHER_DATA_CACHE: dict[str, tuple[float, WeatherData]] = {}
_CACHE_TTL_SECONDS = 1200  # 20 minutes (within 15-30 min spec)


class WeatherService:
    def __init__(self, providers: list[WeatherProvider] | None = None) -> None:
        self.providers = providers or [OpenMeteoWeatherProvider(), WttrInWeatherProvider()]

    async def get_weather_data(self, location: str | None) -> WeatherData | None:
        """Fetch structured WeatherData for a city or ZIP code.
        
        Cached for 20 minutes per location.
        Returns None on failure (silently logged).
        """
        if not location or not location.strip():
            return None

        from app.decision_models import get_current_run_context, scrub_secrets
        ctx = get_current_run_context()
        start_t = time.perf_counter()

        loc_clean = location.strip()
        cache_key = loc_clean.lower()
        now = time.time()

        if cache_key in _WEATHER_DATA_CACHE:
            cached_time, cached_data = _WEATHER_DATA_CACHE[cache_key]
            if now - cached_time < _CACHE_TTL_SECONDS:
                cached_copy = WeatherData(**cached_data.to_dict())
                cached_copy.status = "cached"
                if ctx:
                    ctx.record_external_cache_hit("weather")
                    ctx.add_timeline_event(
                        stage="weather_collection",
                        status="hit",
                        duration_ms=round((time.perf_counter() - start_t) * 1000, 2),
                        result={"location": loc_clean, "source": "in_memory_cache"},
                    )
                return cached_copy

        for provider in self.providers:
            try:
                if ctx:
                    ctx.record_external_attempt("weather")
                data = await provider.fetch_weather(loc_clean)
                dur_ms = round((time.perf_counter() - start_t) * 1000, 2)
                if data:
                    _WEATHER_DATA_CACHE[cache_key] = (now, data)
                    if ctx:
                        ctx.add_timeline_event(
                            stage="weather_collection",
                            status="completed",
                            duration_ms=dur_ms,
                            result={"location": loc_clean, "conditions": data.conditions, "provider": provider.provider_name},
                        )
                    return data
            except Exception as e:
                dur_ms = round((time.perf_counter() - start_t) * 1000, 2)
                logger.warning(f"Weather provider '{provider.provider_name}' failed for '{loc_clean}': {e}")
                if ctx:
                    ctx.add_timeline_event(
                        stage="weather_collection",
                        status="failed",
                        duration_ms=dur_ms,
                        result={"location": loc_clean, "provider": provider.provider_name, "error": str(e)},
                    )

        logger.info(f"Failed to retrieve weather for location '{loc_clean}' across all providers.")
        return None

    @staticmethod
    async def get_weather_report(location: str | None) -> str | None:
        """Legacy helper returning a concise string summary for prompt inclusion."""
        service = WeatherService()
        data = await service.get_weather_data(location)
        if not data:
            return None

        parts = [f"{data.location_used} — {data.temperature_f}°F ({data.temperature_c}°C), {data.conditions}"]
        if data.high_f is not None and data.low_f is not None:
            parts.append(f"High: {data.high_f}°F / Low: {data.low_f}°F")
        if data.precipitation_probability is not None:
            parts.append(f"Precip: {data.precipitation_probability}%")
        if data.significant_alert:
            parts.append(f"ALERT: {data.significant_alert}")

        return ", ".join(parts)
