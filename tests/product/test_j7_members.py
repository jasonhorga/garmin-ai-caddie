"""C16 J7 product checks for member scope and authorization.

These tests intentionally keep the player route inventory next to the assertions.  A new
``/api/v2/players/...`` route must be added to the inventory and then receive the same
owner/self/other/anonymous treatment; an accidental route cannot silently become public.
"""
from __future__ import annotations

import base64
import os
import re
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient

from ai_caddie.history import history, stats_cache
from ai_caddie.rounds import players
from ai_caddie.core import data as core_data
from server_v2 import auth_api, db, identity_repo, media, mobile, reports, history_stats, history_round_detail, annotations
from server_v2.apple_auth import AppleIdentity
from server_v2.identity_models import Base
from server_v2.main import app
from server_v2.players_api import assert_admin_security_config, is_player_scoped_route


ADMIN = "j7-owner-admin"
ADMIN_HEADER = {"X-AI-Caddie-Admin-Token": ADMIN}

# This is the complete explicit player-id surface.  It is deliberately written as a set of
# (method, route-template) pairs and checked against FastAPI's route table below.
PLAYER_ID_ROUTES = frozenset(
    {
        ("POST", "/api/v2/players/{target_player_id}/rounds"),
        ("GET", "/api/v2/players/{player_id}/clubs/bag"),
        ("PUT", "/api/v2/players/{player_id}/clubs/bag"),
        ("POST", "/api/v2/players/{player_id}/sync/garmin/session"),
        ("POST", "/api/v2/players/{player_id}/sync/garmin"),
        ("GET", "/api/v2/players/{player_id}/sync/garmin/jobs/{job_id}"),
        ("POST", "/api/v2/players/{player_id}/sync/garmin/jobs/{job_id}/cancel"),
        ("POST", "/api/v2/players/{player_id}/sync/garmin/jobs/{job_id}/retry"),
    }
)

# Player-scoped endpoints without a literal ``{player_id}`` in the URL resolve the player from
# the bearer.  Keep this second, fixed inventory so adding a new history/evidence route cannot
# accidentally bypass the scope policy.
PLAYER_SCOPED_ROUTES = frozenset(
    {
        ("GET", "/api/v2/history/overview"), ("GET", "/api/v2/history/rounds"),
        ("GET", "/api/v2/history/rounds/{round_ref}"),
        ("GET", "/api/v2/history/rounds/{round_ref}/holes/{hole}/shotmap"),
        ("GET", "/api/v2/history/rounds/{round_ref}/correction-log"),
        ("GET", "/api/v2/history/stats"), ("GET", "/api/v2/history/summary"),
        ("GET", "/api/v2/history/stats/mobile"), ("GET", "/api/v2/history/clubs/bag"),
        ("GET", "/api/v2/history/drilldown/{source_ref}"),
        ("GET", "/api/v2/reports"), ("GET", "/api/v2/reports/round/{round_id}"),
        ("GET", "/api/v2/reports/course/{course_key}"),
        ("GET", "/api/v2/reports/hole/{course_key}/{hole}"),
        ("GET", "/api/v2/reports/club/{club_name}"), ("GET", "/api/v2/reports/trend/{period}"),
        ("GET", "/api/v2/courses/{global_id}/prep"), ("GET", "/api/v2/courses/{global_id}/prep-tips"),
        ("GET", "/api/v2/courses/{global_id}/tees"), ("GET", "/api/v2/courses/search"),
        ("GET", "/api/v2/courses/nearby"), ("GET", "/api/v2/mobile/courses/options"),
        ("GET", "/api/v2/annotations"),
        ("GET", "/api/v2/annotations/target/{target_type}/{target_id}"),
        ("GET", "/api/v2/caddie/context"),
        ("GET", "/api/v2/caddie/decisions/{decision_id}/audit/latest"),
        ("GET", "/api/v2/mobile/rounds/{round_id}/package"),
        ("GET", "/api/v2/mobile/courses/{global_id}/package"),
        ("GET", "/api/v2/mobile/rounds/{round_id}/reconciliation"),
        ("GET", "/api/v2/mobile/rounds/{round_id}/events/replay"),
        ("GET", "/api/v2/mobile/rounds/{round_id}/state"),
        ("GET", "/api/v2/players/{player_id}/clubs/bag"),
        ("GET", "/api/v2/players/{player_id}/sync/garmin/jobs/{job_id}"),
        ("GET", "/api/v2/media/target/{target_type}/{target_id}"),
        ("GET", "/api/v2/media/target/{target_type}/{target_id}/findings"),
        ("GET", "/api/v2/weather/snapshot"),
        ("POST", "/api/v2/mobile/rounds/{round_id}/events"),
        ("POST", "/api/v2/mobile/rounds/{round_id}/events/ack"),
        ("POST", "/api/v2/mobile/rounds/{round_id}/finish"),
        ("POST", "/api/v2/mobile/rounds/{round_id}/swing-candidates"),
        ("POST", "/api/v2/mobile/pin-sheet"), ("POST", "/api/v2/media"),
        ("POST", "/api/v2/media/{media_id}/analyze"), ("POST", "/api/v2/media/{media_id}/redact"),
        ("POST", "/api/v2/media/findings/{finding_id}/confirmation"),
        ("POST", "/api/v2/caddie/decision"),
        ("POST", "/api/v2/caddie/decisions/{decision_id}/audit"),
        ("POST", "/api/v2/annotations"),
        ("POST", "/api/v2/history/rounds/{round_ref}/corrections"),
        ("POST", "/api/v2/history/prepare-recent"),
        ("POST", "/api/v2/reports/round/{round_id}/generate"),
        ("POST", "/api/v2/reports/course/{course_key}/generate"),
        ("POST", "/api/v2/reports/hole/{course_key}/{hole}/generate"),
        ("POST", "/api/v2/reports/club/{club_name}/generate"),
        ("POST", "/api/v2/reports/trend/{period}/generate"),
        ("POST", "/api/v2/players/{player_id}/sync/garmin/jobs/{job_id}/cancel"),
        ("POST", "/api/v2/players/{player_id}/sync/garmin/jobs/{job_id}/retry"),
    }
)


def _route_inventory() -> set[tuple[str, str]]:
    found: set[tuple[str, str]] = set()
    for route in app.routes:
        path = getattr(route, "path", "")
        if not path.startswith("/api/v2/players/"):
            continue
        for method in getattr(route, "methods", set()) or set():
            if method not in {"GET", "POST", "PUT", "PATCH", "DELETE"}:
                continue
            found.add((method, path))
    return found


def _player_scoped_inventory() -> set[tuple[str, str]]:
    found: set[tuple[str, str]] = set()
    for route in app.routes:
        path = getattr(route, "path", "")
        if not path.startswith("/api/v2/"):
            continue
        concrete = re.sub(r"\{[^}]+\}", "1", path)
        for method in getattr(route, "methods", set()) or set():
            if method in {"GET", "POST", "PUT", "PATCH", "DELETE"} and is_player_scoped_route(method, concrete):
                found.add((method, path))
    return found


def _round_body() -> dict[str, object]:
    return {
        "events": [
            {"hole": 1, "kind": "score", "payload": {"strokes": 4}},
            {"hole": 1, "kind": "putt", "payload": {"putts": 2}},
        ],
        "meta": {"courseGlobalId": 41825, "courseName": "Member test course", "holePars": "4"},
    }


def _session_body() -> dict[str, str]:
    return {
        "webSessionHeader": "Cookie: JWT_WEB=j7-test-cookie",
        "antiForgeryValue": "connect-csrf-token: j7-test-csrf",
    }


class _StaticReportProvider:
    model = "fixture"

    def chat(self, messages, max_tokens=None):
        return "只复述输入事实。"


class J7RouteInventoryTests(unittest.TestCase):
    def test_j7_1_route_table_has_exactly_the_declared_player_id_surface(self) -> None:
        self.assertEqual(_route_inventory(), set(PLAYER_ID_ROUTES))

    def test_j7_1_route_table_has_exactly_the_declared_bearer_scoped_surface(self) -> None:
        self.assertEqual(_player_scoped_inventory(), set(PLAYER_SCOPED_ROUTES))


class J7MemberIsolationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        patches = [
            mock.patch.object(players, "ROOT", self.root),
            mock.patch.object(history, "ROOT", self.root),
            mock.patch.object(media, "MEDIA_ROOT", self.root),
            mock.patch.object(mobile, "MOBILE_ROOT", self.root),
            mock.patch.object(reports, "REPORT_ROOT", self.root),
            mock.patch.object(history_round_detail, "ANNOTATION_ROOT", self.root),
            mock.patch.object(annotations, "ANNOTATION_ROOT", self.root),
            *[mock.patch.object(history_stats, name, self.root) for name in
              ("ANNOTATION_ROOT", "WEATHER_ROOT", "REPORTS_ROOT", "DECISION_AUDIT_ROOT")],
            mock.patch.object(stats_cache, "_PLAYERS_DIR", self.root / "data" / "players"),
            mock.patch.object(core_data, "DATA_DIR", self.root / "data"),
            mock.patch.object(core_data, "CLUBS_BAG_FILE", self.root / "data" / "club_bag.json"),
            mock.patch.dict(
                os.environ,
                {"AI_CADDIE_ADMIN_TOKEN": ADMIN, "AI_CADDIE_DATA_MODE": "local"},
            ),
            mock.patch("server_v2.main._prepare_recent_bg"),
            mock.patch("server_v2.session.SESSION_ROOT", self.root),
        ]
        for item in patches:
            item.start()
            self.addCleanup(item.stop)
        stats_cache.clear()
        self.addCleanup(stats_cache.clear)
        self.alice = players.create_player("Alice", root=self.root)
        self.bob = players.create_player("Bob", root=self.root)
        self.client = TestClient(app)

    def _auth(self, token: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {token}"}

    def test_j7_1_owner_self_other_and_anonymous_matrix_for_targeted_writes(self) -> None:
        cases = (
            (
                "round ingest",
                lambda target, headers: self.client.post(
                    f"/api/v2/players/{target}/rounds", json=_round_body(), headers=headers
                ),
                201,
            ),
            (
                "session bind",
                lambda target, headers: self.client.post(
                    f"/api/v2/players/{target}/sync/garmin/session",
                    json=_session_body(),
                    headers=headers,
                ),
                200,
            ),
        )
        for label, call, allowed in cases:
            with self.subTest(label=label, caller="owner", target="alice"):
                response = call(self.alice["id"], ADMIN_HEADER)
                self.assertEqual(response.status_code, allowed, response.text)
            with self.subTest(label=label, caller="alice", target="alice"):
                response = call(self.alice["id"], self._auth(self.alice["token"]))
                self.assertIn(response.status_code, {200, 201}, response.text)
            with self.subTest(label=label, caller="alice", target="bob"):
                response = call(self.bob["id"], self._auth(self.alice["token"]))
                self.assertEqual(response.status_code, 403, response.text)
            with self.subTest(label=label, caller="anonymous", target="alice"):
                response = call(self.alice["id"], {})
                self.assertEqual(response.status_code, 401, response.text)

    def test_j7_1_every_explicit_player_route_enforces_owner_self_other_anonymous(self) -> None:
        """Exercise every route in ``PLAYER_ID_ROUTES`` at its authorization boundary.

        The successful owner/self calls are allowed to return a normal 2xx or a resource-level
        404; a 403 would mean the route rejected a valid scope.  Other-player calls must stop
        before a handler can mutate/read the guessed id, and anonymous calls must stop at 401.
        """
        from server_v2 import main as main_api

        def fake_enqueue(*, response, **_kwargs):
            response.status_code = 202
            return {
                "schema": "ai-caddie-sync-run-v2", "connector": "garmin_cn_web_session",
                "state": "queued", "jobId": "j7-test", "statusUrl": "/api/v2/players/x/sync/garmin/jobs/j7-test",
                "createdAt": "2026-01-01T00:00:00Z", "updatedAt": "2026-01-01T00:00:00Z",
                "detail": "queued", "reauthRequired": False, "errorCode": None,
                "snapshot": None, "safeMeta": {},
            }

        def call(method: str, path: str, target: str, headers: dict[str, str]):
            url = path.replace("{target_player_id}", target).replace("{player_id}", target).replace("{job_id}", "missing")
            body = None
            if method == "PUT":
                body = {"clubs": []}
            elif path.endswith("/rounds"):
                body = _round_body()
            elif path.endswith("/sync/garmin/session"):
                body = _session_body()
            if method == "GET":
                return self.client.get(url, headers=headers)
            if method == "POST":
                return self.client.post(url, headers=headers, json=body)
            return self.client.put(url, headers=headers, json=body)

        callers = [("owner", ADMIN_HEADER, "me"),
                   ("A", self._auth(self.alice["token"]), self.alice["id"]),
                   ("B", self._auth(self.bob["token"]), self.bob["id"]),
                   ("anonymous", {}, None)]
        with mock.patch.object(main_api, "_enqueue_garmin_sync_job", side_effect=fake_enqueue):
            for method, path in sorted(PLAYER_ID_ROUTES):
                for caller, headers, caller_pid in callers:
                    for target in ("me", self.alice["id"], self.bob["id"]):
                        with self.subTest(method=method, path=path, caller=caller, target=target):
                            response = call(method, path, target, headers)
                            if caller == "anonymous":
                                self.assertEqual(response.status_code, 401)
                            elif caller != "owner" and caller_pid != target:
                                self.assertEqual(response.status_code, 403)
                            else:
                                expected = 404 if "{job_id}" in path else (201 if path.endswith("/rounds") else 202 if path.endswith("/sync/garmin") else 200)
                                self.assertEqual(response.status_code, expected, response.text)

    def test_j7_1_member_round_is_in_member_history_and_never_owner_or_other_member(self) -> None:
        own = self.client.post(
            f"/api/v2/players/{self.alice['id']}/rounds",
            json=_round_body(),
            headers=self._auth(self.alice["token"]),
        )
        self.assertEqual(own.status_code, 201, own.text)
        alice_history = self.client.get("/api/v2/history/rounds", headers=self._auth(self.alice["token"]))
        owner_history = self.client.get("/api/v2/history/rounds", headers=ADMIN_HEADER)
        bob_history = self.client.get("/api/v2/history/rounds", headers=self._auth(self.bob["token"]))
        self.assertEqual(alice_history.status_code, 200, alice_history.text)
        self.assertEqual(owner_history.status_code, 200, owner_history.text)
        self.assertEqual(bob_history.status_code, 200, bob_history.text)
        self.assertIn("Member test course", alice_history.text)
        self.assertNotIn("Member test course", owner_history.text)
        self.assertNotIn("Member test course", bob_history.text)
        anonymous = self.client.get("/api/v2/history/rounds")
        self.assertEqual(anonymous.status_code, 401, anonymous.text)

    def test_j7_1_bearer_scope_matrix(self) -> None:
        # Handwritten fixture: one par-4 hole per player; owner=6, A=4, B=5 strokes,
        # 2 putts each. One note event, one photo and one report per partition.
        # Exactly one own round/evidence item is visible; every foreign projection is empty.
        rows = [("owner", "me", ADMIN_HEADER, 6, 210),
                ("A", self.alice["id"], self._auth(self.alice["token"]), 4, 170),
                ("B", self.bob["id"], self._auth(self.bob["token"]), 5, 190)]
        seeded = {}
        for label, pid, headers, strokes, distance in rows:
            body = _round_body()
            body["events"][0]["payload"]["strokes"] = strokes
            body["meta"].update(courseName=f"Scope {label} course", courseGlobalId=991601,
                                date="2026-10-20T08:00:00Z")
            response = self.client.post(f"/api/v2/players/{pid}/rounds", headers=headers, json=body)
            self.assertEqual(response.status_code, 201, response.text)
            rid = str(response.json()["id"])
            seeded[label] = (pid, headers, rid, strokes, distance)
            event = {"schema": "ai-caddie-live-round-event-v1", "eventId": f"scope-{label}",
                     "roundId": rid, "timestamp": "2026-10-20T08:00:00Z", "hole": 1,
                     "kind": "note", "payload": {"note": f"scope-note-{label}"}}
            response = self.client.post(f"/api/v2/mobile/rounds/{rid}/events", headers={**headers, "Idempotency-Key": f"seed-{label}"},
                                        json={"roundId": rid, "events": [event]})
            self.assertEqual(response.status_code, 200, response.text)
            response = self.client.post("/api/v2/media", headers=headers, json={
                "targetType": "round", "targetId": rid, "mediaKind": "photo",
                "fileName": f"scope-{label}.png", "capturedAt": "2026-10-20T08:00:00Z",
                "contentBase64": base64.b64encode(b"\x89PNG\r\n\x1a\nfixture").decode(),
            })
            self.assertEqual(response.status_code, 200, response.text)
            response = self.client.put(f"/api/v2/players/{pid}/clubs/bag", headers=headers,
                json={"clubs": [{"token": "driver", "customName": f"scope-club-{label}", "distanceM": distance}]})
            self.assertEqual(response.status_code, 200, response.text)
            with mock.patch.object(reports, "build_text_provider", return_value=_StaticReportProvider()):
                response = self.client.post(f"/api/v2/reports/round/{rid}/generate", headers=headers)
            self.assertEqual(response.status_code, 200, response.text)

        for caller in ("owner", "A", "B", "anonymous"):
            headers = seeded[caller][1] if caller != "anonymous" else {}
            for target, (pid, _headers, rid, strokes, distance) in seeded.items():
                own = caller == target
                paths = [
                    ("detail", f"/api/v2/history/rounds/{rid}"),
                    ("shotmap", f"/api/v2/history/rounds/{rid}/holes/1/shotmap?includeImage=false"),
                    ("events", f"/api/v2/mobile/rounds/{rid}/events/replay"),
                    ("media", f"/api/v2/media/target/round/{rid}"),
                    ("bag", f"/api/v2/players/{pid}/clubs/bag"),
                    ("report", f"/api/v2/reports/round/{rid}"),
                ]
                for kind, path in paths:
                    with self.subTest(caller=caller, target=target, route=kind):
                        response = self.client.get(path, headers=headers)
                        if caller == "anonymous":
                            self.assertEqual(response.status_code, 401)
                            continue
                        if kind == "bag" and not own and caller != "owner":
                            self.assertEqual(response.status_code, 403)
                            continue
                        self.assertEqual(response.status_code, 200, response.text)
                        payload = response.json()
                        if kind == "detail":
                            self.assertEqual(payload["found"], own, response.text)
                            if own:
                                self.assertEqual(payload["round"]["score"], strokes)
                                self.assertEqual([(h["score"], h["putts"]) for h in payload["scorecard"]], [(strokes, 2)])
                            else:
                                self.assertIsNone(payload["round"])
                                self.assertEqual(payload["scorecard"], [])
                        elif kind == "shotmap":
                            self.assertEqual(payload["found"], own, response.text)
                            self.assertEqual(payload["shots"], [])
                        elif kind == "events":
                            self.assertEqual(payload["eventCount"], 1 if own else 0)
                            self.assertEqual([e["event"]["eventId"] for e in payload["events"]],
                                             [f"scope-{target}"] if own else [])
                        elif kind == "media":
                            self.assertEqual(payload["total"], 1 if own else 0)
                            if own:
                                self.assertEqual(payload["media"][0]["targetId"], rid)
                            else:
                                self.assertEqual(payload["media"], [])
                        elif kind == "bag":
                            self.assertEqual([(c["customName"], c["distanceM"]) for c in payload["clubs"]],
                                             [(f"scope-club-{target}", distance)])
                        elif kind == "report":
                            scorecards = [f["value"] for f in payload["factsUsed"] if f["label"] == "round_scorecard"]
                            if own:
                                self.assertEqual(len(scorecards), 1)
                                self.assertEqual(scorecards[0]["score"], strokes)
                            else:
                                self.assertEqual(scorecards, [])

            # Statistics and indexes have no target parameter: their id sets must contain
            # exactly the caller's one round, never owner/A/B's other rounds.
            for kind, path in [("stats", "/api/v2/history/stats"),
                               ("rounds", "/api/v2/history/rounds"),
                               ("reports", "/api/v2/reports")]:
                with self.subTest(caller=caller, route=kind):
                    response = self.client.get(path, headers=headers)
                    if caller == "anonymous":
                        self.assertEqual(response.status_code, 401)
                        continue
                    self.assertEqual(response.status_code, 200, response.text)
                    payload = response.json()
                    own_rid = seeded[caller][2]
                    if kind == "stats":
                        self.assertEqual(payload["summary"]["totalRounds"], 1)
                        self.assertEqual(payload["drillDown"]["roundIds"], [own_rid])
                    elif kind == "reports":
                        self.assertEqual([r["subjectId"] for r in payload["reports"]], [own_rid])
                    else:
                        self.assertEqual([str(r["id"]) for g in payload["groups"] for r in g["rounds"]], [own_rid])

    def test_j7_1_guessed_event_id_never_changes_victim_partition(self) -> None:
        # Event round ids are client-generated, so the API may accept a guessed id into
        # the CALLER's partition. The victim's original event must remain byte-for-byte.
        victim_rows = [("owner", "me", ADMIN_HEADER),
                       ("B", self.bob["id"], self._auth(self.bob["token"]))]
        for label, pid, victim_headers in victim_rows:
            rid = f"victim-round-{label}"
            event = {"schema": "ai-caddie-live-round-event-v1", "eventId": "victim-note",
                     "roundId": rid, "timestamp": "2026-10-20T08:00:00Z", "hole": 1,
                     "kind": "note", "payload": {"note": f"private-{label}"}}
            def post(headers, note, key):
                return self.client.post(f"/api/v2/mobile/rounds/{rid}/events",
                    headers={**headers, "Idempotency-Key": key},
                    json={"roundId": rid, "events": [{**event, "payload": {"note": note}}]})
            self.assertEqual(post(victim_headers, f"private-{label}", "victim-seed").status_code, 200)
            before = self.client.get(f"/api/v2/mobile/rounds/{rid}/events/replay", headers=victim_headers).json()
            with self.subTest(victim=label):
                response = post(self._auth(self.alice["token"]), "attacker-note", "attacker-write")
                self.assertIn(response.status_code, {200, 403, 404})
                after = self.client.get(f"/api/v2/mobile/rounds/{rid}/events/replay", headers=victim_headers)
                self.assertEqual(after.json(), before)
                self.assertEqual(after.json()["events"][0]["event"]["payload"]["note"], f"private-{label}")

    def test_j7_1_course_capability_is_available_to_members(self) -> None:
        # Course tees are public course facts, available to both members as to owner.
        # No release/geometry is present for this synthetic id: generic tee tiers are valid.
        for label, headers in [("owner", ADMIN_HEADER), ("A", self._auth(self.alice["token"])),
                               ("B", self._auth(self.bob["token"]))]:
            with self.subTest(caller=label):
                response = self.client.get("/api/v2/courses/991601/tees", headers=headers)
                self.assertEqual(response.status_code, 200, response.text)
                self.assertEqual(response.json()["globalId"], 991601)
                self.assertTrue(response.json()["tees"])



class J7AuthorizationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.players_root = mock.patch.object(players, "ROOT", self.root)
        self.players_root.start()
        self.addCleanup(self.players_root.stop)
        self.env = mock.patch.dict(os.environ, {"AI_CADDIE_ADMIN_TOKEN": ADMIN})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.member = players.create_player("Member", root=self.root)
        self.client = TestClient(app)

    def test_j7_2_member_cannot_elevate_with_admin_header_and_anonymous_is_401(self) -> None:
        member = {"Authorization": f"Bearer {self.member['token']}"}
        self.assertEqual(self.client.get("/api/v2/admin/players", headers=member).status_code, 403)
        self.assertEqual(
            self.client.get("/api/v2/admin/players", headers={**member, **ADMIN_HEADER}).status_code,
            403,
        )
        self.assertEqual(self.client.get("/api/v2/admin/players").status_code, 401)
        self.assertEqual(self.client.get("/api/v2/admin/players", headers=ADMIN_HEADER).status_code, 200)

    def test_j7_2_production_without_admin_token_fails_closed_at_startup(self) -> None:
        with mock.patch.dict(
            os.environ,
            {"AI_CADDIE_SECURITY_PROFILE": "production"},
            clear=True,
        ):
            with self.assertRaises(RuntimeError):
                assert_admin_security_config()

    def test_j7_2_session_ttl_is_bounded_by_configured_duration(self) -> None:
        with mock.patch.dict(os.environ, {"AI_CADDIE_SESSION_TTL_HOURS": "2"}):
            self.assertEqual(auth_api._session_ttl(), timedelta(hours=2))

    def test_j7_2_apple_sign_in_mints_a_time_limited_member_session(self) -> None:
        database_url = f"sqlite:///{self.root / 'identity.db'}"
        with mock.patch.dict(
            os.environ,
            {
                "AI_CADDIE_DATABASE_URL": database_url,
                "AI_CADDIE_APPLE_BUNDLE_ID": "com.example.caddie",
                "AI_CADDIE_SESSION_TTL_HOURS": "2",
            },
        ):
            db.reset_engine_for_tests()
            self.addCleanup(db.reset_engine_for_tests)
            Base.metadata.create_all(db.get_engine())
            with db.session_scope() as session:
                family, owner = identity_repo.create_family_with_owner(
                    session, family_name="J7 family", owner_display_name="Owner"
                )
                identity_repo.map_legacy_player(session, legacy_player_id="me", user_id=owner.id)
                session.flush()
            with mock.patch.object(
                auth_api,
                "_verify",
                return_value=AppleIdentity(subject="runtime-member-sub", email=None),
            ):
                response = self.client.post(
                    "/api/v2/auth/apple",
                    json={"identityToken": "runtime-apple-jwt", "displayName": "Member A"},
                )
        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertTrue(payload["token"])
        expires = datetime.fromisoformat(payload["expiresAt"])
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        remaining = expires - datetime.now(timezone.utc)
        self.assertGreater(remaining, timedelta(hours=1, minutes=59))
        self.assertLess(remaining, timedelta(hours=2, minutes=1))
        self.assertTrue(str(payload["playerId"]).startswith("p_"))


if __name__ == "__main__":
    unittest.main()
