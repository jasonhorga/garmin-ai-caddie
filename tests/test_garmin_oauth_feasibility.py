from __future__ import annotations

import unittest

from ai_caddie.connectors.garmin_oauth import (
    build_oauth_feasibility_status,
    build_oauth_probe_status,
    build_pkce_authorization_url,
    run_oauth_live_probe,
)


class FakeOauthHttpClient:
    def __init__(self) -> None:
        self.posted: list[tuple[str, dict[str, str]]] = []
        self.gets: list[str] = []

    def post_form(self, url: str, data: dict[str, str], *, timeout_s: float):
        self.posted.append((url, data))
        return 200, {
            "access_token": "live-access-token",
            "refresh_token": "live-refresh-token",
            "expires_in": 3600,
            "refresh_token_expires_in": 7200,
        }

    def get_json(self, url: str, access_token: str, *, timeout_s: float):
        self.gets.append(url)
        self.seen_token = access_token
        if url.endswith("/user/id"):
            return 200, {"userId": "garmin-user-123"}
        if url.endswith("/user/permissions"):
            return 200, {"permissions": ["ACTIVITY_EXPORT", "COURSE_IMPORT"]}
        return 404, {"message": "not found"}


class GarminOauthFeasibilityTests(unittest.TestCase):
    def test_oauth_feasibility_status_is_secret_free_and_not_syncable(self) -> None:
        status = build_oauth_feasibility_status()

        self.assertEqual(status["name"], "garmin_oauth_feasibility")
        self.assertEqual(status["state"], "not_available")
        self.assertFalse(status["canSync"])
        self.assertFalse(status["reauthRequired"])
        self.assertEqual(status["track"], "official_oauth")
        self.assertIn("高尔夫记分卡", " ".join(status["feasibilityQuestions"]))
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
            self.assertIn(
                row["state"],
                ["unproven", "not_available", "possible", "proven", "needs_golf_fit_validation", "not_replacement"],
            )
            self.assertNotIn("client_secret", str(row).lower())
            self.assertNotIn("access_token", str(row).lower())

    def test_oauth_probe_status_reports_missing_configuration_without_live_calls(self) -> None:
        probe = build_oauth_probe_status(env={})

        self.assertEqual(probe["schema"], "ai-caddie-garmin-oauth-probe-v2")
        self.assertEqual(probe["state"], "not_configured")
        self.assertFalse(probe["liveProbeAllowed"])
        self.assertEqual(probe["missing"], ["client_id", "redirect_uri"])
        self.assertFalse(probe["configured"]["clientId"])
        self.assertTrue(probe["configured"]["consentEndpoint"])
        self.assertTrue(probe["configured"]["exchangeEndpoint"])
        self.assertIn("client_credential", probe["tokenExchange"]["missing"])
        self.assertIn("authorization_code", probe["tokenExchange"]["missing"])
        self.assertIn("code_challenge_method=S256", probe["consentRequest"]["redactedPreview"])
        self.assertIn("Register a Garmin OAuth client", probe["manualSteps"][0])

    def test_oauth_probe_status_builds_secret_free_authorization_preview(self) -> None:
        env = {
            "AI_CADDIE_GARMIN_OAUTH_CLIENT_ID": "client-public-id",
            "AI_CADDIE_GARMIN_OAUTH_CLIENT_SECRET": "super-secret-client-secret",
            "AI_CADDIE_GARMIN_OAUTH_REDIRECT_URI": "https://example.test/oauth/callback",
            "AI_CADDIE_GARMIN_OAUTH_AUTH_URL": "https://garmin.example/oauth/authorize",
            "AI_CADDIE_GARMIN_OAUTH_TOKEN_URL": "https://garmin.example/oauth/token",
            "AI_CADDIE_GARMIN_OAUTH_SCOPES": "profile golf.scorecards golf.shots",
            "AI_CADDIE_GARMIN_OAUTH_CODE": "one-time-code",
            "AI_CADDIE_GARMIN_OAUTH_CODE_VERIFIER": "private-code-verifier",
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
            ["response_type", "client_id", "redirect_uri", "state", "code_challenge", "code_challenge_method"],
        )
        self.assertTrue(probe["tokenExchange"]["ready"])
        self.assertIn("client_id=<configured>", probe["consentRequest"]["redactedPreview"])
        self.assertIn("redirect_uri=<configured>", probe["consentRequest"]["redactedPreview"])
        self.assertIn("code_challenge=<generated>", probe["consentRequest"]["redactedPreview"])
        self.assertNotIn("super-secret-client-secret", rendered)
        self.assertNotIn("client-public-id", rendered)
        self.assertNotIn("one-time-code", rendered)
        self.assertNotIn("private-code-verifier", rendered)
        self.assertNotIn("client_secret", rendered.lower())
        self.assertNotIn("access_token", rendered.lower())

    def test_oauth_feasibility_status_embeds_probe_without_secret_values(self) -> None:
        status = build_oauth_feasibility_status(
            env={
                "AI_CADDIE_GARMIN_OAUTH_CLIENT_ID": "client-public-id",
                "AI_CADDIE_GARMIN_OAUTH_CLIENT_SECRET": "super-secret-client-secret",
            }
        )

        self.assertIn("probe", status)
        self.assertEqual(status["probe"]["schema"], "ai-caddie-garmin-oauth-probe-v2")
        self.assertTrue(status["probe"]["configured"]["clientId"])
        self.assertTrue(status["probe"]["configured"]["clientCredential"])
        self.assertNotIn("super-secret-client-secret", str(status))
        self.assertNotIn("client-public-id", str(status))

    def test_pkce_authorization_url_uses_s256_and_keeps_secret_out_of_status(self) -> None:
        session = build_pkce_authorization_url(
            env={
                "AI_CADDIE_GARMIN_OAUTH_CLIENT_ID": "client-public-id",
                "AI_CADDIE_GARMIN_OAUTH_REDIRECT_URI": "https://example.test/oauth/callback",
            },
            state="fixed-state",
            code_verifier="abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789",
        )

        self.assertIn("https://connect.garmin.com/oauth2Confirm?", session["authorizationUrl"])
        self.assertIn("client_id=client-public-id", session["authorizationUrl"])
        self.assertIn("state=fixed-state", session["authorizationUrl"])
        self.assertIn("code_challenge_method=S256", session["authorizationUrl"])
        self.assertEqual(session["codeVerifier"], "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789")
        self.assertEqual(session["codeChallengeMethod"], "S256")

    def test_live_probe_is_disabled_until_explicitly_allowed(self) -> None:
        probe = run_oauth_live_probe(env={})

        self.assertEqual(probe["schema"], "ai-caddie-garmin-oauth-live-probe-v1")
        self.assertEqual(probe["state"], "disabled")
        self.assertIn("AI_CADDIE_GARMIN_OAUTH_LIVE_PROBE=1", probe["detail"])

    def test_live_probe_exchanges_code_and_checks_user_permissions_without_leaking_secrets(self) -> None:
        env = {
            "AI_CADDIE_GARMIN_OAUTH_CLIENT_ID": "client-public-id",
            "AI_CADDIE_GARMIN_OAUTH_CLIENT_SECRET": "super-secret-client-secret",
            "AI_CADDIE_GARMIN_OAUTH_REDIRECT_URI": "https://example.test/oauth/callback",
            "AI_CADDIE_GARMIN_OAUTH_CODE": "one-time-code",
            "AI_CADDIE_GARMIN_OAUTH_CODE_VERIFIER": "private-code-verifier",
            "AI_CADDIE_GARMIN_OAUTH_LIVE_PROBE": "1",
        }
        fake = FakeOauthHttpClient()

        result = run_oauth_live_probe(env=env, http_client=fake, now_s=1000)
        rendered = str(result)

        self.assertEqual(result["state"], "completed")
        self.assertEqual(fake.posted[0][0], "https://connectapi.garmin.com/di-oauth2-service/oauth/token")
        self.assertEqual(fake.posted[0][1]["client_secret"], "super-secret-client-secret")
        self.assertEqual(fake.posted[0][1]["code"], "one-time-code")
        self.assertEqual(fake.seen_token, "live-access-token")
        self.assertEqual(result["tokenExchange"]["expiresAt"], 4600)
        self.assertEqual(result["tokenExchange"]["refreshExpiresAt"], 8200)
        self.assertTrue(result["resourceProbe"]["userId"]["idReceived"])
        self.assertEqual(result["resourceProbe"]["permissions"]["permissions"], ["ACTIVITY_EXPORT", "COURSE_IMPORT"])
        capabilities = {row["key"]: row for row in result["capabilities"]}
        self.assertEqual(capabilities["identity"]["state"], "proven")
        self.assertEqual(capabilities["fit_golf_activity"]["state"], "needs_golf_fit_validation")
        self.assertEqual(capabilities["course_metadata"]["state"], "not_replacement")
        self.assertFalse(result["summary"]["canReplaceCnConnector"])
        self.assertFalse(result["summary"]["scorecardsProven"])
        self.assertNotIn("super-secret-client-secret", rendered)
        self.assertNotIn("one-time-code", rendered)
        self.assertNotIn("private-code-verifier", rendered)
        self.assertNotIn("live-access-token", rendered)
        self.assertNotIn("live-refresh-token", rendered)
        self.assertNotIn("garmin-user-123", rendered)
        self.assertNotIn("client_secret", rendered.lower())
        self.assertNotIn("access_token", rendered.lower())


if __name__ == "__main__":
    unittest.main()
