from __future__ import annotations

from datetime import datetime
import json
import math
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def _reject_oversized(value: Any, *, label: str, max_bytes: int = 131_072) -> Any:
    """codex MEDIUM #7: reject an arbitrarily large nested object (decision context / audit payload /
    round meta) before it is persisted to JSONL or processed. 128 KB is far above any real payload."""
    if value is not None and len(json.dumps(value, default=str).encode("utf-8")) > max_bytes:
        raise ValueError(f"{label} exceeds {max_bytes} bytes")
    return value

DataQualityState = Literal["good", "partial", "missing"]
ScoreClass = Literal["eagle", "birdie", "par", "bogey", "double", "missing"]
DistributionClass = Literal["eagle", "birdie", "bogey", "double"]
ConnectorState = Literal["ready", "no_data", "reauth_required", "error", "not_available"]
ConnectorName = Literal["garmin_cn_web_session", "garmin_oauth_feasibility"]
ConnectorNextAction = Literal["connect_garmin", "review_history", "reauthenticate_garmin", "inspect_sync_error"]
ResolvedDataModeName = Literal["local", "fixture"]
ReportConfidence = Literal["low", "medium", "high"]
GeometryCoverageState = Literal["ready", "partial", "missing"]
GeometryEnsureStatus = Literal["cached", "downloaded", "failed"]
CaddieShotType = Literal["tee", "approach", "recovery"]
GarminSessionSource = Literal["manual_paste", "web_secure_paste", "ios_secure_input", "ios_keychain_replay", "ios_web_login"]
AnnotationTargetType = Literal["round", "hole", "shot", "decision"]
AnnotationKind = Literal[
    "round_note",
    "hole_note",
    "shot_note",
    "issue_tag",
    "issue_tag_removed",
    "club_correction",
    "lie_correction",
    "penalty_correction",
    "putt_correction",
    "score_correction",
    "weather_context_note",
    "strategy_note",
    "caddie_feedback",
]
MediaTargetType = Literal["round", "hole", "shot"]
MediaKind = Literal["photo", "video"]
MediaPrivacyState = Literal["private_local", "synced", "redacted"]
LiveRoundEventKind = Literal["score", "club", "putt", "penalty", "note", "location", "photo", "video", "sync_marker"]

_LIVE_EVENT_PAYLOAD_FIELDS: dict[str, tuple[set[str], set[str]]] = {
    "score": ({"strokes"}, {"source"}),
    "club": (
        {"clubName"},
        {
            "source",
            "shotType",
            "strategyMode",
            "lie",
            "distanceToPinM",
            "offlineOptionId",
            "decisionId",
            "decision",
            "actualShot",
        },
    ),
    "putt": ({"putts"}, {"source"}),
    "penalty": ({"penalties"}, {"source"}),
    "note": ({"note"}, {"source"}),
    "location": (
        {"latitude", "longitude"},
        {"source", "horizontalAccuracyM", "altitudeM", "targetLatitude", "targetLongitude", "targetSource", "targetKind"},
    ),
    "photo": ({"assetLocalId", "mediaType"}, {"source", "fileURL", "note", "mediaId"}),
    "video": ({"assetLocalId", "mediaType"}, {"source", "fileURL", "durationS", "note", "mediaId"}),
    "sync_marker": ({"status"}, {"source", "acceptedEventIds", "duplicateEventIds", "serverSequence"}),
}

_LIVE_EVENT_PAYLOAD_FIELD_TYPES: dict[str, dict[str, str]] = {
    "score": {"strokes": "number", "source": "string"},
    "club": {
        "clubName": "string",
        "source": "string",
        "shotType": "string",
        "strategyMode": "string",
        "lie": "string",
        "distanceToPinM": "nullable_number",
        "offlineOptionId": "nullable_string",
        "decisionId": "string",
        "decision": "object",
        "actualShot": "object",
    },
    "putt": {"putts": "number", "source": "string"},
    "penalty": {"penalties": "number", "source": "string"},
    "note": {"note": "string", "source": "string"},
    "location": {
        "latitude": "number",
        "longitude": "number",
        "source": "string",
        "horizontalAccuracyM": "nullable_number",
        "altitudeM": "nullable_number",
        "targetLatitude": "number",
        "targetLongitude": "number",
        "targetSource": "string",
        "targetKind": "string",
    },
    "photo": {
        "assetLocalId": "string",
        "mediaType": "string",
        "source": "string",
        "fileURL": "nullable_string",
        "note": "nullable_string",
        "mediaId": "string",
    },
    "video": {
        "assetLocalId": "string",
        "mediaType": "string",
        "source": "string",
        "fileURL": "nullable_string",
        "durationS": "nullable_number",
        "note": "nullable_string",
        "mediaId": "string",
    },
    "sync_marker": {
        "status": "string",
        "source": "string",
        "acceptedEventIds": "string_array",
        "duplicateEventIds": "string_array",
        "serverSequence": "number",
    },
}

_LIVE_EVENT_PAYLOAD_ENUMS: dict[tuple[str, str], set[str]] = {
    ("club", "shotType"): {"tee", "approach", "recovery"},
    ("club", "strategyMode"): {"protect_score", "stock", "attack"},
}


def _is_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _is_count(value: object) -> bool:
    return _count_value(value) is not None


def _count_value(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and math.isfinite(value) and value.is_integer():
        return int(value)
    return None


def _validate_live_event_payload(kind: str, payload: dict[str, Any]) -> None:
    required, optional = _LIVE_EVENT_PAYLOAD_FIELDS[str(kind)]
    keys = set(payload)
    missing = required - keys
    if missing:
        raise ValueError(f"{kind} payload missing required keys: {', '.join(sorted(missing))}")
    null_required = {field for field in required if payload.get(field) is None}
    if null_required:
        raise ValueError(f"{kind} payload has null required keys: {', '.join(sorted(null_required))}")
    extra = keys - required - optional
    if extra:
        raise ValueError(f"{kind} payload has unsupported keys: {', '.join(sorted(extra))}")
    field_types = _LIVE_EVENT_PAYLOAD_FIELD_TYPES[str(kind)]
    for field in keys:
        value = payload.get(field)
        expected = field_types[field]
        if expected == "number" and not _is_number(value):
            raise ValueError(f"{kind} payload field {field} must be numeric")
        if expected == "nullable_number" and value is not None and not _is_number(value):
            raise ValueError(f"{kind} payload field {field} must be numeric or null")
        if expected == "string" and not isinstance(value, str):
            raise ValueError(f"{kind} payload field {field} must be a string")
        if expected == "nullable_string" and value is not None and not isinstance(value, str):
            raise ValueError(f"{kind} payload field {field} must be a string or null")
        if expected == "object" and not isinstance(value, dict):
            raise ValueError(f"{kind} payload field {field} must be an object")
        if expected == "string_array" and (
            not isinstance(value, list) or any(not isinstance(item, str) for item in value)
        ):
            raise ValueError(f"{kind} payload field {field} must be a string array")
        allowed_values = _LIVE_EVENT_PAYLOAD_ENUMS.get((kind, field))
        if allowed_values is not None and value not in allowed_values:
            raise ValueError(
                f"{kind} payload field {field} must be one of {', '.join(sorted(allowed_values))}"
            )
    media_type = payload.get("mediaType")
    if kind in {"photo", "video"} and media_type != kind:
        raise ValueError(f"{kind} payload mediaType must be {kind}")
    count_constraints = {
        "score": ("strokes", 1),
        "putt": ("putts", 0),
        "penalty": ("penalties", 0),
    }
    if kind in count_constraints:
        field, minimum = count_constraints[kind]
        value = payload[field]
        count_value = _count_value(value)
        if count_value is None:
            raise ValueError(f"{kind} payload field {field} must be an integer")
        if count_value < minimum:
            raise ValueError(f"{kind} payload field {field} must be at least {minimum}")
        payload[field] = count_value


class DataQualityBadge(BaseModel):
    label: str
    state: DataQualityState
    value: str
    reason: str


class ScoreStripCell(BaseModel):
    hole: int
    par: int | None
    score: int | None
    toPar: int | None
    className: ScoreClass


class RoundCard(BaseModel):
    id: str
    date: str | None
    courseName: str
    courseKey: str | None
    holesCompleted: int | None
    score: int | None
    par: int | None
    toPar: int | None
    scoreStrip: list[ScoreStripCell]
    badges: list[DataQualityBadge]
    primaryIssue: str | None = None
    # "manual" = phone-logged补录; "garmin" (or None on legacy rows) = watch sync.
    # Display-only marker — engines treat both sources alike.
    source: str | None = None


class CurrentPlayer(BaseModel):
    """Identity of the token-resolved player for the read-only top-bar badge."""

    id: str
    name: str | None
    isOwner: bool = False
    avatar: str | None = None


class HistoryMetricSet(BaseModel):
    totalRounds: int
    eighteenHoleRounds: int
    nineHoleRounds: int
    courseCount: int
    shotCount: int
    average18: float | None
    recent10Average: float | None
    bestScore: int | None


class DistributionFamily(BaseModel):
    label: str
    count: int
    pct: float
    className: DistributionClass
    roundRefs: list[str] = Field(default_factory=list)


class DistributionBucket(BaseModel):
    label: str
    start: int
    count: int
    roundRefs: list[str] = Field(default_factory=list)


class ScoreDistribution(BaseModel):
    total: int
    average: float | None
    best: int | None
    worst: int | None
    families: list[DistributionFamily]
    histogram: list[DistributionBucket]


class EmptyState(BaseModel):
    kind: str
    title: str
    detail: str


class HistoryOverviewResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

    schema_: Literal["ai-caddie-history-overview-v2"] = Field(alias="schema")
    metrics: HistoryMetricSet
    recentRounds: list[RoundCard]
    distribution: ScoreDistribution
    dataQuality: list[DataQualityBadge]
    emptyState: EmptyState | None
    # Token-resolved player whose data this payload represents (top-bar badge).
    currentPlayer: CurrentPlayer | None = None


class MonthRoundGroup(BaseModel):
    key: str
    label: str
    count: int
    average18: float | None
    bestScore: int | None
    rounds: list[RoundCard]


class CourseFilterOption(BaseModel):
    key: str
    label: str


class HistoryRoundsResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

    schema_: Literal["ai-caddie-history-rounds-v2"] = Field(alias="schema")
    total: int
    groups: list[MonthRoundGroup]
    emptyState: EmptyState | None
    availableYears: list[str] = Field(default_factory=list)
    availableCourses: list[CourseFilterOption] = Field(default_factory=list)
    appliedFilters: dict[str, object] = Field(default_factory=dict)


class HistoryRoundDetailResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

    schema_: Literal["ai-caddie-history-round-detail-v1"] = Field(alias="schema")
    roundRef: str
    requestedRef: str
    found: bool
    title: str
    round: dict[str, Any] | None
    scorecard: list[dict[str, Any]]
    phaseSummary: list[dict[str, Any]]
    holeDetails: list[dict[str, Any]]
    relatedRefs: dict[str, list[str]]
    sourceFields: dict[str, Any]
    missingData: list[dict[str, Any]]
    annotations: list[dict[str, Any]] = Field(default_factory=list)
    corrections: list[dict[str, Any]] = Field(default_factory=list)


class HistoryStatsResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

    schema_: Literal["ai-caddie-history-stats-v1"] = Field(alias="schema")
    dataMode: ResolvedDataModeName
    summary: dict[str, Any]
    time: dict[str, Any]
    scoring: dict[str, Any]
    courseDistribution: list[dict[str, Any]]
    records: dict[str, Any]
    courses: list[dict[str, Any]]
    holes: list[dict[str, Any]]
    clubs: list[dict[str, Any]]
    issues: list[dict[str, Any]]
    diagnosis: dict[str, Any]
    playerProfile: dict[str, Any]
    dataQuality: list[dict[str, Any]]
    drillDown: dict[str, Any]


class HistoryStatsSummaryResponse(BaseModel):
    """Lightweight 概览 landing payload: the few summary numbers + the top issue.

    The full HistoryStatsResponse is ~20MB (courses/clubs/holes aggregates); the
    home only reads ``summary`` + ``issues[0].issue``, so this slices those out
    to keep first paint fast. The heavy response stays for the analysis pages.
    """

    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

    schema_: Literal["ai-caddie-history-summary-v1"] = Field(alias="schema")
    summary: dict[str, Any]
    topIssue: str | None = None


class MobileStatsResponse(BaseModel):
    """Compact mobile 统计 payload: the deep / periodic / per-course / per-club slices of the full
    stats blob, WITHOUT the giant per-hole table (``holes[]``) or the heavy per-row evidence refs —
    hundreds of KB instead of ~11MB. Nested sections are passed through as dicts/lists so no field
    is silently dropped (the MobileCourseOption regression: a typed model stripping enriched fields)."""

    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

    schema_: Literal["ai-caddie-mobile-stats-v1"] = Field(alias="schema")
    dataMode: str | None = None
    summary: dict[str, Any] = Field(default_factory=dict)
    time: dict[str, Any] = Field(default_factory=dict)
    trend: dict[str, Any] = Field(default_factory=dict)
    scoring: dict[str, Any] = Field(default_factory=dict)
    records: dict[str, Any] = Field(default_factory=dict)
    courses: list[dict[str, Any]] = Field(default_factory=list)
    clubs: list[dict[str, Any]] = Field(default_factory=list)
    diagnosis: dict[str, Any] = Field(default_factory=dict)
    playerProfile: dict[str, Any] = Field(default_factory=dict)
    dataQuality: list[dict[str, Any]] = Field(default_factory=list)


class ClubBagResponse(BaseModel):
    """The player's REAL Garmin club bag, fetched by the pipeline from Garmin's `/club/player`
    roster + `/club/types` dictionary. Each club carries the authoritative ``clubTypeId``, the
    player's custom name (e.g. "Pw"/"50") when set, the standard type name + loft, and
    retired/deleted flags. Display names resolve to Chinese on the client. ``clubs`` is a dict
    passthrough so no field is silently dropped."""

    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

    schema_: Literal["ai-caddie-club-bag-v1"] = Field(alias="schema")
    found: bool = False
    playerProfileId: int | None = None
    clubs: list[dict[str, Any]] = Field(default_factory=list)


class RoundHoleShotMapResponse(BaseModel):
    """Per-hole 复盘 shot map: this round's actual shots projected onto the hole's 2D render.
    map/shots passed through as dict/list (image is a big data URI; shots carry start/end px)."""

    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

    schema_: Literal["ai-caddie-round-hole-shotmap-v1"] = Field(alias="schema")
    found: bool
    roundRef: str
    hole: int
    par: int | None = None
    map: dict[str, Any] | None = None
    shots: list[dict[str, Any]] = Field(default_factory=list)
    missingData: list[dict[str, Any]] = Field(default_factory=list)


class HistoryDrilldownResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

    schema_: Literal["ai-caddie-history-drilldown-v1"] = Field(alias="schema")
    ref: str
    refType: Literal["round", "hole", "shot", "unknown"]
    found: bool
    title: str
    round: dict[str, Any] | None
    hole: dict[str, Any] | None
    shot: dict[str, Any] | None
    relatedRefs: dict[str, list[str]]
    sourceFields: dict[str, Any]
    missingData: list[dict[str, Any]]
    annotations: list[dict[str, Any]] = Field(default_factory=list)
    corrections: list[dict[str, Any]] = Field(default_factory=list)
    reports: list[dict[str, Any]] = Field(default_factory=list)
    weatherSnapshots: list[dict[str, Any]] = Field(default_factory=list)
    decisionAudits: list[dict[str, Any]] = Field(default_factory=list)
    geometryEvidence: list[dict[str, Any]] = Field(default_factory=list)


class ConnectorStatus(BaseModel):
    name: ConnectorName
    state: ConnectorState
    detail: str
    canSync: bool
    reauthRequired: bool
    nextAction: ConnectorNextAction | None = None
    track: str | None = None
    feasibilityQuestions: list[str] = Field(default_factory=list)
    capabilities: list[dict[str, Any]] = Field(default_factory=list)
    probe: dict[str, Any] = Field(default_factory=dict)


class SnapshotStatus(BaseModel):
    dataMode: ResolvedDataModeName
    scorecardCount: int
    shotFileCount: int
    summaryPresent: bool
    lastSuccessfulSnapshotId: str | None = None
    lastSuccessfulSyncAt: str | None
    geometryDependencyCount: int = 0
    geometryReadyCount: int = 0
    geometryMissingCount: int = 0
    geometryDependencies: list[dict[str, Any]] = Field(default_factory=list)


class SyncLastRunStatus(BaseModel):
    state: ConnectorState
    detail: str
    snapshotId: str | None
    errorCode: str | None
    updatedAt: str | None


class SyncStatusResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

    schema_: Literal["ai-caddie-sync-status-v2"] = Field(alias="schema")
    connector: ConnectorStatus
    connectors: list[ConnectorStatus] = Field(default_factory=list)
    snapshot: SnapshotStatus
    lastRun: SyncLastRunStatus | None


class SyncSnapshotPayload(BaseModel):
    snapshotId: str
    scorecardCount: int
    shotFileCount: int
    summaryPresent: bool
    files: list[str]
    geometryDependencyCount: int = 0
    geometryReadyCount: int = 0
    geometryMissingCount: int = 0
    geometryDependencies: list[dict[str, Any]] = Field(default_factory=list)


class SyncRunResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

    schema_: Literal["ai-caddie-sync-run-v2"] = Field(alias="schema")
    connector: Literal["garmin_cn_web_session"]
    state: ConnectorState
    detail: str
    reauthRequired: bool
    errorCode: str | None
    snapshot: SyncSnapshotPayload | None
    safeMeta: dict[str, Any] = Field(default_factory=dict)


class GarminSessionImportRequest(BaseModel):
    webSessionHeader: str = Field(min_length=1)
    antiForgeryValue: str = Field(min_length=1)
    source: GarminSessionSource = "manual_paste"


class GarminSessionImportResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

    schema_: Literal["ai-caddie-garmin-session-import-v1"] = Field(alias="schema")
    connector: Literal["garmin_cn_web_session"]
    state: Literal["stored"]
    detail: str
    sessionFieldCount: int
    antiForgeryPresent: bool
    source: GarminSessionSource
    acceptedSources: list[GarminSessionSource] = Field(default_factory=list)


class ReviewReportResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

    schema_: Literal["ai-caddie-review-report-v1"] = Field(alias="schema")
    kind: Literal["round", "trend", "hole", "course", "club"]
    subjectId: str
    sourceRefs: list[str] = Field(default_factory=list)
    provider: str
    model: str
    factsUsed: list[dict[str, Any]]
    missingData: list[dict[str, Any]]
    inferencesMade: list[dict[str, Any]] = Field(default_factory=list)
    unsupportedClaims: list[dict[str, Any]] = Field(default_factory=list)
    factBinding: dict[str, Any] = Field(default_factory=lambda: {"state": "bound", "unsupportedClaimCount": 0})
    narrative: str
    confidence: ReportConfidence


class ReviewReportIndexResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

    schema_: Literal["ai-caddie-review-report-index-v1"] = Field(alias="schema")
    total: int
    reports: list[dict[str, Any]]


class GeometryEvidenceResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

    schema_: Literal["ai-caddie-geometry-evidence-v1"] = Field(alias="schema")
    globalId: int
    localHole: int
    coverage: GeometryCoverageState
    hasHazards: bool
    hasMeshes: bool
    sourceRef: str | None = None
    shotRoutes: list[dict[str, Any]] = Field(default_factory=list)
    surfaceClassifications: list[dict[str, Any]] = Field(default_factory=list)
    routeEvidence: dict[str, Any] | None = None
    evidence: list[dict[str, Any]]
    missingData: list[dict[str, Any]]


class CourseGeometryCoverageResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

    schema_: Literal["ai-caddie-course-geometry-coverage-v1"] = Field(alias="schema")
    globalId: int
    coverage: GeometryCoverageState
    readyHoles: int
    partialHoles: int
    totalHoles: int
    holes: list[dict[str, Any]]


class GeometryEnsureResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

    schema_: Literal["ai-caddie-geometry-ensure-v1"] = Field(alias="schema")
    status: GeometryEnsureStatus
    ok: bool
    globalId: int
    localHole: int
    releaseSource: str | None = None
    releaseId: str | None = None
    courseName: str | None = None
    hazards: str | None = None
    meshes: str | None = None
    steps: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None


class HoleMapResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

    schema_: Literal["ai-caddie-hole-map-v1"] = Field(alias="schema")
    globalId: int
    localHole: int
    provider: dict[str, Any]
    coverage: GeometryCoverageState
    layers: list[str]
    featureCollection: dict[str, Any]
    missingData: list[dict[str, Any]]


class CaddieDecisionRequest(BaseModel):
    shotType: CaddieShotType
    context: dict[str, Any] = Field(default_factory=dict)
    includeExplanation: bool = True

    @field_validator("context")
    @classmethod
    def _bound_context(cls, value: dict[str, Any]) -> dict[str, Any]:
        return _reject_oversized(value, label="context")  # codex MEDIUM #7


class CaddieDecisionResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

    schema_: Literal["ai-caddie-decision-v2"] = Field(alias="schema")
    decisionId: str
    sourceRef: str | None = None
    evidenceRefs: list[str] = Field(default_factory=list)
    shotType: CaddieShotType
    phase: str
    context: dict[str, Any]
    options: list[dict[str, Any]]
    selected: dict[str, Any] | None
    selectedOptionId: str | None
    selectedOption: dict[str, Any] | None
    sequences: list[dict[str, Any]] = Field(default_factory=list)
    selectedSequence: dict[str, Any] | None = None
    avoidZones: list[dict[str, Any]]
    forbiddenZones: list[dict[str, Any]]
    acceptableMiss: dict[str, Any]
    evidence: list[dict[str, Any]]
    confidence: dict[str, Any]
    missingData: list[dict[str, Any]]
    auditCriteria: list[dict[str, Any]]
    explanation: dict[str, Any] | None = None


class CaddieContextResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

    schema_: Literal["ai-caddie-context-v1"] = Field(alias="schema")
    sourceRef: str
    shotType: CaddieShotType
    context: dict[str, Any]
    evidence: list[dict[str, Any]]
    missingData: list[dict[str, Any]]


class CaddieDecisionAuditRequest(BaseModel):
    decision: dict[str, Any] | None = None
    actualShot: dict[str, Any] | None = None
    actualShots: list[dict[str, Any]] | None = Field(default=None, max_length=500)
    actualScoreToPar: float | None = None
    penalty: bool | None = None

    @field_validator("decision", "actualShot")
    @classmethod
    def _bound_audit_payload(cls, value: dict[str, Any] | None) -> dict[str, Any] | None:
        return _reject_oversized(value, label="audit payload")  # codex MEDIUM #7


class CaddieDecisionAuditRecord(BaseModel):
    id: str
    storedAt: str
    decisionId: str
    sourceRef: str | None = None
    selectedOptionId: str | None = None
    plannedOptionId: str | None = None
    actualOptionId: str | None = None
    actualShotRefs: list[str] = Field(default_factory=list)
    evidenceRefs: list[str] = Field(default_factory=list)
    classification: str | None = None
    audit: dict[str, Any]


class CaddieDecisionAuditStoreResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

    schema_: Literal["ai-caddie-decision-audit-store-v1"] = Field(alias="schema")
    record: CaddieDecisionAuditRecord


class CaddieDecisionAuditLatestResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

    schema_: Literal["ai-caddie-decision-audit-latest-v1"] = Field(alias="schema")
    decisionId: str
    record: CaddieDecisionAuditRecord | None


class AnnotationRecord(BaseModel):
    id: str
    createdAt: str
    targetType: AnnotationTargetType
    targetId: str
    kind: AnnotationKind
    payload: dict[str, Any]
    source: Literal["manual"]


class AnnotationCreateRequest(BaseModel):
    targetType: AnnotationTargetType
    targetId: str = Field(min_length=1)
    kind: AnnotationKind
    payload: dict[str, Any] = Field(default_factory=dict)


class AnnotationCreateResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

    schema_: Literal["ai-caddie-annotation-create-v1"] = Field(alias="schema")
    annotation: AnnotationRecord


class AnnotationListResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

    schema_: Literal["ai-caddie-annotations-v1"] = Field(alias="schema")
    total: int
    annotations: list[AnnotationRecord]
    target: dict[str, str] | None = None


class MediaRecord(BaseModel):
    id: str
    createdAt: str
    targetType: MediaTargetType
    targetId: str
    mediaKind: MediaKind
    localPath: str
    capturedAt: str
    privacyState: MediaPrivacyState
    source: Literal["manual"]
    contentByteSize: int | None = None
    mimeType: str | None = None
    durationS: float | None = None
    uploadStatus: str | None = None


class MediaCreateRequest(BaseModel):
    targetType: MediaTargetType
    targetId: str = Field(min_length=1)
    mediaKind: MediaKind
    localPath: str | None = None
    fileName: str | None = None
    contentBase64: str | None = None
    capturedAt: str = Field(min_length=1)
    privacyState: MediaPrivacyState = "private_local"
    mimeType: str | None = None
    durationS: float | None = None


class MediaCreateResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

    schema_: Literal["ai-caddie-media-create-v1"] = Field(alias="schema")
    media: MediaRecord


class MediaRedactResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

    schema_: Literal["ai-caddie-media-redact-v1"] = Field(alias="schema")
    media: MediaRecord
    deletedContent: bool


class MediaListResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

    schema_: Literal["ai-caddie-media-list-v1"] = Field(alias="schema")
    total: int
    media: list[MediaRecord]
    target: dict[str, str] | None = None


class VisionAnalysisResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

    schema_: Literal["ai-caddie-vision-context-v1"] = Field(alias="schema")
    mediaId: str | None
    targetType: str | None = None
    targetId: str | None = None
    mediaKind: str | None = None
    provider: str
    model: str
    findings: list[dict[str, Any]]


class VisionFindingRecord(BaseModel):
    id: str
    createdAt: str
    confirmedAt: str | None = None
    confirmedBy: str | None = None
    targetType: MediaTargetType
    targetId: str
    mediaId: str
    mediaKind: str | None = None
    findingType: str
    evidenceText: str
    confidence: Literal["low", "medium", "high"]
    confirmationState: Literal["unconfirmed", "confirmed", "player_confirmed", "manual_confirmed", "rejected"] = (
        "unconfirmed"
    )
    missingInfo: list[str]
    provider: str
    model: str
    source: Literal["vision_model"]


class VisionFindingConfirmationRequest(BaseModel):
    confirmationState: Literal["unconfirmed", "manual_confirmed", "rejected"]
    confirmedBy: str | None = None


class VisionFindingConfirmationResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

    schema_: Literal["ai-caddie-vision-finding-confirmation-v1"] = Field(alias="schema")
    finding: VisionFindingRecord


class VisionFindingsListResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

    schema_: Literal["ai-caddie-vision-findings-list-v1"] = Field(alias="schema")
    total: int
    findings: list[VisionFindingRecord]
    target: dict[str, str]


class LiveRoundPackageResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

    schema_: Literal["ai-caddie-live-round-package-v1"] = Field(alias="schema")
    roundId: str
    dataMode: ResolvedDataModeName
    sourceCoverage: dict[str, Any]
    missingData: list[dict[str, Any]]
    playerProfile: dict[str, Any]
    course: dict[str, Any]
    holes: list[dict[str, Any]]
    coursePrep: dict[str, Any] | None = None
    geometryCoverage: dict[str, Any]
    readinessChecks: list[dict[str, Any]] = Field(default_factory=list)
    nine: Literal["all", "front", "back"] = "all"
    caddieContextSeeds: list[dict[str, Any]]
    weatherSnapshot: dict[str, Any]
    clubProfiles: list[dict[str, Any]]
    caddieDecisionEndpoint: str
    offlinePackageStatus: dict[str, Any]
    eventCursor: dict[str, Any]
    recentHistory: dict[str, Any]
    cachedCaddieRules: dict[str, Any]
    generatedAt: str


class MobileCourseOption(BaseModel):
    globalId: int
    courseKey: str | None = None
    name: str
    venueName: str | None = None
    segmentLabel: str | None = None
    segmentHoles: int | None = None
    roundCount: int
    latestRoundId: str | None = None
    latestRoundDate: str | None = None
    templateRoundId: str | None = None
    suggestedLiveRoundId: str | None = None
    holes: int
    teeBox: str | None = None
    geometryCoverage: str
    sourceRefs: list[str] = Field(default_factory=list)
    latitude: float | None = None
    longitude: float | None = None
    tees: list[str] = Field(default_factory=list)


class MobileCourseOptionsResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

    schema_: Literal["ai-caddie-mobile-course-options-v1"] = Field(alias="schema")
    dataMode: ResolvedDataModeName
    total: int
    courses: list[MobileCourseOption]
    emptyState: dict[str, Any] | None = None
    generatedAt: str


class LiveRoundEventRecord(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

    schema_: Literal["ai-caddie-live-round-event-v1"] = Field(alias="schema")
    eventId: str = Field(min_length=1)
    roundId: str = Field(min_length=1)
    timestamp: str = Field(min_length=1)
    hole: int = Field(ge=1)
    kind: LiveRoundEventKind
    payload: dict[str, Any]
    # round-12 sync spine: which client/device authored this event (e.g. "ios-phone", "apple-watch",
    # "web"). Optional + backward-compatible; when present it joins the dedup key so the SAME eventId
    # from two different clients is not collapsed. Absent → treated as "" (legacy single-client behavior).
    clientId: str | None = None

    @field_validator("timestamp")
    @classmethod
    def timestamp_is_iso8601(cls, value: str) -> str:
        try:
            datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("timestamp must be ISO 8601") from exc
        return value

    @model_validator(mode="after")
    def payload_matches_event_kind(self) -> "LiveRoundEventRecord":
        _validate_live_event_payload(str(self.kind), self.payload)
        return self


class LiveRoundEventBatchRequest(BaseModel):
    roundId: str = Field(min_length=1)
    events: list[LiveRoundEventRecord] = Field(min_length=1)


class LiveRoundEventBatchResponse(BaseModel):
    accepted: int
    duplicate: bool
    acceptedEventIds: list[str] = Field(default_factory=list)
    duplicateEventIds: list[str] = Field(default_factory=list)
    serverSequence: int = 0


class LiveRoundEventReplayItem(BaseModel):
    serverSequence: int
    idempotencyKey: str
    event: dict[str, Any]


class LiveRoundEventReplayResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

    schema_: Literal["ai-caddie-mobile-event-replay-v1"] = Field(alias="schema")
    roundId: str
    clientId: str | None = None
    afterSequence: int
    latestServerSequence: int
    nextCursor: int
    eventCount: int
    hasMore: bool
    events: list[LiveRoundEventReplayItem]


class RoundStateResponse(BaseModel):
    """round-12 sync spine: the materialized authoritative per-hole round state, folded server-side
    from the event log. `holes`/`conflicts` are passthrough dicts so the projection can grow fields
    without a model change (matches the per-hole shape iOS already projects locally)."""

    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

    schema_: Literal["ai-caddie-round-state-v1"] = Field(alias="schema")
    roundId: str
    latestServerSequence: int
    activeHole: int
    holes: list[dict[str, Any]] = Field(default_factory=list)
    conflicts: list[dict[str, Any]] = Field(default_factory=list)


class LiveRoundEventAckRequest(BaseModel):
    clientId: str
    serverSequence: int


class LiveRoundEventAckResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

    schema_: Literal["ai-caddie-mobile-event-ack-v1"] = Field(alias="schema")
    roundId: str
    clientId: str
    ackedServerSequence: int
    latestServerSequence: int
    pendingEventCount: int


class RoundIngestRequest(BaseModel):
    """A manual ("phone") round: live capture events + round meta (see
    ``ai_caddie.round_ingest.ingest_round``). Events are accepted as loose dicts so the
    full live-event payload surface stays forward-compatible; ``ingest_round`` validates
    them and raises a 400 on malformed input."""

    # codex MEDIUM #5/#7: bound the body so a caller can't post a giant events list (a round is
    # ≤18 holes × a handful of shots; 5000 is generous head-room) or an oversized meta blob.
    events: list[dict[str, Any]] = Field(min_length=1, max_length=5000)
    meta: dict[str, Any] = Field(default_factory=dict)
    idempotencyKey: str | None = None
    clientRoundId: str | None = None

    @field_validator("meta")
    @classmethod
    def _bound_meta(cls, value: dict[str, Any]) -> dict[str, Any]:
        return _reject_oversized(value, label="meta")


class RoundIngestResponse(BaseModel):
    id: int
    playerId: str
    source: Literal["manual"]
    date: str | None = None
    course: str | None = None
    holesCompleted: int | None = None
    strokes: int | None = None
    par: int | None = None
    shotCount: int | None = None
    idempotent: bool


class MobileReconciliationApplyRequest(BaseModel):
    suggestionIds: list[str] = Field(default_factory=list)


class MobileReconciliationSummary(BaseModel):
    eventCount: int
    matchedCount: int
    localOnlyCount: int
    garminOnlyCount: int
    conflictCount: int
    candidateDecisionAuditCount: int
    annotationSuggestionCount: int


class MobileReconciliationSuggestion(BaseModel):
    id: str
    targetType: AnnotationTargetType
    targetId: str
    kind: AnnotationKind
    payload: dict[str, Any]
    reason: str
    confidence: ReportConfidence


class MobileReconciliationResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

    schema_: Literal["ai-caddie-mobile-reconciliation-v1"] = Field(alias="schema")
    roundId: str
    summary: MobileReconciliationSummary
    matched: list[dict[str, Any]] = Field(default_factory=list)
    localOnly: list[dict[str, Any]] = Field(default_factory=list)
    garminOnly: list[dict[str, Any]] = Field(default_factory=list)
    conflicts: list[dict[str, Any]] = Field(default_factory=list)
    candidateDecisionAudits: list[dict[str, Any]] = Field(default_factory=list)
    annotationSuggestions: list[MobileReconciliationSuggestion] = Field(default_factory=list)


class MobileReconciliationApplyResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

    schema_: Literal["ai-caddie-mobile-reconciliation-apply-v1"] = Field(alias="schema")
    roundId: str
    appliedCount: int
    decisionAuditCount: int = 0
    skippedCount: int
    missingSuggestionIds: list[str] = Field(default_factory=list)
    skippedSuggestionIds: list[str] = Field(default_factory=list)
    annotations: list[AnnotationRecord]
    decisionAudits: list[dict[str, Any]] = Field(default_factory=list)


class WeatherSnapshotResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

    schema_: Literal["ai-caddie-weather-snapshot-v1"] = Field(alias="schema")
    state: Literal["ready", "missing"]
    source: Literal["manual", "open_meteo", "missing"]
    roundId: str | None = None
    hole: int | None = None
    capturedAt: str | None = None
    location: dict[str, float] | None = None
    windSpeedMps: float | None = None
    windDirectionDeg: int | None = None
    temperatureC: float | None = None
    precipitationMm: float | None = None
    confidence: Literal["low", "medium", "high"]
    missingData: list[dict[str, Any]]
