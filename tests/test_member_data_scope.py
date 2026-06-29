"""A2/A3/A4 — a non-owner family member's OWN logged shots feed their OWN measured club ladder
and shot scatter, with strict cross-player isolation: a member must never read another player's
(or the owner's) shots or distances. Works from manual logs, so it serves a no-Garmin member."""

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from ai_caddie.core import data
from ai_caddie.courses import course_prep
from ai_caddie.geometry import shot_projection as sp


def _shot(order, shot_type, club_id, meters, lat, lon, exclude=False):
    loc = {}
    if lat is not None:
        loc["lat"] = data.deg_to_semicircle(lat)
    if lon is not None:
        loc["lon"] = data.deg_to_semicircle(lon)
    return {
        "shotOrder": order, "shotType": shot_type, "clubId": club_id,
        "meters": meters, "excludeFromStats": exclude,
        "startLoc": {"lat": data.deg_to_semicircle(31.75), "lon": data.deg_to_semicircle(118.62)},
        "endLoc": loc,
    }


def _write_shots(shots_dir, sid, hole_rows, club_details=None):
    payload = {"clubDetails": club_details or [], "holeShots": hole_rows}
    (shots_dir / f"{sid}.json").write_text(json.dumps(payload))


def _write_scorecard(sc_dir, sid, front, back, date):
    payload = {"scorecardDetails": [{"scorecard": {
        "id": sid, "courseGlobalId": front, "frontNineGlobalCourseId": front,
        "backNineGlobalCourseId": back, "formattedStartTime": date,
    }}]}
    (sc_dir / f"{sid}.json").write_text(json.dumps(payload))


class BuildClubProfilesPlayerScopeTests(unittest.TestCase):
    """build_club_profiles(shot_dirs=...) reads ONLY the given dir(s)."""

    def setUp(self):
        tmp = TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.dir_a = self.root / "a"; self.dir_b = self.root / "b"
        self.dir_a.mkdir(); self.dir_b.mkdir()
        _write_shots(self.dir_a, 1, [{"holeNumber": 1, "shots": [
            _shot(1, "APPROACH", 8201, 150.0, 31.76, 118.63)]}],
            club_details=[{"id": 8201, "name": "7I"}])
        _write_shots(self.dir_b, 1, [{"holeNumber": 1, "shots": [
            _shot(1, "TEE", 9001, 230.0, 31.77, 118.64)]}],
            club_details=[{"id": 9001, "name": "1W"}])

    def test_profiles_isolated_per_dir(self):
        prof_a = data.build_club_profiles(shot_dirs=[self.dir_a])
        prof_b = data.build_club_profiles(shot_dirs=[self.dir_b])
        self.assertEqual(set(prof_a), {"7I"})
        self.assertNotIn("1W", prof_a)            # A never sees B's driver
        self.assertEqual(prof_a["7I"]["median"], 150.0)
        self.assertEqual(set(prof_b), {"1W"})
        self.assertNotIn("7I", prof_b)            # B never sees A's iron
        self.assertEqual(prof_b["1W"]["median"], 230.0)

    def test_owner_default_equals_flat_shot_dir(self):
        # No shot_dirs -> reads data.SHOT_DIR (owner flat), byte-identical to before.
        with patch.object(data, "SHOT_DIR", self.dir_a):
            self.assertEqual(data.build_club_profiles(), data.build_club_profiles(shot_dirs=[self.dir_a]))


class ShotsForHoleSourcesIsolationTests(unittest.TestCase):
    """shots_for_hole(..., sources=...) projects ONLY the given player trees."""

    def setUp(self):
        tmp = TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        self.sc_a = root / "a" / "scorecards"; self.sh_a = root / "a" / "shots"
        self.sc_b = root / "b" / "scorecards"; self.sh_b = root / "b" / "shots"
        for d in (self.sc_a, self.sh_a, self.sc_b, self.sh_b):
            d.mkdir(parents=True)
        # Both members played the SAME physical hole (gid 777001 / local 1).
        _write_scorecard(self.sc_a, 5001, 777001, None, "2026-05-02T08:00:00+08:00")
        _write_shots(self.sh_a, 5001, [{"holeNumber": 1, "shots": [
            _shot(1, "TEE", 8201, 150.0, 31.7610, 118.6310)]}])
        _write_scorecard(self.sc_b, 6001, 777001, None, "2026-05-03T08:00:00+08:00")
        _write_shots(self.sh_b, 6001, [{"holeNumber": 1, "shots": [
            _shot(1, "TEE", 9001, 230.0, 31.8000, 118.7000)]}])
        p = patch.object(data, "CLUBS_FILE", root / "clubs.json")  # absent -> deterministic names
        p.start(); self.addCleanup(p.stop)

    def test_member_sources_return_only_their_shots(self):
        rows_a = sp.shots_for_hole(777001, 1, sources=[(self.sc_a, self.sh_a)])
        rows_b = sp.shots_for_hole(777001, 1, sources=[(self.sc_b, self.sh_b)])
        self.assertEqual([r["roundId"] for r in rows_a], ["5001"])
        self.assertEqual([r["roundId"] for r in rows_b], ["6001"])
        self.assertNotEqual(rows_a[0]["lat"], rows_b[0]["lat"])  # neither leaks the other's position

    def test_owner_path_unchanged_when_sources_none(self):
        with patch.object(data, "SCORECARD_DIR", self.sc_a), patch.object(data, "SHOT_DIR", self.sh_a):
            rows = sp.shots_for_hole(777001, 1)
        self.assertEqual([r["roundId"] for r in rows], ["5001"])


class EffectiveClubLadderMemberTests(unittest.TestCase):
    """A member's ladder = their OWN measured median ?? manual typed ?? catalog default, isolated."""

    def test_owner_unchanged_uses_club_ladder(self):
        sentinel = [("7 Iron", 150)]
        with patch.object(course_prep, "club_ladder", return_value=sentinel) as cl:
            self.assertEqual(course_prep.effective_club_ladder("me"), sentinel)
        cl.assert_called_once()

    def test_member_measured_wins_and_is_isolated_from_other_players(self):
        # SAME manual bag for both members (iron7 typed 140, driver no typed -> catalog default).
        bag = {"clubs": [{"token": "iron7", "distanceM": 140}, {"token": "driver"}]}
        sources = {
            "memberA": [(Path("/A/sc"), Path("/A/shots"))],
            "memberB": [(Path("/B/sc"), Path("/B/shots"))],
        }
        # Each member's OWN measured profiles, keyed by club name (canonicalised by the real mapper):
        # A has measured 7-iron (150); B has measured driver (240).
        profiles = {
            Path("/A/shots"): {"7 Iron": {"clubName": "7 Iron", "median": 150.0, "sampleSize": 12}},
            Path("/B/shots"): {"Driver": {"clubName": "Driver", "median": 240.0, "sampleSize": 20}},
        }

        def fake_profiles(*, shot_dirs):
            out = {}
            for d in shot_dirs:
                out.update(profiles.get(d, {}))
            return out

        with patch.object(course_prep, "load_manual_club_bag", side_effect=lambda pid: bag), \
             patch.object(course_prep, "build_club_profiles", side_effect=fake_profiles), \
             patch("ai_caddie.history.history._player_shot_sources", side_effect=lambda pid: sources[pid]):
            ladder_a = dict(course_prep.effective_club_ladder("memberA"))
            ladder_b = dict(course_prep.effective_club_ladder("memberB"))

        # A: own measured 7-iron (150) WINS over the typed 140; driver falls back to catalog default
        # (200) because A has no measured driver — and NEVER B's measured 240.
        self.assertEqual(ladder_a["iron7"], 150)
        self.assertEqual(ladder_a["driver"], 200)
        # B: own measured driver (240); iron7 falls back to typed 140 (B has no measured iron),
        # and NEVER A's measured 150.
        self.assertEqual(ladder_b["driver"], 240)
        self.assertEqual(ladder_b["iron7"], 140)
        # Same bag, different ladders -> each reflects only that member's own shots.
        self.assertNotEqual(ladder_a, ladder_b)


if __name__ == "__main__":
    unittest.main()
