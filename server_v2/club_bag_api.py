"""Builders for the member-scoped manual club-bag API.

``build_effective_club_bag_response`` projects the EFFECTIVE bag (manual selection wins, else the
synced Garmin bag, else empty) into the served shape; ``save_manual_club_bag_response`` validates +
persists a manual bag (or clears it when empty) and returns the resulting effective bag. The route
layer (server_v2/main.py) owns auth + cache invalidation; this module is pure projection so it can be
unit-tested without FastAPI.
"""
from __future__ import annotations

from ai_caddie.caddie import club_bag, club_catalog
from .models import ClubBagManualRequest, EffectiveClubBagResponse


def build_effective_club_bag_response(player_id: str) -> dict:
    bag = club_bag.effective_club_bag(player_id)
    clubs = []
    for c in bag["clubs"]:
        if bag["source"] == "manual":
            token = str(c.get("token") or "")
            dist = c.get("distanceM")
            clubs.append({
                "token": token,
                "zhName": club_catalog.catalog_zh(token),
                "customName": c.get("customName"),
                "clubTypeId": club_catalog.catalog_clubtype_id(token),
                "distanceM": dist if dist is not None else club_catalog.default_distance_m(token),
                "distanceSource": "manual" if dist is not None else "default",
            })
        else:  # garmin synced bag: map clubTypeId -> token via the canon mapping
            from ai_caddie.caddie.club_bag import _CLUBTYPE_CANON, canonical_club_name
            type_id = c.get("clubTypeId")
            token = _CLUBTYPE_CANON.get(type_id) or canonical_club_name(c.get("customName"))
            clubs.append({
                "token": token, "zhName": club_catalog.catalog_zh(token) if token else None,
                "customName": c.get("customName"), "clubTypeId": type_id,
                "distanceM": None, "distanceSource": None,
            })
    return {"schema": "ai-caddie-effective-club-bag-v1", "source": bag["source"],
            "found": bool(clubs), "clubs": clubs}


def save_manual_club_bag_response(player_id: str, request: ClubBagManualRequest) -> dict:
    if not request.clubs:
        club_bag.clear_manual_club_bag(player_id)
    else:
        club_bag.save_manual_club_bag(player_id, [c.model_dump() for c in request.clubs])
    return build_effective_club_bag_response(player_id)
