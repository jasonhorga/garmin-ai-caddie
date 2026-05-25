from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from ai_caddie.media import attach_media, list_media, media_for_target, media_index_file


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


if __name__ == "__main__":
    unittest.main()
