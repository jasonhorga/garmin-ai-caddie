"""Weather context snapshots for history and live caddie decisions."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Literal
from datetime import datetime
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
OPEN_METEO_HOURLY_FIELDS = OPEN_METEO_CURRENT_FIELDS


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


def _parse_iso_datetime(value: str | None) -> datetime | None:
    text = _iso_z(value)
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def _hour_key(value: str | None) -> str | None:
    parsed = _parse_iso_datetime(value)
    if parsed is None:
        return None
    return parsed.replace(minute=0, second=0, microsecond=0).strftime("%Y-%m-%dT%H:00")


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


def _open_meteo_url(latitude: float, longitude: float, captured_at: str | None = None) -> str:
    captured_dt = _parse_iso_datetime(captured_at)
    params: dict[str, object] = {
        "latitude": latitude,
        "longitude": longitude,
        "wind_speed_unit": "ms",
        "timezone": "UTC",
    }
    if captured_dt is None:
        params["current"] = ",".join(OPEN_METEO_CURRENT_FIELDS)
    else:
        params["hourly"] = ",".join(OPEN_METEO_HOURLY_FIELDS)
        params["start_date"] = captured_dt.date().isoformat()
        params["end_date"] = captured_dt.date().isoformat()
    query = urlencode(params)
    return f"{OPEN_METEO_FORECAST_URL}?{query}"


def _default_open_meteo_transport(url: str) -> dict[str, Any]:
    with urlopen(url, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


def _hourly_value(hourly: dict[str, Any], field: str, index: int) -> Any:
    values = hourly.get(field)
    if not isinstance(values, list) or index >= len(values):
        return None
    return values[index]


def _observed_from_hourly(payload: dict[str, Any], captured_at: str | None) -> tuple[dict[str, Any], str]:
    hourly = payload.get("hourly")
    if not isinstance(hourly, dict):
        raise ValueError("open meteo response did not include hourly weather")
    times = hourly.get("time")
    if not isinstance(times, list):
        raise ValueError("open meteo hourly response did not include time values")
    requested_hour = _hour_key(captured_at)
    if requested_hour is None:
        raise ValueError("captured_at could not be resolved to an hourly weather key")
    time_keys = [_hour_key(str(value)) for value in times]
    try:
        index = time_keys.index(requested_hour)
    except ValueError as exc:
        raise ValueError("open meteo hourly response did not include requested round time") from exc
    observed = {
        "windSpeedMps": _hourly_value(hourly, "wind_speed_10m", index),
        "windDirectionDeg": _hourly_value(hourly, "wind_direction_10m", index),
        "temperatureC": _hourly_value(hourly, "temperature_2m", index),
        "precipitationMm": _hourly_value(hourly, "precipitation", index),
    }
    return observed, str(times[index])


def _observed_from_current(payload: dict[str, Any]) -> tuple[dict[str, Any], str]:
    current = payload.get("current") if isinstance(payload, dict) else None
    if not isinstance(current, dict):
        raise ValueError("open meteo response did not include current weather")
    observed = {
        "windSpeedMps": current.get("wind_speed_10m"),
        "windDirectionDeg": current.get("wind_direction_10m"),
        "temperatureC": current.get("temperature_2m"),
        "precipitationMm": current.get("precipitation"),
    }
    return observed, str(current.get("time") or "")


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
        payload = (transport or _default_open_meteo_transport)(_open_meteo_url(latitude, longitude, captured_at))
        if captured_at:
            observed, observed_time = _observed_from_hourly(payload, captured_at)
        else:
            observed, observed_time = _observed_from_current(payload)
        return build_weather_snapshot(
            round_id=round_id,
            hole=hole,
            captured_at=observed_time,
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


def weather_snapshot_for_time(
    round_id: str,
    hole: int | None = None,
    captured_at: str | None = None,
    *,
    root: Path | str | None = None,
) -> dict[str, Any] | None:
    target_time = _parse_iso_datetime(captured_at)
    if target_time is None:
        return latest_weather_snapshot(round_id, hole, root=root)
    matches = [
        row
        for row in list_weather_snapshots(root=root)
        if str(row.get("roundId")) == str(round_id) and (hole is None or row.get("hole") == hole)
    ]
    timed_matches = [(snapshot_time, row) for row in matches if (snapshot_time := _parse_iso_datetime(row.get("capturedAt"))) is not None]
    if not timed_matches:
        return latest_weather_snapshot(round_id, hole, root=root)
    at_or_before = [(snapshot_time, row) for snapshot_time, row in timed_matches if snapshot_time <= target_time]
    if at_or_before:
        return max(at_or_before, key=lambda item: item[0])[1]
    return min(timed_matches, key=lambda item: item[0])[1]
