# Owner Decision Pager Telegram Setup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build one auditable homeserver script that securely captures a Telegram Bot Token, verifies the Bot, pairs exactly one private Owner chat with a nonce, writes a `0600` configuration file atomically, and sends a test notification.

**Architecture:** A standalone Python 3 script uses only the standard library. Pure helper functions handle update matching, API error redaction, and atomic secret-file writes so they can be tested without Telegram. The interactive `main()` uses `getpass`, a one-time `/start <nonce>` deep link, Telegram long polling, and an injected HTTP client boundary.

**Tech Stack:** Python 3 standard library, pytest, Telegram Bot HTTP API, POSIX file permissions.

---

## File structure

- Create `scripts/__init__.py`: makes setup helpers importable by pytest.
- Create `scripts/setup_codex_owner_pager_telegram.py`: interactive credential and Owner-chat pairing script.
- Create `tests/test_setup_codex_owner_pager_telegram.py`: unit tests for pairing, redaction, atomic persistence, and orchestration.

The script writes runtime secrets only to `~/.config/codex-owner-pager/telegram.json`; that file is outside the repository and is never created by tests except under `tmp_path`.

### Task 1: Specify pairing and secret persistence behavior

**Files:**
- Create: `scripts/__init__.py`
- Create: `tests/test_setup_codex_owner_pager_telegram.py`
- Test: `tests/test_setup_codex_owner_pager_telegram.py`

- [ ] **Step 1: Create the importable scripts package**

```python
"""Repository-maintained operator scripts."""
```

- [ ] **Step 2: Write failing tests for exact private-chat pairing**

```python
from scripts.setup_codex_owner_pager_telegram import find_pairing_chat


def test_find_pairing_chat_accepts_only_matching_private_start():
    updates = [
        {"update_id": 1, "message": {"text": "/start wanted", "chat": {"id": -10, "type": "group"}}},
        {"update_id": 2, "message": {"text": "/start wrong", "chat": {"id": 20, "type": "private"}}},
        {
            "update_id": 3,
            "message": {
                "text": "/start wanted",
                "chat": {"id": 30, "type": "private", "username": "owner"},
                "from": {"id": 30, "is_bot": False},
            },
        },
    ]

    assert find_pairing_chat(updates, "wanted") == {
        "chat_id": 30,
        "username": "owner",
        "update_id": 3,
    }
```

- [ ] **Step 3: Write failing tests for atomic `0600` persistence**

```python
import json
import stat

from scripts.setup_codex_owner_pager_telegram import write_private_config


def test_write_private_config_is_atomic_and_owner_only(tmp_path):
    target = tmp_path / "private" / "telegram.json"
    write_private_config(
        target,
        {"bot_token": "123:secret", "owner_chat_id": 30, "bot_username": "pager_bot"},
    )

    assert json.loads(target.read_text()) == {
        "bot_token": "123:secret",
        "owner_chat_id": 30,
        "bot_username": "pager_bot",
    }
    assert stat.S_IMODE(target.stat().st_mode) == 0o600
    assert stat.S_IMODE(target.parent.stat().st_mode) == 0o700
    assert list(target.parent.glob("*.tmp")) == []
```

- [ ] **Step 4: Write a failing test that API failures never expose the Token**

```python
import pytest

from scripts.setup_codex_owner_pager_telegram import TelegramSetupError, telegram_call


def test_telegram_call_redacts_token_from_transport_errors():
    token = "123456:super-secret-token"

    def failing_open(_request, timeout):
        raise OSError(f"failed https://api.telegram.org/bot{token}/getMe")

    with pytest.raises(TelegramSetupError) as error:
        telegram_call(token, "getMe", opener=failing_open)

    assert token not in str(error.value)
    assert "Telegram request failed" in str(error.value)
```

- [ ] **Step 5: Run tests and verify RED**

Run:

```bash
pytest -q tests/test_setup_codex_owner_pager_telegram.py
```

Expected: collection fails with `ModuleNotFoundError` for `scripts.setup_codex_owner_pager_telegram`, proving the implementation does not exist yet.

- [ ] **Step 6: Commit the failing specification**

```bash
git add scripts/__init__.py tests/test_setup_codex_owner_pager_telegram.py
git commit -m "test: specify Telegram owner pager setup"
```

### Task 2: Implement the minimal secure setup helpers

**Files:**
- Create: `scripts/setup_codex_owner_pager_telegram.py`
- Test: `tests/test_setup_codex_owner_pager_telegram.py`

- [ ] **Step 1: Implement the exception and Telegram API boundary**

```python
class TelegramSetupError(RuntimeError):
    """A user-safe setup error that never includes the Bot Token."""


def telegram_call(token, method, payload=None, *, opener=urlopen, timeout=30):
    encoded = urlencode(payload or {}).encode("utf-8")
    request = Request(
        f"https://api.telegram.org/bot{token}/{method}",
        data=encoded,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with opener(request, timeout=timeout) as response:
            result = json.load(response)
    except Exception as exc:
        raise TelegramSetupError(f"Telegram request failed for {method}") from exc
    if not result.get("ok"):
        description = str(result.get("description") or "unknown Telegram error")
        raise TelegramSetupError(f"Telegram rejected {method}: {description}")
    return result.get("result")
```

The implementation must not log `request.full_url`, the original exception, or the Token.

- [ ] **Step 2: Implement exact pairing selection**

```python
def find_pairing_chat(updates, nonce):
    expected = f"/start {nonce}"
    for update in updates:
        message = update.get("message") or {}
        chat = message.get("chat") or {}
        sender = message.get("from") or {}
        if (
            message.get("text") == expected
            and chat.get("type") == "private"
            and sender.get("is_bot") is False
            and chat.get("id") == sender.get("id")
        ):
            return {
                "chat_id": int(chat["id"]),
                "username": chat.get("username"),
                "update_id": int(update["update_id"]),
            }
    return None
```

- [ ] **Step 3: Implement atomic private persistence**

```python
def write_private_config(path, values):
    path = Path(path).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(path.parent, 0o700)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(values, handle, ensure_ascii=False, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        os.chmod(path, 0o600)
    except BaseException:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise
```

- [ ] **Step 4: Run focused tests and verify GREEN**

Run:

```bash
pytest -q tests/test_setup_codex_owner_pager_telegram.py
```

Expected: all helper tests pass.

- [ ] **Step 5: Commit the helpers**

```bash
git add scripts/setup_codex_owner_pager_telegram.py tests/test_setup_codex_owner_pager_telegram.py
git commit -m "feat: add secure Telegram pager setup helpers"
```

### Task 3: Implement and verify the interactive setup flow

**Files:**
- Modify: `scripts/setup_codex_owner_pager_telegram.py`
- Modify: `tests/test_setup_codex_owner_pager_telegram.py`

- [ ] **Step 1: Write a failing orchestration test**

```python
import json
import stat

from scripts.setup_codex_owner_pager_telegram import run_setup


def test_run_setup_pairs_private_owner_and_writes_config(tmp_path, capsys):
    calls = []

    def fake_api(_token, method, payload=None):
        calls.append((method, payload or {}))
        if method == "getMe":
            return {"id": 99, "is_bot": True, "username": "pager_bot"}
        if method == "getUpdates":
            return [
                {
                    "update_id": 7,
                    "message": {
                        "text": "/start fixed-nonce",
                        "chat": {"id": 30, "type": "private", "username": "owner"},
                        "from": {"id": 30, "is_bot": False},
                    },
                }
            ]
        if method == "sendMessage":
            return {"message_id": 100}
        raise AssertionError(method)

    target = tmp_path / "telegram.json"
    result = run_setup(
        config_path=target,
        token_reader=lambda _prompt: "123:fake",
        api=fake_api,
        nonce_factory=lambda: "fixed-nonce",
        output=print,
    )

    assert result == target
    assert calls == [
        ("getMe", {}),
        ("getUpdates", {"offset": 0, "timeout": 20, "allowed_updates": '["message"]'}),
        ("sendMessage", {"chat_id": 30, "text": "Codex Owner Pager 配置成功。"}),
    ]
    assert json.loads(target.read_text()) == {
        "bot_id": 99,
        "bot_token": "123:fake",
        "bot_username": "pager_bot",
        "owner_chat_id": 30,
        "owner_username": "owner",
    }
    assert stat.S_IMODE(target.stat().st_mode) == 0o600
    stdout = capsys.readouterr().out
    assert "https://t.me/pager_bot?start=fixed-nonce" in stdout
    assert "123:fake" not in stdout
```

- [ ] **Step 2: Run the orchestration test and verify RED**

Run:

```bash
pytest -q tests/test_setup_codex_owner_pager_telegram.py -k interactive
```

Expected: FAIL because `run_setup` has not been implemented.

- [ ] **Step 3: Implement `run_setup` and `main`**

```python
DEFAULT_CONFIG_PATH = Path("~/.config/codex-owner-pager/telegram.json").expanduser()


def run_setup(
    *,
    config_path=DEFAULT_CONFIG_PATH,
    token_reader=getpass.getpass,
    api=telegram_call,
    nonce_factory=lambda: secrets.token_urlsafe(18),
    output=print,
):
    token = token_reader("Telegram Bot Token: ").strip()
    if not token or any(character.isspace() for character in token):
        raise TelegramSetupError("Bot Token 不能为空或包含空白字符")

    bot = api(token, "getMe") or {}
    username = str(bot.get("username") or "").strip()
    if not bot.get("is_bot") or not username:
        raise TelegramSetupError("Token 未返回有效的 Telegram Bot")

    nonce = nonce_factory()
    output(f"请在手机打开并点击 Start：https://t.me/{username}?start={nonce}")
    offset = 0
    owner = None
    for _attempt in range(6):
        updates = api(
            token,
            "getUpdates",
            {"offset": offset, "timeout": 20, "allowed_updates": '["message"]'},
        ) or []
        if updates:
            offset = max(int(update.get("update_id", 0)) for update in updates) + 1
        owner = find_pairing_chat(updates, nonce)
        if owner is not None:
            break
    if owner is None:
        raise TelegramSetupError("120 秒内未收到匹配的私聊 Start，请重新运行")

    api(
        token,
        "sendMessage",
        {"chat_id": owner["chat_id"], "text": "Codex Owner Pager 配置成功。"},
    )
    target = Path(config_path).expanduser()
    write_private_config(
        target,
        {
            "bot_id": int(bot["id"]),
            "bot_token": token,
            "bot_username": username,
            "owner_chat_id": owner["chat_id"],
            "owner_username": owner["username"],
        },
    )
    output(f"配置已安全保存：{target}")
    return target


def main():
    try:
        run_setup()
    except KeyboardInterrupt:
        print("\n已取消，未写入配置。", file=sys.stderr)
        return 130
    except TelegramSetupError as exc:
        print(f"配置失败：{exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run focused tests and verify GREEN**

Run:

```bash
pytest -q tests/test_setup_codex_owner_pager_telegram.py
```

Expected: all tests pass with no warnings.

- [ ] **Step 5: Make the script executable and verify syntax**

Run:

```bash
chmod 755 scripts/setup_codex_owner_pager_telegram.py
python3 -m py_compile scripts/setup_codex_owner_pager_telegram.py
```

Expected: exit code 0 and no output.

- [ ] **Step 6: Run repository security checks for accidental Token material**

Run:

```bash
rg -n "[0-9]{6,}:[A-Za-z0-9_-]{20,}" scripts tests docs/superpowers/plans/2026-07-18-owner-decision-pager-telegram-setup.md
```

Expected: no real Token matches. Any deliberately fake fixture must use an obviously invalid short value.

- [ ] **Step 7: Commit the interactive flow**

```bash
git add scripts/setup_codex_owner_pager_telegram.py tests/test_setup_codex_owner_pager_telegram.py
git commit -m "feat: pair Telegram owner pager securely"
```

### Task 4: Install and hand off the verified script

**Files:**
- Source: `scripts/setup_codex_owner_pager_telegram.py`
- Install: `/home/ubuntu/.local/bin/setup-codex-owner-pager-telegram`

- [ ] **Step 1: Run all focused verification**

Run:

```bash
pytest -q tests/test_setup_codex_owner_pager_telegram.py
python3 -m py_compile scripts/setup_codex_owner_pager_telegram.py
git diff --check
```

Expected: tests pass, compilation succeeds, and diff check is clean.

- [ ] **Step 2: Install the exact verified source**

Run:

```bash
install -m 755 scripts/setup_codex_owner_pager_telegram.py /home/ubuntu/.local/bin/setup-codex-owner-pager-telegram
```

Expected: `/home/ubuntu/.local/bin/setup-codex-owner-pager-telegram` exists and is executable.

- [ ] **Step 3: Verify installed source identity**

Run:

```bash
sha256sum scripts/setup_codex_owner_pager_telegram.py /home/ubuntu/.local/bin/setup-codex-owner-pager-telegram
```

Expected: both SHA-256 hashes are identical.

- [ ] **Step 4: Provide the Owner command**

```bash
/home/ubuntu/.local/bin/setup-codex-owner-pager-telegram
```

The Owner enters the Bot Token at the hidden prompt, opens the printed Telegram deep link, presses Start, and confirms receipt of the test message. No Token is sent through Codex chat.
