"""Serve the player's real Garmin club bag (``data/club_bag.json``) to the mobile app.

The bag is fetched by ``fetch.fetch_clubs`` during sync (Garmin ``/club/player`` + ``/club/types``)
and is owner-global — only the owner syncs clubs, so other players have no bag. The display name is
resolved to Chinese on the client (iOS owns the catalog), so this layer stays language-neutral.
"""

from __future__ import annotations

from typing import Any, Callable, Iterable, TypeVar

from ai_caddie.data import load_club_bag

SCHEMA = "ai-caddie-club-bag-v1"

# Garmin clubTypeId (1..23, authoritative — see [[garmin-club-endpoints]]) → a canonical token used
# only to intersect the real bag with the free-form club names in shot history. NOT a display name.
_CLUBTYPE_CANON: dict[int, str] = {
    1: "driver", 2: "wood3", 3: "wood5",
    4: "hybrid1", 5: "hybrid2", 6: "hybrid3", 7: "hybrid4", 8: "hybrid5", 9: "hybrid6",
    10: "iron1", 11: "iron2", 12: "iron3", 13: "iron4", 14: "iron5", 15: "iron6", 16: "iron7",
    17: "iron8", 18: "iron9",
    19: "pw", 20: "gw", 21: "sw", 22: "lw", 23: "putter",
}

_CN_NUM = {"一": "1", "二": "2", "三": "3", "四": "4", "五": "5", "六": "6", "七": "7", "八": "8", "九": "9"}


def _first_digit(text: str) -> str | None:
    for ch in text:
        if ch.isdigit():
            return ch
        if ch in _CN_NUM:
            return _CN_NUM[ch]
    return None


def canonical_club_name(raw: str | None) -> str | None:
    """Normalize a free-form club name ("3W", "5 Iron", "二号小鸡腿", "Pw", "50", "A杆") to a canonical
    token (driver/wood3/iron5/hybrid2/pw/gw/sw/lw/wedge50/putter), or None if unrecognized. Mirrors
    the iOS ``zhClubName`` taxonomy so backend filtering and on-device display agree."""
    if not raw:
        return None
    s = str(raw).strip()
    if not s:
        return None
    lower = s.lower()

    # Degree wedge: "50" / "54°" / "58 度".
    bare = s.replace("°", "").replace("度", "").strip()
    if bare.isdigit():
        deg = int(bare)
        if 44 <= deg <= 64:
            return f"wedge{deg}"
    # Driver (before the fairway-wood rule so "1W" → driver).
    if lower in ("driver", "d", "1w"):
        return "driver"
    # Hybrid / 小鸡腿 / rescue.
    if "小鸡腿" in s or "hybrid" in lower or "rescue" in lower:
        n = _first_digit(s)
        return f"hybrid{n}" if n else "hybrid"
    # Fairway wood: "3W" / "3 Wood" / "3号木".
    if (lower.endswith("w") and lower[:-1].isdigit()) or "号木" in s or "wood" in lower:
        n = _first_digit(s)
        return f"wood{n}" if n else None
    # Iron: "5I" / "5 Iron" / "五号铁".
    if (lower.endswith("i") and lower[:-1].isdigit()) or "号铁" in s or "iron" in lower:
        n = _first_digit(s)
        return f"iron{n}" if n else None
    # Letter wedges (gap/approach merge to gw) + putter.
    if lower in ("pw", "p", "pwedge", "p杆", "p 杆", "pitching wedge", "pitchingwedge"):
        return "pw"
    if lower in ("gw", "aw", "a", "ap", "gap", "a杆", "a 杆", "gap wedge", "approach wedge"):
        return "gw"
    if lower in ("sw", "s", "sand", "s杆", "s 杆", "sand wedge"):
        return "sw"
    if lower in ("lw", "l", "lob", "l杆", "l 杆", "lob wedge"):
        return "lw"
    if lower in ("putter", "putt", "pt", "推杆"):
        return "putter"
    return None


def in_use_canonical_names() -> set[str] | None:
    """Canonical tokens for the player's IN-USE clubs (not retired/deleted), or None when no bag has
    been synced. Each club contributes both its clubTypeId token AND its custom-name token, so a
    history entry written either way (e.g. "GW" vs "50°") still matches the same bag club."""
    raw = load_club_bag()
    if not raw:
        return None
    names: set[str] = set()
    for club in raw.get("clubs") or []:
        if not isinstance(club, dict) or club.get("retired") or club.get("deleted"):
            continue
        type_id = club.get("clubTypeId")
        if isinstance(type_id, int):
            token = _CLUBTYPE_CANON.get(type_id)
            if token:
                names.add(token)
        token = canonical_club_name(club.get("customName"))
        if token:
            names.add(token)
    return names or None


_T = TypeVar("_T")


def restrict_to_bag(items: Iterable[_T], name_of: Callable[[_T], str | None], *, min_keep: int = 2) -> list[_T]:
    """Keep only items whose club name is in the player's in-use bag. Falls back to the full list when
    no bag is known OR filtering would leave fewer than ``min_keep`` clubs — so the caddie always has
    options even if the player's bag and shot-history names don't line up."""
    items = list(items)
    bag = in_use_canonical_names()
    if not bag:
        return items
    kept = [it for it in items if canonical_club_name(name_of(it)) in bag]
    return kept if len(kept) >= min_keep else items


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
