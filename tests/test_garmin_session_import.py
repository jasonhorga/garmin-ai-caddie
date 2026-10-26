from __future__ import annotations

import errno
import json
import os
import stat
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest import mock

from ai_caddie.connectors import session_material
from ai_caddie.connectors.session_material import save_garmin_cn_web_session


SECRET_VALUES = ("JWT_WEB=abc123", "csrf-secret-value", ".garmin_tokens")


def _existing_session(root: Path) -> tuple[Path, Path, Path]:
    token_dir = root / ".garmin_tokens"
    token_dir.mkdir(mode=0o700)
    cookie = token_dir / "web_cookie.txt"
    csrf = token_dir / "csrf.txt"
    cookie.write_text("JWT_WEB=existing-cookie\n", encoding="utf-8")
    csrf.write_text("existing-csrf\n", encoding="utf-8")
    return token_dir, cookie, csrf


def _save_replacement(root: Path) -> dict:
    return save_garmin_cn_web_session(
        web_session_header="Cookie: JWT_WEB=replacement",
        anti_forgery_value="connect-csrf-token: replacement-csrf",
        root=root,
    )


def _current_generation(token_dir: Path) -> Path:
    name = (token_dir / session_material.CURRENT_FILE).read_text(encoding="ascii").strip()
    return token_dir / session_material.GENERATIONS_DIR / name


class GarminSessionImportTests(unittest.TestCase):
    def test_saves_manual_web_session_material_without_echoing_values(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)

            result = save_garmin_cn_web_session(
                web_session_header="Cookie: JWT_WEB=abc123; GARMIN=two",
                anti_forgery_value="connect-csrf-token: csrf-secret-value",
                root=root,
            )

            session_dir = root / ".garmin_tokens"
            generation = _current_generation(session_dir)
            web_session_file = generation / "web_cookie.txt"
            anti_forgery_file = generation / "csrf.txt"
            status_file = root / "data" / "sync" / "garmin_cn_status.json"

            self.assertEqual(result["schema"], "ai-caddie-garmin-session-import-v1")
            self.assertEqual(result["connector"], "garmin_cn_web_session")
            self.assertEqual(result["state"], "stored")
            self.assertEqual(result["sessionFieldCount"], 2)
            self.assertTrue(result["antiForgeryPresent"])
            self.assertEqual(result["source"], "manual_paste")
            self.assertIn("ios_web_login", result["acceptedSources"])
            status = json.loads(status_file.read_text(encoding="utf-8"))
            self.assertEqual(status["state"], "no_data")
            self.assertEqual(status["errorCode"], "session_stored")
            self.assertEqual(web_session_file.read_text(encoding="utf-8").strip(), "JWT_WEB=abc123; GARMIN=two")
            self.assertEqual(anti_forgery_file.read_text(encoding="utf-8").strip(), "csrf-secret-value")
            self.assertEqual(stat.S_IMODE(session_dir.stat().st_mode), 0o700)
            self.assertEqual(stat.S_IMODE(web_session_file.stat().st_mode), 0o600)
            self.assertEqual(stat.S_IMODE(anti_forgery_file.stat().st_mode), 0o600)

            response_text = json.dumps(result, ensure_ascii=False)
            for value in SECRET_VALUES:
                self.assertNotIn(value, response_text)

    def test_accepts_replaceable_ios_session_material_source_without_changing_secret_storage(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)

            result = save_garmin_cn_web_session(
                web_session_header="Cookie: JWT_WEB=abc123",
                anti_forgery_value="connect-csrf-token: csrf-secret-value",
                source="ios_keychain_replay",
                root=root,
            )

        self.assertEqual(result["source"], "ios_keychain_replay")
        self.assertEqual(result["sessionFieldCount"], 1)
        self.assertTrue(result["antiForgeryPresent"])
        response_text = json.dumps(result, ensure_ascii=False)
        for value in SECRET_VALUES:
            self.assertNotIn(value, response_text)

    def test_rejects_empty_or_multiline_session_values(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)

            with self.assertRaises(ValueError):
                save_garmin_cn_web_session(
                    web_session_header="",
                    anti_forgery_value="csrf-secret-value",
                    root=root,
                )
            with self.assertRaises(ValueError):
                save_garmin_cn_web_session(
                    web_session_header="JWT_WEB=abc123\nOther=value",
                    anti_forgery_value="csrf-secret-value",
                    root=root,
                )
            with self.assertRaises(ValueError):
                save_garmin_cn_web_session(
                    web_session_header="JWT_WEB=abc123",
                    anti_forgery_value="csrf-secret-value",
                    source="username_password",
                    root=root,
                )

            self.assertFalse((root / ".garmin_tokens").exists())

    def test_failed_second_file_write_keeps_previous_session_without_temp_files(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            token_dir, cookie, csrf = _existing_session(root)
            before = (cookie.read_bytes(), csrf.read_bytes())
            failed: list[Path] = []
            real_write = session_material._write_generation_file

            def write(path, content):
                if path.name == "csrf.txt" and not failed:
                    failed.append(Path(path))
                    raise OSError(errno.ENOSPC, "No space left on device")
                return real_write(path, content)

            with mock.patch.object(session_material, "_write_generation_file", side_effect=write):
                with self.assertRaises(OSError):
                    _save_replacement(root)

            self.assertEqual([path.name for path in failed], ["csrf.txt"])
            self.assertEqual((cookie.read_bytes(), csrf.read_bytes()), before)
            self.assertEqual(
                sorted(path.name for path in token_dir.iterdir()),
                ["csrf.txt", "web_cookie.txt"],
            )

    def test_rollback_failure_on_one_file_still_restores_the_other_and_raises_original(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            token_dir, cookie, csrf = _existing_session(root)
            csrf_before = csrf.read_bytes()

            def status_failure(**_kwargs):
                # Make the cookie path unrestorable (a directory), then fail the status write.
                cookie.unlink()
                cookie.mkdir()
                raise RuntimeError("status store unavailable")

            with mock.patch.object(session_material, "write_connector_status", side_effect=status_failure):
                with self.assertRaises(Exception) as caught:
                    _save_replacement(root)

            self.assertIs(type(caught.exception), RuntimeError)
            self.assertEqual(str(caught.exception), "status store unavailable")
            self.assertTrue(cookie.is_dir())
            self.assertEqual(csrf.read_bytes(), csrf_before)
            self.assertFalse((token_dir / session_material.CURRENT_FILE).exists())
            self.assertFalse((token_dir / session_material.GENERATIONS_DIR).exists())

    def test_status_failure_removes_files_that_did_not_exist_before(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            with mock.patch.object(
                session_material,
                "write_connector_status",
                side_effect=RuntimeError("status store unavailable"),
            ):
                with self.assertRaises(RuntimeError):
                    _save_replacement(root)

            self.assertEqual(list((root / ".garmin_tokens").iterdir()), [])

    def test_session_files_are_created_private_and_installed_by_replace(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            token_dir, cookie, csrf = _existing_session(root)
            cookie.chmod(0o644)
            csrf.chmod(0o644)
            real_open = os.open
            created_modes: list[int] = []
            installed: dict[str, int] = {}

            def open_(path, flags, mode=0o777, *args, **kwargs):
                if flags & os.O_CREAT:
                    created_modes.append(mode)
                return real_open(path, flags, mode, *args, **kwargs)

            with mock.patch("os.open", side_effect=open_):
                _save_replacement(root)

            self.assertEqual(created_modes, [0o600, 0o600, 0o600])
            generation = _current_generation(token_dir)
            self.assertEqual(stat.S_IMODE((generation / "web_cookie.txt").stat().st_mode), 0o600)
            self.assertEqual(stat.S_IMODE((generation / "csrf.txt").stat().st_mode), 0o600)
            self.assertEqual((generation / "web_cookie.txt").read_text(encoding="utf-8"), "JWT_WEB=replacement\n")
            self.assertEqual((generation / "csrf.txt").read_text(encoding="utf-8"), "replacement-csrf\n")
            self.assertEqual(
                sorted(path.name for path in token_dir.iterdir()),
                [session_material.CURRENT_FILE, session_material.GENERATIONS_DIR],
            )
            self.assertEqual(stat.S_IMODE((token_dir / session_material.CURRENT_FILE).stat().st_mode), 0o600)
            self.assertEqual(
                sorted(path.name for path in generation.iterdir()),
                ["csrf.txt", "web_cookie.txt"],
            )


if __name__ == "__main__":
    unittest.main()
