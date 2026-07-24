"""Durable file-backed storage for the legacy v1 mobile event stream."""

from __future__ import annotations

from collections.abc import Sequence
from contextlib import contextmanager, nullcontext
from copy import deepcopy
from dataclasses import dataclass
from datetime import UTC, datetime
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
from typing import Any, BinaryIO, Callable, Iterator

from ai_caddie.llm.llm_providers import redact_secret_text


EVENT_LOG_FILENAME = "events.jsonl"
EVENT_LOCK_FILENAME = "events.jsonl.lock"
ACK_FILENAME = "client_acks.json"
ACK_LOCK_FILENAME = "client_acks.json.lock"
RESERVATION_FILENAME = "request_reservations.json"
EVENT_COMMIT_FILENAME = "events.jsonl.commit.json"
EVENT_PENDING_COMMIT_FILENAME = "events.jsonl.pending.json"
ACK_SCHEMA = "ai-caddie-mobile-event-acks-v1"
RESERVATION_SCHEMA = "ai-caddie-mobile-event-request-reservations-v1"
EVENT_COMMIT_SCHEMA = "ai-caddie-mobile-event-commit-v2"
EVENT_PENDING_COMMIT_SCHEMA = "ai-caddie-mobile-event-pending-commit-v2"
_IDENTITY_FIELDS = ("roundId", "clientId", "eventId")
REDACTED_LOCAL_MEDIA_URL = "[REDACTED_LOCAL_MEDIA_URL]"
REDACTED_MOBILE_PATH = "[REDACTED_PATH]"


@dataclass(frozen=True)
class EventReceipt:
    event_id: str
    status: str
    position: int
    request_preexisting: bool = False


@dataclass(frozen=True)
class AppendBatchResult(Sequence[EventReceipt]):
    receipts: tuple[EventReceipt, ...]
    server_sequence: int

    def __getitem__(self, index: int | slice) -> EventReceipt | tuple[EventReceipt, ...]:
        return self.receipts[index]

    def __len__(self) -> int:
        return len(self.receipts)


@dataclass(frozen=True)
class _PreparedEvent:
    event: dict[str, Any]
    identity: tuple[str, str, str]
    event_hash: str


@dataclass(frozen=True)
class _StoredRow:
    row: dict[str, Any]
    raw_event: Any
    position: int
    line_number: int


@dataclass(frozen=True)
class _StoredLog:
    rows: tuple[_StoredRow, ...]
    high_water: int


@dataclass(frozen=True)
class _CommitMarker:
    committed_byte_length: int
    committed_prefix_sha256: str
    legacy_baseline_byte_length: int


@dataclass(frozen=True)
class _PendingCommit:
    base_committed_byte_length: int
    base_committed_prefix_sha256: str
    target_byte_length: int
    target_committed_prefix_sha256: str
    tail_sha256: str
    event_count: int
    legacy_baseline_byte_length: int


def _format_time(value: datetime) -> str:
    return value.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _canonical_v1_bytes(value: Any) -> bytes:
    """The deterministic v1 hash encoding (not the future canonical JSON owner)."""

    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_v1_bytes(value)).hexdigest()


def _normalized_event_for_hash(event: dict[str, Any]) -> dict[str, Any]:
    normalized = deepcopy(event)
    if normalized.get("clientId") is None:
        normalized["clientId"] = None
    return normalized


def _redact_mobile_text(value: str) -> str:
    redacted = redact_secret_text(value)
    # The shared LLM redactor intentionally recognizes only its historical path
    # families.  Mobile envelopes additionally treat forward-slash drive paths,
    # forward-slash UNC paths, and named ``label:/absolute`` path boundaries as
    # local filesystem authority.  Requiring a start/delimiter before each path
    # keeps complete non-file URLs (including URL paths that look like drives or
    # UNC shares) byte-exact.
    redacted = re.sub(
        r"(?i)(^|[\s=(\[{'\"])[a-z]:[\\/][^\s,;)]+",
        rf"\1{REDACTED_MOBILE_PATH}",
        redacted,
    )
    redacted = re.sub(
        r"(^|[\s=(\[{'\"])//[^\s,;)]+",
        rf"\1{REDACTED_MOBILE_PATH}",
        redacted,
    )
    redacted = re.sub(
        r"(?i)(^|[\s=(\[{'\"])([a-z_][a-z0-9_-]*):/(?!/)[^\s,;)]+",
        rf"\1\2:{REDACTED_MOBILE_PATH}",
        redacted,
    )
    redacted = re.sub(
        r"(?i)\b(password|secret|token|api[_-]?key|authorization|cookie|csrf)\s*[:=]\s*[^,\s;)]+",
        r"\1=[REDACTED]",
        redacted,
    )
    redacted = re.sub(
        r"(?i)\b(password|secret|token|api[_-]?key|authorization|cookie|csrf)\s+[^\s,;)]+",
        r"\1 [REDACTED]",
        redacted,
    )
    return redacted


def _redact_mobile_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _redact_mobile_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_redact_mobile_value(item) for item in value]
    if isinstance(value, str):
        return _redact_mobile_text(value)
    return value


def sanitize_mobile_event(event: dict[str, Any]) -> dict[str, Any]:
    """Return the one effective legacy-v1 mobile transport envelope."""

    sanitized = _redact_mobile_value(deepcopy(event))
    if not isinstance(sanitized, dict):
        raise ValueError("event sanitizer must return an object")
    payload = sanitized.get("payload")
    if not isinstance(payload, dict):
        return sanitized
    sanitized_payload = dict(payload)
    if (
        str(sanitized.get("kind") or "") in {"photo", "video"}
        and "fileURL" in sanitized_payload
    ):
        file_url = sanitized_payload["fileURL"]
        if (isinstance(file_url, str) and file_url) or (
            file_url is not None and not isinstance(file_url, str)
        ):
            sanitized_payload["fileURL"] = REDACTED_LOCAL_MEDIA_URL
    sanitized["payload"] = sanitized_payload
    return sanitized


class FileEventStore:
    """Store one physical player's v1 event partition.

    ``root`` is the existing ``mobile_events`` directory for that player. Event
    identity and request identity therefore inherit physical player isolation
    from the directory selected by the caller.
    """

    def __init__(
        self,
        root: Path | str,
        *,
        sanitizer: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
    ) -> None:
        self.root = Path(root).expanduser().resolve(strict=False)
        self._trusted_root_anchor = Path(self.root.anchor)
        self.log = self.root / EVENT_LOG_FILENAME
        self.event_lock = self.root / EVENT_LOCK_FILENAME
        self.acks = self.root / ACK_FILENAME
        self.ack_lock = self.root / ACK_LOCK_FILENAME
        self.reservations = self.root / RESERVATION_FILENAME
        self.commit_marker = self.root / EVENT_COMMIT_FILENAME
        self.pending_commit = self.root / EVENT_PENDING_COMMIT_FILENAME
        self._additional_sanitizer = sanitizer

    @contextmanager
    def _locked(self, path: Path, *, shared: bool = False) -> Iterator[None]:
        self._ensure_root_durable()
        with path.open("a+", encoding="utf-8") as handle:
            fcntl.flock(handle, fcntl.LOCK_SH if shared else fcntl.LOCK_EX)
            handle.flush()
            os.fsync(handle.fileno())
            self._fsync_directory()
            yield

    @staticmethod
    def _explicit_position(row: dict[str, Any]) -> int | None:
        value = row.get("serverSequence")
        try:
            position = int(value)
        except (TypeError, ValueError, OverflowError):
            return None
        return position if position > 0 else None

    def _event_log_size(self) -> int:
        try:
            return self.log.stat().st_size
        except FileNotFoundError:
            return 0

    @staticmethod
    def _is_sha256(value: Any) -> bool:
        return (
            isinstance(value, str)
            and len(value) == 64
            and all(character in "0123456789abcdef" for character in value)
        )

    @staticmethod
    def _is_ack_timestamp(value: Any) -> bool:
        if not isinstance(value, str):
            return False
        try:
            parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
        except ValueError:
            return False
        return parsed.strftime("%Y-%m-%dT%H:%M:%SZ") == value

    def _load_commit_marker(self) -> _CommitMarker | None:
        try:
            raw = self.commit_marker.read_bytes()
        except FileNotFoundError:
            return None
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, ValueError) as exc:
            raise ValueError("event_commit_store_corrupt") from exc
        if (
            not isinstance(payload, dict)
            or set(payload)
            != {
                "schema",
                "committedByteLength",
                "committedPrefixSha256",
                "legacyBaselineByteLength",
            }
            or payload.get("schema") != EVENT_COMMIT_SCHEMA
            or any(
                not isinstance(payload.get(field), int) or isinstance(payload.get(field), bool)
                for field in ("committedByteLength", "legacyBaselineByteLength")
            )
            or payload["committedByteLength"] < 0
            or payload["legacyBaselineByteLength"] < 0
            or payload["legacyBaselineByteLength"] > payload["committedByteLength"]
            or not self._is_sha256(payload.get("committedPrefixSha256"))
        ):
            raise ValueError("event_commit_store_corrupt")
        return _CommitMarker(
            committed_byte_length=int(payload["committedByteLength"]),
            committed_prefix_sha256=str(payload["committedPrefixSha256"]),
            legacy_baseline_byte_length=int(payload["legacyBaselineByteLength"]),
        )

    def _write_committed_length(self, marker: _CommitMarker) -> None:
        if (
            marker.committed_byte_length < 0
            or marker.legacy_baseline_byte_length < 0
            or marker.legacy_baseline_byte_length > marker.committed_byte_length
            or not self._is_sha256(marker.committed_prefix_sha256)
        ):
            raise ValueError("event_commit_store_corrupt")
        self._atomic_write_json(
            self.commit_marker,
            {
                "schema": EVENT_COMMIT_SCHEMA,
                "committedByteLength": marker.committed_byte_length,
                "committedPrefixSha256": marker.committed_prefix_sha256,
                "legacyBaselineByteLength": marker.legacy_baseline_byte_length,
            },
        )

    def _advance_committed_length(
        self,
        *,
        base_marker: _CommitMarker,
        target_marker: _CommitMarker,
    ) -> None:
        try:
            self._write_committed_length(target_marker)
            return
        except BaseException:
            pending = self._load_pending_commit()
            committed = self._load_commit_marker()
            actual_size = self._event_log_size()
            if (
                pending is None
                or self._pending_base_marker(pending) != base_marker
                or self._pending_target_marker(pending) != target_marker
                or committed != target_marker
            ):
                raise
            self._validate_commit_marker(target_marker, actual_size)
            if self._pending_marker_state(target_marker, pending) != "target":
                raise
            self._validate_pending_target(pending, actual_size)
            # The exact target replacement is already present. Re-fsync the directory while the
            # event lock is still exclusive so a post-replace error cannot expose an indeterminate
            # marker; after this succeeds the target is a durable committed prefix.
            self._fsync_directory()

    def _load_pending_commit(self) -> _PendingCommit | None:
        try:
            raw = self.pending_commit.read_bytes()
        except FileNotFoundError:
            return None
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, ValueError) as exc:
            raise ValueError("event_commit_store_corrupt") from exc
        integer_fields = (
            "baseCommittedByteLength",
            "targetByteLength",
            "eventCount",
            "legacyBaselineByteLength",
        )
        if (
            not isinstance(payload, dict)
            or set(payload)
            != {
                "schema",
                "baseCommittedByteLength",
                "baseCommittedPrefixSha256",
                "targetByteLength",
                "targetCommittedPrefixSha256",
                "tailSha256",
                "eventCount",
                "legacyBaselineByteLength",
            }
            or payload.get("schema") != EVENT_PENDING_COMMIT_SCHEMA
            or any(
                not isinstance(payload.get(field), int) or isinstance(payload.get(field), bool)
                for field in integer_fields
            )
            or payload["baseCommittedByteLength"] < 0
            or payload["targetByteLength"] <= payload["baseCommittedByteLength"]
            or payload["eventCount"] <= 0
            or payload["legacyBaselineByteLength"] < 0
            or payload["legacyBaselineByteLength"] > payload["baseCommittedByteLength"]
            or not self._is_sha256(payload.get("baseCommittedPrefixSha256"))
            or not self._is_sha256(payload.get("targetCommittedPrefixSha256"))
            or not self._is_sha256(payload.get("tailSha256"))
        ):
            raise ValueError("event_commit_store_corrupt")
        return _PendingCommit(
            base_committed_byte_length=int(payload["baseCommittedByteLength"]),
            base_committed_prefix_sha256=str(payload["baseCommittedPrefixSha256"]),
            target_byte_length=int(payload["targetByteLength"]),
            target_committed_prefix_sha256=str(payload["targetCommittedPrefixSha256"]),
            tail_sha256=str(payload["tailSha256"]),
            event_count=int(payload["eventCount"]),
            legacy_baseline_byte_length=int(payload["legacyBaselineByteLength"]),
        )

    def _write_pending_commit(self, pending: _PendingCommit) -> None:
        self._atomic_write_json(
            self.pending_commit,
            {
                "schema": EVENT_PENDING_COMMIT_SCHEMA,
                "baseCommittedByteLength": pending.base_committed_byte_length,
                "baseCommittedPrefixSha256": pending.base_committed_prefix_sha256,
                "targetByteLength": pending.target_byte_length,
                "targetCommittedPrefixSha256": pending.target_committed_prefix_sha256,
                "tailSha256": pending.tail_sha256,
                "eventCount": pending.event_count,
                "legacyBaselineByteLength": pending.legacy_baseline_byte_length,
            },
        )

    def _clear_pending_commit(self) -> None:
        try:
            self.pending_commit.unlink()
        except FileNotFoundError:
            return
        self._fsync_directory()

    def _read_log_range(
        self,
        start: int,
        end: int,
        *,
        handle: BinaryIO | None = None,
    ) -> bytes:
        if start < 0 or end < start:
            raise ValueError("event_commit_store_corrupt")
        length = end - start
        if length == 0:
            return b""
        if handle is not None:
            handle.seek(start)
            value = handle.read(length)
        else:
            try:
                with self.log.open("rb") as opened:
                    opened.seek(start)
                    value = opened.read(length)
            except FileNotFoundError as exc:
                raise ValueError("event_commit_store_corrupt") from exc
        if len(value) != length:
            raise ValueError("event_commit_store_corrupt")
        return value

    def _validate_untracked_suffix(
        self,
        committed_byte_length: int,
        actual_size: int,
        *,
        handle: BinaryIO | None = None,
    ) -> None:
        if actual_size <= committed_byte_length:
            return
        suffix = self._read_log_range(
            committed_byte_length,
            actual_size,
            handle=handle,
        )
        if b"\n" in suffix or not suffix.startswith(b"{"):
            raise ValueError("event_commit_store_corrupt")
        try:
            text = suffix.decode("utf-8")
        except UnicodeDecodeError:
            return
        try:
            json.loads(text)
        except json.JSONDecodeError:
            try:
                json.JSONDecoder().raw_decode(text)
            except json.JSONDecodeError:
                return
        raise ValueError("event_commit_store_corrupt")

    def _validate_storage_rows(self, raw: bytes, *, expected_event_count: int | None) -> None:
        if not raw:
            if expected_event_count not in (None, 0):
                raise ValueError("event_commit_store_corrupt")
            return
        if not raw.endswith(b"\n"):
            raise ValueError("event_commit_store_corrupt")
        lines = raw.splitlines(keepends=True)
        if expected_event_count is not None and len(lines) != expected_event_count:
            raise ValueError("event_commit_store_corrupt")
        previous_sequence = 0
        batch_context: tuple[str, str, str] | None = None
        required_fields = {
            "roundId",
            "idempotencyKey",
            "serverSequence",
            "eventHash",
            "requestHash",
            "event",
        }
        for raw_line in lines:
            if not raw_line.endswith(b"\n") or not raw_line.strip():
                raise ValueError("event_commit_store_corrupt")
            try:
                row = json.loads(raw_line.decode("utf-8"))
            except (UnicodeDecodeError, ValueError) as exc:
                raise ValueError("event_commit_store_corrupt") from exc
            if not isinstance(row, dict) or not required_fields.issubset(row):
                raise ValueError("event_commit_store_corrupt")
            round_id = row.get("roundId")
            request_key = row.get("idempotencyKey")
            event = row.get("event")
            sequence = row.get("serverSequence")
            if (
                not isinstance(round_id, str)
                or not isinstance(request_key, str)
                or not isinstance(sequence, int)
                or isinstance(sequence, bool)
                or sequence <= previous_sequence
                or not self._is_sha256(row.get("eventHash"))
                or not self._is_sha256(row.get("requestHash"))
                or not self._is_legacy_compatible_event(event)
            ):
                raise ValueError("event_commit_store_corrupt")
            if event.get("roundId") is not None and str(event.get("roundId")) != round_id:
                raise ValueError("event_commit_store_corrupt")
            if row["eventHash"] != _sha256(_normalized_event_for_hash(event)):
                raise ValueError("event_commit_store_corrupt")
            previous_sequence = sequence
            if expected_event_count is not None:
                context = (round_id, request_key, str(row["requestHash"]))
                if batch_context is None:
                    batch_context = context
                elif batch_context != context:
                    raise ValueError("event_commit_store_corrupt")

    def _validate_commit_marker(
        self,
        marker: _CommitMarker,
        actual_size: int,
        *,
        handle: BinaryIO | None = None,
    ) -> None:
        if (
            marker.committed_byte_length > actual_size
            or marker.legacy_baseline_byte_length > marker.committed_byte_length
        ):
            raise ValueError("event_commit_store_corrupt")
        prefix = self._read_log_range(0, marker.committed_byte_length, handle=handle)
        if marker.committed_byte_length and not prefix.endswith(b"\n"):
            raise ValueError("event_commit_store_corrupt")
        if (
            marker.legacy_baseline_byte_length
            and prefix[marker.legacy_baseline_byte_length - 1 : marker.legacy_baseline_byte_length]
            != b"\n"
        ):
            raise ValueError("event_commit_store_corrupt")
        if hashlib.sha256(prefix).hexdigest() != marker.committed_prefix_sha256:
            raise ValueError("event_commit_store_corrupt")
        self._validate_storage_rows(
            prefix[marker.legacy_baseline_byte_length :],
            expected_event_count=None,
        )

    @staticmethod
    def _pending_base_marker(pending: _PendingCommit) -> _CommitMarker:
        return _CommitMarker(
            committed_byte_length=pending.base_committed_byte_length,
            committed_prefix_sha256=pending.base_committed_prefix_sha256,
            legacy_baseline_byte_length=pending.legacy_baseline_byte_length,
        )

    @staticmethod
    def _pending_target_marker(pending: _PendingCommit) -> _CommitMarker:
        return _CommitMarker(
            committed_byte_length=pending.target_byte_length,
            committed_prefix_sha256=pending.target_committed_prefix_sha256,
            legacy_baseline_byte_length=pending.legacy_baseline_byte_length,
        )

    def _pending_marker_state(self, marker: _CommitMarker, pending: _PendingCommit) -> str:
        if marker == self._pending_base_marker(pending):
            return "base"
        if marker == self._pending_target_marker(pending):
            return "target"
        raise ValueError("event_commit_store_corrupt")

    def _validate_pending_target(
        self,
        pending: _PendingCommit,
        actual_size: int,
        *,
        handle: BinaryIO | None = None,
    ) -> None:
        if pending.target_byte_length != actual_size:
            raise ValueError("event_commit_store_corrupt")
        target_prefix = self._read_log_range(0, pending.target_byte_length, handle=handle)
        if (
            pending.base_committed_byte_length
            and target_prefix[
                pending.base_committed_byte_length - 1 : pending.base_committed_byte_length
            ]
            != b"\n"
        ):
            raise ValueError("event_commit_store_corrupt")
        if not target_prefix.endswith(b"\n"):
            raise ValueError("event_commit_store_corrupt")
        base_prefix = target_prefix[: pending.base_committed_byte_length]
        tail = target_prefix[pending.base_committed_byte_length :]
        if hashlib.sha256(base_prefix).hexdigest() != pending.base_committed_prefix_sha256:
            raise ValueError("event_commit_store_corrupt")
        if hashlib.sha256(target_prefix).hexdigest() != pending.target_committed_prefix_sha256:
            raise ValueError("event_commit_store_corrupt")
        if hashlib.sha256(tail).hexdigest() != pending.tail_sha256:
            raise ValueError("event_commit_store_corrupt")
        self._validate_storage_rows(
            target_prefix[pending.legacy_baseline_byte_length :],
            expected_event_count=None,
        )
        self._validate_storage_rows(tail, expected_event_count=pending.event_count)

    def _visible_committed_length_unlocked(self, *, handle: BinaryIO | None = None) -> int:
        actual_size = self._event_log_size()
        committed = self._load_commit_marker()
        pending = self._load_pending_commit()
        if committed is None:
            if pending is not None:
                raise ValueError("event_commit_store_corrupt")
            return actual_size
        self._validate_commit_marker(committed, actual_size, handle=handle)
        if pending is None:
            self._validate_untracked_suffix(
                committed.committed_byte_length,
                actual_size,
                handle=handle,
            )
            return committed.committed_byte_length
        state = self._pending_marker_state(committed, pending)
        if actual_size >= pending.target_byte_length:
            self._validate_pending_target(pending, actual_size, handle=handle)
        if state == "target":
            self._validate_pending_target(pending, actual_size, handle=handle)
            # A target marker left beside its pending intent may be the result of a successful
            # replace followed by a failed directory fsync. Re-establish that barrier before any
            # reader, replay, state fold, or ACK is allowed to observe the target prefix.
            self._fsync_directory()
        return committed.committed_byte_length

    def _stored_log(self, *, handle: BinaryIO | None = None) -> _StoredLog:
        committed_byte_length = self._visible_committed_length_unlocked(handle=handle)
        if committed_byte_length == 0:
            return _StoredLog((), 0)
        rows: list[_StoredRow] = []
        owns_handle = handle is None
        if handle is None:
            try:
                handle = self.log.open("rb")
            except FileNotFoundError as exc:
                raise ValueError("event_commit_store_corrupt") from exc
        running_high_water = 0
        try:
            handle.seek(0)
            remaining = committed_byte_length
            line_number = 0
            while remaining > 0:
                raw_line = handle.readline(remaining)
                if not raw_line:
                    raise ValueError("event_commit_store_corrupt")
                remaining -= len(raw_line)
                line_number += 1
                if not raw_line.strip():
                    running_high_water = max(running_high_water, line_number)
                    continue
                try:
                    parsed = json.loads(raw_line.decode("utf-8"))
                except (UnicodeDecodeError, ValueError):
                    running_high_water = max(running_high_water, line_number)
                    continue
                if not isinstance(parsed, dict):
                    running_high_water = max(running_high_water, line_number)
                    continue
                row = dict(parsed)
                raw_event = deepcopy(row.get("event"))
                if isinstance(raw_event, dict):
                    row["event"] = self._sanitize_event(raw_event)
                    if "eventHash" in row and self._is_legacy_compatible_event(row["event"]):
                        row["eventHash"] = _sha256(_normalized_event_for_hash(row["event"]))
                explicit_position = self._explicit_position(row)
                position = max(explicit_position or 0, running_high_water + 1, line_number)
                running_high_water = position
                row["serverSequence"] = position
                rows.append(
                    _StoredRow(
                        row=row,
                        raw_event=raw_event,
                        position=position,
                        line_number=line_number,
                    )
                )
        finally:
            if owns_handle:
                handle.close()
        return _StoredLog(tuple(rows), running_high_water)

    def _stored_rows(self, *, handle: BinaryIO | None = None) -> list[_StoredRow]:
        return list(self._stored_log(handle=handle).rows)

    @staticmethod
    def _is_legacy_compatible_event(event: Any) -> bool:
        if not isinstance(event, dict):
            return False
        if "hole" not in event or event.get("hole") is None:
            return True
        try:
            int(event["hole"])
        except (TypeError, ValueError, OverflowError):
            return False
        return True

    @classmethod
    def _is_legacy_compatible_stored_row(cls, row: dict[str, Any]) -> bool:
        return cls._is_legacy_compatible_event(row.get("event"))

    def read_rows(self, round_id: str | None = None) -> list[dict[str, Any]]:
        round_key = None if round_id is None else str(round_id)
        with self._locked(self.event_lock, shared=True):
            return [
                deepcopy(stored.row)
                for stored in self._stored_rows()
                if self._is_legacy_compatible_stored_row(stored.row)
                and (round_key is None or str(stored.row.get("roundId") or "") == round_key)
            ]

    def read_events(self, round_id: str) -> list[EventReceipt]:
        receipts: list[EventReceipt] = []
        for row in self.read_rows(round_id):
            event = row.get("event")
            if not isinstance(event, dict):
                continue
            receipts.append(
                EventReceipt(
                    event_id=str(event.get("eventId") or ""),
                    status="accepted",
                    position=int(row.get("serverSequence") or 0),
                )
            )
        return receipts

    def high_water(self) -> int:
        with self._locked(self.event_lock, shared=True):
            return self._high_water_unlocked()

    def _high_water_unlocked(self) -> int:
        return self._stored_log().high_water

    def _sanitize_event(self, event: dict[str, Any]) -> dict[str, Any]:
        source = deepcopy(event)
        candidate = (
            self._additional_sanitizer(deepcopy(source))
            if self._additional_sanitizer is not None
            else deepcopy(source)
        )
        if not isinstance(candidate, dict):
            raise ValueError("event sanitizer must return an object")
        sanitized = sanitize_mobile_event(candidate)
        if not isinstance(sanitized, dict):
            raise ValueError("event sanitizer must return an object")
        sanitized = dict(sanitized)
        for field in _IDENTITY_FIELDS:
            if field in source:
                sanitized[field] = source[field]
            else:
                sanitized.pop(field, None)
        return sanitized

    def _prepare_events(self, round_id: str, events: list[dict[str, Any]]) -> list[_PreparedEvent]:
        prepared: list[_PreparedEvent] = []
        for event in events:
            if not isinstance(event, dict):
                raise ValueError("event envelope must be an object")
            if event.get("roundId") is not None and str(event.get("roundId")) != round_id:
                raise ValueError("event roundId does not match path")
            sanitized = self._sanitize_event(event)
            identity = (
                round_id,
                str(event.get("clientId") or ""),
                str(event.get("eventId") or ""),
            )
            prepared.append(
                _PreparedEvent(
                    sanitized,
                    identity,
                    _sha256(_normalized_event_for_hash(sanitized)),
                )
            )
        return prepared

    @staticmethod
    def _reservation_key(round_id: str, request_key: str) -> str:
        return f"{round_id}\n{request_key}"

    @staticmethod
    def _ack_key(round_id: str, consumer_id: str) -> str:
        return f"{round_id}\n{consumer_id}"

    def _load_reservations(self) -> dict[str, dict[str, Any]]:
        if not self.reservations.exists():
            return {}
        try:
            payload = json.loads(self.reservations.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, ValueError) as exc:
            raise ValueError("request_reservation_store_corrupt") from exc
        if (
            not isinstance(payload, dict)
            or set(payload) != {"schema", "reservations"}
            or payload.get("schema") != RESERVATION_SCHEMA
            or not isinstance(payload.get("reservations"), dict)
        ):
            raise ValueError("request_reservation_store_corrupt")
        reservations: dict[str, dict[str, Any]] = {}
        for key, row in payload["reservations"].items():
            if (
                not isinstance(row, dict)
                or set(row) != {"roundId", "idempotencyKey", "requestHash"}
                or not isinstance(row.get("roundId"), str)
                or not isinstance(row.get("idempotencyKey"), str)
                or not isinstance(row.get("requestHash"), str)
                or len(row["requestHash"]) != 64
                or any(character not in "0123456789abcdef" for character in row["requestHash"])
            ):
                raise ValueError("request_reservation_store_corrupt")
            expected_key = self._reservation_key(row["roundId"], row["idempotencyKey"])
            if str(key) != expected_key:
                raise ValueError("request_reservation_store_corrupt")
            reservations[str(key)] = dict(row)
        return reservations

    def _write_reservations(self, reservations: dict[str, dict[str, Any]]) -> None:
        self._atomic_write_json(
            self.reservations,
            {"schema": RESERVATION_SCHEMA, "reservations": reservations},
        )

    @staticmethod
    def _event_identity(row: dict[str, Any]) -> tuple[str, str, str] | None:
        event = row.get("event")
        if not FileEventStore._is_legacy_compatible_event(event) or not event.get("eventId"):
            return None
        return (
            str(row.get("roundId") or ""),
            str(event.get("clientId") or ""),
            str(event.get("eventId")),
        )

    @staticmethod
    def _event_hash(row: dict[str, Any]) -> str | None:
        event = row.get("event")
        return (
            _sha256(_normalized_event_for_hash(event))
            if FileEventStore._is_legacy_compatible_event(event)
            else None
        )

    def _preflight_request(
        self,
        *,
        round_id: str,
        request_key: str,
        request_hash: str,
        raw_request_hash: str,
        prepared: list[_PreparedEvent],
        stored_rows: list[_StoredRow],
        reservations: dict[str, dict[str, Any]],
    ) -> bool:
        reservation_key = self._reservation_key(round_id, request_key)
        reservation = reservations.get(reservation_key)
        request_preexisting = reservation is not None

        matching_request_rows = [
            stored
            for stored in stored_rows
            if str(stored.row.get("roundId") or "") == round_id
            and "idempotencyKey" in stored.row
            and str(stored.row.get("idempotencyKey") or "") == request_key
        ]
        row_request_hashes = {
            str(stored.row.get("requestHash"))
            for stored in matching_request_rows
            if isinstance(stored.row.get("requestHash"), str) and stored.row.get("requestHash")
        }
        legacy_request_rows = [
            stored
            for stored in matching_request_rows
            if not isinstance(stored.row.get("requestHash"), str) or not stored.row.get("requestHash")
        ]

        if any(not self._is_legacy_compatible_stored_row(stored.row) for stored in matching_request_rows):
            raise ValueError("idempotency_key_body_mismatch")
        ordered_matching_rows = sorted(
            matching_request_rows,
            key=lambda stored: (stored.position, stored.line_number),
        )
        normalized_stored_hashes = [self._event_hash(stored.row) for stored in ordered_matching_rows]
        incoming_identities: dict[tuple[str, str, str], str] = {}
        for item in prepared:
            if not item.identity[2]:
                continue
            previous_hash = incoming_identities.get(item.identity)
            if previous_hash is not None and previous_hash != item.event_hash:
                raise ValueError("identity_envelope_mismatch")
            incoming_identities[item.identity] = item.event_hash

        exact_identities_committed_by_other_requests: set[tuple[str, str, str]] = set()
        for stored in stored_rows:
            if str(stored.row.get("idempotencyKey") or "") == request_key:
                continue
            identity = self._event_identity(stored.row)
            if identity is None:
                continue
            expected_hash = incoming_identities.get(identity)
            if expected_hash is not None and self._event_hash(stored.row) == expected_hash:
                exact_identities_committed_by_other_requests.add(identity)
        append_candidates = [
            item
            for item in prepared
            if not item.identity[2]
            or item.identity not in exact_identities_committed_by_other_requests
        ]
        incoming_hashes = [item.event_hash for item in append_candidates]
        normalized_stored_roster_is_prefix = (
            None not in normalized_stored_hashes
            and normalized_stored_hashes == incoming_hashes[: len(normalized_stored_hashes)]
        )
        complete_normalized_roster = (
            len(normalized_stored_hashes) == len(incoming_hashes)
            and normalized_stored_roster_is_prefix
        )
        if not normalized_stored_roster_is_prefix:
            raise ValueError("idempotency_key_body_mismatch")
        raw_stored_events = [stored.raw_event for stored in ordered_matching_rows]
        legacy_raw_request_hash = (
            _sha256({"roundId": round_id, "events": raw_stored_events})
            if complete_normalized_roster
            and len(append_candidates) == len(prepared)
            and all(isinstance(event, dict) for event in raw_stored_events)
            else None
        )
        compatible_request_hashes = {request_hash, raw_request_hash}
        if legacy_raw_request_hash is not None:
            compatible_request_hashes.add(legacy_raw_request_hash)
        if (
            reservation is not None
            and reservation["requestHash"] not in compatible_request_hashes
        ):
            raise ValueError("idempotency_key_body_mismatch")
        # A recovered legacy batch may retain raw-hash prefix rows while its newly appended tail
        # uses the effective sanitized hash. Only those hashes proven from this exact retry body
        # are compatible; any third value still fails closed.
        if (
            row_request_hashes
            and not row_request_hashes.issubset(compatible_request_hashes)
        ):
            raise ValueError("idempotency_key_body_mismatch")
        if legacy_request_rows:
            if not complete_normalized_roster:
                raise ValueError("idempotency_key_body_mismatch")
            request_preexisting = True
        elif matching_request_rows:
            request_preexisting = True

        stored_identity_hashes: dict[tuple[str, str, str], set[str]] = {}
        for stored in stored_rows:
            identity = self._event_identity(stored.row)
            event_hash = self._event_hash(stored.row)
            if identity is None or event_hash is None:
                continue
            stored_identity_hashes.setdefault(identity, set()).add(event_hash)
        for identity, event_hash in incoming_identities.items():
            hashes = stored_identity_hashes.get(identity)
            if hashes is not None and hashes != {event_hash}:
                raise ValueError("identity_envelope_mismatch")

        return request_preexisting

    def _truncate_event_log(
        self,
        committed_byte_length: int,
        *,
        handle: BinaryIO | None = None,
    ) -> None:
        actual_size = self._event_log_size()
        if actual_size < committed_byte_length:
            raise ValueError("event_commit_store_corrupt")
        if actual_size == committed_byte_length:
            return
        if handle is not None:
            handle.truncate(committed_byte_length)
            handle.flush()
            os.fsync(handle.fileno())
        else:
            try:
                with self.log.open("r+b") as opened:
                    opened.truncate(committed_byte_length)
                    opened.flush()
                    os.fsync(opened.fileno())
            except FileNotFoundError as exc:
                raise ValueError("event_commit_store_corrupt") from exc
        self._fsync_directory()

    def _seal_legacy_baseline_unlocked(
        self,
        actual_size: int,
        *,
        handle: BinaryIO | None = None,
    ) -> _CommitMarker:
        if actual_size:
            if self._read_log_range(actual_size - 1, actual_size, handle=handle) != b"\n":
                if handle is not None:
                    handle.seek(0, os.SEEK_END)
                    handle.write(b"\n")
                    handle.flush()
                    os.fsync(handle.fileno())
                else:
                    try:
                        with self.log.open("ab") as opened:
                            opened.write(b"\n")
                            opened.flush()
                            os.fsync(opened.fileno())
                    except FileNotFoundError as exc:
                        raise ValueError("event_commit_store_corrupt") from exc
                self._fsync_directory()
                actual_size += 1
        prefix = self._read_log_range(0, actual_size, handle=handle)
        marker = _CommitMarker(
            committed_byte_length=actual_size,
            committed_prefix_sha256=hashlib.sha256(prefix).hexdigest(),
            legacy_baseline_byte_length=actual_size,
        )
        self._write_committed_length(marker)
        return marker

    def _recover_event_log_unlocked(self, *, handle: BinaryIO | None = None) -> int:
        actual_size = self._event_log_size()
        committed = self._load_commit_marker()
        pending = self._load_pending_commit()
        if committed is None:
            if pending is not None:
                raise ValueError("event_commit_store_corrupt")
            return self._seal_legacy_baseline_unlocked(
                actual_size,
                handle=handle,
            ).committed_byte_length
        self._validate_commit_marker(committed, actual_size, handle=handle)
        if pending is None:
            self._validate_untracked_suffix(
                committed.committed_byte_length,
                actual_size,
                handle=handle,
            )
            self._truncate_event_log(committed.committed_byte_length, handle=handle)
            return committed.committed_byte_length
        state = self._pending_marker_state(committed, pending)
        if actual_size >= pending.target_byte_length:
            self._validate_pending_target(pending, actual_size, handle=handle)
        if state == "base":
            self._truncate_event_log(committed.committed_byte_length, handle=handle)
            self._clear_pending_commit()
            return committed.committed_byte_length
        if state == "target":
            self._validate_pending_target(pending, actual_size, handle=handle)
            self._truncate_event_log(committed.committed_byte_length, handle=handle)
            self._clear_pending_commit()
            return committed.committed_byte_length
        raise ValueError("event_commit_store_corrupt")

    def append_batch(
        self,
        round_id: str,
        events: list[dict[str, Any]],
        *,
        request_key: str,
    ) -> AppendBatchResult:
        round_key = str(round_id)
        idempotency_key = str(request_key)
        with self._locked(self.event_lock):
            event_log_context = (
                self.log.open("r+b") if self.log.exists() else nullcontext(None)
            )
            with event_log_context as event_log_handle:
                prepared = self._prepare_events(round_key, events)
                raw_request_hash = _sha256(
                    {
                        "roundId": round_key,
                        "events": [_normalized_event_for_hash(event) for event in events],
                    }
                )
                request_hash = _sha256(
                    {
                        "roundId": round_key,
                        "events": [_normalized_event_for_hash(item.event) for item in prepared],
                    }
                )
                self._recover_event_log_unlocked(handle=event_log_handle)
                stored_log = self._stored_log(handle=event_log_handle)
                stored_rows = list(stored_log.rows)
                reservations = self._load_reservations()
                request_preexisting = self._preflight_request(
                    round_id=round_key,
                    request_key=idempotency_key,
                    request_hash=request_hash,
                    raw_request_hash=raw_request_hash,
                    prepared=prepared,
                    stored_rows=stored_rows,
                    reservations=reservations,
                )

                reservation_key = self._reservation_key(round_key, idempotency_key)
                if reservation_key not in reservations:
                    reservations[reservation_key] = {
                        "roundId": round_key,
                        "idempotencyKey": idempotency_key,
                        "requestHash": request_hash,
                    }
                    self._write_reservations(reservations)

                positions: dict[tuple[str, str, str], tuple[str, int]] = {}
                for stored in stored_rows:
                    identity = self._event_identity(stored.row)
                    event_hash = self._event_hash(stored.row)
                    if identity is None or event_hash is None:
                        continue
                    existing = positions.get(identity)
                    if existing is None or stored.position < existing[1]:
                        positions[identity] = (event_hash, stored.position)

                high_water = stored_log.high_water
                receipts: list[EventReceipt] = []
                rows_to_append: list[dict[str, Any]] = []
                for item in prepared:
                    existing = positions.get(item.identity) if item.identity[2] else None
                    if existing is not None:
                        receipts.append(
                            EventReceipt(
                                event_id=item.identity[2],
                                status="duplicate_hash_match",
                                position=existing[1],
                                request_preexisting=request_preexisting,
                            )
                        )
                        continue
                    high_water += 1
                    row = {
                        "roundId": round_key,
                        "idempotencyKey": idempotency_key,
                        "serverSequence": high_water,
                        "eventHash": item.event_hash,
                        "requestHash": request_hash,
                        "event": item.event,
                    }
                    rows_to_append.append(row)
                    if item.identity[2]:
                        positions[item.identity] = (item.event_hash, high_water)
                    receipts.append(
                        EventReceipt(
                            event_id=item.identity[2],
                            status="accepted",
                            position=high_water,
                            request_preexisting=request_preexisting,
                        )
                    )
                if event_log_handle is None:
                    self._append_rows(rows_to_append)
                else:
                    self._append_rows(rows_to_append, handle=event_log_handle)
                return AppendBatchResult(tuple(receipts), high_water)

    def _append_rows(
        self,
        rows: list[dict[str, Any]],
        *,
        handle: BinaryIO | None = None,
    ) -> None:
        if not rows:
            return
        encoded_rows = [
            json.dumps(row, ensure_ascii=False, sort_keys=True).encode("utf-8") + b"\n"
            for row in rows
        ]
        tail = b"".join(encoded_rows)
        self._validate_storage_rows(tail, expected_event_count=len(rows))
        self._ensure_root_durable()
        base_marker = self._load_commit_marker()
        if base_marker is None or self._load_pending_commit() is not None:
            raise ValueError("event_commit_store_corrupt")
        actual_size = self._event_log_size()
        if actual_size != base_marker.committed_byte_length:
            raise ValueError("event_commit_store_corrupt")
        self._validate_commit_marker(base_marker, actual_size, handle=handle)
        event_log_context = self.log.open("a+b") if handle is None else nullcontext(handle)
        with event_log_context as event_log_handle:
            event_log_handle.seek(0)
            prefix_digest = hashlib.sha256()
            remaining = base_marker.committed_byte_length
            while remaining:
                chunk = event_log_handle.read(min(1024 * 1024, remaining))
                if not chunk:
                    raise ValueError("event_commit_store_corrupt")
                prefix_digest.update(chunk)
                remaining -= len(chunk)
            if prefix_digest.hexdigest() != base_marker.committed_prefix_sha256:
                raise ValueError("event_commit_store_corrupt")
            target_digest = prefix_digest.copy()
            target_digest.update(tail)
            target_marker = _CommitMarker(
                committed_byte_length=base_marker.committed_byte_length + len(tail),
                committed_prefix_sha256=target_digest.hexdigest(),
                legacy_baseline_byte_length=base_marker.legacy_baseline_byte_length,
            )
            self._write_pending_commit(
                _PendingCommit(
                    base_committed_byte_length=base_marker.committed_byte_length,
                    base_committed_prefix_sha256=base_marker.committed_prefix_sha256,
                    target_byte_length=target_marker.committed_byte_length,
                    target_committed_prefix_sha256=target_marker.committed_prefix_sha256,
                    tail_sha256=hashlib.sha256(tail).hexdigest(),
                    event_count=len(rows),
                    legacy_baseline_byte_length=base_marker.legacy_baseline_byte_length,
                )
            )
            event_log_handle.seek(0, os.SEEK_END)
            if event_log_handle.tell() != base_marker.committed_byte_length:
                raise ValueError("event_commit_store_corrupt")
            event_log_handle.write(tail)
            event_log_handle.flush()
            os.fsync(event_log_handle.fileno())
        self._fsync_directory()
        self._advance_committed_length(
            base_marker=base_marker,
            target_marker=target_marker,
        )
        self._clear_pending_commit()

    def _load_acks(self, *, strict: bool) -> tuple[dict[str, dict[str, Any]], bytes | None]:
        if not self.acks.exists():
            return {}, None
        try:
            raw = self.acks.read_bytes()
        except OSError:
            if strict:
                raise
            return {}, None
        try:
            payload = json.loads(raw.decode("utf-8"))
            if (
                not isinstance(payload, dict)
                or set(payload) != {"schema", "acks"}
                or payload.get("schema") != ACK_SCHEMA
                or not isinstance(payload.get("acks"), dict)
            ):
                raise ValueError
            acks: dict[str, dict[str, Any]] = {}
            for key, row in payload["acks"].items():
                if (
                    not isinstance(row, dict)
                    or set(row) != {"roundId", "clientId", "serverSequence", "updatedAt"}
                ):
                    raise ValueError
                round_id = row.get("roundId")
                client_id = row.get("clientId")
                position = row.get("serverSequence")
                if (
                    not isinstance(round_id, str)
                    or not isinstance(client_id, str)
                    or not isinstance(position, int)
                    or isinstance(position, bool)
                    or position < 0
                    or not self._is_ack_timestamp(row.get("updatedAt"))
                ):
                    raise ValueError
                if str(key) != self._ack_key(round_id, client_id):
                    raise ValueError
                acks[str(key)] = dict(row)
            return acks, None
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
            return ({}, raw) if strict else ({}, None)

    def read_ack(self, round_id: str, consumer_id: str) -> int:
        with self._locked(self.event_lock, shared=True):
            committed_high_water = self._high_water_unlocked()
            with self._locked(self.ack_lock):
                acks = self._load_safe_acks_unlocked(committed_high_water)
                row = acks.get(self._ack_key(str(round_id), str(consumer_id)), {})
                return max(0, int(row.get("serverSequence") or 0))

    def _load_safe_acks_unlocked(
        self,
        committed_high_water: int,
    ) -> dict[str, dict[str, Any]]:
        acks, corrupt = self._load_acks(strict=True)
        if corrupt is None and any(
            int(row["serverSequence"]) > committed_high_water
            for row in acks.values()
        ):
            corrupt = self.acks.read_bytes()
        if corrupt is not None:
            self._quarantine_corrupt_ack(corrupt)
            return {}
        return acks

    def _quarantine_corrupt_ack(self, raw: bytes) -> None:
        digest = hashlib.sha256(raw).hexdigest()
        backup = self.acks.with_name(f"{self.acks.name}.corrupt.{digest}")
        if backup.exists():
            if backup.read_bytes() != raw:
                raise ValueError("client_ack_store_corrupt")
            self.acks.unlink()
        else:
            os.replace(self.acks, backup)
        self._fsync_directory()

    def ack(self, round_id: str, consumer_id: str, position: int) -> int:
        round_key = str(round_id)
        client_key = str(consumer_id)
        requested = max(0, int(position))
        with self._locked(self.event_lock, shared=True):
            committed_high_water = self._high_water_unlocked()
            with self._locked(self.ack_lock):
                acks = self._load_safe_acks_unlocked(committed_high_water)
                if requested > committed_high_water:
                    raise ValueError("consumer_ack_ahead_of_stream")
                key = self._ack_key(round_key, client_key)
                current = max(0, int(acks.get(key, {}).get("serverSequence") or 0))
                acked = max(current, requested)
                if key not in acks or acked != current:
                    acks[key] = {
                        "roundId": round_key,
                        "clientId": client_key,
                        "serverSequence": acked,
                        "updatedAt": _format_time(datetime.now(UTC)),
                    }
                    self._atomic_write_json(self.acks, {"schema": ACK_SCHEMA, "acks": acks})
                return acked

    def _atomic_write_json(self, path: Path, payload: dict[str, Any]) -> None:
        self._ensure_root_durable()
        descriptor, temporary_name = tempfile.mkstemp(
            dir=self.root,
            prefix=f".{path.name}.",
            suffix=".tmp",
        )
        temporary_path = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_path, path)
            self._fsync_directory()
        except BaseException:
            try:
                temporary_path.unlink()
            except FileNotFoundError:
                pass
            raise

    def _ensure_root_durable(self) -> None:
        current = self._trusted_root_anchor
        for component in self.root.relative_to(self._trusted_root_anchor).parts:
            directory = current / component
            try:
                directory.mkdir()
            except FileExistsError:
                if not directory.is_dir():
                    raise
            # Re-establish every parent-entry barrier for each fresh store use,
            # even when an earlier process already created the directory.  No
            # lock, log, marker, reservation, or ACK mutation happens until the
            # complete root-to-store chain succeeds.
            self._fsync_directory(current)
            current = directory

    def _fsync_directory(self, directory: Path | None = None) -> None:
        target = self.root if directory is None else directory
        flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
        descriptor = os.open(target, flags)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)


def open_mobile_event_store(root: Path | str) -> FileEventStore:
    """Construct the only production v1 store authority with the privacy sanitizer injected."""

    return FileEventStore(root, sanitizer=sanitize_mobile_event)
