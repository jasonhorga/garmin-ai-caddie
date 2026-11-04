"""J8: missing evidence and old/new persisted corrections remain honest."""
import asyncio
import hashlib
import json
import logging
import os
import re
import socket
import threading
import time
import unittest
from unittest.mock import patch

import uvicorn
from fastapi.testclient import TestClient

from ai_caddie.history.history import HistoryData
from ai_caddie.history.history_stats import build_history_stats
from ai_caddie.reports.reports import generate_deterministic_report
from ai_caddie.rounds import round_corrections
from tests.product._support_c16c import HTTPFixture, golden_context, vectors
from server_v2 import main


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
        stable_ids = stable_log_ids = None
        for ref in ("legacy","member","legacy"):
            with self.subTest(row=ref):
                response=self.client.get(f"/api/v2/history/rounds/{ref}/correction-log")
                self.assertEqual(response.status_code,200,response.text)
                entries=response.json()["entries"]
                self.assertEqual([(e["auditSeq"],e["before"],e["after"]) for e in entries],
                                 [(1,"3W","9I"),(2,"9I","PW"),(3,"PW","6I")])
                events=round_corrections.load_round_events("me",["legacy","member"])
                # Semantic order/counts are independent golden; generated legacy identifiers
                # are opaque. Their spelling may change, but reads/aliases must keep them stable.
                self.assertEqual([(e["field"],e["value"]) for e in events],
                                 [("lie","rough"),("club","9I"),("club","PW"),("club","6I")])
                ids = [e["eventId"] for e in events]
                log_ids = [e["sourceRef"] for e in entries]
                self.assertEqual(len(set(ids)),4)
                self.assertTrue(all(isinstance(id,str) and id for id in ids))
                self.assertEqual(ids[2:],["alias-2","new-3"])
                self.assertEqual(log_ids,ids[1:])
                if stable_ids is None:
                    stable_ids,stable_log_ids = ids,log_ids
                self.assertEqual(ids,stable_ids)
                self.assertEqual(log_ids,stable_log_ids)
                result=round_corrections.apply_corrections([rawshot],events,hole=1)
                self.assertEqual([s["clubName"] for s in result],["6I"])
                self.assertEqual(result[0]["start"]["lie"],"rough")
                self.assertEqual(self.disk(),before) # A read never rewrites old facts or invents migrations.

class J8DisconnectTests(unittest.TestCase):
    """J8.5: a client abandoning its request is observable as 499, not as malformed input."""

    ENV = {"AI_CADDIE_BOOT_BACKGROUND_WORK": "0", "AI_CADDIE_SECURITY_PROFILE": "", "AI_CADDIE_ADMIN_TOKEN": ""}

    def setUp(self):
        # uvicorn.Config(access_log=False) clears uvicorn.access handlers and turns off its
        # propagation; restore it so later modules in the same process see main's state.
        access = logging.getLogger("uvicorn.access")
        state = (access.handlers[:], access.propagate)

        def restore():
            access.handlers[:], access.propagate = state
        self.addCleanup(restore)

    def _disconnect(self, request: bytes, *, delay_before_app: float = 0.0) -> list[str]:
        """Send raw bytes to a real uvicorn, close the socket, return timing + server log lines."""
        class DelayedApp:
            # Stands in for whatever holds the app before it reads the body (event loop or
            # thread-pool pressure in production) while the client has already gone away.
            def __init__(self, app):
                self.app = app

            async def __call__(self, scope, receive, send):
                if delay_before_app:
                    await asyncio.sleep(delay_before_app)
                await self.app(scope, receive, send)

        with patch.dict(os.environ, self.ENV), socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            server = uvicorn.Server(uvicorn.Config(
                DelayedApp(main.app), lifespan="off", loop="asyncio", http="h11", ws="none",
                log_config=None, access_log=False, timeout_graceful_shutdown=2,
            ))
            started = threading.Event()
            original_startup = server.startup

            async def startup(*args, **kwargs):
                result = await original_startup(*args, **kwargs)
                started.set()
                return result

            server.startup = startup
            thread = threading.Thread(target=server.run, kwargs={"sockets": [listener]}, daemon=True)
            lines: list[str] = []
            capture = logging.Handler(logging.INFO)
            capture.emit = lambda record: lines.append(f"{record.name}:{record.getMessage()}")
            # request_timing has its own non-propagating service logger; the disconnect line is
            # an ordinary server_v2.main record.  Watch both, then put their levels back.
            watched = [logging.getLogger("server_v2.timing"), logging.getLogger("server_v2.main")]
            levels = [item.level for item in watched]
            for item in watched:
                item.addHandler(capture)
                item.setLevel(logging.INFO)
            thread.start()
            try:
                self.assertTrue(started.wait(5), "uvicorn did not start")
                with socket.create_connection(listener.getsockname(), timeout=2) as client:
                    client.sendall(request)
                    client.shutdown(socket.SHUT_RDWR)
                deadline = time.monotonic() + 3
                while time.monotonic() < deadline and not any("request_timing" in line for line in lines):
                    time.sleep(0.02)
            finally:
                server.should_exit = True
                thread.join(5)
                for item, level in zip(watched, levels):
                    item.removeHandler(capture)
                    item.setLevel(level)
            self.assertFalse(thread.is_alive(), "uvicorn did not shut down")
            return lines

    def _assert_disconnect_logged(self, logs: list[str], route: str) -> None:
        timing = [line for line in logs if "request_timing" in line]
        self.assertEqual(len(timing), 1, logs)
        self.assertIn(f"path={route} status=499 ", timing[0])
        self.assertIn(f"client_disconnected path={route} during=body", "\n".join(logs))
        self.assertFalse(any("status=400" in line for line in logs), logs)

    def test_j8_5_partial_client_timing_body_is_timed_as_499(self):
        # Header promises 2000 bytes; the client sends a fragment and gives up.
        body = b'[{"request_id":"partial"'
        logs = self._disconnect(
            b"POST /api/v2/mobile/client-timing HTTP/1.1\r\n"
            b"Host: fixture\r\nContent-Type: application/json\r\n"
            b"Content-Length: 2000\r\nConnection: close\r\n\r\n" + body
        )
        self._assert_disconnect_logged(logs, "/api/v2/mobile/client-timing")

    def test_j8_5_complete_decision_body_read_after_disconnect_is_timed_as_499(self):
        # Every body byte arrives, but the client is gone before the app gets to read it.
        body = json.dumps({"course_id": "fixture", "hole_number": 1}).encode()
        logs = self._disconnect(
            b"POST /api/v2/caddie/decision HTTP/1.1\r\n"
            b"Host: fixture\r\nContent-Type: application/json\r\n"
            + f"Content-Length: {len(body)}\r\n".encode()
            + b"Connection: close\r\n\r\n" + body,
            delay_before_app=0.2,
        )
        self._assert_disconnect_logged(logs, "/api/v2/caddie/decision")

    def test_j8_5_body_validation_controls_keep_existing_statuses(self):
        # No `with`: entering TestClient runs the lifespan, whose logging setup is process-global.
        client = TestClient(main.app)
        with patch.dict(os.environ, self.ENV):
            self.assertEqual(client.post("/api/v2/mobile/client-timing", json=[]).status_code, 200)
            bad_json = client.post("/api/v2/mobile/client-timing", content=b"{", headers={"Content-Type": "application/json"})
            self.assertEqual(bad_json.status_code, 422)
            self.assertEqual(client.post("/api/v2/mobile/client-timing", json={}).status_code, 422)
            missing = client.get("/api/v2/no-such-route")
            self.assertEqual((missing.status_code, missing.json()), (404, {"detail": "Not Found"}))
