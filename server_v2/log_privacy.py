"""Remove private identities, credentials and local paths at service log exits.

Diagnostic codes, public course ids and numeric values survive at every level.
Exception payloads remain untrusted; retain their types and frame locations.
"""
from collections.abc import Mapping
import logging
import os
from pathlib import Path
import re
import traceback

from ai_caddie.core.request_timing import redact_url, route_template

_REDACTED = "[redacted]"
_STANDARD = frozenset(logging.makeLogRecord({}).__dict__) | {"message", "asctime", "_privacy_sanitized"}
_SENSITIVE_KEY = re.compile(
    r"(?:player(?:id|name)?|round(?:id)?|displayname|nickname|.*token|cookie|csrf|authorization|.*secret|apikey)",
    re.IGNORECASE,
)
_IDENTITY = re.compile(
    r"(?i)\b(player_?id|round_?id|player_?name|display_?name|nickname|player|round|"
    r"[\w-]*token|cookie|csrf|authorization|[\w-]*secret|api_?key)([\"']?\s*[:=]\s*)"
    r"(\[redacted\]|\"[^\"\n]*\"|'[^'\n]*'|[^\s,;&#\)\}\]]+)"
)
_URL = re.compile(r"https?://[^\s\"'<>;,]+|(?<![\w/])/(?:api|p)/[^\s\"'<>;,]+")
_PRIVATE_PATH = re.compile(r"https?://[^\s\"'<>;,\)]+|(?<![\w/])(?:[A-Za-z]:[\\/]|/|\bdata/)[^\s\"'<>;,\)]+")
_FRAME = re.compile(r'^(\s*File ")(.+)(", line \d+, in .+)$')


def _text(value: str) -> str:
    # URL helpers expect ONE URL; applying them to a whole log line eats fields
    # after a share capability or query parameter.
    value = _URL.sub(lambda match: redact_url(match[0]), value)
    def identity(match):
        original = match[3]
        quote = original[0] if original[0] in "\"'" else ""
        return match[1] + match[2] + quote + _REDACTED + quote

    value = _IDENTITY.sub(identity, value)
    value = re.sub(r"(?i)\b(player|round)\s+(?:id\s+)?[^\s,;]+", r"\1=" + _REDACTED, value)
    value = re.sub(r"(?i)\bbearer\s+[^\s,;]+", "Bearer " + _REDACTED, value)

    def path(match):
        candidate = match[0]
        if candidate.startswith(("https://", "http://")):
            return candidate
        if candidate.startswith("/api/") and (
            route_template(candidate) == candidate or ":token" in candidate
        ):
            return candidate
        return _REDACTED

    return _PRIVATE_PATH.sub(path, value)


def _context(value, key=""):
    if _SENSITIVE_KEY.fullmatch(re.sub(r"[^a-zA-Z0-9]", "", str(key))):
        return _REDACTED
    if isinstance(value, Mapping):
        return {key: _context(item, key) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_context(item) for item in value]
    if isinstance(value, str):
        return _text(value)
    if isinstance(value, BaseException):
        return _exception_summary(value)
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return _REDACTED


def _exception_summary(exc):
    detail = _REDACTED
    if isinstance(exc, OSError) and isinstance(exc.errno, int):
        # Use the OS's public diagnostic, never a filename or custom strerror.
        detail = f"[Errno {exc.errno}] {os.strerror(exc.errno)}"
    return f"{type(exc).__name__}: {detail}"


def _clean_frames(stack):
    for frame in stack:
        frame.filename = Path(frame.filename).name
        frame._line = ""


def _stack_text(value):
    lines = []
    for line in value.splitlines():
        frame = _FRAME.fullmatch(line)
        if frame:
            lines.append(frame[1] + Path(frame[2]).name + frame[3])
        elif line == "Stack (most recent call last):":
            lines.append(line)
    return "\n".join(lines)


def _exception_text(exc_info) -> str:
    trace = traceback.TracebackException(*exc_info, capture_locals=False)

    def clean(item, exc):
        item._str = _exception_summary(exc).partition(": ")[2]
        item.__notes__ = None
        if item.exc_type is not None and issubclass(item.exc_type, SyntaxError):
            item.filename = _REDACTED
            item.text = None
            item.msg = _REDACTED
        _clean_frames(item.stack)
        for child, cause in ((item.__cause__, exc.__cause__), (item.__context__, exc.__context__)):
            if child is not None:
                clean(child, cause)
        for child, cause in zip(item.exceptions or (), getattr(exc, "exceptions", ())):
            clean(child, cause)

    clean(trace, exc_info[1])
    return "".join(trace.format()).rstrip()


def _arguments(value):
    # Keep native numeric and tuple-like arguments intact for %-formatting.
    # Only exception arguments need a replacement before getMessage().
    if isinstance(value, BaseException):
        return _exception_summary(value)
    if isinstance(value, Mapping):
        return {key: _arguments(item) for key, item in value.items()}
    if isinstance(value, tuple) and not hasattr(value, "_fields"):
        return tuple(_arguments(item) for item in value)
    return value


class LogPrivacyFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            return self._filter(record)
        except Exception:
            # Logging is diagnostic: even malformed formatting or hostile values
            # must neither leak a partially processed record nor break business work.
            record.msg = "log record redaction failed"
            record.args = ()
            record.exc_info = record.exc_text = record.stack_info = None
            record.pathname = _REDACTED
            record.__dict__.pop("message", None)
            for key in tuple(record.__dict__):
                if key not in _STANDARD:
                    record.__dict__[key] = _REDACTED
            record._privacy_sanitized = True
            return True

    def _filter(self, record: logging.LogRecord) -> bool:
        if not record.name.startswith(("server_v2", "ai_caddie", "uvicorn.error")):
            return True
        record.args = _arguments(record.args)
        record.msg = _text(record.getMessage())
        record.args = ()
        record.__dict__.pop("message", None)
        for key in tuple(record.__dict__):
            if key not in _STANDARD:
                record.__dict__[key] = _context(record.__dict__[key], key)
        if record.exc_info:
            record.exc_text = _exception_text(record.exc_info)
            record.exc_info = None
        elif record.exc_text and not getattr(record, "_privacy_sanitized", False):
            record.exc_text = _REDACTED
        if record.stack_info:
            record.stack_info = _stack_text(record.stack_info)
        record._privacy_sanitized = True
        record.pathname = Path(record.pathname).name
        return True


def protect_handler(handler: logging.Handler) -> None:
    if not any(isinstance(item, LogPrivacyFilter) for item in handler.filters):
        handler.addFilter(LogPrivacyFilter())


def protect_future_handlers() -> None:
    """Protect handlers attached after startup, including propagate=False exits."""
    original = logging.Logger.addHandler
    if getattr(original, "_privacy_guard", False):
        return

    def add_handler(logger, handler):
        if logger.name.startswith(("server_v2", "ai_caddie", "uvicorn")):
            protect_handler(handler)
        return original(logger, handler)

    add_handler._privacy_guard = True
    logging.Logger.addHandler = add_handler
