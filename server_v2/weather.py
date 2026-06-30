from __future__ import annotations

from pathlib import Path
from typing import Literal

from ai_caddie.llm.weather_context import (
    WeatherTransport,
    build_weather_snapshot,
    fetch_open_meteo_weather_snapshot,
    store_weather_snapshot,
)
from ai_caddie.rounds.players import OWNER_ID

from .models import WeatherSnapshotResponse


WEATHER_ROOT = Path(".")
OPEN_METEO_TRANSPORT: WeatherTransport | None = None


def load_weather_snapshot_response(
    *,
    source: Literal["manual", "open_meteo"] = "manual",
    persist: bool = False,
    round_id: str | None = None,
    hole: int | None = None,
    captured_at: str | None = None,
    latitude: float | None = None,
    longitude: float | None = None,
    wind_speed_mps: float | None = None,
    wind_direction_deg: int | None = None,
    temperature_c: float | None = None,
    precipitation_mm: float | None = None,
    player_id: str = OWNER_ID,
) -> WeatherSnapshotResponse:
    if source == "open_meteo":
        snapshot = fetch_open_meteo_weather_snapshot(
            round_id=round_id,
            hole=hole,
            captured_at=captured_at,
            latitude=latitude,
            longitude=longitude,
            transport=OPEN_METEO_TRANSPORT,
        )
    else:
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
    if persist and snapshot.get("state") == "ready":
        # Member-scoped: the snapshot lands in the caller's evidence partition; the owner stays flat.
        store_weather_snapshot(snapshot, root=WEATHER_ROOT, player_id=player_id)
    return WeatherSnapshotResponse(**snapshot)
