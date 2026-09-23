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


if __name__ == "__main__":
    unittest.main()
