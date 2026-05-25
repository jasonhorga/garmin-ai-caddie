from __future__ import annotations

from ai_caddie.weather_context import build_weather_snapshot

from .models import WeatherSnapshotResponse


def load_weather_snapshot_response(
    *,
    round_id: str | None = None,
    hole: int | None = None,
    captured_at: str | None = None,
    latitude: float | None = None,
    longitude: float | None = None,
    wind_speed_mps: float | None = None,
    wind_direction_deg: int | None = None,
    temperature_c: float | None = None,
    precipitation_mm: float | None = None,
) -> WeatherSnapshotResponse:
    observed = {
        "windSpeedMps": wind_speed_mps,
        "windDirectionDeg": wind_direction_deg,
        "temperatureC": temperature_c,
        "precipitationMm": precipitation_mm,
    }
    snapshot = build_weather_snapshot(
        round_id=round_id,
        hole=hole,
        captured_at=captured_at,
        latitude=latitude,
        longitude=longitude,
        source="manual",
        observed=observed,
    )
    return WeatherSnapshotResponse(**snapshot)
