import json
import tempfile
import unittest
from pathlib import Path

from tools.courseview.inventory_courseview_corpus import inventory_courseview


class CourseViewCorpusInventoryTests(unittest.TestCase):
    def test_reports_consumed_structural_and_unknown_assets_without_rewriting_corpus(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "courseview"
            hole_dir = root / "prodgeometry" / "42" / "Hole01_7"
            hole_dir.mkdir(parents=True)
            (hole_dir / "hole.json").write_text(json.dumps({
                "GlobalId": 42,
                "HoleNumber": 1,
                "Biome": "Coastal",
                "TeeLocations": [{"Sets": [1], "X": 2.0, "Y": 3.0}],
                "Doglegs": [{"GlobalId": 42, "Line": [{"X": 2.0, "Y": 3.0}]}],
            }))
            (hole_dir / "foliage.json").write_text(json.dumps({
                "trees": [{"id": 4007, "x": 1, "y": 2, "z": 3}],
                "rocks": [],
            }))
            vp8x_payload = b"\x00\x00\x00\x00" + (63).to_bytes(3, "little") + (31).to_bytes(3, "little")
            (hole_dir / "Terrain.webp").write_bytes(
                b"RIFF" + (22).to_bytes(4, "little") + b"WEBP" + b"VP8X"
                + len(vp8x_payload).to_bytes(4, "little") + vp8x_payload
            )
            (hole_dir / "unexpected.bin").write_bytes(b"opaque")
            for name in (
                "Fairway.drc", "Ocean.drc", "Beach.drc", "Cliff.drc",
                "PhysicsMesh.drc", "Bridge.drc", "WasteArea.drc",
            ):
                (hole_dir / name).write_bytes(b"drc")

            stats_root = root / "mesh-stats"
            stats_root.mkdir()
            (stats_root / "gid42_h01_stats.json").write_text(json.dumps({
                "meshes": [{
                    "file": "Fairway.drc",
                    "attributeSchema": [
                        {
                            "index": 0,
                            "uniqueId": 0,
                            "semantic": "POSITION",
                            "dataType": "FLOAT32",
                            "components": 3,
                            "normalized": False,
                            "minimum": [-4.0, 1.0, 2.0],
                            "maximum": [5.0, 6.0, 7.0],
                            "metadataEntries": [],
                        },
                        {
                            "index": 1,
                            "uniqueId": 1,
                            "semantic": "TEX_COORD",
                            "dataType": "FLOAT32",
                            "components": 2,
                            "normalized": False,
                            "minimum": [0.0, 0.0],
                            "maximum": [1.0, 1.0],
                            "metadataEntries": [],
                        },
                    ],
                }],
            }))

            before = sorted(path.relative_to(root) for path in root.rglob("*"))
            result = inventory_courseview(root, mesh_stats_root=stats_root)
            after = sorted(path.relative_to(root) for path in root.rglob("*"))

            self.assertEqual(before, after)
            geometry = result["prodgeometry"]
            self.assertEqual(result["dskimgDem"]["artifactCount"], 0)
            self.assertEqual(geometry["courseCount"], 1)
            self.assertEqual(geometry["holeCount"], 1)
            self.assertIn("Fairway.drc", geometry["topoConsumedMeshNames"])
            self.assertIn("Ocean.drc", geometry["topoConsumedMeshNames"])
            self.assertIn("Beach.drc", geometry["topoConsumedMeshNames"])
            self.assertIn("Cliff.drc", geometry["topoConsumedMeshNames"])
            self.assertIn("PhysicsMesh.drc", geometry["knownStructuralOrCosmeticMeshNames"])
            self.assertIn("Bridge.drc", geometry["knownStructuralOrCosmeticMeshNames"])
            self.assertEqual(geometry["unclassifiedMeshNames"], ["WasteArea.drc"])
            self.assertEqual(geometry["knownStaticAssetNames"], ["Terrain.webp", "foliage.json", "hole.json"])
            self.assertEqual(geometry["unclassifiedNonMeshAssetNames"], ["unexpected.bin"])
            self.assertEqual(geometry["terrain"]["dimensionCounts"], {"64x32": 1})
            self.assertEqual(geometry["terrain"]["uniqueContentCount"], 1)
            self.assertEqual(geometry["foliageAssetIds"]["trees"], {"4007": 1})
            draco = geometry["dracoStats"]
            self.assertEqual(draco["artifactCount"], 1)
            self.assertEqual(draco["meshRecordCount"], 1)
            self.assertEqual(draco["meshRecordsWithoutAttributeSchema"], 0)
            self.assertEqual(draco["semanticCounts"], {"POSITION": 1, "TEX_COORD": 1})
            self.assertEqual(draco["unclassifiedSemanticCounts"], {})
            self.assertEqual(
                draco["attributeBoundsByMesh"]["Fairway.drc"]["0:POSITION"],
                {"minimum": [-4.0, 1.0, 2.0], "maximum": [5.0, 6.0, 7.0]},
            )


if __name__ == "__main__":
    unittest.main()
