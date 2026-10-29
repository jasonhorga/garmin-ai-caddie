"""Isolated HTTP probe for release-bound geometry; no history, provider or model access.

Run in a fresh child process so import-time data roots and caches cannot leak between fixtures.
The parent supplies a root containing only course geometry; all writes use a temporary copy.
"""
from __future__ import annotations

from contextlib import closing
import json
import os
from pathlib import Path
import shutil
import sys
from tempfile import TemporaryDirectory
from time import perf_counter
from unittest.mock import patch


def run(root: Path, *, warm_requests: int = 1, mode: str = "fixture", position: list | None = None,
        distance: float | None = 284.3, distance_source: str | None = None) -> dict:
    with TemporaryDirectory() as directory:
        isolated = Path(directory)
        shutil.copytree(root, isolated, dirs_exist_ok=True)
        os.environ.update(AI_CADDIE_ROOT=str(isolated), AI_CADDIE_PRIVATE_ROOT=str(isolated),
                          AI_CADDIE_DATA_MODE=mode, AI_CADDIE_LLM_PROVIDER="static",
                          AI_CADDIE_ADMIN_TOKEN="", AI_CADDIE_SECURITY_PROFILE="")
        sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
        from fastapi.testclient import TestClient
        from ai_caddie.courses import course_prep
        from ai_caddie.geometry import shot_projection
        from ai_caddie.geometry.measure_prodgeometry_distances import mesh_components, point_in_triangle, select_green_component
        from server_v2 import caddie
        from server_v2.main import app

        local = position if position is not None else [311.75,89.625]
        lat, lon = shot_projection.local_to_world(*local, ref_lat=22.541387, ref_lon=113.955258)
        context = {"source":"ios_live", "sourceRef":"fixture-course:31834:2", "globalId":31834,
                   "hole":2, "localHole":2, "teeBox":"blue", "par":4, "yards":310,
                   "distanceToPin_m":284.3, "lie":"tee", "currentLocation":{"latitude":lat,"longitude":lon},
                   "greenDistances":{"frontM":272.0,"middleM":284.3,"backM":298.0,
                                     "frontRouteM":306.2,"backRouteM":320.9},
                   # Synthetic bag, not the production player's shots/profile.
                   "clubProfiles":{name:{"clubName":name,"median_m":carry,"p10_m":carry-5,
                                         "p90_m":carry+5,"sampleSize":20}
                                   for name,carry in [("Driver",197),("8I",121)]}}
        if distance is None:
            context.pop("distanceToPin_m")
        else:
            context["distanceToPin_m"] = distance
        if distance_source is not None:
            context["distanceToPinSource"] = distance_source
        hydrated = {}
        real_hydrate = caddie.hydrate_live_caddie_geometry_context

        def capture(*args, **kwargs):
            value = real_hydrate(*args, **kwargs)
            hydrated.clear()
            hydrated.update(value)
            return value

        samples = []
        with (patch.object(course_prep, "_corrected_profile_history", return_value=None),
              patch.object(caddie, "DECISION_LEDGER_ROOT", isolated / "ledger"),
              patch.object(caddie, "hydrate_live_caddie_geometry_context", side_effect=capture),
              patch("socket.socket.connect", side_effect=AssertionError("unexpected network")),
              closing(TestClient(app)) as client):
            for _ in range(1 + warm_requests):
                start = perf_counter()
                response = client.post("/api/v2/caddie/decision", json={"shotType":"tee" if position is None else "approach", "context":context,
                                                                        "includeExplanation":False})
                samples.append((perf_counter() - start) * 1000)
                if response.status_code != 200:
                    raise AssertionError((response.status_code, response.text))
                plan = response.json()

        md = json.loads((isolated / "output/prodgeometry/gid31834_h02_meshes.json").read_text())
        # Independent client-style station interpolation over the factual selected-Tee path.
        line = md["hole"]["Doglegs"][0]["Line"]
        points = [[311.75,89.625]] + [[p["X"],p["Y"]] for p in line[1:]]
        green = next(m for m in md["meshes"] if m["name"] == "Green.drc")
        selected_green = select_green_component(mesh_components(green), tuple(points[-1]))

        def landing(station):
            import math
            for a,b in zip(points,points[1:]):
                length = math.dist(a,b)
                if station <= length:
                    return [a[i]+(b[i]-a[i])*station/length for i in (0,1)]
                station -= length
            return points[-1]

        chains = []
        for sequence in plan["sequences"]:
            clubs = sequence["clubs"]
            point = landing(clubs[-1]["routeOffset_m"])
            inside = any(point_in_triangle(tuple(point), *tri) for tri in selected_green["triangles"])
            chains.append({"clubs":[s["clubName"] for s in clubs],
                           "carries_m":[s["targetCarry_m"] for s in clubs],
                           "offsets_m":[s["routeOffset_m"] for s in clubs],
                           "lastLandingLocal":point,"lastLandingInsideGreen":inside})
        route = hydrated.get("routeEvidence") or {}
        from ai_caddie.geometry.geometry_evidence import geometry_coverage_for_hole
        from ai_caddie.core import data
        from ai_caddie.caddie.decision import _sequence_distance
        return {"rootMatched":data.ROOT == isolated,
                "planningDistance_m":_sequence_distance(hydrated),
                "distanceToPinSource":hydrated.get("distanceToPinSource"),
                "suppliedDistance_m":context.get("distanceToPin_m"),
                "coverage":geometry_coverage_for_hole(31834,2,require_current_authority=True),
                "holeRemaining_m":hydrated.get("holeRemaining_m"),
                "carries_m":[o["carry_m"] for o in plan["options"]],
                "cold_ms":samples[0],"warm_ms":samples[1:],"chains":chains,
                "routeLength_m":route.get("routeLength_m"),"routeLocal":route.get("routeLocal"),
                "water":[z for z in route.get("avoidZones",[]) if z["kind"] == "water"],
                "geometry":hydrated.get("geometry",{}).get("coverage"),
                "options":[{"club":o.get("club"),"targetLocal":o.get("targetLocal")} for o in plan["options"]],
                "missingData":plan.get("missingData")}


if __name__ == "__main__":
    args = json.loads(sys.stdin.read())
    print(json.dumps(run(Path(args["root"]), warm_requests=args.get("warm_requests",1),
                         mode=args.get("mode","fixture"), position=args.get("position"),
                         distance=args.get("distance",284.3), distance_source=args.get("distance_source")), ensure_ascii=False))
