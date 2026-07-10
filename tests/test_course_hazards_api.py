"""Offline decoder tests for the Garmin authoritative Hazards client.

The live endpoint (``GET securemaps.garmin.cn/golf/courseData/{gid}/Hazards``) is behind Garmin's
per-path URL-signing gate (403 without a signed ``garmindlm`` token) and could not be fetched from
the investigation box, so the response schema is INFERRED. The decoder is exercised against a
SYNTHETIC protobuf built in the inferred shape (top-level repeated hazard record: f1=type enum,
f2=name, f3=point{f1=lat_raw, f2=lon_raw} in Garmin semicircle units). See course_hazards_api.py.
"""
import unittest
from unittest.mock import patch

from ai_caddie.courses import course_hazards_api as ha


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


def _fv(field_no: int, val: int) -> bytes:
    return _tag(field_no, 0) + _varint(val)


def _fb(field_no: int, blob: bytes) -> bytes:
    return _tag(field_no, 2) + _varint(len(blob)) + blob


def _fs(field_no: int, text: str) -> bytes:
    return _fb(field_no, text.encode("utf-8"))


def _semicircle(deg: float) -> int:
    """Degrees -> Garmin semicircle varint (unsigned 32-bit two's complement for negatives)."""
    raw = round(deg / ha._SEMICIRCLE_SCALE)
    return raw & 0xFFFFFFFF


def _point(lat: float, lon: float) -> bytes:
    return _fv(1, _semicircle(lat)) + _fv(2, _semicircle(lon))


def _hazard(type_id: int, name: str, points: list[tuple[float, float]]) -> bytes:
    blob = _fv(1, type_id) + _fs(2, name)
    for lat, lon in points:
        blob += _fb(3, _point(lat, lon))
    return blob


def _response(*hazards: bytes) -> bytes:
    return b"".join(_fb(1, h) for h in hazards)


class SemicircleTests(unittest.TestCase):
    def test_positive_roundtrip(self) -> None:
        self.assertAlmostEqual(ha._semicircle_to_deg(_semicircle(32.05)), 32.05, places=4)

    def test_negative_hemisphere_sign_corrected(self) -> None:
        self.assertAlmostEqual(ha._semicircle_to_deg(_semicircle(-33.87)), -33.87, places=4)


class ParseCourseHazardsTests(unittest.TestCase):
    def _fixture(self) -> bytes:
        return _response(
            _hazard(1, "Lake", [(32.0500, 118.8500), (32.0510, 118.8520), (32.0495, 118.8530)]),
            _hazard(2, "Left Bunker", [(32.0480, 118.8490), (32.0485, 118.8495)]),
            _hazard(99, "Weird", [(32.0000, 118.0000)]),  # unmapped type id -> "hazard"
        )

    def test_decodes_kinds_and_polygons(self) -> None:
        hazards = ha.parse_course_hazards(self._fixture())
        self.assertEqual(len(hazards), 3)
        water, bunker, weird = hazards
        self.assertEqual(water.kind, "water")
        self.assertEqual(water.type_id, 1)
        self.assertEqual(water.name, "Lake")
        self.assertEqual(len(water.points), 3)
        self.assertAlmostEqual(water.points[0][0], 32.0500, places=4)
        self.assertAlmostEqual(water.points[0][1], 118.8500, places=4)
        self.assertEqual(bunker.kind, "bunker")
        self.assertEqual(len(bunker.points), 2)
        self.assertEqual(weird.kind, "hazard")  # unmapped id falls through, raw id preserved
        self.assertEqual(weird.type_id, 99)

    def test_empty_bytes_yields_no_hazards(self) -> None:
        self.assertEqual(ha.parse_course_hazards(b""), [])

    def test_garbage_bytes_never_raise(self) -> None:
        self.assertEqual(ha.parse_course_hazards(b"\xff\xff\xff\x07nonsense"), [])


class HazardUrlTests(unittest.TestCase):
    def test_default_host_path(self) -> None:
        self.assertEqual(
            ha.hazard_url(31936),
            "https://securemaps.garmin.cn/golf/courseData/31936/Hazards",
        )


class FetchCourseHazardsTests(unittest.TestCase):
    def test_returns_decoded_hazards(self) -> None:
        pb = _response(_hazard(1, "Lake", [(32.05, 118.85), (32.06, 118.86)]))
        with patch.object(ha, "_fetch_hazards", return_value=pb) as fetch:
            hazards = ha.fetch_course_hazards(31936, cookie="x=y")
        fetch.assert_called_once()
        self.assertEqual([h.kind for h in hazards], ["water"])

    def test_network_failure_returns_empty_list(self) -> None:
        with patch.object(ha, "_fetch_hazards", side_effect=OSError("403 Forbidden")):
            self.assertEqual(ha.fetch_course_hazards(31936), [])

    def test_allow_fetch_false_skips_network(self) -> None:
        with patch.object(ha, "_fetch_hazards") as fetch:
            self.assertEqual(ha.fetch_course_hazards(31936, allow_fetch=False), [])
        fetch.assert_not_called()


if __name__ == "__main__":
    unittest.main()
