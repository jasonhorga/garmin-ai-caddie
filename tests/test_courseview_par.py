import unittest
from pathlib import Path

from ai_caddie.geometry.inspect_courseview_release import inspect_release

FIX = Path(__file__).parent / "fixtures"


def _release(name: str) -> dict:
    return inspect_release((FIX / name).read_bytes())


class ReleaseParDecodeTests(unittest.TestCase):
    def test_decodes_par_and_handicap_for_unplayed_course(self) -> None:
        info = _release("courseview_release_31936.pb")  # 钟山 C Valley (never played)
        pars = [h["par"] for h in info["holes"]]
        hcaps = [h["handicap"] for h in info["holes"]]
        self.assertEqual(pars, [4, 5, 3, 4, 3, 4, 4, 5, 4])
        self.assertEqual(sum(pars), 36)
        self.assertEqual(hcaps, [6, 3, 2, 1, 9, 5, 8, 7, 4])

    def test_nine_mapping_front_and_back_match_played_card(self) -> None:
        front = [h["par"] for h in _release("courseview_release_31870.pb")["holes"]]
        back = [h["par"] for h in _release("courseview_release_31871.pb")["holes"]]
        self.assertEqual(front, [5, 4, 3, 4, 4, 4, 5, 3, 4])
        self.assertEqual(back, [4, 5, 4, 4, 3, 5, 3, 4, 4])


from unittest.mock import patch
from ai_caddie.courses import course_reference as cr


class CourseviewParTests(unittest.TestCase):
    def test_courseview_par_from_cached_release(self) -> None:
        holes = inspect_release((FIX / "courseview_release_31936.pb").read_bytes())["holes"]
        with patch.object(cr, "_release_holes", return_value=holes):
            self.assertEqual(cr.courseview_par(31936), [4, 5, 3, 4, 3, 4, 4, 5, 4])

    def test_courseview_par_none_when_no_release(self) -> None:
        with patch.object(cr, "_release_holes", return_value=None):
            self.assertIsNone(cr.courseview_par(99999, allow_fetch=False))
