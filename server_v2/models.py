from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class DataQualityBadge(BaseModel):
    label: str
    state: str
    value: str
    reason: str


class ScoreStripCell(BaseModel):
    hole: int
    par: int | None
    score: int | None
    toPar: int | None
    className: str


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
    className: str


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

    schema_: str = Field(alias="schema")
    metrics: HistoryMetricSet
    recentRounds: list[RoundCard]
    distribution: ScoreDistribution
    dataQuality: list[DataQualityBadge]
    emptyState: EmptyState | None
