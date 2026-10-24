"""C16b fixture generator (J2 看成绩与复盘). Decides INPUT ONLY — no expected values here.

Run:  python3 tests/product/fixtures/c16b/make_fixture.py
Writes Garmin-shaped raw files under tests/product/fixtures/c16b/player/ :
  scorecards/<id>.json   (scorecardDetails[0].scorecard + courseSnapshots[0], the raw Garmin
                          envelope the product's real loader reads; manual phone rounds use the
                          same envelope with "source": "manual")
  shots/<id>.json        (holeShots[].shots[] + clubDetails[], Garmin shot-file shape)
  club_bag.json          (the player's synced Garmin bag)
and annotations.json (putt corrections the test POSTs through /api/v2/annotations).

This file must not import any product module. Every hole is checked physically legal
(strokes >= putts + penalties + 1) before anything is written.

Courses
  Kestrel Hills  27 holes, three nine-hole loops, each its own Garmin id:
                 A = 7101, B = 7102, C = 7103 (each loop is holes 1-9 of its own id)
  Lark Valley    one 18-hole course, id 7201 (front = holes 1-9, back = holes 10-18)
  Pine Field     18 holes, no Garmin id at all ("无 id")

Hole scores are written as to-par strings, one char per hole:
  e = -2 (eagle)  b = -1 (birdie)  0 = par  1 = bogey  2 = double  3 = triple  4 = quad
Putts rule (holes that record putts): eagle/birdie 1, par/bogey/double 2, triple+ 3, then the
round's explicit overrides. Fairway rule (Garmin rounds, non-par-3 holes): to-par <= 0 -> HIT,
to-par 1 -> LEFT on odd holes / RIGHT on even holes, to-par >= 2 -> RIGHT.
Manual rounds record no fairway. Garmin rounds carry no penalties field (Garmin never sends it).
Manual rounds record penalties on every hole (0 unless listed). A manual "default" hole is the
phone's unedited default: strokes = par, putts 2, penalties 0, scoreSource "default".
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "player"

PARS = {
    "A": [4, 4, 3, 5, 4, 4, 3, 4, 5],
    "B": [4, 5, 3, 4, 4, 3, 4, 5, 4],
    "C": [5, 4, 4, 3, 4, 4, 5, 3, 4],
    "LV": [4, 5, 4, 3, 4, 4, 5, 3, 4, 4, 4, 3, 5, 4, 4, 3, 5, 4],
    "PF": [4, 4, 4, 3, 5, 4, 4, 3, 5, 4, 4, 4, 3, 5, 4, 4, 3, 5],
}
GID = {"A": 7101, "B": 7102, "C": 7103, "LV": 7201, "PF": None}
VENUE = {"A": "Kestrel Hills", "B": "Kestrel Hills", "C": "Kestrel Hills", "LV": "Lark Valley", "PF": "Pine Field"}
VENUE_LATLON = {"Kestrel Hills": (31.20, 121.40), "Lark Valley": (31.30, 121.50), "Pine Field": (31.10, 121.30)}

# 18-hole to-par templates (front nine + back nine). The number is the to-par total.
T = {
    6: "0b0110100" "10010b111",
    9: "010110120" "1001b1010",
    11: "101110120" "1101b0110",
    12: "110110210" "1101b1110",
    13: "110120110" "1011b1201",
    14: "111120110" "1101b1201",
    15: "121110120" "1101b1201",
    16: "121101210" "1120b1111",
    17: "121120121" "1110b1201",
    18: "122110121" "1110b1211",
    20: "122120122" "1110b1211",
    23: "1e1312142" "110211112",
}
# 9-hole to-par strings
N = {
    "B6": "101101110",   # +6
    "B5": "1010b1110",   # +4  (b on hole 5)
    "C8": "112101110",   # +8
    "A7": "101111110",   # +7
    "C9": "111110121",   # +9
    "LVb7": "110b11111",  # +6 on Lark holes 10-18
}

TO_PAR = {"e": -2, "b": -1, "0": 0, "1": 1, "2": 2, "3": 3, "4": 4}

# One row per scorecard card. pos = date order, 1 = newest. P25a/P25b are two 9-hole cards
# played the same day (merged by the product into one 18-hole round).
# layout: "A/B" (composite of two Kestrel loops), "A" (one Kestrel loop, 9 holes),
#         "LV" (Lark 18), "LVback" (Lark holes 10-18 only), "PF" (Pine 18, no id)
ROUNDS = [
    # pos, id,        date-time,             layout, src, tpl, priceable, putts, extra
    ("P1", 310000211, "2026-09-27T08:10:00", "A/B", "garmin", 9, True, True,
     {"putt": {7: 3, 13: 1}, "shots": "P1"}),
    ("P2", 310000027, "2026-09-12T08:20:00", "B/A", "manual", 6, False, True,
     {"default": [6, 12, 14], "putt": {9: 1}}),
    ("P3", 310000310, "2026-08-30T07:50:00", "LV", "garmin", 13, True, True,
     {"putt": {5: 3, 10: 1}, "shots": "P3"}),
    ("P4", 310000105, "2026-08-09T08:00:00", "A/A", "manual", 9, False, True,
     {"pen": {8: 1}}),
    ("P5", 310000420, "2026-07-19T09:00:00", "PF", "manual", 11, False, True,
     {"pen": {8: 1}, "putt": {2: 1}}),
    ("P6", 310000013, "2026-07-04T08:30:00", "B/C", "garmin", 9, True, True, {"putt": {11: 0}}),
    ("P7", 310000398, "2026-06-27T08:15:00", "A/B", "garmin", 16, True, True,
     {"putt": {2: 3, 9: 1}, "shots": "P7"}),
    ("P8", 310000077, "2026-06-14T08:05:00", "LV", "garmin", 9, True, True, {"putt": {15: 3}}),
    ("P9", 310000256, "2026-06-02T08:40:00", "C/A", "manual", 12, False, True,
     {"default": [3, 6], "pen": {7: 1}}),
    ("P10", 310000141, "2026-05-17T08:00:00", "A/B", "garmin", 9, True, True, {"putt": {1: 1}}),
    ("P11", 310000333, "2026-04-26T08:00:00", "LV", "garmin", 18, False, True, {"putt": {4: 3}}),
    ("P12", 310000002, "2026-04-05T08:00:00", "B/A", "garmin", 14, True, True,
     {"putt": {10: 3}, "shots": "P12"}),
    ("P13", 310000188, "2026-03-15T08:00:00", "A/B", "garmin", 9, True, True, {}),
    ("P14", 310000270, "2026-02-22T08:00:00", "LV", "garmin", 15, True, True, {"putt": {12: 1}}),
    ("P15", 310000055, "2026-01-31T08:00:00", "B/C", "garmin", 9, True, True, {}),
    ("P16", 310000366, "2026-01-10T08:00:00", "A/B", "garmin", 17, True, True, {"putt": {17: 3}}),
    ("P17", 310000099, "2025-12-20T08:00:00", "LV", "garmin", 20, False, True, {}),
    ("P18", 310000232, "2025-12-06T08:00:00", "B/A", "garmin", 9, True, True, {}),
    ("P19", 310000164, "2025-11-15T08:00:00", "A/B", "garmin", 18, True, True, {"putt": {3: 1}}),
    ("P20", 310000301, "2025-11-01T08:00:00", "B/C", "garmin", 9, True, True, {}),
    ("P21", 310000044, "2025-10-12T08:00:00", "A/B", "garmin", 13, True, True, {}),
    ("P22", 310000289, "2025-09-20T08:00:00", "LVback", "garmin", "LVb7", False, True, {}),
    ("P23", 310000122, "2025-08-24T08:00:00", "B", "garmin", "B6", False, True, {}),
    ("P24", 310000377, "2025-07-27T08:00:00", "B/A", "garmin", 13, True, True, {}),
    ("P25a", 310000066, "2025-06-29T08:00:00", "A", "garmin", "A7", False, True, {}),
    ("P25b", 310000245, "2025-06-29T10:30:00", "C", "garmin", "C9", False, True, {}),
    ("P26", 310000199, "2025-05-25T08:00:00", "LV", "garmin", 13, True, True, {}),
    ("P27", 310000318, "2025-04-20T08:00:00", "C", "garmin", "C8", False, False, {}),
    ("P28", 310000088, "2025-03-16T08:00:00", "A/B", "garmin", 13, True, False, {}),
    ("P29", 310000355, "2025-02-09T08:00:00", "LV", "garmin", 23, False, False, {}),
    ("P30", 310000177, "2025-01-19T08:00:00", "B", "garmin", "B5", False, False, {}),
    ("P31", 310000011, "2024-12-15T08:00:00", "B/A", "garmin", 13, True, False, {}),
]

# Shot sequences (non-putt strokes only, so len == strokes - putts). Each entry:
# hole -> list of (club key, end lie). Distances are drawn in order from DIST[club key].
SHOTS = {
    "P1": {1: [("D1", "Fairway"), ("7I", "Green")],
           4: [("D2", "Fairway"), ("7I", "Rough"), ("PW", "Rough"), ("PW", "Green")],
           5: [("D1", "Rough"), ("7I", "Fairway"), ("PW", "Green")],
           9: [("D2", "Fairway"), ("7I", "Fairway"), ("PW", "Green")],
           12: [("7I", "Green")]},
    "P3": {1: [("D1", "Fairway"), ("7I", "Rough"), ("PW", "Green")],
           2: [("D2", "Rough"), ("7I", "Fairway"), ("PW", "Bunker"), ("UK", "Green")],
           6: [("D1", "Fairway"), ("PW", "Green")],
           11: [("D2", "Fairway"), ("7I", "Green")]},
    "P7": {1: [("D1", "Fairway"), ("7I", "Rough"), ("UK", "Green")],
           3: [("PW", "Bunker"), ("UK", "Green")],
           5: [("3W", "Fairway"), ("PW", "Green")],
           14: [("D2", "Fairway"), ("7I", "Green")]},
    "P12": {1: [("D1", "Rough"), ("7I", "Fairway"), ("PW", "Green")],
            12: [("PW", "Green")]},
}
# Driver is logged under two Garmin clubs with the same name in different case:
# D1 = clubId 101 "Driver", D2 = clubId 102 "driver". UK = clubId 0 (Garmin "no club").
CLUB_DETAILS = [
    {"clubId": 101, "name": "Driver"},
    {"clubId": 102, "name": "driver"},
    {"clubId": 103, "name": "3W"},
    {"clubId": 107, "name": "7I"},
    {"clubId": 110, "name": "PW"},
]
CLUB_ID = {"D1": 101, "D2": 102, "3W": 103, "7I": 107, "PW": 110, "UK": 0}
DIST = {
    "D1": [205, 210, 212, 215, 218, 220],
    "D2": [222, 225, 228, 230, 235],
    "3W": [195],
    "7I": [138, 140, 142, 144, 146, 148, 150, 152, 154, 156, 158],
    "PW": [95, 98, 100, 102, 104, 105, 106, 108, 110, 112, 115],
    "UK": [60, 120, 180],
}

CLUB_BAG = {
    "clubs": [
        {"id": 101, "clubTypeId": 1, "customName": "Driver", "adviceDistance": 215, "averageDistance": 0,
         "retired": False, "deleted": False},
        {"id": 107, "clubTypeId": 7, "customName": "7I", "adviceDistance": 145, "averageDistance": 0,
         "retired": False, "deleted": False},
        {"id": 110, "clubTypeId": 10, "customName": "PW", "adviceDistance": 0, "averageDistance": 0,
         "retired": False, "deleted": False},
    ]
}


def semicircle(deg: float) -> int:
    return int(round(deg * (2 ** 31) / 180.0))


def layout_pars(layout: str) -> tuple[list[int], int | None, int | None, int | None, str, list[int]]:
    """(per-hole pars, courseGlobalId, front id, back id, name suffix, hole numbers)."""
    if layout in ("LV", "PF"):
        pars = PARS[layout]
        gid = GID[layout]
        return pars, gid, gid, None, "", list(range(1, 19))
    if layout == "LVback":
        return PARS["LV"][9:], 7201, 7201, None, "", list(range(10, 19))
    if "/" in layout:
        front, back = layout.split("/")
        return PARS[front] + PARS[back], GID[front], GID[front], GID[back], layout, list(range(1, 19))
    return PARS[layout], GID[layout], GID[layout], None, layout, list(range(1, 10))


def hole_pars_string(layout: str) -> str:
    if layout in ("LV", "LVback"):
        return "".join(map(str, PARS["LV"]))
    if layout == "PF":
        return "".join(map(str, PARS["PF"]))
    if "/" in layout:
        front, back = layout.split("/")
        return "".join(map(str, PARS[front] + PARS[back]))
    return "".join(map(str, PARS[layout]))


def default_putts(delta: int) -> int:
    if delta <= -1:
        return 1
    if delta <= 2:
        return 2
    return 3


def fairway(delta: int, number: int) -> str:
    if delta <= 0:
        return "HIT"
    if delta == 1:
        return "LEFT" if number % 2 else "RIGHT"
    return "RIGHT"


def build() -> None:
    if OUT.exists():
        shutil.rmtree(OUT)
    (OUT / "scorecards").mkdir(parents=True)
    (OUT / "shots").mkdir(parents=True)
    dist_queues = {key: list(values) for key, values in DIST.items()}
    for pos, sid, when, layout, src, tpl, priceable, has_putts, extra in ROUNDS:
        pars, gid, front, back, suffix, numbers = layout_pars(layout)
        deltas_text = T[tpl] if isinstance(tpl, int) else N[tpl]
        assert len(deltas_text) == len(pars) == len(numbers), pos
        defaults = set(extra.get("default", []))
        putt_over = extra.get("putt", {})
        pens = extra.get("pen", {})
        holes = []
        for index, (number, par) in enumerate(zip(numbers, pars)):
            delta = TO_PAR[deltas_text[index]]
            hole: dict = {"number": number}
            if number in defaults:
                assert delta == 0, f"{pos} default hole {number} must be a par in the template"
                hole.update({"strokes": par, "putts": 2, "penalties": 0, "scoreSource": "default"})
                holes.append(hole)
                continue
            strokes = par + delta
            hole["strokes"] = strokes
            putts = putt_over.get(number, default_putts(delta)) if has_putts else None
            if has_putts:
                hole["putts"] = putts
            if src == "manual":
                hole["penalties"] = pens.get(number, 0)
                hole["scoreSource"] = "manual_edit"
            elif par != 3:
                hole["fairwayShotOutcome"] = fairway(delta, number)
            need = (putts or 0) + int(hole.get("penalties") or 0) + 1
            assert strokes >= need, f"{pos} hole {number}: strokes {strokes} < putts+pen+1 {need}"
            holes.append(hole)
        total = sum(h["strokes"] for h in holes)
        if isinstance(tpl, int):
            assert total == sum(pars) + tpl, (pos, total)
        venue = VENUE["A" if layout[0] in "ABC" else ("LV" if layout.startswith("LV") else "PF")]
        name = f"{venue} ~ {suffix}" if suffix else venue
        lat, lon = VENUE_LATLON[venue]
        scorecard = {
            "id": sid,
            "formattedStartTime": when,
            "startTime": when,
            "strokes": total,
            "holesCompleted": len(holes),
            "courseGlobalId": gid,
            "frontNineGlobalCourseId": front,
            "backNineGlobalCourseId": back,
            "courseSnapshotId": None,
            "teeBox": "Blue",
            "teeBoxRating": 71.0 if priceable else None,
            "teeBoxSlope": 113 if priceable else None,
            "holes": holes,
        }
        raw = {
            "source": src,
            "scorecardDetails": [{"scorecard": scorecard, "scorecardStats": {"round": {}}}],
            "courseSnapshots": [{
                "name": name,
                "holePars": hole_pars_string(layout),
                "roundPar": sum(pars),
                "lat": int(lat * 1_000_000),
                "lon": int(lon * 1_000_000),
            }],
        }
        (OUT / "scorecards" / f"{sid}.json").write_text(json.dumps(raw, indent=1, ensure_ascii=False))

        shot_plan = SHOTS.get(extra.get("shots", ""), {})
        if shot_plan:
            hole_shots = []
            shot_id = sid * 100
            for number, sequence in sorted(shot_plan.items()):
                hole = next(h for h in holes if h["number"] == number)
                assert len(sequence) == hole["strokes"] - hole["putts"], (pos, number)
                rows = []
                cur_lat, cur_lon = lat + number * 0.001, lon
                for order, (club, end_lie) in enumerate(sequence, start=1):
                    meters = dist_queues[club].pop(0)
                    end_lat = cur_lat + meters / 111_000.0
                    shot_id += 1
                    rows.append({
                        "id": shot_id,
                        "shotOrder": order,
                        "clubId": CLUB_ID[club],
                        "meters": meters,
                        "shotType": "TEE" if order == 1 else "APPROACH",
                        "autoShotType": "USED",
                        "startLoc": {"lat": semicircle(cur_lat), "lon": semicircle(cur_lon),
                                     "lie": "TeeBox" if order == 1 else rows[-1]["endLoc"]["lie"]},
                        "endLoc": {"lat": semicircle(end_lat), "lon": semicircle(cur_lon), "lie": end_lie},
                    })
                    cur_lat = end_lat
                hole_shots.append({"holeNumber": number, "shots": rows})
            shot_file = {"scorecardId": sid, "holeShots": hole_shots, "clubDetails": CLUB_DETAILS}
            (OUT / "shots" / f"{sid}.json").write_text(json.dumps(shot_file, indent=1))
    leftover = {key: values for key, values in dist_queues.items() if values}
    assert not leftover, f"unused distances {leftover}"
    (OUT / "club_bag.json").write_text(json.dumps(CLUB_BAG, indent=1))
    ids = {pos: sid for pos, sid, *_ in ROUNDS}
    annotations = [
        # Default hole P2 #12 (scoreSource default, putts 2) corrected by the player to 1 putt.
        {"targetType": "hole", "targetId": f"{ids['P2']}:12", "kind": "putt_correction", "payload": {"to": 1}},
        # Normal hole P4 #5 (A loop par 4, bogey 5, 2 putts) corrected to 3 putts.
        {"targetType": "hole", "targetId": f"{ids['P4']}:5", "kind": "putt_correction", "payload": {"to": 3}},
    ]
    (HERE / "annotations.json").write_text(json.dumps(annotations, indent=1))
    (HERE / "round_ids.json").write_text(json.dumps(ids, indent=1))


if __name__ == "__main__":
    build()
    print("fixture written to", OUT)
