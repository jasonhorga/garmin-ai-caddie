import json
import math
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from tools.courseview.audit_course_data_corpus import audit_course_data_corpus, report_bytes


_SCALE = 180.0 / (1 << 31)
_EARTH_RADIUS_METRES = 6_371_008.8


def _semicircles(degrees: float) -> int:
    return round(degrees / _SCALE)


def _point(number: int, latitude: float, longitude: float, *, flag: int = 0) -> dict:
    return {
        "PointNumber": number,
        "Latitude": _semicircles(latitude),
        "Longitude": _semicircles(longitude),
        "Closure": 0,
        "Flag": flag,
    }


def _line(code: int, flags: int, points: list[dict], *, length: int | None = None) -> dict:
    if length is None:
        first_latitude = points[0]["Latitude"] * _SCALE
        second_latitude = points[-1]["Latitude"] * _SCALE
        first_longitude = points[0]["Longitude"] * _SCALE
        second_longitude = points[-1]["Longitude"] * _SCALE
        north = math.radians(second_latitude - first_latitude) * _EARTH_RADIUS_METRES
        east = (
            math.radians(second_longitude - first_longitude)
            * math.cos(math.radians((first_latitude + second_latitude) / 2))
            * _EARTH_RADIUS_METRES
        )
        length = round(math.hypot(east, north))
    return {
        "LineId": code,
        "LineCode": code,
        "CoordinateCount": len(points),
        "Length": length,
        "Flags": flags,
        "Points": points,
    }


def _payload() -> dict:
    route = [
        _point(1, 1.0000, 2.0000),
        _point(2, 1.0015, 2.0000, flag=1),
        _point(3, 1.0030, 2.0000),
    ]
    return {
        "BuildId": 7,
        "GlobalLayoutId": 123,
        "Group": 0,
        "Holes": [
            {
                "HoleNumber": 1,
                "InfoMask": 8,
                "GreenRadii": [10] * 30,
                "Line": [
                    # Garmin emits this uint32 bit pattern as a signed JSON number in
                    # some builds: 0x80000002 == -2147483646.
                    _line(3240, -2_147_483_646, route),
                    _line(
                        3241,
                        1,
                        [_point(1, 1.0010, 2.0003), _point(2, 1.0012, 2.0003)],
                    ),
                    _line(
                        3242,
                        2,
                        [_point(1, 1.0014, 1.9997), _point(2, 1.0016, 1.9997)],
                    ),
                    _line(
                        3243,
                        3,
                        [_point(1, 1.0018, 1.9999), _point(2, 1.0020, 2.0001)],
                    ),
                    _line(
                        3244,
                        3,
                        [_point(1, 1.0008, 2.0000), _point(2, 1.0022, 2.0000)],
                    ),
                ],
                "Pars": [],
                "Hazards": [
                    {
                        "Code": 18123,
                        "Flags": 1,
                        "Latitude": _semicircles(1.0011),
                        "Longitude": _semicircles(2.0003),
                    },
                    {
                        "Code": 18124,
                        "Flags": 2,
                        "Latitude": _semicircles(1.0015),
                        "Longitude": _semicircles(1.9997),
                    },
                    {
                        "Code": 18125,
                        "Flags": 3,
                        "Latitude": _semicircles(1.0019),
                        "Longitude": _semicircles(2.0000),
                    },
                ],
                "Handicaps": [],
            }
        ],
        "Tees": [],
    }


def _write_corpus(root: Path, payload: dict) -> tuple[Path, Path]:
    artifact = root / "123_7_medium-plus.json"
    artifact.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
    manifest = root / "fetch-manifest.json"
    manifest.write_text(
        json.dumps(
            [
                {
                    "gid": 123,
                    "build": 7,
                    "url": "https://omt.garmin.cn/CourseViewData/courseData/7,123,32/Hazards",
                    "status": "ok",
                    "bytes": artifact.stat().st_size,
                    "holes": 1,
                }
            ]
        ),
        encoding="utf-8",
    )
    return artifact, manifest


class CourseDataCorpusAuditTests(unittest.TestCase):
    def test_closes_route_flags_sides_subspan_and_opaque_category(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _, manifest = _write_corpus(root, _payload())

            report = audit_course_data_corpus(root, fetch_manifest=manifest)
            repeated = audit_course_data_corpus(root, fetch_manifest=manifest)

        self.assertTrue(report["gates"]["passed"])
        self.assertEqual(report["routeFlags"]["infoMaskChecked"], 1)
        self.assertEqual(report["routeFlags"]["pointFlagBitsetChecked"], 1)
        self.assertEqual(report["rawInventory"]["closureCounts"], {"0": 11})
        self.assertEqual(report["hazardSideFlags"]["singleSideChecked"], 4)
        self.assertEqual(report["hazardSideFlags"]["singleSideAgreementRatio"], 1.0)
        self.assertEqual(report["routeSubspan3244"]["lineCount"], 1)
        self.assertEqual(
            report["opaqueThirdHazardCategory"]["classification"],
            "garmin-third-opaque-hazard-category",
        )
        self.assertEqual(report_bytes(report), report_bytes(repeated))

    def test_reports_authority_and_route_bitset_drift(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            payload = _payload()
            payload["Holes"][0]["Line"][0]["Flags"] = 4 << 28
            artifact, manifest = _write_corpus(root, payload)
            manifest_rows = json.loads(manifest.read_text(encoding="utf-8"))
            manifest_rows[0]["bytes"] = artifact.stat().st_size + 1
            manifest.write_text(json.dumps(manifest_rows), encoding="utf-8")

            report = audit_course_data_corpus(root, fetch_manifest=manifest)

        self.assertFalse(report["gates"]["passed"])
        self.assertFalse(report["gates"]["fetchManifestBound"])
        self.assertFalse(report["gates"]["routePointFlagsEqualFlagsLow28Bitset"])
        self.assertEqual(report["routeFlags"]["pointFlagBitsetMismatchCount"], 1)


if __name__ == "__main__":
    unittest.main()
