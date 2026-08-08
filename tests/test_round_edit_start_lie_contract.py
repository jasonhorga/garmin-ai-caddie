from __future__ import annotations

import re
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
COMPONENTS = ROOT / "mobile/ios/AICaddie/Views/RoundShotEditComponents.swift"
MODEL = ROOT / "mobile/ios/AICaddie/Models/RoundEditModel.swift"
SHOT_MAP = ROOT / "mobile/ios/AICaddie/Views/RoundShotMapView.swift"


class RoundEditStartLieContractTests(unittest.TestCase):
    def test_sheet_reads_and_labels_the_shot_start_lie(self) -> None:
        source = COMPONENTS.read_text(encoding="utf-8")

        self.assertIn('Section("击球时球位")', source)
        self.assertIn('let rawLie = (shot.lie ?? "unknown").lowercased()', source)
        self.assertIn('self._selectedLie = State(initialValue:', source)
        self.assertIn('get: { selectedLie }', source)
        self.assertNotIn("shot.endLie ?? shot.lie", source)

    def test_start_lie_picker_excludes_water_and_green(self) -> None:
        source = COMPONENTS.read_text(encoding="utf-8")
        declaration = source.split("public let roundEditLieOptions", 1)[1]
        options = declaration.split("= [", 1)[1].split("]", 1)[0]
        values = re.findall(r'\("([a-z]+)",', options)

        self.assertEqual(
            values,
            ["teebox", "fairway", "rough", "bunker", "fringe", "trees", "unknown"],
        )

    def test_local_manual_shot_does_not_fabricate_end_lie(self) -> None:
        source = MODEL.read_text(encoding="utf-8")

        self.assertIn("club: club, lie: lie, endLie: nil", source)
        self.assertNotIn("club: club, lie: lie, endLie: lie", source)

    def test_every_editable_start_lie_has_a_visible_label(self) -> None:
        source = SHOT_MAP.read_text(encoding="utf-8")

        self.assertIn('case "fringe": return "果岭边"', source)
        self.assertIn('case "trees", "tree_area": return "树下"', source)


if __name__ == "__main__":
    unittest.main()
