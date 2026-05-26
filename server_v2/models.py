from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

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
    "club": ({"clubName"}, {"source", "decisionId", "decision", "actualShot"}),
    "putt": ({"putts"}, {"source"}),
    "penalty": ({"penalties"}, {"source"}),
    "note": ({"note"}, {"source"}),
    "location": ({"latitude", "longitude"}, {"source", "horizontalAccuracyM", "altitudeM"}),
    "photo": ({"assetLocalId", "mediaType"}, {"source", "fileURL", "note", "mediaId"}),
    "video": ({"assetLocalId", "mediaType"}, {"source", "fileURL", "durationS", "note", "mediaId"}),
    "sync_marker": ({"status"}, {"source", "acceptedEventIds", "duplicateEventIds", "serverSequence"}),
}

_LIVE_EVENT_PAYLOAD_FIELD_TYPES: dict[str, dict[str, str]] = {
    "score": {"strokes": "number", "source": "string"},
    "club": {"clubName": "string", "source": "string", "decisionId": "string", "decision": "object", "actualShot": "object"},
    "putt": {"putts": "number", "source": "string"},
    "penalty": {"penalties": "number", "source": "string"},
    "note": {"note": "string", "source": "string"},
    "location": {
        "latitude": "number",
        "longitude": "number",
        "source": "string",
        "horizontalAccuracyM": "nullable_number",
        "altitudeM": "nullable_number",
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


def _is_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


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
    media_type = payload.get("mediaType")
    if kind in {"photo", "video"} and media_type != kind:
        raise ValueError(f"{kind} payload mediaType must be {kind}")
    if kind == "score" and payload["strokes"] < 1:
        raise ValueError("score payload field strokes must be at least 1")
    if kind == "putt" and payload["putts"] < 0:
        raise ValueError("putt payload field putts must be at least 0")
    if kind == "penalty" and payload["penalties"] < 0:
        raise ValueError("penalty payload field penalties must be at least 0")


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


class MonthRoundGroup(BaseModel):
    key: str
    label: str
    count: int
    average18: float | None
    bestScore: int | None
    rounds: list[RoundCard]


class HistoryRoundsResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

    schema_: Literal["ai-caddie-history-rounds-v2"] = Field(alias="schema")
    total: int
    groups: list[MonthRoundGroup]
    emptyState: EmptyState | None


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
    dataQuality: list[dict[str, Any]]
    drillDown: dict[str, Any]


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
    lastSuccessfulSyncAt: str | None


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


class SyncRunResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

    schema_: Literal["ai-caddie-sync-run-v2"] = Field(alias="schema")
    connector: Literal["garmin_cn_web_session"]
    state: ConnectorState
    detail: str
    reauthRequired: bool
    errorCode: str | None
    snapshot: SyncSnapshotPayload | None


class GarminSessionImportRequest(BaseModel):
    webSessionHeader: str = Field(min_length=1)
    antiForgeryValue: str = Field(min_length=1)


class GarminSessionImportResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

    schema_: Literal["ai-caddie-garmin-session-import-v1"] = Field(alias="schema")
    connector: Literal["garmin_cn_web_session"]
    state: Literal["stored"]
    detail: str
    sessionFieldCount: int
    antiForgeryPresent: bool
    source: Literal["manual_paste"]


class ReviewReportResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

    schema_: Literal["ai-caddie-review-report-v1"] = Field(alias="schema")
    kind: Literal["round", "trend"]
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


class CaddieContextResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

    schema_: Literal["ai-caddie-context-v1"] = Field(alias="schema")
    sourceRef: str
    shotType: CaddieShotType
    context: dict[str, Any]
    evidence: list[dict[str, Any]]
    missingData: list[dict[str, Any]]


class CaddieDecisionAuditRequest(BaseModel):
    decision: dict[str, Any]
    actualShot: dict[str, Any] | None = None


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


class MediaCreateRequest(BaseModel):
    targetType: MediaTargetType
    targetId: str = Field(min_length=1)
    mediaKind: MediaKind
    localPath: str | None = None
    fileName: str | None = None
    contentBase64: str | None = None
    capturedAt: str = Field(min_length=1)
    privacyState: MediaPrivacyState = "private_local"


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
    targetType: MediaTargetType
    targetId: str
    mediaId: str
    mediaKind: str | None = None
    findingType: str
    evidenceText: str
    confidence: Literal["low", "medium", "high"]
    missingInfo: list[str]
    provider: str
    model: str
    source: Literal["vision_model"]


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
    geometryCoverage: dict[str, Any]
    caddieContextSeeds: list[dict[str, Any]]
    weatherSnapshot: dict[str, Any]
    clubProfiles: list[dict[str, Any]]
    caddieDecisionEndpoint: str
    offlinePackageStatus: dict[str, Any]
    eventCursor: dict[str, Any]
    recentHistory: dict[str, Any]
    cachedCaddieRules: dict[str, Any]
    generatedAt: str


class LiveRoundEventRecord(BaseModel):
    schema_: Literal["ai-caddie-live-round-event-v1"] = Field(alias="schema")
    eventId: str
    roundId: str
    timestamp: str
    hole: int
    kind: LiveRoundEventKind
    payload: dict[str, Any]

    @model_validator(mode="after")
    def payload_matches_event_kind(self) -> "LiveRoundEventRecord":
        _validate_live_event_payload(str(self.kind), self.payload)
        return self


class LiveRoundEventBatchRequest(BaseModel):
    roundId: str
    events: list[LiveRoundEventRecord]


class LiveRoundEventBatchResponse(BaseModel):
    accepted: int
    duplicate: bool
    acceptedEventIds: list[str] = Field(default_factory=list)
    duplicateEventIds: list[str] = Field(default_factory=list)
    serverSequence: int = 0


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
