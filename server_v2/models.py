from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

DataQualityState = Literal["good", "partial", "missing"]
ScoreClass = Literal["eagle", "birdie", "par", "bogey", "double", "missing"]
DistributionClass = Literal["eagle", "birdie", "bogey", "double"]
ConnectorState = Literal["ready", "no_data", "reauth_required", "error"]
ResolvedDataModeName = Literal["local", "fixture"]


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


class SyncStatusResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

    schema_: Literal["ai-caddie-sync-status-v2"] = Field(alias="schema")
    connector: ConnectorStatus
    snapshot: SnapshotStatus
