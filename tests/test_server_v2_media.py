from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from ai_caddie.llm_providers import StaticProvider
from server_v2.main import app


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


if __name__ == "__main__":
    unittest.main()
