"""Serve the player's real Garmin club bag (``data/club_bag.json``) to the mobile app.

The bag is fetched by ``fetch.fetch_clubs`` during sync (Garmin ``/club/player`` + ``/club/types``)
and is owner-global — only the owner syncs clubs, so other players have no bag. The display name is
resolved to Chinese on the client (iOS owns the catalog), so this layer stays language-neutral.
"""

from __future__ import annotations

from typing import Any

from ai_caddie.data import load_club_bag

SCHEMA = "ai-caddie-club-bag-v1"


def _empty() -> dict[str, Any]:
    return {"schema": SCHEMA, "found": False, "clubs": []}


def build_club_bag_response(*, player_id: str = "me", owner_id: str = "me") -> dict[str, Any]:
    """Build the ``ClubBagResponse`` payload for ``player_id``.

    Returns an empty (``found=false``) bag for non-owners or when the bag hasn't been synced yet.
    Clubs missing a valid integer ``id``/``clubTypeId`` are dropped so the client always decodes.
    """
    if player_id != owner_id:
        return _empty()
    raw = load_club_bag()
    if not raw:
        return _empty()

    clubs: list[dict[str, Any]] = []
    for club in raw.get("clubs") or []:
        if not isinstance(club, dict):
            continue
        club_id = club.get("id")
        type_id = club.get("clubTypeId")
        if not isinstance(club_id, int) or not isinstance(type_id, int):
            continue
        clubs.append(
            {
                "id": club_id,
                "clubTypeId": type_id,
                "customName": club.get("customName"),
                "typeName": club.get("typeName"),
                "loftAngle": club.get("loftAngle"),
                "retired": bool(club.get("retired")),
                "deleted": bool(club.get("deleted")),
            }
        )

    return {
        "schema": SCHEMA,
        "found": bool(clubs),
        "playerProfileId": raw.get("playerProfileId"),
        "clubs": clubs,
    }
