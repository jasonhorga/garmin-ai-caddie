from __future__ import annotations

from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware

from ai_caddie.connectors.garmin_cn import GarminCnWebSessionConnector, sanitize_error
from ai_caddie.connectors.snapshot import snapshot_to_payload

from .history_overview import load_history_overview_response
from .history_rounds import load_history_rounds_response
from .history_stats import load_history_stats_response
from .models import (
    HistoryOverviewResponse,
    HistoryRoundsResponse,
    HistoryStatsResponse,
    ReviewReportResponse,
    SyncRunResponse,
    SyncStatusResponse,
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
