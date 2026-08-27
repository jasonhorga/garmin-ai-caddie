from __future__ import annotations

import os
from pathlib import Path
import subprocess
import unittest


class CIFixtureEntrypointTests(unittest.TestCase):
    def test_entrypoint_is_opt_in_outside_ci(self) -> None:
        env = {key: value for key, value in os.environ.items() if key not in {"CI", "AI_CADDIE_DEBUG_FIXTURE", "AI_CADDIE_ADMIN_TOKEN"}}
        result = subprocess.run(
            ["bash", "ops/run_ci_fixture.sh"],
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 64)
        self.assertIn("requires CI=true", result.stderr)

    def test_entrypoint_forces_fixture_private_profile(self) -> None:
        script = Path("ops/run_ci_fixture.sh").read_text(encoding="utf-8")
        self.assertIn("export AI_CADDIE_DATA_MODE=fixture", script)
        self.assertIn("export AI_CADDIE_SECURITY_PROFILE=private", script)
        self.assertIn("export AI_CADDIE_FIXTURE_MODE=1", script)
        self.assertNotIn("load_latest_snapshot", script)
        self.assertNotIn("AI_CADDIE_ADMIN_TOKEN=ci-admin-token", script)


if __name__ == "__main__":
    unittest.main()
