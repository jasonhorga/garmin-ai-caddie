"""Offline regressions for card 447's shared recovery helpers and result line.

These do not need the shell tools used by the legacy deploy harness. Health reads,
recovery, and signal installation are stubbed; no Docker daemon or endpoint is used.
"""

from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
from copy import deepcopy
import io
import os
import unittest
from unittest.mock import patch

from ops import agenthub_deploy as deploy


class UpContractRegressionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.cfg = deploy.Config({"AICADDIE_API_PORT": "39556"})

    def container(self, name: str, finished: str, *, mounts: list[dict] | None = None) -> deploy.Container:
        return deploy.Container({
            "id": name,
            "name": self.cfg.prefix + name,
            "labels": {deploy.REVISION_LABEL: "2b" * 20},
            "running": False,
            "finishedAt": finished,
            "ports": {"9000/tcp": [{"HostPort": str(self.cfg.port)}]},
            "network": self.cfg.network,
            "mounts": mounts if mounts is not None else [self.valid_mount()],
        })

    def valid_mount(self) -> dict:
        return {"Name": self.cfg.volume, "Destination": deploy.PRIVATE_ROOT, "RW": True}

    def test_health_requires_both_ok_status_and_the_selected_revision(self) -> None:
        revision = "2b" * 20
        cases = (
            ({"status": "ok", "revision": revision}, True),
            ({"status": "starting", "revision": revision}, False),
            ({"status": "ok", "revision": "1" * 40}, False),
            ({"revision": revision}, False),
            ({"status": "ok"}, False),
            (None, False),
        )
        for response, expected in cases:
            with self.subTest(response=response), patch.object(deploy, "fetch_health", return_value=response) as fetch:
                self.assertIs(deploy.wait_health("https://health.example.invalid", revision, 0, 0), expected)
                fetch.assert_called_once_with("https://health.example.invalid")

    def test_stopped_release_selection_compares_fractional_seconds_numerically(self) -> None:
        # Lexical order puts '.9Z' after '.95Z'. Name and listing order must not decide either.
        older = self.container("z-older", "2026-10-19T03:00:00.9Z")
        newer = self.container("a-newer", "2026-10-19T03:00:00.95Z")
        self.assertEqual(older.finished_key, deploy._finished_key("2026-10-19T03:00:00.90Z"))
        self.assertEqual(
            deploy._finished_key("2026-10-19T03:00:00Z"),
            deploy._finished_key("2026-10-19T03:00:00.0Z"),
        )
        for candidates in ([older, newer], [newer, older]):
            with self.subTest(order=[c.name for c in candidates]):
                self.assertIs(deploy.select_up_api(self.cfg, candidates), newer)

    def test_layout_rejects_missing_extra_wrong_destination_and_read_only_mounts(self) -> None:
        valid = self.valid_mount()
        invalid_mounts = (
            [],
            [valid, {"Name": "extra-volume", "Destination": "/extra", "RW": True}],
            [{**valid, "Name": "wrong-volume"}],
            [{**valid, "Destination": "/wrong-destination"}],
            [{**valid, "RW": False}],
        )
        fallback = self.container("valid", "2026-10-19T03:00:00Z")
        deploy.assert_layout(self.cfg, fallback)
        for mounts in invalid_mounts:
            with self.subTest(mounts=mounts):
                malformed = self.container("invalid", "2026-10-19T04:00:00Z", mounts=deepcopy(mounts))
                with self.assertRaises(deploy.DeployError):
                    deploy.assert_layout(self.cfg, malformed)
                self.assertIs(deploy.select_up_api(self.cfg, [malformed, fallback]), fallback)
        wrong_network = self.container("wrong-network", "2026-10-19T04:00:00Z")
        wrong_network.network = "wrong-network"
        with self.assertRaises(deploy.DeployError):
            deploy.assert_layout(self.cfg, wrong_network)
        self.assertIs(deploy.select_up_api(self.cfg, [wrong_network, fallback]), fallback)

    def test_up_failure_result_has_a_nonempty_trailing_reason(self) -> None:
        for part, container in (("docker", "none"), ("database", "fixture-db"), ("api", "fixture-api")):
            with self.subTest(part=part):
                output = io.StringIO()
                error = io.StringIO()
                with (
                    patch.dict(os.environ, {}, clear=True),
                    patch.object(deploy, "install_signal_handlers"),
                    patch.object(deploy, "up", side_effect=deploy.UpFailed(part, container, "fixture recovery failed")),
                    redirect_stdout(output),
                    redirect_stderr(error),
                ):
                    code = deploy.main(["up"])
                self.assertEqual(code, 1)
                self.assertEqual(error.getvalue(), "")
                results = [line for line in output.getvalue().splitlines() if "result=" in line]
                self.assertEqual(len(results), 1)
                fields, separator, reason = results[0].partition(" reason=")
                self.assertEqual(separator, " reason=")
                self.assertTrue(reason.strip(), "a recovery failure must say why it failed")
                self.assertIn("result=failed action=up", fields)
                self.assertIn(f"part={part} container={container}", fields)


if __name__ == "__main__":
    unittest.main()
