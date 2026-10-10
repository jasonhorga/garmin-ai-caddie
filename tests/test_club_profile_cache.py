from __future__ import annotations

import json
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from ai_caddie.core import data


def _write_round(directory: Path, name: str, meters: list[float], club_name: str = "7I") -> Path:
    path = directory / f"{name}.json"
    path.write_text(json.dumps({
        "holeShots": [{"holeNumber": 1, "shots": [
            {"meters": value, "shotType": "APPROACH", "clubId": 2} for value in meters
        ]}],
        "clubDetails": [{"id": 2, "name": club_name}],
    }))
    return path


class ClubProfileCacheTests(unittest.TestCase):
    """build_club_profiles reuses its result while the shot files and clubs.json are unchanged."""

    def setUp(self) -> None:
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.shots = self.root / "shots"
        self.shots.mkdir()
        _write_round(self.shots, "r1", [150.0, 152.0])
        clubs = patch.object(data, "CLUBS_FILE", self.root / "clubs.json")
        clubs.start()
        self.addCleanup(clubs.stop)
        data._CLUB_PROFILE_CACHE.clear()
        self.addCleanup(data._CLUB_PROFILE_CACHE.clear)

    def _profiles(self, **kwargs):
        return data.build_club_profiles(shot_dirs=[self.shots], **kwargs)

    def test_unchanged_inputs_are_read_once(self) -> None:
        with patch.object(data, "_build_club_profiles_uncached", wraps=data._build_club_profiles_uncached) as build:
            first = self._profiles()
            second = self._profiles()
        self.assertEqual(first, second)
        self.assertEqual(first["7I"]["sampleSize"], 2)
        build.assert_called_once()

    def test_a_new_rewritten_or_removed_round_is_read_again(self) -> None:
        self.assertEqual(self._profiles()["7I"]["sampleSize"], 2)
        added = _write_round(self.shots, "r2", [160.0])
        self.assertEqual(self._profiles()["7I"]["sampleSize"], 3)
        _write_round(self.shots, "r2", [160.0, 161.0, 162.0])
        os.utime(added, ns=(1, 1))  # even with an older mtime, the size/mtime pair changed
        self.assertEqual(self._profiles()["7I"]["sampleSize"], 5)
        added.unlink()
        self.assertEqual(self._profiles()["7I"]["sampleSize"], 2)

    def test_a_same_size_rewrite_that_keeps_the_mtime_is_read_again(self) -> None:
        """A re-sync rewriting 150 -> 151 m (same byte count) in the same mtime tick, or a restore
        that keeps mtimes: ctime/inode still change."""
        path = self.shots / "r1.json"
        before = os.stat(path)
        self.assertEqual(self._profiles()["7I"]["median"], 150.0)
        _write_round(self.shots, "r1", [151.0, 152.0])
        os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns))
        after = os.stat(path)
        self.assertEqual((after.st_size, after.st_mtime_ns), (before.st_size, before.st_mtime_ns))
        self.assertEqual(self._profiles()["7I"]["median"], 151.0)

    def test_clubs_json_counts_only_when_overrides_apply(self) -> None:
        self.assertIn("7I", self._profiles())
        self.assertIn("7I", self._profiles(apply_overrides=False))
        (self.root / "clubs.json").write_text(json.dumps({"2": {"name": "OWNER-6I"}}))
        self.assertIn("OWNER-6I", self._profiles(), "the owner's override is picked up")
        member = self._profiles(apply_overrides=False)
        self.assertIn("7I", member)
        self.assertNotIn("OWNER-6I", member)

    def test_callers_get_their_own_copy(self) -> None:
        first = self._profiles()
        first["7I"]["median"] = -1
        first["Driver"] = {}
        second = self._profiles()
        self.assertNotEqual(second["7I"]["median"], -1)
        self.assertNotIn("Driver", second)

    def test_separate_directories_and_thresholds_do_not_share_a_result(self) -> None:
        other = self.root / "other"
        other.mkdir()
        _write_round(other, "x", [90.0], club_name="PW")
        self.assertIn("7I", self._profiles())
        self.assertEqual(set(data.build_club_profiles(shot_dirs=[other])), {"PW"})
        self.assertEqual(self._profiles(min_distance_m=151.0)["7I"]["sampleSize"], 1)

    def test_a_replaced_reader_bypasses_the_cache(self) -> None:
        self._profiles()
        with patch.object(data, "read_json", return_value={"_no_data": True}):
            self.assertEqual(self._profiles(), {})
        self.assertIn("7I", self._profiles())


if __name__ == "__main__":
    unittest.main()
