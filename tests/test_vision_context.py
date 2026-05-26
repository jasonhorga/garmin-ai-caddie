from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from ai_caddie.llm_providers import LLMMediaPart, LLMMessage
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
        self.media_parts: list[LLMMediaPart] = []

    def chat(self, messages, max_tokens=None):
        raise AssertionError("vision analysis must use the multimodal provider path")

    def chat_multimodal(self, messages, media_parts, max_tokens=None):
        self.messages = list(messages)
        self.media_parts = list(media_parts)
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


class TextOnlyVisionProvider:
    model = "text-only"

    def __init__(self) -> None:
        self.called = False

    def chat(self, messages, max_tokens=None):
        self.called = True
        return json.dumps(
            [
                {
                    "findingType": "visible_water",
                    "evidenceText": "I cannot see pixels but will guess water",
                    "confidence": "high",
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

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            image = root / "uploads" / "shot.jpg"
            image.parent.mkdir()
            image.write_bytes(b"image-bytes")
            result = analyze_media_context(
                {
                    "id": "media-1",
                    "targetType": "shot",
                    "targetId": "round-1:7:2",
                    "mediaKind": "photo",
                    "localPath": "uploads/shot.jpg",
                },
                provider,
                root=root,
            )

        self.assertEqual(result["schema"], "ai-caddie-vision-context-v1")
        self.assertEqual(result["mediaId"], "media-1")
        self.assertEqual(result["provider"], "static")
        self.assertEqual(result["model"], "static")
        self.assertEqual(result["findings"][0]["findingType"], "blocked_view")
        self.assertEqual(result["findings"][0]["confidence"], "high")
        self.assertEqual(result["findings"][0]["source"], "vision_model")
        self.assertIn(result["findings"][0]["findingType"], ALLOWED_FINDING_TYPES)

    def test_invalid_or_unparseable_provider_reply_degrades_to_uncertainty(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            video = root / "uploads" / "swing.mp4"
            video.parent.mkdir()
            video.write_bytes(b"video-bytes")
            result = analyze_media_context(
                {"id": "media-2", "mediaKind": "video", "localPath": "uploads/swing.mp4"},
                StaticProvider("not json"),
                root=root,
            )

        self.assertEqual(result["findings"][0]["findingType"], "uncertainty")
        self.assertEqual(result["findings"][0]["confidence"], "low")
        self.assertIn("provider response", result["findings"][0]["missingInfo"][0])

    def test_text_only_provider_degrades_instead_of_guessing_visual_findings(self) -> None:
        provider = TextOnlyVisionProvider()
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            image = root / "uploads" / "shot.jpg"
            image.parent.mkdir()
            image.write_bytes(b"image-bytes")
            result = analyze_media_context(
                {
                    "id": "media-text-only",
                    "targetType": "shot",
                    "targetId": "round-1:7:2",
                    "mediaKind": "photo",
                    "localPath": "uploads/shot.jpg",
                },
                provider,
                root=root,
            )

        self.assertFalse(provider.called)
        self.assertEqual(result["findings"][0]["findingType"], "uncertainty")
        self.assertEqual(result["findings"][0]["confidence"], "low")
        self.assertIn("structured image/video media parts", result["findings"][0]["missingInfo"][0])

    def test_missing_media_content_degrades_without_calling_multimodal_provider(self) -> None:
        provider = RecordingVisionProvider()

        result = analyze_media_context(
            {"id": "media-missing", "mediaKind": "photo", "localPath": "uploads/missing.jpg"},
            provider,
        )

        self.assertEqual(provider.messages, [])
        self.assertEqual(result["findings"][0]["findingType"], "uncertainty")
        self.assertIn("media content is unavailable", result["findings"][0]["missingInfo"][0])

    def test_redacted_media_is_not_sent_to_multimodal_provider(self) -> None:
        provider = RecordingVisionProvider()
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            image = root / "uploads" / "redacted.jpg"
            image.parent.mkdir()
            image.write_bytes(b"redacted-image-bytes")
            result = analyze_media_context(
                {
                    "id": "media-redacted",
                    "targetType": "shot",
                    "targetId": "round-1:7:2",
                    "mediaKind": "photo",
                    "localPath": "uploads/redacted.jpg",
                    "privacyState": "redacted",
                },
                provider,
                root=root,
            )

        self.assertEqual(provider.messages, [])
        self.assertEqual(provider.media_parts, [])
        self.assertEqual(result["findings"][0]["findingType"], "uncertainty")
        self.assertEqual(result["findings"][0]["confidence"], "low")
        self.assertIn("redacted", result["findings"][0]["missingInfo"][0])

    def test_media_bytes_are_sent_as_structured_multimodal_parts(self) -> None:
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
        self.assertEqual(len(provider.media_parts), 1)
        self.assertEqual(provider.media_parts[0].media_type, "image")
        self.assertEqual(provider.media_parts[0].mime_type, "image/jpeg")
        self.assertEqual(provider.media_parts[0].data, b"image-bytes")
        self.assertNotIn("mediaBytesBase64", prompt)
        self.assertNotIn("aW1hZ2UtYnl0ZXM=", prompt)
        self.assertNotIn("image-bytes", prompt)
        self.assertIn("byteLength=11", prompt)

    def test_multimodal_prompt_redacts_absolute_private_media_path(self) -> None:
        provider = RecordingVisionProvider()
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            image = root / "private-media" / "shot.jpg"
            image.parent.mkdir()
            image.write_bytes(b"image-bytes")
            result = analyze_media_context(
                {
                    "id": "media-private-path",
                    "targetType": "shot",
                    "targetId": "round-1:7:2",
                    "mediaKind": "photo",
                    "localPath": str(image),
                },
                provider,
                root=root,
            )

        self.assertEqual(result["findings"][0]["findingType"], "visible_water")
        self.assertNotIn(tmp, provider.messages[-1].content)
        self.assertIn("[REDACTED_PATH]", provider.messages[-1].content)

    def test_video_bytes_are_sent_as_structured_multimodal_parts(self) -> None:
        provider = RecordingVisionProvider()
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            video = root / "uploads" / "swing.mp4"
            video.parent.mkdir()
            video.write_bytes(b"video-bytes")
            result = analyze_media_context(
                {
                    "id": "media-4",
                    "targetType": "shot",
                    "targetId": "round-1:7:2",
                    "mediaKind": "video",
                    "localPath": "uploads/swing.mp4",
                },
                provider,
                root=root,
            )

        prompt = provider.messages[-1].content
        self.assertEqual(result["findings"][0]["findingType"], "visible_water")
        self.assertEqual(len(provider.media_parts), 1)
        self.assertEqual(provider.media_parts[0].media_type, "video")
        self.assertEqual(provider.media_parts[0].mime_type, "video/mp4")
        self.assertEqual(provider.media_parts[0].data, b"video-bytes")
        self.assertNotIn("mediaBytesBase64", prompt)
        self.assertNotIn("dmlkZW8tYnl0ZXM=", prompt)
        self.assertNotIn("video-bytes", prompt)
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
