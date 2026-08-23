"""Derived REAL GIR + fairway-hit for manual (non-Garmin) rounds.

These tests pin the two correctness landmines of task A2:

  1. GIR is the BALL ON THE GREEN after (par-2) strokes -- NOT ``score <= par``. A par can
     be made without a GIR (miss green, chip, 1-putt) and a GIR can be 3-putted for bogey.
     ``test_par_made_without_gir_is_false`` / ``test_gir_three_putt_bogey_is_true`` are the
     anti-score-proxy tests.
  2. COORDINATE UNITS. Manual shots persist ``endLoc`` as SEMICIRCLES, but
     ``classify_shot_surface`` expects DEGREES. ``test_known_in_green_degree_point_classifies_green``
     (and its semicircle foil) is the only thing that catches a units mismatch -- without it
     a units bug looks identical to graceful fallback (everything -> unknown -> all None).

Geometry is synthesized in a temp dir (no real prodgeometry files are in the repo): a hazard
file supplies the WGS84 reference, a mesh file supplies disjoint green/fairway/rough surface
polygons in LOCAL metres. ``local_to_wgs84`` is the exact inverse of ``wgs84_to_local`` (both
linearize on ``cos(refLat)``), so a shot end placed at a local point round-trips back inside
its polygon.
"""
from __future__ import annotations

import contextlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from ai_caddie.core import data as core_data
from ai_caddie.core.data import deg_to_semicircle, local_to_wgs84, read_json
from ai_caddie.geometry.geometry_evidence import classify_shot_surface
from ai_caddie.history import history, stats_cache
from ai_caddie.rounds import round_ingest

GID = 41825
REF_LAT = 47.73
REF_LON = 138.89

# Disjoint surface squares (local metres, [x, y]); centres are the points we classify.
GREEN_C = (0.0, 80.0)
FAIRWAY_C = (0.0, 40.0)
ROUGH_C = (40.0, 40.0)
TEE_C = (0.0, 0.0)


def _square(center: tuple[float, float], half: float = 15.0) -> list[list[float]]:
    cx, cy = center
    return [[cx - half, cy - half], [cx + half, cy - half], [cx + half, cy + half], [cx - half, cy + half]]


def _deg(local: tuple[float, float]) -> tuple[float, float]:
    """Local (x, y) metres -> (lat, lon) DEGREES, the exact inverse of the classifier's convert."""
    lat, lon = local_to_wgs84(local[0], local[1], REF_LAT, REF_LON)
    return (lat, lon)


def _shot(start_local: tuple[float, float], target_local: tuple[float, float] | None = None) -> dict:
    """An ingest-shaped shot: START at ``start_local`` (degrees), optional aim ``target``.
    Its END is the next shot's start, or -- for the last shot -- this target (see _shot_end_deg)."""
    lat, lon = _deg(start_local)
    return {"lat": lat, "lon": lon, "target": _deg(target_local) if target_local else None, "order": 0}


def _write_geometry(geo_dir: Path, *, gid: int = GID, hole: int = 1) -> None:
    hazard = {"refLat": REF_LAT, "refLon": REF_LON, "hazards": []}
    mesh = {
        "surfaces": [
            {"id": "green-1", "kind": "green", "polygon": _square(GREEN_C)},
            {"id": "fairway-1", "kind": "fairway", "polygon": _square(FAIRWAY_C)},
            {"id": "rough-1", "kind": "rough", "polygon": _square(ROUGH_C)},
        ]
    }
    (geo_dir / f"gid{gid}_h{hole:02d}_hazards.json").write_text(json.dumps(hazard))
    (geo_dir / f"gid{gid}_h{hole:02d}_meshes.json").write_text(json.dumps(mesh))


@contextlib.contextmanager
def _patch_geometry(geo_dir: Path):
    # hazard_path/mesh_path read these module globals at call time -> patching reroutes classify.
    with mock.patch.object(core_data, "HAZARD_DIR", geo_dir), mock.patch.object(core_data, "MESH_DIR", geo_dir):
        yield


class GirFairwayDerivationTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.geo_dir = Path(self._tmp.name) / "geo"
        self.geo_dir.mkdir()
        _write_geometry(self.geo_dir)
        self.addCleanup(self._tmp.cleanup)

    # ----- LANDMINE 2: coordinate units -----
    def test_known_in_green_degree_point_classifies_green(self) -> None:
        """A DEGREE end position inside the green polygon must classify as 'green'. This is the
        only test that catches a degrees/semicircles mismatch."""
        lat, lon = _deg(GREEN_C)
        with _patch_geometry(self.geo_dir):
            result = classify_shot_surface(GID, 1, {"end": {"lat": lat, "lon": lon}})
        self.assertEqual(result["surface"]["kind"], "green")

    def test_semicircle_end_does_not_classify_green(self) -> None:
        """Foil for the above: the SAME point fed as SEMICIRCLES (the LANDMINE-2 bug) lands
        nowhere -> not green. Proves the units test actually discriminates."""
        lat, lon = _deg(GREEN_C)
        semi = {"lat": deg_to_semicircle(lat), "lon": deg_to_semicircle(lon)}
        with _patch_geometry(self.geo_dir):
            result = classify_shot_surface(GID, 1, {"end": semi})
        self.assertNotEqual(result["surface"]["kind"], "green")

    def test_derive_uses_degrees_so_in_green_tee_is_gir(self) -> None:
        """(c) End-to-end units check through the helper: a par-3 tee ending on the green -> GIR True."""
        shots = [_shot(TEE_C, target_local=GREEN_C)]  # lone tee, aims & ends on green
        with _patch_geometry(self.geo_dir):
            gir, fairway = round_ingest._derive_gir_fairway(GID, 1, 3, shots, total_strokes=3)
        self.assertIs(gir, True)
        self.assertIsNone(fairway)  # par 3 -> no fairway stat

    # ----- LANDMINE 1: real GIR, not a score proxy -----
    def test_par_made_without_gir_is_false(self) -> None:
        """(a) Par-4, score 4 (par), but the approach (shots[1]) lands in ROUGH, then chip + 1
        putt. Real GIR is False; the score proxy ``score <= par`` would wrongly say True."""
        shots = [
            _shot(TEE_C),                            # tee
            _shot(ROUGH_C),                          # approach start; its END = chip start (rough)
            _shot(ROUGH_C, target_local=GREEN_C),    # chip from rough, aims at green
        ]
        with _patch_geometry(self.geo_dir):
            gir, _ = round_ingest._derive_gir_fairway(GID, 1, 4, shots, total_strokes=4)
        self.assertIs(gir, False)  # NOT None, NOT True

    def test_gir_three_putt_bogey_is_true(self) -> None:
        """(b) Par-4, approach (shots[1]) ends ON the green, then 3 putts (score 5, bogey). Real
        GIR is True; the score proxy ``score <= par`` would wrongly say False."""
        shots = [
            _shot(TEE_C),                            # tee (ends in fairway)
            _shot(FAIRWAY_C, target_local=GREEN_C),  # approach: last shot, END = target = green
        ]
        with _patch_geometry(self.geo_dir):
            gir, _ = round_ingest._derive_gir_fairway(GID, 1, 4, shots, total_strokes=5)
        self.assertIs(gir, True)

    def test_hole_out_in_regulation_is_gir_without_a_reg_shot(self) -> None:
        """Par-5 holed in <= par-2 strokes is regulation-or-better -> GIR True by the total rule
        (no classification needed)."""
        shots = [_shot(TEE_C), _shot(FAIRWAY_C, target_local=GREEN_C)]
        with _patch_geometry(self.geo_dir):
            gir, _ = round_ingest._derive_gir_fairway(GID, 1, 5, shots, total_strokes=3)
        self.assertIs(gir, True)

    # ----- fairway-hit -----
    def test_fairway_hit_miss_and_par3_none(self) -> None:
        """(d) Tee in fairway -> 'hit'; tee off fairway -> 'miss'; par 3 -> None."""
        hit = [_shot(TEE_C), _shot(FAIRWAY_C, target_local=GREEN_C)]   # shots[0].end = fairway
        miss = [_shot(TEE_C), _shot(ROUGH_C, target_local=GREEN_C)]    # shots[0].end = rough
        par3 = [_shot(TEE_C, target_local=FAIRWAY_C)]
        with _patch_geometry(self.geo_dir):
            _, fw_hit = round_ingest._derive_gir_fairway(GID, 1, 4, hit, total_strokes=4)
            _, fw_miss = round_ingest._derive_gir_fairway(GID, 1, 4, miss, total_strokes=5)
            _, fw_par3 = round_ingest._derive_gir_fairway(GID, 1, 3, par3, total_strokes=3)
        self.assertEqual(fw_hit, "hit")
        self.assertEqual(fw_miss, "miss")
        self.assertIsNone(fw_par3)

    # ----- graceful degradation -----
    def test_no_geometry_yields_none(self) -> None:
        """(e, helper) No geometry files -> gir/fairway both None (never guess)."""
        empty = Path(self._tmp.name) / "empty"
        empty.mkdir()
        shots = [_shot(TEE_C), _shot(FAIRWAY_C, target_local=GREEN_C)]
        with _patch_geometry(empty):
            gir, fairway = round_ingest._derive_gir_fairway(GID, 1, 4, shots, total_strokes=5)
        self.assertIsNone(gir)
        self.assertIsNone(fairway)

    def test_missing_global_id_or_par_yields_none(self) -> None:
        shots = [_shot(TEE_C), _shot(FAIRWAY_C, target_local=GREEN_C)]
        with _patch_geometry(self.geo_dir):
            self.assertEqual(round_ingest._derive_gir_fairway(None, 1, 4, shots, 5), (None, None))
            self.assertEqual(round_ingest._derive_gir_fairway(GID, 1, None, shots, 5), (None, None))

    # ----- only-when-absent -----
    def test_only_when_absent_does_not_overwrite(self) -> None:
        """(f) A hole already carrying gir (Garmin-authoritative) is NOT overwritten, while an
        absent fairway IS filled in."""
        shots = [_shot(TEE_C), _shot(ROUGH_C), _shot(ROUGH_C, target_local=GREEN_C)]  # would derive gir=False
        hole = {"number": 1, "strokes": 4, "gir": True}  # pre-existing source value
        with _patch_geometry(self.geo_dir):
            round_ingest._enrich_hole_gir_fairway(
                hole, global_id=GID, local_hole=1, par=4, shots=shots, total_strokes=4
            )
        self.assertIs(hole["gir"], True)            # preserved, not clobbered to False
        self.assertEqual(hole.get("fairway"), "miss")  # absent -> filled (shots[0].end = rough)


class GirFairwayIngestIntegrationTests(unittest.TestCase):
    """End-to-end: ingest_round actually writes gir/fairway into the scorecard, and the
    history pipeline reads them back."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.geo_dir = self.root / "geo"
        self.geo_dir.mkdir()
        _write_geometry(self.geo_dir)
        self._p = mock.patch.object(history, "ROOT", self.root)
        self._p.start()
        stats_cache.clear()
        self.addCleanup(stats_cache.clear)
        self.addCleanup(self._p.stop)
        self.addCleanup(self._tmp.cleanup)

    def _par4_events(self) -> list[dict]:
        tee = _deg(TEE_C)
        fw = _deg(FAIRWAY_C)
        gr = _deg(GREEN_C)
        return [
            {"hole": 1, "kind": "club", "payload": {"clubName": "1D", "shotType": "tee"}},
            {"hole": 1, "kind": "location", "payload": {"latitude": tee[0], "longitude": tee[1]}},
            {"hole": 1, "kind": "club", "payload": {"clubName": "8I", "shotType": "approach"}},
            {"hole": 1, "kind": "location", "payload": {
                "latitude": fw[0], "longitude": fw[1], "targetLatitude": gr[0], "targetLongitude": gr[1]}},
            {"hole": 1, "kind": "putt", "payload": {"putts": 2}},
            {"hole": 1, "kind": "score", "payload": {"strokes": 4}},
        ]

    def test_ingest_writes_gir_fairway_into_scorecard_and_history(self) -> None:
        meta = {"courseGlobalId": GID, "courseName": "Test", "holePars": "4"}
        with _patch_geometry(self.geo_dir):
            summary = round_ingest.ingest_round("p_friend", self._par4_events(), meta, idempotency_key="g1", root=self.root)
        rid = summary["id"]
        sc_path = self.root / "data" / "players" / "p_friend" / "scorecards" / f"{rid}.json"
        raw = read_json(sc_path)
        hole = raw["scorecardDetails"][0]["scorecard"]["holes"][0]
        # Tee ended in fairway -> hit; approach ended on green (last-shot target) -> GIR True.
        self.assertEqual(hole["number"], 1)
        self.assertIs(hole["gir"], True)
        self.assertEqual(hole["fairway"], "hit")
        # And it survives the history loader (dict(hole) preserves the keys).
        rounds = history.load_raw_rounds(player_id="p_friend")
        h = rounds[0]["holes"][0]
        self.assertIs(h["gir"], True)
        self.assertEqual(h["fairway"], "hit")

    def test_ingest_without_geometry_still_succeeds_and_omits_gir(self) -> None:
        """(e, end-to-end) No geometry -> ingest succeeds; holes carry no gir/fairway keys."""
        empty = self.root / "empty"
        empty.mkdir()
        meta = {"courseGlobalId": GID, "courseName": "Test", "holePars": "4"}
        with _patch_geometry(empty):
            summary = round_ingest.ingest_round("p_friend", self._par4_events(), meta, idempotency_key="g2", root=self.root)
        sc_path = self.root / "data" / "players" / "p_friend" / "scorecards" / f"{summary['id']}.json"
        hole = read_json(sc_path)["scorecardDetails"][0]["scorecard"]["holes"][0]
        self.assertEqual(
            hole,
            {"number": 1, "strokes": 4, "putts": 2, "penalties": 0},
        )  # no gir/fairway when undeterminable


if __name__ == "__main__":
    unittest.main()
