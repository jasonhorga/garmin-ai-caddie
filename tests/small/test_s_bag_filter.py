"""Club distances are summarised as a p10-p90 band that impossible readings cannot move (test-plan S-10).

Two public summaries are covered: ``history_clubs`` (the club table in history) and
``build_club_profiles`` (the measured ladder the caddie recommends from). Both pick the value at
index round((n - 1) * p) of the sorted samples; Python rounds .5 to the even integer.
"""
from ai_caddie.caddie.club_bag import garmin_distance_m
from ai_caddie.core.data import build_club_profiles
from ai_caddie.history.history import HistoryData, history_clubs
from tests.support.hermetic import SmallTestCase


def series(count):
    # 100, 105, 110, ... : `count` seven-iron readings, all well under the 185 m seven-iron cap.
    return [100.0 + 5 * index for index in range(count)]


def history_of(club, meters):
    shots = [{"clubName": club, "meters": value} for value in meters]
    return HistoryData(raw_rounds=[], rounds=[], shots=shots)


def profiles_of(club, meters):
    shots = [{"club": club, "distance": value, "type": "APPROACH"} for value in meters]
    return build_club_profiles(history_data=HistoryData(raw_rounds=[], rounds=[], shots=shots))


ROWS = [
    # label, readings, then expected (sampleSize, p10, median, p90, confidence)
    ("one", series(1), (1, 100.0, 100.0, 100.0, "low")),            # every percentile is the only sample
    # n=9: indexes p10 round(0.8)=1 -> 105, median 4 -> 120, p90 round(7.2)=7 -> 135
    ("nine", series(9), (9, 105.0, 120.0, 135.0, "low")),
    # n=10: p10 round(0.9)=1 -> 105, median round(4.5)=4 -> 120, p90 round(8.1)=8 -> 140; 10 is "medium"
    ("ten", series(10), (10, 105.0, 120.0, 140.0, "medium")),
    # n=11: p10 1 -> 105, median 5 -> 125, p90 9 -> 145
    ("eleven", series(11), (11, 105.0, 125.0, 145.0, "medium")),
    ("identical", [150.0] * 12, (12, 150.0, 150.0, 150.0, "medium")),  # no spread: the band collapses
    # A 20 m chunk among ten 150s: index 1 of 11 is already a 150, so the band ignores the mis-hit.
    ("low_mishit", [20.0] + [150.0] * 10, (11, 150.0, 150.0, 150.0, "medium")),
]


class P10P90(SmallTestCase):
    def test_boundaries(self):
        """S-10: the club band is p10-p90 at 0, 1, 9, 10, 11 samples, identical readings and an extreme outlier."""
        for label, readings, (size, p10, median, p90, confidence) in ROWS:
            with self.subTest(case=label):
                club = history_clubs(history_of("7I", readings))["clubs"][0]
                self.assertEqual((club["sampleSize"], club["p10"], club["median"], club["p90"], club["confidence"]),
                                 (size, p10, median, p90, confidence))
                ladder = profiles_of("7I", readings)["7I"]
                self.assertEqual((ladder["sampleSize"], ladder["p10"], ladder["median"], ladder["p90"]),
                                 (size, p10, median, p90))

        with self.subTest(case="zero"):
            empty = history_clubs(history_of("7I", []))
            self.assertEqual((empty["clubs"], empty["totalShotsUsed"], empty["droppedOutliers"]), ([], 0, 0))
            self.assertEqual(profiles_of("7I", []), {})

        with self.subTest(case="extreme_outlier"):
            # A 900 m "seven-iron" is above the 185 m seven-iron cap: dropped and counted, not averaged in.
            table = history_clubs(history_of("7I", [150.0] * 10 + [900.0]))
            club = table["clubs"][0]
            self.assertEqual((table["droppedOutliers"], table["totalShotsUsed"]), (1, 10))
            self.assertEqual((club["p10"], club["median"], club["p90"], club["max"]), (150.0, 150.0, 150.0, 150.0))
            # The ladder keeps the reading but it sits above p90: index 9 of 11 sorted values is still 150.
            ladder = profiles_of("7I", [150.0] * 10 + [900.0])["7I"]
            self.assertEqual((ladder["sampleSize"], ladder["median"], ladder["p90"]), (11, 150.0, 150.0))

    def test_cap_and_floor_readings(self):
        """S-10: readings at the club cap are kept, readings just over it are outliers and non-shots are ignored."""
        rows = [
            # readings, kept samples, dropped outliers
            ([185.0], 1, 0),        # exactly the seven-iron cap
            ([185.1], 0, 1),        # just over the cap
            ([1.0, 0.0], 0, 0),     # 1 m or less is not a shot at all (neither kept nor an outlier)
            ([1.1], 1, 0),
        ]
        for readings, kept, dropped in rows:
            with self.subTest(readings=readings):
                table = history_clubs(history_of("7I", readings))
                self.assertEqual((table["totalShotsUsed"], table["droppedOutliers"]), (kept, dropped))
        unnamed = history_clubs(HistoryData(raw_rounds=[], rounds=[], shots=[
            {"clubName": "Unknown", "meters": 150.0}, {"clubName": "?", "meters": 150.0}, {"meters": 150.0}]))
        self.assertEqual(unnamed["clubs"], [])  # a reading with no club cannot describe a club
        putts = profiles_of("Putter", [3.0, 8.0])  # under the ladder's 5 m floor
        self.assertEqual(putts["Putter"]["sampleSize"], 1)

    def test_garmin_distance_must_be_plausible(self):
        """S-10: a Garmin distance is used only inside 5-350 m, advice before average, otherwise it is absent."""
        rows = [
            # adviceDistance, averageDistance, expected (metres, source) or None
            (230, 225, (230, "garmin_advice")),
            (0, 150, (150, "garmin_average")),      # Garmin sends zero when it has no advice
            (4, 150, (150, "garmin_average")),      # just under the 5 m floor
            (5, None, (5, "garmin_advice")),
            (350, None, (350, "garmin_advice")),
            (351, 349.6, (350, "garmin_average")),  # over the ceiling; the average rounds to 350
            (True, None, None),                     # a boolean is not a distance
            ("200", None, None),                    # nor is text
            (0, 0, None),
            (None, None, None),
        ]
        for advice, average, expected in rows:
            with self.subTest(advice=advice, average=average):
                self.assertEqual(garmin_distance_m({"adviceDistance": advice, "averageDistance": average}), expected)
