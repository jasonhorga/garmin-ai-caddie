"""The round package maps the requested loop order onto physical holes (test-plan 4.1, 4.3).

Loops 31870 / 31871 are the 9-hole CourseView release fixtures (银杏湖 B / C); 31795 is the
18-hole fixture course, whose release facts are supplied in memory.
"""
from __future__ import annotations

from contextlib import contextmanager
import unittest
from unittest.mock import patch

from fastapi import BackgroundTasks

from tests.product.test_c36_cold_release_start import ROUND_PARS, _cache_release, _release_bytes, fake_garmin
from tests.service_logging import ServiceLoggingIsolationMixin

EIGHTEEN = 31795
B, C = ROUND_PARS[:9], ROUND_PARS[9:]


def no_provider(*_args, **_kwargs):
    raise AssertionError("Garmin release provider called for a cached course")


@contextmanager
def eighteen_hole_release():
    """The 18-hole fixture course has a cached release with 18 par-4 holes."""
    from ai_caddie.caddie import mobile_live as ml
    from ai_caddie.courses import course_reference as cr

    info, par = cr.courseview_release_info, cr.courseview_par

    def release_info(global_id, *args, **kwargs):
        if int(global_id) == EIGHTEEN:
            return {"name": "Fixture Eighteen", "holes": [{"par": 4}] * 18}
        return info(global_id, *args, **kwargs)

    def course_par(global_id, *args, **kwargs):
        return [4] * 18 if int(global_id) == EIGHTEEN else par(global_id, *args, **kwargs)

    no_geometry = {"coverage": "missing", "geometryRevision": None, "authorityObservation": "unknown"}
    with patch.object(cr, "courseview_release_info", side_effect=release_info), \
            patch.object(cr, "courseview_par", side_effect=course_par), \
            patch.object(ml, "geometry_coverage_for_hole", return_value=no_geometry):
        yield


def package(loops: str):
    from server_v2 import main, mobile

    return main.mobile_course_package(
        int(loops.split(":")[0]), BackgroundTasks(), round_id=f"loops-{loops}", tee_box="blue",
        loops=loops, background_geometry=True, include_event_cursor=False, player_id=mobile.OWNER_ID,
    )


def hole_map(pkg):
    return [(h["number"], h["sourceGlobalId"], h["sourceLocalHole"], h["par"]) for h in pkg.holes]


def expected(*loops):
    """Round hole n -> (n, physical course, physical hole, par) for the given (gid, first hole, pars)."""
    rows = []
    for gid, first, pars in loops:
        for offset, par in enumerate(pars):
            rows.append((len(rows) + 1, gid, first + offset, par))
    return rows


class Packages(ServiceLoggingIsolationMixin, unittest.TestCase):
    """S-06: the round package maps every loop order to the right physical holes."""

    def test_four_loop_orders_map_physical_holes(self):
        """S-06 [main]: B then C, C then B, front then back, back then front each start an 18-hole round."""
        cases = {
            "31870:all,31871:all": expected((31870, 1, B), (31871, 1, C)),
            "31871:all,31870:all": expected((31871, 1, C), (31870, 1, B)),
            f"{EIGHTEEN}:front,{EIGHTEEN}:back": expected((EIGHTEEN, 1, [4] * 9), (EIGHTEEN, 10, [4] * 9)),
            f"{EIGHTEEN}:back,{EIGHTEEN}:front": expected((EIGHTEEN, 10, [4] * 9), (EIGHTEEN, 1, [4] * 9)),
        }
        for loops, rows in cases.items():
            with self.subTest(loops=loops), fake_garmin(no_provider) as garmin, eighteen_hole_release():
                for gid in (31870, 31871):
                    _cache_release(garmin.courseview, gid)
                self.assertEqual(hole_map(package(loops)), rows)

    def test_never_installed_loops_start_without_visiting_tees(self):
        """S-06: loops whose release was never cached start a full round on the first package call."""
        fetched = []

        def provider(gid, live, *, language_code=None):
            fetched.append(int(gid))
            return _release_bytes(int(gid))

        with fake_garmin(provider):
            pkg = package("31870:all,31871:all")
        self.assertEqual(hole_map(pkg), expected((31870, 1, B), (31871, 1, C)))
        self.assertEqual(sorted(set(fetched)), [31870, 31871])


if __name__ == "__main__":
    unittest.main()
