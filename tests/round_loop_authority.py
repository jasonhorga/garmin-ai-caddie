"""Test helper: authoritative course shapes for the fixture history courses.

Production reads a course's hole count only from its Garmin CourseView release
(``mobile_live._authoritative_course_holes``). The test environment has no release for the
fixture courses, so a past fixture round would (correctly) degrade to a package without a loop
table. Tests that exercise the round package's other content use :func:`fixture_course_authority`
to stand in for those releases. The real lookup runs first, so a test that patches
``_courseview_segment_resolver`` itself still wins.
"""

from __future__ import annotations

from unittest.mock import patch

from ai_caddie.caddie import mobile_live

FIXTURE_COURSE_HOLES = {
    31795: 18,
    41825: 9,
}

_ORIGINAL = mobile_live._authoritative_course_holes


def _with_fixture_fallback(global_id: int) -> int | None:
    holes = _ORIGINAL(global_id)
    if holes is not None:
        return holes
    return FIXTURE_COURSE_HOLES.get(int(global_id))


def fixture_course_authority():
    """A ``patch`` (usable as decorator, context manager or ``start()``) for fixture shapes."""
    return patch.object(mobile_live, "_authoritative_course_holes", side_effect=_with_fixture_fallback)
