from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .history_overview import load_history_overview_response
from .history_rounds import load_history_rounds_response
from .models import HistoryOverviewResponse, HistoryRoundsResponse, SyncStatusResponse
from .sync_status import load_sync_status_response


app = FastAPI(title="AI Caddie v2", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5173",
        "http://localhost:5173",
    ],
    allow_credentials=False,
    allow_methods=["GET"],
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
            "syncStatus": "/api/v2/sync/status",
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


@app.get("/api/v2/sync/status", response_model=SyncStatusResponse)
def sync_status() -> SyncStatusResponse:
    return load_sync_status_response()
