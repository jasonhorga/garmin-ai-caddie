from __future__ import annotations

from ai_caddie.history.history import HistoryData


def _holes(scores: list[int], pars: list[int]) -> list[dict[str, object]]:
    return [
        {
            "number": index + 1,
            "strokes": score,
            "par": pars[index],
            "putts": 2 if score <= pars[index] + 1 else 3,
            "gir": score <= pars[index],
            "fairway": "hit" if index % 3 else "right",
        }
        for index, score in enumerate(scores)
    ]


def fixture_history_data() -> HistoryData:
    pars18 = [4, 5, 4, 3, 4, 4, 5, 3, 4, 4, 5, 4, 3, 4, 4, 5, 3, 4]
    black_scores_good = [4, 5, 4, 3, 5, 4, 6, 3, 4, 4, 5, 5, 3, 4, 5, 5, 4, 4]
    black_scores_bad = [5, 6, 5, 4, 6, 5, 7, 4, 5, 5, 6, 6, 4, 5, 6, 7, 4, 5]
    bay_scores = [4, 4, 5, 3, 4, 5, 5, 4, 4]
    pars9 = pars18[:9]

    rounds = [
        {
            "id": 900001,
            "ids": [900001],
            "date": "2026-05-18",
            "course": "Black Knight B/C",
            "courseCanonical": "Black Knight",
            "courseKey": "black_knight",
            "globalId": 31795,
            "holesCompleted": 18,
            "strokes": sum(black_scores_good),
            "par": sum(pars18),
            "holePars": "".join(str(p) for p in pars18),
            "holes": _holes(black_scores_good, pars18),
            "hasShots": True,
            "shotStatus": "fixture shots ready",
        },
        {
            "id": 900002,
            "ids": [900002],
            "date": "2026-04-26",
            "course": "Black Knight B/C",
            "courseCanonical": "Black Knight",
            "courseKey": "black_knight",
            "globalId": 31795,
            "holesCompleted": 18,
            "strokes": sum(black_scores_bad),
            "par": sum(pars18),
            "holePars": "".join(str(p) for p in pars18),
            "holes": _holes(black_scores_bad, pars18),
            "hasShots": True,
            "shotStatus": "fixture shots ready",
        },
        {
            "id": 900003,
            "ids": [900003],
            "date": "2026-03-09",
            "course": "Bay Practice Nine",
            "courseCanonical": "Bay Practice",
            "courseKey": "bay_practice",
            "globalId": 41825,
            "holesCompleted": 9,
            "strokes": sum(bay_scores),
            "par": sum(pars9),
            "holePars": "".join(str(p) for p in pars9),
            "holes": _holes(bay_scores, pars9),
            "hasShots": False,
            "shotStatus": "fixture missing shots",
        },
    ]
    shots = [
        {"roundId": 900001, "hole": 1, "club": "1D", "distance": 238, "surface": "fairway"},
        {"roundId": 900001, "hole": 1, "club": "8I", "distance": 142, "surface": "green"},
        {"roundId": 900001, "hole": 2, "club": "3W", "distance": 211, "surface": "fairway"},
        {"roundId": 900001, "hole": 2, "club": "58", "distance": 76, "surface": "green"},
        {"roundId": 900002, "hole": 5, "club": "1D", "distance": 225, "surface": "rough"},
        {"roundId": 900002, "hole": 7, "club": "5I", "distance": 168, "surface": "water"},
    ]
    raw_rounds = [{"id": row["id"], "hasShots": row["hasShots"]} for row in rounds]
    return HistoryData(raw_rounds=raw_rounds, rounds=rounds, shots=shots)
