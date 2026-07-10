"""Offline decoder tests for the Garmin course-update check client.

The live endpoint (``POST omt.garmin.cn/CourseViewData/checkForCourseUpdates``) is anonymous and its
request container is verified live, but it only returns a non-empty body for a course whose claimed
release it recognises as stale — which could not be produced from the investigation box. So the
response decoder is exercised against a SYNTHETIC protobuf built in the CourseView family shape
(top-level repeated record: f1=globalId, f2=version, f3=releaseId). See course_updates.py docstring.
"""
import json
import unittest
from unittest.mock import patch

from ai_caddie.courses import course_updates as cu


def _varint(n: int) -> bytes:
    out = bytearray()
    while True:
        b = n & 0x7F
        n >>= 7
        if n:
            out.append(b | 0x80)
        else:
            out.append(b)
            return bytes(out)


def _tag(field_no: int, wire: int) -> bytes:
    return _varint((field_no << 3) | wire)


def _fv(field_no: int, val: int) -> bytes:  # varint field
    return _tag(field_no, 0) + _varint(val)


def _fb(field_no: int, blob: bytes) -> bytes:  # length-delimited field
    return _tag(field_no, 2) + _varint(len(blob)) + blob


def _fs(field_no: int, text: str) -> bytes:  # string field
    return _fb(field_no, text.encode("utf-8"))


def _update_record(gid: int, version: int, release_id: str) -> bytes:
    return _fv(1, gid) + _fv(2, version) + _fs(3, release_id)


def _response(*records: bytes) -> bytes:
    return b"".join(_fb(1, r) for r in records)


class BuildRequestBodyTests(unittest.TestCase):
    def test_serializes_json_array_of_identifiers(self) -> None:
        body = cu.build_request_body([
            cu.CourseIdentifier(31936, "006-D2419-44"),
            cu.CourseIdentifier(31934),
        ])
        parsed = json.loads(body)
        self.assertEqual(parsed, [
            {"globalId": 31936, "releaseId": "006-D2419-44"},
            {"globalId": 31934},
        ])

    def test_identifier_to_json_omits_absent_release(self) -> None:
        self.assertEqual(cu.CourseIdentifier(1).to_json(), {"globalId": 1})


class ParseCourseUpdatesTests(unittest.TestCase):
    def test_decodes_records_with_known_ids(self) -> None:
        pb = _response(
            _update_record(31936, 267, "006-D2419-45"),
            _update_record(31870, 12, "004-D1000-13"),
        )
        rows = cu.parse_course_updates(pb, known_ids=[31936, 31870])
        by_gid = {r.global_id: r for r in rows}
        self.assertEqual(set(by_gid), {31936, 31870})
        self.assertEqual(by_gid[31936].release_id, "006-D2419-45")
        self.assertEqual(by_gid[31936].version, 267)
        self.assertEqual(by_gid[31870].release_id, "004-D1000-13")

    def test_decodes_without_known_ids_via_gid_range_heuristic(self) -> None:
        # version (267) is below the gid floor, so the gid is picked unambiguously.
        pb = _response(_update_record(31936, 267, "006-D2419-45"))
        rows = cu.parse_course_updates(pb)
        self.assertEqual([r.global_id for r in rows], [31936])

    def test_empty_bytes_yields_no_rows(self) -> None:
        self.assertEqual(cu.parse_course_updates(b""), [])

    def test_garbage_bytes_never_raise(self) -> None:
        self.assertEqual(cu.parse_course_updates(b"\xff\xff\xff\x07not-proto"), [])


class CheckCourseUpdatesTests(unittest.TestCase):
    def test_maps_queried_gids_to_update_flags(self) -> None:
        pb = _response(_update_record(31936, 267, "006-D2419-45"))  # only 31936 has an update
        with patch.object(cu, "_post_updates", return_value=pb) as post:
            result = cu.check_course_updates({31936: "006-D2419-44", 31934: "005-D2000-10"})
        post.assert_called_once()
        self.assertEqual(result, {31936: True, 31934: False})

    def test_accepts_bare_iterable_of_ids(self) -> None:
        with patch.object(cu, "_post_updates", return_value=b"") as post:
            result = cu.check_course_updates([31936, 31934])
        post.assert_called_once()
        self.assertEqual(result, {31936: False, 31934: False})

    def test_network_failure_returns_empty_dict(self) -> None:
        with patch.object(cu, "_post_updates", side_effect=OSError("boom")):
            self.assertEqual(cu.check_course_updates([31936]), {})

    def test_allow_fetch_false_skips_network(self) -> None:
        with patch.object(cu, "_post_updates") as post:
            self.assertEqual(cu.check_course_updates([31936], allow_fetch=False), {})
        post.assert_not_called()

    def test_empty_input_skips_network(self) -> None:
        with patch.object(cu, "_post_updates") as post:
            self.assertEqual(cu.check_course_updates([]), {})
        post.assert_not_called()


class FetchCourseUpdatesTests(unittest.TestCase):
    def test_returns_parsed_rows(self) -> None:
        pb = _response(_update_record(31936, 267, "006-D2419-45"))
        with patch.object(cu, "_post_updates", return_value=pb):
            rows = cu.fetch_course_updates({31936: "006-D2419-44"})
        self.assertEqual([r.global_id for r in rows], [31936])

    def test_network_failure_returns_empty_list(self) -> None:
        with patch.object(cu, "_post_updates", side_effect=OSError("boom")):
            self.assertEqual(cu.fetch_course_updates([31936]), [])


if __name__ == "__main__":
    unittest.main()
