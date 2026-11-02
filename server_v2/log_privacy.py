"""Privacy boundary for service log handlers, including future child loggers.

Use constant diagnostic messages and numeric context. Text arguments on errors,
structured text fields and exception messages are untrusted; retain operation,
severity, exception types and stack locations instead of their private payloads.
"""
from collections.abc import Mapping
import logging
from pathlib import Path
import re
import traceback

from ai_caddie.core.request_timing import redact_url, route_template

_REDACTED = "[redacted]"
_STANDARD = frozenset(logging.makeLogRecord({}).__dict__) | {"message", "asctime", "_privacy_sanitized"}
_PARTITION = re.compile(r"(?:main|player):[0-9a-f]{12}\Z")
_IDENTITY = re.compile(
    r"(?i)\b(player_?id|round_?id|player_?name|display_?name|nickname)\s*[:=]\s*[^,;\n]+"
)
_PRIVATE_PATH = re.compile(r"(?:[A-Za-z]:[\\/]|/|\bdata/)[^\s\"'<>]+")


def _text(value: str) -> str:
    value = redact_url(value)
    value = _IDENTITY.sub(lambda match: match[1] + "=" + _REDACTED, value)
    def path(match):
        candidate = match[0]
        if candidate.startswith("/api/") and route_template(candidate) == candidate:
            return candidate
        return _REDACTED
    return _PRIVATE_PATH.sub(path, value)


def _context(value):
    if isinstance(value, Mapping):
        return {key: _context(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return type(value)(_context(item) for item in value)
    if value is None or isinstance(value, (bool, int, float)):
        return value
    # Hashed migration partitions are explicitly public diagnostics (J7.3).
    if isinstance(value, str) and _PARTITION.fullmatch(value):
        return value
    return _REDACTED


def _exception_text(exc_info) -> str:
    trace = traceback.TracebackException(*exc_info, capture_locals=False)

    def clean(item):
        item._str = _REDACTED
        # Notes and source snippets can contain arbitrary user input as well.
        item.__notes__ = None
        if item.exc_type is not None and issubclass(item.exc_type, SyntaxError):
            item.filename = _REDACTED
            item.text = None
            item.msg = _REDACTED
        for frame in item.stack:
            frame.filename = Path(frame.filename).name
            frame._line = ""
        for child in (item.__cause__, item.__context__, *(item.exceptions or ())):
            if child is not None:
                clean(child)

    clean(trace)
    return "".join(trace.format()).rstrip()


class LogPrivacyFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if not record.name.startswith(("server_v2", "ai_caddie")):
            return True
        # Format once, before a formatter caches message or exception text. Sanitize
        # the actual LogRecord so JSON formatters cannot rediscover raw extra/args.
        if record.levelno >= logging.WARNING:
            if isinstance(record.args, Mapping):
                record.args = {key: _context(value) for key, value in record.args.items()}
            elif record.args:
                record.args = tuple(_context(value) for value in record.args)
        record.msg = _text(record.getMessage())
        record.args = ()
        record.__dict__.pop("message", None)
        for key in tuple(record.__dict__):
            if key not in _STANDARD:
                record.__dict__[key] = _context(record.__dict__[key])
        if record.exc_info:
            record.exc_text = _exception_text(record.exc_info)
            record.exc_info = None
        elif record.exc_text and not getattr(record, "_privacy_sanitized", False):
            # An earlier formatter may have cached unsanitized exception text.
            record.exc_text = _REDACTED
        if record.stack_info:
            record.stack_info = _REDACTED
        record._privacy_sanitized = True
        record.pathname = Path(record.pathname).name
        return True


def protect_handler(handler: logging.Handler) -> None:
    if not any(isinstance(item, LogPrivacyFilter) for item in handler.filters):
        handler.addFilter(LogPrivacyFilter())
