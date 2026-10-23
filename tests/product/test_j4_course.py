"""J4: course identity over HTTP and independent, small polygon arithmetic."""
import copy
import json
import unittest
from unittest.mock import patch

from ai_caddie.courses import course_prep, course_reference, course_search
from ai_caddie.geometry import elevation
from ai_caddie.caddie import mobile_live
from ai_caddie.history.history import HistoryData
from tests.product._support_c16c import HTTPFixture, vectors


def mesh(points, faces):
    # Input adapter only: local (east,north) -> Garmin (-east,height,north).
    return {"positions": [[-x, 0, y] for x,y in points], "faces": faces}


def join_mesh(*meshes):
    points, faces = [], []
    for m in meshes:
        offset = len(points)
        points.extend(m["positions"])
        faces.extend([[i+offset for i in tri] for tri in m["faces"]])
    return {"positions": points, "faces": faces}


def rectangle(x1,y1,x2,y2):
    return mesh([(x1,y1),(x2,y1),(x2,y2),(x1,y2)], [[0,1,2],[0,2,3]])


class CourseHTTPTests(HTTPFixture, unittest.TestCase):
    def catalogue(self):
        """Fake only cached provider facts, never a package or a hole mapping."""
        courses = {c["globalId"]: c for c in vectors("loop_map.json")["courses"]}
        names = {81001:"Example Eighteen",82001:"Example Venue ~ A",
                 82002:"Example Venue ~ B",82003:"Example Venue ~ C"}
        self.stack.enter_context(patch.object(course_reference, "courseview_release_info",
            side_effect=lambda gid, **kw: {"name":names[int(gid)], "holes":[{"par":4}]*courses[int(gid)]["holeCount"]}
                if int(gid) in courses else None))
        self.stack.enter_context(patch.object(course_reference, "courseview_par",
            side_effect=lambda gid, **kw: [4]*courses[int(gid)]["holeCount"] if int(gid) in courses else None))
        self.stack.enter_context(patch.object(course_reference, "localized_courseview_name",
            side_effect=lambda gid, **kw: names.get(int(gid))))

    def test_j4_1_discovery_deduplicates_and_names_venues(self):
        from server_v2 import main, map_startup
        self.catalogue()
        # Fake Garmin protobuf bytes at the transport boundary: duplicate catalogue id.
        def varint(value):
            out = bytearray()
            while value > 127:
                out.append((value & 127) | 128); value >>= 7
            return bytes(out) + bytes([value])
        def field(n, value):
            if isinstance(value, str):
                value = value.encode()
            return (varint(n*8+2)+varint(len(value))+value if isinstance(value,bytes)
                    else varint(n*8)+varint(value))
        def record(gid,name,holes,lat):
            return field(4,b"".join(field(k,v) for k,v in [
                (7,gid),(12,name),(13,holes),(9,lat),(10,0)]))
        a = record(82001,"Example Venue ~ A",9,0)
        pb = (a+a+record(82002,"Example Venue ~ B",9,100)+record(82003,"Example Venue ~ C",9,200)
              +record(81001,"Example Eighteen",18,119305))
        # All three nines belong to one 27-hole venue. A played A/C round has
        # 18 holes, but neither A nor C may be advertised as an 18-hole layout.
        rounds=[{"id":str(i),"globalId":gid,"course":name,"date":"2026-01-02",
                 "holesCompleted":18,"holePars":"4"*18,"lat":0,"lon":0}
                for i,(gid,name) in enumerate([(82001,"Example Venue ~ A/C"),
                    (82001,"Example Venue ~ A/C"),(82002,"Example Venue ~ B/A"),
                    (82003,"Example Venue ~ C/A"),(81001,"Example Eighteen")])]
        self.data=lambda: HistoryData(raw_rounds=rounds,rounds=rounds,shots=[])
        self.stack.enter_context(patch.object(main,"cached_load_history_data",side_effect=lambda **kw:self.data()))
        self.stack.enter_context(patch.object(mobile_live,"_courseview_tee_names",return_value=[]))
        sources={}
        # Golden is physical source coverage, not the hole count of a past played combination.
        expected=[(81001,"Example Eighteen",18),(82001,"Example Venue",9),
                  (82002,"Example Venue",9),(82003,"Example Venue",9)]
        course_search._clear_nearby_cache_for_tests()
        for mode in ["search", "nearby"]:
            with self.subTest(row=mode), \
                 patch.object(course_search,"fetch_bytes",return_value=pb), \
                 patch.object(map_startup,"enqueue_nearby"):
                response = self.client.get("/api/v2/courses/"+mode, params={"name":"Example",
                    "latitude":0,"longitude":0})
                self.assertEqual(response.status_code,200,response.text)
                matches = response.json()["matches"]
                actual=[(r["globalId"],r["venueName"],r["holes"]) for r in matches]
                self.assertEqual(sorted(actual),expected,"source layout coverage must be explicit: 9,9,9 and 18")
                sources[mode]=actual
        with self.subTest(row="recent"):
            response=self.client.get("/api/v2/mobile/courses/options")
            self.assertEqual(response.status_code,200,response.text)
            courses=response.json()["courses"]
            actual=[(r["globalId"],r["venueName"],r["segmentHoles"]) for r in courses]
            self.assertEqual(sorted(actual),expected,"recent played 18-hole combos still expose 9-hole layouts")
            sources["recent"]=actual
        with self.subTest(row="downloaded"):
            # The downloaded source is a locally retained HTTP package. Native list grouping
            # belongs to Swift; here verify the server facts consumed by that same grouping.
            saved=[]
            for gid,loops in [(81001,"81001:front,81001:back"),(82001,"82001:all"),
                              (82002,"82002:all"),(82003,"82003:all")]:
                response=self.client.get(f"/api/v2/mobile/courses/{gid}/package",
                    params={"loops":loops,"include_event_cursor":"false"})
                self.assertEqual(response.status_code,200,response.text)
                path=self.root/f"downloaded-{gid}.json"
                path.write_text(response.text)
                package=json.loads(path.read_text())
                saved.append((gid,package["course"]["venueName"],len(package["holes"])))
            self.assertEqual(sorted(saved),expected,"retained package coverage must match the chosen physical layout")
            sources["downloaded"]=saved
        with self.subTest(row="downloaded_A_only"):
            only_a=json.loads((self.root/"downloaded-82001.json").read_text())
            self.assertEqual((only_a["course"]["venueName"],len(only_a["holes"])),("Example Venue",9),
                             "a retained A package covers nine physical holes of a 27-hole venue")
        if len(sources)!=4:
            return  # Source assertions already failed; do not obscure them with a missing-key error.
        for names in [("nearby","search"),("recent","nearby","search"),
                      ("downloaded","nearby","search"),("recent","downloaded","nearby","search")]:
            with self.subTest(row="+".join(names)):
                # This is an identity/coverage projection of actual backend outputs, not a
                # replacement implementation of the native picker. Repeated source records
                # must supply identical grouping keys; all three loop ids map to one venue.
                facts=[fact for name in names for fact in sources[name]]
                self.assertEqual(sorted(set(facts)),expected)
                self.assertEqual({venue for _,venue,_ in facts},{"Example Venue","Example Eighteen"})
                self.assertEqual({(gid,coverage) for gid,venue,coverage in facts if venue=="Example Venue"},
                                 {(82001,9),(82002,9),(82003,9)})
                self.assertEqual(sum(dict((gid,coverage) for gid,venue,coverage in facts
                                          if venue=="Example Venue").values()),27,
                                 "three distinct physical nines cover 27 holes; repeated sources add no coverage")

    def test_j4_2_illegal_course_parameters_are_rejected(self):
        self.catalogue()
        # No entries, >2, wrong path, wrong half/type, cross-venue, unproven course,
        # empty tokens and invalid priority/map flags all lack one playable interpretation.
        rows = [(81001,"",{}),(81001,"81001:front,81001:back,81001:front",{}),
                (81001,"82001:all",{}),(81001,"81001:all",{}),
                (82001,"82001:front",{}),(82001,"82001:all,81001:front",{}),
                (99999,"99999:all",{}),(81001,"81001:middle",{}),
                (81001,"81001:front,",{}),(81001,"81001:front",{"priority_hole":10}),
                (81001,"81001:front",{"priority_hole":0}),
                (81001,"81001:front",{"map_only":"true","ensure_geometry":"true"})]
        for gid,loops,extra in rows:
            with self.subTest(row=(gid,loops,extra)):
                response = self.client.get(f"/api/v2/mobile/courses/{gid}/package",params={
                    "loops":loops,"include_event_cursor":"false",**extra})
                self.assertEqual(response.status_code,422,response.text)
                if not extra:
                    status=self.client.get(f"/api/v2/courses/{gid}/install/status",params={"loops":loops})
                    self.assertEqual(status.status_code,422,status.text)
        self.assertFalse(list(self.root.rglob("*scorecard*.json")))

    def test_j4_3_packages_equal_hand_physical_hole_table(self):
        self.catalogue()
        columns = vectors("loop_map.json")["holeColumns"]
        for row in vectors("loop_map.json")["cases"]:
            with self.subTest(row=row["id"]):
                # Inspect construction independently of its defensive identity validator.
                # A shifted/wrong-half package must fail this golden comparison even if
                # validation is disabled, rather than merely returning an HTTP 422.
                loops=[(int(part.split(":")[0]),part.split(":")[1]) for part in row["loops"].split(",")]
                with patch.object(mobile_live,"validate_round_identity"):
                    raw=mobile_live.build_live_round_package_for_loops(loops,data=self.data(),
                        root=self.root,annotations_root=self.root,include_event_cursor=False,
                        allow_lightweight_fetch=False)
                self.assertEqual([[h["number"],h["sourceGlobalId"],h["sourceLocalHole"]] for h in raw["holes"]],
                                 [hole[:3] for hole in row["expectedHoles"]],
                                 "physical-hole golden with identity validation disabled")
                self.assertEqual([[h[k] for k in columns] for h in raw["holes"]],row["expectedHoles"],
                                 "physical-hole golden with identity validation disabled")
                response = self.client.get(f"/api/v2/mobile/courses/{row['pathGlobalId']}/package",
                    params={"loops":row["loops"],"include_event_cursor":"false"})
                self.assertEqual(response.status_code,200,response.text)
                payload = response.json()
                self.assertEqual(payload["loopKey"],row["expectedLoopKey"])
                self.assertEqual([[h[k] for k in columns] for h in payload["holes"]],row["expectedHoles"])
                # A second request must keep the same physical table (including same-loop replay).
                again = self.client.get(f"/api/v2/mobile/courses/{row['pathGlobalId']}/package",
                    params={"loops":row["loops"],"include_event_cursor":"false"}).json()
                self.assertEqual([[h[k] for k in columns] for h in again["holes"]],row["expectedHoles"])


class GeometryTests(unittest.TestCase):
    def test_j4_4_geometry_equals_polygon_arithmetic(self):
        # A 20x20 square at (0,200), triangle at (100,200), and an unequal-area
        # L surface. Centroids are shoelace centroids, not vertex averages.
        square = rectangle(-10,190,10,210)
        triangle = mesh([(90,190),(110,190),(100,220)],[[0,1,2]])
        ell = mesh([(0,180),(30,180),(30,190),(10,190),(10,210),(0,210)],
                   [[0,1,2],[0,2,3],[0,3,4],[0,4,5]])
        rows = [("square",square,[(0,0),(0,200)],(190.3,200,210.2)),
                ("nearest_connected",join_mesh(square,triangle),[(100,0),(100,200)],(190.3,200,220)),
                ("unequal_area",ell,[(0,0),(10,190)],(180,191.3,210.2)),
                ("missing_green",{},[(0,0),(0,200)],None),("missing_route",square,[],None)]
        for name,green,route,expected in rows:
            with self.subTest(row=name):
                result = course_prep._green_distances({"Green.drc":green},route)
                if expected is None:
                    self.assertEqual(result,{"available":False})
                else:
                    # Square nearest/farthest vertices: sqrt(190^2+10^2), sqrt(210^2+10^2).
                    # Triangle centroid (100,200); L area=500, centroid=(11,191).
                    self.assertTrue(result["available"])
                    self.assertEqual((result["frontM"],result["middleM"],result["backM"]),expected)
        for name,heights,expected in [("up",[10,20],(10,11)),("down",[20,10],(-10,-11)),("none",[],None)]:
            with self.subTest(row=name):
                positions = [[0,heights[0],0],[0,heights[1],200]] if heights else []
                result = elevation.playslike({"ground":{"positions":positions}},(0,0),(0,200))
                if expected is None:
                    self.assertEqual(result,{"available":False})
                else:
                    self.assertEqual((result["deltaM"],result["deltaYd"]),expected) # +/-10m x 1.09361 -> +/-11yd.
        # Ray north intersects the narrow water rectangle exactly at 80 and 120m;
        # the dogleg east intersects it at route offsets 180 and 220, radial distances differ.
        for name,route,lake,expected in [
            ("straight",[(0,0),(0,300)],rectangle(-5,80,5,120),(80,120,80,120)),
            ("dogleg",[(0,0),(0,100),(200,100)],rectangle(80,95,120,105),(128.1,156.2,180,220))]:
            with self.subTest(row=name):
                hazards = course_prep.route_hazards({"Lake.drc":lake},route,to_px=lambda p:p)
                self.assertEqual(hazards["water_carry"],[[expected[2],expected[3]]])
                detail = hazards["details"][0]
                self.assertEqual(tuple(detail[k] for k in ("frontM","backM","frontRouteM","backRouteM")),expected)
        # Side bunker: nearest (20,100), farthest (30,120) -> 102.0/123.7m;
        # orthogonal northbound projections are 100/120m and lateral gap is 20m.
        with self.subTest(row="side_bunker"):
            detail=course_prep.route_hazards({"Bunker.drc":rectangle(20,100,30,120)},
                [(0,0),(0,300)],to_px=lambda p:p)["details"][0]
            self.assertEqual(tuple(detail[k] for k in ("frontM","backM","frontRouteM","backRouteM","sideM")),
                             (102.0,123.7,100,120,20))
        # Ring input: four connected strips surround a 10x10 cutout. Its area is
        # 30x30 - 10x10 = 800; split into two isolated rectangles -> 2 polygons.
        ring = mesh([(0,0),(30,0),(30,30),(0,30),(10,10),(20,10),(20,20),(10,20)],
                    [[0,1,5],[0,5,4],[1,2,6],[1,6,5],[2,3,7],[2,7,6],[3,0,4],[3,4,7]])
        for name,by,expected in [("missing",{},None),
                ("square",{"Fairway.drc":rectangle(0,0,30,30)},(1,0,900)),
                ("cutout",{"Fairway.drc":ring},(1,1,800)),
                ("split",{"Fairway.drc":join_mesh(rectangle(0,0,10,10),rectangle(0,20,10,30))},(2,0,200))]:
            with self.subTest(row=name):
                result = course_prep._fairway_outline(by,[(5,-5),(5,35)],{"hole":{"RefLat":0,"RefLon":0}},lambda p:p)
                if expected is None:
                    self.assertIsNone(result)
                else:
                    polygons=result["polygons"]
                    # Independent shoelace on returned local pixels; never product geometry helpers.
                    def area(points):
                        return abs(sum(a[0]*b[1]-a[1]*b[0] for a,b in zip(points,points[1:]+points[:1])))/2
                    total=sum(area(p["outerPx"])-sum(area(h) for h in p["holesPx"]) for p in polygons)
                    self.assertEqual((len(polygons),sum(len(p["holesPx"]) for p in polygons),total),expected)
                    expected_outer = ({(0,0),(30,0),(30,30),(0,30)} if name in ("square","cutout")
                        else {(0,0),(10,0),(10,10),(0,10),(0,20),(10,20),(10,30),(0,30)})
                    self.assertEqual({tuple(v) for p in polygons for v in p["outerPx"]},expected_outer)
                    if name == "cutout":
                        self.assertEqual({tuple(v) for v in polygons[0]["holesPx"][0]},
                                         {(10,10),(20,10),(20,20),(10,20)})
