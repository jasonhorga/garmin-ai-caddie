"""The Garmin scorecard ``pin`` is a green-CENTER reference, NOT the day's real flag.

``normalize_garmin_hole`` derives a hole's ``pin`` from the shot file's fixed ``pinPosition``
field. Deterministic verification established that ``pinPosition`` is Garmin's FIXED green-CENTER
reference point -- the same hole played 4 months apart landed within <12m of itself, both sitting
at green center -- so it is NOT the live hole/flag position.

These tests lock that provenance: they prove ``pin`` is taken from the fixed ``pinPosition`` field
(green center) and NOT from any per-shot endpoint, so a future change can't silently re-source
``pin`` from a moving/flag coordinate and mislead the user by presenting green center as the real
pin. The human-facing contract is "到果岭中心" (distance to green center).
"""
from __future__ import annotations

import types
import unittest
from unittest import mock

from ai_caddie.core import data as core_data
from ai_caddie.core.data import normalize_garmin_hole, semicircle_to_deg

# A pinPosition in Garmin semicircles (a green-center point ~47.7N/138.9E). A DECOY shot endpoint
# sits ~0.08deg away so the tests can prove ``pin`` comes from pinPosition, not from a shot.
GREEN_CENTER_LAT_SEMI = 569_000_000
GREEN_CENTER_LON_SEMI = 1_658_000_000
DECOY_LAT_SEMI = 570_000_000
DECOY_LON_SEMI = 1_659_000_000


def _fake_shot_data() -> dict:
    return {
        "holeShots": [
            {
                "holeNumber": 7,
                # The FIXED green-center reference Garmin ships on the scorecard.
                "pinPosition": {"lat": GREEN_CENTER_LAT_SEMI, "lon": GREEN_CENTER_LON_SEMI},
                "shots": [
                    # A real shot ends somewhere OTHER than pinPosition; pin must not come from here.
                    {
                        "id": "s1",
                        "shotOrder": 1,
                        "endLoc": {"lat": DECOY_LAT_SEMI, "lon": DECOY_LON_SEMI},
                    },
                ],
            }
        ]
    }


class ScorecardPinIsGreenCenterTest(unittest.TestCase):
    def _normalize(self) -> dict:
        # Isolate the ``pin`` derivation from disk I/O and unrelated summary/geometry helpers.
        with mock.patch.object(
            core_data,
            "load_scorecard",
            return_value={"scorecardDetails": [{"scorecard": {"holes": []}}]},
        ), mock.patch.object(
            core_data, "load_shot_file", return_value=_fake_shot_data()
        ), mock.patch.object(
            core_data, "scorecard_summary", return_value={}
        ), mock.patch.object(
            core_data,
            "round_hole_ref",
            return_value=types.SimpleNamespace(global_id=31795, local_hole=7),
        ), mock.patch.object(
            core_data, "_snapshot_pixel_lookup", return_value={}
        ), mock.patch.object(
            core_data, "club_name_from_details", return_value="Unknown"
        ):
            return normalize_garmin_hole("sc1", 7)

    def test_pin_is_derived_from_pinPosition_green_center(self) -> None:
        pin = self._normalize()["pin"]
        self.assertIsNotNone(pin)
        # pin is exactly the WGS84 of the FIXED pinPosition (Garmin's green-center reference).
        self.assertAlmostEqual(pin["lat"], semicircle_to_deg(GREEN_CENTER_LAT_SEMI))
        self.assertAlmostEqual(pin["lon"], semicircle_to_deg(GREEN_CENTER_LON_SEMI))

    def test_pin_is_not_a_shot_endpoint_or_live_flag(self) -> None:
        pin = self._normalize()["pin"]
        # It must NOT be a per-shot endpoint (which would be a real/moving-position proxy, i.e. the
        # kind of thing that could be mistaken for the live flag).
        self.assertNotAlmostEqual(pin["lat"], semicircle_to_deg(DECOY_LAT_SEMI))
        self.assertNotAlmostEqual(pin["lon"], semicircle_to_deg(DECOY_LON_SEMI))


if __name__ == "__main__":
    unittest.main()
