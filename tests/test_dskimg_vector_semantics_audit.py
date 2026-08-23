from __future__ import annotations

import unittest
from collections import Counter
from types import SimpleNamespace

from tools.courseview.audit_dskimg_vector_semantics import (
    SEMANTIC_DECISIONS,
    _area_index,
    _domain_nesting_summary,
    _line_area_boundary_summary,
    _memberships,
    _prodgeometry_accounting,
    _route_controls,
    _semantic_classification,
    _vector_geometry_summary,
    _vector_surface_coverage,
)


def _polygon(ext_type: int = 0x011404) -> SimpleNamespace:
    return SimpleNamespace(
        ext_type=ext_type,
        lats=[0.0, 0.0, 0.001, 0.001, 0.0],
        lons=[0.0, 0.001, 0.001, 0.0, 0.0],
    )


class DskimgVectorSemanticsAuditTests(unittest.TestCase):
    def test_terminal_decision_table_covers_all_observed_type_families(self) -> None:
        self.assertEqual(
            {kind: len(rows) for kind, rows in SEMANTIC_DECISIONS.items()},
            {"area": 15, "line": 3, "point": 2},
        )
        self.assertTrue(
            all(
                row["productUse"] and row["basis"]
                for rows in SEMANTIC_DECISIONS.values()
                for row in rows.values()
            )
        )

        classification, complete = _semantic_classification(
            {kind: Counter(rows) for kind, rows in SEMANTIC_DECISIONS.items()},
            {},
        )

        self.assertTrue(complete)
        self.assertTrue(
            all(not row["observedButUnclassified"] for row in classification.values())
        )

    def test_structural_bindings_measure_nesting_and_stream_edge(self) -> None:
        outer = SimpleNamespace(
            ext_type=0x01140E,
            lats=[-0.002, -0.002, 0.002, 0.002, -0.002],
            lons=[-0.002, 0.002, 0.002, -0.002, -0.002],
        )
        inner = _polygon(ext_type=0x011409)
        stream = _polygon(ext_type=0x01140A)
        vectors = {
            "image": {
                "areas": [outer, inner, stream],
                "lines": [
                    SimpleNamespace(
                        ext_type=0x010A00,
                        lats=[0.0, 0.0],
                        lons=[0.0, 0.001],
                    )
                ],
            }
        }

        nesting = _domain_nesting_summary(vectors)
        boundaries = _line_area_boundary_summary(vectors)

        self.assertEqual(nesting["innerObjectCount"], 1)
        self.assertEqual(nesting["outerObjectCount"], 1)
        self.assertEqual(nesting["innerVertexCoverageByOuterPercent"], 100.0)
        self.assertEqual(
            boundaries["0x010a00->0x01140a"]["withinTwoMetresPercent"],
            100.0,
        )

    def test_prodgeometry_accounting_requires_exact_unavailable_layout_set(
        self,
    ) -> None:
        unbound = [
            {"layoutId": 31636, "artifact": f"31636_{hole}_meshes.json"}
            for hole in range(1, 10)
        ] + [
            {"layoutId": 31637, "artifact": f"31637_{hole}_meshes.json"}
            for hole in range(1, 10)
        ]

        result = _prodgeometry_accounting(
            artifact_count=184,
            bound_hole_count=166,
            unbound_meshes=unbound,
            expected_unavailable_layouts={31636, 31637},
        )

        self.assertTrue(result["allProdgeometryHolesAccountedFor"])
        self.assertEqual(result["expectedUnavailableHoleCount"], 18)
        self.assertEqual(result["accountedHoleCount"], 184)
        self.assertEqual(result["unexpectedUnboundLayouts"], [])
        self.assertEqual(result["expectedButBoundOrAbsentLayouts"], [])

    def test_prodgeometry_accounting_rejects_extra_or_stale_exceptions(self) -> None:
        unbound = [{"layoutId": 31636}, {"layoutId": 99999}]

        result = _prodgeometry_accounting(
            artifact_count=4,
            bound_hole_count=2,
            unbound_meshes=unbound,
            expected_unavailable_layouts={31636, 31637},
        )

        self.assertFalse(result["allProdgeometryHolesAccountedFor"])
        self.assertEqual(result["unexpectedUnboundLayouts"], [99999])
        self.assertEqual(result["expectedButBoundOrAbsentLayouts"], [31637])

    def test_reverse_coverage_clips_to_scene_and_matches_mesh_surface(self) -> None:
        bbox = SimpleNamespace(north=0.001, east=0.001, south=-0.001, west=-0.001)
        private_green = SimpleNamespace(
            ext_type=0x011404,
            lats=[-0.0002, -0.0002, 0.0002, 0.0002, -0.0002],
            lons=[-0.0002, 0.0002, 0.0002, -0.0002, -0.0002],
        )
        playable_bounds = {
            "name": "PlayableBounds.drc",
            "positions": [
                [30.0, 0.0, -30.0],
                [-30.0, 0.0, -30.0],
                [-30.0, 0.0, 30.0],
                [30.0, 0.0, 30.0],
            ],
            "faces": [[0, 1, 2], [0, 2, 3]],
        }
        green = {
            "name": "Green.drc",
            "positions": [
                [20.0, 0.0, -20.0],
                [-20.0, 0.0, -20.0],
                [-20.0, 0.0, 20.0],
                [20.0, 0.0, 20.0],
            ],
            "faces": [[0, 1, 2], [0, 2, 3]],
        }
        result = _vector_surface_coverage(
            {
                "image": {
                    "bbox": bbox,
                    "areas": [private_green],
                    "lines": [
                        SimpleNamespace(
                            ext_type=0x012E05,
                            lats=[0.0, 0.0],
                            lons=[-0.0001, 0.0001],
                        )
                    ],
                }
            },
            {
                "image": [
                    {
                        "hole": {"RefLat": 0.0, "RefLon": 0.0},
                        "meshes": [playable_bounds, green],
                    }
                ]
            },
            resolution_metres=1.0,
        )

        row = result["areaTypes"]["0x011404"]
        self.assertEqual(row["observedImageCount"], 1)
        self.assertEqual(result["images"][0]["sceneAuthority"], "PlayableBounds.drc")
        self.assertGreater(row["surfaceCoverage"]["Green.drc"]["coveragePercent"], 75.0)
        self.assertGreater(
            result["lineTypes"]["0x012e05"]["surfaceCoverage"]["Green.drc"][
                "coveragePercent"
            ],
            99.0,
        )

    def test_reverse_coverage_falls_back_to_decoded_surface_union(self) -> None:
        bbox = SimpleNamespace(north=0.001, east=0.001, south=-0.001, west=-0.001)
        private_green = SimpleNamespace(
            ext_type=0x011404,
            lats=[-0.0002, -0.0002, 0.0002, 0.0002, -0.0002],
            lons=[-0.0002, 0.0002, 0.0002, -0.0002, -0.0002],
        )
        green = {
            "name": "Green.drc",
            "positions": [
                [20.0, 0.0, -20.0],
                [-20.0, 0.0, -20.0],
                [-20.0, 0.0, 20.0],
                [20.0, 0.0, 20.0],
            ],
            "faces": [[0, 1, 2], [0, 2, 3]],
        }
        result = _vector_surface_coverage(
            {"image": {"bbox": bbox, "areas": [private_green]}},
            {
                "image": [
                    {
                        "hole": {"RefLat": 0.0, "RefLon": 0.0},
                        "meshes": [green],
                    }
                ]
            },
            resolution_metres=1.0,
        )

        self.assertEqual(
            result["images"][0]["sceneAuthority"],
            "decoded-surface-union",
        )
        self.assertGreater(
            result["areaTypes"]["0x011404"]["surfaceCoverage"]["Green.drc"][
                "coveragePercent"
            ],
            99.0,
        )

    def test_area_membership_includes_boundary_tolerance_but_not_distant_point(
        self,
    ) -> None:
        areas = _area_index([_polygon()])

        self.assertEqual(_memberships(0.0005, 0.0005, areas), {0x011404})
        self.assertEqual(_memberships(0.0005, -0.000005, areas), {0x011404})
        self.assertEqual(_memberships(0.0005, -0.001, areas), set())

    def test_route_controls_preserve_typed_hazard_evidence(self) -> None:
        parsed = {
            "holes": [
                {
                    "lines": [
                        {
                            "role": "route",
                            "points": [
                                {"latitude": 1.0, "longitude": 2.0},
                                {"latitude": 1.001, "longitude": 2.001},
                            ],
                        },
                        {
                            "surface": "water",
                            "points": [
                                {"latitude": 1.0004, "longitude": 2.0004},
                                {"latitude": 1.0005, "longitude": 2.0005},
                            ],
                        },
                    ],
                    "hazardAnchors": [
                        {
                            "surface": "bunker",
                            "latitude": 1.0006,
                            "longitude": 2.0006,
                        }
                    ],
                }
            ]
        }

        rows = list(_route_controls(parsed))

        self.assertEqual(
            [row[0] for row in rows],
            [
                "teeRouteStart",
                "greenRouteEnd",
                "routeInterior",
                "waterSpanEndpoint",
                "waterSpanEndpoint",
                "bunkerAnchor",
            ],
        )

    def test_vector_summary_uses_unique_image_geometry_and_factual_labels(self) -> None:
        vectors = {
            "areas": [_polygon()],
            "lines": [
                SimpleNamespace(
                    ext_type=0x012E00,
                    lats=[0.0, 0.001],
                    lons=[0.0, 0.001],
                )
            ],
            "points": [SimpleNamespace(ext_type=0x013800, lat=0.0, lon=0.0)],
            "pointLabels": ["Course ~ A"],
        }
        course_data = {
            "holes": [
                {
                    "lines": [
                        {
                            "role": "route",
                            "points": [
                                {"latitude": 0.0, "longitude": 0.0},
                                {"latitude": 0.001, "longitude": 0.001},
                            ],
                        }
                    ],
                    "hazardAnchors": [],
                }
            ]
        }

        result = _vector_geometry_summary(
            {"same-image": vectors},
            {"same-image": [course_data]},
        )

        self.assertEqual(result["areas"]["0x011404"]["objectCount"], 1)
        self.assertLess(
            result["lines"]["0x012e00"]["routeVertexDistanceMetres"]["median"],
            0.01,
        )
        self.assertEqual(
            result["points"]["0x013800"]["labels"],
            {"Course ~ A": 1},
        )


if __name__ == "__main__":
    unittest.main()
