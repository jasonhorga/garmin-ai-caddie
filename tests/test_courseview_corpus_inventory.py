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
            for name in ("Fairway.drc", "PhysicsMesh.drc", "Bridge.drc", "WasteArea.drc"):
                (hole_dir / name).write_bytes(b"drc")

            before = sorted(path.relative_to(root) for path in root.rglob("*"))
            result = inventory_courseview(root)
            after = sorted(path.relative_to(root) for path in root.rglob("*"))

            self.assertEqual(before, after)
            geometry = result["prodgeometry"]
            self.assertEqual(geometry["courseCount"], 1)
            self.assertEqual(geometry["holeCount"], 1)
            self.assertIn("Fairway.drc", geometry["topoConsumedMeshNames"])
            self.assertIn("PhysicsMesh.drc", geometry["knownStructuralOrCosmeticMeshNames"])
            self.assertIn("Bridge.drc", geometry["knownStructuralOrCosmeticMeshNames"])
            self.assertEqual(geometry["unclassifiedMeshNames"], ["WasteArea.drc"])
            self.assertEqual(geometry["foliageAssetIds"]["trees"], {"4007": 1})


if __name__ == "__main__":
    unittest.main()
