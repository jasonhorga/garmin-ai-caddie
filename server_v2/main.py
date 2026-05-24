from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .history_overview import load_history_overview_response
from .models import HistoryOverviewResponse


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
