"""Small request-scoped timing hooks for startup and package diagnostics.

Timing is intentionally response metadata and structured logging only.  It never
contains player data, provider credentials, or response bodies, and it is safe to
omit when a builder is called directly by a unit test.
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
import json
import logging
import os
from pathlib import Path
import queue
import re
import threading
import time
import uuid
from typing import Any, Callable, Iterator
from zoneinfo import ZoneInfo


_REQUEST_ID = re.compile(r"^[A-Za-z0-9._:-]{1,96}$")
_CURRENT: ContextVar["RequestTiming | None"] = ContextVar("ai_caddie_request_timing", default=None)
logger = logging.getLogger("server_v2.timing")

_SENSITIVE_QUERY_UNQUOTED = re.compile(
    r"([?&](?:key|token|access_token|refresh_token|admin_token|authorization|api_key|member_token|share_token|secret)=)[^&#]*",
    re.IGNORECASE,
)
_SHARE_PATH = re.compile(r"(/api/v2/share/)[A-Za-z0-9_-]+(?=($|[/?&#]))")
_MEMBER_PATH = re.compile(r"(/p/)[A-Za-z0-9_-]+(?=($|[/?&#]))")

_BEIJING = ZoneInfo("Asia/Shanghai")
_TIMING_FILE = re.compile(r"^(?P<kind>client-)?(?P<day>\d{4}-\d{2}-\d{2})\.jsonl$")
_TIMING_QUEUE: queue.Queue[tuple[Path, str, Path, date] | None] = queue.Queue(maxsize=4096)
_TIMING_WRITER_LOCK = threading.Lock()
_TIMING_WRITER_STARTED = False
_TIMING_CLEANED: set[tuple[Path, date]] = set()
# Tests may inject a private root without setting the deployment environment.  ``None`` means
# use AI_CADDIE_PRIVATE_ROOT; with neither configured, fixture/unit requests never create files.
TIMING_ROOT: Path | None = None
TIMING_CLOCK: Callable[[], datetime] | None = None


def redact_url(value: str | None) -> str:
    """Remove capability values from a URL before it reaches logs or timing storage."""
    text = str(value or "")
    text = _SHARE_PATH.sub(r"\1:token", text)
    text = _MEMBER_PATH.sub(r"\1:token", text)
    return _SENSITIVE_QUERY_UNQUOTED.sub(r"\1***", text)


class URLRedactionFilter(logging.Filter):
    """Redact URL-bearing arguments in uvicorn access records in place."""

    def filter(self, record: logging.LogRecord) -> bool:
        args = record.args
        if isinstance(args, tuple):
            record.args = tuple(redact_url(item) if isinstance(item, str) else item for item in args)
        elif isinstance(args, list):
            record.args = [redact_url(item) if isinstance(item, str) else item for item in args]
        elif isinstance(args, str):
            record.args = redact_url(args)
        elif not args and isinstance(record.msg, str):
            record.msg = redact_url(record.msg)
        return True


def _beijing_now() -> datetime:
    return datetime.now(_BEIJING)


def _now() -> datetime:
    value = TIMING_CLOCK() if TIMING_CLOCK is not None else _beijing_now()
    if value.tzinfo is None:
        return value.replace(tzinfo=_BEIJING)
    return value.astimezone(_BEIJING)


def timing_root() -> Path | None:
    """Return the private timing root, or ``None`` in fixture/open unit mode."""
    if TIMING_ROOT is not None:
        return Path(TIMING_ROOT)
    configured = os.environ.get("AI_CADDIE_PRIVATE_ROOT", "").strip()
    return Path(configured) if configured else None


def timing_path(day: date, *, client: bool = False, root: Path | str | None = None) -> Path:
    base = Path(root) if root is not None else timing_root()
    if base is None:
        raise RuntimeError("timing persistence has no private root")
    name = f"{'client-' if client else ''}{day.isoformat()}.jsonl"
    return base / "timing" / name


def template_path(path: str) -> str:
    """Strip query data and replace numeric URL path segments with ``{id}``."""
    clean = redact_url(path).split("?", 1)[0].split("#", 1)[0] or "/"
    segments = clean.split("/")
    return "/".join("{id}" if re.fullmatch(r"\d+", segment or "") else segment for segment in segments)


def _cleanup_old_files(root: Path, today: date) -> None:
    timing_dir = root / "timing"
    try:
        files = tuple(timing_dir.iterdir())
    except (FileNotFoundError, OSError):
        return
    cutoff = today - timedelta(days=13)  # fourteen calendar dates, including today
    for path in files:
        match = _TIMING_FILE.fullmatch(path.name)
        if not match:
            continue
        try:
            file_day = date.fromisoformat(match.group("day"))
        except ValueError:
            continue
        if file_day < cutoff:
            try:
                path.unlink()
            except (FileNotFoundError, OSError):
                logger.warning("request timing cleanup failed path=%s", path, exc_info=True)


def _timing_writer() -> None:
    cleaned: set[tuple[Path, date]] = set()
    while True:
        item = _TIMING_QUEUE.get()
        try:
            if item is None:
                return
            path, line, root, day = item
            key = (root, day)
            if key not in cleaned:
                _cleanup_old_files(root, day)
                cleaned.add(key)
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as handle:
                handle.write(line)
        except Exception:
            # Timing must never turn an otherwise healthy API request into a 500.
            logger.warning("request timing persistence failed", exc_info=True)
        finally:
            _TIMING_QUEUE.task_done()


def _ensure_writer() -> None:
    global _TIMING_WRITER_STARTED
    with _TIMING_WRITER_LOCK:
        if _TIMING_WRITER_STARTED:
            return
        thread = threading.Thread(target=_timing_writer, name="request-timing-writer", daemon=True)
        thread.start()
        _TIMING_WRITER_STARTED = True


def initialize_timing_storage() -> None:
    """Start the writer so startup cleanup runs even before the first request."""
    root = timing_root()
    if root is None:
        return
    _ensure_writer()
    today = _now().date()
    with _TIMING_WRITER_LOCK:
        key = (root, today)
        if key in _TIMING_CLEANED:
            return
        _TIMING_CLEANED.add(key)
    _cleanup_old_files(root, today)


def flush_timing_writes() -> None:
    """Test/support hook: wait until all queued timing lines are durable in the process."""
    if _TIMING_WRITER_STARTED:
        _TIMING_QUEUE.join()


def _enqueue_timing(record: dict[str, Any], *, client: bool = False) -> None:
    try:
        root = timing_root()
        if root is None:
            return
        day = _now().date()
        _ensure_writer()
        path = timing_path(day, client=client, root=root)
        line = json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n"
        _TIMING_QUEUE.put_nowait((path, line, root, day))
    except queue.Full:
        logger.warning("request timing persistence queue full; dropping record")
    except Exception:
        logger.warning("request timing persistence enqueue failed", exc_info=True)


def append_client_timing(record: dict[str, Any]) -> None:
    """Queue a sanitized client timing record for the Beijing ingestion date."""
    _enqueue_timing(record, client=True)


def read_timing_rows(root: Path | str | None = None) -> list[dict[str, Any]]:
    """Read server timing rows, skipping malformed or unexpectedly shaped lines."""
    base = Path(root) if root is not None else timing_root()
    if base is None:
        return []
    rows: list[dict[str, Any]] = []
    try:
        files = sorted((base / "timing").glob("????-??-??.jsonl"), reverse=True)
    except OSError:
        return []
    for path in files:
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except (FileNotFoundError, OSError, UnicodeError):
            continue
        for line in lines:
            try:
                value = json.loads(line)
            except (TypeError, ValueError):
                continue
            if isinstance(value, dict) and isinstance(value.get("ts"), str):
                rows.append(value)
    return rows


def request_id(value: str | None = None) -> str:
    candidate = str(value or "").strip()
    return candidate if _REQUEST_ID.fullmatch(candidate) else f"req-{uuid.uuid4().hex}"


@dataclass
class RequestTiming:
    request_id: str
    started: float = field(default_factory=time.perf_counter)
    marks: dict[str, float] = field(default_factory=dict)
    _last: float | None = None

    def mark(self, name: str) -> None:
        clean = re.sub(r"[^A-Za-z0-9_.-]", "_", str(name or "stage"))[:64] or "stage"
        now = time.perf_counter()
        previous = self._last if self._last is not None else self.started
        self.marks[clean] = self.marks.get(clean, 0.0) + max(0.0, (now - previous) * 1000.0)
        self._last = now

    @property
    def total_ms(self) -> float:
        return max(0.0, (time.perf_counter() - self.started) * 1000.0)

    def server_timing(self) -> str:
        # A disconnected request can finish while its worker records a final stage. Snapshot
        # before formatting so that late additions cannot resize a dict being iterated.
        marks = self.marks.copy()
        values = [f"{name};dur={duration:.1f}" for name, duration in marks.items()]
        values.append(f"total;dur={self.total_ms:.1f}")
        return ", ".join(values)

    def finish(self, *, method: str, path: str, status: int) -> None:
        marks = self.marks.copy()
        total_ms = self.total_ms
        safe_path = redact_url(path)
        record: dict[str, Any] | None = None
        try:
            record = {
                "ts": _now().isoformat(timespec="milliseconds"),
                "request_id": self.request_id,
                "method": str(method).upper(),
                "path": template_path(safe_path),
                "status": int(status),
                "total_ms": round(total_ms, 1),
                "stages": {key: round(value, 1) for key, value in marks.items()},
            }
        except Exception:
            logger.warning("request timing record construction failed", exc_info=True)
        logger.info(
            "request_timing request_id=%s method=%s path=%s status=%s total_ms=%.1f stages=%s",
            self.request_id,
            method,
            safe_path,
            status,
            total_ms,
            ";".join(f"{key}:{value:.1f}" for key, value in marks.items()),
        )
        if record is not None:
            try:
                _enqueue_timing(record)
            except Exception:
                # The optional observability path must never alter the business response.
                logger.warning("request timing enqueue failed", exc_info=True)


def current() -> RequestTiming | None:
    return _CURRENT.get()


@contextmanager
def bind(timing: RequestTiming) -> Iterator[RequestTiming]:
    token = _CURRENT.set(timing)
    try:
        yield timing
    finally:
        _CURRENT.reset(token)


def mark(name: str) -> None:
    timing = current()
    if timing is not None:
        timing.mark(name)

