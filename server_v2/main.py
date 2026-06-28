from __future__ import annotations

import contextlib
import hmac
import os
import threading
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, Header, HTTPException, Path, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.datastructures import QueryParams

from ai_caddie.courses import course_search
from ai_caddie.history import stats_cache
from ai_caddie.rounds import round_ingest
from ai_caddie.rounds.players import OWNER_ID
from ai_caddie.connectors.garmin_cn import GarminCnWebSessionConnector, sanitize_error, sanitize_safe_meta
from ai_caddie.connectors.snapshot import snapshot_to_payload
from ai_caddie.core.data import ROOT

from .annotations import create_annotation_response, list_annotation_response, list_target_annotation_response
from .caddie import (
    build_caddie_context_response,
    build_caddie_decision_response,
    create_decision_audit_response,
    latest_decision_audit_response,
)
from .history_overview import load_history_overview_response
from .history_rounds import load_history_rounds_response
from .history_round_detail import load_history_round_detail_response, load_round_hole_shot_map_response
from .history_drilldown import load_history_drilldown_response
from .history_stats import (
    load_history_stats_response,
    load_history_summary_response,
    load_mobile_stats_response,
    warm_stats_cache_in_background,
)
from .geometry import (
    load_course_geometry_coverage_response,
    load_geometry_ensure_response,
    load_hole_geometry_evidence_response,
    load_hole_map_response,
)
from .media import (
    analyze_media_response,
    confirm_vision_finding_response,
    create_media_response,
    list_target_media_response,
    list_target_vision_findings_response,
    redact_media_response,
)
from .mobile import (
    append_mobile_events_response,
    ack_mobile_events_response,
    apply_mobile_round_reconciliation_response,
    build_mobile_course_package_response,
    build_mobile_course_options_response,
    build_mobile_round_package_response,
    reconcile_mobile_round_response,
    replay_mobile_events_response,
    round_state_response,
)
from .auth_api import auth_router
from .players_api import (
    admin_router,
    current_player_id,
    has_valid_player_token,
    is_player_scoped_route,
    OWNER_ID,
    resolve_request_player,
)
from .prep_tips import load_prep_tips_response
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
    ClubBagResponse,
    CourseGeometryCoverageResponse,
    GarminSessionImportRequest,
    GarminSessionImportResponse,
    GeometryEnsureResponse,
    GeometryEvidenceResponse,
    HistoryDrilldownResponse,
    HoleMapResponse,
    HistoryOverviewResponse,
    HistoryRoundDetailResponse,
    RoundHoleShotMapResponse,
    HistoryRoundsResponse,
    HistoryStatsResponse,
    HistoryStatsSummaryResponse,
    MobileStatsResponse,
    LiveRoundEventBatchRequest,
    LiveRoundEventBatchResponse,
    LiveRoundEventAckRequest,
    LiveRoundEventAckResponse,
    LiveRoundEventReplayResponse,
    LiveRoundPackageResponse,
    RoundStateResponse,
    MediaCreateRequest,
    MediaCreateResponse,
    MediaListResponse,
    MediaRedactResponse,
    MobileCourseOptionsResponse,
    MediaTargetType,
    MobileReconciliationApplyRequest,
    MobileReconciliationApplyResponse,
    MobileReconciliationResponse,
    ReviewReportIndexResponse,
    ReviewReportResponse,
    RoundIngestRequest,
    RoundIngestResponse,
    SyncRunResponse,
    SyncStatusResponse,
    VisionAnalysisResponse,
    VisionFindingConfirmationRequest,
    VisionFindingConfirmationResponse,
    VisionFindingsListResponse,
    WeatherSnapshotResponse,
)
from .reports import (
    generate_club_report_response,
    generate_course_report_response,
    generate_hole_report_response,
    generate_round_report_response,
    generate_trend_report_response,
    load_club_report_response,
    load_course_report_response,
    load_hole_report_response,
    load_report_index_response,
    load_round_report_response,
    load_trend_report_response,
)
from .readiness import build_readiness_response
from .product_settings import build_product_settings_response
from .session import save_garmin_session_response
from .sync_status import load_sync_status_response


@contextlib.asynccontextmanager
async def _lifespan(_app: FastAPI):
    """FastAPI lifespan: warm history caches at startup so the first user request is a hit.

    Fires ``warm_stats_cache_in_background`` on a daemon thread immediately after the
    server starts serving.  Failure-isolated inside ``warm_stats_cache`` itself — a warm
    error never prevents the server from handling requests.  (The identity schema is owned
    solely by Alembic — ``alembic upgrade head`` in start_api.sh — never the app process,
    so create_all can never race or shadow a migration. Phase 1a is additive.)
    """
    warm_stats_cache_in_background()
    yield


app = FastAPI(title="AI Caddie v2", version="0.1.0", lifespan=_lifespan)
app.include_router(admin_router)
app.include_router(auth_router)


def cors_allowed_origins() -> list[str]:
    defaults = ["http://127.0.0.1:5173", "http://localhost:5173"]
    configured = [
        origin.strip().rstrip("/")
        for origin in os.environ.get("AI_CADDIE_CORS_ORIGINS", "").split(",")
        if origin.strip()
    ]
    origins: list[str] = []
    for origin in [*defaults, *configured]:
        if origin not in origins:
            origins.append(origin)
    return origins


def cors_allowed_origin_regex() -> str | None:
    value = os.environ.get("AI_CADDIE_CORS_ORIGIN_REGEX", "").strip()
    return value or None


app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_allowed_origins(),
    allow_origin_regex=cors_allowed_origin_regex(),
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["*"],
)

AdminTokenHeader = Annotated[str | None, Header(alias="X-AI-Caddie-Admin-Token")]


def _safe_validation_errors(exc: RequestValidationError) -> list[dict[str, object]]:
    errors = []
    for row in exc.errors():
        if not isinstance(row, dict):
            errors.append({"type": "value_error", "loc": [], "msg": str(row)})
            continue
        loc = row.get("loc")
        errors.append(
            {
                "type": str(row.get("type") or "value_error"),
                "loc": list(loc) if isinstance(loc, (list, tuple)) else [],
                "msg": str(row.get("msg") or "Invalid request"),
            }
        )
    return errors


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(_request: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse({"detail": _safe_validation_errors(exc)}, status_code=422)


def _security_profile_requires_admin() -> bool:
    profile = os.environ.get("AI_CADDIE_SECURITY_PROFILE", "").strip().lower()
    return profile in {"private", "staging", "production"}


def require_admin_token(header_value: str | None) -> None:
    expected = os.environ.get("AI_CADDIE_ADMIN_TOKEN")
    if not expected and _security_profile_requires_admin():
        raise HTTPException(status_code=503, detail="admin token not configured")
    if expected and not hmac.compare_digest(header_value or "", expected):
        raise HTTPException(status_code=401, detail="admin token required")


def _truthy_query_flag(value: str | None) -> bool:
    return str(value or "").lower() in {"1", "true", "on", "yes"}


def _requires_admin_token(method: str, path: str, query_params: QueryParams) -> bool:
    normalized_method = method.upper()
    # Every owner-management route (/api/v2/admin/*) requires the admin token,
    # regardless of method. These are never player-scoped, so a per-player token
    # cannot bypass the gate in enforce_admin_token_before_body_validation.
    if path == "/api/v2/admin" or path.startswith("/api/v2/admin/"):
        return True
    if normalized_method == "GET":
        return (
            path.startswith("/api/v2/history/")
            or (path == "/api/v2/weather/snapshot" and _truthy_query_flag(query_params.get("persist")))
            or path == "/api/v2/caddie/context"
            or (path.startswith("/api/v2/caddie/decisions/") and path.endswith("/audit/latest"))
            or path == "/api/v2/annotations"
            or path.startswith("/api/v2/annotations/target/")
            or path.startswith("/api/v2/media/target/")
            or path == "/api/v2/reports"
            or path.startswith("/api/v2/reports/")
            or (path.startswith("/api/v2/mobile/rounds/") and path.endswith("/package"))
            or path == "/api/v2/mobile/courses/options"
            or (path.startswith("/api/v2/mobile/courses/") and path.endswith("/package"))
            or (path.startswith("/api/v2/courses/") and path.endswith("/prep"))
            or (path.startswith("/api/v2/courses/") and path.endswith("/prep-tips"))
            or path == "/api/v2/courses/search"
            # codex HIGH #1: a geometry/hole request WITH source_ref loads the owner's real shot
            # routes/clubs/distances (geometry.py) — gate it. Pure course geometry (no source_ref)
            # stays public (course knowledge); only the source-bound private evidence requires auth.
            or (path.startswith("/api/v2/geometry/hole/") and bool(query_params.get("source_ref")))
            or (path.startswith("/api/v2/mobile/rounds/") and path.endswith("/events/replay"))
            or (path.startswith("/api/v2/mobile/rounds/") and path.endswith("/state"))
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
        # owner-bootstrap: links an Apple Sign-in subject to the owner user.
        "/api/v2/auth/apple/link",
    }
    if path in exact_paths:
        return True
    protected_prefix_suffix = (
        ("/api/v2/caddie/decisions/", "/audit"),
        ("/api/v2/geometry/hole/", "/ensure"),
        ("/api/v2/media/", "/analyze"),
        ("/api/v2/media/", "/redact"),
        ("/api/v2/media/findings/", "/confirmation"),
        ("/api/v2/mobile/rounds/", "/events"),
        ("/api/v2/mobile/rounds/", "/events/ack"),
        ("/api/v2/mobile/rounds/", "/reconciliation/apply"),
        ("/api/v2/reports/round/", "/generate"),
        ("/api/v2/reports/trend/", "/generate"),
        # codex MEDIUM #4: these report-generation POSTs (persist owner reports, may call an LLM) were
        # missing from the admin gate — caught by the route-policy guardrail test. Gate them like the
        # round/trend generators.
        ("/api/v2/reports/club/", "/generate"),
        ("/api/v2/reports/course/", "/generate"),
        ("/api/v2/reports/hole/", "/generate"),
    )
    return any(path.startswith(prefix) and path.endswith(suffix) for prefix, suffix in protected_prefix_suffix)


@app.middleware("http")
async def enforce_admin_token_before_body_validation(request: Request, call_next):
    if _requires_admin_token(request.method, request.url.path, request.query_params):
        # A valid per-player token grants access to player-scoped routes. Admin
        # token handling stays in require_admin_token so its 401 (configured but
        # missing) and 503 (fail-closed under a private profile) semantics — and
        # the admin-token-as-owner backward compatibility — are unchanged.
        player_token_allows = is_player_scoped_route(
            request.method, request.url.path
        ) and has_valid_player_token(request)
        if not player_token_allows:
            try:
                require_admin_token(request.headers.get("x-ai-caddie-admin-token"))
            except HTTPException as exc:
                return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)
    return await call_next(request)


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    # codex MEDIUM #10: high-privilege tokens can end up in a URL (?admin= / /p/<token>); a no-referrer
    # policy stops them leaking via the Referer header to any third party the page links to. Defined
    # after the auth middleware so it wraps it — the header is set on every response, including 401s.
    response = await call_next(request)
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    return response


# Comfortably exceeds the largest legitimate body — a base64 video upload (~80 MB raw ≈ 107 MB
# encoded) — while still rejecting absurd/GB-scale payloads before any handler buffers them.
MAX_REQUEST_BODY_BYTES = 160 * 1024 * 1024


@app.middleware("http")
async def reject_oversized_request_body(request: Request, call_next):
    # P1-8 defense-in-depth: protected POSTs are already token-gated pre-body, but nothing capped
    # body size. Refuse an over-large body by its declared Content-Length before parsing. Registered
    # last so it is the OUTERMOST middleware and rejects before auth/handlers do any work.
    raw_length = request.headers.get("content-length")
    if raw_length is not None:
        try:
            declared = int(raw_length)
        except ValueError:
            declared = -1
        if declared > MAX_REQUEST_BODY_BYTES:
            return JSONResponse({"detail": "request body too large"}, status_code=413)
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
            "productSettings": "/api/v2/settings/product",
            "historyOverview": "/api/v2/history/overview",
            "historyRounds": "/api/v2/history/rounds",
            "historyRoundDetail": "/api/v2/history/rounds/{round_ref}",
            "historyStats": "/api/v2/history/stats",
            "historySummary": "/api/v2/history/summary",
            "historyDrilldown": "/api/v2/history/drilldown/{source_ref}",
            "geometryCourseCoverage": "/api/v2/geometry/course/{global_id}/coverage",
            "geometryHoleEvidence": "/api/v2/geometry/hole/{global_id}/{local_hole}",
            "geometryEnsure": "/api/v2/geometry/hole/{global_id}/{local_hole}/ensure",
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
            "confirmVisionFinding": "/api/v2/media/findings/{finding_id}/confirmation",
            "analyzeMedia": "/api/v2/media/{media_id}/analyze",
            "redactMedia": "/api/v2/media/{media_id}/redact",
            "mobileRoundPackage": "/api/v2/mobile/rounds/{round_id}/package",
            "mobileCourseOptions": "/api/v2/mobile/courses/options",
            "mobileCoursePackage": "/api/v2/mobile/courses/{global_id}/package",
            "mobileRoundEvents": "/api/v2/mobile/rounds/{round_id}/events",
            "mobileRoundEventsReplay": "/api/v2/mobile/rounds/{round_id}/events/replay",
            "mobileRoundEventsAck": "/api/v2/mobile/rounds/{round_id}/events/ack",
            "mobileRoundReconciliation": "/api/v2/mobile/rounds/{round_id}/reconciliation",
            "mobileRoundReconciliationApply": "/api/v2/mobile/rounds/{round_id}/reconciliation/apply",
            "weatherSnapshot": "/api/v2/weather/snapshot",
            "reportIndex": "/api/v2/reports",
            "roundReport": "/api/v2/reports/round/{round_id}",
            "generateRoundReport": "/api/v2/reports/round/{round_id}/generate",
            "courseReport": "/api/v2/reports/course/{course_key}",
            "generateCourseReport": "/api/v2/reports/course/{course_key}/generate",
            "holeReport": "/api/v2/reports/hole/{course_key}/{hole}",
            "generateHoleReport": "/api/v2/reports/hole/{course_key}/{hole}/generate",
            "clubReport": "/api/v2/reports/club/{club_name}",
            "generateClubReport": "/api/v2/reports/club/{club_name}/generate",
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
def readiness(request: Request) -> dict[str, object]:
    # Owner operational evidence (round ids/counts/sync errors) + a heavy per-call
    # owner-package build are owner-only. A non-owner caller — anonymous OR a resolved
    # family member (Phase 1b made members resolve) — gets liveness only: both a data-leak
    # fix and a no-auth DoS-amplifier fix. (Liveness lives at GET /api/v2/health.)
    if resolve_request_player(request) != OWNER_ID:
        return {"schema": "ai-caddie-readiness-v1", "status": "ok"}
    return build_readiness_response()


@app.get("/api/v2/settings/product")
def product_settings() -> dict[str, object]:
    return build_product_settings_response()


@app.get("/api/v2/history/overview", response_model=HistoryOverviewResponse)
def history_overview(player_id: str = Depends(current_player_id)) -> HistoryOverviewResponse:
    return load_history_overview_response(player_id=player_id)


@app.post("/api/v2/players/{target_player_id}/rounds", response_model=RoundIngestResponse, status_code=201)
def ingest_player_round(
    target_player_id: str,
    body: RoundIngestRequest,
    request: Request,
    acting_player_id: str = Depends(current_player_id),
) -> RoundIngestResponse:
    """Land a manual ("phone") round for a player. A per-player bearer token may only
    target its own player; the owner (admin token) may target any player. Idempotent on
    the ``Idempotency-Key`` header (or a client-supplied round id)."""
    if acting_player_id != OWNER_ID and acting_player_id != target_player_id:
        raise HTTPException(status_code=403, detail="cannot ingest rounds for another player")
    idempotency_key = (
        request.headers.get("Idempotency-Key")
        or body.idempotencyKey
        or body.clientRoundId
        or round_ingest.derive_idempotency_key(target_player_id, body.events, body.meta)
    )
    try:
        summary = round_ingest.ingest_round(
            target_player_id, body.events, body.meta, idempotency_key=idempotency_key
        )
    except round_ingest.RoundIngestError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return RoundIngestResponse(**summary)


@app.get("/api/v2/history/rounds", response_model=HistoryRoundsResponse)
def history_rounds(
    year: str | None = Query(default=None),
    course: str | None = Query(default=None),
    hasShots: bool | None = Query(default=None),
    hasReport: bool | None = Query(default=None),
    limit: int = Query(default=120, ge=1, le=2000),
    player_id: str = Depends(current_player_id),
) -> HistoryRoundsResponse:
    return load_history_rounds_response(
        year=year, course=course, has_shots=hasShots, has_report=hasReport, limit=limit, player_id=player_id
    )


@app.get("/api/v2/history/rounds/{round_ref}", response_model=HistoryRoundDetailResponse)
def history_round_detail(
    round_ref: str, player_id: str = Depends(current_player_id)
) -> HistoryRoundDetailResponse:
    return load_history_round_detail_response(round_ref, player_id=player_id)


@app.get("/api/v2/history/rounds/{round_ref}/holes/{hole}/shotmap", response_model=RoundHoleShotMapResponse)
def round_hole_shot_map(
    round_ref: str, hole: int, player_id: str = Depends(current_player_id)
) -> RoundHoleShotMapResponse:
    # 复盘 per-hole shot map: this round's actual shots on the 2D render. Rendered on demand per
    # hole (one supersampled JPEG), not all 18 eagerly.
    return load_round_hole_shot_map_response(round_ref, hole, player_id=player_id)


@app.get("/api/v2/history/stats", response_model=HistoryStatsResponse)
def history_stats(
    window: str = Query("all", pattern="^(all|12m|last10)$"),
    player_id: str = Depends(current_player_id),
) -> HistoryStatsResponse:
    return load_history_stats_response(window=window, player_id=player_id)


@app.get("/api/v2/history/summary", response_model=HistoryStatsSummaryResponse)
def history_summary(
    player_id: str = Depends(current_player_id),
) -> HistoryStatsSummaryResponse:
    # 概览 landing: the few summary numbers + top issue, sliced from the cached
    # full build so the home does not download the ~20MB /history/stats payload.
    return load_history_summary_response(player_id=player_id)


@app.get("/api/v2/history/stats/mobile", response_model=MobileStatsResponse)
def history_stats_mobile(
    window: str = Query("all", pattern="^(all|12m|last10)$"),
    player_id: str = Depends(current_player_id),
) -> MobileStatsResponse:
    # Compact 统计 payload for the phone: the deep / periodic / per-course / per-club slices of the
    # full build, without the ~11MB per-hole table — sliced from the same cached stats (cache hit).
    # window (all|12m|last10) mirrors /history/stats so the GolfLive 统计 view keeps windowed KPIs.
    return load_mobile_stats_response(window=window, player_id=player_id)


@app.get("/api/v2/history/clubs/bag", response_model=ClubBagResponse)
def history_clubs_bag(
    player_id: str = Depends(current_player_id),
) -> ClubBagResponse:
    # The player's real Garmin bag (clubTypeId + custom name + retired/deleted), pulled by the sync
    # from Garmin's /club/player + /club/types. Owner-scoped; names resolve to Chinese on-device.
    from ai_caddie.caddie.club_bag import build_club_bag_response

    return ClubBagResponse(**build_club_bag_response(player_id=player_id, owner_id=OWNER_ID))


@app.get("/api/v2/history/drilldown/{source_ref}", response_model=HistoryDrilldownResponse)
def history_drilldown(
    source_ref: str, player_id: str = Depends(current_player_id)
) -> HistoryDrilldownResponse:
    return load_history_drilldown_response(source_ref, player_id=player_id)


@app.get("/api/v2/geometry/course/{global_id}/coverage", response_model=CourseGeometryCoverageResponse)
def geometry_course_coverage(
    global_id: int,
    holes: list[int] | None = Query(default=None, max_length=36),  # codex MEDIUM #6: bound item count
) -> CourseGeometryCoverageResponse:
    return load_course_geometry_coverage_response(global_id, holes=holes)


@app.get("/api/v2/geometry/hole/{global_id}/{local_hole}", response_model=GeometryEvidenceResponse)
def geometry_hole_evidence(
    global_id: int,
    local_hole: int = Path(ge=1, le=36),
    source_ref: str | None = Query(default=None, max_length=128),
    start_x: float | None = None,
    start_y: float | None = None,
    target_x: float | None = None,
    target_y: float | None = None,
    landing_radius_m: float = Query(18.0, ge=0, le=300),  # codex MEDIUM #6: bound cost/abuse
) -> GeometryEvidenceResponse:
    return load_hole_geometry_evidence_response(
        global_id,
        local_hole,
        source_ref=source_ref,
        start_x=start_x,
        start_y=start_y,
        target_x=target_x,
        target_y=target_y,
        landing_radius_m=landing_radius_m,
    )


@app.get("/api/v2/geometry/hole/{global_id}/{local_hole}/map", response_model=HoleMapResponse)
def geometry_hole_map(
    global_id: int,
    local_hole: int,
    provider: str = "esri_world_imagery",
    source_ref: str | None = None,
) -> HoleMapResponse:
    return load_hole_map_response(global_id, local_hole, provider=provider, source_ref=source_ref)


@app.get("/api/v2/courses/{global_id}/prep")
def course_prep_nine(
    global_id: int,
    holes: list[int] | None = Query(default=None, max_length=36),  # codex MEDIUM #6: bound item count
    render: bool = True,
    include_shots: bool = False,
    player_id: str = Depends(current_player_id),
) -> dict:
    """Pre-round prep for a course: per-hole par (labelled source) + route + hazard carries +
    strategy from the player's club ladder + (when render=true) a styled map image + overlay.
    Without an explicit ``holes`` filter every hole with cached geometry is served (18-hole
    single-gid courses get all 18; no geometry falls back to the front nine).
    render=false returns facts only (lightweight). include_shots=true additionally projects
    the player's past TEE/APPROACH end positions into overlay px (``yourShots``) on rendered
    holes they have history for.

    The club ladder (the player's real distances) and shot scatter (their real TEE/APPROACH
    end positions) are PLAYER data. The course_prep engine still sources both from the
    owner's data, so only the owner ("me", incl. the admin token) gets the real ladder +
    scatter; a non-owner player gets the course knowledge (par/route/hazards) with a generic
    default ladder and never the owner's projected shots (per-player engine scoping is a
    multiplayer-foundation follow-up)."""
    from ai_caddie.courses import course_prep, prep_cache

    is_owner = player_id == OWNER_ID
    requested = holes or course_prep.available_prep_holes(global_id)

    # prep_nine rebuilds all-hole mesh geometry (~19s for a 9-hole course) on every request; cache the
    # response by filesystem fingerprint so 备战 opens instantly until geometry / shots / clubs change.
    def _build() -> dict:
        # Owner reads their real club model; a non-owner falls back to the generic default
        # ladder so the owner's measured distances never leak.
        ladder = course_prep.club_ladder() if is_owner else sorted(
            course_prep.DEFAULT_LADDER.items(), key=lambda kv: -kv[1]
        )
        # Shot scatter projects the owner's real end positions — never expose it to a non-owner.
        nine = course_prep.prep_nine(global_id, requested, ladder=ladder, render=render, include_missing=True,
                                     include_shots=include_shots and is_owner)
        return {
            "schema": "ai-caddie-course-prep-v1",
            "globalId": int(global_id),
            "holeCount": len(nine),
            "clubs": [{"name": name, "m": dist, "yd": course_prep.yd(dist)} for name, dist in ladder],
            "holes": nine,
        }

    return prep_cache.cached_course_prep(
        global_id=global_id, requested=requested, render=render,
        include_shots=include_shots, player_id=player_id, build=_build,
    )


@app.get("/api/v2/courses/{global_id}/prep-tips")
def course_prep_tips(global_id: int, player_id: str = Depends(current_player_id)) -> dict:
    """Deterministic pre-round tips (zh, with sourceRefs) assembled from the player's
    EXISTING per-course tendencies (teeDirection/approachMiss/parScoring + playerProfile
    caddie biases) crossed with this course's prep hole features. Never-played courses
    degrade to global-profile tips plus a length-based informational tip."""
    return load_prep_tips_response(global_id, player_id=player_id)


@app.get("/api/v2/courses/search")
def course_search_endpoint(
    name: str,
    city: str | None = None,
    holes: int | None = None,
) -> dict:
    """Search Garmin's course DB by name (+ optional city / hole-count guard); returns ranked
    matches with globalId. Feed a chosen globalId into /api/v2/courses/{global_id}/prep."""
    matches = course_search.courseview_search(name, city=city, expected_holes=holes)
    return {
        "schema": "ai-caddie-course-search-v1",
        "query": name,
        "matches": [
            {"globalId": m.global_id, "name": m.name, "holes": m.holes,
             "city": m.city, "province": m.province, "ratio": m.ratio}
            for m in matches
        ],
    }


@app.post("/api/v2/geometry/hole/{global_id}/{local_hole}/ensure", response_model=GeometryEnsureResponse)
def geometry_hole_ensure(
    global_id: int,
    local_hole: int,
    profile_id: str | None = None,
    force: bool = False,
    x_ai_caddie_admin_token: AdminTokenHeader = None,
) -> GeometryEnsureResponse:
    require_admin_token(x_ai_caddie_admin_token)
    return load_geometry_ensure_response(global_id, local_hole, profile_id=profile_id, force=force)


@app.get("/api/v2/caddie/context", response_model=CaddieContextResponse)
def caddie_context(
    source_ref: str,
    shot_type: Literal["tee", "approach", "recovery"] = "approach",
    distance_to_pin_m: float | None = None,
    lie: str | None = None,
    current_latitude: float | None = None,
    current_longitude: float | None = None,
    target_latitude: float | None = None,
    target_longitude: float | None = None,
    strategy_mode: str | None = None,
    start_x: float | None = None,
    start_y: float | None = None,
    target_x: float | None = None,
    target_y: float | None = None,
    landing_radius_m: float = 18.0,
    captured_at: str | None = None,
    player_id: str = Depends(current_player_id),
) -> CaddieContextResponse:
    return build_caddie_context_response(
        source_ref=source_ref,
        shot_type=shot_type,
        distance_to_pin_m=distance_to_pin_m,
        lie=lie,
        current_latitude=current_latitude,
        current_longitude=current_longitude,
        target_latitude=target_latitude,
        target_longitude=target_longitude,
        strategy_mode=strategy_mode,
        start_x=start_x,
        start_y=start_y,
        target_x=target_x,
        target_y=target_y,
        landing_radius_m=landing_radius_m,
        captured_at=captured_at,
        player_id=player_id,
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
def caddie_decision_audit_latest(
    decision_id: str,
    x_ai_caddie_admin_token: AdminTokenHeader = None,
) -> CaddieDecisionAuditLatestResponse:
    require_admin_token(x_ai_caddie_admin_token)
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


@app.post("/api/v2/media/{media_id}/redact", response_model=MediaRedactResponse)
def redact_media(
    media_id: str,
    x_ai_caddie_admin_token: AdminTokenHeader = None,
) -> MediaRedactResponse:
    require_admin_token(x_ai_caddie_admin_token)
    return redact_media_response(media_id)


@app.post("/api/v2/media/findings/{finding_id}/confirmation", response_model=VisionFindingConfirmationResponse)
def confirm_vision_finding_route(
    finding_id: str,
    request: VisionFindingConfirmationRequest,
    x_ai_caddie_admin_token: AdminTokenHeader = None,
) -> VisionFindingConfirmationResponse:
    require_admin_token(x_ai_caddie_admin_token)
    return confirm_vision_finding_response(finding_id, request)


@app.get("/api/v2/mobile/rounds/{round_id}/package", response_model=LiveRoundPackageResponse)
def mobile_round_package(
    round_id: str,
    captured_at: str | None = None,
    client_id: str | None = None,
    ensure_geometry: bool = False,
    player_id: str = Depends(current_player_id),
) -> LiveRoundPackageResponse:
    return build_mobile_round_package_response(
        round_id,
        captured_at=captured_at,
        client_id=client_id,
        ensure_geometry=ensure_geometry,
        player_id=player_id,
    )


@app.get("/api/v2/mobile/courses/options", response_model=MobileCourseOptionsResponse)
def mobile_course_options(player_id: str = Depends(current_player_id)) -> MobileCourseOptionsResponse:
    return build_mobile_course_options_response(player_id=player_id)


@app.get("/api/v2/mobile/courses/{global_id}/package", response_model=LiveRoundPackageResponse)
def mobile_course_package(
    global_id: int,
    round_id: str | None = None,
    tee_box: str | None = None,
    captured_at: str | None = None,
    client_id: str | None = None,
    ensure_geometry: bool = False,
    nine: str = Query(default="all", pattern="^(all|front|back)$"),
    back_global_id: int | None = None,
    player_id: str = Depends(current_player_id),
) -> LiveRoundPackageResponse:
    return build_mobile_course_package_response(
        global_id,
        round_id=round_id,
        tee_box=tee_box,
        captured_at=captured_at,
        client_id=client_id,
        ensure_geometry=ensure_geometry,
        nine=nine,
        back_global_id=back_global_id,
        player_id=player_id,
    )


@app.post("/api/v2/mobile/rounds/{round_id}/events", response_model=LiveRoundEventBatchResponse)
def mobile_round_events(
    round_id: str,
    request: LiveRoundEventBatchRequest,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
    x_ai_caddie_admin_token: AdminTokenHeader = None,
) -> LiveRoundEventBatchResponse:
    require_admin_token(x_ai_caddie_admin_token)
    return append_mobile_events_response(round_id, request, idempotency_key=idempotency_key)


@app.get("/api/v2/mobile/rounds/{round_id}/events/replay", response_model=LiveRoundEventReplayResponse)
def mobile_round_events_replay(
    round_id: str,
    client_id: str | None = None,
    after_sequence: int | None = None,
    limit: int = 100,
) -> LiveRoundEventReplayResponse:
    return replay_mobile_events_response(
        round_id,
        client_id=client_id,
        after_sequence=after_sequence,
        limit=limit,
    )


@app.post("/api/v2/mobile/rounds/{round_id}/events/ack", response_model=LiveRoundEventAckResponse)
def mobile_round_events_ack(
    round_id: str,
    request: LiveRoundEventAckRequest,
    x_ai_caddie_admin_token: AdminTokenHeader = None,
) -> LiveRoundEventAckResponse:
    require_admin_token(x_ai_caddie_admin_token)
    return ack_mobile_events_response(round_id, request)


@app.get("/api/v2/mobile/rounds/{round_id}/state", response_model=RoundStateResponse)
def mobile_round_state(
    round_id: str,
    x_ai_caddie_admin_token: AdminTokenHeader = None,
) -> RoundStateResponse:
    # round-12 sync spine: authoritative server-projected round state (folded from the event log).
    # Admin-gated like POST/ack (the authoritative read), so multi-client pull is consistently authed.
    require_admin_token(x_ai_caddie_admin_token)
    return round_state_response(round_id)


@app.get("/api/v2/mobile/rounds/{round_id}/reconciliation", response_model=MobileReconciliationResponse)
def mobile_round_reconciliation(
    round_id: str,
    player_id: str = Depends(current_player_id),
) -> MobileReconciliationResponse:
    return reconcile_mobile_round_response(round_id, player_id=player_id)


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
def report_index(player_id: str = Depends(current_player_id)) -> ReviewReportIndexResponse:
    # The report store is a shared single-file store of OWNER-generated reports only
    # (generation is admin-only). The owner ("me", incl. the admin token) sees the index;
    # a non-owner player gets an empty index — never the owner's stored reports/round ids.
    return load_report_index_response(player_id=player_id)


@app.get("/api/v2/reports/round/{round_id}", response_model=ReviewReportResponse)
def round_report(round_id: str, player_id: str = Depends(current_player_id)) -> ReviewReportResponse:
    return load_round_report_response(round_id, player_id=player_id)


@app.post("/api/v2/reports/round/{round_id}/generate", response_model=ReviewReportResponse)
def generate_round_report(round_id: str, x_ai_caddie_admin_token: AdminTokenHeader = None) -> ReviewReportResponse:
    require_admin_token(x_ai_caddie_admin_token)
    return generate_round_report_response(round_id)


@app.get("/api/v2/reports/course/{course_key}", response_model=ReviewReportResponse)
def course_report(course_key: str, player_id: str = Depends(current_player_id)) -> ReviewReportResponse:
    return load_course_report_response(course_key, player_id=player_id)


@app.post("/api/v2/reports/course/{course_key}/generate", response_model=ReviewReportResponse)
def generate_course_report(course_key: str, x_ai_caddie_admin_token: AdminTokenHeader = None) -> ReviewReportResponse:
    require_admin_token(x_ai_caddie_admin_token)
    return generate_course_report_response(course_key)


@app.get("/api/v2/reports/hole/{course_key}/{hole}", response_model=ReviewReportResponse)
def hole_report(
    course_key: str, hole: int, player_id: str = Depends(current_player_id)
) -> ReviewReportResponse:
    return load_hole_report_response(course_key, hole, player_id=player_id)


@app.post("/api/v2/reports/hole/{course_key}/{hole}/generate", response_model=ReviewReportResponse)
def generate_hole_report(course_key: str, hole: int, x_ai_caddie_admin_token: AdminTokenHeader = None) -> ReviewReportResponse:
    require_admin_token(x_ai_caddie_admin_token)
    return generate_hole_report_response(course_key, hole)


@app.get("/api/v2/reports/club/{club_name}", response_model=ReviewReportResponse)
def club_report(club_name: str, player_id: str = Depends(current_player_id)) -> ReviewReportResponse:
    return load_club_report_response(club_name, player_id=player_id)


@app.post("/api/v2/reports/club/{club_name}/generate", response_model=ReviewReportResponse)
def generate_club_report(club_name: str, x_ai_caddie_admin_token: AdminTokenHeader = None) -> ReviewReportResponse:
    require_admin_token(x_ai_caddie_admin_token)
    return generate_club_report_response(club_name)


@app.get("/api/v2/reports/trend/{period}", response_model=ReviewReportResponse)
def trend_report(period: str, player_id: str = Depends(current_player_id)) -> ReviewReportResponse:
    return load_trend_report_response(period, player_id=player_id)


@app.post("/api/v2/reports/trend/{period}/generate", response_model=ReviewReportResponse)
def generate_trend_report(period: str, x_ai_caddie_admin_token: AdminTokenHeader = None) -> ReviewReportResponse:
    require_admin_token(x_ai_caddie_admin_token)
    return generate_trend_report_response(period)


@app.get("/api/v2/sync/status")
def sync_status(request: Request) -> SyncStatusResponse | dict[str, str]:
    # Owner sync metadata (scorecard/shot counts, last-run error code, the course
    # global-IDs the owner plays, snapshot id) is owner-only. Anonymous callers get
    # connector liveness only — no counts, course ids, or error codes.
    # Owner-only. A *resolved* non-owner member token (Phase 1b made members resolve)
    # would otherwise read the owner's sync metadata, so gate on OWNER_ID — not merely
    # "some player". Members and anonymous callers both get connector liveness only.
    if resolve_request_player(request) != OWNER_ID:
        return {"schema": "ai-caddie-sync-status-v2", "status": "ok"}
    return load_sync_status_response()


# Serialises Garmin sync (it mutates process-global token/data paths — codex HIGH #2).
_SYNC_LOCK = threading.Lock()

# Repo root for the per-player connector (data/players/<id>/ lives under it). Module-level
# so tests can repoint it; production = the real data root, so the member route is byte-for-byte.
SYNC_ROOT = ROOT


@app.post("/api/v2/sync/garmin", response_model=SyncRunResponse)
def sync_garmin(
    response: Response,
    with_shots: bool = True,
    force_refresh_auth: bool = False,
    ensure_geometry: bool = False,
    x_ai_caddie_admin_token: AdminTokenHeader = None,
) -> SyncRunResponse:
    require_admin_token(x_ai_caddie_admin_token)
    # codex HIGH #2: Garmin sync mutates process-global token/data paths (connectors/garmin_cn.py),
    # so two concurrent syncs would cross-contaminate. Serialise with a non-blocking lock — a second
    # concurrent sync is rejected (409) rather than racing the in-flight one.
    if not _SYNC_LOCK.acquire(blocking=False):
        raise HTTPException(status_code=409, detail="sync already in progress")
    try:
        result = GarminCnWebSessionConnector().sync(
            with_shots=with_shots,
            force_refresh_auth=force_refresh_auth,
            ensure_geometry=ensure_geometry,
        )
    finally:
        _SYNC_LOCK.release()
    if result.state == "reauth_required":
        response.status_code = 409
    elif result.state == "error":
        response.status_code = 500
    elif result.state == "ready":
        # The sync just wrote new scorecards/shots to disk, invalidating the stats-cache
        # fingerprint. Warm it on a daemon thread so the FIRST user request after the
        # sync is a cache hit instead of a ~10s cold recompute. Failure-isolated inside
        # warm_stats_cache, so it can never break this response.
        warm_stats_cache_in_background()
    return SyncRunResponse(
        schema="ai-caddie-sync-run-v2",
        connector=result.connector,
        state=result.state,
        detail=sanitize_error(result.detail),
        reauthRequired=result.state == "reauth_required",
        errorCode=result.error_code,
        snapshot=snapshot_to_payload(result.snapshot) if result.snapshot else None,
        safeMeta=sanitize_safe_meta(result.safe_meta),
    )


@app.post("/api/v2/sync/garmin/session", response_model=GarminSessionImportResponse)
def save_garmin_session(
    request: GarminSessionImportRequest,
    x_ai_caddie_admin_token: AdminTokenHeader = None,
) -> GarminSessionImportResponse:
    require_admin_token(x_ai_caddie_admin_token)
    return save_garmin_session_response(request)


# --- Member self-binding (Phase B) -------------------------------------------------
# These per-player routes mirror POST /api/v2/players/{id}/rounds: a per-player bearer
# token may target only its OWN player; the owner (admin token) may target any player.
# They are POST and deliberately NOT in the admin exact_paths, so a member token reaches
# them via current_player_id. The legacy admin /api/v2/sync/garmin[/session] stay owner-only.


@app.post("/api/v2/players/{player_id}/sync/garmin/session", response_model=GarminSessionImportResponse)
def save_player_garmin_session(
    player_id: str,
    request: GarminSessionImportRequest,
    acting_player_id: str = Depends(current_player_id),
) -> GarminSessionImportResponse:
    """Bind a captured Garmin web session for ``player_id``. A per-player token may bind
    only its own Garmin; the owner (admin token) may bind for any player. The cookie lands
    in the player's partition (data/players/<id>/.garmin_tokens) — no member credentials
    are stored, so the member re-binds via the WebView when the cookie expires."""
    if acting_player_id != OWNER_ID and acting_player_id != player_id:
        raise HTTPException(status_code=403, detail="cannot bind Garmin for another player")
    return save_garmin_session_response(request, player_id=player_id)


@app.post("/api/v2/players/{player_id}/sync/garmin", response_model=SyncRunResponse)
def sync_player_garmin(
    player_id: str,
    response: Response,
    with_shots: bool = True,
    acting_player_id: str = Depends(current_player_id),
) -> SyncRunResponse:
    """Run a Garmin sync for ``player_id`` into their partition (data/players/<id>/). A
    per-player token may sync only itself; the owner (admin token) may sync any player.

    A member never self-heals (no stored member creds): a missing/expired cookie returns a
    clear re-bind 4xx (409), never the owner's cookie, never a 500. The headed-Playwright
    self-heal + geometry-ensure stay on the legacy owner-only route."""
    if acting_player_id != OWNER_ID and acting_player_id != player_id:
        raise HTTPException(status_code=403, detail="cannot sync Garmin for another player")
    # Same global lock as the legacy sync: the connector mutates process-global fetch paths,
    # so a member sync and any other sync must not run concurrently.
    if not _SYNC_LOCK.acquire(blocking=False):
        raise HTTPException(status_code=409, detail="sync already in progress")
    try:
        result = GarminCnWebSessionConnector(root=SYNC_ROOT, player_id=player_id).sync(
            with_shots=with_shots,
            force_refresh_auth=False,
        )
    finally:
        _SYNC_LOCK.release()
    detail = result.detail
    if result.state == "reauth_required":
        response.status_code = 409
        detail = "Garmin session missing or expired for this player. Re-bind your Garmin, then sync again."
    elif result.state == "error":
        response.status_code = 500
    elif result.state == "ready":
        # New scorecards landed in the player's partition -> invalidate the stats cache so
        # the player's next history/stats read recomputes (mirrors round_ingest._invalidate_cache).
        stats_cache.clear()
    return SyncRunResponse(
        schema="ai-caddie-sync-run-v2",
        connector=result.connector,
        state=result.state,
        detail=sanitize_error(detail),
        reauthRequired=result.state == "reauth_required",
        errorCode=result.error_code,
        snapshot=snapshot_to_payload(result.snapshot) if result.snapshot else None,
        safeMeta=sanitize_safe_meta(result.safe_meta),
    )
