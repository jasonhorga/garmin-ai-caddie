"""Background per-hole prep warming: bounded size, one warmer at a time."""
from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from server_v2 import main


class PrepWarmLimitTests(unittest.TestCase):
    def test_default_is_one_course_and_value_is_clamped(self) -> None:
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("AI_CADDIE_PREP_WARM_COURSES", None)
            self.assertEqual(main._prep_warm_course_limit(), 1)
        for raw, expected in (("0", 0), ("2", 2), ("9", 3), ("-1", 0), ("bad", 1)):
            with patch.dict(os.environ, {"AI_CADDIE_PREP_WARM_COURSES": raw}):
                self.assertEqual(main._prep_warm_course_limit(), expected)


class PrepWarmConcurrencyTests(unittest.TestCase):
    def test_overlapping_warm_is_skipped_not_stacked(self) -> None:
        from ai_caddie.courses import course_prep

        with patch.object(course_prep, "prep_nine") as prep_nine, \
                patch.object(course_prep, "available_prep_holes", return_value=[1, 2]), \
                patch.object(course_prep, "effective_club_ladder", return_value=[("1W", 230)]):
            self.assertTrue(main._PREP_WARM_LOCK.acquire(blocking=False))
            try:
                main._warm_course_prep(31794, "me")  # another warmer holds the lock
            finally:
                main._PREP_WARM_LOCK.release()
            prep_nine.assert_not_called()
            main._warm_course_prep(31794, "me")
            prep_nine.assert_called_once()
            self.assertFalse(prep_nine.call_args.kwargs["render"])


class PrepWarmTeeTests(unittest.TestCase):
    def _warm(self, tee_box, resolved):
        from ai_caddie.courses import course_prep

        with patch.object(course_prep, "prep_nine") as prep_nine, \
                patch.object(course_prep, "available_prep_holes", return_value=[1]), \
                patch.object(course_prep, "effective_club_ladder", return_value=[]), \
                patch("ai_caddie.caddie.analysis.tee_set_for_box", return_value=resolved) as resolve:
            main._warm_course_prep(31795, "me", tee_box=tee_box)
        return prep_nine.call_args.kwargs["tee_set"], resolve

    def test_warm_fills_the_selected_tee_cache_entry(self) -> None:
        tee_set, resolve = self._warm("red", 4)
        self.assertEqual(tee_set, 4)
        resolve.assert_called_once_with(31795, "red", colour_fallback=False)  # same rule as /prep

    def test_unknown_or_missing_tee_warms_the_default_entry(self) -> None:
        for tee_box in (None, "", "unknown"):
            tee_set, resolve = self._warm(tee_box, 4)
            self.assertIsNone(tee_set)
            resolve.assert_not_called()


class BootPrepWarmDelayTests(unittest.TestCase):
    def test_default_delay_and_clamping(self) -> None:
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("AI_CADDIE_PREP_WARM_BOOT_DELAY_S", None)
            self.assertEqual(main._boot_prep_warm_delay_s(), 120.0)
        for raw, expected in (("0", 0.0), ("30", 30.0), ("-5", 0.0), ("99999", 3600.0), ("nan", 120.0), ("x", 120.0)):
            with patch.dict(os.environ, {"AI_CADDIE_PREP_WARM_BOOT_DELAY_S": raw}):
                self.assertEqual(main._boot_prep_warm_delay_s(), expected)

    def test_only_the_first_course_waits_for_the_boot_delay(self) -> None:
        waits: list[float] = []
        with patch.object(main._PREP_WARM_DELAY_EVENT, "wait", side_effect=lambda seconds: waits.append(seconds)), \
                patch.object(main, "_PREP_WARM_LOCK") as lock, \
                patch("ai_caddie.courses.course_prep.prep_nine"), \
                patch("ai_caddie.courses.course_prep.available_prep_holes", return_value=[1]), \
                patch("ai_caddie.courses.course_prep.effective_club_ladder", return_value=[]):
            lock.acquire.return_value = True
            warm = main._delayed_prep_warmer("me", 120.0)
            warm(1)
            warm(2)
            warm(3)
        self.assertEqual(waits, [120.0])

    def test_sync_triggered_warm_does_not_wait(self) -> None:
        with patch.object(main._PREP_WARM_DELAY_EVENT, "wait") as wait, \
                patch("ai_caddie.courses.course_prep.prep_nine"), \
                patch("ai_caddie.courses.course_prep.available_prep_holes", return_value=[1]), \
                patch("ai_caddie.courses.course_prep.effective_club_ladder", return_value=[]):
            main._delayed_prep_warmer("me", 0.0)(1)
        wait.assert_not_called()


if __name__ == "__main__":
    unittest.main()
