"""Garmin course-update check: given the courses we hold (globalId + the CourseView release we've
decoded), ask Garmin which were re-surveyed / got a newer release. Deterministic protobuf decode,
best-effort, never raises — mirrors ``course_search`` / ``inspect_courseview_release``.

This pairs with the "复盘按打球日期取对版几何" logic (``inspect_courseview_release.load_layout_by_date``):
knowing a course changed tells us to re-pull its date-versioned layout + re-decode its geometry.

Endpoint — VERIFIED live from this box, ANONYMOUS (no cookie needed)::

    POST https://omt.garmin.cn/CourseViewData/checkForCourseUpdates
    Content-Type: application/json
    body: a JSON ARRAY of CourseIdentifier objects
    -> 200 application/protobuf   (an EMPTY body == none of the listed courses have an update)

Request shape — empirically established (2026-07-10):
  * GET → ``405`` with ``allow: POST``; the endpoint only accepts POST.
  * ``{}`` (a JSON object) → ``400 "... requires a JSON array (e.g. [1,2,3])"``: the body must be a
    JSON *array* whose elements deserialize to ``Garmin.Omt.CourseViewData.Dto.CourseIdentifier``.
    A bare-int element → ``400 "Error converting value 31936 to type ... CourseIdentifier"``; object
    elements are accepted (``200``). The server carries a ``garmin-trace-id`` header.
  * The natural CourseView identity is the pair ``inspect_release`` already decodes — f1=globalId,
    f3=releaseId (e.g. "006-D2419-44") — so we send ``{"globalId": N, "releaseId": "..."}``. Unknown
    fields are tolerantly ignored (an over-broad identifier still 200s).

Response shape — INFERRED, NOT observed live.  **BLOCKER**: every request from this box returned an
EMPTY ``200`` (``content-length: 0``). The endpoint is a *diff* — it emits a row only for a course
whose *claimed* release it recognises as genuinely stale — and we have no historical release string
to claim; nor could black-box probing reveal the exact release field name (the server silently
swallows unknown *and* mistyped fields: even overflow-large ints and a 30-alias "kitchen-sink" body
all 200-empty). So ``parse_course_updates`` follows the CourseView protobuf *family* convention (a
top-level repeated record carrying the course globalId as a varint + the new release id as a
release-shaped string) and is exercised by a synthetic fixture in ``tests/test_course_updates.py``.
When a real non-empty response is captured (an app MITM, or a valid stale ``(gid, release)`` pair),
confirm/adjust the extraction in ``_decode_update_record``.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Iterable, Mapping
from urllib.request import Request, urlopen

from ai_caddie.geometry.inspect_courseview_release import BASE, parse_fields

UPDATE_URL = f"{BASE}/checkForCourseUpdates"

# A CourseView release id looks like "006-D2419-44" / "004-D0000-00" — digits, a lettered middle
# group, digits. Used to spot the (new) release string inside an update record.
_RELEASE_RE = re.compile(r"\d+-[A-Za-z]\w*-\d+")

# Plausible globalId range, used only when the caller did not pass ``known_ids`` to disambiguate the
# gid varint from a version/handicap varint in the same record.
_GID_MIN = 1000
_GID_MAX = 999_999_999


@dataclass
class CourseIdentifier:
    """One course we hold: its globalId and (optionally) the release string we've decoded."""

    global_id: int
    release_id: str | None = None

    def to_json(self) -> dict:
        out: dict = {"globalId": int(self.global_id)}
        if self.release_id:
            out["releaseId"] = str(self.release_id)
        return out


@dataclass
class CourseUpdate:
    """A course Garmin reports as having a newer release than the one we claimed."""

    global_id: int
    release_id: str | None = None
    version: int | None = None
    extra_varints: list[int] = field(default_factory=list)


def build_request_body(identifiers: Iterable[CourseIdentifier]) -> bytes:
    """Serialize the JSON array the endpoint requires (the request container is verified live)."""
    return json.dumps([c.to_json() for c in identifiers]).encode("utf-8")


def _decode_update_record(raw: bytes, known: set[int]) -> CourseUpdate | None:
    """Pull a course globalId (+ optional new release id / version) out of one repeated record.

    Field-number tolerant: we scan the record's sub-fields and pick the globalId by value (a varint
    in ``known`` when the caller supplied the queried gids, else one in the plausible gid range) and
    the release id by shape — so the decoder survives whatever exact field numbers the real response
    turns out to use.
    """
    varints: list[int] = []
    release: str | None = None
    try:
        for _sub_no, sub_wire, sub_value, _sub_raw in parse_fields(raw):
            if sub_wire == 0 and sub_value is not None:
                varints.append(sub_value)
            elif sub_wire == 2 and isinstance(sub_value, str) and release is None and _RELEASE_RE.search(sub_value):
                release = sub_value
    except Exception:
        pass

    global_id: int | None = None
    if known:
        global_id = next((v for v in varints if v in known), None)
    if global_id is None:
        candidates = [v for v in varints if _GID_MIN <= v <= _GID_MAX and v not in {global_id}]
        global_id = max(candidates, default=None) if candidates else None
    if global_id is None:
        return None

    others = [v for v in varints if v != global_id]
    version = min(others) if others else None
    return CourseUpdate(global_id=int(global_id), release_id=release, version=version, extra_varints=others)


def parse_course_updates(pb: bytes, *, known_ids: Iterable[int] | None = None) -> list[CourseUpdate]:
    """Decode the update-check protobuf into ``CourseUpdate`` rows (best-effort, never raises).

    Every top-level length-delimited field is treated as one course-update record. Pass the gids you
    queried as ``known_ids`` to pin globalId extraction exactly.
    """
    known = {int(g) for g in known_ids} if known_ids else set()
    out: list[CourseUpdate] = []
    try:
        for _field_no, wire_type, _value, raw in parse_fields(pb):
            if wire_type != 2 or raw is None:
                continue
            rec = _decode_update_record(raw, known)
            if rec is not None:
                out.append(rec)
    except Exception:
        return out
    return out


def _post_updates(identifiers: list[CourseIdentifier], *, timeout: int = 30) -> bytes:
    """POST the identifier array — the only networked call here (anonymous, no cookie)."""
    req = Request(
        UPDATE_URL,
        data=build_request_body(identifiers),
        headers={
            "User-Agent": "Mozilla/5.0",
            "Content-Type": "application/json",
            "Accept": "application/protobuf",
        },
        method="POST",
    )
    with urlopen(req, timeout=timeout) as response:
        return response.read()


def fetch_course_updates(
    courses: Mapping[int, str | None] | Iterable[int],
    *,
    allow_fetch: bool = True,
) -> list[CourseUpdate]:
    """Query Garmin and return the ``CourseUpdate`` rows for the given courses.

    ``courses`` is either a mapping ``{globalId: heldReleaseId}`` (preferred — the endpoint is a diff
    and needs the release we hold to tell us it's stale) or a bare iterable of globalIds. Empty list
    on a network failure or ``allow_fetch=False`` — never raises.
    """
    identifiers = _as_identifiers(courses)
    if not identifiers or not allow_fetch:
        return []
    try:
        pb = _post_updates(identifiers)
    except Exception:
        return []
    return parse_course_updates(pb, known_ids=[c.global_id for c in identifiers])


def check_course_updates(
    courses: Mapping[int, str | None] | Iterable[int],
    *,
    allow_fetch: bool = True,
) -> dict[int, bool]:
    """Report which of the given globalIds Garmin flags as having a newer release.

    Returns ``{globalId: has_update}`` for every queried course on success (a gid appearing in the
    response == it has an update). Returns ``{}`` when the check could not run (network failure or
    ``allow_fetch=False``) so callers can tell "no updates" (all-``False``) apart from "couldn't
    check" (empty). Never raises.
    """
    identifiers = _as_identifiers(courses)
    if not identifiers or not allow_fetch:
        return {}
    try:
        pb = _post_updates(identifiers)
    except Exception:
        return {}
    queried = [c.global_id for c in identifiers]
    updated = {u.global_id for u in parse_course_updates(pb, known_ids=queried)}
    return {gid: gid in updated for gid in queried}


def _as_identifiers(courses: Mapping[int, str | None] | Iterable[int]) -> list[CourseIdentifier]:
    if isinstance(courses, Mapping):
        return [CourseIdentifier(int(gid), rel) for gid, rel in courses.items()]
    return [CourseIdentifier(int(gid)) for gid in courses]
