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

    def test_non_numeric_meters_skipped_not_crash(self):
        # A corrupt/non-numeric meters in a (member) shot file must skip the shot, never 500 prep.
        bad = self.root / "bad"; bad.mkdir()
        _write_shots(bad, 1, [{"holeNumber": 1, "shots": [
            {"shotOrder": 1, "shotType": "APPROACH", "clubId": 8201, "meters": "oops", "endLoc": {}},
            _shot(2, "APPROACH", 8201, 150.0, 31.76, 118.63)]}],
            club_details=[{"id": 8201, "name": "7I"}])
        prof = data.build_club_profiles(shot_dirs=[bad])  # must not raise
        self.assertEqual(prof["7I"]["sampleSize"], 1)     # the good shot counted, the bad one skipped


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

        def fake_profiles(*, shot_dirs, apply_overrides=True):
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

    def test_member_zero_shots_falls_back_typed_then_default(self):
        # Manual bag but ZERO logged shots (a no-Garmin member who hasn't played) -> measured empty
        # -> each club falls back to typed distanceM, else catalog default.
        bag = {"clubs": [{"token": "iron7", "distanceM": 145}, {"token": "driver"}]}
        with patch.object(course_prep, "load_manual_club_bag", side_effect=lambda pid: bag), \
             patch.object(course_prep, "build_club_profiles", return_value={}), \
             patch("ai_caddie.history.history._player_shot_sources",
                   side_effect=lambda pid: [(Path("/M/sc"), Path("/M/shots"))]):
            ladder = dict(course_prep.effective_club_ladder("memberZ"))
        self.assertEqual(ladder["iron7"], 145)   # typed (no measured)
        self.assertEqual(ladder["driver"], 200)  # catalog default (no measured, no typed)


class ClubNameOverrideIsolationTests(unittest.TestCase):
    """The owner clubs.json override must NEVER resolve a member's shot (clubId collision guard)."""

    def setUp(self):
        tmp = TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.member_shots = self.root / "m_shots"; self.member_shots.mkdir()
        # member shot: tiny manual clubId=2 (round_ingest assigns 1,2,3…), own clubDetails name "7I".
        _write_shots(self.member_shots, 1, [{"holeNumber": 1, "shots": [
            _shot(1, "APPROACH", 2, 150.0, 31.76, 118.63)]}],
            club_details=[{"id": 2, "name": "7I"}])
        # owner clubs.json override COLLIDES on clubId 2 with the owner's club name.
        (self.root / "clubs.json").write_text(json.dumps({"2": {"name": "OWNER-DRIVER"}}))
        p = patch.object(data, "CLUBS_FILE", self.root / "clubs.json"); p.start(); self.addCleanup(p.stop)

    def test_member_read_uses_own_clubdetails_not_owner_override(self):
        prof = data.build_club_profiles(shot_dirs=[self.member_shots], apply_overrides=False)
        self.assertIn("7I", prof)                 # member's own clubDetails name
        self.assertNotIn("OWNER-DRIVER", prof)    # owner override never applied to member data

    def test_owner_read_still_applies_override(self):
        # Owner default (apply_overrides=True) DOES apply the override -> proves the gate is real.
        prof = data.build_club_profiles(shot_dirs=[self.member_shots])
        self.assertIn("OWNER-DRIVER", prof)
        self.assertNotIn("7I", prof)


class PrepCacheFingerprintPlayerTests(unittest.TestCase):
    """A member's prep fingerprint tracks THEIR shots/scorecards/manual-bag; the owner's fingerprint
    is unaffected by a member's writes."""

    def setUp(self):
        from ai_caddie.courses import prep_cache
        self.pc = prep_cache
        tmp = TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        (self.root / "owner_shots").mkdir(); (self.root / "owner_sc").mkdir()
        for attr, val in [("DATA_DIR", self.root),
                          ("SHOT_DIR", self.root / "owner_shots"),
                          ("SCORECARD_DIR", self.root / "owner_sc")]:
            p = patch.object(prep_cache, attr, val); p.start(); self.addCleanup(p.stop)
        self.member_dir = self.root / "players" / "memberA"
        (self.member_dir / "shots").mkdir(parents=True)
        (self.member_dir / "scorecards").mkdir(parents=True)

    def test_member_fp_changes_on_own_writes_owner_unaffected(self):
        owner_fp = self.pc._fingerprint(31870, "me")
        member_fp = self.pc._fingerprint(31870, "memberA")
        (self.member_dir / "shots" / "1.json").write_text("{}")     # member logs a shot
        self.assertNotEqual(self.pc._fingerprint(31870, "memberA"), member_fp)
        member_fp2 = self.pc._fingerprint(31870, "memberA")
        (self.member_dir / "club_bag_manual.json").write_text("{}")  # member edits their bag
        self.assertNotEqual(self.pc._fingerprint(31870, "memberA"), member_fp2)
        self.assertEqual(self.pc._fingerprint(31870, "me"), owner_fp)  # owner untouched by member


class WiringIsolationTests(unittest.TestCase):
    """Guard a future mis-wire: prep builders must pass the MEMBER's sources/player_id, never fall
    back to the owner's tree (leaf-fn unit tests alone wouldn't catch that)."""

    def test_your_shots_passes_member_sources_and_no_override(self):
        md = {"hole": {"RefLat": 31.7, "RefLon": 118.6}}
        with patch("ai_caddie.history.history._player_shot_sources",
                   return_value=[(Path("/M/sc"), Path("/M/shots"))]), \
             patch.object(course_prep.shot_projection, "shots_for_hole", return_value=[]) as sfh:
            course_prep._your_shots(md, {}, [], 31870, 1, {"w": 100, "h": 100}, player_id="memberA")
        self.assertEqual(sfh.call_args.kwargs["sources"], [(Path("/M/sc"), Path("/M/shots"))])
        self.assertFalse(sfh.call_args.kwargs["apply_overrides"])

    def test_your_shots_owner_uses_none_sources_and_override(self):
        md = {"hole": {"RefLat": 31.7, "RefLon": 118.6}}
        with patch.object(course_prep.shot_projection, "shots_for_hole", return_value=[]) as sfh:
            course_prep._your_shots(md, {}, [], 31870, 1, {"w": 100, "h": 100}, player_id="me")
        self.assertIsNone(sfh.call_args.kwargs["sources"])
        self.assertTrue(sfh.call_args.kwargs["apply_overrides"])

    def test_prep_tips_threads_member_player_id_to_prep_nine(self):
        from types import SimpleNamespace
        from server_v2 import prep_tips
        with patch.object(prep_tips, "load_history_data_for_mode",
                          return_value=(SimpleNamespace(rounds=[]), "fixture")), \
             patch.object(prep_tips, "cached_build_history_stats", return_value={"courses": []}), \
             patch.object(prep_tips, "build_prep_tips", return_value={"tips": []}), \
             patch.object(course_prep, "effective_club_ladder", return_value=[]), \
             patch.object(course_prep, "available_prep_holes", return_value=[1]), \
             patch.object(course_prep, "prep_nine", return_value=[]) as prep_nine:
            prep_tips.load_prep_tips_response(31870, player_id="memberA")
        self.assertEqual(prep_nine.call_args.kwargs["player_id"], "memberA")


if __name__ == "__main__":
    unittest.main()
