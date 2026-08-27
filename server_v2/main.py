from __future__ import annotations

import contextlib
import hashlib
import hmac
import logging
import os
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Annotated, Literal

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
from . import course_install
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
    finish_mobile_round_response,
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
    CourseInstallStatusResponse,
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
    MobileRoundFinishRequest,
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
    threading.Thread(
        target=course_install.resume_pending_jobs,
        name="course-install-resume",
        daemon=True,
    ).start()
    # 「打开即用」:启动即在后台准备 owner 最近一盘(预热其 topo,失败 swallow)。
    threading.Thread(target=_prepare_recent_bg, args=(OWNER_ID,), name="prepare-recent-boot", daemon=True).start()
    yield


app = FastAPI(title="AI Caddie v2", version="0.1.0", lifespan=_lifespan)
if os.getenv("AI_CADDIE_FIXTURE_MODE") == "1":
    # Fixture routes are absent from production processes; this prevents a fixture response from
    # shadowing the real loaders when the environment is not explicitly opted in.
    from .ci_fixture import ROUTE as ci_fixture_router

    app.include_router(ci_fixture_router)

    @app.middleware("http")
    async def reject_unimplemented_fixture_routes(request: Request, call_next):
        path = request.url.path
        allowed = {
            "/api/v2/health", "/api/v2/readiness", "/api/v2/history/rounds",
            "/api/v2/history/overview", "/api/v2/history/stats/mobile",
            "/api/v2/sync/status",
            "/api/v2/courses/search", "/api/v2/courses/nearby",
            "/api/v2/mobile/courses/options", "/api/v2/caddie/context",
        }
        parameterized = (
            r"/api/v2/history/rounds/[^/]+",
            r"/api/v2/history/rounds/[^/]+/holes/[0-9]+/shotmap",
            r"/api/v2/courses/[0-9]+/(?:prep|tees|install/status)",
            r"/api/v2/geometry/course/[0-9]+/coverage",
            r"/api/v2/geometry/hole/[0-9]+/[0-9]+",
            r"/api/v2/mobile/courses/[0-9]+/package",
            r"/api/v2/mobile/rounds/[^/]+/package",
            r"/api/v2/media/target/[^/]+/[^/]+",
            r"/api/v2/reports/round/[^/]+",
        )
        if path.startswith("/api/v2/") and path not in allowed and not any(re.fullmatch(pattern, path) for pattern in parameterized):
            return JSONResponse(status_code=404, content={"detail": "fixture route not implemented"})
        return await call_next(request)
app.include_router(admin_router)
app.include_router(auth_router)

logger = logging.getLogger(__name__)


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
            or (path.startswith("/api/v2/courses/") and path.endswith("/install/status"))
            or (path.startswith("/api/v2/courses/") and path.endswith("/prep"))
            or (path.startswith("/api/v2/courses/") and path.endswith("/prep-tips"))
            or (
                path.startswith("/api/v2/courses/")
                and path.endswith("/tees")
                and _truthy_query_flag(query_params.get("ensure_release"))
            )
            or path == "/api/v2/courses/search"
            or path == "/api/v2/courses/nearby"
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
        ("/api/v2/mobile/rounds/", "/finish"),
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
            "courseInstallStatus": "/api/v2/courses/{global_id}/install/status",
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
        "revision": os.getenv("AI_CADDIE_BUILD_REVISION", "unknown").strip() or "unknown",
    }


@app.get("/api/v2/readiness")
def readiness(request: Request) -> dict[str, object]:
    # Owner operational evidence (round ids/counts/sync errors) + a heavy per-call
    # owner-package build are owner-only. A non-owner caller — anonymous OR a resolved
    # family member (Phase 1b made members resolve) — gets liveness only: both a data-leak
    # fix and a no-auth DoS-amplifier fix. (Liveness lives at GET /api/v2/health.)
    if resolve_request_player(request) != OWNER_ID:
        return {
            "schema": "ai-caddie-readiness-v1",
            "status": "ok",
            "authenticated": False,
            # Keep liveness independent from owner-only packaging evidence.
            # ``status=ok`` is retained for legacy clients; the split fields are
            # consumed by newer probes.
            "runtimeStatus": "unknown",
            "serviceStatus": "ready",
            "evidenceStatus": "unknown",
            "reason": "packaging evidence is owner-only",
            "checks": [],
        }
    payload = build_readiness_response()
    payload["authenticated"] = True
    payload["evidenceStatus"] = payload.get("status", "unknown")
    return payload


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
    round_ref: str,
    hole: int,
    include_image: bool = Query(default=True, alias="includeImage"),
    player_id: str = Depends(current_player_id),
) -> RoundHoleShotMapResponse:
    # 复盘 per-hole shot map: actual shots + projection overlay. Native prefetches all 18 without
    # embedding the PNG; the revision-bound /topo.png endpoint owns bitmap transfer and caching.
    return load_round_hole_shot_map_response(
        round_ref,
        hole,
        player_id=player_id,
        include_image=include_image,
    )


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


# An unpinned route must revalidate because Garmin can publish new geometry for the same gid/hole.
# A caller that pins both geometry revision and renderer version names immutable bytes and can skip
# the home-server round trip entirely after the first download.
_TOPO_CACHE_CONTROL = "public, no-cache"
_IMMUTABLE_TOPO_CACHE_CONTROL = "public, max-age=31536000, immutable"


@app.get("/api/v2/courses/{global_id}/holes/{hole}/topo.png")
def course_hole_topo_png(
    request: Request,
    global_id: int,
    hole: int = Path(ge=1, le=36),
    v: str | None = Query(default=None, max_length=32),
    r: str | None = Query(default=None, max_length=128),
) -> Response:
    """The LOCKED realistic-topo base bitmap for a course hole (design-system §九), the base
    <img> layer the web/mobile hole canvases draw their vector overlays over.

    Public course knowledge (no player data, no source_ref) — like /courses/{id}/prep. Rendered
    once (~seconds) then served from an on-disk cache keyed by gid/hole/style/geometry authority;
    later hits revalidate by ETag. A hole without decoded CourseView geometry (most real/mock
    rounds) 404s so the client falls back to its placeholder — it never blocks or 500s."""
    from ai_caddie.geometry import topo_render
    from ai_caddie.geometry.geometry_evidence import geometry_coverage_for_hole

    if v is not None and v != topo_render.STYLE_VERSION:
        raise HTTPException(status_code=409, detail="topo renderer version changed")

    # Do not combine a freshly refreshed course package with pixels decoded from an older
    # Garmin release.  The lightweight vector remains playable while the normal background
    # geometry upgrade validates or replaces the precise asset.
    geometry_evidence = geometry_coverage_for_hole(
        global_id,
        hole,
        require_current_authority=True,
        refresh_release=True,
    )
    if geometry_evidence.get("coverage") != "ready":
        raise HTTPException(status_code=404, detail="current topo geometry is still preparing")
    # A package/prep revision and its bitmap are one atomic fact. If Garmin changes between those
    # two requests, never return new pixels under the caller's old revision URL—the mobile cache
    # would otherwise persist a projection mismatch with a perfectly plausible filename.
    requested_revision = str(r or "").strip().lower()
    current_revision = str(geometry_evidence.get("geometryRevision") or "").strip().lower()
    if requested_revision and requested_revision != current_revision:
        raise HTTPException(status_code=409, detail="topo geometry revision changed; refresh course facts")

    identity = topo_render.cache_identity(global_id, hole)
    etag = f'"{identity}-{int(global_id)}-{int(hole)}"'
    immutable_request = bool(requested_revision) and v == topo_render.STYLE_VERSION
    headers = {
        "Cache-Control": (
            _IMMUTABLE_TOPO_CACHE_CONTROL if immutable_request else _TOPO_CACHE_CONTROL
        ),
        "ETag": etag,
    }
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers=headers)
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
        headers=headers,
    )


@app.get("/api/v2/courses/{global_id}/holes/{hole}/green.png")
def course_hole_green_detail_png(
    request: Request,
    global_id: int,
    hole: int = Path(ge=1, le=36),
    x: float = Query(..., ge=-1000, le=10000),
    y: float = Query(..., ge=-1000, le=10000),
    width: float = Query(..., ge=20, le=1000),
    height: float = Query(..., ge=20, le=1000),
    size: int = Query(1280, ge=320, le=1280),
    v: str | None = Query(default=None, max_length=32),
    g: str | None = Query(default=None, max_length=32),
    r: str | None = Query(default=None, max_length=128),
) -> Response:
    """High-resolution View Green bitmap in the shared whole-hole pixel frame.

    The client supplies the crop it already computed from ``greenOutline``.  This keeps the image
    and the Watch's offline placement on exactly the same affine frame, while the server re-renders
    the decoded geometry into that small window instead of magnifying a few pixels from ``topo.png``.
    It is public course imagery and follows the same current-authority/revision gate as ``topo.png``.
    """
    from ai_caddie.geometry import topo_render
    from ai_caddie.geometry.geometry_evidence import geometry_coverage_for_hole

    # ``g`` is a URL/cache-busting contract for installed clients.  Older apps omitted it and are
    # still allowed to receive the current renderer; a newer app naming an unknown style must not
    # cache today's pixels under a future contract it assumes the server already understands.
    if v is not None and v != topo_render.STYLE_VERSION:
        raise HTTPException(status_code=409, detail="topo renderer version changed")
    if g is not None and g != topo_render.GREEN_DETAIL_STYLE_VERSION:
        raise HTTPException(status_code=409, detail="green detail renderer version changed")

    geometry_evidence = geometry_coverage_for_hole(
        global_id,
        hole,
        require_current_authority=True,
        refresh_release=True,
    )
    if geometry_evidence.get("coverage") != "ready":
        raise HTTPException(status_code=404, detail="current topo geometry is still preparing")
    requested_revision = str(r or "").strip().lower()
    current_revision = str(geometry_evidence.get("geometryRevision") or "").strip().lower()
    if requested_revision and requested_revision != current_revision:
        raise HTTPException(status_code=409, detail="topo geometry revision changed; refresh course facts")

    try:
        crop = topo_render._validated_green_detail_crop((x, y, width, height))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    identity = topo_render.cache_identity(global_id, hole)
    crop_key = hashlib.sha256(
        (repr(crop) + f"|{int(size)}|{topo_render.GREEN_DETAIL_STYLE_VERSION}").encode("ascii")
    ).hexdigest()[:20]
    etag = f'"{identity}-green-{crop_key}"'
    immutable_request = (
        bool(requested_revision)
        and v == topo_render.STYLE_VERSION
        and g == topo_render.GREEN_DETAIL_STYLE_VERSION
    )
    headers = {
        "Cache-Control": (
            _IMMUTABLE_TOPO_CACHE_CONTROL if immutable_request else _TOPO_CACHE_CONTROL
        ),
        "ETag": etag,
        "X-Green-Detail-Crop": ",".join(str(value) for value in crop),
    }
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers=headers)
    try:
        png = topo_render.render_hole_green_detail_cached(
            global_id,
            hole,
            crop,
            size=size,
        )
    except (topo_render.TopoGeometryUnavailable, topo_render.TopoRenderError):
        raise HTTPException(status_code=404, detail="green detail render unavailable for this hole")
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return Response(content=png, media_type="image/png", headers=headers)


def _prewarm_course_topo(global_id: int, holes: list[int]) -> None:
    """Render + cache every hole's topo bitmap in the background so a later browse hits a warm
    cache (each first render is ~seconds). Sequential + best-effort: a hole with no/broken
    geometry is skipped, never crashing the worker; an already-cached hole returns instantly."""
    from ai_caddie.geometry import topo_render

    def render_one(hole: int) -> None:
        try:
            topo_render.render_hole_topo_cached(global_id, hole)
        except Exception:
            # TopoGeometryUnavailable / TopoRenderError / any transient render fault: skip this hole.
            pass

    # Native-size renders peak at ~150 MB in production measurements. Two workers fit the shared
    # four-core server without starving metadata/search requests and cut an 18-hole cold course from
    # minutes to tens of seconds. ``render_hole_topo_cached`` still single-flights duplicate hits.
    from concurrent.futures import ThreadPoolExecutor

    with ThreadPoolExecutor(max_workers=min(2, max(1, len(holes)))) as executor:
        list(executor.map(render_one, holes))


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
        from ai_caddie.geometry.geometry_sync import ensure_prodgeometry

        for hole in holes:
            try:
                # ``ensure`` is cheap for a current authority-bound hole and performs
                # the bounded release check that notices Garmin course updates.
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
    render=false omits only the legacy embedded JPEG; factual route/projection data remains usable
    with the shared topo endpoint. include_shots=true additionally projects the player's past
    TEE/APPROACH end positions into the same overlay pixels (``yourShots``), with or without JPEGs.

    The club ladder (the player's real distances) and shot scatter (their real TEE/APPROACH
    end positions) are PLAYER data, sourced per ``player_id``: the owner gets their
    history-derived ladder + scatter; a member gets a ladder blended from their OWN logged
    shots (measured medians) + manual bag, and scatter from their OWN rounds only. No player's
    distances or shots ever leak to another (effective_club_ladder + the player-scoped loaders
    read solely the threaded player's tree)."""
    from ai_caddie.courses import course_prep, prep_cache
    from ai_caddie.courses.course_reference import courseview_release_info

    # `/prep` is also a direct product entry (Web 备战 and iOS/Watch per-hole refresh), not only a
    # follow-up to a mobile package. Refresh the small release document before the prep-cache
    # fingerprint and authority checks so this path cannot indefinitely bless an old Garmin map.
    try:
        courseview_release_info(global_id, allow_fetch=True)
    except Exception:
        # Provider failure keeps the last complete cached release/offline geometry usable.
        pass

    requested = holes or course_prep.available_prep_holes(global_id)

    # prep_nine rebuilds all-hole mesh geometry (~19s for a 9-hole course) on every request; cache the
    # response by filesystem fingerprint so 备战 opens instantly until geometry / shots / clubs change.
    def _build() -> dict:
        build_started = time.perf_counter()
        # Each player reads their OWN model: the owner's history-derived ladder, or a member's
        # ladder blended from their own logged shots + manual bag — no player's distances leak to
        # another (effective_club_ladder + the player-scoped loaders are isolated per player_id).
        ladder = course_prep.effective_club_ladder(player_id)
        club_rows = course_prep.club_ladder_with_provenance(player_id, ladder=ladder)
        # Shot scatter is the player's OWN past end positions only: prep_nine reads solely the
        # threaded player_id's tree, so a member sees their own shots and never the owner's.
        nine = course_prep.prep_nine(global_id, requested, ladder=ladder, render=render, include_missing=True,
                                     include_shots=include_shots, player_id=player_id)
        payload = {
            "schema": "ai-caddie-course-prep-v1",
            "globalId": int(global_id),
            "holeCount": len(nine),
            # The original name/m/yd fields remain unchanged.  Provenance is additive so older
            # iOS/Watch/Web clients can continue decoding the v1 response without a migration.
            "clubs": [
                {
                    "name": row["name"],
                    "token": row["token"],
                    "m": row["m"],
                    "yd": course_prep.yd(row["m"]),
                    "distanceSource": row["distanceSource"],
                    "sampleSize": row["sampleSize"],
                    "confidence": row["confidence"],
                }
                for row in club_rows
            ],
            "holes": nine,
        }
        logger.info(
            "course_install stage=prep gid=%s holes=%s render=%s duration_ms=%s",
            int(global_id),
            len(requested),
            bool(render),
            int((time.perf_counter() - build_started) * 1000),
        )
        return payload

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
    latitude: float | None = None,
    longitude: float | None = None,
) -> dict:
    """Search Garmin's course DB by name (+ optional city / hole-count guard); returns ranked
    matches with globalId. Feed a chosen globalId into /api/v2/courses/{global_id}/prep."""
    if (latitude is None) != (longitude is None):
        raise HTTPException(status_code=422, detail="latitude and longitude must be supplied together")
    try:
        matches = course_search.courseview_search(
            name,
            city=city,
            expected_holes=holes,
            latitude=latitude,
            longitude=longitude,
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail="Garmin course catalogue unavailable") from exc
    return {
        "schema": "ai-caddie-course-search-v1",
        "query": name,
        "matches": [
            {"globalId": m.global_id, "name": m.name, "holes": m.holes,
             "city": m.city, "province": m.province, "ratio": m.ratio,
             "latitude": m.latitude, "longitude": m.longitude,
             "distanceKm": m.distance_km}
            for m in matches
        ],
    }


def _course_match_payload(match: course_search.CourseMatch) -> dict:
    return {
        "globalId": match.global_id,
        "name": match.name,
        "holes": match.holes,
        "city": match.city,
        "province": match.province,
        "ratio": match.ratio,
        "latitude": match.latitude,
        "longitude": match.longitude,
        "distanceKm": match.distance_km,
    }


@app.get("/api/v2/courses/nearby")
def course_nearby_endpoint(
    latitude: float = Query(ge=-90, le=90),
    longitude: float = Query(ge=-180, le=180),
    radius_km: int = Query(default=50, ge=1, le=200),
) -> dict:
    """List provider-wide Garmin catalogue rows around a coordinate; metadata only."""
    try:
        nearby_result = course_search.courseview_nearby(
            latitude=latitude,
            longitude=longitude,
            radius_km=radius_km,
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail="Garmin course catalogue unavailable") from exc
    # Keep accepting a plain list from test/adaptor callers while the production
    # implementation carries explicit completeness/cache metadata.
    if isinstance(nearby_result, course_search.NearbyCourseResult):
        matches = nearby_result.matches
        complete = nearby_result.complete
        partial_reason = nearby_result.partial_reason
        pages_fetched = nearby_result.pages_fetched
        cache_status = nearby_result.cache_status
    else:
        matches = nearby_result
        complete = True
        partial_reason = None
        pages_fetched = 0
        cache_status = "adapter"
    return {
        "schema": "ai-caddie-course-nearby-v1",
        "radiusKm": radius_km,
        "complete": complete,
        "partialReason": partial_reason,
        "pagesFetched": pages_fetched,
        "cacheStatus": cache_status,
        "matches": [_course_match_payload(match) for match in matches],
    }


@app.get("/api/v2/courses/{global_id}/tees")
def course_tees(
    global_id: int,
    background_tasks: BackgroundTasks,
    ensure_release: bool = False,
) -> dict:
    """The course's selectable tee boxes (colour + total yards + which is default) for the pre-round
    tee picker — the same list Garmin's 'new round' shows. Pure course knowledge (no player data,
    no source_ref), public exactly like /topo.png + /geometry/hole/{}/coverage: colour names from the
    CourseView release, total yards summed from per-hole tee→target geometry (null when a tee has no
    geometry — never faked), default = blue when the course has it else the longest tee. A course with
    neither CourseView names nor geometry degrades to generic 长/中/短 tiers. ``ensure_release`` only
    fetches and caches the small CourseView release metadata; geometry is intentionally prepared later
    by the selected course-package request."""
    from ai_caddie.caddie.analysis import course_tee_options

    if ensure_release:
        from ai_caddie.courses.course_reference import courseview_tees

        # A valid cached release is already factual Tee authority. Return it immediately and refresh
        # an hourly-stale Garmin release after the response; blocking the picker on that refresh made
        # a known course take ~38 s and allowed the subsequent package request to time out in the
        # client's connection queue. The genuinely cold/no-cache path still fetches synchronously so
        # a never-seen course is not enabled with invented Tee data.
        cached_tees = courseview_tees(int(global_id), allow_fetch=False)
        if cached_tees:
            background_tasks.add_task(courseview_tees, int(global_id), allow_fetch=True)
        else:
            courseview_tees(int(global_id), allow_fetch=True)
    options = course_tee_options(int(global_id))
    response = {
        "schema": "ai-caddie-course-tees-v1",
        "globalId": int(global_id),
        "defaultTeeBox": options["defaultTeeBox"],
        "tees": options["tees"],
    }
    return response


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
    decision_id: str,
    player_id: str = Depends(current_player_id),
) -> CaddieDecisionAuditLatestResponse:
    # Member-scoped read: exactly mirrors the partition used by the decision and audit POSTs.
    return latest_decision_audit_response(decision_id, player_id=player_id)


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


_GEOMETRY_UPGRADE_LOCK = threading.Lock()
_GEOMETRY_UPGRADE_RUNNING: set[int] = set()
_GEOMETRY_UPGRADE_PENDING: dict[int, set[int]] = {}
_GEOMETRY_UPGRADE_INFLIGHT: dict[int, set[int]] = {}
# Geometry installation already has a process-wide two-hole window.  Keep only one heavy topo
# render in the overlap lane so geometry and rasterisation can make progress together without
# multiplying the shared homeserver's peak memory.  The renderer itself still single-flights a
# duplicate path and validates the revision before publishing its PNG.
_TOPO_PIPELINE_POOL = ThreadPoolExecutor(max_workers=1, thread_name_prefix="course-topo-pipeline")


def _normalise_authority_observation(evidence: dict[str, Any]) -> str:
    """Return the release probe's bounded public state.

    Older cached evidence payloads predate ``authorityObservation``. A ready payload that already
    carries a revision is safe to treat as current for compatibility; an incomplete payload remains
    unknown and therefore retryable.
    """
    raw = str(evidence.get("authorityObservation") or "").strip().lower()
    if raw in {"current", "stale", "unknown", "not_required"}:
        return raw
    if (
        str(evidence.get("coverage") or "").strip().lower() == "ready"
        and str(evidence.get("geometryRevision") or "").strip()
    ):
        return "current"
    return "unknown"


def _probe_geometry_revision(global_id: int, hole: int) -> tuple[str | None, str]:
    """Probe a hole's release identity without collapsing transient errors into stale data.

    The second tuple item is one of ``current``, ``stale`` or ``unknown``. ``unknown`` is an
    operationally retryable result: the authority sidecar/release document could not be observed,
    so callers must not overwrite an existing ready row or show a user-facing failure.
    """
    from ai_caddie.geometry.geometry_evidence import geometry_coverage_for_hole

    last_observation = "unknown"
    for delay in (0.0, 0.05, 0.2):
        if delay:
            time.sleep(delay)
        try:
            evidence = geometry_coverage_for_hole(
                int(global_id),
                int(hole),
                require_current_authority=True,
                refresh_release=False,
            )
        except Exception:  # noqa: BLE001 - transient local/provider observation failure
            evidence = {"coverage": "partial", "authorityObservation": "unknown"}
        observation = _normalise_authority_observation(evidence)
        last_observation = observation
        coverage = str(evidence.get("coverage") or "").strip().lower()
        revision = str(evidence.get("geometryRevision") or "").strip().lower() or None
        if observation == "stale":
            return None, "stale"
        if coverage == "ready" and revision:
            # A cached release may be unavailable while the local derivative identity remains
            # usable. Keep the revision, but let the caller know that its freshness is uncertain.
            return revision, observation
        if observation == "current":
            # Current authority without a cache token is incomplete, not proof of staleness.
            last_observation = "unknown"
    return None, "unknown" if last_observation == "current" else last_observation


def _render_course_topo_one(
    global_id: int,
    hole: int,
    expected_revision: str | None = None,
) -> bool | dict[str, Any]:
    """Render one immutable topo asset and report whether bytes were actually available.

    The older ``_prewarm_course_topo`` helper intentionally swallowed every error because it was
    a best-effort HTTP background task.  A durable install journal needs a truthful per-hole result
    so it can remain retryable instead of claiming a complete course after a silent 404.
    """
    from ai_caddie.geometry import topo_render

    expected = str(expected_revision or "").strip().lower() or None
    before_revision, before_observation = _probe_geometry_revision(global_id, hole)
    if before_observation == "stale":
        return {"status": "retryable", "reason": "geometry release changed"}
    if expected and before_revision and before_revision != expected:
        return {"status": "retryable", "reason": "geometry release changed"}
    if expected and not before_revision:
        return {"status": "retryable", "reason": "geometry revision unavailable"}
    try:
        payload = topo_render.render_hole_topo_cached(int(global_id), int(hole))
        if not payload:
            return False
        after_revision, after_observation = _probe_geometry_revision(global_id, hole)
        if after_observation == "stale":
            return {"status": "retryable", "reason": "geometry release changed"}
        if expected and after_revision != expected:
            return {"status": "retryable", "reason": "geometry revision unavailable"}
        if expected or after_revision:
            return {"status": "ready", "revision": after_revision or expected}
        return {"status": "retryable", "reason": "geometry revision unavailable"}
    except Exception:  # noqa: BLE001 - the journal records the failed hole, not a request error
        return False


def _current_geometry_revision(global_id: int, hole: int) -> str | None:
    """Return the release-bound derivative identity after a geometry install.

    ``ensure_prodgeometry`` deliberately returns a compact operational result and does not copy
    the cache-token implementation into every caller.  Re-reading the cheap local authority probe
    here gives the journal a stable per-hole binding and makes an unbound/legacy pair ineligible
    for a supposedly complete install.
    """
    revision, observation = _probe_geometry_revision(global_id, hole)
    return revision if observation != "stale" else None


def run_course_install_job(identifier: str) -> None:
    """Run one durable course-install journal to completion.

    Geometry is downloaded with the existing two-hole bounded window.  Each successful geometry
    hole is handed to the single topo lane immediately, so the first precise bitmap is not held
    behind an 18-hole geometry barrier.  The journal is updated after every hole and can therefore
    resume safely after an API restart or a transient provider failure.
    """
    state = course_install.state_for_worker(identifier)
    if state is None:
        return
    rows = [row for row in (state.get("holes") or {}).values() if isinstance(row, dict)]
    if not rows:
        course_install.update(identifier, phase="failed", stage="error", error="course has no holes")
        return

    state = course_install.state_for_worker(identifier) or state
    rows = [row for row in (state.get("holes") or {}).values() if isinstance(row, dict)]
    topo_futures: dict[Any, tuple[int, int, str, int]] = {}
    topo_completion_events: dict[Any, threading.Event] = {}

    def finish_topo_future(
        future: Any,
        *,
        gid: int,
        hole: int,
        geometry_revision: str,
        work_revision: int,
    ) -> None:
        try:
            result = future.result()
        except Exception:  # noqa: BLE001 - persist a retryable hole state
            result = False
        if isinstance(result, dict):
            result_status = str(result.get("status") or "").strip().lower()
            ok = result_status == "ready"
            retryable = result_status in {"retryable", "unknown", "stale"}
            result_error = str(result.get("reason") or "topo render failed")
        else:
            # Keep compatibility with older/test renderers that returned a boolean.
            ok = bool(result)
            retryable = False
            result_error = "topo render failed"
        topo_state = "ready" if ok else ("queued" if retryable else "failed")
        course_install.update(
            identifier,
            phase="running",
            stage="topo" if ok or retryable else "error",
            global_id=gid,
            local_hole=hole,
            topo=topo_state,
            topo_revision=geometry_revision if ok else None,
            error=None if ok or retryable else result_error,
            clear_error=ok or retryable,
            expected_work_revision=work_revision,
        )

    def queue_topo(row: dict[str, Any]) -> None:
        gid = int(row.get("globalId") or 0)
        hole = int(row.get("localHole") or 0)
        if gid <= 0 or hole <= 0:
            return
        current = course_install.state_for_worker(identifier) or {}
        current_row = (current.get("holes") or {}).get(f"{gid}:{hole}") or {}
        geometry_revision = str(
            current_row.get("geometryRevision") or row.get("geometryRevision") or ""
        ).strip().lower()
        if not geometry_revision:
            return
        if course_install._topo_ready(current_row):
            return
        future = _TOPO_PIPELINE_POOL.submit(_render_course_topo_one, gid, hole, geometry_revision)
        work_revision = int(current_row.get("workRevision") or 1)
        topo_futures[future] = (gid, hole, geometry_revision, work_revision)
        completion_event = threading.Event()
        topo_completion_events[future] = completion_event
        course_install.update(
            identifier,
            phase="running",
            stage="topo",
            global_id=gid,
            local_hole=hole,
            topo="running",
            expected_work_revision=work_revision,
        )
        def persist_completed_topo(
            completed: Any,
            *,
            gid: int = gid,
            hole: int = hole,
            revision: str = geometry_revision,
            work: int = work_revision,
            persisted: threading.Event = completion_event,
        ) -> None:
            try:
                finish_topo_future(
                    completed,
                    gid=gid,
                    hole=hole,
                    geometry_revision=revision,
                    work_revision=work,
                )
            finally:
                # Future.result() may wake before CPython invokes done callbacks. Signal only after
                # the durable row write so the final phase decision cannot observe topo="running".
                persisted.set()

        future.add_done_callback(persist_completed_topo)

    pending_by_gid: dict[int, list[int]] = {}
    for row in rows:
        # Revalidate geometry for every hole whose topo is not complete. A package-level ready bit
        # is only a snapshot; this closes the race where a file is removed/rebound between enqueue
        # and the worker's render attempt.
        if course_install._geometry_ready(row) and course_install._topo_ready(row):
            continue
        gid = int(row.get("globalId") or 0)
        hole = int(row.get("localHole") or 0)
        if gid > 0 and hole > 0:
            pending_by_gid.setdefault(gid, []).append(hole)

    from ai_caddie.caddie.mobile_live import _ensure_geometry_for_course

    completed_geometry_keys: set[tuple[int, int]] = set()
    expected_work_revisions = {
        (
            int(row.get("globalId") or 0),
            int(row.get("localHole") or 0),
        ): int(row.get("workRevision") or 1)
        for row in rows
        if int(row.get("globalId") or 0) > 0 and int(row.get("localHole") or 0) > 0
    }

    def on_geometry_complete(result: dict[str, Any]) -> None:
        gid = int(result.get("globalId") or 0)
        hole = int(result.get("localHole") or 0)
        if gid <= 0 or hole <= 0:
            return
        expected_work_revision = expected_work_revisions.get((gid, hole))
        current = course_install.state_for_worker(identifier) or {}
        current_row = (current.get("holes") or {}).get(f"{gid}:{hole}") or {}
        if (
            expected_work_revision is not None
            and int(current_row.get("workRevision") or 0) != expected_work_revision
        ):
            # A newer package re-bound this hole while the old provider request was in flight.
            # The next worker pass owns it; this callback must not resurrect stale bytes.
            return
        completed_geometry_keys.add((gid, hole))
        ok = bool(result.get("ok"))
        revision, observation = _probe_geometry_revision(gid, hole) if ok else (None, "unknown")
        expected_revision = str(current_row.get("geometryRevision") or "").strip().lower() or None
        retryable = False
        if ok and observation == "stale":
            retryable = True
            result = {**result, "reason": "geometry release changed"}
        elif ok and not revision:
            retryable = True
            result = {**result, "reason": "geometry revision unavailable"}
        elif ok and expected_revision and revision != expected_revision:
            retryable = True
            result = {**result, "reason": "geometry release changed"}
        geometry_state = "ready" if ok and not retryable else "queued"
        course_install.update(
            identifier,
            phase="running",
            stage="geometry" if not ok or retryable else "topo",
            global_id=gid,
            local_hole=hole,
            geometry=geometry_state if (ok or retryable) else "failed",
            geometry_revision=revision if ok and not retryable else expected_revision,
            error=None if ok or retryable else str(result.get("reason") or "geometry download failed"),
            clear_error=ok or retryable,
            expected_work_revision=expected_work_revision,
        )
        if ok and not retryable:
            queue_topo({
                "globalId": gid,
                "localHole": hole,
                "topo": "queued",
                "geometryRevision": revision,
            })

    for gid, holes in sorted(pending_by_gid.items()):
        try:
            summary = _ensure_geometry_for_course(
                gid,
                holes=sorted(set(holes)),
                on_hole_complete=on_geometry_complete,
            )
            # A legacy/test implementation may omit the callback. Reconcile from its deterministic
            # result list so the journal never remains permanently queued.
            for result in summary.get("results") or []:
                if not isinstance(result, dict):
                    continue
                result_key = (int(result.get("globalId") or gid), int(result.get("localHole") or 0))
                if result_key in completed_geometry_keys:
                    continue
                # Real callbacks normally update the row. This branch only fills a missing row
                # for a legacy/test implementation that does not invoke the optional callback.
                on_geometry_complete({**result, "globalId": result_key[0]})
        except Exception as exc:  # noqa: BLE001 - continue other physical loops
            for hole in sorted(set(holes)):
                course_install.update(
                    identifier,
                    global_id=gid,
                    local_hole=hole,
                    geometry="failed",
                    error="geometry download failed",
                    expected_work_revision=expected_work_revisions.get((gid, hole)),
                )

    # Wait for every submitted topo *and its journal callback*. Future.result() alone is not a
    # callback barrier: CPython notifies result waiters before invoking callbacks.
    for future, (_gid, _hole, _revision, _work_revision) in list(topo_futures.items()):
        try:
            future.result()
        except Exception:  # noqa: BLE001
            pass
        topo_completion_events[future].wait()

    final = course_install.state_for_worker(identifier) or {}
    final_rows = [row for row in (final.get("holes") or {}).values() if isinstance(row, dict)]
    if final_rows and course_install._all_assets_ready(final):
        course_install.update(identifier, phase="ready", stage="complete", clear_error=True)
    elif any(
        row.get("geometry") == "failed" or row.get("topo") == "failed"
        for row in final_rows
    ):
        failed = next(
            (str(row.get("error") or "asset unavailable") for row in final_rows
             if row.get("geometry") == "failed" or row.get("topo") == "failed"),
            "asset unavailable",
        )
        course_install.update(identifier, phase="failed", stage="error", error=failed)
    else:
        # New refs can be merged while this worker is finishing. Leave the durable row queued so
        # the hand-off in ``course_install._run`` starts another pass instead of stranding it.
        course_install.update(identifier, phase="queued", stage="queued", error=None, clear_error=True)


@app.get("/api/v2/mobile/courses/{global_id}/package", response_model=LiveRoundPackageResponse)
def mobile_course_package(
    global_id: int,
    background_tasks: BackgroundTasks,
    round_id: str | None = None,
    tee_box: str | None = None,
    captured_at: str | None = None,
    client_id: str | None = None,
    ensure_geometry: bool = False,
    background_geometry: bool = False,
    include_event_cursor: bool = True,
    nine: str = Query(default="all", pattern="^(all|front|back)$"),
    back_global_id: int | None = None,
    player_id: str = Depends(current_player_id),
) -> LiveRoundPackageResponse:
    package = build_mobile_course_package_response(
        global_id,
        round_id=round_id,
        tee_box=tee_box,
        captured_at=captured_at,
        client_id=client_id,
        ensure_geometry=ensure_geometry,
        include_event_cursor=include_event_cursor,
        nine=nine,
        back_global_id=back_global_id,
        player_id=player_id,
    )
    if not background_geometry or ensure_geometry:
        return package

    # The package response remains lightweight, but the expensive work now belongs to a durable,
    # idempotent journal rather than FastAPI's process-local BackgroundTasks. A request can safely
    # finish, the app can be suspended, and an API restart can resume the same course job.
    refs: list[dict[str, Any]] = []
    requested: dict[int, list[int]] = {}
    ready: dict[int, list[int]] = {}
    for hole in package.holes:
        source_global_id = int(
            hole.get("sourceGlobalId") or package.course.get("globalId") or global_id
        )
        source_local_hole = int(hole.get("sourceLocalHole") or hole.get("number") or 0)
        display_hole = int(hole.get("number") or source_local_hole or 0)
        if source_global_id <= 0 or source_local_hole <= 0:
            continue
        refs.append({
            "globalId": source_global_id,
            "localHole": source_local_hole,
            "displayHole": display_hole,
            "geometryRevision": hole.get("geometryRevision"),
            "geometryAuthorityObservation": hole.get("geometryAuthorityObservation"),
        })
        target = (
            ready
            if str(hole.get("geometryCoverage") or "missing").lower() == "ready"
            else requested
        )
        target.setdefault(source_global_id, []).append(source_local_hole)

    if not refs:
        return package
    job = course_install.enqueue(
        global_id=int(global_id),
        tee_box=str(tee_box or package.course.get("teeBox") or "blue"),
        nine=nine,
        player_id=player_id,
        refs=refs,
        requested=requested,
        ready=ready,
        back_global_id=back_global_id,
    )
    # Pydantic response models are mutable in the current contract, but use model_copy when
    # available so this remains safe if the model becomes frozen later.
    if hasattr(package, "model_copy"):
        return package.model_copy(update={"courseInstallJob": job})
    package.courseInstallJob = job
    return package


@app.get(
    "/api/v2/courses/{global_id}/install/status",
    response_model=CourseInstallStatusResponse,
)
def course_install_status(
    global_id: int,
    tee_box: str | None = Query(default=None, alias="tee_box"),
    nine: str = Query(default="all", pattern="^(all|front|back)$"),
    back_global_id: int | None = Query(default=None, alias="back_global_id", ge=1),
    player_id: str = Depends(current_player_id),
) -> CourseInstallStatusResponse:
    state = course_install.status(
        global_id=int(global_id),
        tee_box=str(tee_box or "blue"),
        nine=nine,
        player_id=player_id,
        back_global_id=back_global_id,
    )
    if state is None:
        raise HTTPException(status_code=404, detail="course install job not found")
    return CourseInstallStatusResponse(**state)


def _upgrade_course_geometry(requested: dict[int, list[int]]) -> None:
    """Best-effort precise upgrade after a lightweight package is already returned.

    Mobile installers fetch the selected topo PNGs themselves (iOS concurrently, Watch in bounded
    batches). Once geometry is installed, also warm the immutable topo cache: iOS may be suspended
    after the user backgrounds the app, but server-side preparation can safely finish and the phone
    then resumes with cache hits. Duplicate client requests share the renderer's singleflight.

    Multiple package reads commonly overlap while a course is being installed.  Coalesce those
    requests by source GID and ignore holes already in flight; the per-hole geometry locks remain the
    final write-safety boundary, while this process-level single-flight avoids duplicate queue work.
    """
    from ai_caddie.caddie.mobile_live import _ensure_geometry_for_course

    owned: list[int] = []
    with _GEOMETRY_UPGRADE_LOCK:
        for raw_global_id, raw_holes in requested.items():
            global_id = int(raw_global_id)
            inflight = _GEOMETRY_UPGRADE_INFLIGHT.get(global_id, set())
            holes = {int(hole) for hole in raw_holes if int(hole) > 0} - inflight
            if holes:
                _GEOMETRY_UPGRADE_PENDING.setdefault(global_id, set()).update(holes)
            if global_id not in _GEOMETRY_UPGRADE_RUNNING and _GEOMETRY_UPGRADE_PENDING.get(global_id):
                _GEOMETRY_UPGRADE_RUNNING.add(global_id)
                owned.append(global_id)

    for global_id in sorted(owned):
        try:
            while True:
                with _GEOMETRY_UPGRADE_LOCK:
                    # Keep the completed batch marked in-flight until this same critical section
                    # checks for follow-up work. A duplicate arriving in that small hand-off window
                    # is therefore still coalesced instead of causing one final cached re-run.
                    _GEOMETRY_UPGRADE_INFLIGHT.pop(global_id, None)
                    holes = sorted(_GEOMETRY_UPGRADE_PENDING.pop(global_id, set()))
                    if not holes:
                        _GEOMETRY_UPGRADE_RUNNING.discard(global_id)
                        break
                    _GEOMETRY_UPGRADE_INFLIGHT[global_id] = set(holes)
                logger.info("course geometry upgrade started gid=%s holes=%s", global_id, holes)
                try:
                    # This legacy helper remains a compatibility path for callers that explicitly
                    # request the old best-effort upgrade. The durable install worker above owns the
                    # progressive geometry→topo pipeline; keeping this path simple also preserves
                    # its injected/test contract and avoids two coordinators doing the same work.
                    _ensure_geometry_for_course(global_id, holes=holes)
                    topo_started = time.perf_counter()
                    _prewarm_course_topo(global_id, holes)
                    logger.info(
                        "course_install stage=topo gid=%s duration_ms=%s",
                        global_id,
                        int((time.perf_counter() - topo_started) * 1000),
                    )
                except Exception:
                    # The active lightweight package remains valid; a later request may retry the
                    # precise upgrade without changing the course or round identity.
                    logger.exception("course geometry upgrade failed gid=%s holes=%s", global_id, holes)
                logger.info("course geometry upgrade finished gid=%s holes=%s", global_id, holes)
        finally:
            # Do not leave a permanently owned GID if the worker is cancelled during shutdown.
            with _GEOMETRY_UPGRADE_LOCK:
                _GEOMETRY_UPGRADE_INFLIGHT.pop(global_id, None)
                _GEOMETRY_UPGRADE_RUNNING.discard(global_id)


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


@app.post(
    "/api/v2/mobile/rounds/{round_id}/finish",
    response_model=RoundIngestResponse,
    status_code=201,
)
def mobile_round_finish(
    round_id: str,
    request: MobileRoundFinishRequest,
    acting_player_id: str = Depends(current_player_id),
) -> RoundIngestResponse:
    return finish_mobile_round_response(round_id, request, player_id=acting_player_id)


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
