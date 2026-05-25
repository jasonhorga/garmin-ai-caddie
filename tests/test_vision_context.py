from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from ai_caddie.llm_providers import LLMMessage
from ai_caddie.llm_providers import StaticProvider
from ai_caddie.vision_context import (
    ALLOWED_FINDING_TYPES,
    analyze_media_context,
    list_findings_for_target,
    store_vision_findings,
    vision_findings_file,
)


class RecordingVisionProvider:
    model = "recording"

    def __init__(self) -> None:
        self.messages: list[LLMMessage] = []

    def chat(self, messages, max_tokens=None):
        self.messages = list(messages)
        return json.dumps(
            [
                {
                    "findingType": "visible_water",
                    "evidenceText": "blue hazard area visible",
                    "confidence": "medium",
                    "missingInfo": [],
                }
            ]
        )


class VisionContextTests(unittest.TestCase):
    def test_static_provider_returns_allowed_finding_contract(self) -> None:
        provider = StaticProvider(
            json.dumps(
                [
                    {
                        "findingType": "blocked_view",
                        "evidenceText": "tree line blocks direct target view",
                        "confidence": "high",
                        "missingInfo": ["exact target line"],
                    }
                ]
            )
        )
        media = {
            "id": "media-1",
            "targetType": "shot",
            "targetId": "round-1:7:2",
            "mediaKind": "photo",
            "localPath": "uploads/shot.jpg",
        }

        result = analyze_media_context(media, provider)

        self.assertEqual(result["schema"], "ai-caddie-vision-context-v1")
        self.assertEqual(result["mediaId"], "media-1")
        self.assertEqual(result["provider"], "static")
        self.assertEqual(result["model"], "static")
        self.assertEqual(result["findings"][0]["findingType"], "blocked_view")
        self.assertEqual(result["findings"][0]["confidence"], "high")
        self.assertEqual(result["findings"][0]["source"], "vision_model")
        self.assertIn(result["findings"][0]["findingType"], ALLOWED_FINDING_TYPES)

    def test_invalid_or_unparseable_provider_reply_degrades_to_uncertainty(self) -> None:
        result = analyze_media_context(
            {"id": "media-2", "mediaKind": "video", "localPath": "uploads/swing.mp4"},
            StaticProvider("not json"),
        )

        self.assertEqual(result["findings"][0]["findingType"], "uncertainty")
        self.assertEqual(result["findings"][0]["confidence"], "low")
        self.assertIn("provider response", result["findings"][0]["missingInfo"][0])

    def test_media_bytes_are_included_in_provider_payload(self) -> None:
        provider = RecordingVisionProvider()
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            image = root / "uploads" / "shot.jpg"
            image.parent.mkdir()
            image.write_bytes(b"image-bytes")
            result = analyze_media_context(
                {
                    "id": "media-3",
                    "targetType": "shot",
                    "targetId": "round-1:7:2",
                    "mediaKind": "photo",
                    "localPath": "uploads/shot.jpg",
                },
                provider,
                root=root,
            )

        prompt = provider.messages[-1].content
        self.assertEqual(result["findings"][0]["findingType"], "visible_water")
        self.assertIn("mediaBytesBase64=aW1hZ2UtYnl0ZXM=", prompt)
        self.assertIn("byteLength=11", prompt)

    def test_store_and_list_findings_for_target_without_secret_fields(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            analysis = {
                "schema": "ai-caddie-vision-context-v1",
                "mediaId": "media-3",
                "targetType": "shot",
                "targetId": "round-1:7:2",
                "mediaKind": "photo",
                "provider": "static",
                "model": "static",
                "findings": [
                    {
                        "findingType": "visible_water",
                        "evidenceText": (
                            "water visible near /home/player/private/shot.jpg "
                            "with authorization: Bearer secret-token"
                        ),
                        "confidence": "medium",
                        "missingInfo": ["/tmp/private-media/shot.jpg"],
                        "source": "vision_model",
                        "localPath": "/home/player/private/shot.jpg",
                        "mediaBytesBase64": "cHJpdmF0ZS1ieXRlcw==",
                    }
                ],
            }

            stored = store_vision_findings(analysis, root=root)
            listed = list_findings_for_target("shot", "round-1:7:2", root=root)
            raw_jsonl = vision_findings_file(root).read_text(encoding="utf-8")

        self.assertEqual(len(stored), 1)
        self.assertEqual(listed, stored)
        self.assertEqual(listed[0]["mediaId"], "media-3")
        self.assertEqual(listed[0]["targetType"], "shot")
        self.assertEqual(listed[0]["targetId"], "round-1:7:2")
        self.assertEqual(listed[0]["findingType"], "visible_water")
        self.assertEqual(listed[0]["confidence"], "medium")
        self.assertEqual(listed[0]["source"], "vision_model")
        self.assertNotIn("localPath", listed[0])
        self.assertNotIn("mediaBytesBase64", listed[0])
        self.assertNotIn("secret-token", raw_jsonl)
        self.assertNotIn("/home/player/private", raw_jsonl)
        self.assertNotIn("/tmp/private-media", raw_jsonl)
        self.assertNotIn("cHJpdmF0ZS1ieXRlcw==", raw_jsonl)


if __name__ == "__main__":
    unittest.main()
