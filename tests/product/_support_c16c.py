"""C16c HTTP fixtures. No old test helpers or old expected values."""
from contextlib import ExitStack
import copy
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from fastapi.testclient import TestClient
from ai_caddie.history import history
from server_v2 import annotations, caddie, history_round_detail, main, mobile

SHARED = Path(__file__).parent / "fixtures" / "shared"
STAMP = "2026-01-02T08:00:00Z"
META = {"courseName": "Example Links", "courseGlobalId": 81001,
        "holePars": "444444444444444444", "teeTime": STAMP}


def vectors(name):
    return json.loads((SHARED / name).read_text())


def event(kind, payload, *, hole=1, id=None, round_id="example", client=None):
    row = {"schema": "ai-caddie-live-round-event-v1", "eventId": id or kind,
           "roundId": round_id, "timestamp": STAMP, "hole": hole,
           "kind": kind, "payload": payload}
    if client:
        row["clientId"] = client
    return row


def score_events(strokes=5, putts=2, penalties=1, *, source="manual_edit", hole=1):
    return [event(k, {field: value, "source": source}, hole=hole, id=f"h{hole}-{k}")
            for k, field, value in [("score", "strokes", strokes), ("putt", "putts", putts),
                                    ("penalty", "penalties", penalties)]]


def golden_context(row):
    context = {k: copy.deepcopy(row[k]) for k in
               ("hole", "par", "shotType", "distanceToPin_m", "clubProfiles")}
    context.update({"source": "fixture", "sourceRef": f"course:81001:hole:{row['hole']}",
                    "routeEvidence": {"startLocal": row["ballLocal"], "targetLocal": row["pinLocal"]}})
    context["candidateRoutes"] = [
        {"id": route_id, "club": row["openingClubs"][strategy],
         "carry_m": row["clubProfiles"][row["openingClubs"][strategy]]["median_m"],
         "landingLocal": [a + (b-a) * row["clubProfiles"][row["openingClubs"][strategy]]["median_m"] / row["distanceToPin_m"]
                          for a, b in zip(row["ballLocal"], row["pinLocal"])], "riskScore": risk, "sourceRefs": [context["sourceRef"]]}
        for strategy, route_id, risk in [
            ("safe", "conservative_layup", 0),
            ("stock", "stock_line", 1),
            ("attack", "aggressive_line", 2)]]
    return context


class HTTPFixture:
    """Real app/router/storage, with isolated roots and no background/network work."""
    def setUp(self):
        super().setUp()
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.root = Path(self.stack.enter_context(TemporaryDirectory()))
        self.stack.enter_context(patch.dict(os.environ, {"AI_CADDIE_DATA_MODE": "fixture",
            "AI_CADDIE_ADMIN_TOKEN": "", "AI_CADDIE_SECURITY_PROFILE": ""}))
        for module, attribute in [(history, "ROOT"), (main, "ROOT"), (mobile, "MOBILE_ROOT"),
                (mobile, "ANNOTATION_ROOT"), (annotations, "ANNOTATION_ROOT"),
                (history_round_detail, "ANNOTATION_ROOT"), (caddie, "DECISION_LEDGER_ROOT")]:
            self.stack.enter_context(patch.object(module, attribute, self.root))
        for module in (main, mobile, annotations, history_round_detail):
            self.stack.enter_context(patch.object(module, "load_history_data_for_mode",
                side_effect=lambda *a, **kw: (self.data(), "fixture")))
        self.stack.enter_context(patch.object(main, "_prepare_recent_bg"))
        self.stack.enter_context(patch.object(mobile, "warm_stats_cache_in_background"))
        # A surprise network request fails here instead of contacting Garmin or a model.
        self.stack.enter_context(patch("socket.socket.connect", side_effect=AssertionError("unexpected network")))
        self.client = TestClient(main.app)
        self.addCleanup(self.client.close)

    def data(self):
        return history.load_history_data("me")

    def ingest(self, events=None, *, key="round", meta=None):
        return self.client.post("/api/v2/players/me/rounds", json={
            "events": events if events is not None else score_events(), "meta": meta or META},
            headers={"Idempotency-Key": key})

    def card(self, rid):
        return json.loads((self.root / f"data/players/me/scorecards/{rid}.json").read_text())

    def holes(self, rid):
        return self.card(rid)["scorecardDetails"][0]["scorecard"]["holes"]

    def disk(self):
        return {str(p.relative_to(self.root)): p.read_bytes() for p in self.root.rglob("*")
                if p.is_file() and (p.suffix in (".json", ".jsonl") or p.name == "audit_seq")}
