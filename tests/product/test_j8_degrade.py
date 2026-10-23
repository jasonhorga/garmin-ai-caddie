"""J8: missing evidence and old/new persisted corrections remain honest."""
import hashlib
import json
import re
import unittest

from ai_caddie.history.history import HistoryData
from ai_caddie.history.history_stats import build_history_stats
from ai_caddie.reports.reports import generate_deterministic_report
from ai_caddie.rounds import round_corrections
from tests.product._support_c16c import HTTPFixture, golden_context, vectors


def walk(value, path=""):
    if isinstance(value, dict):
        for k,v in value.items():
            yield path+"/"+k, k, v
            yield from walk(v,path+"/"+k)
    elif isinstance(value, list):
        for i,v in enumerate(value):
            yield from walk(v,path+f"/{i}")


class DegradeTests(HTTPFixture, unittest.TestCase):
    def test_j8_1_no_baseline_no_prescription(self):
        # A single untracked bogey gives +1 but no shot evidence or comparison baseline.
        one = {"id":"one","ids":["one"],"date":"2026-01-02","course":"Example",
               "holesCompleted":1,"holes":[{"number":1,"par":4,"strokes":5}],"strokes":5,"par":4}
        for name,rounds in [("empty",[]),("untracked_bogey",[one])]:
            with self.subTest(row=name):
                stats = build_history_stats(HistoryData(raw_rounds=rounds,rounds=rounds,shots=[]),
                    data_mode="fixture",annotations_root=self.root,weather_root=self.root,
                    reports_root=self.root,decision_audit_root=self.root)
                profile = stats["playerProfile"]
                self.assertEqual((profile["strengths"],profile["weaknesses"],profile["caddieBiases"]),([],[],[]))
                self.assertIsNone(profile["topWeakness"])
                self.assertEqual(profile["sourceRefs"],[])
                # An absent calibrated baseline cannot yield a numeric SG/saving/prescription.
                banned = {"strokesgained","sg","strokessaved","potentialstrokessaved",
                          "practiceplan","prescription","recommendedpractice"}
                self.assertEqual([(p,v) for p,k,v in walk(stats)
                    if re.sub(r"[^a-z]","",k.lower()) in banned and v not in (None,[],{})],[])
        # Report kinds all receive no facts/evidence; no inference, source, or prescription
        # can exist. This checks actual report payloads, never exact prose wording.
        for kind in ("round","trend","hole","course","club"):
            with self.subTest(row="report_"+kind):
                report = generate_deterministic_report({"kind":kind,"subjectId":"example",
                    "factsUsed":[],"missingData":[{"label":"baseline","reason":"not measured"}]})
                self.assertEqual(report["inferencesMade"],[])
                self.assertEqual(report["sourceRefs"],[])
                self.assertEqual(report["unsupportedClaims"],[])
                self.assertIsNone(re.search(r"(?i)strokes?\s*gained|\bSG\b|可省\s*\d|处方|最该练",report["narrative"]))

    def test_j8_2_missing_geometry_and_bag_give_no_distances(self):
        for shot in ("tee",):
            with self.subTest(row=shot):
                response = self.client.post("/api/v2/caddie/decision",json={"shotType":shot,
                    "includeExplanation":False,"context":{"hole":1,"par":4,
                    "geometry":{"hasMeshes":False,"hasHazards":False,"coverage":"missing"}}})
                self.assertEqual(response.status_code,200,response.text)
                result=response.json()
                self.assertIsNone(result["selected"])
                self.assertEqual(result["options"],[])
                self.assertTrue(result["missingData"])
                distance_keys={"distanceToPin_m","frontM","middleM","backM","slopeAdjustmentM"}
                self.assertEqual([(p,v) for p,k,v in walk(result) if k in distance_keys and v is not None],[])

    @unittest.expectedFailure
    def test_j8_2_nontee_without_distance_does_not_invent_targets(self):
        violations=[]
        for shot in ("approach","recovery"):
            with self.subTest(row=shot):
                response=self.client.post("/api/v2/caddie/decision",json={"shotType":shot,
                    "includeExplanation":False,"context":{"hole":1,"par":4,
                    "geometry":{"coverage":"missing","hasMeshes":False,"hasHazards":False}}})
                self.assertEqual(response.status_code,200,response.text)
                selected=response.json()["selected"]
                if selected is not None:
                    violations.append((shot,selected.get("carry_m"),selected.get("clubRecommendation")))
        self.assertEqual(violations,[],"No factual distance/bag means no numeric target recommendation")

    @unittest.expectedFailure
    def test_j8_2_caddie_recursively_omits_success_percentages(self):
        violations=[]
        for row in vectors("caddie_golden.json")["cases"]:
            with self.subTest(row=row["id"]):
                response=self.client.post("/api/v2/caddie/decision",json={"shotType":"tee",
                    "context":golden_context(row),"includeExplanation":False})
                self.assertEqual(response.status_code,200,response.text)
                for path,key,value in walk(response.json()):
                    normalized=re.sub(r"[^a-z]","",key.lower())
                    if ("success" in normalized and any(w in normalized for w in ("rate","pct","percent","probability"))) \
                            or (isinstance(value,str) and re.search(r"(?i)(success|成功率).*\d\s*[%％]",value)):
                        violations.append(row["id"]+path)
        self.assertEqual(violations,[],"Success percentages must be absent even inside nested club performance models")

    def test_j8_3_legacy_and_current_corrections_merge_stably(self):
        # Same shot: 3W -> 9I (legacy) -> PW (alias file) -> 6I (current).
        # File order deliberately disagrees with audit order. Expected before/after is
        # written here, not obtained from replay or from the correction-log builder.
        rawshot={"id":7,"scorecardId":"legacy","roundId":"legacy","hole":1,"order":1,
                 "clubName":"3W","type":"TEE","start":{"lat":0,"lon":0,"lie":"teebox"},
                 "end":{"lat":0.001,"lon":0,"lie":"fairway"},"meters":111.3}
        row={"id":"legacy","ids":["legacy","member"],"date":"2026-01-02","course":"Example",
             "holesCompleted":1,"holes":[{"number":1,"par":4,"strokes":4,"putts":2}],"strokes":4,"par":4}
        self.data=lambda: HistoryData(raw_rounds=[row],rounds=[row],shots=[rawshot])
        directory=self.root/"data/players/me/corrections"; directory.mkdir(parents=True)
        def record(seq,before,after,id=None):
            event={"op":"editField","shotId":"s:legacy:7","field":"club","value":after,
                   "ts":"2026-01-02T08:00:00Z","auditSeq":seq,
                   "audit":{"status":"ok","entries":[{"op":"club","before":before,"after":after,"hole":1}]}}
            if id:
                event.update({"eventId":id,"recordType":"correction"})
            return event
        preaudit={"op":"editField","shotId":"s:legacy:7","field":"lie","value":"rough",
                  "ts":"2026-01-01T08:00:00Z"}
        old=record(1,"3W","9I")
        current=record(3,"PW","6I","new-3")
        member=record(2,"9I","PW","alias-2")
        legacy_bytes=(json.dumps(preaudit,separators=(",",":"))+"\n"+json.dumps(old,separators=(",",":"))+"\n").encode()
        (directory/"legacy.jsonl").write_bytes(legacy_bytes)
        digest=hashlib.sha256(b"legacy").hexdigest()[:16]
        (directory/f"legacy--{digest}.jsonl").write_text(json.dumps(current)+"\n")
        (directory/"member.jsonl").write_text(json.dumps(member)+"\n")
        before=self.disk()
        # Byte-level golden: SHA256(filename + LF + ASCII line number + LF + compact UTF-8 row),
        # independently evaluated with hashlib; no product id/loader supplies this value.
        expected_id="legacy:f0855a7a4e28ca8c"
        expected_preaudit_id="legacy:6643cff1e0f343c6"
        for ref in ("legacy","member","legacy"):
            with self.subTest(row=ref):
                response=self.client.get(f"/api/v2/history/rounds/{ref}/correction-log")
                self.assertEqual(response.status_code,200,response.text)
                entries=response.json()["entries"]
                self.assertEqual([(e["auditSeq"],e["before"],e["after"]) for e in entries],
                                 [(1,"3W","9I"),(2,"9I","PW"),(3,"PW","6I")])
                self.assertEqual([e["sourceRef"] for e in entries],[expected_id,"alias-2","new-3"])
                events=round_corrections.load_round_events("me",["legacy","member"])
                self.assertEqual([e["eventId"] for e in events],
                                 [expected_preaudit_id,expected_id,"alias-2","new-3"])
                result=round_corrections.apply_corrections([rawshot],events,hole=1)
                self.assertEqual([s["clubName"] for s in result],["6I"])
                self.assertEqual(result[0]["start"]["lie"],"rough")
                self.assertEqual(self.disk(),before) # A read never rewrites old facts or invents migrations.
