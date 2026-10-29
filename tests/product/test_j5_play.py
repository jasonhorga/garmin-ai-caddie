"""J5 backend play promises; all expected scores and routes are hand calculations."""
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import time
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from server_v2.main import app
from ai_caddie.caddie.mobile_event_store import FileEventStore
from tests.event_log_io import count_log_reads

from ai_caddie.caddie.decision import build_decision_plan
from ai_caddie.caddie import mobile_live
from ai_caddie.courses.tee_result import classify_tee_result
from ai_caddie.geometry import geometry_evidence
from ai_caddie.rounds import swing_candidates
from tests.product._support_c16c import HTTPFixture, META, event, golden_context, score_events, vectors


ROUND_A = "11111111-1111-4111-8111-111111111111"
ROUND_B = "22222222-2222-4222-8222-222222222222"


class PlayTests(HTTPFixture, unittest.TestCase):
    def test_j5_7_legal_writes(self):
        # 5 = 2 putts + 1 penalty + 2 other strokes; boundary 4 = 2+1+1.
        admitted = []
        for name, strokes, source in [("new", 5, "manual_edit"), ("legacy", 4, "old-client"),
                                       ("http", 4, "manual_edit")]:
            with self.subTest(row=name):
                response = self.ingest(score_events(strokes=strokes, source=source), key=name)
                self.assertEqual(response.status_code, 201, response.text)
                admitted.append(response.json()["id"])
                hole = self.holes(response.json()["id"])[0]
                self.assertEqual((hole["strokes"], hole["putts"], hole["penalties"]), (strokes, 2, 1))

        # Legal correction entrances also remain usable; the immutable source card stays intact.
        if not admitted:
            return  # Admission assertions already failed; avoid a secondary fixture error.
        rid=admitted[-1]
        raw=self.card(rid)
        annotation=self.client.post("/api/v2/annotations",json={"targetType":"hole","targetId":f"{rid}:1",
            "kind":"putt_correction","payload":{"to":1}})
        self.assertEqual(annotation.status_code,200,annotation.text)
        self.assertEqual(annotation.json()["annotation"]["payload"]["to"],1)
        correction=self.client.post(f"/api/v2/history/rounds/{rid}/corrections",
            json={"op":"setHolePenalty","hole":1,"value":2})
        self.assertEqual(correction.status_code,201,correction.text)
        self.assertEqual(correction.json()["stored"]["value"],2)
        self.assertEqual(self.card(rid),raw)

    def test_j5_7_impossible_writes_are_atomic(self):
        """Every entry must reject 3 < 2+1+1, preserving existing files."""
        rid = self.ingest(key="historical").json()["id"]
        violations = []
        for name in ["new", "legacy", "http", "live-events", "finish-replay", "annotation-putts", "annotation-total", "annotation-penalty", "correction-penalty", "correction-replay"]:
            with self.subTest(row=name):
                before = self.disk()
                if name == "live-events":
                    url = "/api/v2/mobile/rounds/impossible/events"
                    response = self.client.post(url, json={"roundId": "impossible", "events": [
                        {**e, "roundId": "impossible"} for e in score_events(strokes=3)]},
                        headers={"Idempotency-Key": "impossible"})
                elif name == "finish-replay":
                    legacy = [{**e,"roundId":"old-queue"} for e in score_events(strokes=3)]
                    # Old on-disk queue is input, bypassing today's HTTP admission path.
                    mobile_live.append_event_batch("old-queue",legacy,idempotency_key="old-queue",root=self.root)
                    before=self.disk()
                    response=self.client.post("/api/v2/mobile/rounds/old-queue/finish",json={"meta":META})
                elif name.startswith("annotation-"):
                    kind,payload={"annotation-putts":("putt_correction",{"to":5}),
                                  "annotation-total":("score_correction",{"to":3}),
                                  "annotation-penalty":("penalty_correction",{"strokes":4})}[name]
                    response = self.client.post("/api/v2/annotations", json={"targetType": "hole",
                        "targetId": f"{rid}:1", "kind":kind,"payload":payload})
                elif name in ("correction-penalty","correction-replay"):
                    response = self.client.post(f"/api/v2/history/rounds/{rid}/corrections",
                        json={"op":"setHolePenalty","hole":1,"value":4,"clientMutationId":"invalid-correction"})
                else:
                    response = self.ingest(score_events(strokes=3,
                        source="old-client" if name == "legacy" else "manual_edit"), key=f"bad-{name}")
                if response.status_code not in (400, 422) or self.disk() != before:
                    violations.append((name, response.status_code, self.disk() != before))
        self.assertEqual(violations, [], "Illegal totals must reject before any persisted write")

    def test_j5_8_tee_result_shared_golden(self):
        for row in vectors("tee_result.json")["cases"]:
            with self.subTest(row=row["id"]):
                self.assertEqual(classify_tee_result(row["point"], row["fairwayOutline"], row["route"], row["par"]),
                                 row["expected"], row["handCalculation"])

    def test_j5_8_manual_round_uses_second_position(self):
        """No fairway value is supplied: the server must derive the hand-written side."""
        failures = []
        # Four GPS scenarios: fairway, west rough, east rough, west first putt.
        selected = [r for r in vectors("tee_result.json")["cases"] if r["id"] in ("middle","left","right")]
        selected.append({**selected[1], "id":"left_first_putt", "putter":True})
        # Known surface polygons in the local metre frame (111319.49 m/degree at
        # the equator). These are independent geometry inputs, not classified answers.
        hazards = {"refLat":0,"refLon":0,"hazards":[]}
        surfaces = {"surfaces":[
            {"kind":"fairway","polygon":[[-11.131949,0],[11.131949,0],[11.131949,333.95847],[-11.131949,333.95847]]},
            {"kind":"rough","polygon":[[-100,0],[-11.131949,0],[-11.131949,334],[-100,334]]},
            {"kind":"rough","polygon":[[11.131949,0],[100,0],[100,334],[11.131949,334]]}]}
        for row in selected:
            with self.subTest(row=row["id"]):
                ev = [event("club", {"clubName":"3W"}, id="club1"),
                      event("location", {"latitude":0,"longitude":0}, id="loc1"),
                      event("club", {"clubName":"Putter" if row.get("putter") else "9I"}, id="club2"),
                      event("location", dict(zip(("latitude","longitude"),row["point"])), id="loc2"),
                      *score_events(penalties=0)]
                with patch.object(geometry_evidence,"_load_hole_sources",return_value=(hazards,surfaces)), \
                     patch("ai_caddie.courses.course_prep.tee_result_geometry",return_value={
                         "fairwayOutline":row["fairwayOutline"],"routeLatLon":row["route"]}):
                    response=self.ingest(ev,key=row["id"])
                self.assertEqual(response.status_code,201,response.text)
                actual=self.holes(response.json()["id"])[0].get("fairway")
                if actual != row["expected"]:
                    failures.append((row["id"],actual,row["expected"]))
        self.assertEqual(failures, [], "Manual scorecards must retain left/right/unknown, never blanket miss")

    def test_j5_9_event_retry_order_and_materialization(self):
        # h2 arrives before h1; each is 5 strokes, 2 putts, 1 penalty. Total = 10.
        for name, source, expected_source in [("entered", "manual_edit", "manual_edit"),
                ("default", "default", "default"), ("watch", "watch_detected", "watch_detected"),
                ("phone", "phone_shots", "phone_shots"), ("legacy", "old-client", "manual_edit")]:
            with self.subTest(row=name):
                round_id = "round-" + name
                events = [*score_events(source=source, hole=2), *score_events(source=source, hole=1)]
                events = [{**e, "roundId": round_id} for e in events]
                url = f"/api/v2/mobile/rounds/{round_id}"
                for batch, expected in [(events, 6), (events, 0), (list(reversed(events)), 0)]:
                    result = self.client.post(url+"/events", json={"roundId": round_id, "events": batch},
                        headers={"Idempotency-Key": name+str(expected)+str(batch[0]["hole"])})
                    self.assertEqual(result.status_code, 200, result.text)
                    self.assertEqual(result.json()["accepted"], expected)
                replay=self.client.get(url+"/events/replay").json()
                self.assertEqual([r["event"]["eventId"] for r in replay["events"]],
                                 ["h2-score","h2-putt","h2-penalty","h1-score","h1-putt","h1-penalty"])
                finish = self.client.post(url+"/finish", json={"meta": META})
                self.assertEqual(finish.status_code, 201, finish.text)
                rid = finish.json()["id"]
                self.assertEqual((finish.json()["strokes"], finish.json()["holesCompleted"]), (10, 2))
                holes = self.holes(rid)
                self.assertEqual([(h["number"],h["strokes"],h["putts"],h["penalties"],h["scoreSource"])
                    for h in holes], [(1,5,2,1,expected_source),(2,5,2,1,expected_source)])
                before = self.card(rid)
                retry = self.client.post(url+"/finish", json={"meta": META})
                self.assertEqual(retry.json()["id"], rid)
                self.assertTrue(retry.json()["idempotent"])
                self.assertEqual(self.card(rid), before)
                self.assertTrue((self.root/f"data/players/me/shots/{rid}.json").exists())

    def test_j5_15_candidate_retry_never_changes_scores(self):
        rid = self.ingest().json()["id"]
        before = self.disk()
        def candidate(id):
            return {"id": id, "capturedAt": "2026-01-02T08:00:00Z", "hole": 1,
                    "features": {"kind": "fullSwing", "stillnessBeforeS": 2,
                    "swingDurationS": 1, "cumulativeRotationRad": 4, "peakRotationRadS": 12}}
        url = f"/api/v2/mobile/rounds/{rid}/swing-candidates"
        first, late = candidate("first"), candidate("late")
        for name, batch, count in [("initial", [first], 1), ("retry", [first], 1),
                                   ("late", [late], 2), ("reordered", [late, first], 2)]:
            with self.subTest(row=name):
                response = self.client.post(url, json={"candidates": batch})
                self.assertEqual(response.status_code, 201, response.text)
                self.assertEqual(response.json()["stored"], count)
                self.assertEqual([c["id"] for c in swing_candidates.load_candidates("me", str(rid))],
                                 ["first"] if count == 1 else ["first", "late"])
                self.assertEqual({k:v for k,v in self.disk().items() if "/swing-candidates/" not in k}, before)
        # A failed replace must keep both the previous file and the client's retry body usable.
        saved = copy.deepcopy(first); saved["id"] = "after-failure"
        with patch.object(swing_candidates.os, "replace", side_effect=OSError("fixture disk failure")):
            with self.assertRaises(OSError):
                self.client.post(url, json={"candidates": [saved]})
        self.assertEqual([c["id"] for c in swing_candidates.load_candidates("me", str(rid))], ["first", "late"])
        self.assertEqual(self.client.post(url, json={"candidates": [saved]}).json()["stored"], 3)
        self.assertEqual(self.client.post(url, json={"candidates": [saved]}).json()["stored"], 3)
        self.assertEqual({k:v for k,v in self.disk().items() if "/swing-candidates/" not in k}, before)


class DecisionGoldenTests(unittest.TestCase):
    def test_j5_11_decisions_equal_hand_routes(self):
        for row in vectors("caddie_golden.json")["cases"]:
            with self.subTest(row=row["id"]):
                plan = build_decision_plan(golden_context(row))
                sequences = {s["id"]: s for s in plan["sequences"]}
                self.assertEqual(set(sequences), {"safe", "stock", "attack"})
                for expected in row["expected"]:
                    steps = sequences[expected["id"]]["clubs"]
                    self.assertEqual([s["clubName"] for s in steps], expected["clubNames"])
                    self.assertEqual([s["routeOffset_m"] for s in steps], expected["routeOffsets_m"])
                    self.assertEqual([s["planIndex"] for s in steps], expected["planIndices"])
                    self.assertEqual(len(steps),expected["plannedStrokes"],row["handCalculation"])
                    if "greenDistances" in row:
                        self.assertEqual(sequences[expected["id"]]["shotsToGreen"],expected["plannedStrokes"])
                options = {o["id"]:o for o in plan["options"]}
                for expected in row["expected"]:
                    self.assertEqual(options[expected["id"]]["targetLocal"], expected["landingsLocal"][0])
                    if "nextShotExpectedStrokes" in expected:
                        self.assertEqual(options[expected["id"]]["scoreImpact"]["expectedStrokes"],
                                         expected["nextShotExpectedStrokes"],row["handCalculation"])
                self.assertEqual(len({tuple(s["clubNames"]) for s in row["expected"]}), 3)
                columns=("id","kind","carryToFront_m","carryToClear_m")
                expected_zones=row.get("expectedAvoidZones",[])
                for advice in [plan,*options.values()]:
                    self.assertEqual([{k:z[k] for k in columns} for z in advice["avoidZones"]],expected_zones)
                # Every hazard identity anywhere in advice must be a supplied physical fact.
                def hazard_ids(value):
                    if isinstance(value,dict):
                        if value.get("kind") in {"water","bunker","ob","out_of_bounds","tree_area"}:
                            yield value.get("id") or value.get("hazardId")
                        for k,v in value.items():
                            if k in {"hazardId","criticalHazardId"} and v:
                                yield v
                            yield from hazard_ids(v)
                    elif isinstance(value,list):
                        for v in value:
                            yield from hazard_ids(v)
                self.assertEqual(set(hazard_ids(plan)),{z["id"] for z in expected_zones})
                self.assertTrue(plan["evidence"])
                # Every club/route reference must be an input fact, never a made-up hazard.
                allowed = {golden_context(row)["sourceRef"],*[ref for z in row.get("hazards",[]) for ref in z.get("sourceRefs",[])]}
                def refs(value):
                    if isinstance(value, dict):
                        for k,v in value.items():
                            if k in ("sourceRefs", "evidenceRefs") and isinstance(v,list):
                                yield from (r for r in v if isinstance(r,str))
                            else:
                                yield from refs(v)
                    elif isinstance(value,list):
                        for v in value:
                            yield from refs(v)
                self.assertLessEqual(set(refs(plan)), allowed)
                self.assertLessEqual({ref for z in row.get("hazards",[]) for ref in z.get("sourceRefs",[])},
                                     set(refs(plan)),"Known hazards must retain a resolvable evidence reference")
        # No measured bag/geometry means an explicit missing-data result, no invented club chain.
        missing = build_decision_plan({"par":4, "hole":1, "geometry":{}})
        self.assertEqual(missing["sequences"], [])
        self.assertIsNone(missing["selected"])
        self.assertTrue(missing["missingData"])


class EventAppendTests(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    @staticmethod
    def _event(event_id):
        return {"eventId": event_id, "clientId": "ios", "roundId": ROUND_A,
                "kind": "score", "payload": {"strokes": 4}}

    def test_j59_append_reads_only_target_round_on_seven_mb_history(self) -> None:
        """J5.9 durable append/ACK and J4.2 responsiveness: unrelated history is not replayed."""
        from ai_caddie.core.request_timing import RequestTiming, bind
        from ai_caddie.rounds.score_invariant import require_possible_appended_scores

        log = self.root / "events.jsonl"
        unrelated = {"roundId": ROUND_B, "event": {
            "hole": 1, "kind": "note", "payload": {"text": "x" * 2600},
        }}
        log.write_bytes((json.dumps(unrelated, sort_keys=True) + "\n").encode() * 2600)
        self.assertGreaterEqual(log.stat().st_size, 7_000_000)
        FileEventStore(self.root).append_batch(
            ROUND_A, [{**self._event("seed"), "hole": 1}], request_key="seed",
            validate_append=require_possible_appended_scores,
        )
        before = log.read_bytes()
        timing = RequestTiming("append-probe")
        started = time.perf_counter()
        with count_log_reads(log) as reads, bind(timing):
            result = FileEventStore(self.root).append_batch(
                ROUND_A, [{**self._event("next"), "hole": 2}], request_key="next",
                validate_append=require_possible_appended_scores,
            )
        elapsed = time.perf_counter() - started
        print(f"APPEND_PROBE bytes={len(before)} sha256={hashlib.sha256(before).hexdigest()} "
              f"elapsed_ms={elapsed * 1000:.3f} read_bytes={reads['bytes']} stages={timing.marks}")
        self.assertEqual(result[0].status, "accepted")
        # One small existing target row plus the new tail, with 4KiB slack for boundary checks.
        self.assertLess(reads["bytes"], 8192)
        # Read bytes above are the regression guard against replaying unrelated history.
        # Timing only catches extreme degradation and follows the user's <1s standard;
        # rewriting/fsyncing the index can exceed 200ms under concurrent host load.
        self.assertLess(elapsed, 1.0)

    def test_j59_warm_append_refuses_same_size_prefix_edit_even_with_restored_mtime(self) -> None:
        """J5.9: a previously acknowledged event cannot silently change before the next ACK."""
        log = self.root / "events.jsonl"
        FileEventStore(self.root).append_batch(
            ROUND_A, [{**self._event("original"), "hole": 3}], request_key="original",
        )
        original_stat = log.stat()
        raw = log.read_bytes()
        log.write_bytes(raw.replace(b'"hole": 3', b'"hole": 9'))
        os.utime(log, ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns))
        with self.assertRaisesRegex(ValueError, "^event_commit_store_corrupt$"):
            FileEventStore(self.root).append_batch(ROUND_A, [self._event("new")], request_key="new")
        self.assertNotIn("new", (self.root / "request_reservations.json").read_text())

    def test_j59_stale_index_repairs_before_dedup_and_score_validation(self):
        """J5.9/J5.7: index damage cannot lose an ACK, duplicate a score, or admit 3 < 2+1+1."""
        from ai_caddie.rounds.score_invariant import require_possible_appended_scores, ScoreInvariantError

        first = {**self._event("score"), "hole": 1}
        store = FileEventStore(self.root)
        store.append_batch(ROUND_A, [
            first,
            {**self._event("putts"), "hole": 1, "kind": "putt", "payload": {"putts": 2}},
            {**self._event("penalty"), "hole": 1, "kind": "penalty", "payload": {"penalties": 1}},
        ], request_key="first")
        store.append_batch(ROUND_B, [{**first, "roundId": ROUND_B, "eventId": "other"}], request_key="other")
        payload = json.loads(store.round_index.read_text())
        payload["offsets"][ROUND_A] = []
        store.round_index.write_text(json.dumps(payload))
        duplicate = FileEventStore(self.root).append_batch(
            ROUND_A, [first], request_key="retry", validate_append=require_possible_appended_scores,
        )
        self.assertEqual((duplicate[0].status, duplicate[0].position, duplicate.server_sequence),
                         ("duplicate_hash_match", 1, 4))
        before_log, before_reservations = store.log.read_bytes(), store.reservations.read_bytes()
        store.round_index.unlink()
        with self.assertRaises(ScoreInvariantError):
            FileEventStore(self.root).append_batch(ROUND_A, [
                {**self._event("too-low"), "hole": 1, "payload": {"strokes": 3}},
            ], request_key="impossible", validate_append=require_possible_appended_scores)
        self.assertEqual(store.log.read_bytes(), before_log)
        self.assertEqual(store.reservations.read_bytes(), before_reservations)
        self.assertEqual(store.round_event_holes(ROUND_A), [1, 1, 1])

    def test_j59_external_process_append_refreshes_prefix_and_global_positions(self):
        """J5.9: another process can commit between requests without stale dedupe or sequence state."""
        store = FileEventStore(self.root)
        first = {**self._event("one"), "hole": 1}
        store.append_batch(ROUND_A, [first], request_key="one")
        script = """
import json, sys
from ai_caddie.caddie.mobile_event_store import FileEventStore
FileEventStore(sys.argv[1]).append_batch(sys.argv[2], [json.loads(sys.argv[3])], request_key="external")
"""
        second = {**self._event("two"), "hole": 2}
        subprocess.run([sys.executable, "-c", script, str(self.root), ROUND_A, json.dumps(second)],
                       cwd=Path(__file__).resolve().parents[2], check=True, timeout=30)
        result = FileEventStore(self.root).append_batch(
            ROUND_A, [second, {**self._event("three"), "hole": 3}], request_key="three",
        )
        self.assertEqual([(r.status, r.position) for r in result],
                         [("duplicate_hash_match", 2), ("accepted", 3)])
        self.assertEqual(store.round_event_holes(ROUND_A), [1, 2, 3])

    def test_j59_unavailable_auxiliary_index_still_allows_durable_ack(self):
        """J5.9: sidecar repair failure cannot lose or duplicate a committed event."""
        store = FileEventStore(self.root)
        first = self._event("one")
        with self.assertLogs("ai_caddie.caddie.mobile_event_store", level="WARNING"), patch.object(
            FileEventStore, "_write_round_index_unlocked", side_effect=OSError("fixture-sidecar-unavailable"),
        ):
            result = store.append_batch(ROUND_A, [first], request_key="first")
            retry = FileEventStore(self.root).append_batch(ROUND_A, [first], request_key="retry")
        self.assertEqual((result[0].status, retry[0].status), ("accepted", "duplicate_hash_match"))
        self.assertEqual(len(store.read_rows()), 1)
        self.assertTrue(store.ensure_round_event_index())

    def test_j59_event_append_persists_request_and_storage_stage_timings(self) -> None:
        """J5.9: the durable event ACK is observable without recording the event body."""
        from ai_caddie.core import request_timing

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            with (
                patch("server_v2.mobile.MOBILE_ROOT", root),
                patch.object(request_timing, "TIMING_ROOT", root / "private"),
            ):
                response = TestClient(app).post(
                    "/api/v2/mobile/rounds/timing-round/events",
                    headers={"Idempotency-Key": "timing-request", "X-AI-Caddie-Request-ID": "append-timing-test"},
                    json={"roundId": "timing-round", "events": [{
                        "schema": "ai-caddie-live-round-event-v1",
                        "eventId": "private-event-body", "roundId": "timing-round",
                        "timestamp": "2026-05-25T00:00:00Z", "hole": 1,
                        "kind": "score", "payload": {"strokes": 4},
                    }]},
                )
                request_timing.flush_timing_writes()
            self.assertEqual(response.status_code, 200, response.text)
            rows = [json.loads(line) for path in (root / "private/timing").glob("*.jsonl")
                    for line in path.read_text().splitlines()]
            row = next(row for row in rows if row["request_id"] == "append-timing-test")
            self.assertEqual((row["method"], row["path"], row["status"]),
                             ("POST", "/api/v2/mobile/rounds/{id}/events", 200))
            self.assertTrue(all("timing-round" not in json.dumps(item) for item in rows))
            for stage in ("event_materialization_lock_wait", "event_lock_wait", "event_validate",
                          "event_parse", "event_write", "event_index"):
                self.assertIn(stage, response.headers["server-timing"])
                self.assertIn(stage, row["stages"])
            self.assertNotIn("private-event-body", json.dumps(rows))
            self.assertNotIn("timing-request", json.dumps(rows))
