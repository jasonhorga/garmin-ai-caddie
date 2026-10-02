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


from ai_caddie.caddie import club_bag


class EffectiveBagTests(unittest.TestCase):
    def _root(self, tmp):
        # Patch CLUBS_BAG_FILE too: load_club_bag("me") reads the module-level CLUBS_BAG_FILE
        # (frozen at import from the original DATA_DIR), so the owner synced/none cases below need
        # it repointed at the temp tree — mirrors tests/test_club_bag.py's own patching.
        root = Path(tmp) / "data"
        return patch.multiple(data, DATA_DIR=root, CLUBS_BAG_FILE=root / "club_bag.json")

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

    def test_manual_carry_replaces_history_median_and_moves_the_band(self) -> None:
        profiles = [
            {"clubName": "7I", "sampleSize": 40, "median_m": 128.0, "p10_m": 118.0, "p90_m": 136.0},
            {"clubName": "7 Iron", "sampleSize": 3, "median_m": 120.0, "p10_m": 115.0, "p90_m": 125.0},
            {"clubName": "Driver", "sampleSize": 50, "median_m": 210.0, "p10_m": 190.0, "p90_m": 225.0},
        ]
        with TemporaryDirectory() as tmp, self._root(tmp):
            (Path(tmp) / "data").mkdir()
            # No manual bag: history is untouched.
            self.assertEqual(club_bag.apply_manual_carries(profiles, player_id="me"), profiles)
            club_bag.save_manual_club_bag(
                "me",
                [{"token": "iron7", "distanceM": 155}, {"token": "driver"}, {"token": "putter", "distanceM": 5}],
            )
            self.assertEqual(club_bag.manual_carries_m("me"), {"iron7": 155.0})
            rows = club_bag.apply_manual_carries(profiles, player_id="me")
            seven, alias, driver = rows
            self.assertEqual((seven["median_m"], seven["p10_m"], seven["p90_m"]), (155.0, 145.0, 163.0))
            # Every alias of the physical club moves to the same carry.
            self.assertEqual((alias["median_m"], alias["p10_m"], alias["p90_m"]), (155.0, 150.0, 160.0))
            self.assertEqual(driver, profiles[2])
            # Idempotent, and the input rows are not mutated.
            self.assertEqual(club_bag.apply_manual_carries(rows, player_id="me"), rows)
            self.assertEqual(profiles[0]["median_m"], 128.0)
            # Clearing the manual bag (PUT {"clubs": []}) restores history.
            club_bag.clear_manual_club_bag("me")
            self.assertEqual(club_bag.apply_manual_carries(profiles, player_id="me"), profiles)

    def test_a_manual_roster_is_authoritative_and_typed_clubs_without_history_are_kept(self) -> None:
        history = [
            {"clubName": "Driver", "sampleSize": 50, "median_m": 210.0, "p10_m": 190.0, "p90_m": 225.0},
            {"clubName": "7I", "sampleSize": 40, "median_m": 128.0, "p10_m": 118.0, "p90_m": 136.0},
            {"clubName": "5I", "sampleSize": 30, "median_m": 150.0, "p10_m": 140.0, "p90_m": 160.0},
        ]
        with TemporaryDirectory() as tmp, self._root(tmp):
            (Path(tmp) / "data").mkdir()
            club_bag.save_manual_club_bag(
                "me", [{"token": "iron7", "distanceM": 150}, {"token": "wedge58", "distanceM": 80}]
            )
            kept = club_bag.restrict_to_bag(history, lambda row: row["clubName"], player_id="me")
            # No "fewer than two clubs" fallback to the full history for a roster the player chose.
            self.assertEqual([row["clubName"] for row in kept], ["7I"])
            rows = club_bag.apply_manual_carries(kept, player_id="me")
            self.assertEqual([(r["clubName"], r["median_m"], r["sampleSize"]) for r in rows],
                             [("7I", 150.0, 40), ("58", 80.0, 0)])
            self.assertEqual(club_bag.canonical_club_name(rows[1]["clubName"]), "wedge58")
            # Total projection: a mixed roster keeps the history club and adds the catalog default
            # for the selected club that has neither history nor a typed carry (Codex 5947998710).
            club_bag.save_manual_club_bag("me", [{"token": "iron5"}, {"token": "iron7"}, {"token": "putter"}])
            no_seven = [row for row in history if row["clubName"] != "7I"]  # 7I: no shot history
            kept = club_bag.restrict_to_bag(no_seven, lambda row: row["clubName"], player_id="me")
            rows = club_bag.apply_manual_carries(kept, player_id="me")
            self.assertEqual([(r["clubName"], r["median_m"], r["sampleSize"]) for r in rows],
                             [("5I", 150.0, 30), ("iron7", 128.0, 0)])
            # A club with no catalog default and nothing measured cannot get an invented distance.
            club_bag.save_manual_club_bag("me", [{"token": "wood7"}])
            self.assertEqual(club_bag.apply_manual_carries([], player_id="me"), [])
            # Putter-only and explicit roster: no hitting rows at all.
            club_bag.save_manual_club_bag("me", [{"token": "putter"}])
            self.assertEqual(club_bag.manual_roster_tokens("me"), {"putter"})
            kept = club_bag.restrict_to_bag(history, lambda row: row["clubName"], player_id="me")
            self.assertEqual(club_bag.apply_manual_carries(kept, player_id="me"), [])
            club_bag.clear_manual_club_bag("me")
            self.assertIsNone(club_bag.manual_roster_tokens("me"))

    def test_every_catalog_token_round_trips_through_its_profile_name(self) -> None:
        from ai_caddie.caddie import club_catalog

        for token in club_catalog.CLUB_CATALOG:
            if token == "putter":
                continue
            self.assertEqual(club_bag.canonical_club_name(club_bag.manual_profile_name(token)), token)

    def test_fresh_package_profiles_and_seeds_follow_the_manual_roster(self) -> None:
        from ai_caddie.caddie import mobile_live
        from ai_caddie.core.fixtures import fixture_history_data
        from tests.round_loop_authority import fixture_course_authority

        authority = fixture_course_authority()
        authority.start()
        self.addCleanup(authority.stop)
        manual = {"schema": club_bag.MANUAL_SCHEMA, "clubs": [
            # The fixture history has a 5 iron (and a driver, 3 wood, 8 iron, 58°) but no 7 iron.
            {"token": "iron5", "customName": None, "distanceM": 150},
            {"token": "iron7", "customName": None, "distanceM": 140},
        ]}
        geometry = {"coverage": "ready", "hasHazards": True, "hasMeshes": True, "hazardCount": 0, "hazards": []}
        with patch.object(club_bag, "load_manual_club_bag", return_value=manual), patch.object(
            mobile_live, "_geometry_seed", return_value=(geometry, [], [])
        ), patch.object(
            mobile_live, "_route_evidence_seed",
            return_value=({"routeLength_m": 100.0, "avoidZones": [], "sourceRefs": ["live:1"]}, [], []),
        ):
            package = mobile_live.build_live_round_package(
                "900001", data=fixture_history_data(), data_mode="fixture",
                allow_weather_fetch=False, priority_holes=[1], defer_non_priority_enrichment=True,
            )
        tokens = {club_bag.canonical_club_name(p["clubName"]): p for p in package["clubProfiles"]}
        self.assertEqual(set(tokens), {"iron5", "iron7"}, "only the roster; Driver never comes back")
        self.assertEqual(tokens["iron5"]["median_m"], 150.0)
        self.assertGreater(tokens["iron5"]["sampleSize"], 0, "history stays attached")
        self.assertEqual((tokens["iron7"]["median_m"], tokens["iron7"]["sampleSize"]), (140.0, 0),
                         "a typed club with no history is in the package")
        seed = next(row for row in package["caddieContextSeeds"] if row["hole"] == 1)
        seed_profiles = seed["context"]["clubProfiles"]
        seed_rows = seed_profiles.values() if isinstance(seed_profiles, dict) else seed_profiles
        self.assertEqual({club_bag.canonical_club_name(r["clubName"]) for r in seed_rows}, {"iron5", "iron7"})
        for option in seed["offlineOptions"]:
            self.assertIn(club_bag.canonical_club_name(option["clubName"]), {"iron5", "iron7"})

        # A putter-only roster: no hitting profile, and never the placeholder 8I.
        putter_only = {"schema": club_bag.MANUAL_SCHEMA, "clubs": [{"token": "putter", "customName": None, "distanceM": None}]}
        with patch.object(club_bag, "load_manual_club_bag", return_value=putter_only), patch.object(
            mobile_live, "_geometry_seed", return_value=(geometry, [], [])
        ), patch.object(
            mobile_live, "_route_evidence_seed",
            return_value=({"routeLength_m": 100.0, "avoidZones": [], "sourceRefs": ["live:1"]}, [], []),
        ):
            package = mobile_live.build_live_round_package(
                "900001", data=fixture_history_data(), data_mode="fixture",
                allow_weather_fetch=False, priority_holes=[1], defer_non_priority_enrichment=True,
            )
        self.assertEqual(package["clubProfiles"], [])
        for seed in package["caddieContextSeeds"]:
            profiles = seed["context"].get("clubProfiles") or {}
            self.assertFalse(profiles, f"hole {seed['hole']} has no hitting club")
            self.assertEqual(seed["offlineOptions"], [])

    def test_fresh_package_profiles_apply_the_manual_carry(self) -> None:
        source = (Path(__file__).resolve().parents[1] / "ai_caddie" / "caddie" / "mobile_live.py").read_text()
        restrict = source.index("club_profiles = restrict_to_bag(club_profiles")
        project = source.index("club_profiles = apply_manual_carries(club_profiles, player_id=player_id)")
        seeds = source.index("caddie_profiles = _club_performance_profiles(club_profiles")
        self.assertLess(restrict, project)
        self.assertLess(project, seeds)


from ai_caddie.courses import course_prep
from server_v2.club_bag_api import build_effective_club_bag_response


class ManualBagRobustnessTests(unittest.TestCase):
    def _root(self, tmp):
        root = Path(tmp) / "data"
        return patch.multiple(data, DATA_DIR=root, CLUBS_BAG_FILE=root / "club_bag.json")

    def test_corrupt_entries_are_sanitized_not_crash(self) -> None:
        # A hand-corrupted manual file: non-numeric distanceM, non-string token, non-dict entry.
        # load_manual_club_bag must sanitize (drop/coerce) so a downstream int(distanceM) never 500s.
        with TemporaryDirectory() as tmp, self._root(tmp):
            (Path(tmp) / "data").mkdir()
            mdir = Path(tmp) / "data" / "players" / "p_m"
            mdir.mkdir(parents=True)
            (mdir / "club_bag_manual.json").write_text(json.dumps({
                "schema": "ai-caddie-club-bag-manual-v1",
                "clubs": [
                    {"token": "iron7", "distanceM": "abc"},  # non-numeric -> coerced to None
                    {"token": "driver", "distanceM": 200},   # ok
                    {"token": 123},                           # non-string token -> dropped
                    "not-a-dict",                             # dropped
                ],
            }))
            by = {c["token"]: c for c in data.load_manual_club_bag("p_m")["clubs"]}
            self.assertEqual(set(by), {"iron7", "driver"})
            self.assertIsNone(by["iron7"]["distanceM"])  # coerced, not crashed
            self.assertEqual(by["driver"]["distanceM"], 200)
            # The ladder builds without a 500 (iron7 falls back to its catalog default 128).
            ladder = dict(course_prep.effective_club_ladder("p_m"))
            self.assertEqual(ladder["iron7"], 128)
            self.assertEqual(ladder["driver"], 200)

    def test_non_finite_and_out_of_range_distance_dropped_not_crash(self) -> None:
        # json.loads accepts NaN/Infinity; they pass isinstance(float) and would crash int().
        # An out-of-range finite value (matches the save-time 0<d<=400 rule) is dropped too.
        with TemporaryDirectory() as tmp, self._root(tmp):
            (Path(tmp) / "data").mkdir()
            mdir = Path(tmp) / "data" / "players" / "p_m"
            mdir.mkdir(parents=True)
            (mdir / "club_bag_manual.json").write_text(
                '{"schema":"ai-caddie-club-bag-manual-v1","clubs":['
                '{"token":"iron7","distanceM":NaN},'
                '{"token":"driver","distanceM":Infinity},'
                '{"token":"wood3","distanceM":99999},'
                '{"token":"pw","distanceM":102}]}'
            )
            by = {c["token"]: c for c in data.load_manual_club_bag("p_m")["clubs"]}
            self.assertIsNone(by["iron7"]["distanceM"])   # NaN -> None
            self.assertIsNone(by["driver"]["distanceM"])  # Infinity -> None
            self.assertIsNone(by["wood3"]["distanceM"])   # out-of-range -> None
            self.assertEqual(by["pw"]["distanceM"], 102)  # valid kept
            # The ladder builds without a 500 (coerced clubs fall back to catalog defaults).
            ladder = dict(course_prep.effective_club_ladder("p_m"))
            self.assertEqual(ladder["iron7"], 128)   # catalog default
            self.assertEqual(ladder["driver"], 200)  # catalog default
            self.assertEqual(ladder["pw"], 102)      # user value

    def test_no_default_token_reports_null_distance_source(self) -> None:
        # wood7 has no catalog default; with no user distance it must report distanceM + source null
        # (NOT distanceSource="default"). iron7 DOES have a default, so it reports source="default".
        with TemporaryDirectory() as tmp, self._root(tmp):
            (Path(tmp) / "data").mkdir()
            club_bag.save_manual_club_bag("p_m", [{"token": "wood7"}, {"token": "iron7"}])
            by = {c["token"]: c for c in build_effective_club_bag_response("p_m")["clubs"]}
            self.assertIsNone(by["wood7"]["distanceM"])
            self.assertIsNone(by["wood7"]["distanceSource"])
            self.assertEqual(by["iron7"]["distanceM"], 128)
            self.assertEqual(by["iron7"]["distanceSource"], "default")

    def test_synced_garmin_bag_exposes_nonzero_advice_distance(self) -> None:
        with TemporaryDirectory() as tmp, self._root(tmp):
            data_dir = Path(tmp) / "data"
            data_dir.mkdir()
            (data_dir / "club_bag.json").write_text(json.dumps({
                "clubs": [{
                    "id": 1,
                    "clubTypeId": 2,
                    "averageDistance": 181,
                    "adviceDistance": 188,
                    "retired": False,
                    "deleted": False,
                }]
            }))

            club = build_effective_club_bag_response("me")["clubs"][0]

        self.assertEqual(club["token"], "wood3")
        self.assertEqual(club["distanceM"], 188)
        self.assertEqual(club["distanceSource"], "garmin_advice")
