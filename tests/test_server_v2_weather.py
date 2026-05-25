from __future__ import annotations

import unittest

from fastapi.testclient import TestClient

from server_v2.main import app


class ServerV2WeatherTests(unittest.TestCase):
    def test_weather_snapshot_endpoint_degrades_when_context_is_missing(self) -> None:
        response = TestClient(app).get("/api/v2/weather/snapshot?round_id=round-1&hole=7")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["schema"], "ai-caddie-weather-snapshot-v1")
        self.assertEqual(payload["state"], "missing")
        self.assertEqual(payload["confidence"], "low")
        self.assertIn("weather_values", {row["label"] for row in payload["missingData"]})

    def test_weather_snapshot_endpoint_accepts_manual_observed_values(self) -> None:
        response = TestClient(app).get(
            "/api/v2/weather/snapshot"
            "?round_id=round-1&hole=7&captured_at=2026-05-25T08:00:00Z"
            "&latitude=22.279&longitude=114.162&wind_speed_mps=5.4"
            "&wind_direction_deg=110&temperature_c=28.5&precipitation_mm=0"
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["state"], "ready")
        self.assertEqual(payload["source"], "manual")
        self.assertEqual(payload["windSpeedMps"], 5.4)
        self.assertNotIn("/home/", response.text)


if __name__ == "__main__":
    unittest.main()
