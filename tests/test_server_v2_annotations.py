from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from server_v2.main import app


class ServerV2AnnotationTests(unittest.TestCase):
    def test_annotation_create_list_and_target_endpoints_use_temp_root(self) -> None:
        client = TestClient(app)

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch("server_v2.annotations.ANNOTATION_ROOT", root):
                create_response = client.post(
                    "/api/v2/annotations",
                    json={
                        "targetType": "hole",
                        "targetId": "round-1:7",
                        "kind": "issue_tag",
                        "payload": {"tag": "approach_short"},
                    },
                )
                list_response = client.get("/api/v2/annotations")
                target_response = client.get("/api/v2/annotations/target/hole/round-1:7")

        self.assertEqual(create_response.status_code, 200)
        self.assertEqual(create_response.json()["schema"], "ai-caddie-annotation-create-v1")
        annotation = create_response.json()["annotation"]
        self.assertEqual(annotation["targetType"], "hole")
        self.assertEqual(annotation["kind"], "issue_tag")
        self.assertNotIn(tmp, create_response.text)

        self.assertEqual(list_response.status_code, 200)
        self.assertEqual(list_response.json()["schema"], "ai-caddie-annotations-v1")
        self.assertEqual(list_response.json()["total"], 1)

        self.assertEqual(target_response.status_code, 200)
        self.assertEqual(target_response.json()["total"], 1)
        self.assertEqual(target_response.json()["target"]["targetType"], "hole")
        self.assertEqual(target_response.json()["target"]["targetId"], "round-1:7")

    def test_annotation_api_accepts_live_round_correction_kinds(self) -> None:
        client = TestClient(app)

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch("server_v2.annotations.ANNOTATION_ROOT", root):
                responses = [
                    client.post(
                        "/api/v2/annotations",
                        json={
                            "targetType": "hole",
                            "targetId": "round-1:7",
                            "kind": kind,
                            "payload": payload,
                        },
                    )
                    for kind, payload in [
                        ("putt_correction", {"from": 2, "to": 4}),
                        ("score_correction", {"from": 5, "to": 4}),
                        ("weather_context_note", {"text": "wind into from the left"}),
                        ("strategy_note", {"text": "aimed right center"}),
                    ]
                ]

        self.assertEqual([response.status_code for response in responses], [200, 200, 200, 200])

    def test_annotation_post_rejects_invalid_target_and_kind(self) -> None:
        client = TestClient(app)

        bad_target = client.post(
            "/api/v2/annotations",
            json={"targetType": "course", "targetId": "c1", "kind": "round_note", "payload": {}},
        )
        bad_kind = client.post(
            "/api/v2/annotations",
            json={"targetType": "round", "targetId": "r1", "kind": "swing_thought", "payload": {}},
        )

        self.assertEqual(bad_target.status_code, 422)
        self.assertEqual(bad_kind.status_code, 422)


if __name__ == "__main__":
    unittest.main()
