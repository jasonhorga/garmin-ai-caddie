from __future__ import annotations

import unittest

from ai_caddie.courses.name_authority import (
    GARMIN_SNAPSHOT_NAME_SOURCE,
    GarminNameIdentity,
    canonical_course_identity,
    is_trusted_garmin_identity,
    is_composite_segment,
    localized_names_by_global_id,
    localized_provider_name,
    preferred_garmin_venue,
    preferred_garmin_source_name,
    select_garmin_name_identity,
    split_garmin_course_name,
)


class GarminNameAuthorityTests(unittest.TestCase):
    def test_snapshot_name_wins_over_derived_english_fields(self) -> None:
        identity = select_garmin_name_identity(
            [
                {
                    "globalId": 123,
                    "course": "West Park Golf & Country Club ~ A/C",
                    "courseCanonical": "West Park Golf & Country Club",
                    "garminSnapshotName": "西郊高尔夫俱乐部 ~ A/C",
                    "source": "garmin",
                }
            ]
        )

        self.assertIsNotNone(identity)
        assert identity is not None
        self.assertEqual(identity.venue, "西郊高尔夫俱乐部")
        self.assertIsNone(identity.segment)
        self.assertEqual(identity.source, "garmin_scorecard_snapshot")

    def test_composite_routes_never_become_a_segment(self) -> None:
        for value in ("A/C", "A+B", "AB", "AC", "AF", "ABC"):
            self.assertTrue(is_composite_segment(value), value)
        for value in ("A", "B", "Ocean", "Faldo"):
            self.assertFalse(is_composite_segment(value), value)

        self.assertEqual(
            localized_provider_name(
                "West Park Golf & Country Club ~ A/C",
                select_garmin_name_identity(
                    [
                        {
                            "garminSnapshotName": "西郊高尔夫俱乐部 ~ A/C",
                            "source": "garmin",
                        }
                    ]
                ),
            ),
            "西郊高尔夫俱乐部",
        )

    def test_global_id_index_uses_formal_snapshot_name(self) -> None:
        index = localized_names_by_global_id(
            [
                {
                    "courseId": 31794,
                    "course": "Black Knight ~ A/C",
                    "garminSnapshotName": "北京天竺黑骑士球员俱乐部 ~ A/C",
                    "source": "garmin",
                }
            ]
        )
        self.assertEqual(index[31794].venue, "北京天竺黑骑士球员俱乐部")

    def test_split_preserves_single_provider_suffix(self) -> None:
        self.assertEqual(
            split_garmin_course_name("  Dalian Xiali Country Club~Left  "),
            ("Dalian Xiali Country Club", "Left"),
        )

    def test_split_removes_compact_and_separated_routes_from_venue(self) -> None:
        for raw, expected in (
            ("Black Knight B/C", ("Black Knight", "B/C")),
            ("Black Knight AC", ("Black Knight", "AC")),
            ("Black Knight ~ A/C", ("Black Knight", "A/C")),
        ):
            self.assertEqual(split_garmin_course_name(raw), expected)

    def test_canonical_identity_rejects_untrusted_manual_name(self) -> None:
        identity = GarminNameIdentity(
            venue="手填中文球场",
            source="manual",
        )
        canonical = canonical_course_identity("Provider Golf Club ~ A", identity)
        self.assertEqual(canonical.name, "Provider Golf Club")
        self.assertEqual(canonical.venue, "Provider Golf Club")
        self.assertIsNone(canonical.source)

    def test_canonical_identity_accepts_only_explicit_garmin_snapshot_name(self) -> None:
        identity = GarminNameIdentity(
            venue="Garmin 中文球场",
            source=GARMIN_SNAPSHOT_NAME_SOURCE,
        )
        canonical = canonical_course_identity("Provider Golf Club ~ A", identity)
        self.assertEqual(canonical.name, "Garmin 中文球场")
        self.assertEqual(canonical.venue, "Garmin 中文球场")
        self.assertEqual(canonical.segment, "A")
        self.assertEqual(canonical.source, GARMIN_SNAPSHOT_NAME_SOURCE)

    def test_raw_garmin_snapshot_shape_is_an_explicit_name_source(self) -> None:
        identity = select_garmin_name_identity(
            [
                {
                    "course": "West Park Golf & Country Club",
                    "scorecardDetails": [{"scorecard": {"id": 1, "courseGlobalId": 42001}}],
                    "courseSnapshots": [{"name": "西郊高尔夫俱乐部 ~ A/C"}],
                }
            ]
        )
        self.assertIsNotNone(identity)
        assert identity is not None
        self.assertEqual(identity.venue, "西郊高尔夫俱乐部")
        self.assertEqual(identity.source, "garmin_scorecard_snapshot")

    def test_preferred_venue_materializes_generators(self) -> None:
        rows = (
            row
            for row in [
                {"course": "West Park Golf & Country Club"},
                {"garminSnapshotName": "西郊高尔夫俱乐部", "source": "garmin"},
            ]
        )
        self.assertEqual(preferred_garmin_venue(rows), "西郊高尔夫俱乐部")

    def test_provider_single_loop_wins_over_historical_loop(self) -> None:
        identity = select_garmin_name_identity(
            [{"garminSnapshotName": "北京天竺黑骑士球员俱乐部 ~ B", "source": "garmin"}]
        )
        self.assertEqual(
            localized_provider_name(
                "The Players Club ~ A",
                identity,
            ),
            "北京天竺黑骑士球员俱乐部 ~ A",
        )

    def test_merged_route_does_not_become_a_raw_snapshot_source(self) -> None:
        merged = {
            "merged": True,
            "source": "garmin",  # inherited from the front member
            "course": "西郊高尔夫俱乐部 ~ A+C",
            "garminSnapshotName": "西郊高尔夫俱乐部 ~ A+C",  # stale derived field
            "garminSnapshotNames": [
                "西郊高尔夫俱乐部 ~ A",
                "西郊高尔夫俱乐部 ~ C",
            ],
        }
        # The history label keeps the factual combined route, but the stale
        # singular field on a legacy derived row is never promoted to an exact
        # snapshot source; the member list remains authoritative.
        self.assertEqual(
            preferred_garmin_source_name(merged),
            "西郊高尔夫俱乐部 ~ A+C",
        )
        identity = select_garmin_name_identity([merged])
        self.assertIsNotNone(identity)
        assert identity is not None
        self.assertEqual(identity.source, "garmin_scorecard_snapshot")

    def test_manual_snapshot_shaped_round_is_never_garmin_authority(self) -> None:
        identity = select_garmin_name_identity(
            [
                {
                    "source": "manual",
                    "course": "用户填写的中文球场",
                    "garminSnapshotName": "用户填写的中文球场",
                    "scorecardDetails": [{"scorecard": {"id": 9, "courseGlobalId": 9}}],
                    "courseSnapshots": [{"name": "用户填写的中文球场"}],
                }
            ]
        )
        self.assertIsNotNone(identity)
        assert identity is not None
        self.assertEqual(identity.venue, "用户填写的中文球场")
        self.assertFalse(is_trusted_garmin_identity(identity))
        self.assertEqual(identity.source, "history_fallback")

    def test_unmarked_normalized_snapshot_field_is_not_enough_evidence(self) -> None:
        identity = select_garmin_name_identity(
            [{"garminSnapshotName": "不明来源中文", "course": "Provider English"}]
        )
        self.assertIsNotNone(identity)
        assert identity is not None
        self.assertEqual(identity.venue, "Provider English")
        self.assertFalse(is_trusted_garmin_identity(identity))

    def test_legacy_normalized_provenance_connector_authorizes_garmin_snapshot(self) -> None:
        identity = select_garmin_name_identity(
            [
                {
                    # Old normalized history rows did not yet materialize
                    # ``garminSnapshotName``; their ``course`` value is still
                    # the Garmin snapshot spelling.
                    "course": "北京丽宫体育公园高尔夫俱乐部",
                    "courseCanonical": "北京丽宫体育公园高尔夫俱乐部",
                    "provenance": {"sourceConnector": "garmin_cn_web_session"},
                }
            ]
        )
        self.assertIsNotNone(identity)
        assert identity is not None
        self.assertEqual(identity.venue, "北京丽宫体育公园高尔夫俱乐部")
        self.assertTrue(is_trusted_garmin_identity(identity))

    def test_manual_marker_wins_over_garmin_connector(self) -> None:
        identity = select_garmin_name_identity(
            [
                {
                    "source": "manual",
                    "garminSnapshotName": "用户填写的中文球场",
                    "course": "Provider English",
                    "provenance": {"sourceConnector": "garmin_cn_web_session"},
                }
            ]
        )
        self.assertIsNotNone(identity)
        assert identity is not None
        self.assertEqual(identity.venue, "Provider English")
        self.assertFalse(is_trusted_garmin_identity(identity))


if __name__ == "__main__":
    unittest.main()
