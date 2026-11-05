"""Builders for the member-scoped manual club-bag API.

``build_effective_club_bag_response`` projects the EFFECTIVE bag (manual selection wins, else the
synced Garmin bag, else empty) into the served shape; ``save_manual_club_bag_response`` validates +
persists a manual bag (or clears it when empty) and returns the resulting effective bag. The route
layer (server_v2/main.py) owns auth + cache invalidation; this module is pure projection so it can be
unit-tested without FastAPI.
"""
from __future__ import annotations

from typing import Callable, TypeVar

import anyio
from anyio.lowlevel import RunVar
from fastapi import Request

from ai_caddie.caddie import club_bag, club_catalog
from ai_caddie.core import request_timing
from .models import ClubBagManualRequest, EffectiveClubBagResponse
from .players_api import current_player_id


_T = TypeVar("_T")
_READ_LIMITER: RunVar[anyio.CapacityLimiter] = RunVar("club_bag_read_limiter")


def _read_limiter() -> anyio.CapacityLimiter:
    # Per running loop, like AnyIO's default limiter, but never shared with course/startup work.
    limiter = _READ_LIMITER.get(None)
    if limiter is None:
        limiter = anyio.CapacityLimiter(4)
        _READ_LIMITER.set(limiter)
    return limiter


async def run_bag_read(stage: str, function: Callable[..., _T], *args, **kwargs) -> _T:
    """Offload only bag GET auth/reads; waiting and execution are separate timed spans.

    Cancellation keeps AnyIO's shielded worker semantics: no abandoned read can free a
    limiter token while it is still running. This lane never does sync, stats or course prep.
    """
    timing = request_timing.current()
    queued = timing.clock() if timing is not None else 0.0

    def work() -> _T:
        if timing is not None:
            timing.duration(f"{stage}_worker_queue", queued)
            started = timing.clock()
        try:
            return function(*args, **kwargs)
        finally:
            if timing is not None:
                timing.duration(stage, started)

    return await anyio.to_thread.run_sync(work, limiter=_read_limiter())


async def bag_current_player_id(request: Request) -> str:
    # Call the original resolver on every request; no credential/result cache or policy change.
    return await run_bag_read("auth_player", current_player_id, request)


def build_effective_club_bag_response(player_id: str) -> dict:
    bag = club_bag.effective_club_bag(player_id)
    clubs = []
    for c in bag["clubs"]:
        if bag["source"] == "manual":
            token = str(c.get("token") or "")
            dist = c.get("distanceM")
            default = club_catalog.default_distance_m(token)
            # distanceSource is "default" ONLY when a catalog default actually fills in for a missing
            # user value; a token with no default (e.g. wood7) reports null distance + null source.
            clubs.append({
                "token": token,
                "zhName": club_catalog.catalog_zh(token),
                "customName": c.get("customName"),
                "clubTypeId": club_catalog.catalog_clubtype_id(token),
                "distanceM": dist if dist is not None else default,
                "distanceSource": "manual" if dist is not None else ("default" if default is not None else None),
            })
        else:  # garmin synced bag: map clubTypeId -> token via the canon mapping
            from ai_caddie.caddie.club_bag import _CLUBTYPE_CANON, canonical_club_name
            type_id = c.get("clubTypeId")
            # A recognised player rename is more specific than Garmin's generic type (for example
            # a 50° wedge stored under GW). Keep one physical identity instead of exposing both.
            token = canonical_club_name(c.get("customName")) or _CLUBTYPE_CANON.get(type_id)
            garmin_distance = club_bag.garmin_distance_m(c)
            clubs.append({
                "token": token, "zhName": club_catalog.catalog_zh(token) if token else None,
                "customName": c.get("customName"), "clubTypeId": type_id,
                "distanceM": garmin_distance[0] if garmin_distance else None,
                "distanceSource": garmin_distance[1] if garmin_distance else None,
            })
    return {"schema": "ai-caddie-effective-club-bag-v1", "source": bag["source"],
            "found": bool(clubs), "clubs": clubs}


def save_manual_club_bag_response(player_id: str, request: ClubBagManualRequest) -> dict:
    if not request.clubs:
        club_bag.clear_manual_club_bag(player_id)
    else:
        club_bag.save_manual_club_bag(player_id, [c.model_dump() for c in request.clubs])
    return build_effective_club_bag_response(player_id)
