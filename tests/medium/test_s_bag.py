"""The club bag: a distance the player typed wins, Garmin distances are used only when plausible (test-plan S-10).

Bag files live in a temporary data directory (the production ``DATA_DIR`` / ``CLUBS_BAG_FILE``
seams); measured history for the caddie ladder is served through the history cache seam.
Reads and edits go through ``server_v2.main.app``; the ladder the caddie recommends from is read
with the public ``course_prep`` functions.
"""
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient

from ai_caddie.core import data as core_data
from ai_caddie.core.config import get_settings
from ai_caddie.courses import course_prep, prep_cache
from ai_caddie.history import stats_cache
from ai_caddie.history.history import HistoryData
from server_v2 import course_install
from server_v2 import main as server_main

BAG = "/api/v2/players/me/clubs/bag"
ACTIVE_ROUND_STATE = (
    (server_main, ("_ACTIVE_ROUNDS", "_ACTIVE_COURSES", "_ACTIVE_EVENT_TIMES", "_ACTIVE_START_TIMES",
                   "_ROUND_START_CACHE", "_ACTIVE_EVENT_DEVICES", "_ACTIVE_SELECTIONS")),
    (course_install, ("_CURRENT_COURSE_IDS",)),
)


def garmin_club(club_id, type_id, advice, average, **extra):
    return {"id": club_id, "clubTypeId": type_id, "customName": None, "typeName": None,
            "adviceDistance": advice, "averageDistance": average, **extra}


# Garmin's synced bag: driver with an advice distance, seven-iron with only an average, a pitching
# wedge where Garmin has nothing (both zero). clubTypeIds 1/16/19 are driver/iron7/pw.
GARMIN_BAG = {"clubs": [garmin_club(1, 1, 230, 225), garmin_club(2, 16, 0, 150), garmin_club(3, 19, 0, 0)]}


def measured_history():
    # Logged shots: driver 200/210/220, seven-iron 130/140/150, wedge 90/100/110 -> medians 210, 140, 100.
    shots = [{"type": "APPROACH", "club": club, "distance": metres}
             for club, values in (("Driver", (200, 210, 220)), ("7I", (130, 140, 150)), ("PW", (90, 100, 110)))
             for metres in values]
    return HistoryData(raw_rounds=[], rounds=[], shots=shots, corrected=True)


def by_token(bag):
    return {club["token"]: (club["distanceM"], club["distanceSource"]) for club in bag["clubs"]}


class Bag(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(dir=os.environ.get("TMPDIR"))
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        patches = [
            mock.patch.dict(os.environ, {"AI_CADDIE_DATA_MODE": "fixture", "AI_CADDIE_ADMIN_TOKEN": "",
                                         "AI_CADDIE_SECURITY_PROFILE": ""}),
            mock.patch.object(core_data, "DATA_DIR", self.root),
            mock.patch.object(core_data, "CLUBS_BAG_FILE", self.root / "club_bag.json"),
            mock.patch.object(stats_cache, "cached_load_history_data", side_effect=lambda *a, **kw: measured_history()),
            mock.patch.object(server_main, "_ACTIVE_PACKAGED_ROUNDS", set()),
            *(mock.patch.dict(getattr(module, name), clear=True)
              for module, names in ACTIVE_ROUND_STATE for name in names),
        ]
        for target in patches:
            target.start()
            self.addCleanup(target.stop)
        for clear in (get_settings.cache_clear, stats_cache.clear, prep_cache.clear):
            clear()
            self.addCleanup(clear)
        self.client = TestClient(server_main.app)
        self.addCleanup(self.client.close)

    def sync_garmin(self, bag):
        (self.root / "club_bag.json").write_text(json.dumps(bag), encoding="utf-8")

    def get_bag(self):
        response = self.client.get(BAG)
        self.assertEqual(response.status_code, 200, response.text[:300])
        return response.json()

    def put_bag(self, clubs, status=200):
        response = self.client.put(BAG, json={"clubs": clubs})
        self.assertEqual(response.status_code, status, response.text[:300])
        return response.json()

    def ladder(self):
        rows = course_prep.club_ladder_with_provenance("me", ladder=course_prep.effective_club_ladder("me"))
        return {row["token"]: (row["m"], row["distanceSource"]) for row in rows}

    def test_manual_overrides_garmin(self):
        """S-10 [main]: a distance typed in the bag replaces Garmin's and history's for the bag and the caddie ladder."""
        self.sync_garmin(GARMIN_BAG)
        before = self.get_bag()
        self.assertEqual(before["source"], "garmin")
        self.assertEqual(by_token(before), {"driver": (230, "garmin_advice"),    # advice wins over the 225 average
                                            "iron7": (150, "garmin_average"),    # no advice (0) -> average
                                            "pw": (None, None)})                 # Garmin has nothing usable
        # Caddie ladder before any typing: Garmin's plausible values, else the logged median (PW 100).
        self.assertEqual(self.ladder(), {"driver": (230, "garmin_advice"), "iron7": (150, "garmin_average"),
                                         "pw": (100, "history_median")})

        typed = self.put_bag([{"token": "driver", "distanceM": 205},
                              {"token": "iron7"},                                    # chosen, no distance typed
                              {"token": "pw", "customName": "Pitch", "distanceM": 95.4}])
        self.assertEqual(typed, self.get_bag())  # what the edit returns is what is stored
        self.assertEqual(typed["source"], "manual")
        self.assertEqual(by_token(typed), {"driver": (205, "manual"),
                                           "iron7": (128, "default"),   # catalog seven-iron default, shown as such
                                           "pw": (95, "manual")})        # 95.4 is stored as whole metres
        # The caddie uses the typed 205 and 95 over Garmin's 230 and history's 100; the untyped seven-iron
        # keeps its measured 150 rather than the catalog default.
        self.assertEqual(self.ladder(), {"driver": (205, "manual"), "iron7": (150, "garmin_average"),
                                         "pw": (95, "manual")})

        reset = self.put_bag([])  # an empty roster means "go back to Garmin"
        self.assertEqual((reset["source"], by_token(reset)), ("garmin", by_token(before)))
        self.assertFalse((self.root / "club_bag_manual.json").exists())
        self.assertEqual(self.ladder()["driver"], (230, "garmin_advice"))

    def test_bad_edit_is_refused_and_keeps_the_bag(self):
        """S-10: an unknown club or a distance outside 0-400 m is refused and the saved bag stays as it was."""
        self.put_bag([{"token": "driver", "distanceM": 205}])
        rows = [
            # clubs sent, expected status
            ([{"token": "bogus"}], 422),
            ([{"token": "driver", "distanceM": 0}], 422),
            ([{"token": "driver", "distanceM": -5}], 422),
            ([{"token": "driver", "distanceM": 400.4}], 422),
            ([{"token": "driver", "distanceM": 401}], 422),
            ([{"token": "driver", "distanceM": 205}, {"token": "iron7", "distanceM": 500}], 422),  # one bad row
        ]
        for clubs, status in rows:
            with self.subTest(clubs=clubs):
                self.put_bag(clubs, status=status)
                self.assertEqual(by_token(self.get_bag()), {"driver": (205, "manual")})
        upper = self.put_bag([{"token": "driver", "distanceM": 400}])  # the 400 m ceiling itself is allowed
        self.assertEqual(by_token(upper), {"driver": (400, "manual")})

    def test_implausible_garmin_distances_are_absent(self):
        """S-10: Garmin distances outside 5-350 m or not numbers are shown as missing, not used."""
        clubs = [
            garmin_club(1, 1, 351, 0),      # driver: advice over the 350 m ceiling, no average
            garmin_club(2, 2, 0, 350),      # wood3: the ceiling itself
            garmin_club(3, 16, 4, 5),       # iron7: advice under the 5 m floor, average exactly 5
            garmin_club(4, 17, "120", 0),   # iron8: text is not a distance
            garmin_club(5, 18, 0, 0),       # iron9: nothing
        ]
        self.sync_garmin({"clubs": clubs})
        self.assertEqual(by_token(self.get_bag()), {"driver": (None, None), "wood3": (350, "garmin_average"),
                                                    "iron7": (5, "garmin_average"), "iron8": (None, None),
                                                    "iron9": (None, None)})

    def test_raw_garmin_bag_is_owner_shaped(self):
        """S-10: the synced Garmin bag is reported as missing before a sync and drops rows it cannot identify."""
        empty = self.client.get("/api/v2/history/clubs/bag").json()
        self.assertEqual((empty["found"], empty["clubs"]), (False, []))
        self.assertEqual(self.get_bag(), {"schema": "ai-caddie-effective-club-bag-v1", "source": "none",
                                          "found": False, "clubs": []})

        self.sync_garmin({"clubs": [*GARMIN_BAG["clubs"], {"id": "x", "clubTypeId": 19}, {"id": 9},
                                    garmin_club(4, 13, 180, 0, retired=True)]})
        raw = self.client.get("/api/v2/history/clubs/bag").json()
        # The string id and the row without clubTypeId are dropped; the retired four-iron is kept and marked.
        self.assertEqual([(club["id"], club["retired"]) for club in raw["clubs"]],
                         [(1, False), (2, False), (3, False), (4, True)])
        self.assertEqual((raw["clubs"][0]["adviceDistance"], raw["clubs"][1]["averageDistance"]), (230, 150))
