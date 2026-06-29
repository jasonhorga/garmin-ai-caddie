"""The canonical club catalog: the token vocabulary a MANUAL club bag is built from.

Tokens are exactly the ones canonical_club_name() emits (so a manual bag plugs into the
existing in-use-bag intersection with no new normalization). Mirrors the iOS ClubCatalog +
the backend _CLUBTYPE_CANON, plus 7-wood and the degree wedges (which Garmin expresses as a
customName, not a clubTypeId). defaultDistanceM is the prefill carry distance in metres,
taken from course_prep.DEFAULT_LADDER for the 13 clubs it covers (asserted by a test), None
elsewhere (the UI then asks the user to enter it).
"""
from __future__ import annotations

from typing import Any

# token -> (zhName, category, clubTypeId|None, defaultDistanceM|None). Defaults are the
# DEFAULT_LADDER values (1W=200, 3W=171, 3H=159, 5I=146, 6I=132, 7I=128, 8I=122, 9I=114,
# PW=102, A杆/gw=84, 50°=53, 54°=52, 58°=42); a drift test pins them.
CLUB_CATALOG: dict[str, dict[str, Any]] = {
    "driver": {"zhName": "一号木", "category": "wood", "clubTypeId": 1, "defaultDistanceM": 200},
    "wood3": {"zhName": "三号木", "category": "wood", "clubTypeId": 2, "defaultDistanceM": 171},
    "wood5": {"zhName": "五号木", "category": "wood", "clubTypeId": 3, "defaultDistanceM": None},
    "wood7": {"zhName": "七号木", "category": "wood", "clubTypeId": None, "defaultDistanceM": None},
    "hybrid1": {"zhName": "一号小鸡腿", "category": "hybrid", "clubTypeId": 4, "defaultDistanceM": None},
    "hybrid2": {"zhName": "二号小鸡腿", "category": "hybrid", "clubTypeId": 5, "defaultDistanceM": None},
    "hybrid3": {"zhName": "三号小鸡腿", "category": "hybrid", "clubTypeId": 6, "defaultDistanceM": 159},
    "hybrid4": {"zhName": "四号小鸡腿", "category": "hybrid", "clubTypeId": 7, "defaultDistanceM": None},
    "hybrid5": {"zhName": "五号小鸡腿", "category": "hybrid", "clubTypeId": 8, "defaultDistanceM": None},
    "hybrid6": {"zhName": "六号小鸡腿", "category": "hybrid", "clubTypeId": 9, "defaultDistanceM": None},
    "iron1": {"zhName": "一号铁", "category": "iron", "clubTypeId": 10, "defaultDistanceM": None},
    "iron2": {"zhName": "二号铁", "category": "iron", "clubTypeId": 11, "defaultDistanceM": None},
    "iron3": {"zhName": "三号铁", "category": "iron", "clubTypeId": 12, "defaultDistanceM": None},
    "iron4": {"zhName": "四号铁", "category": "iron", "clubTypeId": 13, "defaultDistanceM": None},
    "iron5": {"zhName": "五号铁", "category": "iron", "clubTypeId": 14, "defaultDistanceM": 146},
    "iron6": {"zhName": "六号铁", "category": "iron", "clubTypeId": 15, "defaultDistanceM": 132},
    "iron7": {"zhName": "七号铁", "category": "iron", "clubTypeId": 16, "defaultDistanceM": 128},
    "iron8": {"zhName": "八号铁", "category": "iron", "clubTypeId": 17, "defaultDistanceM": 122},
    "iron9": {"zhName": "九号铁", "category": "iron", "clubTypeId": 18, "defaultDistanceM": 114},
    "pw": {"zhName": "P杆", "category": "wedge", "clubTypeId": 19, "defaultDistanceM": 102},
    "gw": {"zhName": "A杆", "category": "wedge", "clubTypeId": 20, "defaultDistanceM": 84},
    "sw": {"zhName": "S杆", "category": "wedge", "clubTypeId": 21, "defaultDistanceM": None},
    "lw": {"zhName": "L杆", "category": "wedge", "clubTypeId": 22, "defaultDistanceM": None},
    "wedge50": {"zhName": "50°", "category": "wedge", "clubTypeId": None, "defaultDistanceM": 53},
    "wedge52": {"zhName": "52°", "category": "wedge", "clubTypeId": None, "defaultDistanceM": None},
    "wedge54": {"zhName": "54°", "category": "wedge", "clubTypeId": None, "defaultDistanceM": 52},
    "wedge56": {"zhName": "56°", "category": "wedge", "clubTypeId": None, "defaultDistanceM": None},
    "wedge58": {"zhName": "58°", "category": "wedge", "clubTypeId": None, "defaultDistanceM": 42},
    "wedge60": {"zhName": "60°", "category": "wedge", "clubTypeId": None, "defaultDistanceM": None},
    "putter": {"zhName": "推杆", "category": "putter", "clubTypeId": 23, "defaultDistanceM": None},
}


def is_valid_token(token: str) -> bool:
    return bool(token) and token in CLUB_CATALOG


def default_distance_m(token: str) -> int | None:
    entry = CLUB_CATALOG.get(token)
    return entry["defaultDistanceM"] if entry else None


def catalog_zh(token: str) -> str | None:
    entry = CLUB_CATALOG.get(token)
    return entry["zhName"] if entry else None


def catalog_clubtype_id(token: str) -> int | None:
    entry = CLUB_CATALOG.get(token)
    return entry["clubTypeId"] if entry else None
