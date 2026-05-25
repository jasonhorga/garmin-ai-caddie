"""Weather context snapshots for history and live caddie decisions."""

from __future__ import annotations

from typing import Any, Literal


WeatherSource = Literal["manual", "open_meteo", "missing"]


def _float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int_or_none(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def build_weather_snapshot(
    *,
    round_id: str | None = None,
    hole: int | None = None,
    captured_at: str | None = None,
    latitude: float | None = None,
    longitude: float | None = None,
    source: WeatherSource = "missing",
    observed: dict[str, Any] | None = None,
) -> dict[str, Any]:
    values = observed or {}
    wind_speed = _float_or_none(values.get("windSpeedMps"))
    wind_direction = _int_or_none(values.get("windDirectionDeg"))
    temperature = _float_or_none(values.get("temperatureC"))
    precipitation = _float_or_none(values.get("precipitationMm"))
    missing = []
    if latitude is None or longitude is None:
        missing.append({"label": "location", "reason": "weather lookup needs latitude and longitude"})
    if not captured_at:
        missing.append({"label": "captured_at", "reason": "weather context needs round or shot time"})
    if wind_speed is None and wind_direction is None and temperature is None and precipitation is None:
        missing.append({"label": "weather_values", "reason": "no observed or forecast weather values available"})
    state = "missing" if missing else "ready"
    resolved_source = source if state == "ready" else "missing"
    return {
        "schema": "ai-caddie-weather-snapshot-v1",
        "state": state,
        "source": resolved_source,
        "roundId": round_id,
        "hole": hole,
        "capturedAt": captured_at,
        "location": {"latitude": latitude, "longitude": longitude} if latitude is not None and longitude is not None else None,
        "windSpeedMps": wind_speed,
        "windDirectionDeg": wind_direction,
        "temperatureC": temperature,
        "precipitationMm": precipitation,
        "confidence": "medium" if state == "ready" and resolved_source == "manual" else "high" if state == "ready" else "low",
        "missingData": missing,
    }
