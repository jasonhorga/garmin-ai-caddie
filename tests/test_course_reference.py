from __future__ import annotations

import json
import hashlib
import os
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from ai_caddie.courses import course_reference as cr
from ai_caddie.courses import prep_cache


class PlayedParAggregationTests(unittest.TestCase):
    def test_front_back_split_and_source(self) -> None:
        rounds = [{"front_gid": 31870, "back_gid": 31871,
                   "hole_pars": "543444534453443544", "name": "银杏湖 ~ B/C"}]
        recs = cr.aggregate_played_par(rounds)
        self.assertEqual(recs[31870].par, [5, 4, 3, 4, 4, 4, 5, 3, 4])
        self.assertEqual(recs[31871].par, [4, 5, 3, 4, 4, 3, 5, 4, 4])
        self.assertEqual(recs[31870].par_source, "played")
        self.assertEqual(recs[31870].confidence, "high")
        self.assertEqual(recs[31870].course_name, "银杏湖 ~ B/C")

    def test_mode_aggregation_ignores_outlier(self) -> None:
        rounds = [
            {"front_gid": 7, "back_gid": None, "hole_pars": "443444443", "name": "X"},
            {"front_gid": 7, "back_gid": None, "hole_pars": "443444443", "name": "X"},
            {"front_gid": 7, "back_gid": None, "hole_pars": "443444445", "name": "X"},
        ]
        recs = cr.aggregate_played_par(rounds)
        self.assertEqual(recs[7].par, [4, 4, 3, 4, 4, 4, 4, 4, 3])
        self.assertEqual(recs[7].rounds, 3)

    def test_nine_hole_round_only_fills_front(self) -> None:
        rounds = [{"front_gid": 9, "back_gid": 99, "hole_pars": "443444453", "name": "Y"}]
        recs = cr.aggregate_played_par(rounds)
        self.assertIn(9, recs)
        self.assertNotIn(99, recs)


class EstimateTests(unittest.TestCase):
    def test_length_to_par_boundaries(self) -> None:
        self.assertEqual(cr.estimate_par_from_length(150), 3)
        self.assertEqual(cr.estimate_par_from_length(209), 3)
        self.assertEqual(cr.estimate_par_from_length(210), 4)
        self.assertEqual(cr.estimate_par_from_length(449), 4)
        self.assertEqual(cr.estimate_par_from_length(450), 5)


class PersistenceTests(unittest.TestCase):
    def test_venue_loop_index_keeps_explicit_venues_separate(self) -> None:
        from ai_caddie.courses.course_search import CourseMatch

        rows = [
            CourseMatch(31905, "愉景灣 ~ A", 9, None, None, 0.0, venue_name="愉景灣", segment_label="A"),
            CourseMatch(31906, "愉景灣 ~ B", 9, None, None, 0.0, venue_name="愉景灣", segment_label="B"),
            CourseMatch(40001, "另一球会 ~ A", 9, None, None, 0.0, venue_name="另一球会", segment_label="A"),
            CourseMatch(49999, "没有明确球会", 9, None, None, 0.0),
        ]
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch.object(cr, "courseview_par", return_value=[4] * 9):
                cr.record_courseview_venue_loops(rows, root=root)
            self.assertEqual(
                [row["globalId"] for row in cr.courseview_venue_loops(31905, "拼写不同的愉景灣", root=root)],
                [31905, 31906],
            )
            self.assertEqual(
                [row["globalId"] for row in cr.courseview_venue_loops(40001, "另一球会", root=root)],
                [40001],
            )
            self.assertEqual(cr.courseview_venue_loops(49999, None, root=root), [])

    def test_venue_loop_index_is_thread_safe_bounded_and_keeps_null_par(self) -> None:
        from ai_caddie.courses.course_search import CourseMatch

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            rows = [
                CourseMatch(50000 + index, f"球会{index} ~ A", 9, None, None, 0.0,
                            venue_name=f"球会{index}", segment_label="A")
                for index in range(70)
            ]
            with patch.object(cr, "courseview_par", return_value=None), \
                    patch.object(cr, "logger") as logger:
                with ThreadPoolExecutor(max_workers=8) as pool:
                    list(pool.map(
                        lambda batch: cr.record_courseview_venue_loops(batch, root=root),
                        [rows[index::8] for index in range(8)],
                    ))
            logger.warning.assert_not_called()
            payload = json.loads((root / "data" / "courseview" / "venue_loops.json").read_text())
            self.assertLessEqual(len(payload["venues"]), 64)
            self.assertTrue(all(row["par"] is None for group in payload["venues"] for row in group["loops"]))

    def test_venue_loop_index_keeps_every_row_from_a_concurrent_multi_row_batch(self) -> None:
        from ai_caddie.courses.course_search import CourseMatch

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            rows = [
                CourseMatch(
                    61000 + venue * 3 + loop,
                    f"多环球会{venue} ~ {chr(65 + loop)}",
                    9,
                    None,
                    None,
                    0.0,
                    venue_name=f"多环球会{venue}",
                    segment_label=chr(65 + loop),
                )
                for venue in range(32)
                for loop in range(3)
            ]
            with patch.object(cr, "courseview_par", return_value=[4] * 9):
                with ThreadPoolExecutor(max_workers=8) as pool:
                    list(pool.map(
                        lambda batch: cr.record_courseview_venue_loops(batch, root=root),
                        [rows[index::8] for index in range(8)],
                    ))
            payload = json.loads((root / "data" / "courseview" / "venue_loops.json").read_text())
            persisted = {
                int(row["globalId"])
                for group in payload["venues"]
                for row in group["loops"]
            }
            self.assertEqual(persisted, {row.global_id for row in rows})

    def test_venue_loop_index_refreshes_seen_groups_and_prioritizes_them_for_eviction(self) -> None:
        from ai_caddie.courses.course_search import CourseMatch

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            index_path = root / "data" / "courseview" / "venue_loops.json"
            index_path.parent.mkdir(parents=True)
            index_path.write_text(json.dumps({
                "schema": "garmin-courseview-venue-loops-v1",
                "venues": [
                    {
                        "venueKey": f"旧球会{index}",
                        "venueName": f"旧球会{index}",
                        # The revisited group is the oldest and last in the file, so only batch
                        # priority (not lastSeenAt or file order) can keep it.
                        "lastSeenAt": 50.0 if index == 63 else 100.0,
                        "loops": [{
                            "globalId": 62000 + index,
                            "name": f"旧球会{index} ~ A",
                            "segmentLabel": "A",
                            "holeCount": 9,
                            "par": 36,
                        }],
                    }
                    for index in range(64)
                ],
            }), encoding="utf-8")
            rows = [
                CourseMatch(62063, "旧球会63 ~ A", 9, None, None, 0.0,
                            venue_name="旧球会63", segment_label="A"),
                CourseMatch(62064, "新球会 ~ A", 9, None, None, 0.0,
                            venue_name="新球会", segment_label="A"),
            ]
            with patch.object(cr.time, "time", return_value=100.5), \
                    patch.object(cr, "courseview_par", return_value=None):
                cr.record_courseview_venue_loops(rows, root=root)
            payload = json.loads(index_path.read_text())
            groups = {group["venueName"]: group for group in payload["venues"]}
            self.assertEqual(len(groups), 64)
            self.assertIn("旧球会63", groups)
            self.assertIn("新球会", groups)
            # The active group is retained by batch priority even though it was seen again within
            # the daily refresh window, so its timestamp remains unchanged.
            self.assertEqual(groups["旧球会63"]["lastSeenAt"], 50.0)
            self.assertEqual(groups["新球会"]["lastSeenAt"], 100.5)

    def test_venue_loop_index_refreshes_an_existing_group_after_one_day(self) -> None:
        from ai_caddie.courses.course_search import CourseMatch

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            row = CourseMatch(62100, "每日球会 ~ A", 9, None, None, 0.0,
                              venue_name="每日球会", segment_label="A")
            with patch.object(cr.time, "time", return_value=100.0), \
                    patch.object(cr, "courseview_par", return_value=None):
                cr.record_courseview_venue_loops([row], root=root)
            with patch.object(cr.time, "time", return_value=100.0 + 86_400.1), \
                    patch.object(cr, "courseview_par", return_value=None):
                cr.record_courseview_venue_loops([row], root=root)
            payload = json.loads((root / "data" / "courseview" / "venue_loops.json").read_text())
            self.assertEqual(payload["venues"][0]["lastSeenAt"], 86_500.1)

    def test_venue_loop_index_truncates_batch_in_input_order_without_repeat_writes(self) -> None:
        from ai_caddie.courses.course_search import CourseMatch

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            rows = [
                CourseMatch(62200 + index, f"批量球会{index} ~ A", 9, None, None, 0.0,
                            venue_name=f"批量球会{index}", segment_label="A")
                for index in range(70)
            ]
            with patch.object(cr.time, "time", return_value=200.0), \
                    patch.object(cr, "courseview_par", return_value=None), \
                    patch.object(cr, "_atomic_write_venue_loops", wraps=cr._atomic_write_venue_loops) as write:
                cr.record_courseview_venue_loops(rows, root=root)
                self.assertEqual(write.call_count, 1)
                write.reset_mock()
                cr.record_courseview_venue_loops(rows, root=root)
                write.assert_not_called()
            payload = json.loads((root / "data" / "courseview" / "venue_loops.json").read_text())
            self.assertEqual(
                sorted(row["globalId"] for group in payload["venues"] for row in group["loops"]),
                [row.global_id for row in rows[:64]],
            )

    def test_venue_loop_index_alternating_batches_do_not_rewrite_the_file(self) -> None:
        from ai_caddie.courses.course_search import CourseMatch

        def match(gid: int, venue: str) -> CourseMatch:
            return CourseMatch(gid, f"{venue} ~ A", 9, None, None, 0.0,
                               venue_name=venue, segment_label="A")

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            first = [match(62300, "甲球会"), match(62301, "乙球会")]
            second = [match(62302, "丙球会")]
            with patch.object(cr.time, "time", return_value=300.0), \
                    patch.object(cr, "courseview_par", return_value=None):
                cr.record_courseview_venue_loops(first, root=root)
                cr.record_courseview_venue_loops(second, root=root)
                with patch.object(cr, "_atomic_write_venue_loops",
                                  wraps=cr._atomic_write_venue_loops) as write:
                    for _ in range(3):
                        cr.record_courseview_venue_loops(first, root=root)
                        cr.record_courseview_venue_loops(second, root=root)
                    write.assert_not_called()

    def test_venue_loop_index_migrates_entire_group_and_unifies_names(self) -> None:
        from ai_caddie.courses.course_search import CourseMatch

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch.object(cr, "courseview_par", return_value=[4] * 9):
                cr.record_courseview_venue_loops([
                    CourseMatch(60001, "旧名 ~ A", 9, None, None, 0.0, venue_name="旧名", segment_label="A"),
                    CourseMatch(60002, "旧名 ~ B", 9, None, None, 0.0, venue_name="旧名", segment_label="B"),
                ], root=root)
                cr.record_courseview_venue_loops([
                    CourseMatch(60001, "新名 ~ A", 9, None, None, 0.0, venue_name="新名", segment_label="A"),
                ], root=root)
            payload = json.loads((root / "data" / "courseview" / "venue_loops.json").read_text())
            groups = {group["venueName"]: group for group in payload["venues"]}
            self.assertEqual({row["globalId"] for row in groups["新名"]["loops"]}, {60001, 60002})
            self.assertNotIn("旧名", groups)
            self.assertEqual(
                {row["name"] for row in groups["新名"]["loops"]},
                {"新名 ~ A", "新名 ~ B"},
            )

    def test_venue_group_migration_preserves_latest_last_seen(self) -> None:
        from ai_caddie.courses.course_search import CourseMatch

        # lastSeenAt controls refresh and eviction; renaming cannot make a recently seen
        # group older, even if discovery's clock lags the persisted timestamp.
        for destination_seen, old_seen, expected in [(100, 450, 450), (480, 450, 480), (100, 600, 600)]:
            for changed_label in (False, True):
                with self.subTest(destination_seen=destination_seen, old_seen=old_seen,
                                  changed_label=changed_label), TemporaryDirectory() as tmp:
                    root = Path(tmp)
                    path = root / "data" / "courseview" / "venue_loops.json"
                    path.parent.mkdir(parents=True)
                    path.write_text(json.dumps({"venues": [
                        {"venueName": "旧名", "lastSeenAt": old_seen, "loops": [
                            {"globalId": 60001, "segmentLabel": "A", "name": "旧名 ~ A"},
                            {"globalId": 60002, "segmentLabel": "B", "name": "旧名 ~ B"},
                        ]},
                        {"venueName": "新名", "lastSeenAt": destination_seen, "loops": []},
                    ]}), encoding="utf-8")
                    with patch.object(cr.time, "time", return_value=500), \
                            patch.object(cr, "courseview_par", return_value=[4] * 9):
                        cr.record_courseview_venue_loops([
                            CourseMatch(60001, "新名 ~ A", 9, None, None, 0.0,
                                        venue_name="新名", segment_label="C" if changed_label else "A"),
                        ], root=root)
                    groups = json.loads(path.read_text())["venues"]
                    self.assertEqual(len(groups), 1)
                    self.assertEqual(groups[0]["lastSeenAt"], max(expected, 500) if changed_label else expected)
                    self.assertEqual({row["globalId"] for row in groups[0]["loops"]}, {60001, 60002})

    def test_catalogue_name_cache_accepts_only_native_garmin_cjk_rows(self) -> None:
        from ai_caddie.courses.course_search import CourseMatch

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            cr.record_courseview_catalogue_names(
                [
                    CourseMatch(32842, "北京黄港国际高尔夫俱乐部", 18, "beijing", "beijing", 0.0),
                    CourseMatch(3881, "Cypress Point Club", 18, "Monterey", "california", 0.0),
                ],
                root=root,
            )
            self.assertEqual(
                cr.courseview_catalogue_name(32842, root=root),
                "北京黄港国际高尔夫俱乐部",
            )
            self.assertIsNone(cr.courseview_catalogue_name(3881, root=root))

    def test_localized_courseview_name_prefers_observed_catalogue_over_old_release(self) -> None:
        from ai_caddie.courses.course_search import CourseMatch

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            cr.record_courseview_catalogue_names(
                [
                    CourseMatch(
                        32842,
                        "北京黄港国际高尔夫俱乐部",
                        18,
                        "北京",
                        "北京",
                        0.0,
                    )
                ],
                root=root,
            )
            self.assertEqual(
                cr.localized_courseview_name(
                    32842,
                    info={
                        "course_name": "Beijing Huanggang International Golf Club",
                        "_localized": False,
                    },
                    root=root,
                ),
                "北京黄港国际高尔夫俱乐部",
            )

    def test_localized_courseview_name_keeps_current_localized_release(self) -> None:
        from ai_caddie.courses.course_search import CourseMatch

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            cr.record_courseview_catalogue_names(
                [
                    CourseMatch(
                        32842,
                        "北京黄港旧名",
                        18,
                        "北京",
                        "北京",
                        0.0,
                    )
                ],
                root=root,
            )
            self.assertEqual(
                cr.localized_courseview_name(
                    32842,
                    info={
                        "course_name": "北京黄港新名",
                        "_localized": True,
                    },
                    root=root,
                ),
                "北京黄港新名",
            )

    def test_concurrent_stale_release_refresh_is_singleflight(self) -> None:
        old_fixture = Path(__file__).parent / "fixtures" / "courseview_release_31870.pb"
        new_fixture = Path(__file__).parent / "fixtures" / "courseview_release_31936.pb"
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            release_path = root / "data" / "courseview" / "31936_releases.pb"
            release_path.parent.mkdir(parents=True)
            release_path.write_bytes(old_fixture.read_bytes())
            os.utime(release_path, (1, 1))
            with patch.object(cr, "load_release_pb", return_value=new_fixture.read_bytes()) as fetch:
                with ThreadPoolExecutor(max_workers=8) as pool:
                    rows = list(pool.map(lambda _: cr.courseview_release_info(31936, root=root), range(8)))

            fetch.assert_called_once_with(
                31936,
                True,
                language_code=cr.COURSEVIEW_RELEASE_LANGUAGE_CODE,
            )
            self.assertTrue(all(row and row["course_id"] == 31936 for row in rows))

    def test_stale_release_refresh_same_bytes_preserves_pb_and_prep_fingerprint(self) -> None:
        """Refreshing an unchanged release advances fetchedAt without touching release bytes."""
        fixture = Path(__file__).parent / "fixtures" / "courseview_release_31936.pb"
        payload = fixture.read_bytes()
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            release_dir = root / "data" / "courseview"
            release_dir.mkdir(parents=True)
            release_path = release_dir / "31936_releases.pb"
            release_path.write_bytes(payload)
            metadata_path = release_dir / "31936_releases.meta.json"
            metadata_path.write_text(
                json.dumps({
                    "globalId": 31936,
                    "languageCode": cr.COURSEVIEW_RELEASE_LANGUAGE_CODE,
                    "sha256": hashlib.sha256(payload).hexdigest(),
                    "fetchedAt": 1,
                }),
                encoding="utf-8",
            )
            os.utime(release_path, (1, 1))
            original_courseview_dir = prep_cache._COURSEVIEW_DIR
            prep_cache._COURSEVIEW_DIR = release_dir
            self.addCleanup(setattr, prep_cache, "_COURSEVIEW_DIR", original_courseview_dir)
            inode_before = release_path.stat().st_ino
            mtime_before = release_path.stat().st_mtime_ns
            sig_before = prep_cache._course_data_sig(31936)
            fingerprint_before = prep_cache._fingerprint(31936)

            with patch.object(cr, "load_release_pb", return_value=payload) as fetch:
                info = cr.courseview_release_info(31936, root=root)
                self.assertEqual(info["course_id"], 31936)
                info_again = cr.courseview_release_info(31936, root=root)

            fetch.assert_called_once_with(
                31936,
                True,
                language_code=cr.COURSEVIEW_RELEASE_LANGUAGE_CODE,
            )
            self.assertEqual(info_again["course_id"], 31936)
            self.assertEqual(release_path.read_bytes(), payload)
            self.assertEqual(release_path.stat().st_ino, inode_before)
            self.assertEqual(release_path.stat().st_mtime_ns, mtime_before)
            self.assertEqual(prep_cache._course_data_sig(31936), sig_before)
            self.assertEqual(prep_cache._fingerprint(31936), fingerprint_before)
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            self.assertGreater(metadata["fetchedAt"], 1)

    def test_identical_release_replacement_keeps_content_signatures(self) -> None:
        """J4.2: replacing a release with equal bytes must keep vector/prep authorities warm."""
        fixture = Path(__file__).parent / "fixtures" / "courseview_release_31936.pb"
        payload = fixture.read_bytes()
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            release_dir = root / "data" / "courseview"
            release_dir.mkdir(parents=True)
            release_path = release_dir / "31936_releases.pb"
            release_path.write_bytes(payload)
            original_courseview_dir = prep_cache._COURSEVIEW_DIR
            prep_cache._COURSEVIEW_DIR = release_dir
            self.addCleanup(setattr, prep_cache, "_COURSEVIEW_DIR", original_courseview_dir)

            before = prep_cache._course_data_sig(31936)
            release_signature = cr.courseview_release_signature(31936, root=root)
            replacement = release_path.with_name(".replacement.pb")
            replacement.write_bytes(payload)
            os.replace(replacement, release_path)

            self.assertEqual(prep_cache._course_data_sig(31936), before)
            self.assertEqual(cr.courseview_release_signature(31936, root=root), release_signature)

    def test_stale_release_refresh_different_bytes_writes_and_changes_prep_fingerprint(self) -> None:
        fixture = Path(__file__).parent / "fixtures" / "courseview_release_31936.pb"
        original = fixture.read_bytes()
        # A repeated release_version field is valid protobuf; inspect_release uses the latest value.
        replacement = original + b"\x10\x81\x01"
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            release_dir = root / "data" / "courseview"
            release_dir.mkdir(parents=True)
            release_path = release_dir / "31936_releases.pb"
            release_path.write_bytes(original)
            metadata_path = release_dir / "31936_releases.meta.json"
            metadata_path.write_text(
                json.dumps({
                    "globalId": 31936,
                    "languageCode": cr.COURSEVIEW_RELEASE_LANGUAGE_CODE,
                    "sha256": hashlib.sha256(original).hexdigest(),
                    "fetchedAt": 1,
                }),
                encoding="utf-8",
            )
            os.utime(release_path, (1, 1))
            original_courseview_dir = prep_cache._COURSEVIEW_DIR
            prep_cache._COURSEVIEW_DIR = release_dir
            self.addCleanup(setattr, prep_cache, "_COURSEVIEW_DIR", original_courseview_dir)
            inode_before = release_path.stat().st_ino
            sig_before = prep_cache._course_data_sig(31936)

            with patch.object(cr, "load_release_pb", return_value=replacement) as fetch:
                info = cr.courseview_release_info(31936, root=root)

            fetch.assert_called_once()
            self.assertEqual(info["course_id"], 31936)
            self.assertEqual(release_path.read_bytes(), replacement)
            self.assertNotEqual(release_path.stat().st_ino, inode_before)
            self.assertNotEqual(prep_cache._course_data_sig(31936), sig_before)

    def test_old_release_without_metadata_uses_mtime_for_refresh(self) -> None:
        fixture = Path(__file__).parent / "fixtures" / "courseview_release_31936.pb"
        payload = fixture.read_bytes()
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            release_path = root / "data" / "courseview" / "31936_releases.pb"
            release_path.parent.mkdir(parents=True)
            release_path.write_bytes(payload)
            os.utime(release_path, (1, 1))
            with patch.object(cr, "load_release_pb", return_value=payload) as fetch:
                info = cr.courseview_release_info(31936, root=root)

            fetch.assert_called_once_with(
                31936,
                True,
                language_code=cr.COURSEVIEW_RELEASE_LANGUAGE_CODE,
            )
            self.assertEqual(info["course_id"], 31936)
            self.assertTrue((release_path.parent / "31936_releases.meta.json").exists())

    def test_stale_release_cache_refreshes_atomically_when_online(self) -> None:
        old_fixture = Path(__file__).parent / "fixtures" / "courseview_release_31870.pb"
        new_fixture = Path(__file__).parent / "fixtures" / "courseview_release_31936.pb"
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            release_path = root / "data" / "courseview" / "31936_releases.pb"
            release_path.parent.mkdir(parents=True)
            release_path.write_bytes(old_fixture.read_bytes())
            os.utime(release_path, (1, 1))
            with patch.object(cr, "load_release_pb", return_value=new_fixture.read_bytes()) as fetch:
                info = cr.courseview_release_info(31936, root=root)

            fetch.assert_called_once_with(
                31936,
                True,
                language_code=cr.COURSEVIEW_RELEASE_LANGUAGE_CODE,
            )
            self.assertEqual(info["course_id"], 31936)
            self.assertEqual(release_path.read_bytes(), new_fixture.read_bytes())

    def test_stale_release_cache_remains_available_when_refresh_fails(self) -> None:
        fixture = Path(__file__).parent / "fixtures" / "courseview_release_31936.pb"
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            release_path = root / "data" / "courseview" / "31936_releases.pb"
            release_path.parent.mkdir(parents=True)
            release_path.write_bytes(fixture.read_bytes())
            os.utime(release_path, (1, 1))
            with patch.object(cr, "load_release_pb", side_effect=OSError("offline")):
                info = cr.courseview_release_info(31936, root=root)

            self.assertEqual(info["course_id"], 31936)

    def test_failed_stale_refresh_backs_off_instead_of_retrying_every_request(self) -> None:
        """Garmin jitter must not put a 30s fetch in front of every topo/green/prep request."""
        fixture = Path(__file__).parent / "fixtures" / "courseview_release_31936.pb"
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            release_path = root / "data" / "courseview" / "31936_releases.pb"
            release_path.parent.mkdir(parents=True)
            release_path.write_bytes(fixture.read_bytes())
            os.utime(release_path, (1, 1))
            with patch.object(cr, "load_release_pb", side_effect=OSError("offline")) as fetch, \
                    patch.object(cr, "logger") as logger:
                rows = [cr.courseview_release_info(31936, root=root) for _ in range(5)]
            self.assertEqual(fetch.call_count, 1)
            logger.warning.assert_called_once()  # one observable signal per failed refresh
            self.assertIn("refresh_failed", logger.warning.call_args.args[0])
            self.assertTrue(all(row and row["course_id"] == 31936 for row in rows))

            # Once the backoff window has passed, the stale release is refreshed again.
            key = (str(root.resolve()), 31936)
            cr._RELEASE_FETCH_FAILED_AT[key] -= cr.COURSEVIEW_RELEASE_RETRY_BACKOFF_S + 1
            with patch.object(cr, "load_release_pb", return_value=fixture.read_bytes()) as fetch:
                cr.courseview_release_info(31936, root=root)
            fetch.assert_called_once()
            self.assertNotIn(key, cr._RELEASE_FETCH_FAILED_AT)

    def test_fresh_release_without_locale_marker_is_upgraded_once(self) -> None:
        """A pre-zh_CHS protobuf must not keep an English name forever."""
        fixture = Path(__file__).parent / "fixtures" / "courseview_release_31936.pb"
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            release_path = root / "data" / "courseview" / "31936_releases.pb"
            release_path.parent.mkdir(parents=True)
            release_path.write_bytes(fixture.read_bytes())
            with patch.object(cr, "load_release_pb", return_value=fixture.read_bytes()) as fetch:
                info = cr.courseview_release_info(31936, root=root)

            fetch.assert_called_once_with(
                31936,
                True,
                language_code=cr.COURSEVIEW_RELEASE_LANGUAGE_CODE,
            )
            marker = json.loads(
                (root / "data" / "courseview" / "31936_releases.meta.json").read_text()
            )
            self.assertEqual(marker["languageCode"], cr.COURSEVIEW_RELEASE_LANGUAGE_CODE)
            self.assertEqual(info["course_id"], 31936)

    def test_localized_release_marker_keeps_fresh_cache_offline(self) -> None:
        fixture = Path(__file__).parent / "fixtures" / "courseview_release_31936.pb"
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            release_dir = root / "data" / "courseview"
            release_dir.mkdir(parents=True)
            (release_dir / "31936_releases.pb").write_bytes(fixture.read_bytes())
            (release_dir / "31936_releases.meta.json").write_text(
                json.dumps({
                    "globalId": 31936,
                    "languageCode": cr.COURSEVIEW_RELEASE_LANGUAGE_CODE,
                    "sha256": hashlib.sha256(fixture.read_bytes()).hexdigest(),
                }),
                encoding="utf-8",
            )
            with patch.object(cr, "load_release_pb") as fetch:
                info = cr.courseview_release_info(31936, root=root)

            fetch.assert_not_called()
            self.assertEqual(info["course_id"], 31936)

    def test_malformed_refresh_never_replaces_last_valid_release(self) -> None:
        fixture = Path(__file__).parent / "fixtures" / "courseview_release_31936.pb"
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            release_path = root / "data" / "courseview" / "31936_releases.pb"
            release_path.parent.mkdir(parents=True)
            original = fixture.read_bytes()
            release_path.write_bytes(original)
            os.utime(release_path, (1, 1))
            with patch.object(cr, "load_release_pb", return_value=b""):
                info = cr.courseview_release_info(31936, root=root)

            self.assertEqual(info["course_id"], 31936)
            self.assertEqual(release_path.read_bytes(), original)

    def test_cached_courseview_release_exposes_mens_tee_names_with_real_indices(self) -> None:
        fixture = Path(__file__).parent / "fixtures" / "courseview_release_31936.pb"
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            release_path = root / "data" / "courseview" / "31936_releases.pb"
            release_path.parent.mkdir(parents=True)
            release_path.write_bytes(fixture.read_bytes())
            resolve_tees = getattr(cr, "courseview_tees", lambda *_args, **_kwargs: [])

            tees = resolve_tees(31936, allow_fetch=False, root=root)

        self.assertEqual(
            [
                {key: tee[key] for key in ("name", "gender", "index")}
                for tee in tees
            ],
            [
                {"name": "Black", "gender": "MEN", "index": 1},
                {"name": "Blue", "gender": "MEN", "index": 2},
                {"name": "White", "gender": "MEN", "index": 3},
                {"name": "Red", "gender": "MEN", "index": 4},
            ],
        )
        self.assertEqual(tees[0]["slopeRating"], 115)
        self.assertEqual(tees[0]["courseRating"], 35.96)

    def test_save_and_load_preserves_source_confidence_provenance_and_yardage(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            rec = cr.CoursePar(
                global_id=31936,
                par=[4, 5, 3, 4, 3, 4, 4, 5, 4],
                par_source="courseview",
                confidence="high",
                provenance="courseview_release",
                course_name="Fixture C",
                handicap=[6, 3, 2, 1, 9, 5, 8, 7, 4],
                yardages_m=[360, 470, 160, 380, 155, 390, 410, 455, 370],
                yardage_source="courseview",
                yardage_confidence="high",
                yardage_provenance="courseview_release",
            )

            cr.save_course_par(rec, root=root)
            loaded = cr.load_course_par(31936, root=root)

        self.assertEqual(loaded, rec)

    def test_load_course_par_ignores_corrupt_or_incomplete_records(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "data" / "courses" / "31936.json"
            path.parent.mkdir(parents=True)
            path.write_text(json.dumps({"global_id": 31936, "par": "not-a-list", "par_source": "courseview"}), encoding="utf-8")

            self.assertIsNone(cr.load_course_par(31936, root=root))


class ResolveLadderTests(unittest.TestCase):
    def test_played_supersedes(self) -> None:
        played = {31870: cr.CoursePar(31870, [5, 4, 3, 4, 4, 4, 5, 3, 4], "played", "high", rounds=2)}
        with patch.object(cr, "played_par_by_nine", return_value=played), \
                patch.object(cr, "save_course_par"):
            rec = cr.resolve_par(31870, lengths_m=[400] * 9)
        self.assertEqual(rec.par_source, "played")

    def test_courseview_when_unplayed(self) -> None:
        holes = [{"par": p, "handicap": h} for p, h in
                 zip([4, 5, 3, 4, 3, 4, 4, 5, 4], [6, 3, 2, 1, 9, 5, 8, 7, 4])]
        with patch.object(cr, "played_par_by_nine", return_value={}), \
                patch.object(cr, "_release_holes", return_value=holes), \
                patch.object(cr, "save_course_par"):
            rec = cr.resolve_par(31936)
        self.assertEqual(rec.par_source, "courseview")
        self.assertEqual(rec.par, [4, 5, 3, 4, 3, 4, 4, 5, 4])
        self.assertEqual(rec.handicap, [6, 3, 2, 1, 9, 5, 8, 7, 4])

    def test_courseview_record_persists_yardage_metadata(self) -> None:
        holes = [
            {"par": p, "handicap": h, "yardage_or_length": y}
            for p, h, y in zip(
                [4, 5, 3, 4, 3, 4, 4, 5, 4],
                [6, 3, 2, 1, 9, 5, 8, 7, 4],
                [360, 470, 160, 380, 155, 390, 410, 455, 370],
            )
        ]
        saved: dict[int, cr.CoursePar] = {}
        with patch.object(cr, "played_par_by_nine", return_value={}), \
                patch.object(cr, "_release_holes", return_value=holes), \
                patch.object(cr, "save_course_par", side_effect=lambda record, **_: saved.__setitem__(record.global_id, record)):
            rec = cr.resolve_par(31936)

        self.assertEqual(rec.yardages_m, [360, 470, 160, 380, 155, 390, 410, 455, 370])
        self.assertEqual(rec.yardage_source, "courseview")
        self.assertEqual(rec.yardage_confidence, "high")
        self.assertEqual(rec.yardage_provenance, "courseview_release")
        self.assertEqual(saved[31936].yardages_m, rec.yardages_m)

    def test_estimate_when_no_release(self) -> None:
        with patch.object(cr, "played_par_by_nine", return_value={}), \
                patch.object(cr, "_release_holes", return_value=None), \
                patch.object(cr, "save_course_par"):
            rec = cr.resolve_par(99999, lengths_m=[150, 460, 300, 300, 300, 300, 300, 300, 300])
        self.assertEqual(rec.par_source, "estimate")
        self.assertEqual(rec.par[:2], [3, 5])

    def test_estimate_persists_length_yardage_metadata_without_overriding_courseview(self) -> None:
        lengths = [150, 460, 300, 300, 300, 300, 300, 300, 300]
        with patch.object(cr, "played_par_by_nine", return_value={}), \
                patch.object(cr, "_release_holes", return_value=None), \
                patch.object(cr, "save_course_par") as save:
            rec = cr.resolve_par(99999, lengths_m=lengths)

        self.assertEqual(rec.par_source, "estimate")
        self.assertEqual(rec.confidence, "medium")
        self.assertEqual(rec.yardages_m, lengths)
        self.assertEqual(rec.yardage_source, "length_estimate")
        self.assertEqual(rec.yardage_confidence, "medium")
        self.assertEqual(rec.yardage_provenance, "length_estimate")
        save.assert_called_once()

    def test_none_when_nothing(self) -> None:
        with patch.object(cr, "played_par_by_nine", return_value={}), \
                patch.object(cr, "_release_holes", return_value=None), \
                patch.object(cr, "save_course_par"):
            self.assertIsNone(cr.resolve_par(99999))


class BuildStoreTests(unittest.TestCase):
    def test_fills_courseview_for_referenced_unplayed_nine(self) -> None:
        rounds = [{"front_gid": 40590, "back_gid": 31936, "hole_pars": "453444434", "name": "X"}]
        played = {40590: cr.CoursePar(40590, [4, 5, 3, 4, 4, 4, 4, 3, 4], "played", "high")}
        holes = [{"par": p} for p in [4, 5, 3, 4, 3, 4, 4, 5, 4]]
        saved = {}
        with patch.object(cr, "played_par_by_nine", return_value=played), \
                patch.object(cr, "_rounds_from_files", return_value=rounds), \
                patch.object(cr, "_release_holes", return_value=holes), \
                patch.object(cr, "load_course_par", return_value=None), \
                patch.object(cr, "save_course_par", side_effect=lambda r, **_: saved.__setitem__(r.global_id, r)):
            store = cr.build_played_store()
        self.assertEqual(store[40590].par_source, "played")
        self.assertEqual(store[31936].par_source, "courseview")

    def test_returns_cached_courseview_for_referenced_unplayed_nine(self) -> None:
        rounds = [{"front_gid": 40590, "back_gid": 31936, "hole_pars": "453444434", "name": "X"}]
        played = {40590: cr.CoursePar(40590, [4, 5, 3, 4, 4, 4, 4, 3, 4], "played", "high")}
        cached = cr.CoursePar(31936, [4, 5, 3, 4, 3, 4, 4, 5, 4], "courseview", "high")
        with patch.object(cr, "played_par_by_nine", return_value=played), \
                patch.object(cr, "_rounds_from_files", return_value=rounds), \
                patch.object(cr, "load_course_par", side_effect=lambda gid, **_: cached if gid == 31936 else None), \
                patch.object(cr, "_courseview_record") as courseview_record, \
                patch.object(cr, "save_course_par"):
            store = cr.build_played_store()
        courseview_record.assert_not_called()
        self.assertEqual(store[40590].par_source, "played")
        self.assertEqual(store[31936].par_source, "courseview")

    def test_course_reference_coverage_counts_referenced_and_stored_nines(self) -> None:
        rounds = [
            {"front_gid": 40590, "back_gid": 31936, "hole_pars": "453444434453444544", "name": "X"},
        ]
        with patch.object(cr, "_rounds_from_files", return_value=rounds), \
                patch.object(cr, "load_course_par", side_effect=lambda gid, **_: cr.CoursePar(gid, [4] * 9, "played", "high", provenance="garmin_scorecard") if gid == 40590 else None):
            coverage = cr.course_reference_coverage()

        self.assertEqual(coverage["schema"], "ai-caddie-course-reference-coverage-v1")
        self.assertEqual(coverage["total"], 2)
        self.assertEqual(coverage["ready"], 1)
        self.assertEqual(coverage["missing"], 1)
        self.assertEqual(coverage["pct"], 50.0)
        self.assertEqual(coverage["missingGlobalIds"], [31936])


if __name__ == "__main__":
    unittest.main()
