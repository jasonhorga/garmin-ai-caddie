from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from urllib.parse import parse_qs, urlparse

import ai_caddie.llm.weather_context as weather_context
from ai_caddie.llm.weather_context import (
    build_weather_snapshot,
    weather_condition,
    fetch_open_meteo_weather_snapshot,
    latest_weather_snapshot,
    list_weather_snapshots,
    store_weather_snapshot,
)


class WeatherContextTests(unittest.TestCase):
    def test_missing_weather_snapshot_exposes_missing_location_and_time(self) -> None:
        snapshot = build_weather_snapshot(round_id="round-1", hole=7)

        self.assertEqual(snapshot["schema"], "ai-caddie-weather-snapshot-v1")
        self.assertEqual(snapshot["state"], "missing")
        self.assertEqual(snapshot["confidence"], "low")
        self.assertEqual(snapshot["source"], "missing")
        self.assertEqual({row["label"] for row in snapshot["missingData"]}, {"location", "captured_at", "weather_values"})

    def test_manual_weather_snapshot_is_ready_and_structured(self) -> None:
        snapshot = build_weather_snapshot(
            round_id="round-1",
            hole=7,
            captured_at="2026-05-25T08:00:00Z",
            latitude=22.279,
            longitude=114.162,
            source="manual",
            observed={
                "windSpeedMps": 5.4,
                "windDirectionDeg": 110,
                "temperatureC": 28.5,
                "precipitationMm": 0.0,
            },
        )

        self.assertEqual(snapshot["state"], "ready")
        self.assertEqual(snapshot["confidence"], "medium")
        self.assertEqual(snapshot["location"], {"latitude": 22.279, "longitude": 114.162})
        self.assertEqual(snapshot["windSpeedMps"], 5.4)
        self.assertEqual(snapshot["windDirectionDeg"], 110)
        self.assertEqual(snapshot["missingData"], [])

    def test_open_meteo_provider_maps_current_response_without_key(self) -> None:
        captured_urls: list[str] = []

        def fake_transport(url: str) -> dict[str, object]:
            captured_urls.append(url)
            parsed = urlparse(url)
            params = parse_qs(parsed.query)
            self.assertEqual(parsed.netloc, "api.open-meteo.com")
            self.assertEqual(params["latitude"], ["22.279"])
            self.assertEqual(params["longitude"], ["114.162"])
            self.assertEqual(params["wind_speed_unit"], ["ms"])
            self.assertIn("temperature_2m", params["current"][0])
            self.assertIn("wind_speed_10m", params["current"][0])
            return {
                "current": {
                    "time": "2026-05-25T08:00",
                    "temperature_2m": 28.5,
                    "wind_speed_10m": 5.4,
                    "wind_direction_10m": 110,
                    "precipitation": 0.2,
                }
            }

        snapshot = fetch_open_meteo_weather_snapshot(
            round_id="round-1",
            hole=7,
            latitude=22.279,
            longitude=114.162,
            transport=fake_transport,
        )

        self.assertEqual(len(captured_urls), 1)
        self.assertEqual(snapshot["state"], "ready")
        self.assertEqual(snapshot["source"], "open_meteo")
        self.assertEqual(snapshot["capturedAt"], "2026-05-25T08:00:00Z")
        self.assertEqual(snapshot["windSpeedMps"], 5.4)
        self.assertEqual(snapshot["windDirectionDeg"], 110)
        self.assertEqual(snapshot["temperatureC"], 28.5)
        self.assertEqual(snapshot["precipitationMm"], 0.2)
        self.assertEqual(snapshot["confidence"], "high")

    def test_open_meteo_reports_the_condition_and_rain_chance_for_the_home_tile(self) -> None:
        def fake_transport(url: str) -> dict[str, object]:
            params = parse_qs(urlparse(url).query)
            self.assertIn("weather_code", params["current"][0])
            self.assertIn("precipitation_probability", params["current"][0])
            return {
                "current": {
                    "time": "2026-10-04T08:00",
                    "temperature_2m": 19.0,
                    "wind_speed_10m": 5.0,
                    "wind_direction_10m": 90,
                    "precipitation": 0.4,
                    "weather_code": 61,
                    "precipitation_probability": 70,
                }
            }

        snapshot = fetch_open_meteo_weather_snapshot(latitude=40.0, longitude=116.5, transport=fake_transport)
        self.assertEqual(snapshot["weatherCode"], 61)
        self.assertEqual(snapshot["condition"], "rain")
        self.assertEqual(snapshot["precipitationProbabilityPct"], 70)

    def test_unknown_codes_and_bad_rain_chances_are_dropped_not_guessed(self) -> None:
        self.assertEqual(
            [weather_condition(code) for code in (0, 2, 3, 45, 53, 81, 75, 95)],
            ["clear", "partly_cloudy", "overcast", "fog", "drizzle", "rain", "snow", "thunderstorm"],
        )
        self.assertIsNone(weather_condition(42))
        self.assertIsNone(weather_condition(None))
        snapshot = build_weather_snapshot(
            captured_at="2026-10-04T08:00:00Z", latitude=40.0, longitude=116.5, source="manual",
            observed={"temperatureC": 20.0, "weatherCode": 42, "precipitationProbabilityPct": 140},
        )
        self.assertIsNone(snapshot["weatherCode"])
        self.assertIsNone(snapshot["condition"])
        self.assertIsNone(snapshot["precipitationProbabilityPct"])

    def test_open_meteo_provider_selects_hourly_weather_for_requested_round_time(self) -> None:
        captured_urls: list[str] = []

        def fake_transport(url: str) -> dict[str, object]:
            captured_urls.append(url)
            parsed = urlparse(url)
            params = parse_qs(parsed.query)
            self.assertIn("temperature_2m", params["hourly"][0])
            self.assertIn("wind_speed_10m", params["hourly"][0])
            self.assertEqual(params["start_date"], ["2026-05-25"])
            self.assertEqual(params["end_date"], ["2026-05-25"])
            self.assertNotIn("current", params)
            return {
                "hourly": {
                    "time": ["2026-05-25T08:00", "2026-05-25T09:00", "2026-05-25T10:00"],
                    "temperature_2m": [27.1, 29.2, 30.4],
                    "wind_speed_10m": [3.1, 6.2, 4.4],
                    "wind_direction_10m": [80, 125, 150],
                    "precipitation": [0.0, 0.7, 0.1],
                }
            }

        snapshot = fetch_open_meteo_weather_snapshot(
            round_id="round-1",
            hole=7,
            captured_at="2026-05-25T09:18:00Z",
            latitude=22.279,
            longitude=114.162,
            transport=fake_transport,
        )

        self.assertEqual(len(captured_urls), 1)
        self.assertEqual(snapshot["state"], "ready")
        self.assertEqual(snapshot["capturedAt"], "2026-05-25T09:00:00Z")
        self.assertEqual(snapshot["windSpeedMps"], 6.2)
        self.assertEqual(snapshot["windDirectionDeg"], 125)
        self.assertEqual(snapshot["temperatureC"], 29.2)
        self.assertEqual(snapshot["precipitationMm"], 0.7)

    def test_open_meteo_provider_degrades_without_network_or_values(self) -> None:
        def failing_transport(_url: str) -> dict[str, object]:
            raise TimeoutError("provider timed out")

        snapshot = fetch_open_meteo_weather_snapshot(
            round_id="round-1",
            hole=7,
            captured_at="2026-05-25T08:00:00Z",
            latitude=22.279,
            longitude=114.162,
            transport=failing_transport,
        )

        self.assertEqual(snapshot["state"], "missing")
        self.assertEqual(snapshot["source"], "missing")
        self.assertIn("weather_provider", {row["label"] for row in snapshot["missingData"]})

    def test_open_meteo_provider_redacts_secret_and_private_path_exception_text(self) -> None:
        def failing_transport(_url: str) -> dict[str, object]:
            raise RuntimeError(
                "failed token=abc123 cookie=session-value authorization Bearer abc "
                "file:///private/var/mobile/tmp/weather.json /home/ubuntu/.env "
                "/Users/player/secret.txt C:\\Users\\player\\secret.txt"
            )

        snapshot = fetch_open_meteo_weather_snapshot(
            round_id="round-1",
            hole=7,
            captured_at="2026-05-25T08:00:00Z",
            latitude=22.279,
            longitude=114.162,
            transport=failing_transport,
        )

        reason = " ".join(str(row.get("reason", "")) for row in snapshot["missingData"])
        for private_fragment in [
            "abc123",
            "session-value",
            "Bearer abc",
            "file://",
            "/private/var",
            "/home/ubuntu",
            "/Users/player",
            "C:\\Users\\player",
            "weather.json",
            "secret.txt",
        ]:
            self.assertNotIn(private_fragment, reason)
        self.assertIn("[REDACTED]", reason)
        self.assertIn("[REDACTED_PATH]", reason)

    def test_weather_snapshot_store_round_trips_and_finds_latest(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            first = build_weather_snapshot(
                round_id="round-1",
                hole=7,
                captured_at="2026-05-25T08:00:00Z",
                latitude=22.279,
                longitude=114.162,
                source="manual",
                observed={"windSpeedMps": 4.0},
            )
            second = build_weather_snapshot(
                round_id="round-1",
                hole=7,
                captured_at="2026-05-25T09:00:00Z",
                latitude=22.279,
                longitude=114.162,
                source="manual",
                observed={"windSpeedMps": 6.0},
            )

            store_weather_snapshot(first, root=root)
            store_weather_snapshot(second, root=root)

            snapshots = list_weather_snapshots(root=root)
            latest = latest_weather_snapshot("round-1", 7, root=root)

        self.assertEqual(len(snapshots), 2)
        self.assertEqual(latest["capturedAt"], "2026-05-25T09:00:00Z")
        self.assertEqual(latest["windSpeedMps"], 6.0)

    def test_weather_snapshot_for_time_prefers_latest_at_or_before_decision_time(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            for captured_at, wind_speed in [
                ("2026-05-25T08:00:00Z", 4.0),
                ("2026-05-25T09:00:00Z", 6.0),
                ("2026-05-25T15:00:00Z", 12.0),
            ]:
                store_weather_snapshot(
                    build_weather_snapshot(
                        round_id="round-1",
                        hole=7,
                        captured_at=captured_at,
                        latitude=22.279,
                        longitude=114.162,
                        source="manual",
                        observed={"windSpeedMps": wind_speed},
                    ),
                    root=root,
                )

            selector = getattr(weather_context, "weather_snapshot_for_time", None)
            self.assertIsNotNone(selector)
            selected = selector("round-1", 7, "2026-05-25T09:15:00Z", root=root)
            before_first = selector("round-1", 7, "2026-05-25T07:30:00Z", root=root)
            without_decision_time = selector("round-1", 7, root=root)

        self.assertEqual(selected["capturedAt"], "2026-05-25T09:00:00Z")
        self.assertEqual(selected["windSpeedMps"], 6.0)
        self.assertEqual(before_first["capturedAt"], "2026-05-25T08:00:00Z")
        self.assertEqual(without_decision_time["capturedAt"], "2026-05-25T15:00:00Z")


if __name__ == "__main__":
    unittest.main()
