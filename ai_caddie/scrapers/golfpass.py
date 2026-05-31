"""Deterministic GolfPass scorecard scraper — NO AI.

GolfPass renders a course's scorecard server-side as one HTML table with fixed CSS
classes ``CourseScorecardsItem-hole{1..18}`` (plus ``-out``/``-in``/``-total``). Each
row is a tee's yardages, the handicap/stroke index, or the par row. We extract every
hole cell with a single regex and classify each row purely by its numeric values:

* par row     -> every value in 3..6 and the 9/18-hole total ~= 36 / 72
* yardage row -> every value large (>= 70)
* index row   -> a permutation of small distinct ranks (ignored here)

Pure parsing lives in :func:`parse_scorecard` (offline-testable against saved HTML).
:func:`fetch_scorecard_html` is the only networked function.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

_CELL = re.compile(r"CourseScorecardsItem-hole(\d{1,2})\"[^>]*>\s*([0-9]{1,3})\s*<")
_COURSE_LINK = re.compile(r"/travel-advisor/courses/(\d+)-([a-z0-9-]+)")

USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"


@dataclass(frozen=True)
class GolfPassScorecard:
    holes: int
    par: list[int]
    front_par: list[int]
    back_par: list[int] | None
    tee_yardages: list[list[int]] = field(default_factory=list)


def _rows(html: str) -> list[list[int | None]]:
    """Group hole cells into rows in document order (a row ends when a hole repeats)."""
    cells = _CELL.findall(html)
    rows: list[dict[int, int]] = []
    cur: dict[int, int] = {}
    for hole, val in cells:
        h = int(hole)
        if h in cur:
            rows.append(cur)
            cur = {}
        cur[h] = int(val)
    if cur:
        rows.append(cur)
    out: list[list[int | None]] = []
    for r in rows:
        width = max(r)
        out.append([r.get(i) for i in range(1, width + 1)])
    return out


def _is_par_row(vals: list[int]) -> bool:
    n = len(vals)
    if n not in (9, 18) or not all(3 <= v <= 6 for v in vals):
        return False
    tot = sum(vals)
    return (n == 9 and 33 <= tot <= 39) or (n == 18 and 66 <= tot <= 78)


def parse_scorecard(html: str) -> GolfPassScorecard:
    """Parse par + tee yardages from a GolfPass course page. Deterministic, offline."""
    rows = _rows(html)
    par: list[int] = []
    yardages: list[list[int]] = []
    for seq in rows:
        vals = [v for v in seq if v is not None]
        if not vals:
            continue
        if not par and _is_par_row(vals):
            par = vals
        elif len(vals) in (9, 18) and all(v >= 70 for v in vals):
            yardages.append(vals)
    front = par[:9]
    back = par[9:18] if len(par) >= 18 else None
    return GolfPassScorecard(holes=len(par), par=par, front_par=front, back_par=back, tee_yardages=yardages)


def combo_nines_from_url(url: str) -> tuple[str, str] | None:
    """From a course URL slug like '...-mountain-lake-course' return ('mountain','lake').

    GolfPass names an 18-hole combo as ``<front>-<back>-course``; holes 1-9 are the
    front nine, 10-18 the back. Returns lowercased nine names, or None if not a combo.
    """
    m = _COURSE_LINK.search(url)
    if not m:
        return None
    slug = m.group(2)
    slug = re.sub(r"-course$", "", slug)
    parts = slug.split("-")
    # the trailing two tokens of a "<...>-<front>-<back>" combo are the nine names
    if len(parts) >= 2:
        return parts[-2], parts[-1]
    return None


def course_links(html: str) -> list[tuple[str, str]]:
    """Extract (course_id, slug) pairs from a GolfPass search/directory page."""
    seen: dict[str, str] = {}
    for cid, slug in _COURSE_LINK.findall(html):
        seen.setdefault(cid, slug)
    return list(seen.items())


def fetch_scorecard_html(url: str, *, timeout: float = 20.0) -> str:
    """GET a GolfPass course page. The ONLY networked call in this module."""
    import requests

    resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=timeout)
    resp.raise_for_status()
    return resp.text
