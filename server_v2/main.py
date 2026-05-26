from __future__ import annotations

import hmac
import os
from typing import Annotated, Literal

from fastapi import FastAPI, Header, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.datastructures import QueryParams

from ai_caddie.connectors.garmin_cn import GarminCnWebSessionConnector, sanitize_error
from ai_caddie.connectors.snapshot import snapshot_to_payload

from .annotations import create_annotation_response, list_annotation_response, list_target_annotation_response
from .caddie import (
    build_caddie_context_response,
    build_caddie_decision_response,
    create_decision_audit_response,
    latest_decision_audit_response,
)
from .history_overview import load_history_overview_response
from .history_rounds import load_history_rounds_response
from .history_drilldown import load_history_drilldown_response
from .history_stats import load_history_stats_response
from .geometry import load_course_geometry_coverage_response, load_hole_geometry_evidence_response, load_hole_map_response
from .media import (
    analyze_media_response,
    create_media_response,
    list_target_media_response,
    list_target_vision_findings_response,
)
from .mobile import (
    append_mobile_events_response,
    apply_mobile_round_reconciliation_response,
    build_mobile_round_package_response,
    reconcile_mobile_round_response,
)
from .weather import load_weather_snapshot_response
from .models import (
    AnnotationCreateRequest,
    AnnotationCreateResponse,
    AnnotationListResponse,
    AnnotationTargetType,
    CaddieDecisionRequest,
    CaddieDecisionResponse,
    CaddieContextResponse,
    CaddieDecisionAuditLatestResponse,
    CaddieDecisionAuditRequest,
    CaddieDecisionAuditStoreResponse,
    CourseGeometryCoverageResponse,
    GarminSessionImportRequest,
    GarminSessionImportResponse,
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
    MobileReconciliationApplyRequest,
    MobileReconciliationApplyResponse,
    MobileReconciliationResponse,
    ReviewReportIndexResponse,
    ReviewReportResponse,
    SyncRunResponse,
    SyncStatusResponse,
    VisionAnalysisResponse,
    VisionFindingsListResponse,
    WeatherSnapshotResponse,
)
from .reports import (
    generate_round_report_response,
    generate_trend_report_response,
    load_report_index_response,
    load_round_report_response,
    load_trend_report_response,
)
from .readiness import build_readiness_response
from .session import save_garmin_session_response
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

AdminTokenHeader = Annotated[str | None, Header(alias="X-AI-Caddie-Admin-Token")]


def require_admin_token(header_value: str | None) -> None:
    expected = os.environ.get("AI_CADDIE_ADMIN_TOKEN")
    if expected and not hmac.compare_digest(header_value or "", expected):
        raise HTTPException(status_code=401, detail="admin token required")


def _truthy_query_flag(value: str | None) -> bool:
    return str(value or "").lower() in {"1", "true", "on", "yes"}


def _requires_admin_token(method: str, path: str, query_params: QueryParams) -> bool:
    normalized_method = method.upper()
    if normalized_method == "GET":
        return (
            (path == "/api/v2/weather/snapshot" and _truthy_query_flag(query_params.get("persist")))
            or (path.startswith("/api/v2/mobile/rounds/") and path.endswith("/package"))
            or (path.startswith("/api/v2/mobile/rounds/") and path.endswith("/reconciliation"))
        )
    if normalized_method != "POST":
        return False
    exact_paths = {
        "/api/v2/caddie/decision",
        "/api/v2/annotations",
        "/api/v2/media",
        "/api/v2/sync/garmin",
        "/api/v2/sync/garmin/session",
    }
    if path in exact_paths:
        return True
    protected_prefix_suffix = (
        ("/api/v2/caddie/decisions/", "/audit"),
        ("/api/v2/media/", "/analyze"),
        ("/api/v2/mobile/rounds/", "/events"),
        ("/api/v2/mobile/rounds/", "/reconciliation/apply"),
        ("/api/v2/reports/round/", "/generate"),
        ("/api/v2/reports/trend/", "/generate"),
    )
    return any(path.startswith(prefix) and path.endswith(suffix) for prefix, suffix in protected_prefix_suffix)


@app.middleware("http")
async def enforce_admin_token_before_body_validation(request: Request, call_next):
    if _requires_admin_token(request.method, request.url.path, request.query_params):
        try:
            require_admin_token(request.headers.get("x-ai-caddie-admin-token"))
        except HTTPException as exc:
            return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)
    return await call_next(request)


@app.get("/")
def service_index() -> dict[str, object]:
    return {
        "schema": "ai-caddie-service-index-v2",
        "status": "ok",
        "service": "server_v2",
        "ui": "http://127.0.0.1:5173",
        "endpoints": {
            "health": "/api/v2/health",
            "readiness": "/api/v2/readiness",
            "historyOverview": "/api/v2/history/overview",
            "historyRounds": "/api/v2/history/rounds",
            "historyStats": "/api/v2/history/stats",
            "historyDrilldown": "/api/v2/history/drilldown/{source_ref}",
            "geometryCourseCoverage": "/api/v2/geometry/course/{global_id}/coverage",
            "geometryHoleEvidence": "/api/v2/geometry/hole/{global_id}/{local_hole}",
            "geometryHoleMap": "/api/v2/geometry/hole/{global_id}/{local_hole}/map",
            "caddieContext": "/api/v2/caddie/context",
            "caddieDecision": "/api/v2/caddie/decision",
            "caddieDecisionAudit": "/api/v2/caddie/decisions/{decision_id}/audit",
            "caddieDecisionAuditLatest": "/api/v2/caddie/decisions/{decision_id}/audit/latest",
            "annotations": "/api/v2/annotations",
            "annotationsByTarget": "/api/v2/annotations/target/{target_type}/{target_id}",
            "media": "/api/v2/media",
            "mediaByTarget": "/api/v2/media/target/{target_type}/{target_id}",
            "visionFindingsByTarget": "/api/v2/media/target/{target_type}/{target_id}/findings",
            "analyzeMedia": "/api/v2/media/{media_id}/analyze",
            "mobileRoundPackage": "/api/v2/mobile/rounds/{round_id}/package",
            "mobileRoundEvents": "/api/v2/mobile/rounds/{round_id}/events",
            "mobileRoundReconciliation": "/api/v2/mobile/rounds/{round_id}/reconciliation",
            "mobileRoundReconciliationApply": "/api/v2/mobile/rounds/{round_id}/reconciliation/apply",
            "weatherSnapshot": "/api/v2/weather/snapshot",
            "reportIndex": "/api/v2/reports",
            "roundReport": "/api/v2/reports/round/{round_id}",
            "generateRoundReport": "/api/v2/reports/round/{round_id}/generate",
            "trendReport": "/api/v2/reports/trend/{period}",
            "generateTrendReport": "/api/v2/reports/trend/{period}/generate",
            "syncStatus": "/api/v2/sync/status",
            "syncGarmin": "/api/v2/sync/garmin",
            "saveGarminSession": "/api/v2/sync/garmin/session",
        },
    }


@app.get("/api/v2/health")
def health() -> dict[str, str]:
    return {
        "schema": "ai-caddie-health-v2",
        "status": "ok",
        "service": "server_v2",
    }


@app.get("/api/v2/readiness")
def readiness() -> dict[str, object]:
    return build_readiness_response()


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
def geometry_hole_evidence(global_id: int, local_hole: int, source_ref: str | None = None) -> GeometryEvidenceResponse:
    return load_hole_geometry_evidence_response(global_id, local_hole, source_ref=source_ref)


@app.get("/api/v2/geometry/hole/{global_id}/{local_hole}/map", response_model=HoleMapResponse)
def geometry_hole_map(
    global_id: int,
    local_hole: int,
    provider: str = "esri_world_imagery",
    source_ref: str | None = None,
) -> HoleMapResponse:
    return load_hole_map_response(global_id, local_hole, provider=provider, source_ref=source_ref)


@app.get("/api/v2/caddie/context", response_model=CaddieContextResponse)
def caddie_context(
    source_ref: str,
    shot_type: Literal["tee", "approach", "recovery"] = "approach",
    distance_to_pin_m: float | None = None,
    lie: str | None = None,
) -> CaddieContextResponse:
    return build_caddie_context_response(
        source_ref=source_ref,
        shot_type=shot_type,
        distance_to_pin_m=distance_to_pin_m,
        lie=lie,
    )


@app.post("/api/v2/caddie/decision", response_model=CaddieDecisionResponse)
def caddie_decision(
    request: CaddieDecisionRequest,
    x_ai_caddie_admin_token: AdminTokenHeader = None,
) -> CaddieDecisionResponse:
    require_admin_token(x_ai_caddie_admin_token)
    return build_caddie_decision_response(request)


@app.post("/api/v2/caddie/decisions/{decision_id}/audit", response_model=CaddieDecisionAuditStoreResponse)
def caddie_decision_audit(
    decision_id: str,
    request: CaddieDecisionAuditRequest,
    x_ai_caddie_admin_token: AdminTokenHeader = None,
) -> CaddieDecisionAuditStoreResponse:
    require_admin_token(x_ai_caddie_admin_token)
    return create_decision_audit_response(decision_id, request)


@app.get("/api/v2/caddie/decisions/{decision_id}/audit/latest", response_model=CaddieDecisionAuditLatestResponse)
def caddie_decision_audit_latest(decision_id: str) -> CaddieDecisionAuditLatestResponse:
    return latest_decision_audit_response(decision_id)


@app.get("/api/v2/annotations", response_model=AnnotationListResponse)
def annotations() -> AnnotationListResponse:
    return list_annotation_response()


@app.post("/api/v2/annotations", response_model=AnnotationCreateResponse)
def create_annotation(
    request: AnnotationCreateRequest,
    x_ai_caddie_admin_token: AdminTokenHeader = None,
) -> AnnotationCreateResponse:
    require_admin_token(x_ai_caddie_admin_token)
    return create_annotation_response(request)


@app.get("/api/v2/annotations/target/{target_type}/{target_id}", response_model=AnnotationListResponse)
def annotations_by_target(target_type: AnnotationTargetType, target_id: str) -> AnnotationListResponse:
    return list_target_annotation_response(target_type, target_id)


@app.post("/api/v2/media", response_model=MediaCreateResponse)
def create_media(
    request: MediaCreateRequest,
    x_ai_caddie_admin_token: AdminTokenHeader = None,
) -> MediaCreateResponse:
    require_admin_token(x_ai_caddie_admin_token)
    return create_media_response(request)


@app.get("/api/v2/media/target/{target_type}/{target_id}", response_model=MediaListResponse)
def media_by_target(target_type: MediaTargetType, target_id: str) -> MediaListResponse:
    return list_target_media_response(target_type, target_id)


@app.get("/api/v2/media/target/{target_type}/{target_id}/findings", response_model=VisionFindingsListResponse)
def vision_findings_by_target(target_type: MediaTargetType, target_id: str) -> VisionFindingsListResponse:
    return list_target_vision_findings_response(target_type, target_id)


@app.post("/api/v2/media/{media_id}/analyze", response_model=VisionAnalysisResponse)
def analyze_media(
    media_id: str,
    x_ai_caddie_admin_token: AdminTokenHeader = None,
) -> VisionAnalysisResponse:
    require_admin_token(x_ai_caddie_admin_token)
    return analyze_media_response(media_id)


@app.get("/api/v2/mobile/rounds/{round_id}/package", response_model=LiveRoundPackageResponse)
def mobile_round_package(round_id: str) -> LiveRoundPackageResponse:
    return build_mobile_round_package_response(round_id)


@app.post("/api/v2/mobile/rounds/{round_id}/events", response_model=LiveRoundEventBatchResponse)
def mobile_round_events(
    round_id: str,
    request: LiveRoundEventBatchRequest,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
    x_ai_caddie_admin_token: AdminTokenHeader = None,
) -> LiveRoundEventBatchResponse:
    require_admin_token(x_ai_caddie_admin_token)
    return append_mobile_events_response(round_id, request, idempotency_key=idempotency_key)


@app.get("/api/v2/mobile/rounds/{round_id}/reconciliation", response_model=MobileReconciliationResponse)
def mobile_round_reconciliation(round_id: str) -> MobileReconciliationResponse:
    return reconcile_mobile_round_response(round_id)


@app.post("/api/v2/mobile/rounds/{round_id}/reconciliation/apply", response_model=MobileReconciliationApplyResponse)
def mobile_round_reconciliation_apply(
    round_id: str,
    request: MobileReconciliationApplyRequest,
    x_ai_caddie_admin_token: AdminTokenHeader = None,
) -> MobileReconciliationApplyResponse:
    require_admin_token(x_ai_caddie_admin_token)
    return apply_mobile_round_reconciliation_response(round_id, request)


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
    x_ai_caddie_admin_token: AdminTokenHeader = None,
) -> WeatherSnapshotResponse:
    if persist:
        require_admin_token(x_ai_caddie_admin_token)
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


@app.get("/api/v2/reports", response_model=ReviewReportIndexResponse)
def report_index() -> ReviewReportIndexResponse:
    return load_report_index_response()


@app.get("/api/v2/reports/round/{round_id}", response_model=ReviewReportResponse)
def round_report(round_id: str) -> ReviewReportResponse:
    return load_round_report_response(round_id)


@app.post("/api/v2/reports/round/{round_id}/generate", response_model=ReviewReportResponse)
def generate_round_report(round_id: str, x_ai_caddie_admin_token: AdminTokenHeader = None) -> ReviewReportResponse:
    require_admin_token(x_ai_caddie_admin_token)
    return generate_round_report_response(round_id)


@app.get("/api/v2/reports/trend/{period}", response_model=ReviewReportResponse)
def trend_report(period: str) -> ReviewReportResponse:
    return load_trend_report_response(period)


@app.post("/api/v2/reports/trend/{period}/generate", response_model=ReviewReportResponse)
def generate_trend_report(period: str, x_ai_caddie_admin_token: AdminTokenHeader = None) -> ReviewReportResponse:
    require_admin_token(x_ai_caddie_admin_token)
    return generate_trend_report_response(period)


@app.get("/api/v2/sync/status", response_model=SyncStatusResponse)
def sync_status() -> SyncStatusResponse:
    return load_sync_status_response()


@app.post("/api/v2/sync/garmin", response_model=SyncRunResponse)
def sync_garmin(
    response: Response,
    with_shots: bool = True,
    force_refresh_auth: bool = False,
    x_ai_caddie_admin_token: AdminTokenHeader = None,
) -> SyncRunResponse:
    require_admin_token(x_ai_caddie_admin_token)
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


@app.post("/api/v2/sync/garmin/session", response_model=GarminSessionImportResponse)
def save_garmin_session(
    request: GarminSessionImportRequest,
    x_ai_caddie_admin_token: AdminTokenHeader = None,
) -> GarminSessionImportResponse:
    require_admin_token(x_ai_caddie_admin_token)
    return save_garmin_session_response(request)
