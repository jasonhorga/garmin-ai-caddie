from __future__ import annotations

from pathlib import Path

from fastapi import HTTPException

from ai_caddie.connectors.garmin_cn import garmin_token_dir
from ai_caddie.connectors.session_material import save_garmin_cn_web_session
from ai_caddie.core.data import ROOT
from ai_caddie.rounds.players import OWNER_ID

from .models import GarminSessionImportRequest, GarminSessionImportResponse


SESSION_ROOT = ROOT


def save_garmin_session_response(
    request: GarminSessionImportRequest, *, player_id: str = OWNER_ID
) -> GarminSessionImportResponse:
    """Persist a captured Garmin web session for ``player_id`` (owner by default).

    The cookie lands at the player's token dir: owner -> ``SESSION_ROOT/.garmin_tokens``
    (byte-for-byte); member -> ``SESSION_ROOT/data/players/<id>/.garmin_tokens``. The
    connector-status write follows the same partition so a member bind never clobbers
    the owner's status.
    """
    token_dir = garmin_token_dir(player_id, SESSION_ROOT)
    bind_root = token_dir.parent  # owner -> SESSION_ROOT; member -> SESSION_ROOT/data/players/<id>
    data_dir = None if player_id == OWNER_ID else bind_root
    try:
        payload = save_garmin_cn_web_session(
            web_session_header=request.webSessionHeader,
            anti_forgery_value=request.antiForgeryValue,
            source=request.source,
            root=bind_root,
            data_dir=data_dir,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return GarminSessionImportResponse(**payload)
