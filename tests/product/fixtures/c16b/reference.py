"""C16b independent reference calculation -> golden.json. Imports NO product module.

Run after make_fixture.py:  python3 tests/product/fixtures/c16b/reference.py
Reads only the raw fixture files and applies the definitions written in the product docs:

  [SPEC]   docs/product/2026-10-23-product-test-spec.md  J2 2.1-2.11
  [UI9]    docs/design/2026-09-25-ui-redesign/README.md  §4 (GIR = 第一推是第几杆 <= Par-1), §7, §9
  [B0c]    IMPLEMENTATION_PLAN.md B0c  (默认未改洞退出推杆/GIR 分子分母，推杆订正后重新计入)
  [B0d1]   IMPLEMENTATION_PLAN.md B0d-1 (putting 0/1/2/3+, penalties, scrambling, roundSequences,
           loops, nineCombos, nineOnlyRounds, hardestHoles)
  [B5a]    IMPLEMENTATION_PLAN.md B5a (和之前比 = 前一个满额周期；全部不比；handicapChangeRecent20)
  [MERGE]  docs/product/2026-08-12-history-performance-merged-design.md §2 (范围 / 粒度)
  [MANUAL] docs/product/2026-06-29-product-manual.md §3 (WHS handicap; effective bag manual>garmin>empty)
  [GUIDE]  docs/USER_GUIDE.md 3.3 (成绩构成 7 维；球杆合并大小写、剔除 Unknown)

Every golden value is written as {"value": ..., "formula": "..."}; the formula lists the items.
Where the docs leave a choice open the fixture is built so every reasonable reading gives the
same number; those spots say "ambiguity-proof" in the formula.
"""
from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
PLAYER = HERE / "player"
IDS = json.loads((HERE / "round_ids.json").read_text())
POS_BY_ID = {str(v): k for k, v in IDS.items()}
ANNOTATIONS = json.loads((HERE / "annotations.json").read_text())


def g(value, formula):
    return {"value": value, "formula": formula}


def r1(x):
    # one decimal, half up (all fixture averages are chosen away from .x5 ties where it matters)
    return None if x is None else float(f"{x + 1e-9:.1f}")


def r2(x):
    return None if x is None else float(f"{x + 1e-9:.2f}") if x >= 0 else -float(f"{-x + 1e-9:.2f}")


def venue_of(name: str) -> str:
    return name.split("~", 1)[0].strip()


def course_key(venue: str) -> str:
    # implementation contract (key format, not a statistic): "c_" + sha1(venue)[:10]
    return "c_" + hashlib.sha1(venue.encode("utf-8")).hexdigest()[:10]


# ---------------------------------------------------------------- load fixture cards
cards = []
for path in sorted((PLAYER / "scorecards").glob("*.json")):
    raw = json.loads(path.read_text())
    sc = raw["scorecardDetails"][0]["scorecard"]
    snap = raw["courseSnapshots"][0]
    pars = [int(c) for c in snap["holePars"]]
    cards.append({
        "id": str(sc["id"]), "pos": POS_BY_ID[str(sc["id"])], "when": sc["formattedStartTime"],
        "date": sc["formattedStartTime"][:10], "name": snap["name"], "venue": venue_of(snap["name"]),
        "source": raw["source"], "front": sc["frontNineGlobalCourseId"], "back": sc["backNineGlobalCourseId"],
        "gid": sc["courseGlobalId"], "rating": sc["teeBoxRating"], "slope": sc["teeBoxSlope"],
        "holesCompleted": sc["holesCompleted"], "holes": sc["holes"], "pars": pars,
    })

corrections = {a["targetId"]: a["payload"]["to"] for a in ANNOTATIONS if a["kind"] == "putt_correction"}


def build_round(card_list):
    """Normalise one or two (same-day 9-hole) cards into the round the player sees."""
    holes = []
    if len(card_list) == 2:
        first, second = sorted(card_list, key=lambda c: c["when"])
        rid = f"merged_{first['id']}_{second['id']}"
        parts = [(first, 0, "front", first["front"]), (second, 9, "back", second["front"])]
        name_suffix = "+".join(c["name"].split("~", 1)[1].strip() for c in (first, second))
        base = first
        layout_letters = (first["name"].split("~")[1].strip(), second["name"].split("~")[1].strip())
    else:
        base = card_list[0]
        rid = base["id"]
        parts = [(base, 0, None, None)]
        layout_letters = None
    for card, offset, forced_side, forced_gid in parts:
        for h in card["holes"]:
            number = int(h["number"])
            display = number + offset
            par = card["pars"][number - 1]
            if forced_side:
                side = forced_side
                gid = forced_gid
                physical = number
                loop_hole = number
            elif number > 9:
                side = "back"
                if card["back"]:
                    gid, physical, loop_hole = card["back"], number - 9, number - 9   # composite: back loop = holes 1-9 of its id
                else:
                    gid, physical, loop_hole = card["front"], number, number          # single 18 course: 10-18 of the same id
            else:
                side, gid, physical, loop_hole = "front", card["front"], number, number
            span = "10-18" if loop_hole > 9 else "1-9"
            key = f"gid:{gid}:{span}" if gid else f"course:{course_key(card['venue'])}:{span}"
            ref = f"{rid}:{display}"
            default = h.get("scoreSource") == "default"
            raw_putts = h.get("putts")
            corrected = ref in corrections
            eff_putts = corrections[ref] if corrected else (None if default else raw_putts)
            holes.append({
                "display": display, "number": number, "par": par, "strokes": h["strokes"],
                "rawPutts": raw_putts, "putts": eff_putts, "default": default, "corrected": corrected,
                "penalties": h.get("penalties"), "fairway": (h.get("fairwayShotOutcome") or "").lower() or None,
                "side": side, "gid": gid, "localHole": loop_hole if gid else None, "loopKey": key,
                "loopHole": loop_hole, "ref": ref,
            })
    holes.sort(key=lambda x: x["display"])
    score = sum(h["strokes"] for h in holes)
    hc = sum(c["holesCompleted"] for c in card_list)
    pos = base["pos"].rstrip("ab")
    return {
        "id": rid, "pos": pos, "date": base["date"], "when": base["when"], "venue": base["venue"],
        "name": base["name"] if len(card_list) == 1 else f"{base['venue']} ~ {name_suffix}",
        "source": base["source"], "holes": holes, "score": score, "holesCompleted": hc,
        "par": sum(h["par"] for h in holes),
        "priceable": len(card_list) == 1 and base["rating"] is not None and base["slope"] is not None,
        "rating": base["rating"] if len(card_list) == 1 else None, "slope": base["slope"] if len(card_list) == 1 else None,
        "courseKey": course_key(base["venue"]), "hasShots": (PLAYER / "shots" / f"{base['id']}.json").exists() and len(card_list) == 1,
        "cards": [c["id"] for c in card_list], "layoutLetters": layout_letters,
    }


by_day = defaultdict(list)
for c in cards:
    by_day[(c["date"], c["venue"])].append(c)
rounds = []
for (_d, _v), group in by_day.items():
    if len(group) == 2 and all(c["holesCompleted"] == 9 for c in group):
        rounds.append(build_round(group))
    else:
        for c in group:
            rounds.append(build_round([c]))
rounds.sort(key=lambda r: r["when"], reverse=True)          # newest first == P1..P31
assert [r["pos"] for r in rounds] == [f"P{i}" for i in range(1, 32)], [r["pos"] for r in rounds]
R = {r["pos"]: r for r in rounds}


def ids(rows):
    return [r["id"] for r in rows]


def plist(rows):
    return ",".join(r["pos"] for r in rows)


# ---------------------------------------------------------------- hole-level statistics
def gir_of(h):
    """[UI9 §4] GIR = 第一推是第几杆 <= Par-1  <=>  strokes - putts <= par - 2. Unknown putts -> unknown."""
    if h["putts"] is None:
        return None
    return h["strokes"] - h["putts"] <= h["par"] - 2


def hole_stats(rows):
    out = {}
    holes = [(r, h) for r in rows for h in r["holes"]]
    # putting [B0c, B0d1]
    elig = [(r, h) for r, h in holes if (not h["default"]) or h["corrected"]]
    with_putts = [(r, h) for r, h in elig if h["putts"] is not None]
    per_round = Counter(r["pos"] for r, _ in with_putts)
    putts_sum_round = defaultdict(int)
    for r, h in with_putts:
        putts_sum_round[r["pos"]] += h["putts"]
    buckets = Counter(min(h["putts"], 3) for _, h in with_putts)
    excl = [f"{r['pos']}#{h['display']}" for r, h in holes if h["default"] and not h["corrected"]]
    corr = [f"{r['pos']}#{h['display']}={h['putts']}" for r, h in holes if h["corrected"]]
    nop = Counter(r["pos"] for r, h in elig if h["putts"] is None)
    out["puttEligibleHoles"] = g(len(elig), f"{len(holes)} holes - {len(excl)} unedited default {excl} = {len(elig)} (corrected default holes stay in: {corr})")
    out["holesWithPutts"] = g(len(with_putts), "sum per round " + " + ".join(f"{p}:{n}" for p, n in per_round.items()) + f" = {len(with_putts)}; eligible holes without putts (Garmin did not record) {dict(nop)} are unknown, not 0")
    out["totalPutts"] = g(sum(putts_sum_round.values()), " + ".join(f"{p}:{n}" for p, n in putts_sum_round.items()) + f" = {sum(putts_sum_round.values())} (corrected values used: {corr})")
    for key, b in (("zeroPutts", 0), ("onePutts", 1), ("twoPutts", 2), ("threePlusPutts", 3)):
        listed = [f"{r['pos']}#{h['display']}" for r, h in with_putts if min(h["putts"], 3) == b] if b != 2 else None
        out[key] = g(buckets.get(b, 0), (f"holes {listed}" if listed is not None else f"{len(with_putts)} - zero {buckets.get(0,0)} - one {buckets.get(1,0)} - three+ {buckets.get(3,0)}") + f" = {buckets.get(b, 0)}")
    out["puttBucketsSum"] = g(len(with_putts), "zero+one+two+three+ = holesWithPutts (four buckets total 100%)")
    # GIR [B0c, SPEC 2.5]: default holes leave numerator and denominator; a putt-corrected hole counts with its corrected putts
    gir_known = [(r, h) for r, h in elig if gir_of(h) is not None]
    gir_hit = [(r, h) for r, h in gir_known if gir_of(h)]
    per_round_known = Counter(r["pos"] for r, _ in gir_known)
    per_round_hit = Counter(r["pos"] for r, _ in gir_hit)
    out["girRecorded"] = g(len(gir_known), "holes with known putts (GIR 按推杆推算 strokes-putts<=par-2) " + " + ".join(f"{p}:{n}" for p, n in per_round_known.items()) + f" = {len(gir_known)}")
    out["gir"] = g(len(gir_hit), " + ".join(f"{p}:{n}" for p, n in per_round_hit.items()) + f" = {len(gir_hit)}")
    out["girEligibleHoles"] = g(len(elig), "same denominator rule as putting: all holes minus unedited default holes")
    # scrambling [B0d1]: missed-GIR holes finishing at par or better
    missed = [(r, h) for r, h in gir_known if not gir_of(h)]
    saves = [(r, h) for r, h in missed if h["strokes"] <= h["par"]]
    out["scrambleChances"] = g(len(missed), f"girRecorded {len(gir_known)} - gir {len(gir_hit)} = {len(missed)}")
    save_list = [f"{r['pos']}#{h['display']}" for r, h in saves]
    out["scrambleSaves"] = g(len(saves), f"missed-GIR holes with strokes<=par: {save_list}")
    # tee [SPEC 2.5 未知不算失败]
    fw = [(r, h) for r, h in holes if h["fairway"]]
    fwc = Counter(h["fairway"] for _, h in fw)
    out["fairwaysRecorded"] = g(len(fw), " + ".join(f"{p}:{n}" for p, n in Counter(r["pos"] for r, _ in fw).items()) + f" = {len(fw)} (manual rounds record no fairway; par 3 none)")
    out["fairwaysHit"] = g(fwc.get("hit", 0), f"HIT holes = {fwc.get('hit', 0)}")
    out["fairwayMissLeft"] = g(fwc.get("left", 0), f"LEFT holes = {fwc.get('left', 0)}")
    out["fairwayMissRight"] = g(fwc.get("right", 0), f"RIGHT holes = {fwc.get('right', 0)}")
    # penalties [B0d1]: only holes that carry a penalties field and are not unedited defaults
    pen = [(r, h) for r, h in holes if isinstance(h["penalties"], int) and not h["default"]]
    pen_rounds = sorted({r["pos"] for r, _ in pen}, key=lambda p: int(p[1:]))
    total_pen = sum(h["penalties"] for _, h in pen)
    out["penaltiesTotal"] = g(total_pen, " + ".join(f"{r['pos']}#{h['display']}:{h['penalties']}" for r, h in pen if h["penalties"]) + f" = {total_pen}")
    out["penaltyHolesRecorded"] = g(len(pen), " + ".join(f"{p}:{n}" for p, n in Counter(r["pos"] for r, _ in pen).items()) + f" = {len(pen)} (Garmin holes carry no penalties field -> not recorded, not 0)")
    out["penaltyRoundsRecorded"] = g(len(pen_rounds), f"rounds {pen_rounds}")
    out["penaltyAveragePerRound"] = g(round(total_pen / len(pen_rounds), 2) if pen_rounds else None, f"{total_pen} / {len(pen_rounds)}")
    # composition 7 dims [GUIDE 3.3] over every scored hole (default holes keep their default strokes)
    comp = Counter()
    for _, h in holes:
        d = h["strokes"] - h["par"]
        comp["eagle" if d <= -2 else "birdie" if d == -1 else "par" if d == 0 else "bogey" if d == 1 else "double" if d == 2 else "triple" if d == 3 else "quadPlus"] += 1
    out["composition"] = g({k: comp.get(k, 0) for k in ("eagle", "birdie", "par", "bogey", "double", "triple", "quadPlus")},
                           f"count of (strokes-par) over {len(holes)} holes: <=-2 eagle, -1 birdie, 0 par, 1 bogey, 2 double, 3 triple, >=4 quadPlus")
    # by par [SPEC 2.5 Par3/4/5 均杆与保帕]
    bypar = {}
    for p in (3, 4, 5):
        hs = [h for _, h in holes if h["par"] == p]
        sc = sum(h["strokes"] for h in hs)
        keep = sum(1 for h in hs if h["strokes"] <= p)
        bypar[f"par{p}"] = {"holeCount": len(hs), "strokes": sc, "averageScore": r1(sc / len(hs)) if hs else None, "parOrBetter": keep}
    out["byPar"] = g(bypar, "per par: holeCount, sum strokes / holeCount -> averageScore (1 dp), parOrBetter = strokes<=par (保帕)")
    return out


# ---------------------------------------------------------------- windows [B5a, MERGE]
anchor = date.fromisoformat(rounds[0]["date"])
cut = anchor - timedelta(days=365)
cut2 = anchor - timedelta(days=730)
W = {
    "all": rounds,
    "last10": rounds[:10], "prev10": rounds[10:20],
    "last20": rounds[:20], "prev20": rounds[20:40],
    "12m": [r for r in rounds if date.fromisoformat(r["date"]) >= cut],
    "prev12m": [r for r in rounds if cut2 <= date.fromisoformat(r["date"]) < cut],
}
assert len(W["12m"]) == 21 and len(W["prev12m"]) == 10


def avg18(rows):
    s = [r["score"] for r in rows if r["holesCompleted"] == 18]
    return (r1(sum(s) / len(s)) if s else None), s


# ---------------------------------------------------------------- handicap [MANUAL WHS, B5a]
def diff(r):
    return round((r["score"] - r["rating"]) * 113 / r["slope"], 1)


def whs(rows):
    d = [diff(r) for r in rows if r["priceable"]][:20]
    n = len(d)
    table = {3: (1, -2.0), 4: (1, -1.0), 5: (1, 0), 6: (2, -1.0), 7: (2, 0), 8: (2, 0)}
    if n < 3:
        return None, d, "n<3"
    if n in table:
        k, adj = table[n]
    elif n <= 11:
        k, adj = 3, 0
    elif n <= 14:
        k, adj = 4, 0
    elif n <= 16:
        k, adj = 5, 0
    elif n <= 18:
        k, adj = 6, 0
    elif n == 19:
        k, adj = 7, 0
    else:
        k, adj = 8, 0
    low = sorted(d)[:k]
    return r1(sum(low) / k + adj), d, f"lowest {k} of {n} {low} -> {sum(low)}/{k}{'+' + str(adj) if adj else ''}"


golden: dict = {"_about": "C16b golden, written before any product run. value + formula per item. Round positions P1 (newest) .. P31 (oldest); ids in round_ids.json; P25 = merged same-day cards P25a+P25b.",
                "roundIdByPos": {r["pos"]: r["id"] for r in rounds}}

now_est, now_d, now_f = whs(rounds)
before_rows = rounds[20:]
before_est, before_d, before_f = whs(before_rows)
# ambiguity-proof: also the reading "latest 20 rounds, drop unpriceable" and "best 8 of what is there"
alt_now = sorted(diff(r) for r in rounds[:20] if r["priceable"])
assert r1(sum(alt_now[:4]) / 4) == now_est == r1(sum(sorted(now_d)[:8]) / 8)
assert r1(sum(sorted(before_d)[:8][: len(before_d)]) / min(8, len(before_d))) == before_est
golden["2.1"] = {
    "handicapEstimate": g(now_est, "WHS: differential=(score-71.0)*113/113; most recent 20 priceable records (unpriceable P2,P4,P5,P9,P11,P17 skipped) " + now_f
                          + f"; ambiguity-proof: reading 'latest 20 rounds minus unpriceable' = {len(alt_now)} diffs -> lowest 4 {alt_now[:4]} -> same"),
    "handicapBefore20": g(before_est, "estimate on rounds older than the latest 20 (P21..P31): " + before_f + " (every older priceable diff is 14.0 -> any WHS sample rule gives 14.0)"),
    "handicapChangeRecent20": g(r1(now_est - before_est), f"[B5a] now {now_est} - before {before_est}"),
    "recent10Average": g(avg18(W["last10"])[0], f"P1..P10 scores {avg18(W['last10'])[1]} sum {sum(avg18(W['last10'])[1])} / 10"),
    "careerAverage18": g(avg18(rounds)[0], f"all 18-hole rounds (27, incl. merged P25) sum {sum(avg18(rounds)[1])} / {len(avg18(rounds)[1])} -- must differ from recent10Average (生涯不冒充近期)"),
    "bestScore": g(min(avg18(rounds)[1]), "min 18-hole score; best overall = P2 78, which is also the best of the last 10 (ambiguity-proof for '近 10 场 ... 最佳')"),
    "bestScoreLast10": g(min(avg18(W["last10"])[1]), "min of P1..P10"),
    "totalRounds": g(len(rounds), "31 rounds (32 cards, P25a+P25b merge into one)"),
    "courseCount": g(len({r["courseKey"] for r in rounds}), "Kestrel Hills, Lark Valley, Pine Field"),
}
trend_rows = [r for r in reversed(rounds) if r["holesCompleted"] == 18]
last20 = trend_rows[-20:]
golden["2.1"]["trendLast20"] = g([{"roundId": r["id"], "pos": r["pos"], "score": r["score"]} for r in last20],
                                 "18-hole rounds oldest->newest, last 20 = P20..P1 (all 18-hole)")
line = []
for i in range(len(trend_rows) - 20, len(trend_rows)):
    win = [x["score"] for x in trend_rows[max(0, i - 9): i + 1]]
    line.append(r1(sum(win) / len(win)))
golden["2.1"]["line10"] = g(line, "info for C16e (drawn client-side): mean of each point and the up-to-9 18-hole rounds before it; last value must equal recent10Average")
assert line[-1] == golden["2.1"]["recent10Average"]["value"]
golden["2.1"]["recentThree"] = g([{"roundId": r["id"], "pos": r["pos"], "score": r["score"],
                                   "toPar": [h["strokes"] - h["par"] for h in r["holes"]]} for r in rounds[:3]],
                                 "archive newest first P1,P2,P3; strip = per-hole strokes-par in hole order")

# ---------------------------------------------------------------- 2.2 windows / previous / periods
w22 = {}
for wname in ("all", "last10", "last20", "12m"):
    w22[wname] = {"roundIds": g(ids(W[wname]), f"{wname}: {plist(W[wname])}"), "roundCount": g(len(W[wname]), f"len = {len(W[wname])}")}
golden["2.2"] = {"windows": w22}
golden["2.2"]["last10Months"] = g(sorted({r["date"][:7] for r in W["last10"]}, reverse=True), "范围定样本: months of P1..P10 only (not 12 months)")
prev = {}
for wname, pname, need in (("last10", "prev10", 10), ("last20", "prev20", 20), ("12m", "prev12m", None), ("all", None, None)):
    if pname is None:
        prev[wname] = g(None, "[B5a] 全部不比较: no previous block")
        continue
    rows = W[pname]
    full = need is None or len(rows) >= need
    prev[wname] = g({"window": pname, "roundCount": len(rows), "requiredRounds": need, "hasScoring": full},
                    f"{pname} = {plist(rows)} ({len(rows)} rounds); " + ("full -> compare" if full else f"short of {need} -> no comparison"))
golden["2.2"]["previous"] = prev
cmp = {}
for wname in ("last10", "prev10", "prev12m"):
    hs = hole_stats(W[wname])
    cmp[wname] = {k: hs[k] for k in ("totalPutts", "holesWithPutts", "zeroPutts", "onePutts", "twoPutts", "threePlusPutts",
                                     "girRecorded", "gir", "fairwaysRecorded", "fairwaysHit", "fairwayMissLeft", "fairwayMissRight",
                                     "scrambleChances", "scrambleSaves")}
golden["2.2"]["compareScoring"] = cmp


def period_pack(rows):
    a, s = avg18(rows)
    birdies = sum(1 for r in rows for h in r["holes"] if h["strokes"] - h["par"] == -1)
    doubles = sum(1 for r in rows for h in r["holes"] if h["strokes"] - h["par"] >= 2)
    return {"roundCount": len(rows), "roundIds": sorted(ids(rows)), "average18": a, "bestScore": min(s) if s else None,
            "worstScore": max(s) if s else None, "birdies": birdies, "doubleOrWorse": doubles,
            "formula": f"{plist(rows)}; 18-hole scores {s}; birdie holes {birdies}; double+ holes {doubles} (鸟/场 = birdies/roundCount, 双柏+/场 = doubleOrWorse/roundCount, drawn client-side)"}


def quarter(d):
    return f"{d[:4]}-Q{(int(d[5:7]) - 1) // 3 + 1}"


periods = {"byQuarter": {}, "byYear": {}, "byMonth": {}, "byDay": {}}
for keyf, bucket in ((quarter, "byQuarter"), (lambda d: d[:4], "byYear"), (lambda d: d[:7], "byMonth"), (lambda d: d[:10], "byDay")):
    grp = defaultdict(list)
    for r in rounds:
        grp[keyf(r["date"])].append(r)
    for k in sorted(grp, reverse=True):
        periods[bucket][k] = period_pack(grp[k])
golden["2.2"]["periods"] = periods
months = sorted(periods["byMonth"])
span = []
y, m = int(months[0][:4]), int(months[0][5:7])
while (y, m) <= (int(months[-1][:4]), int(months[-1][5:7])):
    span.append(f"{y:04d}-{m:02d}")
    y, m = (y + 1, 1) if m == 12 else (y, m + 1)
assert span == months, "every calendar month in the span has a round (ambiguity-proof 月均场数)"
most = max(months, key=lambda k: periods["byMonth"][k]["roundCount"])
assert sum(1 for k in months if periods["byMonth"][k]["roundCount"] == periods["byMonth"][most]["roundCount"]) == 1
golden["2.2"]["playFrequency"] = {
    "totalMonths": g(len(months), f"{months[0]}..{months[-1]} = {len(months)} months, each with >=1 round"),
    "roundsPerMonth": g(r1(len(rounds) / len(months)), f"{len(rounds)} rounds / {len(months)} months = {len(rounds) / len(months):.4f}"),
    "mostActiveMonth": g({"key": most, "roundCount": periods["byMonth"][most]["roundCount"]}, f"unique max: {most} has {plist(sorted(W['all'], key=lambda r: r['when']) and [r for r in rounds if r['date'][:7] == most])}"),
}

# ---------------------------------------------------------------- 2.3 drill-downs (roundIds = hand sets)
def band(s):
    return "70s" if s < 80 else "80s" if s < 90 else "90s" if s < 100 else "100+"


bands = defaultdict(list)
for r in rounds:
    if r["holesCompleted"] == 18:
        bands[band(r["score"])].append(r)
golden["2.3"] = {
    "quarter2026Q2": g(sorted(ids([r for r in rounds if quarter(r["date"]) == "2026-Q2"])), "2026-Q2 (Apr-Jun) = " + plist([r for r in rounds if quarter(r["date"]) == "2026-Q2"])),
    "scoreBands": g({k: sorted(ids(v)) for k, v in bands.items()}, "; ".join(f"{k}: {plist(v)}" for k, v in bands.items())),
    "day20260614": g(sorted(ids([r for r in rounds if r["date"] == "2026-06-14"])), "calendar cell 2026-06-14 = P8"),
    "larkCourseRounds": g(ids([r for r in rounds if r["venue"] == "Lark Valley"]), "Lark Valley newest first: " + plist([r for r in rounds if r["venue"] == "Lark Valley"])),
    "larkCourseKey": g(course_key("Lark Valley"), "c_ + sha1('Lark Valley')[:10]"),
    "kestrelCourseKey": g(course_key("Kestrel Hills"), "c_ + sha1('Kestrel Hills')[:10]"),
    "pineCourseKey": g(course_key("Pine Field"), "c_ + sha1('Pine Field')[:10]"),
}

# ---------------------------------------------------------------- 2.4 archive search / filters / month groups
def sel(pred):
    return [r for r in rounds if pred(r)]


k_venue = "Kestrel Hills"
golden["2.4"] = {
    "searchLark": g(ids(sel(lambda r: "lark" in r["name"].lower())), "course name contains 'Lark' (case-insensitive): " + plist(sel(lambda r: "lark" in r["name"].lower()))),
    "searchDate202606": g(ids(sel(lambda r: r["date"].startswith("2026-06"))), "date 2026-06: " + plist(sel(lambda r: r["date"].startswith("2026-06")))),
    "year2025": g(ids(sel(lambda r: r["date"][:4] == "2025")), "year 2025: " + plist(sel(lambda r: r["date"][:4] == "2025"))),
    "hasShots": g(ids(sel(lambda r: r["hasShots"])), "rounds with a shot file: " + plist(sel(lambda r: r["hasShots"]))),
    "kestrel2026": g(ids(sel(lambda r: r["venue"] == k_venue and r["date"][:4] == "2026")), "Kestrel Hills x 2026: " + plist(sel(lambda r: r["venue"] == k_venue and r["date"][:4] == "2026"))),
    "larkNoShots": g(ids(sel(lambda r: r["venue"] == "Lark Valley" and not r["hasShots"])), "Lark Valley x no shots: " + plist(sel(lambda r: r["venue"] == "Lark Valley" and not r["hasShots"]))),
    "monthGroups2026": g([{"key": k, "roundIds": [r["id"] for r in rounds if r["date"][:7] == k]} for k in sorted({r["date"][:7] for r in rounds if r["date"][:4] == "2026"}, reverse=True)],
                         "year=2026 grouped by month, newest month first, rounds newest first inside"),
    "total": g(len(rounds), "全部 N 场 = 31"),
}

# ---------------------------------------------------------------- 2.5 honesty (window all) + per-hole states
golden["2.5"] = {"all": hole_stats(rounds)}
state_rows = {
    "valued": ("P1", 1), "garminNoPutts": ("P28", 1), "defaultUnedited": ("P2", 6),
    "defaultCorrected": ("P2", 12), "normalCorrected": ("P4", 5), "manualPenaltyZero": ("P2", 1),
    "manualPenaltyOne": ("P4", 8), "garminNoPenaltyField": ("P1", 8),
}
srows = {}
for label, (pos, disp) in state_rows.items():
    h = next(x for x in R[pos]["holes"] if x["display"] == disp)
    elig = (not h["default"]) or h["corrected"]
    putts = h["putts"] if elig else None
    gir = gir_of(h) if elig else None
    srows[label] = g({"roundId": R[pos]["id"], "hole": disp, "putts": putts, "gir": gir, "fairway": h["fairway"],
                      "penaltyCounted": isinstance(h["penalties"], int) and not h["default"]},
                     f"{pos}#{disp}: strokes {h['strokes']} par {h['par']} raw putts {h['rawPutts']} default={h['default']} corrected={h['corrected']} -> putts {putts}, GIR {'(' + str(h['strokes']) + '-' + str(putts) + '<=' + str(h['par'] - 2) + ')' if putts is not None else 'unknown'}")
golden["2.5"]["holeStates"] = srows

# ---------------------------------------------------------------- 2.6 loops / combos / hardest
loops = {}
names = defaultdict(Counter)
for r in rounds:
    sides_present = {h["side"] for h in r["holes"]}
    suffix = r["name"].split("~", 1)[1].strip().replace("+", "/") if "~" in r["name"] else ""
    parts = [p for p in suffix.split("/") if p]
    ev = {}
    if len(parts) == 2:
        ev = {"front": parts[0], "back": parts[1]}
    elif len(parts) == 1 and len(sides_present) == 1:
        ev = {sides_present.pop(): parts[0]}
    for h in r["holes"]:
        L = loops.setdefault(h["loopKey"], {"rounds": set(), "holes": defaultdict(list), "pars": defaultdict(Counter), "venue": r["venue"],
                                            "span": "10–18 洞" if h["loopKey"].endswith("10-18") else "1–9 洞"})
        L["rounds"].add(r["pos"])
        L["holes"][h["loopHole"]].append((h["strokes"] - h["par"], r["pos"]))
        L["pars"][h["loopHole"]][h["par"]] += 1
        if h["side"] in ev:
            names[h["loopKey"]][ev[h["side"]]] += 1
loop_out = {}
hard = []
for key, L in loops.items():
    label = f"{L['venue']} {names[key].most_common(1)[0][0]}" if names[key] else f"{L['venue']} {L['span']}"
    hole_rows = []
    for hn in sorted(L["holes"]):
        vals = L["holes"][hn]
        par = min(L["pars"][hn].items(), key=lambda kv: (-kv[1], kv[0]))[0]
        a = sum(v for v, _ in vals) / len(vals)
        hole_rows.append({"hole": hn, "par": par, "averageToPar": r2(a), "samples": len(vals),
                          "formula": f"({' + '.join(f'{v:+d}[{p}]' for v, p in vals)}) / {len(vals)} = {a:.4f}"})
        if len(vals) >= 2:
            hard.append({"loopKey": key, "label": label, "hole": hn, "par": par, "averageToPar": r2(a), "exact": a, "samples": len(vals)})
    loop_out[key] = {"label": label, "roundCount": len(L["rounds"]), "rounds": sorted(L["rounds"], key=lambda p: int(p[1:])), "holes": hole_rows}
hard.sort(key=lambda x: (-x["exact"], -x["samples"], x["label"], x["hole"]))
assert hard[4]["exact"] > hard[5]["exact"] + 1e-9, "top-5 boundary must not tie"
assert len({round(x["exact"], 6) for x in hard[:5]}) == 5, "top-5 averages must be distinct"
combos = defaultdict(list)
nine_only = []
for r in rounds:
    if r["holesCompleted"] == 18:
        fk = next(h["loopKey"] for h in r["holes"] if h["side"] == "front")
        bk = next(h["loopKey"] for h in r["holes"] if h["side"] == "back")
        combos[(fk, bk)].append(r)
    elif r["holesCompleted"] == 9:
        nine_only.append(r)
combo_rows = sorted(({"frontKey": f, "backKey": b, "rounds": len(v), "average": r1(sum(x["score"] for x in v) / len(v)),
                      "formula": f"{plist(v)} scores {[x['score'] for x in v]}"} for (f, b), v in combos.items()),
                    key=lambda x: -x["rounds"])
golden["2.6"] = {
    "loops": g(loop_out, "[B0d1] key = gid:<id>:<span> (no id -> course:<courseKey>:<span>); per loop hole mean(strokes-par) over every time it was played, 2 dp"),
    "nineCombos": g(combo_rows, "[B0d1] holesCompleted==18 rounds grouped front loop -> back loop (A/B != B/A); rows with >1 round have distinct counts"),
    "nineOnlyRounds": g(len(nine_only), "holesCompleted==9: " + plist(nine_only)),
    "kestrelNineOnly": g(sum(1 for r in nine_only if r["venue"] == k_venue), "Kestrel 9-hole rounds"),
    "kestrelLoopKeys": g(sorted(k for k, L in loops.items() if L["venue"] == k_venue), "loops played at Kestrel Hills"),
    "kestrelComboCount": g(sum(1 for (f, b) in combos if loops[f]["venue"] == k_venue), "全部 N 种组合 at Kestrel"),
    "kestrelTopThreeCombos": g([{"frontKey": c["frontKey"], "backKey": c["backKey"], "rounds": c["rounds"]} for c in combo_rows if loops[c["frontKey"]]["venue"] == k_venue][:3], "常打三种: highest round counts 8,5,3 (no ties)"),
    "hardestHoles": g([{k: x[k] for k in ("loopKey", "label", "hole", "par", "averageToPar", "samples")} for x in hard[:5]],
                      "[B0d1] loop holes with >=2 samples, by averageToPar desc, top 5; boundary and order tie-free"),
    "kestrelHardestThree": g([{k: x[k] for k in ("loopKey", "hole", "averageToPar", "samples")} for x in hard if loops[x["loopKey"]]["venue"] == k_venue][:3],
                             "[SPEC 2.6] course page: that course's own loop holes, >=2 samples, top 3 (selection drawn client-side; info for C16e)"),
}
hk = hard[0]
visits = [(r["pos"], h["display"]) for r in rounds for h in r["holes"] if h["loopKey"] == hk["loopKey"] and h["loopHole"] == hk["hole"]]
golden["2.3"]["hardestHoleVisits"] = g([{"roundId": R[p]["id"], "pos": p, "displayHole": d} for p, d in visits],
                                       f"every round/display hole that played {hk['loopKey']} hole {hk['hole']}")

# ---------------------------------------------------------------- 2.7 clubs
shots = []
for path in sorted((PLAYER / "shots").glob("*.json")):
    data = json.loads(path.read_text())
    names_by_id = {c["clubId"]: c["name"] for c in data["clubDetails"]}
    for hole in data["holeShots"]:
        for s in hole["shots"]:
            shots.append({"club": names_by_id.get(s["clubId"]) if s["clubId"] else None, "meters": s["meters"],
                          "round": POS_BY_ID[str(data["scorecardId"])], "hole": hole["holeNumber"], "order": s["shotOrder"],
                          "endLie": s["endLoc"]["lie"]})
by_club = defaultdict(list)
spell = defaultdict(Counter)
for s in shots:
    if s["club"] is None:
        continue
    by_club[s["club"].upper()].append(s["meters"])
    spell[s["club"].upper()][s["club"]] += 1


def pct(vals, p):
    v = sorted(vals)
    pos = (len(v) - 1) * p
    assert abs(pos - round(pos)) < 1e-9, "fixture uses n where (n-1)p is an integer: nearest-rank == interpolation"
    return float(v[int(round(pos))])


clubs = {}
for k, vals in sorted(by_club.items()):
    clubs[k.lower()] = {"sampleCount": len(vals), "median": pct(vals, 0.5), "p10": pct(vals, 0.1), "p90": pct(vals, 0.9),
                        "spellings": dict(spell[k]), "formula": f"sorted {sorted(vals)}"}
golden["2.7"] = {
    "clubs": g(clubs, "[GUIDE] Driver(clubId101)+driver(clubId102) merge case-insensitively into one club of 11; clubId 0 (Unknown, 3 shots) dropped; 3W has 1 sample (low sample)"),
    "unknownShots": g(sum(1 for s in shots if s["club"] is None), "clubId 0 shots, excluded from every club row"),
    "bagGarmin": g({"source": "garmin", "clubs": [{"token": "driver", "distanceM": 215}, {"token": "iron7", "distanceM": 145}, {"token": "pw", "distanceM": None}]},
                   "[MANUAL] no manual bag -> the synced Garmin bag; PW advice 0 = no distance (empty, not 0)"),
    "bagNone": g({"source": "none", "clubs": []}, "a player with neither manual nor synced bag -> empty"),
    "bagManual": g({"source": "manual", "clubs": [{"token": "driver", "distanceM": None}, {"token": "iron7", "distanceM": 150}, {"token": "pw", "distanceM": None}]},
                   "PUT manual bag [driver (no distance), iron7 150 m, pw (no distance)] -> manual wins over Garmin"),
    "ladderAfterManual": g([["driver", clubs["driver"]["median"]], ["iron7", 150], ["pw", clubs["pw"]["median"]]],
                           f"[course_prep.effective_club_ladder contract] manual distance > own measured median > catalog: driver median {clubs['driver']['median']} (11 merged shots), iron7 typed 150 (measured {clubs['7i']['median']} ignored), pw median {clubs['pw']['median']}; sorted longest first"),
}

# ---------------------------------------------------------------- 2.8 single-round review
def review(pos):
    r = R[pos]
    cells = [{"hole": h["display"], "par": h["par"], "score": h["strokes"], "toPar": h["strokes"] - h["par"],
              "putts": h["rawPutts"], "penalties": h["penalties"], "globalId": h["gid"], "localHole": h["localHole"]} for h in r["holes"]]
    cum, run = [], 0
    for c in cells:
        run += c["toPar"]
        cum.append(run)
    fw = [h for h in r["holes"] if h["fairway"]]
    known = [h for h in r["holes"] if h["rawPutts"] is not None]
    gir_hit = sum(1 for h in known if h["strokes"] - h["rawPutts"] <= h["par"] - 2)
    pens = [h["penalties"] for h in r["holes"] if isinstance(h["penalties"], int)]
    four = {
        "tee": {"state": "ready" if fw else "missing", "fairwaysHit": sum(1 for h in fw if h["fairway"] == "hit"), "fairwaysRecorded": len(fw)},
        "approach": {"state": "ready" if known else "missing", "gir": gir_hit if known else None, "girRecorded": len(known)},
        "putting": {"state": "ready" if known else "missing", "totalPutts": sum(h["rawPutts"] for h in known) if known else None},
        "penalty": {"totalPenalties": sum(pens) if pens else None},
    }
    cards_ = []
    for side in ("front", "back"):
        hs = [h for h in r["holes"] if h["side"] == side]
        if hs:
            cards_.append({"side": side, "globalId": hs[0]["gid"], "localHoles": [h["localHole"] for h in hs], "displayHoles": [h["display"] for h in hs]})
    return {"roundId": r["id"], "score": r["score"], "par": r["par"], "holesCompleted": r["holesCompleted"], "cells": cells,
            "cumulativeToPar": cum, "four": four, "loopCards": cards_}


golden["2.8"] = {pos: g(review(pos), {"P12": "Garmin B/A composite: card 1 = loop B holes 1-9 (id 7102), card 2 = loop A holes 1-9 (id 7101)",
                                      "P3": "Lark single 18: holes 10-18 are holes 10-18 of the same id 7201",
                                      "P25": "two same-day 9-hole cards A then C merged: 10-18 are loop C holes 1-9 (id 7103)",
                                      "P22": "9-hole round on Lark back nine: one card, holes 10-18 of id 7201",
                                      "P28": "Garmin round without putts: GIR/putting unknown (missing, not 0)",
                                      "P5": "manual round, no Garmin id: penalties recorded (1), no fairway"}[pos]
                                     + "; GIR by putts strokes-putts<=par-2; penalty total only from holes that carry penalties")
                 for pos in ("P12", "P3", "P25", "P22", "P28", "P5")}

# ---------------------------------------------------------------- 2.9 shot map
def shotmap(pos, hole):
    rows = [s for s in shots if s["round"] == pos and s["hole"] == hole]
    h = next(x for x in R[pos]["holes"] if x["display"] == hole)
    return {"roundId": R[pos]["id"], "hole": hole, "orders": [s["order"] for s in rows], "clubs": [s["club"] for s in rows],
            "endLies": [s["endLie"] for s in rows], "meters": [s["meters"] for s in rows], "putts": h["rawPutts"]}


golden["2.9"] = {
    "P1h4": g(shotmap("P1", 4), "P1 #4 (A par 5, 6 strokes, 2 putts): 4 shots driver/7I/PW/PW, ends Fairway/Rough/Rough/Green; 推 x2"),
    "P7h1": g(shotmap("P7", 1), "P7 #1: Driver, 7I, then a clubId-0 shot (no club label, not 'Unknown'); 推 x2"),
    "P12h12": g(shotmap("P12", 12), "P12 #12 (A#3 par 3): one PW shot to Green, 推 x2"),
}

# ---------------------------------------------------------------- 2.10 report facts
golden["2.10"] = {
    "totalRounds": g(len(rounds), "summary.totalRounds"),
    "average18": golden["2.1"]["careerAverage18"],
    "bestScore": golden["2.1"]["bestScore"],
    "roundP1": g({"roundId": R["P1"]["id"], "score": R["P1"]["score"], "par": R["P1"]["par"]}, "P1 scorecard 81 on par 72"),
    "noShotRound": g(R["P2"]["id"], "P2 has no shot file -> the report must not cite shots for it"),
}

(HERE / "golden.json").write_text(json.dumps(golden, indent=1, ensure_ascii=False))
print("golden written:", sum(1 for _ in json.dumps(golden)), "bytes")
