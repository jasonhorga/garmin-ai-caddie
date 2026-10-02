"""Serve the player's real Garmin club bag (``data/club_bag.json``) to the mobile app.

The bag is fetched by ``fetch.fetch_clubs`` during sync (Garmin ``/club/player`` + ``/club/types``)
and is owner-global — only the owner syncs clubs, so other players have no bag. The display name is
resolved to Chinese on the client (iOS owns the catalog), so this layer stays language-neutral.
"""

from __future__ import annotations

from typing import Any, Callable, Iterable, TypeVar

from ai_caddie.core.data import (
    OWNER_ID,
    atomic_write_json,
    load_club_bag,
    load_manual_club_bag,
    manual_club_bag_file,
)
from ai_caddie.caddie import club_catalog

SCHEMA = "ai-caddie-club-bag-v1"
MANUAL_SCHEMA = "ai-caddie-club-bag-manual-v1"

# Garmin clubTypeId (1..23, authoritative — see [[garmin-club-endpoints]]) → a canonical token used
# only to intersect the real bag with the free-form club names in shot history. NOT a display name.
_CLUBTYPE_CANON: dict[int, str] = {
    1: "driver", 2: "wood3", 3: "wood5",
    4: "hybrid1", 5: "hybrid2", 6: "hybrid3", 7: "hybrid4", 8: "hybrid5", 9: "hybrid6",
    10: "iron1", 11: "iron2", 12: "iron3", 13: "iron4", 14: "iron5", 15: "iron6", 16: "iron7",
    17: "iron8", 18: "iron9",
    19: "pw", 20: "gw", 21: "sw", 22: "lw", 23: "putter",
}


def garmin_distance_m(club: dict[str, Any]) -> tuple[int, str] | None:
    """Return Garmin's own usable normal distance, preferring advice over average.

    Historical `/club/player` payloads often contain zero for both fields; zero/non-numeric/outlier
    values are absence, never a reason to replace the player's AutoShot-derived model.
    """
    for key, source in (("adviceDistance", "garmin_advice"), ("averageDistance", "garmin_average")):
        value = club.get(key)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            continue
        if 5 <= float(value) <= 350:
            return round(float(value)), source
    return None

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
    if lower in ("driver", "d", "dr", "1d", "1w") or s in ("一号木", "一号木杆"):
        return "driver"
    # Hybrid / 铁木 / 小鸡腿 / rescue (incl. the "3H" shorthand, mirroring the "3W"/"5I" rules below so
    # every DEFAULT_LADDER key — which uses "3H" — normalizes to a catalog token).
    if "小鸡腿" in s or "铁木" in s or "hybrid" in lower or "rescue" in lower or (lower.endswith("h") and lower[:-1].isdigit()):
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


class InvalidClubError(ValueError):
    """A manual-bag club has an unknown token or an out-of-range distance."""


def save_manual_club_bag(player_id: str, clubs: list[dict]) -> dict:
    """Validate + persist a player's manual bag. Each club: {token, customName?, distanceM?}.
    Raises InvalidClubError on an unknown token or a distance outside (0, 400] m."""
    cleaned: list[dict] = []
    for club in clubs:
        token = str(club.get("token") or "")
        if not club_catalog.is_valid_token(token):
            raise InvalidClubError(f"unknown club token: {token!r}")
        distance = club.get("distanceM")
        if distance is not None:
            if not isinstance(distance, (int, float)) or not (0 < float(distance) <= 400):
                raise InvalidClubError(f"distanceM out of range for {token}: {distance!r}")
            distance = int(round(float(distance)))
        name = club.get("customName")
        cleaned.append({"token": token, "customName": (str(name) if name else None), "distanceM": distance})
    payload = {"schema": MANUAL_SCHEMA, "clubs": cleaned}
    atomic_write_json(manual_club_bag_file(player_id), payload)
    return payload


def clear_manual_club_bag(player_id: str) -> None:
    """Drop the manual bag so the effective bag falls back to the synced (Garmin) bag."""
    path = manual_club_bag_file(player_id)
    if path.exists():
        path.unlink()


def effective_club_bag(player_id: str = OWNER_ID) -> dict:
    """The bag the caddie + the served response use: manual if set, else synced, else empty.
    Returns {"source": "manual"|"garmin"|"none", "clubs": [...raw...]}."""
    manual = load_manual_club_bag(player_id)
    if manual:
        return {"source": "manual", "clubs": manual.get("clubs") or []}
    synced = load_club_bag(player_id)
    if synced:
        return {"source": "garmin", "clubs": synced.get("clubs") or []}
    return {"source": "none", "clubs": []}


def manual_carries_m(player_id: str = OWNER_ID) -> dict[str, float]:
    """Canonical token -> the carry (metres) the player typed in 球包, from the manual bag only.
    The putter has no carry; an unknown token or a missing distance is skipped."""
    bag = effective_club_bag(player_id)
    if bag["source"] != "manual":
        return {}
    carries: dict[str, float] = {}
    for club in bag["clubs"]:
        if not isinstance(club, dict):
            continue
        token = str(club.get("token") or "")
        distance = club.get("distanceM")
        if token == "putter" or not club_catalog.is_valid_token(token):
            continue
        if isinstance(distance, (int, float)) and float(distance) > 0:
            carries[token] = float(distance)
    return carries


def apply_manual_carries(profiles: Iterable[dict[str, Any]], *, player_id: str = OWNER_ID) -> list[dict[str, Any]]:
    """The effective-profile projection shared with iOS ``ClubBagStore.effectiveProfiles``: a typed
    carry replaces the history median and the history p10/p90 band moves with it, so the caddie, the
    map and the Watch use the distance the player set while keeping the measured spread. Aliases of
    one physical club ("Aw"/"GW") all move to the same carry. Idempotent: re-applying is a no-op."""
    carries = manual_carries_m(player_id)
    rows = [dict(row) for row in profiles if isinstance(row, dict)]
    roster = manual_roster_tokens(player_id)
    if not carries and roster is None:
        return rows
    covered: set[str] = set()
    for row in rows:
        token = canonical_club_name(row.get("clubName")) or ""
        covered.add(token)
        carry = carries.get(token)
        if carry is None:
            continue
        try:
            median = float(row.get("median_m") or 0)
        except (TypeError, ValueError):
            median = 0.0
        delta = carry - median if median > 0 else 0.0
        for key in ("p10_m", "p90_m"):
            try:
                value = float(row.get(key) or 0)
            except (TypeError, ValueError):
                value = 0.0
            row[key] = round(max(1.0, value + delta), 1) if median > 0 and value > 0 else carry
        row["median_m"] = carry
    # Every selected club reaches the caddie (iOS adds the same zero-sample rows): a typed carry
    # first, else the catalog default for a club with no shot history. A club with neither (no
    # catalog default, e.g. a 7 wood) cannot be given an invented distance and stays out.
    for token in [*carries, *sorted(roster or ())]:
        if token in covered or token == "putter":
            continue
        carry = carries.get(token)
        if carry is None:
            default = club_catalog.default_distance_m(token)
            carry = float(default) if default else None
        if carry is None:
            continue
        covered.add(token)
        rows.append({
            "clubName": manual_profile_name(token),
            "sampleSize": 0,
            "median_m": carry,
            "p10_m": carry,
            "p90_m": carry,
        })
    return rows


def manual_roster_tokens(player_id: str = OWNER_ID) -> set[str] | None:
    """The canonical tokens of a manual roster (``set()`` for an explicit empty one), or None when
    the player has no manual bag."""
    bag = effective_club_bag(player_id)
    if bag["source"] != "manual":
        return None
    return {
        str(club.get("token"))
        for club in bag["clubs"]
        if isinstance(club, dict) and club_catalog.is_valid_token(str(club.get("token") or ""))
    }


def manual_profile_name(token: str) -> str:
    """A profile name both normalizers resolve to ``token``: the server's ``canonical_club_name``
    and iOS ``zhClubName`` ("iron7" -> 七号铁, "50" -> 50° 挖起杆)."""
    if token.startswith("wedge") and token[5:].isdigit():
        return token[5:]
    return token


def in_use_canonical_names(player_id: str = OWNER_ID) -> set[str] | None:
    """Canonical tokens for ``player_id``'s IN-USE clubs (not retired/deleted), or None when that
    player has no bag. Reads the EFFECTIVE bag (manual selection wins, else the synced Garmin bag) —
    only that player's data (never the owner's, for a member). A recognised Garmin custom name is
    the player's factual club identity and therefore wins over the generic clubTypeId. Adding both
    identities made one physical club appear twice (for example ``3W`` + ``三号木杆`` or ``GW`` +
    ``50°``) and let two different distance models survive into recommendations. A manual bag's
    tokens are already canonical."""
    bag = effective_club_bag(player_id)
    if bag["source"] == "manual":
        names = {c["token"] for c in bag["clubs"] if club_catalog.is_valid_token(str(c.get("token") or ""))}
        return names or None
    raw = {"clubs": bag["clubs"]} if bag["clubs"] else None
    if not raw:
        return None
    names: set[str] = set()
    for club in raw.get("clubs") or []:
        if not isinstance(club, dict) or club.get("retired") or club.get("deleted"):
            continue
        custom_token = canonical_club_name(club.get("customName"))
        if custom_token:
            names.add(custom_token)
            continue
        type_id = club.get("clubTypeId")
        if isinstance(type_id, int):
            type_token = _CLUBTYPE_CANON.get(type_id)
            if type_token:
                names.add(type_token)
    return names or None


_T = TypeVar("_T")


def restrict_to_bag(
    items: Iterable[_T], name_of: Callable[[_T], str | None], *, player_id: str = OWNER_ID, min_keep: int = 2
) -> list[_T]:
    """Keep only items whose club name is in ``player_id``'s in-use bag. Falls back to the full list
    when that player has no known bag OR filtering would leave fewer than ``min_keep`` clubs — so the
    caddie always has options. Scoped by ``player_id`` so a member-reachable caller (the mobile
    package) never filters by — and thus never leaks — the OWNER's bag."""
    items = list(items)
    bag = in_use_canonical_names(player_id)
    if not bag:
        return items
    kept = [it for it in items if canonical_club_name(name_of(it)) in bag]
    # A roster the player chose in 球包 is authoritative: a club taken out never comes back as a
    # "keep the caddie alive" fallback. Typed carries for the remaining clubs are added by
    # ``apply_manual_carries``; only the synced Garmin bag keeps the full-history fallback.
    if effective_club_bag(player_id)["source"] == "manual":
        return kept
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
                "averageDistance": club.get("averageDistance"),
                "adviceDistance": club.get("adviceDistance"),
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
