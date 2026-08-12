from __future__ import annotations

import contextlib
import hmac
import os
import threading
from typing import Annotated, Literal

from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException, Path, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.datastructures import QueryParams

from ai_caddie.courses import course_search
from ai_caddie.history import stats_cache
from ai_caddie.rounds import round_corrections, round_ingest
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
    admin_request_disposition,
    admin_router,
    assert_admin_security_config,
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
    ClubBagManualRequest,
    EffectiveClubBagResponse,
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
    RoundCorrectionRequest,
    RoundCorrectionResponse,
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
    # Fail fast (require-admin profile with no admin token) / warn loudly (open-dev owner-grant active)
    # before serving any request — the per-request path already fail-closes, this makes it audible at boot.
    assert_admin_security_config()
    warm_stats_cache_in_background()
    # 「打开即用」:启动即在后台准备 owner 最近一盘(预热其 topo,失败 swallow)。
    threading.Thread(target=_prepare_recent_bg, args=(OWNER_ID,), name="prepare-recent-boot", daemon=True).start()
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
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["*"],
)


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


def enforce_admin_or_owner(request: Request) -> None:
    """Authorize a genuinely-admin request, raising HTTPException unless allowed.

    (2) Beyond the literal admin token, an OWNER Apple session (a bearer that resolves to OWNER_ID)
    now authorizes /admin/*, the sync trigger, and the rest of the admin surface — so the owner can
    drive them from the iOS app without the homeserver admin token. A resolved MEMBER is rejected
    403 (authenticated, not the owner); an unresolved request keeps the literal admin-token semantics
    (401 configured-but-missing/mismatched, 503 fail-closed under a private/staging/production
    profile, allow under open-dev). The literal admin token stays the always-on DEBUG/CI/homeserver
    fallback. Used by BOTH the global gate and the in-handler admin checks so they agree."""
    disposition = admin_request_disposition(request)
    if disposition == "allow":
        return
    if disposition == "forbid":
        raise HTTPException(status_code=403, detail="owner access required")
    require_admin_token(request.headers.get("x-ai-caddie-admin-token"))


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
        # A valid per-player token grants access to player-scoped routes (history, evidence
        # writes, mobile aggregators). For genuinely-admin routes, enforce_admin_or_owner accepts
        # the literal admin token (or open-dev) OR an OWNER Apple session, rejects a MEMBER 403,
        # and otherwise preserves the require_admin_token 401/503 fail-closed semantics.
        player_token_allows = is_player_scoped_route(
            request.method, request.url.path
        ) and has_valid_player_token(request)
        if not player_token_allows:
            try:
                enforce_admin_or_owner(request)
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
            "courseHoleTopoPng": "/api/v2/courses/{global_id}/holes/{hole}/topo.png",
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
    # 「打开即用」:手动记分落地,后台准备这名玩家的最近一盘(预热其 topo)。
    threading.Thread(target=_prepare_recent_bg, args=(target_player_id,), name="prepare-recent-ingest", daemon=True).start()
    return RoundIngestResponse(**summary)


@app.get("/api/v2/history/rounds", response_model=HistoryRoundsResponse)
def history_rounds(
    year: str | None = Query(default=None),
    course: str | None = Query(default=None),
    hasShots: bool | None = Query(default=None),
    hasReport: bool | None = Query(default=None),
    period: str | None = Query(default=None, pattern=r"^(\d{4}|\d{4}-Q[1-4]|\d{4}-\d{2}|\d{4}-\d{2}-\d{2})$"),
    scoreBand: str | None = Query(default=None, pattern=r"^(70s|80s|90s|100\+)$"),
    search: str | None = Query(default=None, max_length=120),
    limit: int = Query(default=120, ge=1, le=2000),
    player_id: str = Depends(current_player_id),
) -> HistoryRoundsResponse:
    return load_history_rounds_response(
        year=year,
        course=course,
        has_shots=hasShots,
        has_report=hasReport,
        period=period,
        score_band=scoreBand,
        search=search,
        limit=limit,
        player_id=player_id,
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


@app.post(
    "/api/v2/history/rounds/{round_ref}/corrections",
    response_model=RoundCorrectionResponse,
    status_code=201,
)
def add_round_correction(
    round_ref: str,
    body: RoundCorrectionRequest,
    player_id: str = Depends(current_player_id),
) -> RoundCorrectionResponse:
    """复盘修改:给某局追加一条「增/改/删一杆 或 手填罚杆」事件,写在**本人名下**
    (幂等 on clientMutationId)。原始 Garmin 数据不动,读取 shotmap 时套上。一个成员
    token 只能写自己的修改;此路由不在 admin 门内,成员登录即可用。"""
    try:
        stored = round_corrections.append_correction(player_id, round_ref, body.model_dump())
    except round_corrections.CorrectionError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return RoundCorrectionResponse(stored=stored)


@app.get("/api/v2/history/stats", response_model=HistoryStatsResponse)
def history_stats(
    window: str = Query("all", pattern="^(all|12m|last20|last10)$"),
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
    window: str = Query("all", pattern="^(all|12m|last20|last10)$"),
    player_id: str = Depends(current_player_id),
) -> MobileStatsResponse:
    # Compact 统计 payload for the phone: the deep / periodic / per-course / per-club slices of the
    # full build, without the ~11MB per-hole table — sliced from the same cached stats (cache hit).
    # window (all|12m|last20|last10) mirrors /history/stats so the 统计 view keeps windowed KPIs.
    return load_mobile_stats_response(window=window, player_id=player_id)


@app.get("/api/v2/history/clubs/bag", response_model=ClubBagResponse)
def history_clubs_bag(
    player_id: str = Depends(current_player_id),
) -> ClubBagResponse:
    # The player's real Garmin bag (clubTypeId + custom name + retired/deleted), pulled by the sync
    # from Garmin's /club/player + /club/types. Owner-scoped; names resolve to Chinese on-device.
    from ai_caddie.caddie.club_bag import build_club_bag_response

    return ClubBagResponse(**build_club_bag_response(player_id=player_id, owner_id=OWNER_ID))


@app.get("/api/v2/players/{player_id}/clubs/bag", response_model=EffectiveClubBagResponse)
def player_clubs_bag(player_id: str, acting_player_id: str = Depends(current_player_id)) -> EffectiveClubBagResponse:
    """The player's EFFECTIVE club bag (manual selection wins, else the synced Garmin bag, else
    empty). A per-player bearer may read only its own bag; the owner (admin token) may read any —
    mirrors POST /api/v2/players/{id}/rounds."""
    if acting_player_id != OWNER_ID and acting_player_id != player_id:
        raise HTTPException(status_code=403, detail="cannot read another player's club bag")
    from .club_bag_api import build_effective_club_bag_response

    return EffectiveClubBagResponse(**build_effective_club_bag_response(player_id))


@app.put("/api/v2/players/{player_id}/clubs/bag", response_model=EffectiveClubBagResponse)
def put_player_clubs_bag(player_id: str, body: ClubBagManualRequest,
                         acting_player_id: str = Depends(current_player_id)) -> EffectiveClubBagResponse:
    """Set (or, with an empty list, clear) the player's MANUAL club bag. A per-player bearer may
    write only its own bag; the owner may write any. Unknown token / out-of-range distance -> 422."""
    if acting_player_id != OWNER_ID and acting_player_id != player_id:
        raise HTTPException(status_code=403, detail="cannot edit another player's club bag")
    from .club_bag_api import save_manual_club_bag_response
    from ai_caddie.caddie.club_bag import InvalidClubError

    try:
        payload = save_manual_club_bag_response(player_id, body)
    except InvalidClubError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    from ai_caddie.history import stats_cache
    from ai_caddie.courses import prep_cache

    # The manual bag changed the player's effective club ladder, which feeds both the history stats
    # caddie ladder AND the cached /api/v2/courses/{id}/prep response. prep_cache's fingerprint stats
    # the synced club_bag.json but NOT club_bag_manual.json, so without an explicit drop a prior prep
    # entry would keep serving the OLD ladder until an unrelated sync/geometry change. clear() is the
    # whole process cache (rare write, read-heavy endpoint), the simplest sound invalidation.
    stats_cache.clear(player_id)
    prep_cache.clear()
    return EffectiveClubBagResponse(**payload)


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


# Immutable topo bitmaps are content-addressed by (gid, hole, style-version): a course/hole's
# geometry is fixed, so the rendered PNG never changes for a given STYLE_VERSION. Cache hard.
_TOPO_CACHE_CONTROL = "public, max-age=31536000, immutable"


@app.get("/api/v2/courses/{global_id}/holes/{hole}/topo.png")
def course_hole_topo_png(global_id: int, hole: int = Path(ge=1, le=36)) -> Response:
    """The LOCKED realistic-topo base bitmap for a course hole (design-system §九), the base
    <img> layer the web/mobile hole canvases draw their vector overlays over.

    Public course knowledge (no player data, no source_ref) — like /courses/{id}/prep. Rendered
    once (~seconds) then served from an on-disk cache keyed by gid/hole/style-version; later hits
    return the cached bytes with a long immutable cache header. A hole without decoded CourseView
    geometry (most real/mock rounds) 404s so the client falls back to its placeholder — it never
    blocks or 500s."""
    from ai_caddie.geometry import topo_render

    try:
        png = topo_render.render_hole_topo_cached(global_id, hole)
    except topo_render.TopoGeometryUnavailable:
        raise HTTPException(status_code=404, detail="no topo geometry for this hole")
    except topo_render.TopoRenderError:
        # A malformed mesh must degrade to the client placeholder, never crash the worker.
        raise HTTPException(status_code=404, detail="topo render unavailable for this hole")
    return Response(
        content=png,
        media_type="image/png",
        headers={
            "Cache-Control": _TOPO_CACHE_CONTROL,
            "ETag": f'"{topo_render.STYLE_VERSION}-{int(global_id)}-{int(hole)}"',
        },
    )


def _prewarm_course_topo(global_id: int, holes: list[int]) -> None:
    """Render + cache every hole's topo bitmap in the background so a later browse hits a warm
    cache (each first render is ~seconds). Sequential + best-effort: a hole with no/broken
    geometry is skipped, never crashing the worker; an already-cached hole returns instantly."""
    from ai_caddie.geometry import topo_render

    for hole in holes:
        try:
            topo_render.render_hole_topo_cached(global_id, hole)
        except Exception:
            # TopoGeometryUnavailable / TopoRenderError / any transient render fault: skip this hole.
            continue


@app.post("/api/v2/courses/{global_id}/topo/prewarm")
def course_topo_prewarm(global_id: int, background_tasks: BackgroundTasks) -> dict:
    """Kick a FIRE-AND-FORGET background render of every geometry-backed hole's topo bitmap so the
    web/mobile client can browse holes against a warm cache instead of paying ~6–10s on each hole's
    first view. Returns immediately with the queued hole list (never blocks on rendering). Public
    course knowledge like /topo.png + /prep. A course with NO decoded geometry queues nothing and
    still 200s (queued: 0) — it never errors on a geometry-less gid."""
    from ai_caddie.core.data import available_prep_holes, mesh_path

    # available_prep_holes falls back to [1..9] with no cached geometry; filter to holes that
    # actually have a mesh so a geometry-less course enqueues nothing (and never spins on 404s).
    holes = [hole for hole in available_prep_holes(global_id) if mesh_path(global_id, hole).exists()]
    if holes:
        background_tasks.add_task(_prewarm_course_topo, global_id, holes)
    return {
        "schema": "ai-caddie-topo-prewarm-v1",
        "globalId": int(global_id),
        "holes": holes,
        "queued": len(holes),
    }


def _prepare_recent_bg(player_id: str) -> None:
    """「打开即用」后台准备最近一盘:预热其球洞图 topo + 烤统计。best-effort,绝不抛
    (镜像 warm_stats_cache 的 swallow 语义,不弄崩触发它的响应/线程)。"""
    from ai_caddie.history.history import load_history_data
    from ai_caddie.rounds.prepare_recent import prepare_recent_round
    from server_v2.history_stats import warm_stats_cache

    def _ensure_geometry(gid: int, holes: list[int]) -> None:
        # On-demand: fetch + decode any MISSING course geometry from Garmin CourseView, so a course we
        # haven't decoded yet (a newly played one) fills in on the next sync/prewarm — its 复盘落点图
        # then has real geometry. best-effort: a 404 (course pulled from Garmin) or a decode hiccup
        # just leaves that hole empty, never crashes the background thread.
        from ai_caddie.geometry.geometry_sync import ensure_prodgeometry, geometry_present

        for hole in holes:
            if geometry_present(int(gid), int(hole)):
                continue
            try:
                ensure_prodgeometry(int(gid), int(hole))
            except Exception:  # noqa: BLE001
                pass

    try:
        data = load_history_data(player_id=player_id)
        prepare_recent_round(
            data, prewarm=_prewarm_course_topo, warm_stats=warm_stats_cache,
            ensure_geometry=_ensure_geometry,
        )
    except Exception:  # noqa: BLE001 - best-effort;绝不弄崩触发它的线程
        import logging

        logging.getLogger(__name__).exception("prepare-recent failed for %s", player_id)


@app.post("/api/v2/history/prepare-recent")
def history_prepare_recent(
    background_tasks: BackgroundTasks, player_id: str = Depends(current_player_id)
) -> dict:
    """「打开即用」触发器:fire-and-forget 后台准备调用者的最近一盘(预热球洞图 topo + 烤统计),
    立即返回。定时同步尾巴 + 未来「拉一下最新」按钮都打这个。写调用者自己缓存,member 可用。"""
    background_tasks.add_task(_prepare_recent_bg, player_id)
    return {"schema": "ai-caddie-prepare-recent-v1", "queued": True}


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
    end positions) are PLAYER data, sourced per ``player_id``: the owner gets their
    history-derived ladder + scatter; a member gets a ladder blended from their OWN logged
    shots (measured medians) + manual bag, and scatter from their OWN rounds only. No player's
    distances or shots ever leak to another (effective_club_ladder + the player-scoped loaders
    read solely the threaded player's tree)."""
    from ai_caddie.courses import course_prep, prep_cache

    requested = holes or course_prep.available_prep_holes(global_id)

    # prep_nine rebuilds all-hole mesh geometry (~19s for a 9-hole course) on every request; cache the
    # response by filesystem fingerprint so 备战 opens instantly until geometry / shots / clubs change.
    def _build() -> dict:
        # Each player reads their OWN model: the owner's history-derived ladder, or a member's
        # ladder blended from their own logged shots + manual bag — no player's distances leak to
        # another (effective_club_ladder + the player-scoped loaders are isolated per player_id).
        ladder = course_prep.effective_club_ladder(player_id)
        # Shot scatter is the player's OWN past end positions only: prep_nine reads solely the
        # threaded player_id's tree, so a member sees their own shots and never the owner's.
        nine = course_prep.prep_nine(global_id, requested, ladder=ladder, render=render, include_missing=True,
                                     include_shots=include_shots, player_id=player_id)
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


@app.get("/api/v2/courses/{global_id}/tees")
def course_tees(global_id: int) -> dict:
    """The course's selectable tee boxes (colour + total yards + which is default) for the pre-round
    tee picker — the same list Garmin's 'new round' shows. Pure course knowledge (no player data, no
    source_ref), public exactly like /topo.png + /geometry/hole/{}/coverage: colour names from the
    CourseView release, total yards summed from per-hole tee→target geometry (null when a tee has no
    geometry — never faked), default = blue when the course has it else the longest tee. A course with
    neither CourseView names nor geometry degrades to generic 长/中/短 tiers."""
    from ai_caddie.caddie.analysis import course_tee_options

    options = course_tee_options(int(global_id))
    return {
        "schema": "ai-caddie-course-tees-v1",
        "globalId": int(global_id),
        "defaultTeeBox": options["defaultTeeBox"],
        "tees": options["tees"],
    }


@app.post("/api/v2/geometry/hole/{global_id}/{local_hole}/ensure", response_model=GeometryEnsureResponse)
def geometry_hole_ensure(
    request: Request,
    global_id: int,
    local_hole: int,
    profile_id: str | None = None,
    force: bool = False,
) -> GeometryEnsureResponse:
    enforce_admin_or_owner(request)
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
    player_id: str = Depends(current_player_id),
) -> CaddieDecisionResponse:
    # Member-scoped (gate: player-scoped + a per-player/owner token): the decision lands in the
    # caller's evidence partition; the owner (admin token / owner session) stays flat.
    return build_caddie_decision_response(request, player_id=player_id)


@app.post("/api/v2/caddie/decisions/{decision_id}/audit", response_model=CaddieDecisionAuditStoreResponse)
def caddie_decision_audit(
    decision_id: str,
    request: CaddieDecisionAuditRequest,
    player_id: str = Depends(current_player_id),
) -> CaddieDecisionAuditStoreResponse:
    # Member-scoped: the audit (and the re-read of the stored decision) is partitioned to the caller.
    return create_decision_audit_response(decision_id, request, player_id=player_id)


@app.get("/api/v2/caddie/decisions/{decision_id}/audit/latest", response_model=CaddieDecisionAuditLatestResponse)
def caddie_decision_audit_latest(
    http_request: Request,
    decision_id: str,
) -> CaddieDecisionAuditLatestResponse:
    # Admin-only read of the owner's stored audit; an OWNER session authorizes it, a member is 403.
    enforce_admin_or_owner(http_request)
    return latest_decision_audit_response(decision_id)


@app.get("/api/v2/annotations", response_model=AnnotationListResponse)
def annotations(player_id: str = Depends(current_player_id)) -> AnnotationListResponse:
    # Member-scoped read: a member lists ONLY their own annotations; the owner reads the flat store.
    return list_annotation_response(player_id=player_id)


@app.post("/api/v2/annotations", response_model=AnnotationCreateResponse)
def create_annotation(
    request: AnnotationCreateRequest,
    player_id: str = Depends(current_player_id),
) -> AnnotationCreateResponse:
    # Member-scoped: the annotation lands in the caller's evidence partition; the owner stays flat.
    return create_annotation_response(request, player_id=player_id)


@app.get("/api/v2/annotations/target/{target_type}/{target_id}", response_model=AnnotationListResponse)
def annotations_by_target(
    target_type: AnnotationTargetType, target_id: str, player_id: str = Depends(current_player_id)
) -> AnnotationListResponse:
    # Member-scoped read: a member sees ONLY their own annotations for this target; the owner stays flat.
    return list_target_annotation_response(target_type, target_id, player_id=player_id)


@app.post("/api/v2/media", response_model=MediaCreateResponse)
def create_media(
    request: MediaCreateRequest,
    player_id: str = Depends(current_player_id),
) -> MediaCreateResponse:
    return create_media_response(request, player_id=player_id)


@app.get("/api/v2/media/target/{target_type}/{target_id}", response_model=MediaListResponse)
def media_by_target(
    target_type: MediaTargetType, target_id: str, player_id: str = Depends(current_player_id)
) -> MediaListResponse:
    return list_target_media_response(target_type, target_id, player_id=player_id)


@app.get("/api/v2/media/target/{target_type}/{target_id}/findings", response_model=VisionFindingsListResponse)
def vision_findings_by_target(
    target_type: MediaTargetType, target_id: str, player_id: str = Depends(current_player_id)
) -> VisionFindingsListResponse:
    return list_target_vision_findings_response(target_type, target_id, player_id=player_id)


@app.post("/api/v2/media/{media_id}/analyze", response_model=VisionAnalysisResponse)
def analyze_media(
    media_id: str,
    player_id: str = Depends(current_player_id),
) -> VisionAnalysisResponse:
    return analyze_media_response(media_id, player_id=player_id)


@app.post("/api/v2/media/{media_id}/redact", response_model=MediaRedactResponse)
def redact_media(
    media_id: str,
    player_id: str = Depends(current_player_id),
) -> MediaRedactResponse:
    return redact_media_response(media_id, player_id=player_id)


@app.post("/api/v2/media/findings/{finding_id}/confirmation", response_model=VisionFindingConfirmationResponse)
def confirm_vision_finding_route(
    finding_id: str,
    request: VisionFindingConfirmationRequest,
    player_id: str = Depends(current_player_id),
) -> VisionFindingConfirmationResponse:
    return confirm_vision_finding_response(finding_id, request, player_id=player_id)


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
    acting_player_id: str = Depends(current_player_id),
) -> LiveRoundEventBatchResponse:
    # Auth = the global middleware (admin OR a valid per-player token for this player-scoped route).
    # Events write to the ACTING player's OWN partition (mobile_event_log(player_id)) — owner unchanged.
    return append_mobile_events_response(
        round_id, request, idempotency_key=idempotency_key, player_id=acting_player_id
    )


@app.get("/api/v2/mobile/rounds/{round_id}/events/replay", response_model=LiveRoundEventReplayResponse)
def mobile_round_events_replay(
    round_id: str,
    client_id: str | None = None,
    after_sequence: int | None = None,
    limit: int = 100,
    acting_player_id: str = Depends(current_player_id),
) -> LiveRoundEventReplayResponse:
    return replay_mobile_events_response(
        round_id,
        client_id=client_id,
        after_sequence=after_sequence,
        limit=limit,
        player_id=acting_player_id,
    )


@app.post("/api/v2/mobile/rounds/{round_id}/events/ack", response_model=LiveRoundEventAckResponse)
def mobile_round_events_ack(
    round_id: str,
    request: LiveRoundEventAckRequest,
    acting_player_id: str = Depends(current_player_id),
) -> LiveRoundEventAckResponse:
    return ack_mobile_events_response(round_id, request, player_id=acting_player_id)


@app.get("/api/v2/mobile/rounds/{round_id}/state", response_model=RoundStateResponse)
def mobile_round_state(
    round_id: str,
    acting_player_id: str = Depends(current_player_id),
) -> RoundStateResponse:
    # round-12 sync spine: authoritative server-projected round state (folded from the event log),
    # per-player partitioned — a member sees only their OWN round's state (owner unchanged).
    return round_state_response(round_id, player_id=acting_player_id)


@app.get("/api/v2/mobile/rounds/{round_id}/reconciliation", response_model=MobileReconciliationResponse)
def mobile_round_reconciliation(
    round_id: str,
    player_id: str = Depends(current_player_id),
) -> MobileReconciliationResponse:
    return reconcile_mobile_round_response(round_id, player_id=player_id)


@app.post("/api/v2/mobile/rounds/{round_id}/reconciliation/apply", response_model=MobileReconciliationApplyResponse)
def mobile_round_reconciliation_apply(
    http_request: Request,
    round_id: str,
    request: MobileReconciliationApplyRequest,
) -> MobileReconciliationApplyResponse:
    # Admin-only (mutates the owner's shared round reconciliation); an OWNER session authorizes it.
    enforce_admin_or_owner(http_request)
    return apply_mobile_round_reconciliation_response(round_id, request)


@app.get("/api/v2/weather/snapshot", response_model=WeatherSnapshotResponse)
def weather_snapshot(
    request: Request,
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
    # persist=true WRITES the snapshot to the caller's evidence partition (member → their tree, owner
    # → flat). The global gate already requires a token for persist=true, so current_player_id
    # resolves here. A non-persist read stays public (no token, owner-scoped, no write).
    player_id = current_player_id(request) if persist else OWNER_ID
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
        player_id=player_id,
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
def generate_round_report(round_id: str, player_id: str = Depends(current_player_id)) -> ReviewReportResponse:
    # Member-scoped: a member generates a report from THEIR history into THEIR partition; owner flat.
    return generate_round_report_response(round_id, player_id=player_id)


@app.get("/api/v2/reports/course/{course_key}", response_model=ReviewReportResponse)
def course_report(course_key: str, player_id: str = Depends(current_player_id)) -> ReviewReportResponse:
    return load_course_report_response(course_key, player_id=player_id)


@app.post("/api/v2/reports/course/{course_key}/generate", response_model=ReviewReportResponse)
def generate_course_report(course_key: str, player_id: str = Depends(current_player_id)) -> ReviewReportResponse:
    return generate_course_report_response(course_key, player_id=player_id)


@app.get("/api/v2/reports/hole/{course_key}/{hole}", response_model=ReviewReportResponse)
def hole_report(
    course_key: str, hole: int, player_id: str = Depends(current_player_id)
) -> ReviewReportResponse:
    return load_hole_report_response(course_key, hole, player_id=player_id)


@app.post("/api/v2/reports/hole/{course_key}/{hole}/generate", response_model=ReviewReportResponse)
def generate_hole_report(course_key: str, hole: int, player_id: str = Depends(current_player_id)) -> ReviewReportResponse:
    return generate_hole_report_response(course_key, hole, player_id=player_id)


@app.get("/api/v2/reports/club/{club_name}", response_model=ReviewReportResponse)
def club_report(club_name: str, player_id: str = Depends(current_player_id)) -> ReviewReportResponse:
    return load_club_report_response(club_name, player_id=player_id)


@app.post("/api/v2/reports/club/{club_name}/generate", response_model=ReviewReportResponse)
def generate_club_report(club_name: str, player_id: str = Depends(current_player_id)) -> ReviewReportResponse:
    return generate_club_report_response(club_name, player_id=player_id)


@app.get("/api/v2/reports/trend/{period}", response_model=ReviewReportResponse)
def trend_report(period: str, player_id: str = Depends(current_player_id)) -> ReviewReportResponse:
    return load_trend_report_response(period, player_id=player_id)


@app.post("/api/v2/reports/trend/{period}/generate", response_model=ReviewReportResponse)
def generate_trend_report(period: str, player_id: str = Depends(current_player_id)) -> ReviewReportResponse:
    return generate_trend_report_response(period, player_id=player_id)


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
    http_request: Request,
    response: Response,
    with_shots: bool = True,
    force_refresh_auth: bool = False,
    ensure_geometry: bool = False,
) -> SyncRunResponse:
    # Owner-only sync of the flat owner tree; an OWNER Apple session authorizes it (a member uses
    # the per-member /api/v2/players/{id}/sync/garmin route instead, and is 403 here).
    enforce_admin_or_owner(http_request)
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
        # 「打开即用」:Garmin 新数据落地,后台顺带准备 owner 最近一盘(预热其 topo)。
        threading.Thread(target=_prepare_recent_bg, args=(OWNER_ID,), name="prepare-recent-sync", daemon=True).start()
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
    http_request: Request,
    request: GarminSessionImportRequest,
) -> GarminSessionImportResponse:
    # Owner-only (binds the owner's flat Garmin cookie); an OWNER Apple session authorizes it.
    enforce_admin_or_owner(http_request)
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
        # New scorecards landed in the player's partition -> invalidate ONLY that player's
        # stats cache so their next history/stats read recomputes, without evicting other
        # players' caches (mirrors round_ingest._invalidate_cache, but player-scoped).
        stats_cache.clear(player_id)
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
