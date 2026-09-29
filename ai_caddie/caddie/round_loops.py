"""B4b-2 round loops: the one strict parser, resolver and invariant checker.

A round is one or two ordered loops. Each loop is ``(globalId, half)`` with ``half`` = ``all`` for
an authoritative 9-hole loop, or ``front`` / ``back`` for a half of an authoritative 18-hole
course. The package route and the install-status route both go through
:func:`resolve_round_loops`, so a request that cannot be proven never gets a ``loopKey``.

Course shape (hole count + physical venue) comes from the Garmin CourseView release or from a
fact that proves it (a physical hole 10+ exists only on an 18-hole course). When neither is
available the request is unprovable and is rejected / degraded — never guessed.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Iterable, Mapping

ROUND_LOOP_HALVES = ("all", "front", "back")
ROUND_LOOP_HOLES = 9
ROUND_LOOP_STARTS = (1, 1 + ROUND_LOOP_HOLES)


class RoundLoopError(ValueError):
    """A ``loops=`` request, or a package, that does not name one unambiguous round order."""


@dataclass(frozen=True)
class CourseShape:
    """Authoritative physical shape of one Garmin course: 9 (a loop) or 18 holes, and its venue."""

    holes: int
    venue: str


def parse_round_loops(raw: str | None, *, path_global_id: int) -> list[tuple[int, str]]:
    """Parse ``G:H[,G2:H2]`` into the round's ordered loops (duplicates allowed).

    Syntax only; :func:`resolve_round_loops` proves the loops against course shapes. Empty
    entries (leading, trailing or doubled commas) are rejected, never dropped, so a malformed
    request cannot alias a valid one.
    """
    text = str(raw or "")
    parts = [part.strip() for part in text.split(",")]
    if any(not part for part in parts):
        raise RoundLoopError("loops must not contain empty entries")
    if not 1 <= len(parts) <= 2:
        raise RoundLoopError("loops must name one or two ordered loops")
    loops: list[tuple[int, str]] = []
    for entry in parts:
        gid_text, separator, half = entry.partition(":")
        gid_text = gid_text.strip()
        if not separator or not (gid_text.isascii() and gid_text.isdigit()):
            raise RoundLoopError(f"loop {entry!r} must be globalId:half")
        gid = int(gid_text)
        half = half.strip()
        if gid <= 0 or half not in ROUND_LOOP_HALVES:
            raise RoundLoopError(f"loop {entry!r} must be a positive globalId and all|front|back")
        loops.append((gid, half))
    if loops[0][0] != int(path_global_id):
        raise RoundLoopError("the first loop must be the requested course")
    return loops


def round_loop_key(loops: Iterable[tuple[int, str]]) -> str:
    """The canonical ordered loop identity: order and duplicates are preserved."""
    return "+".join(f"{int(gid)}:{half}" for gid, half in loops)


def source_start_hole(half: str) -> int:
    return ROUND_LOOP_STARTS[1] if half == "back" else ROUND_LOOP_STARTS[0]


def round_loops_table(loops: list[tuple[int, str]]) -> list[dict[str, Any]]:
    return [
        {
            "globalId": int(gid),
            "half": half,
            "roundStartHole": ROUND_LOOP_STARTS[index],
            "sourceStartHole": source_start_hole(half),
            "holeCount": ROUND_LOOP_HOLES,
        }
        for index, (gid, half) in enumerate(loops)
    ]


def resolve_round_loops(
    loops: list[tuple[int, str]],
    shape_of: Callable[[int], CourseShape | None],
) -> list[tuple[int, str]]:
    """Prove an ordered loop request against authoritative course shapes.

    Raises :class:`RoundLoopError` unless every course is known, ``all`` names a 9-hole loop,
    ``front`` / ``back`` name a half of an 18-hole course, and every loop is on one venue.
    """
    if not 1 <= len(loops) <= 2:
        raise RoundLoopError("loops must name one or two ordered loops")
    venues: set[str] = set()
    for gid, half in loops:
        shape = shape_of(int(gid))
        if shape is None:
            raise RoundLoopError(f"course {gid} has no authoritative hole layout")
        if half == "all" and shape.holes != ROUND_LOOP_HOLES:
            raise RoundLoopError(f"{gid}:all needs an authoritative 9-hole loop")
        if half in ("front", "back") and shape.holes != 2 * ROUND_LOOP_HOLES:
            raise RoundLoopError(f"{gid}:{half} needs an authoritative 18-hole course")
        venues.add(shape.venue)
    if len(venues) > 1:
        raise RoundLoopError("every loop must belong to the same physical venue")
    return loops


def validate_round_identity(
    round_loops: Any,
    loop_key: Any,
    holes: Any,
) -> None:
    """The complete v2 invariant of a package with playable holes.

    One or two loops; round starts 1 then 10; exactly nine holes per loop; ``sourceStartHole``
    matches ``half``; ``loopKey`` is the canonical key of the table; hole numbers are unique; and
    every hole matches its row (``sourceGlobalId``, ``sourceLocalHole`` and ``courseHoleNumber``).
    """
    if not isinstance(round_loops, list) or not 1 <= len(round_loops) <= 2:
        raise RoundLoopError("roundLoops must list one or two loops")
    entries: list[tuple[int, str]] = []
    for index, row in enumerate(round_loops):
        if not isinstance(row, Mapping):
            raise RoundLoopError("roundLoops rows must be objects")
        gid, half = row.get("globalId"), row.get("half")
        if not _positive_int(gid) or half not in ROUND_LOOP_HALVES:
            raise RoundLoopError("a loop needs a positive globalId and all|front|back")
        if row.get("roundStartHole") != ROUND_LOOP_STARTS[index]:
            raise RoundLoopError("loops start on round hole 1, then 10")
        if row.get("sourceStartHole") != source_start_hole(half):
            raise RoundLoopError(f"{half} starts on physical hole {source_start_hole(half)}")
        if row.get("holeCount") != ROUND_LOOP_HOLES:
            raise RoundLoopError("every loop has exactly nine holes")
        entries.append((int(gid), str(half)))
    if loop_key != round_loop_key(entries):
        raise RoundLoopError("loopKey must be the canonical key of roundLoops")
    if not isinstance(holes, list):
        raise RoundLoopError("holes must be a list")
    expected: dict[int, tuple[int, int, int]] = {}
    for index, (gid, half) in enumerate(entries):
        for offset in range(ROUND_LOOP_HOLES):
            number = ROUND_LOOP_STARTS[index] + offset
            local = source_start_hole(half) + offset
            expected[number] = (gid, local, local if half != "all" else number)
    seen: set[int] = set()
    for hole in holes:
        if not isinstance(hole, Mapping):
            raise RoundLoopError("package holes must be objects")
        number = hole.get("number")
        for key in ("number", "sourceGlobalId", "sourceLocalHole", "courseHoleNumber"):
            if not _positive_int(hole.get(key)):
                raise RoundLoopError(f"package hole is missing {key}")
        if number in seen:
            raise RoundLoopError(f"round hole {number} appears twice")
        seen.add(number)
        row = expected.get(number)
        actual = (hole["sourceGlobalId"], hole["sourceLocalHole"], hole["courseHoleNumber"])
        if row is None or actual != row:
            raise RoundLoopError(f"round hole {number} does not match its loop row")
    if seen != set(expected):
        raise RoundLoopError("every loop must carry all nine of its holes")


def _positive_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0
