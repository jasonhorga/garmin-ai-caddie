from __future__ import annotations

import base64
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from ai_caddie.llm_providers import StaticProvider
from server_v2.main import app


ADMIN_ENV = {"AI_CADDIE_ADMIN_TOKEN": "admin-secret"}
ADMIN_HEADER = {"X-AI-Caddie-Admin-Token": "admin-secret"}


class ServerV2MediaTests(unittest.TestCase):
    def test_media_create_list_and_analyze_do_not_expose_private_paths(self) -> None:
        client = TestClient(app)

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            image = root / "uploads" / "shot.jpg"
            image.parent.mkdir()
            image.write_bytes(b"fake image bytes")
            with patch("server_v2.media.MEDIA_ROOT", root):
                create_response = client.post(
                    "/api/v2/media",
                    json={
                        "targetType": "shot",
                        "targetId": "round-1:7:2",
                        "mediaKind": "photo",
                        "localPath": str(image),
                        "capturedAt": "2026-05-25T00:00:00Z",
                        "privacyState": "private_local",
                    },
                )
                media_id = create_response.json()["media"]["id"]
                list_response = client.get("/api/v2/media/target/shot/round-1:7:2")
                with patch(
                    "server_v2.media.build_media_vision_provider",
                    return_value=StaticProvider(
                        '[{"findingType":"visible_bunker","evidenceText":"front bunker visible","confidence":"medium","missingInfo":[]}]'
                    ),
                ):
                    analyze_response = client.post(f"/api/v2/media/{media_id}/analyze")
                findings_response = client.get("/api/v2/media/target/shot/round-1:7:2/findings")

        self.assertEqual(create_response.status_code, 200)
        self.assertEqual(create_response.json()["schema"], "ai-caddie-media-create-v1")
        self.assertEqual(create_response.json()["media"]["localPath"], "uploads/shot.jpg")
        self.assertNotIn(tmp, create_response.text)

        self.assertEqual(list_response.status_code, 200)
        self.assertEqual(list_response.json()["schema"], "ai-caddie-media-list-v1")
        self.assertEqual(list_response.json()["total"], 1)
        self.assertNotIn(tmp, list_response.text)

        self.assertEqual(analyze_response.status_code, 200)
        self.assertEqual(analyze_response.json()["schema"], "ai-caddie-vision-context-v1")
        self.assertEqual(analyze_response.json()["findings"][0]["findingType"], "visible_bunker")
        self.assertNotIn(tmp, analyze_response.text)

        self.assertEqual(findings_response.status_code, 200)
        self.assertEqual(findings_response.json()["schema"], "ai-caddie-vision-findings-list-v1")
        self.assertEqual(findings_response.json()["total"], 1)
        finding = findings_response.json()["findings"][0]
        self.assertEqual(finding["mediaId"], media_id)
        self.assertEqual(finding["targetType"], "shot")
        self.assertEqual(finding["targetId"], "round-1:7:2")
        self.assertEqual(finding["findingType"], "visible_bunker")
        self.assertEqual(finding["confidence"], "medium")
        self.assertNotIn("localPath", finding)
        self.assertNotIn("mediaBytesBase64", findings_response.text)
        self.assertNotIn("fake image bytes", findings_response.text)
        self.assertNotIn(tmp, findings_response.text)

    def test_media_create_rejects_invalid_kind(self) -> None:
        client = TestClient(app)

        response = client.post(
            "/api/v2/media",
            json={
                "targetType": "shot",
                "targetId": "round-1:7:2",
                "mediaKind": "audio",
                "localPath": "uploads/voice.m4a",
                "capturedAt": "2026-05-25T00:00:00Z",
            },
        )

        self.assertEqual(response.status_code, 422)

    def test_media_create_can_store_uploaded_content_without_jsonl_bytes(self) -> None:
        client = TestClient(app)

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch("server_v2.media.MEDIA_ROOT", root):
                response = client.post(
                    "/api/v2/media",
                    json={
                        "targetType": "shot",
                        "targetId": "round-1:7:2",
                        "mediaKind": "photo",
                        "fileName": "lie.jpg",
                        "contentBase64": base64.b64encode(b"uploaded-bytes").decode("ascii"),
                        "capturedAt": "2026-05-25T00:00:00Z",
                    },
                )
                local_path = response.json()["media"]["localPath"]
                stored = root / local_path
                stored_bytes = stored.read_bytes()
                index_text = (root / "data" / "media" / "media_index.jsonl").read_text(encoding="utf-8")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(stored_bytes, b"uploaded-bytes")
        self.assertNotIn("uploaded-bytes", index_text)
        self.assertTrue(local_path.startswith("data/media/uploads/"))

    def test_media_redact_requires_admin_removes_bytes_and_returns_latest_redacted_metadata(self) -> None:
        client = TestClient(app)

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch("server_v2.media.MEDIA_ROOT", root):
                create_response = client.post(
                    "/api/v2/media",
                    json={
                        "targetType": "shot",
                        "targetId": "round-1:7:2",
                        "mediaKind": "photo",
                        "fileName": "lie.jpg",
                        "contentBase64": base64.b64encode(b"private-lie-bytes").decode("ascii"),
                        "capturedAt": "2026-05-25T00:00:00Z",
                    },
                )
                media_id = create_response.json()["media"]["id"]
                local_path = create_response.json()["media"]["localPath"]
                stored = root / local_path
                existed_before_redact = stored.exists()

                with patch.dict("os.environ", ADMIN_ENV):
                    unauthorized = client.post(f"/api/v2/media/{media_id}/redact")
                    redact_response = client.post(f"/api/v2/media/{media_id}/redact", headers=ADMIN_HEADER)
                    list_response = client.get("/api/v2/media/target/shot/round-1:7:2", headers=ADMIN_HEADER)
                    analyze_after_redact = client.post(f"/api/v2/media/{media_id}/analyze", headers=ADMIN_HEADER)

        self.assertEqual(create_response.status_code, 200)
        self.assertTrue(existed_before_redact)
        self.assertEqual(unauthorized.status_code, 401)
        self.assertEqual(redact_response.status_code, 200)
        self.assertEqual(redact_response.json()["schema"], "ai-caddie-media-redact-v1")
        self.assertTrue(redact_response.json()["deletedContent"])
        self.assertEqual(redact_response.json()["media"]["id"], media_id)
        self.assertEqual(redact_response.json()["media"]["privacyState"], "redacted")
        self.assertEqual(redact_response.json()["media"]["localPath"], "[redacted]")
        self.assertFalse(stored.exists())
        self.assertNotIn(tmp, redact_response.text + list_response.text)
        self.assertNotIn(local_path, redact_response.text + list_response.text)

        self.assertEqual(list_response.status_code, 200)
        self.assertEqual(list_response.json()["total"], 1)
        self.assertEqual(list_response.json()["media"][0]["id"], media_id)
        self.assertEqual(list_response.json()["media"][0]["privacyState"], "redacted")
        self.assertEqual(list_response.json()["media"][0]["localPath"], "[redacted]")

        self.assertEqual(analyze_after_redact.status_code, 200)
        self.assertEqual(analyze_after_redact.json()["findings"][0]["findingType"], "uncertainty")
        self.assertIn("redacted", analyze_after_redact.json()["findings"][0]["missingInfo"][0])
        self.assertNotIn(tmp, analyze_after_redact.text)
        self.assertNotIn(local_path, analyze_after_redact.text)


if __name__ == "__main__":
    unittest.main()
