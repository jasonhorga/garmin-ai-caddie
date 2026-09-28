"""Tee-result classifier against the shared vectors, and the ``fairwayOutline`` it consumes."""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from unittest.mock import patch

from ai_caddie.courses import course_prep as cp
from ai_caddie.courses.course_reference import CoursePar
from ai_caddie.courses.tee_result import classify_tee_result

VECTORS = Path(__file__).resolve().parent / "fixtures" / "tee_result_vectors.json"
REF_LAT, REF_LON = 40.0981, 116.6123


def grid_mesh(x0, x1, y0, y1, *, step=5.0, skip=None):
    """A filled rectangle of local-metre cells as a Garmin mesh (positions are [-x, elev, y])."""
    positions, faces, index = [], [], {}

    def vertex(x, y):
        key = (round(x, 3), round(y, 3))
        if key not in index:
            index[key] = len(positions)
            positions.append([-x, 0.0, y])
        return index[key]

    x = x0
    while x < x1 - 1e-9:
        y = y0
        while y < y1 - 1e-9:
            if not (skip and skip(x, y)):
                a, b = vertex(x, y), vertex(x + step, y)
                c, d = vertex(x + step, y + step), vertex(x, y + step)
                faces += [[a, b, c], [a, c, d]]
            y += step
        x += step
    return {"positions": positions, "faces": faces}


def merge_meshes(*meshes):
    positions, faces = [], []
    for mesh in meshes:
        offset = len(positions)
        positions += mesh["positions"]
        faces += [[offset + i for i in face] for face in mesh["faces"]]
    return {"positions": positions, "faces": faces}


class SharedVectorTest(unittest.TestCase):
    def test_every_shared_vector(self) -> None:
        data = json.loads(VECTORS.read_text())
        self.assertGreaterEqual(len(data["cases"]), 15)
        for case in data["cases"]:
            with self.subTest(case["name"]):
                self.assertEqual(
                    classify_tee_result(case["point"], case["fairwayOutline"], case["route"], case["par"]),
                    case["expected"],
                )

    def test_swift_fixture_is_an_exact_copy(self) -> None:
        swift_copy = Path(__file__).resolve().parents[1] / "mobile/ios/AICaddieDomainTests/Fixtures/tee_result_vectors.json"
        self.assertEqual(swift_copy.read_bytes(), VECTORS.read_bytes())

    def test_expected_values_are_the_closed_set(self) -> None:
        data = json.loads(VECTORS.read_text())
        self.assertLessEqual({case["expected"] for case in data["cases"]}, {"hit", "left", "right", None})


class FairwayOutlineTest(unittest.TestCase):
    def prep(self, md, by):
        with patch.object(cp.hole_render, "load_mesh", return_value=(md, by)):
            prep = cp.prep_hole(
                99999, 1, ladder=[("1W", 220), ("7I", 140)],
                par_record=CoursePar(global_id=99999, par=[4], par_source="courseview", confidence="high"),
                render=False,
            )
        return prep if isinstance(prep, dict) else prep.to_dict()

    def hole(self, **extra):
        return {"hole": {
            "TeeLocations": [{"Sets": [2], "X": 0.0, "Y": 0.0}],
            "Doglegs": [{"Line": [{"X": 0.0, "Y": 0.0}, {"X": 0.0, "Y": 400.0}]}],
            **extra,
        }}

    def test_outline_has_inner_ring_and_excludes_neighbouring_fairway(self) -> None:
        own = grid_mesh(-15, 15, 150, 300, skip=lambda x, y: -5 <= x < 5 and 200 <= y < 210)
        neighbour = grid_mesh(200, 230, 150, 300)
        row = self.prep(self.hole(RefLat=REF_LAT, RefLon=REF_LON), {"Fairway.drc": merge_meshes(own, neighbour)})
        outline = row["fairwayOutline"]
        self.assertEqual(outline["version"], 1)
        self.assertEqual(outline["source"], "prodgeometry.Fairway.drc")
        self.assertEqual(len(outline["polygons"]), 1)
        polygon = outline["polygons"][0]
        self.assertEqual(len(polygon["holesLatLon"]), 1)
        self.assertEqual(len(polygon["outerPx"]), len(polygon["outerLatLon"]))
        self.assertNotEqual(polygon["outerLatLon"][0], polygon["outerLatLon"][-1])  # rings are not closed

        def lonlat_area(ring):
            return sum(a[1] * b[0] - b[1] * a[0] for a, b in zip(ring, ring[1:] + ring[:1])) / 2

        self.assertGreater(lonlat_area(polygon["outerLatLon"]), 0)  # RFC 7946: outer counter-clockwise
        self.assertLess(lonlat_area(polygon["holesLatLon"][0]), 0)

        # The server's own outline drives the shared classifier end to end.
        route = [[REF_LAT, REF_LON], list(cp.shot_projection.local_to_world(0, 400, ref_lat=REF_LAT, ref_lon=REF_LON))]

        def at(x, y):
            return list(cp.shot_projection.local_to_world(x, y, ref_lat=REF_LAT, ref_lon=REF_LON))

        self.assertEqual(classify_tee_result(at(8, 240), outline, route, 4), "hit")
        self.assertEqual(classify_tee_result(at(-40, 240), outline, route, 4), "left")
        self.assertEqual(classify_tee_result(at(40, 240), outline, route, 4), "right")
        self.assertEqual(classify_tee_result(at(-2, 205), outline, route, 4), "left")  # in the cut-out

    def test_sections_are_largest_first_whatever_the_mesh_order(self) -> None:
        small, large = grid_mesh(-12, 12, 320, 380), grid_mesh(-15, 15, 150, 300)
        for mesh in (merge_meshes(small, large), merge_meshes(large, small)):
            row = self.prep(self.hole(RefLat=REF_LAT, RefLon=REF_LON), {"Fairway.drc": mesh})
            first, second = row["fairwayOutline"]["polygons"]
            # The 150-300 m section (larger) comes first; it lies south of the 320-380 m one.
            self.assertLess(min(p[0] for p in first["outerLatLon"]), min(p[0] for p in second["outerLatLon"]))

    def test_outline_is_null_without_fairway_mesh_or_geo_anchor(self) -> None:
        fairway = {"Fairway.drc": grid_mesh(-15, 15, 150, 300)}
        self.assertIsNone(self.prep(self.hole(), fairway)["fairwayOutline"])  # no RefLat/RefLon
        row = self.prep(self.hole(RefLat=REF_LAT, RefLon=REF_LON), {})
        self.assertIn("fairwayOutline", row)
        self.assertIsNone(row["fairwayOutline"])


if __name__ == "__main__":
    unittest.main()
