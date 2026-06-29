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
