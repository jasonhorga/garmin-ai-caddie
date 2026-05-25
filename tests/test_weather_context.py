from __future__ import annotations

import unittest

from ai_caddie.weather_context import build_weather_snapshot


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


if __name__ == "__main__":
    unittest.main()
