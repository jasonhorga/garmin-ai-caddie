from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

DataQualityState = Literal["good", "partial", "missing"]
ScoreClass = Literal["eagle", "birdie", "par", "bogey", "double", "missing"]
DistributionClass = Literal["eagle", "birdie", "bogey", "double"]
ConnectorState = Literal["ready", "no_data", "reauth_required", "error"]
ResolvedDataModeName = Literal["local", "fixture"]
ReportConfidence = Literal["low", "medium", "high"]
GeometryCoverageState = Literal["ready", "partial", "missing"]
CaddieShotType = Literal["tee", "approach", "recovery"]
AnnotationTargetType = Literal["round", "hole", "shot", "decision"]
AnnotationKind = Literal[
    "round_note",
    "hole_note",
    "shot_note",
    "issue_tag",
    "club_correction",
    "lie_correction",
    "penalty_correction",
    "putt_correction",
    "weather_context_note",
    "strategy_note",
    "caddie_feedback",
]
MediaTargetType = Literal["round", "hole", "shot"]
MediaKind = Literal["photo", "video"]
MediaPrivacyState = Literal["private_local", "synced", "redacted"]
LiveRoundEventKind = Literal["score", "club", "putt", "penalty", "note", "location", "photo", "video", "sync_marker"]


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


class DistributionBucket(BaseModel):
    label: str
    start: int
    count: int


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
    courses: list[dict[str, Any]]
    holes: list[dict[str, Any]]
    clubs: list[dict[str, Any]]
    issues: list[dict[str, Any]]
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
    name: Literal["garmin_cn_web_session"]
    state: ConnectorState
    detail: str
    canSync: bool
    reauthRequired: bool


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


class ReviewReportResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

    schema_: Literal["ai-caddie-review-report-v1"] = Field(alias="schema")
    kind: Literal["round", "trend"]
    provider: str
    model: str
    factsUsed: list[dict[str, Any]]
    missingData: list[dict[str, Any]]
    narrative: str
    confidence: ReportConfidence


class GeometryEvidenceResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

    schema_: Literal["ai-caddie-geometry-evidence-v1"] = Field(alias="schema")
    globalId: int
    localHole: int
    coverage: GeometryCoverageState
    hasHazards: bool
    hasMeshes: bool
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
    shotType: CaddieShotType
    phase: str
    context: dict[str, Any]
    options: list[dict[str, Any]]
    selected: dict[str, Any] | None
    selectedOptionId: str | None
    selectedOption: dict[str, Any] | None
    avoidZones: list[dict[str, Any]]
    forbiddenZones: list[dict[str, Any]]
    acceptableMiss: dict[str, Any]
    evidence: list[dict[str, Any]]
    confidence: dict[str, Any]
    missingData: list[dict[str, Any]]
    auditCriteria: list[dict[str, Any]]


class CaddieDecisionAuditRequest(BaseModel):
    decision: dict[str, Any]
    actualShot: dict[str, Any] | None = None


class CaddieDecisionAuditRecord(BaseModel):
    id: str
    storedAt: str
    decisionId: str
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


class LiveRoundPackageResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

    schema_: Literal["ai-caddie-live-round-package-v1"] = Field(alias="schema")
    roundId: str
    playerProfile: dict[str, Any]
    course: dict[str, Any]
    holes: list[dict[str, Any]]
    geometryCoverage: dict[str, Any]
    weatherSnapshot: dict[str, Any]
    clubProfiles: list[dict[str, Any]]
    caddieDecisionEndpoint: str
    generatedAt: str


class LiveRoundEventRecord(BaseModel):
    schema_: Literal["ai-caddie-live-round-event-v1"] = Field(alias="schema")
    eventId: str
    roundId: str
    timestamp: str
    hole: int
    kind: LiveRoundEventKind
    payload: dict[str, Any]


class LiveRoundEventBatchRequest(BaseModel):
    roundId: str
    events: list[LiveRoundEventRecord]


class LiveRoundEventBatchResponse(BaseModel):
    accepted: int
    duplicate: bool


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
