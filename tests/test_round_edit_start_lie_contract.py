from __future__ import annotations

import re
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
COMPONENTS = ROOT / "mobile/ios/AICaddie/Views/RoundShotEditComponents.swift"
MODEL = ROOT / "mobile/ios/AICaddie/Models/RoundEditModel.swift"
SHOT_MAP = ROOT / "mobile/ios/AICaddie/Views/RoundShotMapView.swift"


class RoundEditStartLieContractTests(unittest.TestCase):
    def test_edit_bar_lie_grid_reads_and_labels_the_shot_start_lie(self) -> None:
        source = COMPONENTS.read_text(encoding="utf-8")
        # B3: the detail sheet is gone; the bottom edit bar's lie grid edits the selected shot's
        # start lie (where it was played from), never its landing.
        grid = source.split("private func lieGrid(_ shot: RoundShot) -> some View {", 1)[1]
        grid = grid.split("\n    }\n", 1)[0]

        self.assertIn('let rawLie = (shot.lie ?? "unknown").lowercased()', grid)
        self.assertIn('let current = validLies.contains(rawLie) ? rawLie : "unknown"', grid)
        self.assertIn("ForEach(roundEditLieOptions, id: \\.0)", grid)
        self.assertIn('editModel.editLie(shotId: shot.id, option.0 == "unknown" ? nil : option.0)', grid)
        self.assertIn('.accessibilityLabel("击球时球位 \\(option.1)")', grid)
        self.assertIn('.accessibilityIdentifier("round-edit-lie-\\(option.0)")', grid)
        self.assertNotIn("endLie", grid)
        self.assertIn("lieGrid(shot)", source)
        self.assertNotIn("shot.endLie ?? shot.lie", source)
        self.assertNotIn('Section("击球时球位")', source)
        self.assertNotIn("_selectedLie", source)

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

        add_shot = source.split("public func addShot", 1)[1].split("public func previewMove", 1)[0]
        self.assertIn("endLie: nil", add_shot)
        self.assertNotIn("endLie: normalizedOptional(lie)", add_shot)

    def test_every_editable_start_lie_has_a_visible_label(self) -> None:
        source = SHOT_MAP.read_text(encoding="utf-8")

        self.assertIn('case "fringe": return "果岭边"', source)
        self.assertIn('case "trees", "tree_area": return "树下"', source)


if __name__ == "__main__":
    unittest.main()
