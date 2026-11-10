"""A player's credentials never leak out of the service (test-plan S-23).

Every request enters the real app with startup run (TestClient as a context
manager), so the log privacy guard is installed exactly as in production.  The
secrets are sent where a phone or a confused client could put them: the
Authorization header, a cookie, the query string, extra JSON fields, nested
payload objects and text that is echoed back by an upstream error.  The identity
store is faked to fail with an error that echoes the presented token (as a
database driver echoing its bound parameter would), so the secret really does
reach a log record and only the privacy filter stands between it and the log.

The secret must then appear in none of: response bodies or headers, the final
formatted log text (including tracebacks), any file written under the private
roots, or the messages and media handed to the vision model.
"""
import base64
import io
import json
import logging
import os
import struct
import unittest
import zlib
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from urllib.parse import quote

from fastapi.testclient import TestClient

from ai_caddie.core import request_timing
from ai_caddie.rounds import players
from server_v2 import course_install, db, identity_repo, mobile, pin_sheet
from server_v2 import main as server_main
from server_v2 import session as session_routes
from server_v2.main import app

SECRETS = {
    "player bearer token": "s23PlayerTok-Q7ZP4XW2kd",
    "garmin session": "s23GarminSess-9KD2mVt8oa",
    "apple identity token": "eyJraWQiOiJzMjMifQ.s23AppleIdTok.c2lnUzIzeA",
    "apple subject": "001234.s23applesub7f9e1c.0420",
    "apple email": "s23relay-x7q2@privaterelay.appleid.com",
}
ROUND_ID = "900001"
STARTED_AT = "2026-10-27T08:00:00Z"
LOG_FORMAT = "%(name)s %(levelname)s %(message)s"
ACTIVE_ROUND_STATE = (
    (server_main, ("_ACTIVE_ROUNDS", "_ACTIVE_COURSES", "_ACTIVE_EVENT_TIMES", "_ACTIVE_START_TIMES",
                   "_ROUND_START_CACHE", "_ACTIVE_EVENT_DEVICES", "_ACTIVE_SELECTIONS")),
    (course_install, ("_CURRENT_COURSE_IDS",)),
)
PIN_SHEET_REPLY = json.dumps({"date": None, "holes": [{"hole": 1, "fromFrontYd": 12, "side": "C"}]})


def _forms(secret):
    """The literal and its URL-encoded spelling (a query value may be stored either way)."""
    return {secret, quote(secret, safe="")}


def _png():
    def chunk(kind, data):
        body = kind + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)
    header = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header)
            + chunk(b"IDAT", zlib.compress(b"\x00\xff\xff\xff")) + chunk(b"IEND", b""))


def _store_echoes_token(_session, token):
    # A failing identity store whose driver error repeats the bound parameter.
    raise RuntimeError(f"identity lookup failed token={token} raw parameter {token}")


def _timing_record(request_id, **extra):
    return {"request_id": request_id, "path": f"/api/v2/mobile/rounds/{ROUND_ID}/package",
            "client_total_ms": 120.5, "status": 200, "started_at": STARTED_AT,
            "network_type": "wifi", **extra}


def _event(event_id, round_id=ROUND_ID, **extra):
    return {"schema": "ai-caddie-live-round-event-v1", "eventId": event_id, "roundId": round_id,
            "timestamp": STARTED_AT, "hole": 1, "kind": "score", "payload": {"strokes": 4}, **extra}


class _Capture(logging.Handler):
    """Keeps what a log sink would receive: the formatted line and the record's fields."""

    def __init__(self):
        super().__init__(logging.DEBUG)
        self.setFormatter(logging.Formatter(LOG_FORMAT))
        self.lines = []

    def emit(self, record):
        self.lines.append(self.format(record) + "\n" + repr(sorted(record.__dict__.items(), key=str)))

    def text(self):
        return "\n".join(self.lines)


def _preserve_logging(case):
    """Snapshot logging globals that app startup changes; restore them at test end."""
    manager = logging.Logger.manager
    original_add, original_call = logging.Logger.addHandler, logging.Logger.callHandlers
    loggers = {name: value for name, value in manager.loggerDict.items() if isinstance(value, logging.Logger)}
    saved = {name: (list(lg.handlers), list(lg.filters), lg.level, lg.propagate, lg.disabled)
             for name, lg in loggers.items()}
    root = logging.getLogger()
    saved_root = (list(root.handlers), list(root.filters), root.level)
    handlers = {id(h): h for lg in [root, *loggers.values()] for h in lg.handlers}
    if logging.lastResort is not None:
        handlers[id(logging.lastResort)] = logging.lastResort
    handler_filters = {key: list(h.filters) for key, h in handlers.items()}
    last_resort = logging.lastResort

    def restore():
        if logging.Logger.addHandler is not original_add:
            handle = getattr(logging.Logger.addHandler, "_privacy_handle", None)
            if handle is not None:
                handle.close()
        logging.Logger.addHandler, logging.Logger.callHandlers = original_add, original_call
        for name, value in list(manager.loggerDict.items()):
            if not isinstance(value, logging.Logger):
                continue
            if name in saved:
                value.handlers[:], value.filters[:], value.level, value.propagate, value.disabled = (
                    list(saved[name][0]), list(saved[name][1]), *saved[name][2:])
            else:
                value.handlers[:], value.filters[:] = [], []
                value.level, value.propagate, value.disabled = logging.NOTSET, True, False
        root.handlers[:], root.filters[:], root.level = list(saved_root[0]), list(saved_root[1]), saved_root[2]
        for key, handler in handlers.items():
            handler.filters[:] = handler_filters[key]
        logging.lastResort = last_resort
        manager._clear_cache()

    case.addCleanup(restore)


class Secrets(unittest.TestCase):
    def setUp(self):
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        env = patch.dict(os.environ, {
            "AI_CADDIE_BOOT_BACKGROUND_WORK": "0",
            "AI_CADDIE_DATABASE_URL": f"sqlite:///{self.root / 'identity.db'}",
        })
        env.start()
        self.addCleanup(env.stop)
        for name in ("AI_CADDIE_ADMIN_TOKEN", "AI_CADDIE_SECURITY_PROFILE", "AI_CADDIE_PRIVATE_ROOT"):
            os.environ.pop(name, None)  # open-dev owner grant; restored by the env patch
        for target in (
            patch.object(mobile, "MOBILE_ROOT", self.root / "mobile"),
            patch.object(mobile, "ANNOTATION_ROOT", self.root / "mobile" / "annotations"),
            patch.dict(mobile._PACKAGE_SINGLEFLIGHT, {}, clear=True),
            patch.object(request_timing, "TIMING_ROOT", self.root / "private"),
            patch.object(request_timing, "_TIMING_CLEANED", set()),
            patch.object(session_routes, "SESSION_ROOT", self.root / "sessions"),
            patch.object(players, "ROOT", self.root / "players"),
            patch.object(identity_repo, "resolve_session_token", side_effect=_store_echoes_token),
            patch.object(server_main, "_ACTIVE_PACKAGED_ROUNDS", set()),
            *(patch.dict(getattr(module, name), clear=True) for module, names in ACTIVE_ROUND_STATE for name in names),
        ):
            target.start()
            self.addCleanup(target.stop)
        db.reset_engine_for_tests()
        self.addCleanup(db.reset_engine_for_tests)
        _preserve_logging(self)
        self.addCleanup(request_timing.flush_timing_writes)
        self.client = TestClient(app)
        self.client.__enter__()  # runs the real startup, which mounts the log privacy guard
        self.addCleanup(self.client.__exit__, None, None, None)
        self.logs = _Capture()
        logging.getLogger().addHandler(self.logs)
        for name in server_main.SERVICE_INFO_LOGGERS:  # these do not propagate to the root
            logging.getLogger(name).addHandler(self.logs)

    # -- observation helpers -------------------------------------------------
    def stored_text(self):
        request_timing.flush_timing_writes()
        return "\n".join(path.read_bytes().decode("utf-8", "replace")
                         for path in sorted(self.root.rglob("*")) if path.is_file())

    def assertNoSecret(self, secrets, *responses, model_input=""):
        stored, logs = self.stored_text(), self.logs.text()
        bodies = "\n".join(f"{r.text}\n{dict(r.headers)}" for r in responses)
        for secret in secrets:
            for form in _forms(secret):
                self.assertNotIn(form, bodies, "secret in a response")
                self.assertNotIn(form, logs, "secret in the log output")
                self.assertNotIn(form, stored, "secret in stored files")
                self.assertNotIn(form, model_input, "secret in model input")

    def post_timing(self, entries, headers=None, params=None):
        return self.client.post("/api/v2/mobile/client-timing", json=entries, headers=headers, params=params)

    def post_events(self, body, key, headers=None, params=None, round_id=ROUND_ID):
        return self.client.post(f"/api/v2/mobile/rounds/{round_id}/events", json=body,
                                headers={"Idempotency-Key": key, **(headers or {})}, params=params)

    # -- tests ---------------------------------------------------------------
    def test_no_secret_in_response_log_store(self):
        """S-23 [main]: token, Garmin session and Apple identity sent by the phone never reach responses, logs or storage

        The same credentials ride in the Authorization header, a cookie, the query
        string and extra JSON fields of a timing report and an event sync, while the
        identity store fails with an error that repeats the token.
        """
        token, garmin = SECRETS["player bearer token"], SECRETS["garmin session"]
        apple = SECRETS["apple identity token"]
        headers = {"Authorization": f"Bearer {token}", "Cookie": f"GARMIN-SSO-CUST-GUID={garmin}"}
        params = {"key": apple}

        timing = self.post_timing([
            _timing_record("s23-main-timing", path=f"/api/v2/mobile/rounds/{ROUND_ID}/package?key={token}"),
            _timing_record("s23-main-extra", identityToken=apple, appleSub=SECRETS["apple subject"],
                           email=SECRETS["apple email"]),
        ], headers=headers, params=params)
        self.assertEqual(timing.status_code, 200, timing.text)
        self.assertEqual(timing.json(), {"accepted": 1, "rejected": 1})

        events = self.post_events(
            {"roundId": ROUND_ID, "token": token, "garminSession": garmin,
             "events": [_event("s23-main-e1", identityToken=apple, appleSub=SECRETS["apple subject"])]},
            "s23-main-sync", headers=headers, params=params)
        self.assertEqual(events.status_code, 200, events.text)
        self.assertEqual(events.json()["acceptedEventIds"], ["s23-main-e1"])

        self.assertNoSecret(SECRETS.values(), timing, events)
        # The token did reach a log record: the store failure was logged, only without its payload.
        logs = self.logs.text()
        self.assertIn("identity store error during session-token resolution", logs)
        self.assertIn("RuntimeError: [redacted]", logs)
        # Non-secret facts survive: the round id, the event, and the timing record.
        stored = self.stored_text()
        self.assertIn(f'"roundId": "{ROUND_ID}"', stored)
        self.assertIn("s23-main-e1", stored)
        self.assertIn('"request_id":"s23-main-timing"', stored)

    def test_secret_kind_by_location_table(self):
        """S-23: every kind of secret is kept out in every place a client can put it

        Rows are secret kind x location: Authorization header, cookie header, query
        string, extra JSON field, nested payload object, URL text in a report and an
        upstream error text that echoes the credential.
        """
        fake = _FakeVision(error_for=lambda secret: RuntimeError(
            f"vision upstream 401: Authorization: Bearer {secret}; access_token={secret}"))
        locations = {
            "authorization header": lambda s, n: (self.post_timing(
                [_timing_record(f"s23-row-{n}")], headers={"Authorization": f"Bearer {s}"}), 200),
            "cookie header": lambda s, n: (self.post_timing(
                [_timing_record(f"s23-row-{n}")], headers={"Cookie": f"SESSIONID={s}; GARMIN-SSO-CUST-GUID={s}"}), 200),
            "query string": lambda s, n: (self.post_timing(
                [_timing_record(f"s23-row-{n}")], params={"key": s, "token": s}), 200),
            "json body field": lambda s, n: (self.post_timing(
                [_timing_record(f"s23-row-{n}", token=s, password=s)]), 200),
            "nested field": lambda s, n: (self.post_events(
                {"roundId": ROUND_ID, "events": [_event(f"s23-row-{n}", payload={
                    "strokes": 4, "garmin": {"session": {"oauthToken": s, "identityToken": s}}})]},
                f"s23-row-{n}"), 422),
            "url text": lambda s, n: (self.post_timing([_timing_record(
                f"s23-row-{n}", path=f"/api/v2/share/{s}?key={s}&token={s}")]), 200),
            "upstream error text": lambda s, n: (self.post_pin_sheet(fake, secret=s), 502),
        }
        with patch.object(pin_sheet, "build_media_vision_provider", return_value=fake):
            row = 0
            for kind, secret in SECRETS.items():
                for location, send in locations.items():
                    row += 1
                    with self.subTest(kind=kind, location=location):
                        response, expected = send(secret, row)
                        self.assertEqual(response.status_code, expected, response.text)
                        self.assertNoSecret([secret], response, model_input=fake.seen())
        # The report path keeps its valid rows and drops the one carrying unknown fields.
        stored = self.stored_text()
        self.assertIn('"request_id":"s23-row-1"', stored)
        self.assertNotIn('"request_id":"s23-row-4"', stored)

    def test_key_spellings_redacted_and_plain_values_survive(self):
        """S-23: credential keys are redacted in any case or separator spelling, while plain values survive

        Boundaries: identityToken / IDENTITY_TOKEN / identity-token style keys in log
        text and in structured log fields; Bearer prefix case on the header; the
        50-record report limit; and the round id, status and near-miss keys such as
        tokenCount that must not be over-redacted.
        """
        secret = SECRETS["apple identity token"]
        log = logging.getLogger("server_v2.mobile")
        spellings = ("identityToken", "IDENTITY_TOKEN", "identity-token", "Identity_Token", "authorization",
                     "Authorization", "AUTHORIZATION", "Cookie", "COOKIE", "garmin_session_token",
                     "GarminSessionToken", "oauth_token", "access_token", "client_secret", "CLIENT-SECRET",
                     "api_key", "apiKey", "API_KEY", "X-CSRF-Token")
        for spelling in spellings:
            for separator in ("=", ": "):
                with self.subTest(spelling=spelling, separator=separator):
                    del self.logs.lines[:]
                    log.warning("upstream rejected %s%s%s status=401 tokenCount=2 hole=7",
                                spelling, separator, secret, extra={spelling: secret})
                    self.assertNoSecret([secret])
                    line = self.logs.lines[0]
                    self.assertIn(f"{spelling}{separator}[redacted]", line)
                    for plain in ("status=401", "tokenCount=2", "hole=7"):
                        self.assertIn(plain, line)
        for line in (f"Authorization: Bearer {secret}", f"Bearer {secret}", f"bearer:{secret}"):
            with self.subTest(bare=line):
                del self.logs.lines[:]
                log.warning("method=POST %s", line)
                self.assertNoSecret([secret])
                self.assertIn("method=POST", self.logs.text())

        for prefix in ("Bearer", "bearer", "BEARER"):
            with self.subTest(header_prefix=prefix):
                del self.logs.lines[:]
                response = self.post_timing([_timing_record(f"s23-case-{prefix}")],
                                            headers={"Authorization": f"{prefix} {secret}"})
                self.assertEqual(response.json(), {"accepted": 1, "rejected": 0})
                self.assertNoSecret([secret], response)
                # The bearer was read as a credential (the store was asked), not ignored.
                self.assertIn("identity store error during session-token resolution", self.logs.text())

        headers = {"Authorization": f"Bearer {secret}"}
        for count, status in ((50, 200), (51, 413)):
            with self.subTest(batch=count):
                response = self.post_timing([_timing_record(f"s23-limit-{count}-{i}") for i in range(count)],
                                            headers=headers)
                self.assertEqual(response.status_code, status, response.text)
                self.assertNoSecret([secret], response)

        response = self.post_events({"roundId": "900002", "events": [_event("s23-keep", round_id="900002")]},
                                    "s23-keep", headers=headers, round_id="900002")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertNoSecret([secret], response)
        stored = self.stored_text()
        self.assertIn('"roundId": "900002"', stored)
        self.assertIn('"strokes": 4', stored)

    def test_retried_posts_do_not_leak(self):
        """S-23: a retried timing report and a retried event sync stay free of secrets and give the same answer"""
        token, garmin = SECRETS["player bearer token"], SECRETS["garmin session"]
        headers = {"Authorization": f"Bearer {token}", "Cookie": f"SESSIONID={garmin}"}
        batch = [_timing_record("s23-retry"), _timing_record("s23-retry-bad", sessionToken=garmin)]
        first = self.post_timing(batch, headers=headers, params={"key": token})
        second = self.post_timing(batch, headers=headers, params={"key": token})
        self.assertEqual(first.json(), {"accepted": 1, "rejected": 1})
        self.assertEqual(second.json(), first.json())

        body = {"roundId": ROUND_ID, "token": token, "events": [_event("s23-retry-e1", identityToken=token)]}
        sent = self.post_events(body, "s23-retry-sync", headers=headers)
        again = self.post_events(body, "s23-retry-sync", headers=headers)
        self.assertEqual(sent.status_code, 200, sent.text)
        self.assertEqual(again.status_code, 200, again.text)
        self.assertFalse(sent.json()["duplicate"])
        self.assertTrue(again.json()["duplicate"])

        self.assertNoSecret([token, garmin], first, second, sent, again)
        stored = self.stored_text()
        self.assertEqual(stored.count('"request_id":"s23-retry"'), 2)
        self.assertEqual(stored.count('"eventId": "s23-retry-e1"'), 1)

    def test_model_input_never_carries_credentials(self):
        """S-23: the vision model sees the prompt and the photo, never the caller's token, Garmin session or Apple identity"""
        fake = _FakeVision()
        with patch.object(pin_sheet, "build_media_vision_provider", return_value=fake):
            response = self.post_pin_sheet(fake, secret=None)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual([hole["hole"] for hole in response.json()["holes"]], [1])
        self.assertEqual(len(fake.calls), 1)
        self.assertEqual([part.data for part in fake.calls[0][1]], [_png()])
        self.assertNoSecret(SECRETS.values(), response, model_input=fake.seen())

    def post_pin_sheet(self, fake, *, secret):
        """Send a sheet photo carrying every credential outside the image itself."""
        fake.fail_with = secret
        token, garmin, apple = (SECRETS[k] for k in ("player bearer token", "garmin session", "apple identity token"))
        return self.client.post(
            "/api/v2/mobile/pin-sheet",
            json={"images": [{"contentBase64": base64.b64encode(_png()).decode(), "mimeType": "image/png"}],
                  "identityToken": apple, "token": token},
            headers={"Authorization": f"Bearer {token}", "Cookie": f"SESSIONID={garmin}"},
            params={"key": apple})


class _FakeVision:
    """Records exactly what the service hands to the model."""

    def __init__(self, error_for=None):
        self.calls = []
        self.error_for = error_for
        self.fail_with = None

    def chat_multimodal(self, messages, media_parts, max_tokens=None):
        self.calls.append((list(messages), list(media_parts)))
        if self.fail_with is not None and self.error_for is not None:
            raise self.error_for(self.fail_with)
        return PIN_SHEET_REPLY

    def seen(self):
        out = io.StringIO()
        for messages, media in self.calls:
            out.write(repr(messages))
            for part in media:
                out.write(part.mime_type)
                out.write(part.data.decode("latin-1"))
        return out.getvalue()


if __name__ == "__main__":
    unittest.main()
