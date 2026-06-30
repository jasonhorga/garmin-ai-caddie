"""Per-player partition of the media store: a member's media (index + uploads + vision findings)
write AND read to their OWN partition only — never the owner's or another member's. Isolation is
by construction (the media root path differs per player), so there is no ownership check to bypass."""
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from fastapi import HTTPException

from server_v2 import media as media_api
from server_v2.models import MediaCreateRequest
from ai_caddie.rounds.players import OWNER_ID

A = "p_aaaaaaaa"
B = "p_bbbbbbbb"


class MemberMediaPartitionTests(unittest.TestCase):
    def _create(self, base: Path, player_id: str, target_id: str, name: str):
        root = base if player_id == OWNER_ID else base / "data" / "players" / player_id
        up = root / "data" / "media" / "uploads" / name
        up.parent.mkdir(parents=True, exist_ok=True)
        up.write_bytes(b"fake image bytes")
        req = MediaCreateRequest(
            targetType="round", targetId=target_id, mediaKind="photo",
            localPath=str(up), capturedAt="2026-05-25T00:00:00Z", privacyState="private_local",
        )
        return media_api.create_media_response(req, player_id=player_id)

    def test_resolver_owner_flat_member_partitioned(self) -> None:
        with patch("server_v2.media.MEDIA_ROOT", Path("/x")):
            self.assertEqual(media_api._media_root(OWNER_ID), Path("/x"))
            self.assertEqual(media_api._media_root(A), Path("/x") / "data" / "players" / A)
            self.assertNotEqual(media_api._media_root(A), media_api._media_root(B))

    def test_member_media_isolated_from_owner_and_other_member(self) -> None:
        with TemporaryDirectory() as tmp:
            base = Path(tmp)
            with patch("server_v2.media.MEDIA_ROOT", base):
                self._create(base, OWNER_ID, "round-1", "o.jpg")
                a = self._create(base, A, "round-1", "a.jpg")
                self._create(base, B, "round-1", "b.jpg")
                owner_list = media_api.list_target_media_response("round", "round-1", player_id=OWNER_ID)
                a_list = media_api.list_target_media_response("round", "round-1", player_id=A)
                b_list = media_api.list_target_media_response("round", "round-1", player_id=B)
            # each player sees exactly their own one media — no cross-player bleed
            self.assertEqual((owner_list.total, a_list.total, b_list.total), (1, 1, 1))
            # distinct partition index files
            self.assertTrue((base / "data" / "media" / "media_index.jsonl").exists())  # owner flat
            self.assertTrue((base / "data" / "players" / A / "data" / "media" / "media_index.jsonl").exists())
            # A's media id is absent from the owner's + B's lists
            a_id = a.media.id
            self.assertNotIn(a_id, {m.id for m in owner_list.media})
            self.assertNotIn(a_id, {m.id for m in b_list.media})

    def test_member_acting_on_another_players_media_is_404(self) -> None:
        with TemporaryDirectory() as tmp:
            base = Path(tmp)
            with patch("server_v2.media.MEDIA_ROOT", base):
                owner = self._create(base, OWNER_ID, "round-1", "o.jpg")
                owner_id = owner.media.id
                # member A cannot analyze or redact the OWNER's media — not in A's partition → 404
                for op in (media_api.analyze_media_response, media_api.redact_media_response):
                    with self.assertRaises(HTTPException) as ctx:
                        op(owner_id, player_id=A)
                    self.assertEqual(ctx.exception.status_code, 404)

    def test_owner_media_is_flat_not_under_players(self) -> None:
        with TemporaryDirectory() as tmp:
            base = Path(tmp)
            with patch("server_v2.media.MEDIA_ROOT", base):
                self._create(base, OWNER_ID, "round-1", "o.jpg")
            self.assertTrue((base / "data" / "media" / "media_index.jsonl").exists())
            self.assertFalse((base / "data" / "players").exists())  # owner never writes a player partition


if __name__ == "__main__":
    unittest.main()
