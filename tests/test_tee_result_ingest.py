"""Manual-round tee result through the real ingest path (spec 5.8, IMPLEMENTATION_PLAN B0).

Nothing on the decision path is mocked: ``ingest_round`` reads installed prodgeometry files
from disk (Garmin's ``hole.json`` + ``Fairway.drc`` mesh layout, written to a temporary
``MESH_DIR``), ``course_prep.tee_result_geometry`` builds the fairway outline and route from
them, and the shared ``classify_tee_result`` decides. No real Garmin geometry is committed to
this public repository, so the holes are small invented ones whose answers can be worked out
by hand. Only Garmin's cached Tee list (a release input) is supplied for the Red-Tee round.

Hand calculation of the coordinates: hole-local metres are x east / y north about
RefLat 40.0, RefLon 116.0 (mesh positions are ``[-x, elevation, y]``). With the WGS84
equatorial radius R = 6378137 m, 1 m north = 180 / (pi R) = 8.983153e-6 deg of latitude and
1 m east = 8.983153e-6 / cos(40 deg) = 1.172667e-5 deg of longitude. The positions below are
those offsets written out to 9 decimals.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ai_caddie.core import data as core_data
from ai_caddie.courses import course_prep
from ai_caddie.history import history, stats_cache
from ai_caddie.rounds import round_ingest

GID = 990042
REF = {"RefLat": 40.0, "RefLon": 116.0}
TEE = (40.0, 116.0)                            # local (0, 0)
# Straight hole: fairway x -15..15 m, y 150..300 m; route (0, 0) -> (0, 400), due north.
MIDDLE = (40.002021209, 116.0)                 # (0, 225): inside, 15 m from either side edge
WEST = (40.002021209, 115.999530933)           # (-40, 225): 25 m west of the fairway
EAST = (40.002021209, 116.000469067)           # (40, 225): 25 m east of the fairway
# Dogleg: Blue tee (0, 0), forward Red tee (60, 150); Doglegs (0, 0) -> (0, 200) -> (100, 300);
# fairway x -15..15 m, y 100..200 m.
DOGLEG_BALL = (40.00148222, 116.000234533)     # (20, 165): 5 m east of the fairway
GREEN = (40.00350343, 116.0)                   # (0, 390): the second shot's aim


def _rectangle(x0: float, x1: float, y0: float, y1: float) -> dict:
    corners = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    return {"name": "Fairway.drc", "positions": [[-x, 0.0, y] for x, y in corners],
            "faces": [[0, 1, 2], [0, 2, 3]]}


STRAIGHT = {
    "hole": {**REF, "TeeLocations": [{"Sets": [2], "X": 0.0, "Y": 0.0}],
             "Doglegs": [{"Line": [{"X": 0.0, "Y": 0.0}, {"X": 0.0, "Y": 400.0}]}]},
    "meshes": [_rectangle(-15, 15, 150, 300)],
}
DOGLEG = {
    "hole": {**REF, "TeeLocations": [{"Sets": [2], "X": 0.0, "Y": 0.0}, {"Sets": [5], "X": 60.0, "Y": 150.0}],
             "Doglegs": [{"Line": [{"X": 0.0, "Y": 0.0}, {"X": 0.0, "Y": 200.0}, {"X": 100.0, "Y": 300.0}]}]},
    "meshes": [_rectangle(-15, 15, 100, 200)],
}
RELEASE_TEES = [{"name": "Blue", "gender": "MEN", "index": 2}, {"name": "Red", "gender": "MEN", "index": 5}]


def _hole_events(hole: int, second: tuple[float, float]) -> list[dict]:
    """Tee and approach shots plus an explicit putt event, five strokes total.

    The approach aim is that shot's end, so GIR reads the mesh while the tee result reads the
    second location. Product spec 2.8 treats the explicit putt event as the only persisted putts
    value.
    """
    return [
        {"hole": hole, "kind": "club", "payload": {"clubName": "1W", "shotType": "tee"}},
        {"hole": hole, "kind": "location", "payload": {"latitude": TEE[0], "longitude": TEE[1]}},
        {"hole": hole, "kind": "club", "payload": {"clubName": "7I", "shotType": "approach"}},
        {"hole": hole, "kind": "location", "payload": {"latitude": second[0], "longitude": second[1],
                                                       "targetLatitude": GREEN[0], "targetLongitude": GREEN[1]}},
        {"hole": hole, "kind": "putt", "payload": {"putts": 2}},
        {"hole": hole, "kind": "score", "payload": {"strokes": 5}},
    ]


class TeeResultIngestTest(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.geo = self.root / "geo"
        self.geo.mkdir()
        for name, value in (("MESH_DIR", self.geo), ("HAZARD_DIR", self.geo)):
            patcher = patch.object(core_data, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        patcher = patch.object(history, "ROOT", self.root)
        patcher.start()
        self.addCleanup(patcher.stop)
        stats_cache.clear()
        self.addCleanup(stats_cache.clear)

    def install(self, hole_json: dict, local_hole: int = 1) -> None:
        (self.geo / f"gid{GID}_h{local_hole:02d}_meshes.json").write_text(json.dumps(hole_json))
        (self.geo / f"gid{GID}_h{local_hole:02d}_hazards.json").write_text(
            json.dumps({"refLat": 40.0, "refLon": 116.0, "hazards": []}))

    def fairways(self, events: list[dict], key: str, **meta) -> list[str | None]:
        meta = {"courseGlobalId": GID, "courseName": "C42", "holePars": "4", **meta}
        summary = round_ingest.ingest_round("p_c42", events, meta, idempotency_key=key, root=self.root)
        path = self.root / "data" / "players" / "p_c42" / "scorecards" / f"{summary['id']}.json"
        holes = json.loads(path.read_text())["scorecardDetails"][0]["scorecard"]["holes"]
        return [hole.get("fairway") for hole in holes]

    def test_second_position_against_installed_fairway(self) -> None:
        self.install(STRAIGHT)
        # Inside the rectangle -> hit. Outside, the route runs due north, so west of it is the
        # golfer's left and east is the right (25 m clear of the fairway, far from the line).
        self.assertEqual(self.fairways(_hole_events(1, MIDDLE), "middle"), ["hit"])
        self.assertEqual(self.fairways(_hole_events(1, WEST), "west"), ["left"])
        self.assertEqual(self.fairways(_hole_events(1, EAST), "east"), ["right"])

    def test_course_without_precise_geometry_has_no_tee_result(self) -> None:
        # Spec 5.8: no fairway outline -> no result. Nothing is installed for GID; CourseView
        # courseData has no fairway polygon, so its lightweight prep is not consulted either.
        with patch.object(course_prep, "lightweight_prep_hole", return_value=None) as lightweight:
            self.assertEqual(self.fairways(_hole_events(1, WEST), "no-geometry"), [None])
        lightweight.assert_not_called()

    def test_round_tee_route_sides_a_miss_like_the_phone(self) -> None:
        # The phone sides a miss against its prep ``route``: the route of the round's Tee.
        # Blue route (0,0)->(0,200)->(100,300): the nearest leg to (20,165) is the first one,
        # 20 m away (the bend is 40.3 m away); heading north, x = +20 is the right.
        # Red route (60,150)->(0,200)->(100,300): the Red Tee projects onto the Blue line at
        # station 150, so only (0,200) and the green remain ahead of it. Leg 1 heads (-60,+50);
        # the ball is (-40,+15) from its start, cross = -60*15 - 50*(-40) = +1100 > 0 -> left
        # (distance 14.1 m; the bend is again 40.3 m away).
        self.install(DOGLEG)
        with patch("ai_caddie.courses.course_reference.courseview_tees", return_value=RELEASE_TEES):
            self.assertEqual(self.fairways(_hole_events(1, DOGLEG_BALL), "blue"), ["right"])
            self.assertEqual(self.fairways(_hole_events(1, DOGLEG_BALL), "red", teeBox="red"), ["left"])

    def test_each_hole_mesh_is_decoded_once_per_ingest(self) -> None:
        # An A+A composite round plays local hole 1 as holes 1 and 10. Its GIR surface and its tee
        # result both need the mesh: one decode serves all four uses.
        self.install(STRAIGHT)
        reads: list[str] = []
        read_text = Path.read_text

        def counting(path: Path, *args, **kwargs):
            if path.name.endswith("_meshes.json"):
                reads.append(path.name)
            return read_text(path, *args, **kwargs)

        events = [*_hole_events(1, WEST), *_hole_events(10, WEST)]
        with patch.object(Path, "read_text", counting):
            fairways = self.fairways(events, "a-plus-a", holePars="4" * 18,
                                     frontNineGlobalCourseId=GID, backNineGlobalCourseId=GID)
        self.assertEqual(fairways, ["left", "left"])
        self.assertEqual(reads, [f"gid{GID}_h01_meshes.json"])

    def retained(self, events: list[dict], key: str, **meta) -> tuple[list[str | None], list, list[int], list[str]]:
        """Ingest ``events`` and observe the ingest's mesh store: the (gid, hole) keys it still
        holds after each scored hole, its size after every insert, and every mesh file read."""
        after_hole: list[tuple[int, set]] = []
        sizes: list[int] = []
        reads: list[str] = []

        class Recording(dict):
            def __setitem__(self, k, v):
                super().__setitem__(k, v)
                sizes.append(len(self))

        init = round_ingest._IngestGeometry.__init__
        enrich = round_ingest._enrich_hole_gir_fairway
        read_text = Path.read_text

        def recording_init(geometry, *args, **kwargs):
            init(geometry, *args, **kwargs)
            geometry._meshes = Recording()
            sizes.append(len(geometry._meshes))

        def observed_enrich(hole, **kwargs):
            result = enrich(hole, **kwargs)
            after_hole.append((hole["number"], set(kwargs["geometry"]._meshes)))
            return result

        def counting(path: Path, *args, **kwargs):
            if path.name.endswith("_meshes.json"):
                reads.append(path.name)
            return read_text(path, *args, **kwargs)

        with patch.object(round_ingest._IngestGeometry, "__init__", recording_init), \
                patch.object(round_ingest, "_enrich_hole_gir_fairway", observed_enrich), \
                patch.object(Path, "read_text", counting):
            fairways = self.fairways(events, key, **meta)
        return fairways, after_hole, sizes, reads

    def test_a_plus_a_round_keeps_only_meshes_still_to_be_used(self) -> None:
        # Local holes 1..9 are played as holes 1..9 and again as 10..18. After hole n <= 9 the
        # meshes of locals 1..n are still needed (for holes 10..9+n); after hole 9+k locals 1..k
        # are done for good, leaving k+1..9. After hole 18 nothing is left.
        for local in range(1, 10):
            self.install(STRAIGHT, local)
        events = [event for number in range(1, 19) for event in _hole_events(number, WEST)]
        fairways, after_hole, _sizes, reads = self.retained(
            events, "a-plus-a-18", holePars="4" * 18, frontNineGlobalCourseId=GID, backNineGlobalCourseId=GID)
        self.assertEqual(fairways, ["left"] * 18)
        expected = [(n, {(GID, k) for k in range(1, n + 1)}) for n in range(1, 10)]
        expected += [(9 + k, {(GID, j) for j in range(k + 1, 10)}) for k in range(1, 10)]
        self.assertEqual(after_hole, expected)
        self.assertEqual(sorted(reads), [f"gid{GID}_h{local:02d}_meshes.json" for local in range(1, 10)])

    def test_ordinary_round_holds_at_most_one_mesh(self) -> None:
        """Product spec 2.8: each ordinary hole releases its mesh after GIR and tee result."""
        for local in range(1, 19):
            self.install(STRAIGHT, local)
        events = [event for number in range(1, 19) for event in _hole_events(number, WEST)]
        fairways, after_hole, sizes, reads = self.retained(events, "eighteen", holePars="4" * 18)
        self.assertEqual(fairways, ["left"] * 18)
        self.assertEqual(max(sizes), 1)
        self.assertEqual(after_hole, [(n, set()) for n in range(1, 19)])
        self.assertEqual(sorted(reads), [f"gid{GID}_h{local:02d}_meshes.json" for local in range(1, 19)])

    def test_ordinary_round_without_putt_event_shares_one_mesh_decode(self) -> None:
        """Product spec 2.8: missing putts still share one mesh decode for GIR and tee result."""
        for local in range(1, 19):
            self.install(STRAIGHT, local)
        events = [
            event
            for number in range(1, 19)
            for event in _hole_events(number, WEST)
            if event["kind"] != "putt"
        ]
        fairways, _after_hole, sizes, reads = self.retained(events, "eighteen-no-putts", holePars="4" * 18)
        self.assertEqual(fairways, ["left"] * 18)
        self.assertEqual(max(sizes), 1)
        self.assertEqual(sorted(reads), [f"gid{GID}_h{local:02d}_meshes.json" for local in range(1, 19)])


if __name__ == "__main__":
    unittest.main()
