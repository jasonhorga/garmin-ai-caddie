"""Build prototype dashboard — 8 macro views + 1 shot-distance view + index.

Outputs: output/dashboard/{trend,courses,timeline,analysis,distribution,frequency,courses_list,quarterly,scorecards,shots,index}.html
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]  # repo root: tools/<sub>/<file>.py is 2 dirs deep (P2 reorg fix)
SCORECARD_DIR = ROOT / "data" / "scorecards"
SHOT_DIR = ROOT / "data" / "shots"
OUT = ROOT / "output" / "dashboard"
OUT.mkdir(parents=True, exist_ok=True)

CSS = """
body { font-family: -apple-system, "PingFang SC", sans-serif; background: #1a1a1a; color: #ddd; margin: 0; padding: 20px; }
h1 { font-weight: 500; font-size: 18px; margin: 0 0 6px; }
.sub { color: #888; font-size: 13px; margin-bottom: 18px; }
.stats { color: #999; font-size: 13px; margin-bottom: 16px; }
.stats span { margin-right: 18px; }
.stats b { color: #6cf; font-weight: 600; }
.card { background: #222; border-radius: 8px; padding: 14px; margin-bottom: 12px; }
.nav { background: #222; border-radius: 8px; padding: 10px 14px; margin-bottom: 18px; }
.nav a { color: #6cf; text-decoration: none; margin-right: 16px; font-size: 13px; }
.nav a:hover { text-decoration: underline; }
table { border-collapse: collapse; width: 100%; font-size: 13px; }
th, td { text-align: right; padding: 4px 8px; border-bottom: 1px solid #2a2a2a; }
th { color: #888; font-weight: 500; }
td:first-child, th:first-child { text-align: left; }
"""

NAV_LINKS = [
    ("index.html", "总览"),
    ("trend.html", "总杆波动"),
    ("analysis.html", "成绩分析"),
    ("distribution.html", "成绩分布"),
    ("frequency.html", "打球频率"),
    ("quarterly.html", "年度汇总"),
    ("courses.html", "球场分布图"),
    ("courses_list.html", "球场列表"),
    ("timeline.html", "打球记录"),
    ("scorecards.html", "成绩卡"),
    ("shots.html", "击球距离"),
]


def make_nav(prefix: str = "") -> str:
    inner = "".join(f'<a href="{prefix}{href}">{label}</a>' for href, label in NAV_LINKS)
    return f'<div class="nav">{inner}</div>'


NAV = make_nav()


def page(title: str, body: str, head_extra: str = "", nav: str | None = None) -> str:
    return f"""<!DOCTYPE html>
<html lang="zh"><head><meta charset="utf-8"><title>{title}</title>
<style>{CSS}</style>{head_extra}</head>
<body>{nav if nav is not None else NAV}{body}</body></html>"""


def semicircle_to_deg(s):
    return None if s is None else s * 180.0 / 2**31


def millionths_to_deg(s):
    """courseSnapshot.lat/lon are stored as millionths of a degree (8-digit ints)."""
    return None if s is None else s / 1e6


CLUB_TYPE_NAME = {
    0: "Unknown", 1: "Driver", 2: "3W", 3: "5W", 4: "7W", 5: "Hybrid",
    6: "2I/Hybrid", 7: "3I", 8: "4I", 9: "5I", 10: "6I", 11: "7I",
    12: "8I", 13: "9I", 14: "PW", 15: "GW", 16: "SW", 17: "LW", 18: "Putter",
}

# Reasonable upper bound (meters) for a single shot per club type — anything
# above is almost certainly bogus auto-detect noise (e.g. GPS jitter, missed
# club label). Used to drop outliers from distance histogram.
CLUB_MAX_M = {
    "Driver": 330, "3W": 290, "5W": 270, "7W": 250, "Hybrid": 240,
    "2I/Hybrid": 240, "3I": 230, "4I": 220, "5I": 210, "6I": 200,
    "7I": 185, "8I": 170, "9I": 155, "PW": 140, "GW": 130, "SW": 110,
    "LW": 90, "Putter": 35, "Unknown": 320,
}


def max_distance_for(name: str) -> int:
    """Lookup physical max distance for a club name (handles user labels like '1D', '5铁', '50°')."""
    if name in CLUB_MAX_M:
        return CLUB_MAX_M[name]
    n = name.upper().replace("°", "")
    if "1D" in n or "DRIVER" in n: return 330
    if "3W" in n or "WOOD" in n.replace("_", ""): return 290
    if "H" in n or "HYBRID" in n or "鸡腿" in name: return 240
    if "PW" in n: return 140
    if "50" in n: return 130
    if "54" in n: return 115
    if "58" in n: return 95
    if "SW" in n: return 110
    if "GW" in n or "AW" in n: return 130
    if "LW" in n: return 95
    if "PUTTER" in n: return 35
    # iron lookup: "5I" / "5铁"
    for k, cap in [(9, 155), (8, 170), (7, 185), (6, 200), (5, 210), (4, 220), (3, 230)]:
        if f"{k}I" in n or f"{k}铁" in name:
            return cap
    return 320  # unknown


def club_label(club_type_id, shaft_length) -> str:
    name = CLUB_TYPE_NAME.get(club_type_id, "Unknown")
    if name != "Unknown":
        return name
    # fallback on shaft length
    if shaft_length:
        if shaft_length >= 44.5: return "Driver"
        if shaft_length >= 42.5: return "Fairway Wood"
        if shaft_length >= 40: return "Hybrid/Long Iron"
        if shaft_length >= 38: return "Mid Iron"
        if shaft_length >= 36: return "Wedge"
        return "Putter"
    return "Unknown"


def canonical_course_name(name: str) -> str:
    """Strip A/B/C/D nine-hole-combination suffixes so multi-nine courses merge."""
    if not name:
        return name
    for sep in (" ~ ", " ~", "~"):
        if sep in name:
            return name.split(sep)[0].strip()
    return name.strip()


# ---------- data loaders ----------

def load_rounds() -> list[dict]:
    rounds = []
    for f in SCORECARD_DIR.glob("*.json"):
        try:
            d = json.loads(f.read_text())
        except Exception:
            continue
        details = d.get("scorecardDetails", [])
        if not details:
            continue
        sc = details[0]["scorecard"]
        stats = details[0].get("scorecardStats", {}).get("round", {})
        snap = (d.get("courseSnapshots") or [{}])[0]
        cmp_ = details[0].get("statsComparison", {})
        rounds.append({
            "id": sc["id"],
            "date": sc.get("formattedStartTime", sc.get("startTime", "")),
            "strokes": sc.get("strokes"),
            "holesCompleted": sc.get("holesCompleted"),
            "course": snap.get("name", "未知"),
            "courseCanonical": canonical_course_name(snap.get("name", "未知")),
            "courseId": sc.get("courseGlobalId"),
            "snapshotId": sc.get("courseSnapshotId"),
            "lat": millionths_to_deg(snap.get("lat")),
            "lon": millionths_to_deg(snap.get("lon")),
            "city": snap.get("city"),
            "country": snap.get("country"),
            "par": snap.get("roundPar", 72),
            "holePars": snap.get("holePars", ""),
            "holes": sc.get("holes", []),
            "fh": stats.get("fairwaysHit"),
            "fl": stats.get("fairwaysLeft"),
            "fr": stats.get("fairwaysRight"),
            "frec": stats.get("fairwaysRecorded"),
            "gir": stats.get("greensInRegulation"),
            "putts": stats.get("putts"),
            "ub": stats.get("holesUnderPar"),
            "pa": stats.get("holesPar"),
            "bo": stats.get("holesBogey"),
            "ob": stats.get("holesOverBogey"),
            "bi": stats.get("holesBirdie"),
            "ea": stats.get("holesEagle"),
            "rating": sc.get("teeBoxRating"),
            "slope": sc.get("teeBoxSlope"),
            "longest": details[0].get("longestShotInMeters"),
            "drive": cmp_.get("driveRating"),
            "approach": cmp_.get("approachRating"),
            "chip": cmp_.get("chipRating"),
        })
    rounds.sort(key=lambda r: r["date"])
    return rounds


def merge_same_day_halves(rounds: list[dict]) -> list[dict]:
    """Merge two 9-hole rounds at the same canonical course on the same day
    into one virtual 18-hole round. Logged when user split 18 holes across
    two scorecards (e.g. A→B at 黑骑士)."""
    by_key: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for r in rounds:
        by_key[(r["date"][:10], r["courseCanonical"])].append(r)

    merged: list[dict] = []
    n_merged = 0
    for (day, canon), group in by_key.items():
        group.sort(key=lambda r: r["date"])  # earliest first
        if (
            len(group) == 2
            and all(r["holesCompleted"] == 9 for r in group)
            and sum(r["holesCompleted"] for r in group) == 18
        ):
            front, back = group
            # Sum additive fields
            def s(field: str, default=0) -> int:
                return (front.get(field) or default) + (back.get(field) or default)

            # Renumber back-nine holes 10..18
            back_holes = []
            for i, h in enumerate(back.get("holes") or []):
                hh = dict(h)
                hh["number"] = i + 10
                back_holes.append(hh)

            virtual = {
                "id": f"merged_{front['id']}_{back['id']}",
                "ids": [front["id"], back["id"]],
                "date": front["date"],
                "strokes": s("strokes"),
                "holesCompleted": 18,
                "course": f"{canon} ~ {front['course'].rsplit('~',1)[-1].strip()}+{back['course'].rsplit('~',1)[-1].strip()}",
                "courseCanonical": canon,
                "courseId": front["courseId"],
                "snapshotId": front["snapshotId"],
                "lat": front["lat"],
                "lon": front["lon"],
                "city": front["city"],
                "country": front["country"],
                "par": (front.get("par") or 0) + (back.get("par") or 0),
                "holePars": (front.get("holePars") or "") + (back.get("holePars") or ""),
                "holes": (front.get("holes") or []) + back_holes,
                "fh": s("fh"), "fl": s("fl"), "fr": s("fr"), "frec": s("frec"),
                "gir": s("gir"), "putts": s("putts"),
                "ub": s("ub"), "pa": s("pa"), "bo": s("bo"), "ob": s("ob"),
                "bi": s("bi"), "ea": s("ea"),
                "rating": front.get("rating"),
                "slope": front.get("slope"),
                "longest": max((r.get("longest") or 0) for r in group) or None,
                "drive": None, "approach": None, "chip": None,  # not meaningful when summed
                "merged": True,
            }
            merged.append(virtual)
            n_merged += 1
        else:
            merged.extend(group)
    print(f"  merged {n_merged} same-day 9-hole pairs into virtual 18-hole rounds")
    merged.sort(key=lambda r: r["date"])
    return merged


CLUBS_OVERRIDE_FILE = ROOT / "clubs.json"


def load_clubs_override() -> dict[int, dict]:
    """User-edited mapping clubId -> {name, retired}. Beats heuristics."""
    if not CLUBS_OVERRIDE_FILE.exists():
        return {}
    raw = json.loads(CLUBS_OVERRIDE_FILE.read_text())
    out = {}
    for k, v in raw.items():
        if k.startswith("_") or not isinstance(v, dict):
            continue
        try:
            out[int(k)] = v
        except ValueError:
            pass
    return out


def load_shots(rounds_18: list[dict]) -> list[dict]:
    """Return all shots across all rounds, joined with round/club metadata."""
    override = load_clubs_override()
    # club lookup: aggregated from per-round clubDetails
    club_map: dict[int, str] = {}
    retired_set: set[int] = set()
    rounds_by_id = {r["id"]: r for r in rounds_18}
    shots = []
    for f in SHOT_DIR.glob("*.json"):
        try:
            d = json.loads(f.read_text())
        except Exception:
            continue
        sid = int(f.stem)
        r = rounds_by_id.get(sid)
        if not r:
            continue
        for cd in d.get("clubDetails", []) or []:
            cid = cd.get("clubId") or cd.get("id")
            if not cid:
                continue
            if cid in override:
                club_map[cid] = override[cid].get("name", "?") or "?"
                if override[cid].get("retired"):
                    retired_set.add(cid)
            else:
                club_map[cid] = club_label(cd.get("clubTypeId"), cd.get("shaftLength"))
                if cd.get("retired"):
                    retired_set.add(cid)
        for h in d.get("holeShots", []) or []:
            hn = h.get("holeNumber")
            for s in h.get("shots", []) or []:
                shots.append({
                    "scorecardId": sid,
                    "date": r["date"][:10],
                    "course": r["course"],
                    "hole": hn,
                    "order": s.get("shotOrder"),
                    "club": s.get("clubId"),
                    "type": s.get("shotType"),
                    "auto": s.get("autoShotType"),
                    "meters": s.get("meters"),
                    "endLie": s.get("endLoc", {}).get("lie"),
                })
    # backfill club name + retired flag
    for s in shots:
        s["clubName"] = club_map.get(s["club"], "Unknown") if s["club"] else "Unknown"
        s["clubRetired"] = s["club"] in retired_set if s["club"] else False
    return shots


# ---------- views ----------

def render_index(rounds: list[dict], shots: list[dict]) -> None:
    rounds_18 = [r for r in rounds if r["holesCompleted"] == 18]
    courses = {r["courseId"] for r in rounds if r["courseId"]}
    cards = []
    for label, href, count in [
        ("总杆波动", "trend.html", f"{len(rounds_18)} 场 18 洞"),
        ("成绩分析", "analysis.html", "走势 + 各分段 + par 分类"),
        ("成绩分布", "distribution.html", "金字塔 + 直方图"),
        ("打球频率", "frequency.html", "日历热力"),
        ("年度汇总", "quarterly.html", "季度均/最好/最差"),
        ("球场分布图", "courses.html", f"{len(courses)} 个球场"),
        ("球场列表", "courses_list.html", "次数 + 均杆"),
        ("打球记录", "timeline.html", "时间线"),
        ("成绩卡", "scorecards.html", "每洞 +/-"),
        ("击球距离", "shots.html", f"{len(shots)} 杆按 club 分布"),
    ]:
        cards.append(f'<a class="card" href="{href}" style="display:block;text-decoration:none;color:#ddd"><div style="color:#6cf;font-size:15px;font-weight:500">{label}</div><div style="color:#888;font-size:12px;margin-top:4px">{count}</div></a>')
    body = f"""
<h1>Garmin 高尔夫 dashboard prototype</h1>
<div class="sub">{len(rounds)} 场 · {len(shots)} 杆 · {len(courses)} 球场</div>
<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:12px">{''.join(cards)}</div>
"""
    (OUT / "index.html").write_text(page("Dashboard", body))


def render_trend(rounds: list[dict]) -> None:
    pts = [{"x": r["date"][:10], "y": r["strokes"], "course": r["course"], "id": r["id"]}
           for r in rounds if r["holesCompleted"] == 18 and r["strokes"]]
    avg = sum(p["y"] for p in pts) / max(1, len(pts))
    body = f"""
<h1>总杆波动图</h1>
<div class="stats"><span>共 <b>{len(pts)}</b> 场</span><span>平均 <b>{avg:.1f}</b></span><span>最好 <b>{min(p['y'] for p in pts)}</b></span><span>最差 <b>{max(p['y'] for p in pts)}</b></span></div>
<div class="card" style="height:520px"><canvas id="ch"></canvas></div>
<script>
const points = {json.dumps(pts, ensure_ascii=False)};
new Chart(document.getElementById('ch'), {{
  type:'line', data:{{ datasets:[{{ label:'总杆', data: points.map(p=>({{x:p.x,y:p.y,course:p.course,id:p.id}})), borderColor:'#6cf', backgroundColor:'#6cf3', tension:0.2, pointRadius:2.5, pointHoverRadius:6 }}] }},
  options:{{ responsive:true, maintainAspectRatio:false,
    interaction:{{mode:'index', intersect:false, axis:'x'}},
    scales:{{ x:{{type:'time', time:{{unit:'month'}}, ticks:{{color:'#888'}}, grid:{{color:'#333'}}}}, y:{{ticks:{{color:'#888'}}, grid:{{color:'#333'}}}} }},
    plugins:{{ legend:{{display:false}}, tooltip:{{ mode:'index', intersect:false, backgroundColor:'#000c', callbacks:{{ title:i=>i[0].raw.x, label:i=>`${{i.raw.y}} 杆 · ${{i.raw.course}}` }} }} }}
  }}
}});
</script>"""
    head = '<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script><script src="https://cdn.jsdelivr.net/npm/chartjs-adapter-date-fns/dist/chartjs-adapter-date-fns.bundle.min.js"></script>'
    (OUT / "trend.html").write_text(page("总杆波动", body, head))


def render_courses(rounds: list[dict], course_slugs: dict[str, str]) -> None:
    by_course: dict[str, dict] = {}
    for r in rounds:
        if r["lat"] is None:
            continue
        key = r["courseCanonical"]
        c = by_course.setdefault(key, {
            "name": key, "lat": r["lat"], "lon": r["lon"],
            "city": r["city"], "country": r["country"],
            "all_count": 0, "scores18": [], "variants": set(),
        })
        c["all_count"] += 1
        if r["holesCompleted"] == 18 and r["strokes"]:
            c["scores18"].append(r["strokes"])
        c["variants"].add(r["course"])
    courses = []
    for c in by_course.values():
        c["count"] = c["all_count"]
        c["count18"] = len(c["scores18"])
        c["avg"] = (sum(c["scores18"]) / c["count18"]) if c["count18"] else None
        c["best"] = min(c["scores18"]) if c["scores18"] else None
        c["slug"] = course_slugs[c["name"]]
        del c["scores18"], c["all_count"], c["variants"]
        courses.append(c)
    body = f"""
<h1>球场分布图</h1>
<div class="stats">共 <b>{len(courses)}</b> 个球场（点 marker 看场次列表）</div>
<div id="map" style="height:70vh;border-radius:8px"></div>
<script>
const courses = {json.dumps(courses, ensure_ascii=False)};
const map = L.map('map').setView([35,110],4);
L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{{z}}/{{y}}/{{x}}',{{ attribution:'Esri', maxZoom:18 }}).addTo(map);
const cluster = L.markerClusterGroup();
for (const c of courses) {{
  const m = L.circleMarker([c.lat,c.lon], {{radius: Math.min(20, 6+Math.log(c.count+1)*4), color:'#6cf', weight:2, fillColor:'#6cf', fillOpacity:0.5}});
  const avgStr = c.avg ? ` · 均杆 ${{c.avg.toFixed(1)}}` : '';
  const bestStr = c.best ? ` · 最好 ${{c.best}}` : '';
  m.bindPopup(`<b>${{c.name}}</b><br>${{c.city||''}} ${{c.country||''}}<br>${{c.count}} 场${{avgStr}}${{bestStr}}<br><a href="course/${{c.slug}}.html" style="color:#06c">查看场次列表 →</a>`);
  cluster.addLayer(m);
}}
map.addLayer(cluster);
if (courses.length) map.fitBounds(L.latLngBounds(courses.map(c=>[c.lat,c.lon])),{{padding:[40,40]}});
</script>"""
    head = '<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"><script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script><script src="https://unpkg.com/leaflet.markercluster@1.5.3/dist/leaflet.markercluster.js"></script><link rel="stylesheet" href="https://unpkg.com/leaflet.markercluster@1.5.3/dist/MarkerCluster.css"><link rel="stylesheet" href="https://unpkg.com/leaflet.markercluster@1.5.3/dist/MarkerCluster.Default.css">'
    (OUT / "courses.html").write_text(page("球场分布图", body, head))


def render_courses_list(rounds: list[dict], course_slugs: dict[str, str]) -> None:
    by_course: dict[str, dict] = {}
    for r in rounds:
        key = r["courseCanonical"]
        c = by_course.setdefault(key, {"name": key, "city": r["city"], "country": r["country"], "all": [], "scores18": [], "variants": set()})
        c["all"].append(r)
        if r["holesCompleted"] == 18 and r["strokes"]:
            c["scores18"].append(r["strokes"])
        c["variants"].add(r["course"])
    items = []
    total_rounds = 0
    for c in by_course.values():
        total_rounds += len(c["all"])
        items.append({
            "name": c["name"],
            "slug": course_slugs[c["name"]],
            "city": f"{c['city'] or ''} {c['country'] or ''}".strip(),
            "count": len(c["all"]),
            "count18": len(c["scores18"]),
            "avg": (sum(c["scores18"]) / len(c["scores18"])) if c["scores18"] else None,
            "best": min(c["scores18"]) if c["scores18"] else None,
            "variants": len(c["variants"]),
        })
    items.sort(key=lambda x: (-x["count"], x["avg"] or 999))
    row_html = []
    for i, c in enumerate(items):
        variant_tag = f' <span style="color:#666;font-size:11px">({c["variants"]} 配置)</span>' if c["variants"] > 1 else ""
        avg_str = f'{c["avg"]:.1f}' if c["avg"] is not None else "-"
        best_str = str(c["best"]) if c["best"] is not None else "-"
        count18_str = f'<span style="color:#666;font-size:11px"> · 18洞 {c["count18"]}</span>' if c["count18"] != c["count"] else ""
        row_html.append(
            f'<tr style="cursor:pointer" onclick="location=\'course/{c["slug"]}.html\'">'
            f'<td style="padding-right:14px">{i+1}</td>'
            f'<td><a href="course/{c["slug"]}.html" style="color:#ddd;text-decoration:none">{c["name"]}{variant_tag}</a></td>'
            f'<td style="color:#888">{c["city"]}</td>'
            f'<td>{c["count"]}{count18_str}</td>'
            f'<td>{avg_str}</td>'
            f'<td style="color:#6cf">{best_str}</td></tr>'
        )
    rows = "\n".join(row_html)
    body = f"""
<h1>打过的球场</h1>
<div class="stats">共 <b>{len(items)}</b> 个 · 总场次 <b>{total_rounds}</b>（含 9 洞/未完赛；点行进球场详情）</div>
<div class="card"><table>
<thead><tr><th>#</th><th>球场</th><th>地点</th><th>场次</th><th>均杆 (18)</th><th>最好</th></tr></thead>
<tbody>{rows}</tbody>
</table></div>"""
    (OUT / "courses_list.html").write_text(page("打过的球场", body))


def render_analysis(rounds: list[dict]) -> None:
    rs = [r for r in rounds if r["holesCompleted"] == 18 and r["strokes"]]
    pts = [{"x": r["date"][:10], "y": r["strokes"]} for r in rs]
    buckets = {"eagle": [], "birdie": [], "par": [], "bogey": [], "ob": []}
    for r in rs:
        d = r["date"][:10]
        buckets["eagle"].append({"x": d, "y": r["ea"] or 0})
        buckets["birdie"].append({"x": d, "y": r["bi"] or 0})
        buckets["par"].append({"x": d, "y": r["pa"] or 0})
        buckets["bogey"].append({"x": d, "y": r["bo"] or 0})
        buckets["ob"].append({"x": d, "y": r["ob"] or 0})

    per_par = {3: [], 4: [], 5: []}
    for r in rs:
        if not r["holePars"] or len(r["holePars"]) != 18 or len(r["holes"]) != 18:
            continue
        sums = {3: [0, 0], 4: [0, 0], 5: [0, 0]}
        for i, h in enumerate(r["holes"]):
            try:
                par = int(r["holePars"][i])
                if par in sums:
                    sums[par][0] += h.get("strokes", 0)
                    sums[par][1] += 1
            except Exception:
                pass
        d = r["date"][:10]
        for p in (3, 4, 5):
            if sums[p][1]:
                per_par[p].append({"x": d, "y": sums[p][0] / sums[p][1]})

    body = f"""
<h1>成绩分析</h1>

<div class="card" style="margin-bottom:14px">
  <div style="color:#888;font-size:13px;margin-bottom:6px">总杆波动图（含 5 场移动平均）</div>
  <div style="height:300px"><canvas id="c1"></canvas></div>
</div>

<div class="card" style="margin-bottom:14px">
  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">
    <div style="color:#888;font-size:13px">各分段每场出现次数</div>
    <div id="bucketBtns" style="display:flex;gap:6px"></div>
  </div>
  <div style="height:300px"><canvas id="c2"></canvas></div>
</div>

<div class="card">
  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">
    <div style="color:#888;font-size:13px">三/四/五杆洞 单场平均杆</div>
    <div id="parBtns" style="display:flex;gap:6px"></div>
  </div>
  <div style="height:300px"><canvas id="c3"></canvas></div>
</div>

<script>
const totalPts = {json.dumps(pts, ensure_ascii=False)};
const buckets = {json.dumps(buckets, ensure_ascii=False)};
const perPar = {json.dumps(per_par, ensure_ascii=False)};

function movingAvg(arr, w) {{
  const out = [];
  for (let i=0;i<arr.length;i++) {{
    const lo = Math.max(0, i-w+1);
    const slice = arr.slice(lo, i+1).map(p=>p.y);
    out.push({{x: arr[i].x, y: slice.reduce((a,b)=>a+b,0)/slice.length}});
  }}
  return out;
}}

const baseOpts = {{
  responsive:true, maintainAspectRatio:false,
  interaction:{{mode:'index', intersect:false, axis:'x'}},
  scales:{{
    x:{{type:'time', time:{{unit:'quarter'}}, ticks:{{color:'#888'}}, grid:{{color:'#333'}}}},
    y:{{ticks:{{color:'#888'}}, grid:{{color:'#333'}}, beginAtZero:true}}
  }},
  plugins:{{
    legend:{{labels:{{color:'#aaa'}}}},
    tooltip:{{mode:'index', intersect:false, backgroundColor:'#000c', borderColor:'#444', borderWidth:1}}
  }},
  elements:{{point:{{radius:1}}}}
}};

new Chart(document.getElementById('c1'), {{
  type:'line', data:{{datasets:[
    {{label:'单场总杆', data: totalPts, borderColor:'#6cf3', backgroundColor:'#6cf2', tension:0, borderWidth:1}},
    {{label:'5 场移动均', data: movingAvg(totalPts, 5), borderColor:'#6cf', tension:0.3, borderWidth:2.5, pointRadius:0}},
  ]}},
  options: baseOpts
}});

const bucketDefs = [
  {{key:'birdie', label:'鸟+', color:'#7c7'}},
  {{key:'par',    label:'par', color:'#cc7'}},
  {{key:'bogey',  label:'博忌', color:'#ec8'}},
  {{key:'ob',     label:'博忌+', color:'#e77'}},
  {{key:'eagle',  label:'鹰',  color:'#fcb'}},
];
let activeBucket = 'ob';
const c2 = new Chart(document.getElementById('c2'), {{ type:'line', data:{{datasets:[]}}, options: baseOpts }});

function renderBucket() {{
  const def = bucketDefs.find(d=>d.key===activeBucket);
  const data = buckets[activeBucket];
  c2.data.datasets = [
    {{label:def.label, data, borderColor:def.color+'88', tension:0, borderWidth:1, pointRadius:1}},
    {{label:def.label+' 5 场移动均', data: movingAvg(data,5), borderColor:def.color, tension:0.3, borderWidth:2.5, pointRadius:0}},
  ];
  c2.update();
  document.querySelectorAll('#bucketBtns button').forEach(b=>{{
    b.style.background = b.dataset.k === activeBucket ? '#6cf' : '#2a2a2a';
    b.style.color = b.dataset.k === activeBucket ? '#000' : '#aaa';
  }});
}}

const bb = document.getElementById('bucketBtns');
bucketDefs.forEach(def=>{{
  const b = document.createElement('button');
  b.dataset.k = def.key; b.textContent = def.label;
  b.style.cssText = 'border:none;border-radius:4px;padding:4px 10px;font-size:12px;cursor:pointer;background:#2a2a2a;color:#aaa';
  b.onclick = ()=>{{ activeBucket = def.key; renderBucket(); }};
  bb.appendChild(b);
}});
renderBucket();

let activePar = '4';
const c3 = new Chart(document.getElementById('c3'), {{ type:'line', data:{{datasets:[]}}, options: baseOpts }});
const parDefs = [
  {{k:'3', label:'三杆洞', color:'#9cf'}},
  {{k:'4', label:'四杆洞', color:'#fc9'}},
  {{k:'5', label:'五杆洞', color:'#c9f'}},
];

function renderPar() {{
  const def = parDefs.find(d=>d.k===activePar);
  const data = perPar[activePar];
  c3.data.datasets = [
    {{label:def.label, data, borderColor:def.color+'88', tension:0, borderWidth:1, pointRadius:1}},
    {{label:def.label+' 5 场移动均', data: movingAvg(data,5), borderColor:def.color, tension:0.3, borderWidth:2.5, pointRadius:0}},
  ];
  c3.update();
  document.querySelectorAll('#parBtns button').forEach(b=>{{
    b.style.background = b.dataset.k === activePar ? '#6cf' : '#2a2a2a';
    b.style.color = b.dataset.k === activePar ? '#000' : '#aaa';
  }});
}}

const pb = document.getElementById('parBtns');
parDefs.forEach(def=>{{
  const b = document.createElement('button');
  b.dataset.k = def.k; b.textContent = def.label;
  b.style.cssText = 'border:none;border-radius:4px;padding:4px 10px;font-size:12px;cursor:pointer;background:#2a2a2a;color:#aaa';
  b.onclick = ()=>{{ activePar = def.k; renderPar(); }};
  pb.appendChild(b);
}});
renderPar();
</script>"""
    head = '<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script><script src="https://cdn.jsdelivr.net/npm/chartjs-adapter-date-fns/dist/chartjs-adapter-date-fns.bundle.min.js"></script>'
    (OUT / "analysis.html").write_text(page("成绩分析", body, head))


def render_distribution(rounds: list[dict]) -> None:
    rs = [r for r in rounds if r["holesCompleted"] == 18 and r["strokes"]]
    scores = [r["strokes"] for r in rs]
    # buckets by tens digit family: 70s, 80s, 90s, 100+
    fam = {"70s": 0, "80s": 0, "90s": 0, "100+": 0}
    for s in scores:
        if s < 80: fam["70s"] += 1
        elif s < 90: fam["80s"] += 1
        elif s < 100: fam["90s"] += 1
        else: fam["100+"] += 1
    total = len(scores)
    pct = {k: v / total * 100 for k, v in fam.items()}

    # histogram by 5 bins
    hist = Counter()
    for s in scores:
        b = (s // 5) * 5
        hist[b] += 1
    bins = sorted(hist.keys())

    pyramid_rows = []
    for k, color in [("70s", "#6c6"), ("80s", "#9c6"), ("90s", "#c96"), ("100+", "#c63")]:
        v = fam[k]; p = pct[k]
        pyramid_rows.append(
            f'<div style="display:flex;align-items:center;margin-bottom:8px;gap:10px">'
            f'<div style="width:48px;color:#aaa;font-size:13px;font-weight:500">{k}</div>'
            f'<div style="flex:1;background:#2a2a2a;height:22px;border-radius:4px;overflow:hidden;position:relative">'
            f'<div style="background:{color};width:{p}%;height:100%"></div></div>'
            f'<div style="width:130px;color:#ccc;font-size:13px">{v} 场 · {p:.1f}%</div>'
            f'</div>'
        )
    body = f"""
<h1>成绩分布图</h1>
<div class="stats"><span>共 <b>{total}</b> 场 18 洞</span><span>平均 <b>{sum(scores)/total:.1f}</b></span><span>最好 <b>{min(scores)}</b></span><span>最差 <b>{max(scores)}</b></span></div>
<div class="card"><div style="color:#888;font-size:13px;margin-bottom:10px">杆数家族</div>{''.join(pyramid_rows)}</div>
<div class="card"><div style="color:#888;font-size:13px;margin-bottom:6px">5 杆一档分布</div><div style="height:280px"><canvas id="hist"></canvas></div></div>
<script>
const labels = {json.dumps([f"{b}-{b+4}" for b in bins])};
const data = {json.dumps([hist[b] for b in bins])};
new Chart(document.getElementById('hist'), {{
  type:'bar', data:{{ labels, datasets:[{{label:'场次', data, backgroundColor:'#6cf'}}] }},
  options:{{ responsive:true, maintainAspectRatio:false,
    scales:{{ x:{{ticks:{{color:'#888'}}, grid:{{color:'#333'}}}}, y:{{ticks:{{color:'#888'}}, grid:{{color:'#333'}}, beginAtZero:true}} }},
    plugins:{{legend:{{display:false}}}}
  }}
}});
</script>"""
    head = '<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>'
    (OUT / "distribution.html").write_text(page("成绩分布", body, head))


def render_frequency(rounds: list[dict]) -> None:
    by_year_md: dict[int, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for r in rounds:
        d = r["date"][:10]
        try:
            y, m, dd = int(d[:4]), int(d[5:7]), int(d[8:10])
        except Exception:
            continue
        by_year_md[y][f"{m:02d}-{dd:02d}"] += 1

    years = sorted(by_year_md.keys())
    blocks = []
    for y in years:
        cells_per_month: dict[int, list[int]] = {}
        days_in_month = [31, 29, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
        for m in range(1, 13):
            cells_per_month[m] = []
            for d in range(1, days_in_month[m - 1] + 1):
                k = f"{m:02d}-{d:02d}"
                cells_per_month[m].append(by_year_md[y].get(k, 0))
        rows = []
        for m in range(1, 13):
            cells = "".join(
                f'<div title="{m:02d}-{d+1:02d}: {c}" style="width:8px;height:8px;background:{"#6cf" if c>=2 else ("#369" if c==1 else "#2a2a2a")};border-radius:2px;margin:1px"></div>'
                for d, c in enumerate(cells_per_month[m])
            )
            rows.append(f'<div style="display:flex;align-items:center;margin-bottom:1px"><div style="width:24px;color:#888;font-size:11px">{m}</div><div style="display:flex">{cells}</div></div>')
        ytotal = sum(by_year_md[y].values())
        blocks.append(f'<div class="card" style="margin-bottom:14px"><div style="display:flex;justify-content:space-between;margin-bottom:8px"><div style="color:#aaa;font-weight:600">{y}</div><div style="color:#6cf">{ytotal} 场</div></div>{"".join(rows)}</div>')

    body = f"""
<h1>打球频率</h1>
<div class="stats">深蓝 = 1 场，亮蓝 = 多场</div>
{''.join(blocks)}"""
    (OUT / "frequency.html").write_text(page("打球频率", body))


def render_quarterly(rounds: list[dict]) -> None:
    by_q: dict[tuple[int, int], list[dict]] = defaultdict(list)
    for r in rounds:
        if r["holesCompleted"] != 18 or not r["strokes"]:
            continue
        try:
            y, m = int(r["date"][:4]), int(r["date"][5:7])
        except Exception:
            continue
        q = (m - 1) // 3 + 1
        by_q[(y, q)].append(r)
    rows = []
    for (y, q), rs in sorted(by_q.items(), reverse=True):
        scores = [r["strokes"] for r in rs]
        bi = sum(r["bi"] or 0 for r in rs)
        ea = sum(r["ea"] or 0 for r in rs)
        pa = sum(r["pa"] or 0 for r in rs)
        rows.append(
            f'<div class="card" style="margin-bottom:10px">'
            f'<div style="display:flex;justify-content:space-between;margin-bottom:8px">'
            f'<div style="color:#aaa;font-weight:600">{y} 第 {q} 季度</div>'
            f'<div style="color:#888">共 {len(rs)} 场</div></div>'
            f'<div style="display:grid;grid-template-columns:repeat(4,1fr);gap:8px;font-size:13px;color:#ddd">'
            f'<div>平均：<b style="color:#6cf">{sum(scores)/len(scores):.1f}</b></div>'
            f'<div>最好：<b style="color:#6cf">{min(scores)}</b></div>'
            f'<div>最差：<b style="color:#6cf">{max(scores)}</b></div>'
            f'<div>par：<b style="color:#6cf">{pa}</b></div>'
            f'<div>鸟：<b style="color:#6cf">{bi}</b></div>'
            f'<div>鹰：<b style="color:#6cf">{ea}</b></div>'
            f'</div></div>'
        )
    body = f"<h1>年度汇总（按季度）</h1>{''.join(rows)}"
    (OUT / "quarterly.html").write_text(page("年度汇总", body))


def render_timeline(rounds: list[dict]) -> None:
    # latest first
    by_ym: dict[str, list[dict]] = defaultdict(list)
    for r in sorted(rounds, key=lambda r: r["date"], reverse=True):
        by_ym[r["date"][:7]].append(r)
    blocks = []
    for ym, rs in by_ym.items():
        items = []
        for r in rs:
            par = r["par"]
            score = r["strokes"]
            net = (score - par) if (score and par) else None
            net_str = f"<span style='color:{'#6cf' if (net is not None and net <= 0) else '#fa6' if (net is not None and net <= 6) else '#f76'}'>{net:+d}</span>" if net is not None else ""
            items.append(
                f'<div class="card" style="margin-bottom:8px">'
                f'<div style="display:flex;justify-content:space-between;align-items:center">'
                f'<div><div style="color:#aaa">{r["course"]}</div>'
                f'<div style="color:#888;font-size:12px">{r["date"][:10]} · {r["holesCompleted"]} 洞 · par {par}</div></div>'
                f'<div style="text-align:right"><div style="color:#6cf;font-size:18px;font-weight:600">{score or "-"}</div><div style="font-size:12px">{net_str}</div></div>'
                f'</div></div>'
            )
        blocks.append(f'<div style="margin-bottom:14px"><div style="color:#888;font-size:13px;margin-bottom:6px">{ym}</div>{"".join(items)}</div>')
    body = f"""<h1>打球记录</h1>
<div class="stats">共 <b>{len(rounds)}</b> 场，倒序</div>
{''.join(blocks)}"""
    (OUT / "timeline.html").write_text(page("打球记录", body))


def render_scorecards(rounds: list[dict]) -> None:
    """Per-round 18-hole grid like the mockup. Show recent 30 rounds."""
    recent = sorted([r for r in rounds if r["holesCompleted"] == 18 and r["holes"]], key=lambda r: r["date"], reverse=True)[:30]
    blocks = []
    for r in recent:
        pars = r["holePars"] if len(r["holePars"]) == 18 else "0" * 18
        front_total = sum(h["strokes"] for h in r["holes"][:9] if h.get("strokes"))
        back_total = sum(h["strokes"] for h in r["holes"][9:] if h.get("strokes"))

        def cell(h, par):
            try:
                p = int(par)
                net = h.get("strokes", 0) - p
            except Exception:
                net = "?"
            color = "#888" if net == 0 else ("#7c7" if isinstance(net, int) and net < 0 else
                                              "#cc7" if net == 1 else "#fc8" if net == 2 else "#f76")
            symbol = "" if net == 0 else (f"+{net}" if isinstance(net, int) and net > 0 else f"{net}")
            return f'<div style="text-align:center;padding:2px;color:{color};font-size:12px">{symbol}</div>'

        front_cells = "".join(
            f'<div style="display:flex;flex-direction:column;align-items:center;width:30px"><div style="color:#888;font-size:10px">{i+1}</div><div style="color:#666;font-size:10px">par {pars[i]}</div><div style="color:#ddd;font-size:13px">{r["holes"][i].get("strokes","-")}</div>{cell(r["holes"][i], pars[i])}</div>'
            for i in range(9)
        )
        back_cells = "".join(
            f'<div style="display:flex;flex-direction:column;align-items:center;width:30px"><div style="color:#888;font-size:10px">{i+1}</div><div style="color:#666;font-size:10px">par {pars[i]}</div><div style="color:#ddd;font-size:13px">{r["holes"][i].get("strokes","-")}</div>{cell(r["holes"][i], pars[i])}</div>'
            for i in range(9, 18)
        )
        blocks.append(
            f'<div class="card" style="margin-bottom:12px">'
            f'<div style="display:flex;justify-content:space-between;margin-bottom:8px">'
            f'<div><div style="color:#aaa">{r["course"]}</div>'
            f'<div style="color:#888;font-size:12px">{r["date"][:10]}</div></div>'
            f'<div style="color:#6cf;font-size:20px;font-weight:600">{r["strokes"]}</div></div>'
            f'<div style="color:#888;font-size:12px;margin-bottom:4px">前九 {front_total}</div>'
            f'<div style="display:flex;gap:2px;margin-bottom:8px;flex-wrap:wrap">{front_cells}</div>'
            f'<div style="color:#888;font-size:12px;margin-bottom:4px">后九 {back_total}</div>'
            f'<div style="display:flex;gap:2px;flex-wrap:wrap">{back_cells}</div>'
            f'</div>'
        )
    body = f"""<h1>成绩卡（最近 30 场）</h1>
{''.join(blocks)}"""
    (OUT / "scorecards.html").write_text(page("成绩卡", body))


def render_course_details(rounds: list[dict], course_slugs: dict[str, str]) -> None:
    """One detail page per canonical course: round list + scorecard grids."""
    course_dir = OUT / "course"
    course_dir.mkdir(exist_ok=True)

    by_course: dict[str, list[dict]] = defaultdict(list)
    for r in rounds:
        by_course[r["courseCanonical"]].append(r)

    for name, rs in by_course.items():
        slug = course_slugs[name]
        rs.sort(key=lambda r: r["date"], reverse=True)
        scores18 = [r["strokes"] for r in rs if r["holesCompleted"] == 18 and r["strokes"]]
        avg = sum(scores18) / len(scores18) if scores18 else None
        best = min(scores18) if scores18 else None
        worst = max(scores18) if scores18 else None
        variants = sorted({r["course"] for r in rs})

        round_blocks = []
        for r in rs:
            par = r["par"]
            net = (r["strokes"] - par) if (r["strokes"] and par) else None
            net_color = "#6cf" if (net is not None and net <= 0) else "#fa6" if (net is not None and net <= 6) else "#f76"
            net_str = f'<span style="color:{net_color}">{net:+d}</span>' if net is not None else ""

            grid = ""
            holes = r.get("holes") or []
            pars = r.get("holePars") or ""
            if holes:
                cells = []
                for i, h in enumerate(holes):
                    p_str = pars[i] if i < len(pars) else "0"
                    try:
                        p = int(p_str)
                        d = (h.get("strokes", 0) - p) if (h.get("strokes") and p > 0) else None
                    except Exception:
                        p, d = 0, None
                    color = "#888" if d == 0 else ("#7c7" if isinstance(d, int) and d < 0 else
                                                   "#cc7" if d == 1 else "#fc8" if d == 2 else "#f76" if isinstance(d, int) else "#888")
                    diff_str = ("+" + str(d)) if isinstance(d, int) and d > 0 else (str(d) if isinstance(d, int) and d != 0 else "")
                    cells.append(
                        f'<div style="display:flex;flex-direction:column;align-items:center;width:30px">'
                        f'<div style="color:#888;font-size:10px">{h.get("number", i+1)}</div>'
                        f'<div style="color:#666;font-size:10px">par {p}</div>'
                        f'<div style="color:#ddd;font-size:13px">{h.get("strokes","-")}</div>'
                        f'<div style="color:{color};font-size:11px">{diff_str}</div>'
                        f'</div>'
                    )
                front = "".join(cells[:9])
                back = "".join(cells[9:])
                grid = f'<div style="display:flex;gap:2px;margin-top:8px;flex-wrap:wrap">{front}</div>'
                if back:
                    grid += f'<div style="display:flex;gap:2px;margin-top:6px;flex-wrap:wrap">{back}</div>'

            round_blocks.append(
                f'<div class="card" style="margin-bottom:10px">'
                f'<div style="display:flex;justify-content:space-between;align-items:flex-start">'
                f'<div><div style="color:#aaa;font-size:14px">{r["date"][:10]} · {r["course"]}</div>'
                f'<div style="color:#666;font-size:11px;margin-top:2px">{r["holesCompleted"]} 洞 · par {par or "?"}</div></div>'
                f'<div style="text-align:right">'
                f'<div style="color:#6cf;font-size:18px;font-weight:600">{r["strokes"] or "-"}</div>'
                f'<div style="font-size:12px">{net_str}</div></div></div>'
                f'{grid}'
                f'</div>'
            )

        avg_str = f'{avg:.1f}' if avg else "-"
        body = f"""
<h1>{name}</h1>
<div class="sub">{rs[0].get("city") or ""} {rs[0].get("country") or ""}</div>
<div class="stats">
  <span>总场次 <b>{len(rs)}</b></span>
  <span>18 洞 <b>{len(scores18)}</b></span>
  <span>均杆 <b>{avg_str}</b></span>
  <span>最好 <b>{best or "-"}</b></span>
  <span>最差 <b>{worst or "-"}</b></span>
</div>
<div style="margin-bottom:14px"><a href="../courses_list.html" style="color:#6cf;font-size:13px">← 返回球场列表</a></div>
{''.join(round_blocks)}"""
        page_html = page(name, body, nav=make_nav(prefix="../"))
        (course_dir / f"{slug}.html").write_text(page_html)
    print(f"  wrote {len(by_course)} course detail pages")


def render_shots(shots: list[dict]) -> None:
    """Shot distance histogram by club."""
    active: dict[str, list[float]] = defaultdict(list)
    retired: dict[str, list[float]] = defaultdict(list)
    dropped = 0
    for s in shots:
        if not (s["meters"] and s["meters"] > 1):
            continue
        cname = s["clubName"]
        if cname in (None, "", "Unknown", "?"):
            continue
        cap = max_distance_for(cname)
        if s["meters"] > cap:
            dropped += 1
            continue
        bucket = retired if s.get("clubRetired") else active
        bucket[cname].append(s["meters"])

    SELF_ASSESS = {
        "1W": 230, "3W": 205, "3H": 195,
        "5I": 170, "6I": 160, "7I": 150, "8I": 140, "9I": 130,
        "PW": 120, "A杆": 110, "50°": 100, "54°": 90, "58°": 80,
    }

    def stats_block(buckets: dict[str, list[float]]) -> tuple[list, list]:
        items_ = sorted(buckets.items(), key=lambda kv: -sum(kv[1]) / max(1, len(kv[1])))
        items_ = [(c, ds) for c, ds in items_ if len(ds) >= 3]
        rs, cd = [], []
        for club, ds in items_:
            ds_s = sorted(ds)
            n = len(ds_s)
            med = ds_s[n // 2]
            p25 = ds_s[n // 4]
            p75 = ds_s[3 * n // 4]
            self_v = SELF_ASSESS.get(club.replace(" 旧", "").strip())
            if self_v is None:
                self_cell = '<td style="color:#555">-</td>'
                diff_cell = '<td style="color:#555">-</td>'
            else:
                diff = p75 - self_v
                color = "#6c6" if diff >= -5 else ("#fc6" if diff >= -20 else "#f66")
                self_cell = f'<td style="color:#888">{self_v}</td>'
                diff_cell = f'<td style="color:{color}">{diff:+.0f}</td>'
            rs.append(f'<tr><td>{club}</td><td>{n}</td><td>{p25:.0f}</td><td style="color:#6cf">{med:.0f}</td><td>{p75:.0f}</td><td>{max(ds):.0f}</td>{self_cell}{diff_cell}</tr>')
            cd.append({"club": club, "median": med, "p25": p25, "p75": p75, "n": n})
        return rs, cd

    active_rows, active_chart = stats_block(active)
    retired_rows, _ = stats_block(retired)
    total_active = sum(len(ds) for ds in active.values())
    total_retired = sum(len(ds) for ds in retired.values())

    retired_section = ""
    if retired_rows:
        retired_section = f"""
<h1 style="margin-top:24px;font-size:16px;color:#888">退役球杆（{total_retired} 杆历史数据）</h1>
<div class="card"><table>
<thead><tr><th>球杆</th><th>次数</th><th>P25</th><th>中位数</th><th>P75</th><th>最远</th><th>自评</th><th>P75−自评</th></tr></thead>
<tbody>{''.join(retired_rows)}</tbody>
</table></div>"""

    body = f"""
<h1>击球距离分布（按球杆）</h1>
<div class="stats">在用 <b>{total_active}</b> 杆 · 退役 <b>{total_retired}</b> 杆 · 剔除离群 <b>{dropped}</b> 杆</div>
<div class="card"><table>
<thead><tr><th>球杆</th><th>次数</th><th>P25</th><th>中位数</th><th>P75</th><th>最远</th><th>自评</th><th>P75−自评</th></tr></thead>
<tbody>{''.join(active_rows)}</tbody>
</table></div>
<div class="card" style="margin-top:14px;height:380px"><canvas id="ch"></canvas></div>
{retired_section}
<script>
const data = {json.dumps(active_chart, ensure_ascii=False)};
new Chart(document.getElementById('ch'), {{
  type:'bar', data:{{
    labels: data.map(d=>d.club),
    datasets:[{{label:'中位数距离 (m)', data:data.map(d=>d.median), backgroundColor:'#6cf'}}]
  }},
  options:{{ responsive:true, maintainAspectRatio:false,
    scales:{{ x:{{ticks:{{color:'#888'}}, grid:{{color:'#333'}}}}, y:{{ticks:{{color:'#888'}}, grid:{{color:'#333'}}, beginAtZero:true}} }},
    plugins:{{legend:{{display:false}}}}
  }}
}});
</script>"""
    head = '<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>'
    (OUT / "shots.html").write_text(page("击球距离", body, head))


def main() -> None:
    print("loading rounds...")
    raw_rounds = load_rounds()
    print(f"  {len(raw_rounds)} raw rounds")
    rounds = merge_same_day_halves(raw_rounds)
    print(f"  {len(rounds)} after merge ({sum(1 for r in rounds if r['holesCompleted']==18)} are 18-hole)")
    print("loading shots...")
    shots = load_shots(raw_rounds)  # use raw rounds since shots are keyed by individual scorecardId
    print(f"  {len(shots)} shots")

    # Build a stable slug per canonical course so links work across pages.
    canon_names = sorted({r["courseCanonical"] for r in rounds})
    course_slugs = {n: f"c{i:03d}" for i, n in enumerate(canon_names)}

    render_index(rounds, shots)
    render_trend(rounds)
    render_courses(rounds, course_slugs)
    render_courses_list(rounds, course_slugs)
    render_course_details(rounds, course_slugs)
    render_analysis(rounds)
    render_distribution(rounds)
    render_frequency(rounds)
    render_quarterly(rounds)
    render_timeline(rounds)
    render_scorecards(rounds)
    render_shots(shots)
    print(f"\nwrote pages -> {OUT}")


if __name__ == "__main__":
    main()
