from __future__ import annotations

import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from ai_caddie.config import get_settings
from server_v2.main import app


class ServerV2SettingsTests(unittest.TestCase):
    def tearDown(self) -> None:
        get_settings.cache_clear()

    def test_product_settings_endpoint_reports_secret_free_capabilities(self) -> None:
        client = TestClient(app)

        with patch.dict(
            "os.environ",
            {
                "AI_CADDIE_LLM_PROVIDER": "gemini_api_key",
                "GEMINI_API_KEY": "secret-key",
                "GEMINI_OAUTH_CREDENTIALS_FILE": "/tmp/gemini-oauth.json",
                "GOOGLE_CLOUD_PROJECT": "gemini-project",
            },
        ):
            get_settings.cache_clear()
            response = client.get("/api/v2/settings/product")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["schema"], "ai-caddie-product-settings-v1")
        data_sources = {row["id"]: row for row in payload["dataSources"]}
        self.assertEqual(data_sources["garmin_cn_web_session"]["track"], "primary")
        self.assertEqual(data_sources["garmin_cn_web_session"]["credentialPolicy"], "session_material_only")
        self.assertEqual(data_sources["garmin_oauth"]["track"], "feasibility")
        self.assertEqual(data_sources["garmin_oauth"]["state"], "not_syncable")
        self.assertEqual(data_sources["garmin_oauth"]["probe"]["schema"], "ai-caddie-garmin-oauth-probe-v2")
        self.assertEqual(data_sources["garmin_oauth"]["probe"]["state"], "not_configured")
        self.assertIn("client_id", data_sources["garmin_oauth"]["probe"]["missing"])
        self.assertIn("Can official OAuth access golf scorecards?", data_sources["garmin_oauth"]["feasibilityQuestions"])
        oauth_capabilities = {row["key"]: row for row in data_sources["garmin_oauth"]["capabilityMatrix"]}
        self.assertEqual(oauth_capabilities["scorecards"]["state"], "unproven")
        self.assertFalse(oauth_capabilities["scorecards"]["canReplaceCnConnector"])
        self.assertIn("scorecards", data_sources["garmin_cn_web_session"]["capabilities"])

        self.assertEqual(payload["aiProviders"]["activeProvider"], "gemini_api_key")
        providers = {row["id"]: row for row in payload["aiProviders"]["providers"]}
        self.assertEqual(providers["gemini_api_key"]["state"], "configured")
        self.assertEqual(providers["gemini_cli_oauth"]["state"], "configured")
        self.assertEqual(providers["gemini_cli_oauth"]["credentialPolicy"], "oauth_token_cache_with_refresh_client_credential")
        self.assertTrue(providers["gemini_cli_oauth"]["refreshRequiresClientCredential"])
        self.assertEqual(providers["gemini_cli_oauth"]["productionUse"], "internal_only")
        self.assertEqual(providers["static"]["state"], "ready")
        self.assertTrue(payload["aiProviders"]["factBindingRequired"])

        self.assertTrue(payload["liveApps"]["ios"]["offlineFirst"])
        self.assertEqual(
            payload["liveApps"]["ios"]["captures"],
            ["gps", "score", "club", "putt", "penalty", "note", "photo", "video"],
        )
        self.assertTrue(payload["liveApps"]["watch"]["requiresIphoneBridge"])
        self.assertEqual(payload["liveApps"]["watch"]["inputs"], ["club", "distance", "score", "putt", "penalty"])
        self.assertTrue(payload["privacy"]["noGarminPasswordStorage"])
        self.assertTrue(payload["privacy"]["adminProtectedWrites"])
        self.assertEqual(payload["endpoints"]["syncStatus"], "/api/v2/sync/status")
        self.assertNotIn("secret-key", response.text)
        self.assertNotIn("client_secret", response.text.lower())
        self.assertNotIn("cookie", response.text.lower())
        self.assertNotIn("csrf", response.text.lower())


if __name__ == "__main__":
    unittest.main()
