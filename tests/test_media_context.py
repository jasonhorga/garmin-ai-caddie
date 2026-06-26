from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from ai_caddie.core.media import attach_media, list_media, media_for_target, media_index_file, redact_media, resolve_media_content_path


class MediaContextTests(unittest.TestCase):
    def test_attach_and_list_media_metadata_without_binary_bytes(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            image = root / "uploads" / "shot.jpg"
            image.parent.mkdir()
            image.write_bytes(b"\xff\xd8private-binary")

            record = attach_media(
                target_type="shot",
                target_id="round-1:7:2",
                media_kind="photo",
                local_path=image,
                captured_at="2026-05-25T00:00:00Z",
                privacy_state="private_local",
                root=root,
            )
            attach_media(
                target_type="hole",
                target_id="round-1:7",
                media_kind="video",
                local_path="uploads/approach.mp4",
                captured_at="2026-05-25T00:01:00Z",
                privacy_state="private_local",
                root=root,
            )

            rows = list_media(root=root)
            target_rows = media_for_target("shot", "round-1:7:2", root=root)
            raw_index = media_index_file(root).read_text(encoding="utf-8")

        self.assertTrue(record["id"])
        self.assertEqual(record["targetType"], "shot")
        self.assertEqual(record["targetId"], "round-1:7:2")
        self.assertEqual(record["mediaKind"], "photo")
        self.assertEqual(record["localPath"], "uploads/shot.jpg")
        self.assertEqual(record["capturedAt"], "2026-05-25T00:00:00Z")
        self.assertEqual(record["privacyState"], "private_local")
        self.assertEqual(len(rows), 2)
        self.assertEqual([row["id"] for row in target_rows], [record["id"]])
        self.assertNotIn("private-binary", raw_index)
        self.assertNotIn(str(root), raw_index)

    def test_rejects_invalid_target_kind_and_privacy_state(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)

            with self.assertRaises(ValueError):
                attach_media("course", "c1", "photo", "shot.jpg", "2026-05-25T00:00:00Z", root=root)
            with self.assertRaises(ValueError):
                attach_media("shot", "s1", "audio", "shot.wav", "2026-05-25T00:00:00Z", root=root)
            with self.assertRaises(ValueError):
                attach_media("shot", "s1", "photo", "shot.jpg", "2026-05-25T00:00:00Z", privacy_state="public", root=root)

            self.assertEqual(list_media(root=root), [])

    def test_redaction_does_not_delete_manually_attached_file_outside_media_uploads(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            local_note = root / "notes.txt"
            local_note.write_text("keep this file", encoding="utf-8")

            record = attach_media(
                target_type="shot",
                target_id="round-1:7:2",
                media_kind="photo",
                local_path=local_note,
                captured_at="2026-05-25T00:00:00Z",
                privacy_state="private_local",
                root=root,
            )

            result = redact_media(record["id"], root=root)
            latest = list_media(root=root)[0]
            local_note_exists = local_note.exists()
            local_note_text = local_note.read_text(encoding="utf-8")

        self.assertFalse(result["deletedContent"])
        self.assertTrue(local_note_exists)
        self.assertEqual(local_note_text, "keep this file")
        self.assertEqual(latest["privacyState"], "redacted")
        self.assertEqual(latest["localPath"], "[redacted]")

    def test_existing_media_index_absolute_paths_are_sanitized_on_read(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            upload = root / "data" / "media" / "uploads" / "legacy.jpg"
            upload.parent.mkdir(parents=True, exist_ok=True)
            upload.write_bytes(b"legacy-bytes")
            path = media_index_file(root)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                (
                    '{"id":"legacy-media","createdAt":"2026-05-25T00:00:00Z",'
                    '"targetType":"shot","targetId":"round-1:7:2","mediaKind":"photo",'
                    f'"localPath":"{upload.as_posix()}","capturedAt":"2026-05-25T00:00:00Z",'
                    '"privacyState":"private_local","source":"manual"}\n'
                ),
                encoding="utf-8",
            )

            rows = list_media(root=root)
            target_rows = media_for_target("shot", "round-1:7:2", root=root)

        combined = f"{rows} {target_rows}"
        self.assertEqual(rows[0]["localPath"], "data/media/uploads/legacy.jpg")
        self.assertNotIn(tmp, combined)

    def test_media_content_resolution_stays_inside_upload_root(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            upload = root / "data" / "media" / "uploads" / "shot.jpg"
            upload.parent.mkdir(parents=True, exist_ok=True)
            upload.write_bytes(b"safe-media")
            secret = root / "secret.txt"
            secret.write_text("must not be read", encoding="utf-8")
            outside = root.parent / "outside-secret.txt"
            outside.write_text("must not be read", encoding="utf-8")

            allowed = resolve_media_content_path("data/media/uploads/shot.jpg", root=root)
            traversal = resolve_media_content_path("data/media/uploads/../../secret.txt", root=root)
            sibling = resolve_media_content_path("secret.txt", root=root)
            absolute_outside = resolve_media_content_path(outside, root=root)

        self.assertEqual(allowed, upload.resolve())
        self.assertIsNone(traversal)
        self.assertIsNone(sibling)
        self.assertIsNone(absolute_outside)


if __name__ == "__main__":
    unittest.main()
