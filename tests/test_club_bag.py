"""Tests for the real Garmin club bag: fetch (merge /club/player + /club/types),
on-disk loader, and the owner-scoped response builder."""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import requests

from ai_caddie.garmin import fetch
from ai_caddie import club_bag, data


# A subset of the owner's real bag (/club/player) — note custom names + a 2nd type-18 club.
BAG_PAYLOAD = [
    {"id": 42684923, "clubTypeId": 1, "shaftLength": 45.5, "retired": False, "deleted": False},
    {"id": 42684934, "clubTypeId": 18, "shaftLength": 35.5, "retired": False, "deleted": False},
    {"id": 42684975, "name": "Pw", "clubTypeId": 18, "shaftLength": 45.5, "retired": False, "deleted": False},
    {"id": 42684936, "name": "50", "clubTypeId": 20, "shaftLength": 35.5, "retired": False, "deleted": False},
    {"id": 99999999, "clubTypeId": 7, "shaftLength": 0, "retired": True, "deleted": False},
    {"id": 88888888, "clubTypeId": 2, "shaftLength": 0, "retired": False, "deleted": True},
]
TYPES_PAYLOAD = [
    {"value": 1, "name": "Driver", "loftAngle": 10.5, "shaftLength": 45.5},
    {"value": 2, "name": "3 Wood", "loftAngle": 15.0},
    {"value": 18, "name": "9 Iron", "loftAngle": 42.0},
    {"value": 20, "name": "Gap Wedge", "loftAngle": 50.0},
]


class _Resp:
    def __init__(self, status: int, payload) -> None:
        self.status_code = status
        self._payload = payload

    def json(self):
        return self._payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(f"status {self.status_code}")


class _Session:
    """Minimal requests.Session stand-in routing by URL suffix; can fail-once for auth retry."""

    def __init__(self, routes: dict[str, _Resp], fail_once: set[str] | None = None) -> None:
        self.routes = routes
        self.fail_once = fail_once or set()
        self.calls: list[str] = []

    def get(self, url: str, params=None, timeout=None) -> _Resp:
        self.calls.append(url)
        for suffix, resp in self.routes.items():
            if url.endswith(suffix):
                if suffix in self.fail_once:
                    self.fail_once.discard(suffix)
                    return _Resp(401, None)
                return resp
        return _Resp(404, {})


class FetchClubsTests(unittest.TestCase):
    def _run(self, session: _Session) -> dict:
        with TemporaryDirectory() as tmp:
            bag_file = Path(tmp) / "club_bag.json"
            with patch.object(fetch, "DATA_DIR", Path(tmp)), patch.object(fetch, "CLUBS_BAG_FILE", bag_file):
                out = fetch.fetch_clubs(session)
            self.assertTrue(bag_file.exists())
            on_disk = json.loads(bag_file.read_text())
        self.assertEqual(out, on_disk)
        return out

    def test_merges_player_roster_with_type_dictionary(self) -> None:
        session = _Session({"club/player": _Resp(200, BAG_PAYLOAD), "club/types": _Resp(200, TYPES_PAYLOAD)})
        out = self._run(session)
        self.assertEqual(out["schema"], "ai-caddie-club-bag-v1")
        by_id = {c["id"]: c for c in out["clubs"]}
        # Standard club: type name + loft merged in, no custom name.
        self.assertEqual(by_id[42684923]["typeName"], "Driver")
        self.assertEqual(by_id[42684923]["loftAngle"], 10.5)
        self.assertIsNone(by_id[42684923]["customName"])
        # Custom-named club keeps the user's name AND the underlying type.
        self.assertEqual(by_id[42684975]["customName"], "Pw")
        self.assertEqual(by_id[42684975]["clubTypeId"], 18)
        self.assertEqual(by_id[42684936]["customName"], "50")
        # retired/deleted flags carried through.
        self.assertTrue(by_id[99999999]["retired"])
        self.assertTrue(by_id[88888888]["deleted"])

    def test_refreshes_auth_once_on_401(self) -> None:
        session = _Session(
            {"club/player": _Resp(200, BAG_PAYLOAD), "club/types": _Resp(200, TYPES_PAYLOAD)},
            fail_once={"club/player"},
        )
        with patch.object(fetch, "refresh_session_auth", return_value=True) as refresh:
            out = self._run(session)
        refresh.assert_called_once()
        self.assertTrue(any(c["id"] == 42684923 for c in out["clubs"]))


class LoadClubBagTests(unittest.TestCase):
    def test_missing_file_returns_none(self) -> None:
        with TemporaryDirectory() as tmp:
            with patch.object(data, "CLUBS_BAG_FILE", Path(tmp) / "nope.json"):
                self.assertIsNone(data.load_club_bag())

    def test_malformed_returns_none(self) -> None:
        with TemporaryDirectory() as tmp:
            bad = Path(tmp) / "club_bag.json"
            bad.write_text("{ not json")
            with patch.object(data, "CLUBS_BAG_FILE", bad):
                self.assertIsNone(data.load_club_bag())

    def test_loads_valid_bag(self) -> None:
        with TemporaryDirectory() as tmp:
            good = Path(tmp) / "club_bag.json"
            good.write_text(json.dumps({"schema": "ai-caddie-club-bag-v1", "clubs": [{"id": 1, "clubTypeId": 1}]}))
            with patch.object(data, "CLUBS_BAG_FILE", good):
                loaded = data.load_club_bag()
        self.assertIsNotNone(loaded)
        self.assertEqual(len(loaded["clubs"]), 1)


class BuildClubBagResponseTests(unittest.TestCase):
    def _write(self, tmp: str, payload: dict) -> None:
        Path(tmp, "club_bag.json").write_text(json.dumps(payload))

    def test_non_owner_gets_empty_bag(self) -> None:
        with TemporaryDirectory() as tmp:
            self._write(tmp, {"clubs": [{"id": 1, "clubTypeId": 1}]})
            with patch.object(data, "CLUBS_BAG_FILE", Path(tmp) / "club_bag.json"):
                resp = club_bag.build_club_bag_response(player_id="friend-7", owner_id="me")
        self.assertFalse(resp["found"])
        self.assertEqual(resp["clubs"], [])

    def test_owner_gets_resolved_bag_and_drops_invalid(self) -> None:
        payload = {
            "clubs": [
                {"id": 42684923, "clubTypeId": 1, "customName": None, "typeName": "Driver", "loftAngle": 10.5,
                 "retired": False, "deleted": False},
                {"id": 42684936, "clubTypeId": 20, "customName": "50", "typeName": "Gap Wedge", "retired": False, "deleted": False},
                {"id": None, "clubTypeId": 5, "typeName": "junk"},  # dropped: no id
                {"clubTypeId": 5},  # dropped: no id
                "not-a-dict",  # dropped
            ]
        }
        with TemporaryDirectory() as tmp:
            self._write(tmp, payload)
            with patch.object(data, "CLUBS_BAG_FILE", Path(tmp) / "club_bag.json"):
                resp = club_bag.build_club_bag_response(player_id="me", owner_id="me")
        self.assertTrue(resp["found"])
        self.assertEqual(resp["schema"], "ai-caddie-club-bag-v1")
        ids = {c["id"] for c in resp["clubs"]}
        self.assertEqual(ids, {42684923, 42684936})
        custom = next(c for c in resp["clubs"] if c["id"] == 42684936)
        self.assertEqual(custom["customName"], "50")

    def test_owner_no_file_is_not_found(self) -> None:
        with TemporaryDirectory() as tmp:
            with patch.object(data, "CLUBS_BAG_FILE", Path(tmp) / "club_bag.json"):
                resp = club_bag.build_club_bag_response(player_id="me", owner_id="me")
        self.assertFalse(resp["found"])
        self.assertEqual(resp["clubs"], [])


class ClubBagRouteTests(unittest.TestCase):
    """The `/api/v2/history/clubs/bag` route the iOS SyncClient.fetchClubBag() hits."""

    def _client(self):
        from fastapi.testclient import TestClient
        from server_v2.main import app

        return TestClient(app)

    def test_owner_route_returns_resolved_bag(self) -> None:
        bag = {
            "clubs": [
                {"id": 42684923, "clubTypeId": 1, "customName": None, "typeName": "Driver",
                 "loftAngle": 10.5, "retired": False, "deleted": False},
                {"id": 42684936, "clubTypeId": 20, "customName": "50", "typeName": "Gap Wedge",
                 "loftAngle": 50.0, "retired": False, "deleted": False},
            ]
        }
        with patch("ai_caddie.club_bag.load_club_bag", return_value=bag):
            response = self._client().get("/api/v2/history/clubs/bag")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["schema"], "ai-caddie-club-bag-v1")
        self.assertTrue(payload["found"])
        self.assertEqual(len(payload["clubs"]), 2)
        driver = next(c for c in payload["clubs"] if c["id"] == 42684923)
        self.assertEqual(driver["clubTypeId"], 1)
        self.assertEqual(driver["typeName"], "Driver")
        wedge = next(c for c in payload["clubs"] if c["id"] == 42684936)
        self.assertEqual(wedge["customName"], "50")

    def test_unsynced_bag_is_found_false(self) -> None:
        with patch("ai_caddie.club_bag.load_club_bag", return_value=None):
            response = self._client().get("/api/v2/history/clubs/bag")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["schema"], "ai-caddie-club-bag-v1")
        self.assertFalse(payload["found"])
        self.assertEqual(payload["clubs"], [])


class CanonicalClubNameTests(unittest.TestCase):
    def test_normalizes_real_garmin_forms(self) -> None:
        cases = {
            "Driver": "driver", "1W": "driver", "3W": "wood3", "3 Wood": "wood3", "三号木": "wood3",
            "5I": "iron5", "5 Iron": "iron5", "九号铁": "iron9",
            "二号小鸡腿": "hybrid2", "2I/Hybrid": "hybrid2", "3 Hybrid": "hybrid3",
            "Pw": "pw", "PW": "pw", "Aw": "gw", "GW": "gw", "A杆": "gw", "SW": "sw", "LW": "lw",
            "50": "wedge50", "54°": "wedge54", "58": "wedge58",
            "Putter": "putter", "推杆": "putter",
        }
        for raw, expected in cases.items():
            self.assertEqual(club_bag.canonical_club_name(raw), expected, raw)

    def test_unknown_and_empty(self) -> None:
        self.assertIsNone(club_bag.canonical_club_name(""))
        self.assertIsNone(club_bag.canonical_club_name(None))
        self.assertIsNone(club_bag.canonical_club_name("banana"))


# The owner's real bag (in-use) + one retired club to prove it's excluded.
_OWNER_BAG = {
    "clubs": [
        {"id": 1, "clubTypeId": 1, "customName": None, "retired": False, "deleted": False},   # driver
        {"id": 2, "clubTypeId": 2, "customName": None, "retired": False, "deleted": False},   # wood3
        {"id": 3, "clubTypeId": 6, "customName": None, "retired": False, "deleted": False},   # hybrid3
        {"id": 4, "clubTypeId": 14, "customName": None, "retired": False, "deleted": False},  # iron5
        {"id": 5, "clubTypeId": 18, "customName": None, "retired": False, "deleted": False},  # iron9
        {"id": 6, "clubTypeId": 18, "customName": "Pw", "retired": False, "deleted": False},  # iron9 + pw
        {"id": 7, "clubTypeId": 19, "customName": "Aw", "retired": False, "deleted": False},  # pw + gw
        {"id": 8, "clubTypeId": 20, "customName": "50", "retired": False, "deleted": False},  # gw + wedge50
        {"id": 9, "clubTypeId": 23, "customName": None, "retired": False, "deleted": False},  # putter
        {"id": 10, "clubTypeId": 5, "customName": None, "retired": True, "deleted": False},   # 2-hybrid, retired
    ]
}


class InUseCanonicalTests(unittest.TestCase):
    def test_includes_clubtype_and_custom_tokens_excludes_retired(self) -> None:
        with patch.object(club_bag, "load_club_bag", return_value=_OWNER_BAG):
            names = club_bag.in_use_canonical_names()
        self.assertIn("driver", names)
        self.assertIn("hybrid3", names)
        self.assertIn("iron9", names)
        self.assertIn("pw", names)        # from clubTypeId 19 AND custom "Pw"
        self.assertIn("gw", names)        # from custom "Aw" AND clubTypeId 20
        self.assertIn("wedge50", names)   # from custom "50"
        self.assertIn("putter", names)
        self.assertNotIn("hybrid2", names)  # the retired 2-hybrid is excluded

    def test_no_bag_returns_none(self) -> None:
        with patch.object(club_bag, "load_club_bag", return_value=None):
            self.assertIsNone(club_bag.in_use_canonical_names())


class RestrictToBagTests(unittest.TestCase):
    LADDER = [("1W", 230), ("3W", 210), ("2I/Hybrid", 195), ("5I", 165), ("9I", 130), ("PW", 110)]

    def test_drops_clubs_not_in_bag(self) -> None:
        with patch.object(club_bag, "load_club_bag", return_value=_OWNER_BAG):
            kept = club_bag.restrict_to_bag(self.LADDER, lambda kv: kv[0])
        names = [n for n, _ in kept]
        self.assertIn("1W", names)        # driver, carried
        self.assertIn("5I", names)        # iron5, carried
        self.assertNotIn("2I/Hybrid", names)  # NOT in bag -> dropped (the bug the user hit)

    def test_no_bag_keeps_everything(self) -> None:
        with patch.object(club_bag, "load_club_bag", return_value=None):
            kept = club_bag.restrict_to_bag(self.LADDER, lambda kv: kv[0])
        self.assertEqual(kept, self.LADDER)

    def test_falls_back_when_intersection_too_small(self) -> None:
        sparse_bag = {"clubs": [{"id": 1, "clubTypeId": 1, "retired": False, "deleted": False}]}  # only driver
        ladder = [("5I", 165), ("9I", 130)]  # none match -> would be empty
        with patch.object(club_bag, "load_club_bag", return_value=sparse_bag):
            kept = club_bag.restrict_to_bag(ladder, lambda kv: kv[0])
        self.assertEqual(kept, ladder)  # fallback to full list, never strand the caddie


if __name__ == "__main__":
    unittest.main()
