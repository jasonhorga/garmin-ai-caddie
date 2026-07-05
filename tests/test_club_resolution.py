"""Shared club-resolution prep layer (core.data): shot clubIds often do NOT match our bag's ids
(clubId 0 = no club logged; a clubTypeId present but the bag id in a different space). The resolver
must turn any real signal into a real bag label and everything else into None — never a meaningless
"Unknown" / "ClubType 7" / bare number leaking to a surface (owner: "那些杆都找不到")."""
from __future__ import annotations

import unittest

from ai_caddie.core import data


class CleanClubNameTests(unittest.TestCase):
    def test_placeholders_become_none(self) -> None:
        # "Unknown" / "ClubType N" / "?" / empty, plus 0 and a raw 8-digit Garmin clubId leaking as text.
        for junk in ("Unknown", "unknown", "  Unknown  ", "ClubType 7", "ClubType7",
                     "42684923", "36696899", "0", "?", "", "   ", None):
            self.assertIsNone(data.clean_club_name(junk), junk)

    def test_real_names_pass_through(self) -> None:
        for real in ("一号木", "7I", "58°", "Driver", "3H", "PW", "Putter"):
            self.assertEqual(data.clean_club_name(real), real, real)

    def test_bare_number_wedge_and_club_labels_are_kept(self) -> None:
        # The owner's wedges are named as bare degrees ("50"/"54"/"58") and club numbers exist too —
        # these are REAL labels, NOT clubId placeholders, and must survive (regression guard).
        for real in ("50", "54", "58", "7", "9", "460"):
            self.assertEqual(data.clean_club_name(real), real, real)

    def test_strips_surrounding_whitespace_on_real_names(self) -> None:
        self.assertEqual(data.clean_club_name("  7I "), "7I")


class ClubNameFromDetailsTests(unittest.TestCase):
    def test_no_club_id_is_unknown(self) -> None:
        # clubId 0 / None = Garmin logged no club for the shot.
        self.assertEqual(data.club_name_from_details(0, {"clubDetails": []}), "Unknown")
        self.assertEqual(data.club_name_from_details(None, {"clubDetails": []}), "Unknown")

    def test_explicit_name_wins(self) -> None:
        sd = {"clubDetails": [{"id": 555, "clubTypeId": 8, "name": "5号小鸡腿"}]}
        self.assertEqual(data.club_name_from_details(555, sd, apply_overrides=False), "5号小鸡腿")

    def test_club_type_id_maps_to_generic_label_not_clubtype_leak(self) -> None:
        # The mismatch case the owner hit: a shot's clubId matches a bag record that has only a
        # clubTypeId (no name) → resolve via the shared club/types table to a REAL label, not
        # the old "ClubType 11" string.
        sd = {"clubDetails": [{"id": 999, "clubTypeId": 11, "name": None}]}
        self.assertEqual(data.club_name_from_details(999, sd, apply_overrides=False), "7I")
        # And it cleans to a real name (never a placeholder).
        self.assertEqual(data.clean_club_name(data.club_name_from_details(999, sd, apply_overrides=False)), "7I")

    def test_unmappable_club_falls_back_to_id_then_cleans_to_none(self) -> None:
        sd = {"clubDetails": [{"id": 42684999, "clubTypeId": 99, "name": None}]}  # clubTypeId not in table
        raw = data.club_name_from_details(42684999, sd, apply_overrides=False)
        self.assertEqual(raw, "42684999")
        self.assertIsNone(data.clean_club_name(raw))

    def test_club_id_not_in_details_falls_back_to_id_then_cleans_to_none(self) -> None:
        raw = data.club_name_from_details(42684923, {"clubDetails": []}, apply_overrides=False)
        self.assertEqual(raw, "42684923")
        self.assertIsNone(data.clean_club_name(raw))


if __name__ == "__main__":
    unittest.main()
