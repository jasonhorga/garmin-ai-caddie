"""Deterministic Garmin course-name authority helpers.

Garmin exposes two related but different names:

* ``courseSnapshots[0].name`` is the localized name attached to a played
  scorecard (and is the only trusted source for a localized venue name).
* CourseView ``name`` identifies one playable layout and may contain its
  single loop label.

Played 18-hole scorecards sometimes append a route such as ``A/C`` or
``A+B``.  That route is a fact about that round, not the identity of one
  playable layout.  This module keeps the route available as an alias for
  search while exposing only a base venue and, when it is unambiguous, one
  segment label for catalogue presentation.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
import re
from typing import Any, Iterable, Mapping


_PLACEHOLDER_NAMES = {"unknown", "unknown course", "unnamed course", "n/a", "-"}
GARMIN_SNAPSHOT_NAME_SOURCE = "garmin_scorecard_snapshot"
_MANUAL_SOURCE_NAMES = {
    "manual",
    "manual_entry",
    "phone",
    "user",
    "user_entered",
}
_COMPOSITE_SEGMENT_RE = re.compile(r"[+/]")
_COMPACT_COMPOSITE_SEGMENT_RE = re.compile(r"^[A-H]{2,4}$", re.IGNORECASE)
_TRAILING_ROUTE_RE = re.compile(r"(?i)([A-H](?:\s*[/+]\s*[A-H]){1,3})$")
_TRAILING_COMPACT_ROUTE_RE = re.compile(r"(?i)\s+([A-H]{2,4})$")
_SEPARATOR_RE = re.compile(r"\s*~\s*")


@dataclass(frozen=True)
class GarminNameIdentity:
    """A venue plus an optional single playable-layout label."""

    venue: str
    segment: str | None = None
    source: str = "history_fallback"
    aliases: tuple[str, ...] = ()


@dataclass(frozen=True)
class CanonicalCourseIdentity:
    """The backend-owned identity shared by every catalogue/client surface.

    ``name`` is always the physical venue title.  A selectable CourseView loop
    is carried separately in ``segment``; it is never appended to the venue
    title.  No value in this object is translated or inferred from a global id.
    """

    name: str
    venue: str
    segment: str | None = None
    source: str | None = None


def canonical_course_identity(
    provider_name: Any,
    identity: GarminNameIdentity | None = None,
    *,
    segment_override: str | None = None,
    holes: int | None = None,
) -> CanonicalCourseIdentity:
    """Resolve one stable display identity from already-observed Garmin values.

    Callers must pass only a trusted identity when it is intended to replace a
    provider spelling.  The guard is repeated here rather than relying on each
    caller: a manually entered Chinese round must never become a catalogue
    translation merely because it was wrapped in ``GarminNameIdentity``.
    """
    trusted_identity = identity if is_trusted_garmin_identity(identity) else None
    display = localized_provider_name(
        provider_name,
        trusted_identity,
        segment_override=segment_override,
        holes=holes,
    )
    venue, suffix = split_garmin_course_name(display)
    venue = normalize_course_text(venue)
    display = normalize_course_text(display)
    segment = normalize_course_text(suffix)
    if not segment or is_composite_segment(segment):
        segment = None
    source = trusted_identity.source if trusted_identity is not None else None
    physical_venue = venue or normalize_course_text(provider_name)
    return CanonicalCourseIdentity(
        # The wire-level `name` is deliberately venue-only.  Keep the factual
        # single-loop suffix in `segment`, where all three clients can render
        # it as independent selection metadata.
        name=physical_venue,
        venue=physical_venue,
        segment=segment,
        source=source,
    )


def is_trusted_garmin_identity(identity: GarminNameIdentity | None) -> bool:
    """Whether an identity came from Garmin's own scorecard snapshot field.

    ``history_fallback`` is intentionally still useful for displaying a manual
    round's name, but it must never overwrite an anonymous CourseView name: a
    manually entered Chinese label is not evidence that Garmin supplied that
    localization.
    """
    return bool(
        identity
        and normalize_course_text(identity.source).casefold() == GARMIN_SNAPSHOT_NAME_SOURCE
    )


def _best_record(records: Iterable[dict[str, Any]]) -> dict[str, Any] | None:
    """Choose one source spelling without inventing a translation.

    CJK is preferred only when it is already present in a Garmin-backed field.
    The explicit snapshot field wins otherwise, followed by the least-derived
    legacy field and the newest observation.  This ordering is shared by
    history cards and reconciliation so each surface tells the same story.
    """
    values = list(records)
    if not values:
        return None

    def score(item: dict[str, Any]) -> tuple[Any, ...]:
        # An already-marked Garmin snapshot is stronger evidence than a legacy
        # normalized field, even when the latter happens to contain CJK text.
        # This prevents a manually-entered/derived Chinese alias from
        # displacing an explicit provider spelling.
        explicit = int(bool(item.get("explicit")))
        cjk = int(contains_cjk(item.get("venue")))
        return (
            int(explicit and cjk),
            explicit,
            cjk,
            -int(item.get("rank", 99)),
            str(item.get("date") or ""),
            str(item.get("raw") or "").casefold(),
        )

    return max(values, key=score)


def normalize_course_text(value: Any) -> str:
    """Collapse incidental whitespace while preserving the provider's spelling."""
    return " ".join(str(value or "").split()).strip()


def is_garmin_source(value: Any) -> bool:
    """Return whether a provenance marker identifies a Garmin-backed record.

    ``source`` is deliberately the boundary here.  Manual phone rounds use
    Garmin's scorecard-shaped storage format too, but their ``courseSnapshots``
    name is the text supplied by the player and must not become a catalogue
    localization merely because the JSON field has the same name.
    """
    source = normalize_course_text(value).casefold()
    return bool(
        source == "garmin"
        or source == GARMIN_SNAPSHOT_NAME_SOURCE
        or source.startswith("garmin_")
        or source.startswith("garmin:")
    )


def _row_source(row: Mapping[str, Any]) -> str:
    # New history rows carry a compact top-level ``source`` marker, while the
    # first normalized Garmin exports only carried the connector name inside
    # ``provenance.sourceConnector``.  Keep an explicit non-Garmin top-level
    # marker authoritative: a manual row can still contain the same raw
    # scorecard envelope, but its name must never become catalogue authority.
    source = row.get("source")
    if source is None or not normalize_course_text(source):
        source = row.get("sourceConnector")
    provenance = row.get("provenance")
    if isinstance(provenance, Mapping):
        nested_source = provenance.get("source")
        connector = provenance.get("sourceConnector")
        if source is None or not normalize_course_text(source):
            source = nested_source
        if source is None or not normalize_course_text(source):
            source = connector
    return normalize_course_text(source).casefold()


def _looks_like_unmarked_garmin_scorecard(row: Mapping[str, Any]) -> bool:
    """Recognise old raw Garmin payloads that predate a top-level source marker.

    This compatibility path is intentionally narrow.  A bare normalized row
    with a field named ``garminSnapshotName`` is not enough evidence; it needs
    the complete raw scorecard/snapshot envelope.  Explicit ``manual`` (or any
    other non-Garmin) marker always wins and disables this fallback.
    """
    if _row_source(row):
        return False
    details = row.get("scorecardDetails")
    snapshots = row.get("courseSnapshots")
    if not isinstance(details, (list, tuple)) or not details:
        return False
    if not isinstance(snapshots, (list, tuple)) or not snapshots:
        return False
    detail = details[0]
    snapshot = snapshots[0]
    if not isinstance(detail, Mapping) or not isinstance(snapshot, Mapping):
        return False
    scorecard = detail.get("scorecard")
    return isinstance(scorecard, Mapping) and bool(
        normalize_course_text(snapshot.get("name"))
    )


def _allows_garmin_snapshot_name(row: Mapping[str, Any]) -> bool:
    """Whether snapshot/name fields may be used as Garmin authority."""
    source = _row_source(row)
    if source in _MANUAL_SOURCE_NAMES or source.startswith("manual"):
        return False
    if source:
        return is_garmin_source(source)
    # A source marker is absent only on old raw Garmin exports.  Do not infer
    # authority from a hand-shaped normalized row.
    return _looks_like_unmarked_garmin_scorecard(row)


def split_garmin_course_name(value: Any) -> tuple[str, str | None]:
    """Return ``(venue, suffix)`` using Garmin's separator and route spellings.

    Older Garmin exports sometimes omit ``~`` and emit names such as
    ``Black Knight B/C`` or ``Black Knight AC``.  Those trailing values are
    played routes, not venue text.  Normalising them here keeps every backend
    endpoint and client from independently leaking a route as the venue.
    """
    text = normalize_course_text(value)
    if not text:
        return "", None
    parts = [part.strip() for part in _SEPARATOR_RE.split(text) if part.strip()]
    if not parts:
        return "", None
    venue = parts[0]
    suffix = " ~ ".join(parts[1:]) if len(parts) > 1 else None
    # A malformed/legacy row can carry a composite route in the venue portion
    # even when another suffix is present.  Strip only unambiguous multi-loop
    # spellings; ordinary names ending in a single letter remain untouched.
    route_match = _TRAILING_ROUTE_RE.search(venue)
    if route_match:
        base = normalize_course_text(venue[: route_match.start()])
        if base:
            venue = base
            if not suffix:
                suffix = normalize_course_text(route_match.group(1))
    elif not suffix:
        compact_match = _TRAILING_COMPACT_ROUTE_RE.search(venue)
        if compact_match and is_composite_segment(compact_match.group(1)):
            base = normalize_course_text(venue[: compact_match.start()])
            if base:
                venue = base
                suffix = normalize_course_text(compact_match.group(1))
    return venue, suffix or None


def is_placeholder_course_name(value: Any) -> bool:
    venue, _suffix = split_garmin_course_name(value)
    return not venue or normalize_course_text(venue).casefold() in _PLACEHOLDER_NAMES


def contains_cjk(value: Any) -> bool:
    """Return whether a name contains a CJK ideograph (not an inferred translation)."""
    text = normalize_course_text(value)
    return any(
        (0x3400 <= ord(char) <= 0x4DBF)
        or (0x4E00 <= ord(char) <= 0x9FFF)
        or (0x20000 <= ord(char) <= 0x2FA1F)
        for char in text
    )


def is_composite_segment(value: Any) -> bool:
    """Whether a suffix names more than one layout/loop.

    Garmin has emitted both separated routes (``A/C`` or ``A+B``) and compact
    loop codes (``AB``, ``AC``, ``ABC``). Keep the latter out of selectable
    segment labels while leaving normal word labels such as ``Ocean`` intact.
    """
    text = normalize_course_text(value)
    if not text:
        return False
    if _COMPOSITE_SEGMENT_RE.search(text):
        return True
    return bool(_COMPACT_COMPOSITE_SEGMENT_RE.fullmatch(text.replace(" ", "")))


def _candidate_values(row: Mapping[str, Any]) -> list[tuple[str, int, bool]]:
    """Return raw names with an explicit Garmin snapshot ranked first.

    ``garminSnapshotName`` was added after the first normalized exports.  It is
    only authoritative when the row carries a Garmin provenance marker (or is
    an old, complete raw Garmin envelope).  The remaining fields are retained
    as non-authoritative fallbacks for history/search; no value is translated.
    """
    values: list[tuple[str, int, bool]] = []
    seen: set[str] = set()
    snapshot_allowed = _allows_garmin_snapshot_name(row)

    # Normalized exports carry ``garminSnapshotName`` explicitly.  Accept the
    # exact nested field only for a marked Garmin row (or the narrow legacy raw
    # envelope above).  A manual round deliberately has the same nested shape,
    # so its explicit ``source=manual`` marker prevents this branch.
    nested_snapshot_name = ""
    snapshots = row.get("courseSnapshots")
    if snapshot_allowed and isinstance(snapshots, (list, tuple)) and snapshots:
        first_snapshot = snapshots[0]
        if isinstance(first_snapshot, Mapping):
            nested_snapshot_name = normalize_course_text(first_snapshot.get("name"))
    explicit_values = (
        (
            ("garminSnapshotName", 0, True),
            ("courseSnapshotName", 0, True),
            ("courseSnapshots[0].name", 0, True),
        )
        if snapshot_allowed
        else ()
    )
    snapshots_names = row.get("garminSnapshotNames")
    if snapshot_allowed and isinstance(snapshots_names, (list, tuple)):
        for raw_name in snapshots_names:
            value = normalize_course_text(raw_name)
            if not value or value.casefold() in seen or is_placeholder_course_name(value):
                continue
            seen.add(value.casefold())
            values.append((value, 0, True))
    # API/catalogue rows may carry the same trusted source marker alongside a
    # venue-only field rather than ``garminSnapshotName``.  Treat that field as
    # an explicit Garmin observation without trusting an unmarked ``venueName``.
    if (
        normalize_course_text(row.get("venueNameSource")).casefold()
        == GARMIN_SNAPSHOT_NAME_SOURCE
    ):
        venue_name = normalize_course_text(row.get("venueName"))
        if venue_name and not is_placeholder_course_name(venue_name):
            seen.add(venue_name.casefold())
            values.append((venue_name, 0, True))
    # Rows written by older Garmin syncs predate garminSnapshotName. Their
    # ``course`` value still came directly from courseSnapshots[0].name, so it
    # is safe to treat it as explicit only when the row is marked Garmin (or is
    # the narrow unmarked raw Garmin envelope).
    # A merged 18-hole row inherits ``source=garmin`` from its first member,
    # but its ``course`` value is a derived route assembled from two raw
    # scorecards.  Do not let that inherited marker promote the derived route
    # back to an exact Garmin snapshot source.  The member values remain
    # available through ``garminSnapshotNames`` above.
    legacy_garmin = snapshot_allowed and not bool(row.get("merged"))
    explicit_keys = {item[0] for item in explicit_values}
    for key, rank, explicit in (
        *explicit_values,
        ("courseCanonical", 1, False),
        ("course", 2, False),
        ("courseName", 3, False),
        ("name", 4, False),
    ):
        # A legacy merged row may have inherited a singular snapshot field
        # from its front member. Only the member list is authoritative for a
        # derived row; ignore that stale singular value even if it contains
        # Chinese text.
        if row.get("merged") and key in explicit_keys:
            value = ""
        else:
            value = nested_snapshot_name if key == "courseSnapshots[0].name" else normalize_course_text(row.get(key))
        if key in {"courseCanonical", "course", "courseName", "name"} and legacy_garmin:
            explicit = True
        if not value or value.casefold() in seen or is_placeholder_course_name(value):
            continue
        seen.add(value.casefold())
        values.append((value, rank, explicit))
    return values


def _candidate_records(row: Mapping[str, Any]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    date = _row_date(row)
    for raw, rank, explicit in _candidate_values(row):
        venue, suffix = split_garmin_course_name(raw)
        if not venue or is_placeholder_course_name(venue):
            continue
        records.append(
            {
                "raw": raw,
                "venue": venue,
                "suffix": suffix,
                "rank": rank,
                "explicit": explicit,
                "date": date,
            }
        )
    return records


def _row_date(row: Mapping[str, Any]) -> str:
    return normalize_course_text(row.get("date") or row.get("startTime"))


def select_garmin_name_identity(rows: Iterable[Mapping[str, Any]]) -> GarminNameIdentity | None:
    """Choose a localized venue and an unambiguous single segment from rows.

    The ordering is intentionally conservative: a CJK Garmin snapshot wins
    over an English provider spelling, an explicit snapshot wins over a legacy
    normalized fallback, and composite suffixes never become segment labels.
    Frequency/date only break ties between otherwise equivalent observations.
    """
    records: list[dict[str, Any]] = []
    aliases: set[str] = set()
    for row in rows or ():
        if not isinstance(row, Mapping):
            continue
        row_id = normalize_course_text(row.get("id"))
        for record in _candidate_records(row):
            raw = str(record["raw"])
            venue = str(record["venue"])
            suffix = record["suffix"]
            records.append(
                {
                    **record,
                    "id": row_id,
                }
            )
            aliases.add(raw)
            aliases.add(venue)
            if suffix and not is_composite_segment(suffix):
                aliases.add(f"{venue} ~ {suffix}")
    if not records:
        return None

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        grouped[normalize_course_text(record["venue"]).casefold()].append(record)

    def base_score(items: list[dict[str, Any]]) -> tuple[Any, ...]:
        venue = str(items[0]["venue"])
        non_composite = any(
            item["suffix"] is None or not is_composite_segment(item["suffix"])
            for item in items
        )
        count = len(items)
        latest = max((str(item["date"]) for item in items), default="")
        best_rank = min(int(item["rank"]) for item in items)
        explicit_cjk = any(bool(item["explicit"]) and contains_cjk(item["venue"]) for item in items)
        explicit_any = any(bool(item["explicit"]) for item in items)
        cjk = any(contains_cjk(item["venue"]) for item in items)
        return (
            int(explicit_cjk),
            int(explicit_any),
            int(cjk),
            int(non_composite),
            count,
            latest,
            -best_rank,
            venue.casefold(),
        )

    _venue_key, venue_records = max(grouped.items(), key=lambda entry: base_score(entry[1]))
    venue = str(venue_records[0]["venue"]).strip()

    segment_records = [
        item
        for item in venue_records
        if item["suffix"] and not is_composite_segment(item["suffix"])
    ]
    segment: str | None = None
    if segment_records:
        suffix_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for item in segment_records:
            suffix_groups[normalize_course_text(item["suffix"]).casefold()].append(item)

        def segment_score(items: list[dict[str, Any]]) -> tuple[Any, ...]:
            suffix = str(items[0]["suffix"])
            cjk = any(contains_cjk(item["suffix"]) for item in items)
            explicit = any(bool(item["explicit"]) for item in items)
            count = len(items)
            latest = max((str(item["date"]) for item in items), default="")
            best_rank = min(int(item["rank"]) for item in items)
            explicit_cjk = any(bool(item["explicit"]) and contains_cjk(item["suffix"]) for item in items)
            explicit_any = any(bool(item["explicit"]) for item in items)
            return (int(explicit_cjk), int(explicit_any), int(cjk), count, latest, -best_rank, suffix.casefold())

        _segment_key, best_segment_records = max(
            suffix_groups.items(), key=lambda entry: segment_score(entry[1])
        )
        segment = str(best_segment_records[0]["suffix"]).strip() or None

    source = GARMIN_SNAPSHOT_NAME_SOURCE if any(item["explicit"] for item in venue_records) else "history_fallback"
    ordered_aliases = tuple(sorted(aliases, key=lambda value: (value.casefold(), value)))
    return GarminNameIdentity(venue=venue, segment=segment, source=source, aliases=ordered_aliases)


def localized_provider_name(
    provider_name: Any,
    identity: GarminNameIdentity | None,
    *,
    segment_override: str | None = None,
    holes: int | None = None,
) -> str:
    """Combine a trusted venue with a provider/layout suffix without inventing text."""
    provider_venue, provider_suffix = split_garmin_course_name(provider_name)
    venue = identity.venue if identity and identity.venue else provider_venue
    venue = normalize_course_text(venue)
    if not venue:
        return normalize_course_text(provider_name)

    override = normalize_course_text(segment_override)
    identity_segment = normalize_course_text(identity.segment) if identity and identity.segment else ""
    provider_segment = normalize_course_text(provider_suffix)
    if override and not is_composite_segment(override):
        suffix = override
    elif provider_segment and not is_composite_segment(provider_segment):
        suffix = provider_segment
    elif (
        identity_segment
        and not is_composite_segment(identity_segment)
        # A historical loop label is a useful fallback only for a nine-hole
        # provider row.  Applying it to an unsuffixed 18-hole CourseView row
        # would make an otherwise factual whole-course name look like the
        # wrong layout.
        and holes == 9
    ):
        # A provider row without a suffix can use a factual single-loop label
        # from history.  A provider suffix always wins when present because it
        # identifies the row currently being selected.
        suffix = identity_segment
    else:
        suffix = ""

    # ``holes`` is intentionally only a fallback hint.  A CourseView 18-hole
    # layout can still have a meaningful suffix (Ocean/Old), so never discard a
    # factual provider suffix solely because of its hole count.
    _ = holes
    return f"{venue} ~ {suffix}" if suffix else venue


def preferred_garmin_source_name(
    row: Mapping[str, Any] | None,
    *,
    preserve_suffix: bool = True,
) -> str:
    """Return the best already-provided Garmin spelling for one history row.

    ``preserve_suffix`` is true for a round card, where ``A/C`` is a factual
    route.  Aggregate/selectable callers should use ``select_garmin_name_identity``
    and its venue instead so a played combination cannot become one layout.
    """
    if not isinstance(row, Mapping):
        return ""
    records = _candidate_records(row)
    best = _best_record(records)
    if best is None:
        return ""
    identity = select_garmin_name_identity([row])
    venue = identity.venue if identity is not None else str(best["venue"])
    # A merged row's ``course`` is a factual route assembled from its two raw
    # scorecards. It must not be copied into ``garminSnapshotName`` (which is
    # reserved for an exact source field), but it is the right suffix for a
    # round-history label.
    if preserve_suffix and row.get("merged"):
        merged_venue, merged_suffix = split_garmin_course_name(row.get("course"))
        suffix = normalize_course_text(merged_suffix)
        if merged_venue and not venue:
            venue = merged_venue
    else:
        suffix = normalize_course_text(best.get("suffix")) if preserve_suffix else ""
        if preserve_suffix and not suffix:
            # A legacy CourseView/history row used a space before a compact route
            # (`Black Knight B/C`) instead of Garmin's `~` separator. The
            # canonical field then wins identity selection and would otherwise
            # erase the factual route from history. Recover only the trailing
            # loop combination; this does not make it a selectable segment.
            raw_course = normalize_course_text(row.get("course") or row.get("courseName"))
            match = _TRAILING_ROUTE_RE.search(raw_course)
            if match:
                route = normalize_course_text(match.group(1))
                raw_prefix = normalize_course_text(raw_course[: match.start()])
                if raw_prefix and raw_prefix.casefold() == venue.casefold():
                    return raw_course
                suffix = route
    return f"{venue} ~ {suffix}" if suffix else venue


def preferred_garmin_venue(
    rows: Iterable[Mapping[str, Any]],
    *,
    fallback: str = "",
) -> str:
    """Return a trusted venue-only name for an aggregate/history group."""
    # The public API accepts any iterable.  Materialize once because identity
    # selection and the fallback scan both need to inspect the rows; generators
    # otherwise silently lose their second pass.
    materialized = [row for row in (rows or ()) if isinstance(row, Mapping)]
    identity = select_garmin_name_identity(materialized)
    if identity is not None and identity.venue:
        return identity.venue
    for row in materialized:
        best = _best_record(_candidate_records(row))
        if best is not None and best.get("venue"):
            return str(best["venue"])
    return normalize_course_text(fallback)


def localized_names_by_global_id(rows: Iterable[Mapping[str, Any]]) -> dict[int, GarminNameIdentity]:
    """Build a cache-only Garmin-name index without requiring coordinates."""
    grouped: dict[int, list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows or ():
        if not isinstance(row, Mapping):
            continue
        ids: set[int] = set()
        for key in (
            "globalId",
            "courseGlobalId",
            "courseId",
            "frontNineGlobalCourseId",
            "backNineGlobalCourseId",
        ):
            try:
                value = int(row.get(key))
            except (TypeError, ValueError, OverflowError):
                continue
            if value > 0:
                ids.add(value)
        for global_id in ids:
            grouped[global_id].append(row)
    result: dict[int, GarminNameIdentity] = {}
    for global_id, grouped_rows in grouped.items():
        identity = select_garmin_name_identity(grouped_rows)
        if identity is not None:
            result[global_id] = identity
    return result
