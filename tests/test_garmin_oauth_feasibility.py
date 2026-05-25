from __future__ import annotations

import unittest

from ai_caddie.connectors.garmin_oauth import build_oauth_feasibility_status


class GarminOauthFeasibilityTests(unittest.TestCase):
    def test_oauth_feasibility_status_is_secret_free_and_not_syncable(self) -> None:
        status = build_oauth_feasibility_status()

        self.assertEqual(status["name"], "garmin_oauth_feasibility")
        self.assertEqual(status["state"], "not_available")
        self.assertFalse(status["canSync"])
        self.assertFalse(status["reauthRequired"])
        self.assertEqual(status["track"], "official_oauth")
        self.assertIn("golf scorecards", " ".join(status["feasibilityQuestions"]))
        self.assertNotIn("client_secret", str(status).lower())
        self.assertNotIn("access_token", str(status).lower())


if __name__ == "__main__":
    unittest.main()
