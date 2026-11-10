"""Stats windows pick exactly the rounds they promise (test-plan S-15), checked on the public window filter."""
from datetime import date, timedelta

from ai_caddie.history.history import HistoryData
from ai_caddie.history.history_stats import windowed_history_data
from tests.support.hermetic import SmallTestCase

START = date(2025, 1, 1)


def ladder(count):
    # `count` rounds on consecutive days, deliberately stored oldest-last so input order is not date order.
    rounds = [{"id": f"r{index:02d}", "ids": [f"r{index:02d}"], "date": (START + timedelta(days=index)).isoformat(),
               "holesCompleted": 18, "strokes": 80 + index} for index in range(count)]
    rounds.reverse()
    shots = [{"roundId": row["id"], "hole": 1, "order": 1} for row in rounds]
    return HistoryData(raw_rounds=[{"id": row["id"]} for row in rounds], rounds=rounds, shots=shots)


def ids_of(rows, key="id"):
    return sorted(str(row[key]) for row in rows)


def newest(count, first, size):
    # Round ids for the newest-first slice [first, first + size) of a `count`-round ladder.
    return sorted(f"r{index:02d}" for index in range(count - 1 - first, count - 1 - first - size, -1) if index >= 0)


class Windows(SmallTestCase):
    def test_recent_n_boundaries(self):
        """S-15: last-10 and last-20 keep the newest 10 or 20 rounds and prev-10 the ten before them."""
        rows = [
            # rounds, kept by last10, last20, prev10 (newest round index is count-1)
            (0, [], [], []),
            (1, ["r00"], ["r00"], []),
            (9, newest(9, 0, 9), newest(9, 0, 9), []),
            (10, newest(10, 0, 10), newest(10, 0, 10), []),
            (11, newest(11, 0, 10), newest(11, 0, 11), ["r00"]),        # only r00 is older than the newest 10
            (19, newest(19, 0, 10), newest(19, 0, 19), newest(19, 10, 9)),
            (20, newest(20, 0, 10), newest(20, 0, 20), newest(20, 10, 10)),
            (21, newest(21, 0, 10), newest(21, 0, 20), newest(21, 10, 10)),  # r00 falls out of last20
        ]
        for count, last10, last20, prev10 in rows:
            data = ladder(count)
            for window, expected in (("last10", last10), ("last20", last20), ("prev10", prev10)):
                with self.subTest(rounds=count, window=window):
                    kept = windowed_history_data(data, window)
                    self.assertEqual(ids_of(kept.rounds), expected)
                    self.assertEqual(ids_of(kept.shots, "roundId"), expected)      # shots follow their round
                    self.assertEqual(ids_of(kept.raw_rounds), expected)
        self.assertEqual(len(ladder(21).rounds), 21)  # the filter never mutates its input

    def test_explicit_boundary_ids(self):
        """S-15: the 11th-newest round is outside last-10 and the 21st-newest is outside last-20."""
        data = ladder(21)  # r20 is newest, r10 is the 11th-newest, r00 the 21st-newest
        self.assertNotIn("r10", ids_of(windowed_history_data(data, "last10").rounds))
        self.assertIn("r11", ids_of(windowed_history_data(data, "last10").rounds))
        self.assertNotIn("r00", ids_of(windowed_history_data(data, "last20").rounds))
        self.assertIn("r01", ids_of(windowed_history_data(data, "last20").rounds))

    def test_twelve_month_window_is_anchored_on_newest_round(self):
        """S-15: the 12-month window keeps rounds within 365 days of the newest round, whatever today is."""
        rounds = [{"id": rid, "date": day, "strokes": 80}
                  for rid, day in (("new", "2026-06-01"), ("edge", "2025-06-01"), ("old", "2025-05-31"))]
        # 2026-06-01 minus 365 days is 2025-06-01: "edge" is kept, "old" (one day earlier) is not.
        data = HistoryData(raw_rounds=[], rounds=rounds, shots=[])
        self.assertEqual(ids_of(windowed_history_data(data, "12m").rounds), ["edge", "new"])
        self.assertEqual(ids_of(windowed_history_data(data, "prev12m").rounds), ["old"])

    def test_unknown_window_is_refused(self):
        """S-15: an unknown stats window is an error, not a silent fall back to all rounds."""
        with self.assertRaises(ValueError):
            windowed_history_data(ladder(3), "last7")
