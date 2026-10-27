"""Anonymous, read-only round-share HTTP endpoints."""
from __future__ import annotations

from collections import defaultdict, deque
import threading
import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field

from ai_caddie.history.history_round_detail import build_history_round_detail
from ai_caddie.rounds import correction_audit, players, round_shares
from server_v2.data_source import load_history_data_for_mode
from server_v2.history_round_detail import ANNOTATION_ROOT
from server_v2.players_api import current_player_id


router = APIRouter(prefix="/api/v2", tags=["round-shares"])

_NOT_FOUND_HEADERS = {
    "Cache-Control": "no-store",
    "X-Robots-Tag": "noindex, nofollow, noarchive",
}
_PUBLIC_HEADERS = dict(_NOT_FOUND_HEADERS)

# The service currently runs one API worker.  A small in-process sliding window keeps abuse
# bounded without introducing a new shared state dependency; every route still remains correct
# if a worker restarts (the capability itself is persisted and revocation is read-through).
CREATE_LIMIT = 30
CREATE_WINDOW_SECONDS = 3600.0
TOKEN_READ_LIMIT = 120
TOKEN_READ_WINDOW_SECONDS = 60.0
UNKNOWN_READ_LIMIT = 60
UNKNOWN_READ_WINDOW_SECONDS = 60.0


class SharedRoundModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    date: str | None = None
    courseName: str
    score: int | None = None
    par: int | None = None
    toPar: int | None = None
    holesScored: int = 0


class SharedScorecardHole(BaseModel):
    model_config = ConfigDict(extra="forbid")

    hole: int
    par: int | None = None
    score: int | None = None
    toPar: int | None = None
    putts: int | None = None
    penalties: int | None = None
    gir: bool | None = None
    fairway: str | bool | None = None


class SharedRoundResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_: str = Field(alias="schema")
    found: bool
    expiresAt: str
    round: SharedRoundModel
    scorecard: list[SharedScorecardHole]


class ShareCreatedResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_: str = Field(alias="schema")
    url: str
    pageUrl: str
    expiresAt: str
    shareId: str


class ShareRevokedResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    revoked: int


class _SlidingWindow:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._values: dict[str, deque[float]] = defaultdict(deque)

    def allow(self, key: str, *, limit: int, window: float, now: float | None = None) -> bool:
        current = time.monotonic() if now is None else now
        with self._lock:
            values = self._values[key]
            cutoff = current - window
            while values and values[0] <= cutoff:
                values.popleft()
            if len(values) >= limit:
                return False
            values.append(current)
            # Keep a bounded number of stale keys in a long-lived worker.
            if len(self._values) > 4096:
                for old_key in list(self._values)[:1024]:
                    if not self._values[old_key]:
                        self._values.pop(old_key, None)
            return True


_create_window = _SlidingWindow()
_read_window = _SlidingWindow()


def reset_rate_limits() -> None:
    """Test hook; production never needs to clear these process-local windows."""
    global _create_window, _read_window
    _create_window = _SlidingWindow()
    _read_window = _SlidingWindow()


def _not_found() -> HTTPException:
    return HTTPException(status_code=404, detail="share link not found", headers=_NOT_FOUND_HEADERS)


def _too_many() -> HTTPException:
    return HTTPException(status_code=429, detail="share rate limit exceeded", headers=_NOT_FOUND_HEADERS)


def _method_not_allowed() -> HTTPException:
    return HTTPException(status_code=405, detail="share links are read-only", headers={**_NOT_FOUND_HEADERS, "Allow": "GET"})


def _round_for_player(player_id: str, round_ref: str):
    data, _mode = load_history_data_for_mode(player_id=player_id)
    if not correction_audit.round_exists(data, round_ref):
        raise _not_found()
    canonical, _refs = correction_audit.round_identity(data, round_ref)
    return data, canonical


def _shared_payload(row: dict[str, Any]) -> dict[str, Any]:
    player_id = str(row.get("playerId") or "")
    if players.get_player(player_id) is None:
        raise _not_found()
    data, _mode = load_history_data_for_mode(player_id=player_id)
    round_ref = str(row.get("roundRef") or "")
    detail = build_history_round_detail(
        data,
        round_ref,
        annotations_root=ANNOTATION_ROOT,
        player_id=player_id,
    )
    if not detail.get("found") or not isinstance(detail.get("round"), dict):
        raise _not_found()
    summary = detail["round"]
    public_round = {
        key: summary.get(key)
        for key in ("id", "date", "courseName", "score", "par", "toPar", "holesScored")
    }
    public_scorecard: list[dict[str, Any]] = []
    for cell in detail.get("scorecard") or []:
        if not isinstance(cell, dict):
            continue
        public_scorecard.append({
            key: cell.get(key)
            for key in ("hole", "par", "score", "toPar", "putts", "penalties", "gir", "fairway")
        })
    return {
        "schema": "ai-caddie-shared-round-v1",
        "found": True,
        "expiresAt": str(row.get("expiresAt")),
        "round": public_round,
        "scorecard": public_scorecard,
    }


def _set_headers(response: Response, headers: dict[str, str] = _PUBLIC_HEADERS) -> None:
    for key, value in headers.items():
        response.headers[key] = value


@router.post(
    "/history/rounds/{round_ref}/share",
    response_model=ShareCreatedResponse,
    status_code=201,
)
def create_round_share(
    round_ref: str,
    response: Response,
    player_id: str = Depends(current_player_id),
) -> ShareCreatedResponse:
    if not _create_window.allow(str(player_id), limit=CREATE_LIMIT, window=CREATE_WINDOW_SECONDS):
        raise _too_many()
    _data, canonical = _round_for_player(player_id, round_ref)
    # Re-check the player at creation time.  The owner is implicit and need not have a registry file.
    if players.get_player(player_id) is None:
        raise _not_found()
    created = round_shares.create_share(player_id, canonical)
    if created is None:
        raise _too_many()
    token = str(created["token"])
    _set_headers(response)
    return ShareCreatedResponse(
        schema="ai-caddie-round-share-v1",
        url=f"/api/v2/share/{token}",
        pageUrl=f"/s/{token}",
        expiresAt=str(created["expiresAt"]),
        shareId=str(created["shareId"]),
    )


@router.delete(
    "/history/rounds/{round_ref}/share",
    response_model=ShareRevokedResponse,
)
def revoke_round_share(
    round_ref: str,
    response: Response,
    player_id: str = Depends(current_player_id),
) -> ShareRevokedResponse:
    _data, canonical = _round_for_player(player_id, round_ref)
    revoked = round_shares.revoke_round(player_id, canonical)
    _set_headers(response)
    return ShareRevokedResponse(revoked=revoked)


@router.get("/share/{token}", response_model=SharedRoundResponse)
def read_round_share(token: str, response: Response) -> SharedRoundResponse:
    if not round_shares.token_format_ok(token):
        raise _not_found()
    row = round_shares.find_share(token)
    if row is None:
        if not _read_window.allow("unknown", limit=UNKNOWN_READ_LIMIT, window=UNKNOWN_READ_WINDOW_SECONDS):
            raise _too_many()
        raise _not_found()
    key = "token:" + str(row.get("tokenHash"))
    if not _read_window.allow(key, limit=TOKEN_READ_LIMIT, window=TOKEN_READ_WINDOW_SECONDS):
        raise _too_many()
    payload = _shared_payload(row)
    _set_headers(response)
    return SharedRoundResponse.model_validate(payload)


@router.get("/share/{token}/{rest:path}")
def read_round_share_subpath(token: str, rest: str) -> None:
    # Keeping a catch-all GET avoids a framework-generated 307/405 distinction for guessed
    # correction paths, while retaining one uniform anonymous failure response.
    raise _not_found()


def _reject_share_write(token: str, rest: str = "") -> None:
    raise _method_not_allowed()


for _method in ("post", "put", "patch", "delete"):
    # FastAPI's decorator API is intentionally used here rather than a generic ASGI middleware:
    # OpenAPI and route-policy tests can see every read-only method explicitly.
    router.add_api_route(
        "/share/{token}", _reject_share_write, methods=[_method.upper()], include_in_schema=False,
    )
    router.add_api_route(
        "/share/{token}/{rest:path}", _reject_share_write, methods=[_method.upper()], include_in_schema=False,
    )

