"""Weather context snapshots for history and live caddie decisions."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Literal
from urllib.parse import urlencode
from urllib.request import urlopen


WeatherSource = Literal["manual", "open_meteo", "missing"]
WeatherTransport = Callable[[str], dict[str, Any]]
OPEN_METEO_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
OPEN_METEO_CURRENT_FIELDS = (
    "temperature_2m",
    "wind_speed_10m",
    "wind_direction_10m",
    "precipitation",
)


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


def _iso_z(value: str | None) -> str | None:
    if not value:
        return None
    text = str(value)
    if text.endswith("Z"):
        return text
    if "T" in text and len(text) == 16:
        return f"{text}:00Z"
    if "T" in text and len(text) == 19:
        return f"{text}Z"
    return text


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
        "capturedAt": _iso_z(captured_at),
        "location": {"latitude": latitude, "longitude": longitude} if latitude is not None and longitude is not None else None,
        "windSpeedMps": wind_speed,
        "windDirectionDeg": wind_direction,
        "temperatureC": temperature,
        "precipitationMm": precipitation,
        "confidence": "medium" if state == "ready" and resolved_source == "manual" else "high" if state == "ready" else "low",
        "missingData": missing,
    }


def _open_meteo_url(latitude: float, longitude: float) -> str:
    query = urlencode(
        {
            "latitude": latitude,
            "longitude": longitude,
            "current": ",".join(OPEN_METEO_CURRENT_FIELDS),
            "wind_speed_unit": "ms",
            "timezone": "UTC",
        }
    )
    return f"{OPEN_METEO_FORECAST_URL}?{query}"


def _default_open_meteo_transport(url: str) -> dict[str, Any]:
    with urlopen(url, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


def fetch_open_meteo_weather_snapshot(
    *,
    round_id: str | None = None,
    hole: int | None = None,
    captured_at: str | None = None,
    latitude: float | None = None,
    longitude: float | None = None,
    transport: WeatherTransport | None = None,
) -> dict[str, Any]:
    if latitude is None or longitude is None:
        return build_weather_snapshot(
            round_id=round_id,
            hole=hole,
            captured_at=captured_at,
            latitude=latitude,
            longitude=longitude,
            source="open_meteo",
        )
    try:
        payload = (transport or _default_open_meteo_transport)(_open_meteo_url(latitude, longitude))
        current = payload.get("current") if isinstance(payload, dict) else None
        if not isinstance(current, dict):
            raise ValueError("open meteo response did not include current weather")
        observed = {
            "windSpeedMps": current.get("wind_speed_10m"),
            "windDirectionDeg": current.get("wind_direction_10m"),
            "temperatureC": current.get("temperature_2m"),
            "precipitationMm": current.get("precipitation"),
        }
        return build_weather_snapshot(
            round_id=round_id,
            hole=hole,
            captured_at=captured_at or str(current.get("time") or ""),
            latitude=latitude,
            longitude=longitude,
            source="open_meteo",
            observed=observed,
        )
    except Exception as exc:
        snapshot = build_weather_snapshot(
            round_id=round_id,
            hole=hole,
            captured_at=captured_at,
            latitude=latitude,
            longitude=longitude,
            source="open_meteo",
        )
        snapshot["missingData"].append({"label": "weather_provider", "reason": str(exc)})
        return snapshot


def weather_snapshot_file(root: Path | str | None = None) -> Path:
    return Path(root or ".") / "data" / "weather" / "weather_snapshots.jsonl"


def store_weather_snapshot(snapshot: dict[str, Any], *, root: Path | str | None = None) -> dict[str, Any]:
    path = weather_snapshot_file(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(snapshot, sort_keys=True, ensure_ascii=False) + "\n")
    return snapshot


def list_weather_snapshots(*, root: Path | str | None = None) -> list[dict[str, Any]]:
    path = weather_snapshot_file(root)
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def latest_weather_snapshot(round_id: str, hole: int | None = None, *, root: Path | str | None = None) -> dict[str, Any] | None:
    matches = [
        row
        for row in list_weather_snapshots(root=root)
        if str(row.get("roundId")) == str(round_id) and (hole is None or row.get("hole") == hole)
    ]
    if not matches:
        return None
    return sorted(matches, key=lambda row: str(row.get("capturedAt") or ""))[-1]
