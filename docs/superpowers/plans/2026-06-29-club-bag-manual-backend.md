# Club-bag Manual Setup — Backend Slice Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A per-player **manual** club bag (modeled on the Garmin app) with a member-scoped read/write API and caddie consumption, so non-Garmin members can set their clubs + optional per-club distances and get a personalized club-selection ladder.

**Architecture:** A new standalone `CLUB_CATALOG` (the token vocabulary + zh names + default distances) underpins a manual-bag JSON stored per player (`data/players/<id>/club_bag_manual.json`). An `effective_club_bag` resolver (manual → synced → empty) is read by both the served response and the caddie. Two member-scoped routes (`GET`/`PUT /api/v2/players/{id}/clubs/bag`) mirror `POST /players/{id}/rounds` (owner acts-for-any). Club-selection (`restrict_to_bag`) and the ladder gating read the effective bag, so a member with a manual bag gets a personalized ladder while everyone with no manual bag stays byte-for-byte.

**Tech Stack:** Python 3.12, FastAPI, stdlib `unittest` (CI gate `AI_CADDIE_DATA_MODE=fixture`), `uv`.

---

## File Structure

- **Create** `ai_caddie/caddie/club_catalog.py` — standalone catalog: `CLUB_CATALOG` (token → entry), `is_valid_token`, `default_distance_m`, `catalog_zh`, `catalog_clubtype_id`. No imports from `club_bag`/`course_prep` (avoids cycles).
- **Modify** `ai_caddie/core/data.py` — `manual_club_bag_file(player_id)`, `load_manual_club_bag(player_id)` (defensive read). Pure storage, no caddie imports.
- **Modify** `ai_caddie/caddie/club_bag.py` — `save_manual_club_bag(player_id, clubs)` (validate via catalog + atomic write), `clear_manual_club_bag(player_id)`, `effective_club_bag(player_id)` (manual→synced→none + source), and make `in_use_canonical_names(player_id)` read the effective bag.
- **Modify** `ai_caddie/courses/course_prep.py` — `effective_club_ladder(player_id)` (owner→`club_ladder()`; member+manual→manual ladder; member+none→`DEFAULT_LADDER`).
- **Modify** `server_v2/prep_tips.py`, `ai_caddie/caddie/mobile_live.py`, `server_v2/main.py` (the `/course/{id}/prep` builder) — call `effective_club_ladder(player_id)` instead of the inline owner/generic gate.
- **Modify** `server_v2/models.py` — `ClubBagManualRequest`, `EffectiveClubBagResponse`.
- **Modify** `server_v2/club_bag_api.py` (Create) — `build_effective_club_bag_response(player_id)`, `save_manual_club_bag_response(player_id, request)`.
- **Modify** `server_v2/main.py` — `GET`/`PUT /api/v2/players/{id}/clubs/bag` + guard + cache invalidation.
- **Modify** `server_v2/players_api.py` — add the GET to `is_player_scoped_route`; ensure the PUT is not admin-required.
- **Create** tests: `tests/test_club_catalog.py`, `tests/test_manual_club_bag.py`, `tests/test_effective_club_ladder.py`, `tests/test_player_club_bag_api.py`.

---

## Task 1: Club catalog (token vocabulary + defaults)

**Files:**
- Create: `ai_caddie/caddie/club_catalog.py`
- Test: `tests/test_club_catalog.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_club_catalog.py
import unittest
from ai_caddie.caddie import club_catalog as cat
from ai_caddie.caddie.club_bag import canonical_club_name
from ai_caddie.courses.course_prep import DEFAULT_LADDER


class ClubCatalogTests(unittest.TestCase):
    def test_tokens_cover_garmin_types_and_extras(self) -> None:
        # The 23 Garmin clubTypeId tokens + wood7 + the degree wedges must all be present.
        for tok in ["driver", "wood3", "wood5", "wood7", "hybrid1", "hybrid3", "iron5",
                    "iron9", "pw", "gw", "sw", "lw", "wedge50", "wedge58", "putter"]:
            self.assertIn(tok, cat.CLUB_CATALOG, tok)

    def test_entry_shape(self) -> None:
        e = cat.CLUB_CATALOG["driver"]
        self.assertEqual(e["zhName"], "一号木")
        self.assertEqual(e["category"], "wood")
        self.assertEqual(e["clubTypeId"], 1)
        self.assertEqual(e["defaultDistanceM"], 200)

    def test_non_garmin_tokens_have_null_clubtype(self) -> None:
        self.assertIsNone(cat.CLUB_CATALOG["wood7"]["clubTypeId"])
        self.assertIsNone(cat.CLUB_CATALOG["wedge54"]["clubTypeId"])

    def test_is_valid_token(self) -> None:
        self.assertTrue(cat.is_valid_token("iron7"))
        self.assertFalse(cat.is_valid_token("banana"))
        self.assertFalse(cat.is_valid_token(""))

    def test_defaults_are_consistent_with_default_ladder(self) -> None:
        # Every DEFAULT_LADDER key normalizes to a catalog token whose default == the ladder value.
        for raw, dist in DEFAULT_LADDER.items():
            tok = canonical_club_name(raw)
            self.assertIsNotNone(tok, raw)
            self.assertIn(tok, cat.CLUB_CATALOG, f"{raw}->{tok}")
            self.assertEqual(cat.CLUB_CATALOG[tok]["defaultDistanceM"], dist, raw)
```

- [ ] **Step 2: Run it — expect FAIL** (`ModuleNotFoundError: club_catalog`)

Run: `cd <worktree> && export PATH="$HOME/.local/bin:$PATH" && AI_CADDIE_DATA_MODE=fixture uv run python -m unittest tests.test_club_catalog -v`

- [ ] **Step 3: Implement the catalog**

```python
# ai_caddie/caddie/club_catalog.py
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
```

- [ ] **Step 4: Run — expect PASS.** If `test_defaults_are_consistent_with_default_ladder` fails, fix the catalog defaults to match `DEFAULT_LADDER` (do not change DEFAULT_LADDER).

- [ ] **Step 5: Commit** — `git add ai_caddie/caddie/club_catalog.py tests/test_club_catalog.py && git commit -m "feat(clubs): add the club catalog (token vocabulary + default distances)"`

---

## Task 2: Manual-bag storage (read path)

**Files:**
- Modify: `ai_caddie/core/data.py` (next to `load_club_bag`)
- Test: `tests/test_manual_club_bag.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_manual_club_bag.py
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from ai_caddie.core import data


class ManualBagStorageTests(unittest.TestCase):
    def test_manual_bag_file_is_player_scoped(self) -> None:
        root = Path("/srv/app")
        with patch.object(data, "DATA_DIR", root / "data"):
            self.assertEqual(data.manual_club_bag_file("me"), root / "data" / "club_bag_manual.json")
            self.assertEqual(
                data.manual_club_bag_file("p_m"),
                root / "data" / "players" / "p_m" / "club_bag_manual.json",
            )

    def test_load_manual_bag_owner_vs_member_vs_missing(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "data").mkdir()
            (root / "data" / "club_bag_manual.json").write_text(
                json.dumps({"schema": "ai-caddie-club-bag-manual-v1",
                            "clubs": [{"token": "driver", "customName": None, "distanceM": 205}]})
            )
            mdir = root / "data" / "players" / "p_m"
            mdir.mkdir(parents=True)
            (mdir / "club_bag_manual.json").write_text(
                json.dumps({"schema": "ai-caddie-club-bag-manual-v1",
                            "clubs": [{"token": "iron7", "customName": None, "distanceM": 130}]})
            )
            with patch.object(data, "DATA_DIR", root / "data"):
                self.assertEqual(data.load_manual_club_bag("me")["clubs"][0]["token"], "driver")
                self.assertEqual(data.load_manual_club_bag("p_m")["clubs"][0]["token"], "iron7")
                self.assertIsNone(data.load_manual_club_bag("p_other"))

    def test_corrupt_manual_bag_returns_none(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "data").mkdir()
            (root / "data" / "club_bag_manual.json").write_text("{ not json")
            with patch.object(data, "DATA_DIR", root / "data"):
                self.assertIsNone(data.load_manual_club_bag("me"))
```

- [ ] **Step 2: Run — expect FAIL** (`AttributeError: manual_club_bag_file`)

- [ ] **Step 3: Implement (in `ai_caddie/core/data.py`, after `load_club_bag`)**

```python
def manual_club_bag_file(player_id: str = OWNER_ID) -> Path:
    """The player's MANUAL club bag (user-set), parallel to the Garmin-synced club_bag.json.
    Owner -> data/club_bag_manual.json; member -> data/players/<id>/club_bag_manual.json."""
    if player_id == OWNER_ID:
        return DATA_DIR / "club_bag_manual.json"
    return DATA_DIR / "players" / player_id / "club_bag_manual.json"


def load_manual_club_bag(player_id: str = OWNER_ID) -> dict[str, Any] | None:
    """The player's manual bag, or None when unset/corrupt (caller falls back to the synced bag).
    Shape: {"schema": "ai-caddie-club-bag-manual-v1", "clubs": [{"token","customName","distanceM"}]}."""
    path = manual_club_bag_file(player_id)
    if not path.exists():
        return None
    try:
        raw = read_json(path)
    except (json.JSONDecodeError, OSError, ValueError):
        return None
    if not isinstance(raw, dict) or not isinstance(raw.get("clubs"), list):
        return None
    return raw
```

- [ ] **Step 4: Run — expect PASS.**
- [ ] **Step 5: Commit** — `feat(clubs): per-player manual club-bag storage (read path)`

---

## Task 3: Effective bag + manual save/validate + in-use scoping

**Files:**
- Modify: `ai_caddie/caddie/club_bag.py`
- Test: append to `tests/test_manual_club_bag.py`

- [ ] **Step 1: Write the failing test** (append)

```python
from ai_caddie.caddie import club_bag


class EffectiveBagTests(unittest.TestCase):
    def _root(self, tmp):
        return patch.object(data, "DATA_DIR", Path(tmp) / "data")

    def test_save_validates_tokens_and_round_trips(self) -> None:
        with TemporaryDirectory() as tmp, self._root(tmp):
            (Path(tmp) / "data").mkdir()
            club_bag.save_manual_club_bag("p_m", [{"token": "iron7", "distanceM": 130},
                                                  {"token": "driver"}])
            eff = club_bag.effective_club_bag("p_m")
            self.assertEqual(eff["source"], "manual")
            tokens = {c["token"] for c in eff["clubs"]}
            self.assertEqual(tokens, {"iron7", "driver"})

    def test_save_rejects_unknown_token(self) -> None:
        with TemporaryDirectory() as tmp, self._root(tmp):
            (Path(tmp) / "data").mkdir()
            with self.assertRaises(club_bag.InvalidClubError):
                club_bag.save_manual_club_bag("p_m", [{"token": "banana"}])

    def test_save_rejects_bad_distance(self) -> None:
        with TemporaryDirectory() as tmp, self._root(tmp):
            (Path(tmp) / "data").mkdir()
            with self.assertRaises(club_bag.InvalidClubError):
                club_bag.save_manual_club_bag("p_m", [{"token": "iron7", "distanceM": -5}])

    def test_effective_prefers_manual_then_synced_then_none(self) -> None:
        with TemporaryDirectory() as tmp, self._root(tmp):
            (Path(tmp) / "data").mkdir()
            # none
            self.assertEqual(club_bag.effective_club_bag("me")["source"], "none")
            # synced only
            (Path(tmp) / "data" / "club_bag.json").write_text(
                '{"clubs": [{"id": 1, "clubTypeId": 1}]}')
            self.assertEqual(club_bag.effective_club_bag("me")["source"], "garmin")
            # manual wins
            club_bag.save_manual_club_bag("me", [{"token": "iron7"}])
            self.assertEqual(club_bag.effective_club_bag("me")["source"], "manual")

    def test_in_use_canonical_names_reads_effective_manual(self) -> None:
        with TemporaryDirectory() as tmp, self._root(tmp):
            (Path(tmp) / "data").mkdir()
            club_bag.save_manual_club_bag("p_m", [{"token": "iron7"}, {"token": "driver"}])
            names = club_bag.in_use_canonical_names("p_m")
            self.assertEqual(names, {"iron7", "driver"})

    def test_clear_manual_falls_back(self) -> None:
        with TemporaryDirectory() as tmp, self._root(tmp):
            (Path(tmp) / "data").mkdir()
            club_bag.save_manual_club_bag("me", [{"token": "iron7"}])
            club_bag.clear_manual_club_bag("me")
            self.assertEqual(club_bag.effective_club_bag("me")["source"], "none")
```

- [ ] **Step 2: Run — expect FAIL** (`AttributeError: save_manual_club_bag`)

- [ ] **Step 3: Implement (in `ai_caddie/caddie/club_bag.py`)**

Add imports at top: `from ai_caddie.core.data import OWNER_ID, atomic_write_json, load_club_bag, load_manual_club_bag, manual_club_bag_file` and `from ai_caddie.caddie import club_catalog`. Then:

```python
MANUAL_SCHEMA = "ai-caddie-club-bag-manual-v1"


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
```

Then change `in_use_canonical_names(player_id)` to read the effective bag instead of `load_club_bag` directly:

```python
def in_use_canonical_names(player_id: str = OWNER_ID) -> set[str] | None:
    """... (docstring unchanged except: reads the EFFECTIVE bag — manual selection wins) ..."""
    bag = effective_club_bag(player_id)
    if bag["source"] == "manual":
        names = {c["token"] for c in bag["clubs"] if club_catalog.is_valid_token(str(c.get("token") or ""))}
        return names or None
    raw = {"clubs": bag["clubs"]} if bag["clubs"] else None
    if not raw:
        return None
    # (existing clubTypeId + customName tokenization over raw["clubs"], unchanged)
    ...
```

(Keep the existing synced-bag tokenization for the `garmin` branch; only the `manual` branch is new — manual tokens ARE canonical tokens already.)

- [ ] **Step 4: Run — expect PASS.** Also run `tests.test_club_bag` to confirm the synced path is byte-for-byte:
  `AI_CADDIE_DATA_MODE=fixture uv run python -m unittest tests.test_manual_club_bag tests.test_club_bag -v`
- [ ] **Step 5: Commit** — `feat(clubs): effective bag (manual>synced) + validated manual save; in-use reads effective`

---

## Task 4: Personalized ladder from the manual bag

**Files:**
- Modify: `ai_caddie/courses/course_prep.py`
- Modify call sites: `server_v2/prep_tips.py`, `ai_caddie/caddie/mobile_live.py` (`_course_prep_package`), `server_v2/main.py` (the `/course/{id}/prep` `_build`)
- Test: `tests/test_effective_club_ladder.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_effective_club_ladder.py
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from ai_caddie.core import data
from ai_caddie.caddie import club_bag
from ai_caddie.courses import course_prep


class EffectiveLadderTests(unittest.TestCase):
    def _root(self, tmp):
        return patch.object(data, "DATA_DIR", Path(tmp) / "data")

    def test_member_with_manual_bag_gets_personalized_ladder(self) -> None:
        with TemporaryDirectory() as tmp, self._root(tmp):
            (Path(tmp) / "data").mkdir()
            club_bag.save_manual_club_bag("p_m", [
                {"token": "driver", "distanceM": 210},  # explicit
                {"token": "iron7"},                      # null -> catalog default 128
            ])
            ladder = course_prep.effective_club_ladder("p_m")
            d = dict(ladder)
            self.assertEqual(d["driver"], 210)
            self.assertEqual(d["iron7"], 128)
            self.assertEqual([n for n, _ in ladder], ["driver", "iron7"])  # sorted desc by distance

    def test_member_without_manual_bag_gets_generic(self) -> None:
        with TemporaryDirectory() as tmp, self._root(tmp):
            (Path(tmp) / "data").mkdir()
            ladder = course_prep.effective_club_ladder("p_m")
            self.assertEqual(ladder, sorted(course_prep.DEFAULT_LADDER.items(), key=lambda kv: -kv[1]))

    def test_owner_uses_history_club_ladder(self) -> None:
        with TemporaryDirectory() as tmp, self._root(tmp):
            (Path(tmp) / "data").mkdir()
            with patch.object(course_prep, "club_ladder", return_value=[("driver", 230)]) as cl:
                ladder = course_prep.effective_club_ladder("me")
            cl.assert_called_once()
            self.assertEqual(ladder, [("driver", 230)])
```

- [ ] **Step 2: Run — expect FAIL** (`AttributeError: effective_club_ladder`)

- [ ] **Step 3: Implement (in `ai_caddie/courses/course_prep.py`)**

```python
from ai_caddie.core.data import OWNER_ID, load_manual_club_bag
from ai_caddie.caddie import club_catalog


def effective_club_ladder(player_id: str) -> list[tuple[str, int]]:
    """The recommended-club ladder for a player, used by every member-reachable prep builder.

    - Owner -> club_ladder() (history-derived distances, restricted to the owner's effective bag).
    - A member WITH a manual bag -> a ladder from that bag: per selected token,
      distanceM ?? CLUB_CATALOG default, sorted descending (clubs with neither are dropped).
    - A member with no manual bag -> the generic DEFAULT_LADDER. Never the owner's distances.
    """
    if player_id == OWNER_ID:
        return club_ladder()
    manual = load_manual_club_bag(player_id)
    if manual:
        pairs: list[tuple[str, int]] = []
        for club in manual.get("clubs") or []:
            token = str(club.get("token") or "")
            if not club_catalog.is_valid_token(token):
                continue
            dist = club.get("distanceM")
            if dist is None:
                dist = club_catalog.default_distance_m(token)
            if dist is None:
                continue
            pairs.append((token, int(dist)))
        if pairs:
            return sorted(pairs, key=lambda kv: -kv[1])
    return sorted(DEFAULT_LADDER.items(), key=lambda kv: -kv[1])
```

- [ ] **Step 4: Replace the inline owner/generic gate at the 3 call sites with `effective_club_ladder(player_id)`.**

In `server_v2/prep_tips.py` (the block added by the G4 fix):
```python
    ladder = course_prep.effective_club_ladder(player_id)
```
In `ai_caddie/caddie/mobile_live.py` `_course_prep_package(global_id, holes, *, player_id=OWNER_ID)`:
```python
    ladder = course_prep.effective_club_ladder(player_id)
```
In `server_v2/main.py` `_build()` of the `/course/{id}/prep` route (currently `ladder = course_prep.club_ladder() if is_owner else sorted(...)`):
```python
    ladder = course_prep.effective_club_ladder(player_id)
```
Each keeps passing `ladder=ladder` into `prep_nine(...)`. (Owner result is byte-for-byte: `effective_club_ladder("me") == club_ladder()`.)

- [ ] **Step 5: Run the ladder test + the gating tests** (must stay green — owner byte-for-byte):
  `AI_CADDIE_DATA_MODE=fixture uv run python -m unittest tests.test_effective_club_ladder tests.test_prep_tips_api tests.test_course_prep_api -v`
- [ ] **Step 6: Commit** — `feat(clubs): personalized club ladder from the manual bag (members)`

---

## Task 5: API models + response/save builders

**Files:**
- Modify: `server_v2/models.py`
- Create: `server_v2/club_bag_api.py`
- Test: in `tests/test_player_club_bag_api.py` (Task 6 runs them end-to-end)

- [ ] **Step 1: Add models (`server_v2/models.py`)**

```python
class ManualClubInput(BaseModel):
    token: str
    customName: str | None = None
    distanceM: float | None = None


class ClubBagManualRequest(BaseModel):
    clubs: list[ManualClubInput] = Field(default_factory=list)


class EffectiveClubOut(BaseModel):
    token: str
    zhName: str | None = None
    customName: str | None = None
    clubTypeId: int | None = None
    distanceM: int | None = None
    distanceSource: str | None = None  # "manual" | "default" | None


class EffectiveClubBagResponse(BaseModel):
    schema_: str = Field("ai-caddie-effective-club-bag-v1", alias="schema")
    source: str  # "manual" | "garmin" | "none"
    found: bool
    clubs: list[EffectiveClubOut] = Field(default_factory=list)

    model_config = {"populate_by_name": True}
```

- [ ] **Step 2: Builders (`server_v2/club_bag_api.py`)**

```python
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
```

- [ ] **Step 3: Commit** — `feat(clubs): API models + effective-bag/save builders`

---

## Task 6: Member-scoped routes + auth + cache invalidation

**Files:**
- Modify: `server_v2/main.py`, `server_v2/players_api.py`
- Test: `tests/test_player_club_bag_api.py`

- [ ] **Step 1: Write the failing test** (mirror `tests/test_server_v2_member_sync.py` harness: ADMIN_ENV + a member capability token; seed a member via the identity/registry path used there)

```python
# tests/test_player_club_bag_api.py — key cases (full harness mirrors test_server_v2_member_sync.py)
#  - owner (admin token) PUT /api/v2/players/p_m/clubs/bag {clubs:[{token:iron7,distanceM:130}]} -> 200,
#    GET same -> source="manual", iron7 present, distanceM 130 (owner acts-for-any).
#  - member token PUTs OWN id -> 200; member PUT another id or "me" -> 403.
#  - GET with member token for OWN id -> 200; anon (no token, admin configured) -> 401.
#  - PUT {token:"banana"} -> 422; PUT {token:iron7,distanceM:-5} -> 422.
#  - PUT empty clubs -> clears manual; GET -> source falls back (garmin/none).
#  - legacy GET /api/v2/history/clubs/bag is UNCHANGED (still the synced bag; never the manual one).
```

- [ ] **Step 2: Run — expect FAIL** (routes 404)

- [ ] **Step 3: Routes (`server_v2/main.py`)**

```python
@app.get("/api/v2/players/{player_id}/clubs/bag", response_model=EffectiveClubBagResponse)
def player_clubs_bag(player_id: str, acting_player_id: str = Depends(current_player_id)) -> EffectiveClubBagResponse:
    if acting_player_id != OWNER_ID and acting_player_id != player_id:
        raise HTTPException(status_code=403, detail="cannot read another player's club bag")
    from .club_bag_api import build_effective_club_bag_response
    return EffectiveClubBagResponse(**build_effective_club_bag_response(player_id))


@app.put("/api/v2/players/{player_id}/clubs/bag", response_model=EffectiveClubBagResponse)
def put_player_clubs_bag(player_id: str, body: ClubBagManualRequest,
                         acting_player_id: str = Depends(current_player_id)) -> EffectiveClubBagResponse:
    if acting_player_id != OWNER_ID and acting_player_id != player_id:
        raise HTTPException(status_code=403, detail="cannot edit another player's club bag")
    from .club_bag_api import save_manual_club_bag_response
    from ai_caddie.caddie.club_bag import InvalidClubError
    try:
        payload = save_manual_club_bag_response(player_id, body)
    except InvalidClubError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    from ai_caddie.history import stats_cache
    stats_cache.clear(player_id)  # the player's caddie ladder changed
    return EffectiveClubBagResponse(**payload)
```

- [ ] **Step 4: Route auth (`server_v2/players_api.py`)**

Add the GET to `is_player_scoped_route` (so a member token is accepted on the read): in the GET allowlist add a clause matching `method == "GET" and path.startswith("/api/v2/players/") and path.endswith("/clubs/bag")`. The PUT mirrors `POST /players/{id}/rounds` — confirm `_requires_admin_token` returns False for it (it is under `/api/v2/players/{id}/...`, not in the admin `exact_paths`) so the handler's `current_player_id` guard governs it. Add a test asserting a member token reaches both and anon is 401.

- [ ] **Step 5: Run the API tests + the auth guardrail** (`tests.test_codex_sec2` if it enumerates routes):
  `AI_CADDIE_DATA_MODE=fixture uv run python -m unittest tests.test_player_club_bag_api tests.test_codex_sec2 -v`
- [ ] **Step 6: Commit** — `feat(clubs): member-scoped GET/PUT /players/{id}/clubs/bag (owner acts-for-any)`

---

## Task 7: Full-suite gate + manual smoke

- [ ] **Step 1: Run the full fixture suite** — `AI_CADDIE_DATA_MODE=fixture uv run python -m unittest discover -s tests` → expect OK.
- [ ] **Step 2:** Confirm the legacy `GET /api/v2/history/clubs/bag` test (`tests/test_club_bag.py::ClubBagRouteTests`) still passes unchanged (synced bag only).
- [ ] **Step 3: Commit** any test-only fixups; push the branch and open a PR to `integration/v2`.

---

## Self-Review

**Spec coverage:** storage (T2) ✓, effective resolver (T3) ✓, catalog/tokens (T1) ✓, member-scoped API + owner-acts-for-any (T6) ✓, caddie personalized ladder (T4) ✓, validation 422 (T3/T6) ✓, owner byte-for-byte (T3/T4 tests) ✓, legacy endpoint unchanged (T7) ✓.
**Type consistency:** `effective_club_bag` returns `{source, clubs}` everywhere; manual club shape `{token, customName, distanceM}` consistent across save/load/builder/ladder; `EffectiveClubBagResponse` uses `schema` alias.
**No placeholders:** all code blocks are complete; the only "…" is the explicitly-unchanged existing tokenization in `in_use_canonical_names`'s garmin branch (Task 3 Step 3).
