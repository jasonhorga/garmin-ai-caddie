from __future__ import annotations

import json
import unittest

from ai_caddie.llm_providers import StaticProvider
from ai_caddie.vision_context import ALLOWED_FINDING_TYPES, analyze_media_context


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


if __name__ == "__main__":
    unittest.main()
