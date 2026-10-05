"""Daily pin sheet (洞位图): the model reply is normalised to printed facts only."""
from __future__ import annotations

import base64
import json
import unittest
from unittest.mock import patch

from fastapi import HTTPException
from fastapi.testclient import TestClient
from starlette.datastructures import QueryParams

from ai_caddie.llm.llm_providers import ProviderConfigurationError
from ai_caddie.llm.pin_sheet_vision import (
    PinSheetImage,
    PinSheetReadError,
    parse_pin_sheet_reply,
    read_pin_sheet,
)
from server_v2.main import _requires_admin_token, app
from server_v2.models import PinSheetImageIn, PinSheetRequest
from server_v2.players_api import is_player_scoped_route
from server_v2 import pin_sheet as pin_sheet_api

JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 64


class _Provider:
    def __init__(self, reply: str) -> None:
        self.reply = reply
        self.calls = []

    def chat_multimodal(self, messages, media_parts, max_tokens=None):
        self.calls.append((list(messages), list(media_parts), max_tokens))
        return self.reply


class PinSheetParseTests(unittest.TestCase):
    def test_numbers_dot_and_zone_tiers_are_kept_and_bad_rows_dropped(self) -> None:
        reply = "```json\n" + json.dumps({
            "date": "2026-10-04",
            "holes": [
                {"hole": 20, "fromFrontYd": 40, "side": "R", "fromSideYd": 6, "depthYd": 45, "dotU": 0.9, "dotV": 0.8},
                {"hole": 26, "fromFrontYd": 22, "side": "c"},
                {"hole": 3, "dotU": 0.3, "dotV": 0.6},
                {"hole": 4, "zone": "Back"},
                {"hole": 5},
                {"hole": 99, "fromFrontYd": 5, "side": "L", "fromSideYd": 5},
                {"hole": 7, "fromFrontYd": 11, "side": "R"},
                {"hole": 20, "fromFrontYd": 1, "side": "L", "fromSideYd": 1},
            ],
        }) + "\n```"
        sheet = parse_pin_sheet_reply(reply)
        self.assertEqual(sheet["schema"], "ai-caddie-pin-sheet-v1")
        self.assertEqual(sheet["date"], "2026-10-04")
        by_hole = {row["hole"]: row for row in sheet["holes"]}
        self.assertEqual(sorted(by_hole), [3, 4, 20, 26])
        self.assertEqual((by_hole[20]["fromFrontYd"], by_hole[20]["side"], by_hole[20]["fromSideYd"]), (40, "R", 6))
        self.assertEqual(by_hole[20]["depthYd"], 45, "the first row of a duplicated hole wins")
        self.assertEqual((by_hole[26]["fromFrontYd"], by_hole[26]["side"], by_hole[26]["fromSideYd"]), (22, "C", None))
        self.assertEqual((by_hole[3]["dotU"], by_hole[3]["dotV"], by_hole[3]["fromFrontYd"]), (0.3, 0.6, None))
        self.assertEqual(by_hole[4]["zone"], "back")

    def test_unusable_replies_are_errors_not_invented_pins(self) -> None:
        for reply in ("no json here", "[]", '{"holes": "x"}', '{"holes": [{"hole": 1}]}'):
            with self.assertRaises(PinSheetReadError):
                parse_pin_sheet_reply(reply)

    def test_read_sends_every_photo_to_the_model(self) -> None:
        provider = _Provider('{"date": null, "holes": [{"hole": 1, "fromFrontYd": 6, "side": "R", "fromSideYd": 5}]}')
        sheet = read_pin_sheet([PinSheetImage("image/jpeg", JPEG), PinSheetImage("image/jpeg", JPEG)], provider)
        self.assertEqual(sheet["holes"][0]["hole"], 1)
        _, media, _ = provider.calls[0]
        self.assertEqual(len(media), 2)
        with self.assertRaises(ProviderConfigurationError):
            read_pin_sheet([PinSheetImage("image/jpeg", JPEG)], object())


class PinSheetNumberingTests(unittest.TestCase):
    def test_per_loop_numbering_keeps_each_loop_and_straight_through_has_no_loop(self) -> None:
        per_loop = parse_pin_sheet_reply(json.dumps({"holes": [
            {"loop": "b", "hole": 1, "zone": "front"},
            {"loop": "A", "hole": 1, "zone": "back"},
            {"loop": "A", "hole": 1, "zone": "middle"},
            {"loop": "A", "hole": 9, "zone": "middle"},
        ]}))
        self.assertEqual(
            [(row["loop"], row["hole"], row["zone"]) for row in per_loop["holes"]],
            [("A", 1, "back"), ("A", 9, "middle"), ("B", 1, "front")],
            "A1 and B1 are different holes; a repeated A1 (overlapping photos) keeps its first read",
        )
        straight = parse_pin_sheet_reply(json.dumps({"holes": [
            {"loop": None, "hole": 19, "zone": "front"}, {"hole": 1, "zone": "back"},
        ]}))
        self.assertEqual([(row["loop"], row["hole"]) for row in straight["holes"]], [(None, 1), (None, 19)])

    def test_unsupported_numbering_is_rejected_not_guessed(self) -> None:
        for holes in (
            [{"loop": "A", "hole": 1, "zone": "front"}, {"hole": 10, "zone": "front"}],
            [{"loop": "A", "hole": 27, "zone": "front"}],
        ):
            with self.assertRaises(PinSheetReadError):
                parse_pin_sheet_reply(json.dumps({"holes": holes}))

    def test_only_a_real_calendar_date_is_passed_on(self) -> None:
        row = [{"hole": 1, "zone": "front"}]
        self.assertEqual(parse_pin_sheet_reply(json.dumps({"date": "2026-10-04", "holes": row}))["date"], "2026-10-04")
        for printed in ("2026-02-30", "10-04", "Oct 4", None):
            self.assertIsNone(parse_pin_sheet_reply(json.dumps({"date": printed, "holes": row}))["date"])


class PinSheetEndpointTests(unittest.TestCase):
    """The whole server path: auth gate → body → image checks → provider → normalised reply."""

    ADMIN_ENV = {"AI_CADDIE_ADMIN_TOKEN": "admin-secret"}
    ADMIN_HEADER = {"X-AI-Caddie-Admin-Token": "admin-secret"}

    def _post(self, client: TestClient, headers: dict, images: list[bytes]):
        return client.post(
            "/api/v2/mobile/pin-sheet",
            headers=headers,
            json={"images": [{"contentBase64": base64.b64encode(data).decode(), "mimeType": "image/jpeg"} for data in images]},
        )

    def test_authenticated_post_returns_the_read_sheet_and_failures_map_to_statuses(self) -> None:
        client = TestClient(app)
        reply = json.dumps({"date": "2026-10-04", "holes": [
            {"hole": 20, "fromFrontYd": 40, "side": "R", "fromSideYd": 6, "depthYd": 45},
        ]})
        with patch.dict("os.environ", self.ADMIN_ENV):
            unauthenticated = self._post(client, {}, [JPEG])
            with patch("server_v2.pin_sheet.build_media_vision_provider", return_value=_Provider(reply)) as built:
                ok = self._post(client, self.ADMIN_HEADER, [JPEG, JPEG])
            with patch("server_v2.pin_sheet.build_media_vision_provider", return_value=_Provider("no json")):
                unreadable = self._post(client, self.ADMIN_HEADER, [JPEG])
            with patch("server_v2.pin_sheet.build_media_vision_provider", side_effect=RuntimeError("boom key=sk-secret")):
                broken = self._post(client, self.ADMIN_HEADER, [JPEG])
            with patch("server_v2.pin_sheet.build_media_vision_provider", return_value=object()):
                text_only = self._post(client, self.ADMIN_HEADER, [JPEG])
            not_image = self._post(client, self.ADMIN_HEADER, [b"hello"])
            too_many = self._post(client, self.ADMIN_HEADER, [JPEG] * 4)

        self.assertEqual(unauthenticated.status_code, 401)
        self.assertEqual(ok.status_code, 200, ok.text)
        self.assertEqual(ok.json(), {
            "schema": "ai-caddie-pin-sheet-v1",
            "date": "2026-10-04",
            "holes": [{"loop": None, "hole": 20, "fromFrontYd": 40, "side": "R", "fromSideYd": 6,
                       "depthYd": 45, "dotU": None, "dotV": None, "zone": None}],
        })
        self.assertEqual(built.call_count, 1)
        self.assertEqual(unreadable.status_code, 422)
        self.assertEqual(broken.status_code, 502)
        # A model that cannot read images is a deployment problem, not a bad photo.
        self.assertEqual(text_only.status_code, 503)
        self.assertEqual(not_image.status_code, 415)
        self.assertEqual(too_many.status_code, 422)


class PinSheetRouteTests(unittest.TestCase):
    def test_the_route_is_prebody_gated_and_player_scoped(self) -> None:
        path = "/api/v2/mobile/pin-sheet"
        self.assertTrue(_requires_admin_token("POST", path, QueryParams("")))
        self.assertTrue(is_player_scoped_route("POST", path))

    def test_the_handler_rejects_non_images_and_maps_a_read_failure(self) -> None:
        not_image = PinSheetRequest(images=[PinSheetImageIn(contentBase64=base64.b64encode(b"hello").decode())])
        with self.assertRaises(HTTPException) as caught:
            pin_sheet_api.read_pin_sheet_response(not_image)
        self.assertEqual(caught.exception.status_code, 415)

        image = PinSheetRequest(images=[PinSheetImageIn(contentBase64=base64.b64encode(JPEG).decode())])
        original = pin_sheet_api.build_media_vision_provider
        try:
            pin_sheet_api.build_media_vision_provider = lambda: _Provider("not json")
            with self.assertRaises(HTTPException) as caught:
                pin_sheet_api.read_pin_sheet_response(image)
            self.assertEqual(caught.exception.status_code, 422)
            pin_sheet_api.build_media_vision_provider = lambda: _Provider(
                '{"holes": [{"hole": 26, "fromFrontYd": 22, "side": "C"}]}'
            )
            self.assertEqual(pin_sheet_api.read_pin_sheet_response(image)["holes"][0]["side"], "C")
        finally:
            pin_sheet_api.build_media_vision_provider = original



class GeminiOAuthMultimodalTests(unittest.TestCase):
    def test_code_assist_request_carries_the_images_with_the_user_turn(self) -> None:
        from ai_caddie.llm.llm_providers import LLMMediaPart, LLMMessage, _to_code_assist_generate_content_request

        body = _to_code_assist_generate_content_request(
            model="gemini-2.5-flash",
            project="p",
            messages=[LLMMessage("system", "s"), LLMMessage("user", "read")],
            max_tokens=10,
            session_id="x",
            media_parts=[LLMMediaPart(media_type="image", mime_type="image/jpeg", data=JPEG)],
        )
        parts = body["request"]["contents"][0]["parts"]
        self.assertEqual(parts[0], {"text": "read"})
        self.assertEqual(parts[1]["inlineData"]["mimeType"], "image/jpeg")
        self.assertEqual(base64.b64decode(parts[1]["inlineData"]["data"]), JPEG)


if __name__ == "__main__":
    unittest.main()
