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

    def test_oauth_feasibility_exposes_capability_matrix(self) -> None:
        status = build_oauth_feasibility_status()

        capabilities = {row["key"]: row for row in status["capabilities"]}

        self.assertEqual(
            sorted(capabilities),
            ["course_metadata", "fit_golf_activity", "golf_shots", "identity", "scorecards"],
        )
        self.assertEqual(capabilities["scorecards"]["label"], "Golf scorecards")
        self.assertEqual(capabilities["scorecards"]["state"], "unproven")
        self.assertFalse(capabilities["scorecards"]["canReplaceCnConnector"])
        self.assertIn("OAuth", capabilities["scorecards"]["evidence"])
        self.assertIn("scorecard", capabilities["scorecards"]["nextStep"].lower())
        self.assertEqual(capabilities["identity"]["state"], "possible")
        self.assertTrue(capabilities["identity"]["migrationValue"])
        for row in capabilities.values():
            self.assertIn(row["state"], ["unproven", "not_available", "possible"])
            self.assertNotIn("client_secret", str(row).lower())
            self.assertNotIn("access_token", str(row).lower())


if __name__ == "__main__":
    unittest.main()
