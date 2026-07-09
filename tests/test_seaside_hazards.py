"""海边障碍补全:Ocean/OceanSide/Beach 映射到现有 kind(水/水边/沙);未登记的 drc 记警告(自愈)。"""
from __future__ import annotations

import unittest

from ai_caddie.geometry.export_prodgeometry_hazards import FEATURES, KNOWN_NON_HAZARD, _log_unknown_meshes


class SeasideHazardsTests(unittest.TestCase):
    def test_seaside_features_mapped_to_existing_kinds(self):
        self.assertEqual(FEATURES["Ocean.drc"], "water")
        self.assertEqual(FEATURES["OceanSide.drc"], "water_edge")
        self.assertEqual(FEATURES["Beach.drc"], "bunker")

    def test_cosmetic_stay_out_of_features(self):
        for c in ("VfxOcean.drc", "PhysicsMesh.drc", "Cartpath.drc", "CliffUV2.drc"):
            self.assertNotIn(c, FEATURES)
            self.assertIn(c, KNOWN_NON_HAZARD)

    def test_unclassified_mesh_returned_known_not(self):
        # Returns the unclassified names (robust to a suite that globally disables logging).
        unknown = _log_unknown_meshes(["Bunker.drc", "Ocean.drc", "WasteBunker.drc", "PhysicsMesh.drc"])
        self.assertIn("WasteBunker.drc", unknown, "新障碍类型该被点名")
        self.assertNotIn("Bunker.drc", unknown, "已登记的不该点名")
        self.assertNotIn("Ocean.drc", unknown, "新加的海水也已登记,不该点名")
        self.assertNotIn("PhysicsMesh.drc", unknown, "已知装饰的不该点名")


if __name__ == "__main__":
    unittest.main()
