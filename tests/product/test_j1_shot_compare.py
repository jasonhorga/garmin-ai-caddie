"""J1.1 behavior tests for Garmin shot cache identity."""

from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

from ai_caddie.garmin import fetch as F


class ShotCompareProductTests(unittest.TestCase):
    def test_j1_1_rotating_garmindlm_token_is_a_shot_cache_hit(self):
        """J1.1: rotating Garmin image signatures do not rewrite a shot cache."""
        before = {
            "holeShots": [{
                "holeImageUrl": (
                    "https://birdseye.garmin.cn/birdseye/golf/raster3d/3100/"
                    "gd31500/gid031597/hole01/gid031597_hole01_0_280630.jpg"
                    "?garmindlm=1793428809_oldsignature"
                ),
            }],
        }
        after = {
            "holeShots": [{
                "holeImageUrl": before["holeShots"][0]["holeImageUrl"].replace(
                    "1793428809_oldsignature", "1793515200_newsignature"
                ),
            }],
        }
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "shots.json"
            path.write_text(json.dumps(before), encoding="utf-8")
            before_stat = path.stat()
            with self.assertNoLogs(F.logger.name, level="INFO"):
                self.assertFalse(F._write_shot_cache_if_changed(path, after))
            after_stat = path.stat()
            self.assertEqual(after_stat.st_ino, before_stat.st_ino)
            self.assertEqual(after_stat.st_mtime_ns, before_stat.st_mtime_ns)
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), before)

    def test_j1_1_changed_garmin_image_path_is_logged_and_saved(self):
        """J1.1: a changed Garmin image asset path remains a real shot change."""
        before = {
            "holeShots": [{
                "holeImageUrl": (
                    "https://birdseye.garmin.cn/birdseye/golf/raster3d/3100/"
                    "gd31500/gid031597/hole01/gid031597_hole01_0_280630.jpg"
                    "?garmindlm=1793428809_oldsignature"
                ),
            }],
        }
        after = deepcopy(before)
        after["holeShots"][0]["holeImageUrl"] = after["holeShots"][0]["holeImageUrl"].replace(
            "hole01/gid031597_hole01_0_280630.jpg",
            "hole01/gid031597_hole01_1_280631.jpg",
        ).replace("1793428809_oldsignature", "1793515200_newsignature")
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "shots.json"
            path.write_text(json.dumps(before), encoding="utf-8")
            before_inode = path.stat().st_ino
            with self.assertLogs(F.logger.name, level="INFO") as captured:
                self.assertTrue(F._write_shot_cache_if_changed(path, after))
            self.assertNotEqual(path.stat().st_ino, before_inode)
            self.assertEqual(len(captured.records), 1, captured.output)
            line = captured.records[0].getMessage()
            self.assertIn("garmin_sync_round_changed diffs=", line)
            self.assertIn("path=root.holeShots[0].holeImageUrl", line)
            self.assertNotIn("1793428809_oldsignature", line)
            self.assertNotIn("1793515200_newsignature", line)

    def test_j1_1_pin_change_with_rotating_token_is_logged_and_saved(self):
        """J1.1: a real shot field change is retained beside a rotated image signature."""
        before = {
            "holeShots": [{
                "pin": {"latitude": 30.1},
                "holeImageUrl": (
                    "https://birdseye.garmin.cn/birdseye/golf/raster3d/3100/"
                    "gd31500/gid031597/hole01/gid031597_hole01_0_280630.jpg"
                    "?garmindlm=1793428809_oldsignature"
                ),
            }],
        }
        after = deepcopy(before)
        after["holeShots"][0]["pin"]["latitude"] = 30.2
        after["holeShots"][0]["holeImageUrl"] = after["holeShots"][0]["holeImageUrl"].replace(
            "1793428809_oldsignature", "1793515200_newsignature"
        )
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "shots.json"
            path.write_text(json.dumps(before), encoding="utf-8")
            with self.assertLogs(F.logger.name, level="INFO") as captured:
                self.assertTrue(F._write_shot_cache_if_changed(path, after))
            self.assertEqual(len(captured.records), 1, captured.output)
            line = captured.records[0].getMessage()
            self.assertIn(
                "path=root.holeShots[0].pin.latitude before=float:30.1 after=float:30.2",
                line,
            )
            self.assertNotIn("1793428809_oldsignature", line)
            self.assertNotIn("1793515200_newsignature", line)

    def test_j1_1_numeric_type_change_still_writes(self):
        """J1.1: Garmin shot comparison keeps core's type-sensitive JSON identity."""
        after = {"holeShots": [{"pin": {"latitude": 30.1}, "value": 1.0}]}
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "shots.json"
            path.write_text(
                json.dumps({"holeShots": [{"pin": {"latitude": 30.1}, "value": 1}]}),
                encoding="utf-8",
            )
            with self.assertLogs(F.logger.name, level="INFO") as captured:
                self.assertTrue(F._write_shot_cache_if_changed(path, after))
            self.assertEqual(len(captured.records), 1, captured.output)
            self.assertIn("before=int:1 after=float:1.0", captured.records[0].getMessage())
