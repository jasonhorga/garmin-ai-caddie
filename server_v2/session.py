from __future__ import annotations

from pathlib import Path

from fastapi import HTTPException

from ai_caddie.connectors.session_material import save_garmin_cn_web_session
from ai_caddie.data import ROOT

from .models import GarminSessionImportRequest, GarminSessionImportResponse


SESSION_ROOT = ROOT


def save_garmin_session_response(request: GarminSessionImportRequest) -> GarminSessionImportResponse:
    try:
        payload = save_garmin_cn_web_session(
            web_session_header=request.webSessionHeader,
            anti_forgery_value=request.antiForgeryValue,
            source=request.source,
            root=SESSION_ROOT,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return GarminSessionImportResponse(**payload)
