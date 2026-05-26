from __future__ import annotations

import unittest

from ai_caddie.connectors.garmin_oauth import build_oauth_feasibility_status, build_oauth_probe_status


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

    def test_oauth_probe_status_reports_missing_configuration_without_live_calls(self) -> None:
        probe = build_oauth_probe_status(env={})

        self.assertEqual(probe["schema"], "ai-caddie-garmin-oauth-probe-v1")
        self.assertEqual(probe["state"], "not_configured")
        self.assertFalse(probe["liveProbeAllowed"])
        self.assertEqual(
            probe["missing"],
            ["client_id", "redirect_uri", "consent_endpoint", "exchange_endpoint", "scopes"],
        )
        self.assertFalse(probe["configured"]["clientId"])
        self.assertFalse(probe["configured"]["clientCredential"])
        self.assertEqual(probe["consentRequest"]["redactedPreview"], None)
        self.assertIn("Register a Garmin OAuth client", probe["manualSteps"][0])

    def test_oauth_probe_status_builds_secret_free_authorization_preview(self) -> None:
        env = {
            "AI_CADDIE_GARMIN_OAUTH_CLIENT_ID": "client-public-id",
            "AI_CADDIE_GARMIN_OAUTH_CLIENT_SECRET": "super-secret-client-secret",
            "AI_CADDIE_GARMIN_OAUTH_REDIRECT_URI": "https://example.test/oauth/callback",
            "AI_CADDIE_GARMIN_OAUTH_AUTH_URL": "https://garmin.example/oauth/authorize",
            "AI_CADDIE_GARMIN_OAUTH_TOKEN_URL": "https://garmin.example/oauth/token",
            "AI_CADDIE_GARMIN_OAUTH_SCOPES": "profile golf.scorecards golf.shots",
            "AI_CADDIE_GARMIN_OAUTH_LIVE_PROBE": "1",
        }

        probe = build_oauth_probe_status(env=env)
        rendered = str(probe)

        self.assertEqual(probe["state"], "ready_for_manual_consent")
        self.assertTrue(probe["liveProbeAllowed"])
        self.assertTrue(probe["configured"]["clientId"])
        self.assertTrue(probe["configured"]["clientCredential"])
        self.assertEqual(probe["missing"], [])
        self.assertEqual(
            probe["consentRequest"]["parameterKeys"],
            ["response_type", "client_id", "redirect_uri", "scope", "state"],
        )
        self.assertIn("client_id=<configured>", probe["consentRequest"]["redactedPreview"])
        self.assertIn("redirect_uri=<configured>", probe["consentRequest"]["redactedPreview"])
        self.assertIn("scope=<configured>", probe["consentRequest"]["redactedPreview"])
        self.assertNotIn("super-secret-client-secret", rendered)
        self.assertNotIn("client-public-id", rendered)
        self.assertNotIn("access_token", rendered.lower())

    def test_oauth_feasibility_status_embeds_probe_without_secret_values(self) -> None:
        status = build_oauth_feasibility_status(
            env={
                "AI_CADDIE_GARMIN_OAUTH_CLIENT_ID": "client-public-id",
                "AI_CADDIE_GARMIN_OAUTH_CLIENT_SECRET": "super-secret-client-secret",
            }
        )

        self.assertIn("probe", status)
        self.assertEqual(status["probe"]["schema"], "ai-caddie-garmin-oauth-probe-v1")
        self.assertTrue(status["probe"]["configured"]["clientId"])
        self.assertTrue(status["probe"]["configured"]["clientCredential"])
        self.assertNotIn("super-secret-client-secret", str(status))
        self.assertNotIn("client-public-id", str(status))


if __name__ == "__main__":
    unittest.main()
