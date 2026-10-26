from __future__ import annotations

from pathlib import Path
import os
import signal
import subprocess
import sys
from tempfile import TemporaryDirectory
import threading
import unittest
from unittest.mock import patch

from ai_caddie.connectors import session_material
from ai_caddie.garmin import garmin_auth


def _save(root: Path, cookie: str, csrf: str) -> None:
    session_material.save_garmin_cn_web_session(
        web_session_header=f"Cookie: {cookie}",
        anti_forgery_value=f"connect-csrf-token: {csrf}",
        root=root,
    )


class SessionMaterialGenerationTests(unittest.TestCase):
    def test_failed_second_import_keeps_one_complete_generation(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _save(root, "JWT_WEB=first", "csrf-first")

            with patch.object(
                session_material,
                "_publish_generation",
                side_effect=OSError("simulated process failure before switch"),
            ):
                with self.assertRaises(OSError):
                    _save(root, "JWT_WEB=second", "csrf-second")

            token_dir = root / ".garmin_tokens"
            current = (token_dir / session_material.CURRENT_FILE).read_text().strip()
            generation = token_dir / session_material.GENERATIONS_DIR / current
            self.assertEqual((generation / "web_cookie.txt").read_text(), "JWT_WEB=first\n")
            self.assertEqual((generation / "csrf.txt").read_text(), "csrf-first\n")

    def test_concurrent_imports_publish_only_complete_pairs(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            first_cookie_written = threading.Event()
            second_finished = threading.Event()
            original_write = session_material._write_generation_file

            def delayed_write(path: Path, content: bytes) -> None:
                original_write(path, content)
                if path.name == "web_cookie.txt" and content == b"JWT_WEB=first\n":
                    first_cookie_written.set()
                    self.assertTrue(second_finished.wait(timeout=2))
                elif path.name == "web_cookie.txt" and content == b"JWT_WEB=second\n":
                    self.assertTrue(first_cookie_written.wait(timeout=2))
                elif path.name == "csrf.txt" and content == b"csrf-second\n":
                    second_finished.set()

            errors: list[BaseException] = []

            def run(cookie: str, csrf: str) -> None:
                try:
                    _save(root, cookie, csrf)
                except BaseException as exc:  # pragma: no cover - assertion aid
                    errors.append(exc)

            with patch.object(session_material, "_write_generation_file", side_effect=delayed_write):
                threads = [
                    threading.Thread(target=run, args=("JWT_WEB=first", "csrf-first")),
                    threading.Thread(target=run, args=("JWT_WEB=second", "csrf-second")),
                ]
                for thread in threads:
                    thread.start()
                for thread in threads:
                    thread.join(timeout=3)

            self.assertFalse(errors)
            self.assertTrue(all(not thread.is_alive() for thread in threads))
            token_dir = root / ".garmin_tokens"
            current = (token_dir / session_material.CURRENT_FILE).read_text().strip()
            generation = token_dir / session_material.GENERATIONS_DIR / current
            pair = (
                (generation / "web_cookie.txt").read_text().strip(),
                (generation / "csrf.txt").read_text().strip(),
            )
            self.assertIn(pair, {("JWT_WEB=first", "csrf-first"), ("JWT_WEB=second", "csrf-second")})

    def test_startup_cleanup_removes_temps_and_orphan_generations(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _save(root, "JWT_WEB=kept", "csrf-kept")
            token_dir = root / ".garmin_tokens"
            current = (token_dir / session_material.CURRENT_FILE).read_text().strip()
            orphan = token_dir / session_material.GENERATIONS_DIR / "orphan-generation"
            orphan.mkdir(parents=True)
            (orphan / "web_cookie.txt").write_text("JWT_WEB=orphan\n")
            (token_dir / ".web_cookie.txt.crashed.tmp").write_text("partial")
            (token_dir / session_material.GENERATIONS_DIR / ".pointer.tmp").write_text("partial")

            session_material.cleanup_session_material(root)

            self.assertTrue((token_dir / session_material.GENERATIONS_DIR / current).exists())
            self.assertFalse(orphan.exists())
            self.assertFalse((token_dir / ".web_cookie.txt.crashed.tmp").exists())
            self.assertFalse((token_dir / session_material.GENERATIONS_DIR / ".pointer.tmp").exists())

    def test_legacy_pair_is_read_and_migrated_on_first_write(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            token_dir = root / ".garmin_tokens"
            token_dir.mkdir()
            (token_dir / "web_cookie.txt").write_text("JWT_WEB=legacy\n")
            (token_dir / "csrf.txt").write_text("csrf-legacy\n")

            with patch.object(garmin_auth, "TOKEN_DIR", token_dir), patch.object(
                garmin_auth, "COOKIE_FILE", token_dir / "web_cookie.txt"
            ), patch.object(garmin_auth, "CSRF_FILE", token_dir / "csrf.txt"):
                auth = garmin_auth._read_existing()

            self.assertIsNotNone(auth)
            assert auth is not None
            self.assertEqual((auth.cookie_header, auth.csrf_token), ("JWT_WEB=legacy", "csrf-legacy"))

            _save(root, "JWT_WEB=migrated", "csrf-migrated")
            current = (token_dir / session_material.CURRENT_FILE).read_text().strip()
            generation = token_dir / session_material.GENERATIONS_DIR / current
            self.assertEqual((generation / "web_cookie.txt").read_text(), "JWT_WEB=migrated\n")
            self.assertEqual((generation / "csrf.txt").read_text(), "csrf-migrated\n")
            self.assertFalse((token_dir / "web_cookie.txt").exists())
            self.assertFalse((token_dir / "csrf.txt").exists())

    def test_automatic_refresh_uses_the_same_generation_writer(self) -> None:
        with TemporaryDirectory() as tmp:
            token_dir = Path(tmp) / ".garmin_tokens"
            auth = garmin_auth.GarminWebAuth(
                "JWT_WEB=refresh", "csrf-refresh", "browser", 1
            )
            with patch.object(garmin_auth, "TOKEN_DIR", token_dir):
                garmin_auth.save_web_auth(auth)

            current = (token_dir / session_material.CURRENT_FILE).read_text().strip()
            generation = token_dir / session_material.GENERATIONS_DIR / current
            self.assertEqual((generation / "web_cookie.txt").read_text(), "JWT_WEB=refresh\n")
            self.assertEqual((generation / "csrf.txt").read_text(), "csrf-refresh\n")

    def test_incomplete_current_generation_never_mixes_with_legacy_files(self) -> None:
        with TemporaryDirectory() as tmp:
            token_dir = Path(tmp) / ".garmin_tokens"
            generation = token_dir / session_material.GENERATIONS_DIR / "generation-broken"
            generation.mkdir(parents=True)
            (generation / "web_cookie.txt").write_text("JWT_WEB=current\n")
            (token_dir / "current").write_text("generation-broken\n")
            (token_dir / "web_cookie.txt").write_text("JWT_WEB=legacy\n")
            (token_dir / "csrf.txt").write_text("csrf-legacy\n")

            self.assertIsNone(session_material.read_session_material(token_dir))

    def test_subprocess_killed_after_second_import_switch_keeps_a_complete_pair(self) -> None:
        script = r"""
import os
from pathlib import Path
import signal
import sys

from ai_caddie.connectors.session_material import save_garmin_cn_web_session

root = Path(sys.argv[1])
save_garmin_cn_web_session(
    web_session_header="Cookie: JWT_WEB=A",
    anti_forgery_value="csrf-A",
    root=root,
)

def kill_on_switch(_source, _destination):
    os.kill(os.getpid(), signal.SIGKILL)

os.replace = kill_on_switch
save_garmin_cn_web_session(
    web_session_header="Cookie: JWT_WEB=B",
    anti_forgery_value="csrf-B",
    root=root,
)
"""
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            completed = subprocess.run(
                [sys.executable, "-c", script, str(root)],
                cwd=Path(__file__).resolve().parents[1],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(completed.returncode, -signal.SIGKILL, completed.stderr)

            with patch.object(garmin_auth, "TOKEN_DIR", root / ".garmin_tokens"):
                auth = garmin_auth._read_existing()
            self.assertIsNotNone(auth)
            assert auth is not None
            self.assertIn(
                (auth.cookie_header, auth.csrf_token),
                {("JWT_WEB=A", "csrf-A"), ("JWT_WEB=B", "csrf-B")},
            )


if __name__ == "__main__":
    unittest.main()
