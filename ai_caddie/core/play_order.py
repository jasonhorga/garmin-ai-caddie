"""The shared round-order rule used by server-side course warming.

The iPhone offline downloader walks the round's ordered holes from the hole currently being played,
wrapping at the end.  Keeping that small rule here prevents the install and topo warmers from
quietly reverting to numeric sort when a round starts on the back nine.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any, TypeVar


T = TypeVar("T")


def hole_number(value: Any) -> int | None:
    """Extract the round/display number accepted by the server's hole row shapes."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return int(value)
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, dict):
        for key in ("displayHole", "number", "hole", "roundHole"):
            raw = value.get(key)
            if raw is None or isinstance(raw, bool):
                continue
            try:
                parsed = int(raw)
            except (TypeError, ValueError):
                continue
            if parsed > 0:
                return parsed
    return None


def hole_key(value: Any) -> Any:
    """Return the physical identity used to collapse repeated loop visits."""
    if isinstance(value, dict):
        explicit = value.get("key")
        if explicit is not None:
            return str(explicit)
        global_id = value.get("globalId") or value.get("sourceGlobalId")
        local_hole = value.get("localHole") or value.get("sourceLocalHole")
        if global_id is not None and local_hole is not None:
            try:
                return (int(global_id), int(local_hole))
            except (TypeError, ValueError):
                pass
    try:
        hash(value)
    except TypeError:
        return id(value)
    return value


def expand_display_holes(values: Iterable[T]) -> list[T]:
    """Expand journal rows that record multiple display visits of one physical hole."""
    expanded: list[T] = []
    for value in values:
        if not isinstance(value, dict):
            expanded.append(value)
            continue
        raw_holes = value.get("displayHoles")
        if not isinstance(raw_holes, (list, tuple)) or not raw_holes:
            expanded.append(value)
            continue
        for raw in raw_holes:
            try:
                display = int(raw)
            except (TypeError, ValueError):
                continue
            if display <= 0:
                continue
            copy = dict(value)
            copy["displayHole"] = display
            expanded.append(copy)  # type: ignore[arg-type]
    if expanded and all(isinstance(value, dict) for value in expanded):
        expanded.sort(key=lambda value: int(value.get("displayHole") or value.get("localHole") or 0))
    return expanded


def play_order(
    values: Iterable[T],
    current_hole: int | None = 1,
    *,
    number: Callable[[T], int | None] | None = None,
) -> list[T]:
    """Return ``values`` rotated to the current hole, preserving round order.

    Unknown or missing current holes use the first item, matching
    ``OfflineCourseDownloadOrder.ranks``.  The function does not sort the input: callers pass the
    round order (or rows with their display-hole order) and receive the same order after rotation.
    """
    # Rotate round visits first, then collapse repeated physical holes. This preserves the
    # display-hole visit that contains the active hole in a two-loop nine-hole round.
    source = list(values)
    if not source:
        return []
    extract = number or hole_number
    target = int(current_hole or 1)
    start = next(
        (index for index, value in enumerate(source) if extract(value) == target),
        0,
    )
    rotated = source[start:] + source[:start]
    ordered: list[T] = []
    seen: set[Any] = set()
    for value in rotated:
        key = hole_key(value)
        if key in seen:
            continue
        seen.add(key)
        ordered.append(value)
    return ordered

