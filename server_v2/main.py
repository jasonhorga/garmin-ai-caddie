from __future__ import annotations

from typing import Annotated, Literal

from fastapi import FastAPI, Header, Query, Response
from fastapi.middleware.cors import CORSMiddleware

from ai_caddie.connectors.garmin_cn import GarminCnWebSessionConnector, sanitize_error
from ai_caddie.connectors.snapshot import snapshot_to_payload

from .annotations import create_annotation_response, list_annotation_response, list_target_annotation_response
from .caddie import build_caddie_decision_response
from .history_overview import load_history_overview_response
from .history_rounds import load_history_rounds_response
from .history_drilldown import load_history_drilldown_response
from .history_stats import load_history_stats_response
from .geometry import load_course_geometry_coverage_response, load_hole_geometry_evidence_response, load_hole_map_response
from .media import analyze_media_response, create_media_response, list_target_media_response
from .mobile import append_mobile_events_response, build_mobile_round_package_response
from .weather import load_weather_snapshot_response
from .models import (
    AnnotationCreateRequest,
    AnnotationCreateResponse,
    AnnotationListResponse,
    AnnotationTargetType,
    CaddieDecisionRequest,
    CaddieDecisionResponse,
    CourseGeometryCoverageResponse,
    GeometryEvidenceResponse,
    HistoryDrilldownResponse,
    HoleMapResponse,
    HistoryOverviewResponse,
    HistoryRoundsResponse,
    HistoryStatsResponse,
    LiveRoundEventBatchRequest,
    LiveRoundEventBatchResponse,
    LiveRoundPackageResponse,
    MediaCreateRequest,
    MediaCreateResponse,
    MediaListResponse,
    MediaTargetType,
    ReviewReportResponse,
    SyncRunResponse,
    SyncStatusResponse,
    VisionAnalysisResponse,
    WeatherSnapshotResponse,
)
from .reports import generate_round_report_response, load_round_report_response
from .sync_status import load_sync_status_response


app = FastAPI(title="AI Caddie v2", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5173",
        "http://localhost:5173",
    ],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.get("/")
def service_index() -> dict[str, object]:
    return {
        "schema": "ai-caddie-service-index-v2",
        "status": "ok",
        "service": "server_v2",
        "ui": "http://127.0.0.1:5173",
        "endpoints": {
            "health": "/api/v2/health",
            "historyOverview": "/api/v2/history/overview",
            "historyRounds": "/api/v2/history/rounds",
            "historyStats": "/api/v2/history/stats",
            "historyDrilldown": "/api/v2/history/drilldown/{source_ref}",
            "geometryCourseCoverage": "/api/v2/geometry/course/{global_id}/coverage",
            "geometryHoleEvidence": "/api/v2/geometry/hole/{global_id}/{local_hole}",
            "geometryHoleMap": "/api/v2/geometry/hole/{global_id}/{local_hole}/map",
            "caddieDecision": "/api/v2/caddie/decision",
            "annotations": "/api/v2/annotations",
            "annotationsByTarget": "/api/v2/annotations/target/{target_type}/{target_id}",
            "media": "/api/v2/media",
            "mediaByTarget": "/api/v2/media/target/{target_type}/{target_id}",
            "analyzeMedia": "/api/v2/media/{media_id}/analyze",
            "mobileRoundPackage": "/api/v2/mobile/rounds/{round_id}/package",
            "mobileRoundEvents": "/api/v2/mobile/rounds/{round_id}/events",
            "weatherSnapshot": "/api/v2/weather/snapshot",
            "roundReport": "/api/v2/reports/round/{round_id}",
            "generateRoundReport": "/api/v2/reports/round/{round_id}/generate",
            "syncStatus": "/api/v2/sync/status",
            "syncGarmin": "/api/v2/sync/garmin",
        },
    }


@app.get("/api/v2/health")
def health() -> dict[str, str]:
    return {
        "schema": "ai-caddie-health-v2",
        "status": "ok",
        "service": "server_v2",
    }


@app.get("/api/v2/history/overview", response_model=HistoryOverviewResponse)
def history_overview() -> HistoryOverviewResponse:
    return load_history_overview_response()


@app.get("/api/v2/history/rounds", response_model=HistoryRoundsResponse)
def history_rounds() -> HistoryRoundsResponse:
    return load_history_rounds_response()


@app.get("/api/v2/history/stats", response_model=HistoryStatsResponse)
def history_stats() -> HistoryStatsResponse:
    return load_history_stats_response()


@app.get("/api/v2/history/drilldown/{source_ref}", response_model=HistoryDrilldownResponse)
def history_drilldown(source_ref: str) -> HistoryDrilldownResponse:
    return load_history_drilldown_response(source_ref)


@app.get("/api/v2/geometry/course/{global_id}/coverage", response_model=CourseGeometryCoverageResponse)
def geometry_course_coverage(
    global_id: int,
    holes: list[int] | None = Query(default=None),
) -> CourseGeometryCoverageResponse:
    return load_course_geometry_coverage_response(global_id, holes=holes)


@app.get("/api/v2/geometry/hole/{global_id}/{local_hole}", response_model=GeometryEvidenceResponse)
def geometry_hole_evidence(global_id: int, local_hole: int) -> GeometryEvidenceResponse:
    return load_hole_geometry_evidence_response(global_id, local_hole)


@app.get("/api/v2/geometry/hole/{global_id}/{local_hole}/map", response_model=HoleMapResponse)
def geometry_hole_map(global_id: int, local_hole: int, provider: str = "esri_world_imagery") -> HoleMapResponse:
    return load_hole_map_response(global_id, local_hole, provider=provider)


@app.post("/api/v2/caddie/decision", response_model=CaddieDecisionResponse)
def caddie_decision(request: CaddieDecisionRequest) -> CaddieDecisionResponse:
    return build_caddie_decision_response(request)


@app.get("/api/v2/annotations", response_model=AnnotationListResponse)
def annotations() -> AnnotationListResponse:
    return list_annotation_response()


@app.post("/api/v2/annotations", response_model=AnnotationCreateResponse)
def create_annotation(request: AnnotationCreateRequest) -> AnnotationCreateResponse:
    return create_annotation_response(request)


@app.get("/api/v2/annotations/target/{target_type}/{target_id}", response_model=AnnotationListResponse)
def annotations_by_target(target_type: AnnotationTargetType, target_id: str) -> AnnotationListResponse:
    return list_target_annotation_response(target_type, target_id)


@app.post("/api/v2/media", response_model=MediaCreateResponse)
def create_media(request: MediaCreateRequest) -> MediaCreateResponse:
    return create_media_response(request)


@app.get("/api/v2/media/target/{target_type}/{target_id}", response_model=MediaListResponse)
def media_by_target(target_type: MediaTargetType, target_id: str) -> MediaListResponse:
    return list_target_media_response(target_type, target_id)


@app.post("/api/v2/media/{media_id}/analyze", response_model=VisionAnalysisResponse)
def analyze_media(media_id: str) -> VisionAnalysisResponse:
    return analyze_media_response(media_id)


@app.get("/api/v2/mobile/rounds/{round_id}/package", response_model=LiveRoundPackageResponse)
def mobile_round_package(round_id: str) -> LiveRoundPackageResponse:
    return build_mobile_round_package_response(round_id)


@app.post("/api/v2/mobile/rounds/{round_id}/events", response_model=LiveRoundEventBatchResponse)
def mobile_round_events(
    round_id: str,
    request: LiveRoundEventBatchRequest,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
) -> LiveRoundEventBatchResponse:
    return append_mobile_events_response(round_id, request, idempotency_key=idempotency_key)


@app.get("/api/v2/weather/snapshot", response_model=WeatherSnapshotResponse)
def weather_snapshot(
    source: Literal["manual", "open_meteo"] = "manual",
    persist: bool = False,
    round_id: str | None = None,
    hole: int | None = None,
    captured_at: str | None = None,
    latitude: float | None = None,
    longitude: float | None = None,
    wind_speed_mps: float | None = None,
    wind_direction_deg: int | None = None,
    temperature_c: float | None = None,
    precipitation_mm: float | None = None,
) -> WeatherSnapshotResponse:
    return load_weather_snapshot_response(
        source=source,
        persist=persist,
        round_id=round_id,
        hole=hole,
        captured_at=captured_at,
        latitude=latitude,
        longitude=longitude,
        wind_speed_mps=wind_speed_mps,
        wind_direction_deg=wind_direction_deg,
        temperature_c=temperature_c,
        precipitation_mm=precipitation_mm,
    )


@app.get("/api/v2/reports/round/{round_id}", response_model=ReviewReportResponse)
def round_report(round_id: str) -> ReviewReportResponse:
    return load_round_report_response(round_id)


@app.post("/api/v2/reports/round/{round_id}/generate", response_model=ReviewReportResponse)
def generate_round_report(round_id: str) -> ReviewReportResponse:
    return generate_round_report_response(round_id)


@app.get("/api/v2/sync/status", response_model=SyncStatusResponse)
def sync_status() -> SyncStatusResponse:
    return load_sync_status_response()


@app.post("/api/v2/sync/garmin", response_model=SyncRunResponse)
def sync_garmin(
    response: Response,
    with_shots: bool = True,
    force_refresh_auth: bool = False,
) -> SyncRunResponse:
    result = GarminCnWebSessionConnector().sync(
        with_shots=with_shots,
        force_refresh_auth=force_refresh_auth,
    )
    if result.state == "reauth_required":
        response.status_code = 409
    elif result.state == "error":
        response.status_code = 500
    return SyncRunResponse(
        schema="ai-caddie-sync-run-v2",
        connector=result.connector,
        state=result.state,
        detail=sanitize_error(result.detail),
        reauthRequired=result.state == "reauth_required",
        errorCode=result.error_code,
        snapshot=snapshot_to_payload(result.snapshot) if result.snapshot else None,
    )
