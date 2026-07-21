"""Durable file-backed storage for the legacy v1 mobile event stream."""

from __future__ import annotations

from collections.abc import Sequence
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import dataclass
from datetime import UTC, datetime
import fcntl
import hashlib
import json
import os
from pathlib import Path
import tempfile
from typing import Any, Callable, Iterator


EVENT_LOG_FILENAME = "events.jsonl"
EVENT_LOCK_FILENAME = "events.jsonl.lock"
ACK_FILENAME = "client_acks.json"
ACK_LOCK_FILENAME = "client_acks.json.lock"
RESERVATION_FILENAME = "request_reservations.json"
EVENT_COMMIT_FILENAME = "events.jsonl.commit.json"
EVENT_PENDING_COMMIT_FILENAME = "events.jsonl.pending.json"
ACK_SCHEMA = "ai-caddie-mobile-event-acks-v1"
RESERVATION_SCHEMA = "ai-caddie-mobile-event-request-reservations-v1"
EVENT_COMMIT_SCHEMA = "ai-caddie-mobile-event-commit-v1"
EVENT_PENDING_COMMIT_SCHEMA = "ai-caddie-mobile-event-pending-commit-v1"
_IDENTITY_FIELDS = ("roundId", "clientId", "eventId")


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
    position: int
    line_number: int


@dataclass(frozen=True)
class _StoredLog:
    rows: tuple[_StoredRow, ...]
    high_water: int


@dataclass(frozen=True)
class _PendingCommit:
    base_committed_byte_length: int
    target_byte_length: int
    tail_sha256: str
    event_count: int


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
        self.root = Path(root)
        self.log = self.root / EVENT_LOG_FILENAME
        self.event_lock = self.root / EVENT_LOCK_FILENAME
        self.acks = self.root / ACK_FILENAME
        self.ack_lock = self.root / ACK_LOCK_FILENAME
        self.reservations = self.root / RESERVATION_FILENAME
        self.commit_marker = self.root / EVENT_COMMIT_FILENAME
        self.pending_commit = self.root / EVENT_PENDING_COMMIT_FILENAME
        self._sanitizer = sanitizer

    @contextmanager
    def _locked(self, path: Path, *, shared: bool = False) -> Iterator[None]:
        self._ensure_root_durable()
        with path.open("a+", encoding="utf-8") as handle:
            fcntl.flock(handle, fcntl.LOCK_SH if shared else fcntl.LOCK_EX)
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

    def _load_committed_length(self) -> int | None:
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
            or set(payload) != {"schema", "committedByteLength"}
            or payload.get("schema") != EVENT_COMMIT_SCHEMA
            or not isinstance(payload.get("committedByteLength"), int)
            or isinstance(payload.get("committedByteLength"), bool)
            or payload["committedByteLength"] < 0
        ):
            raise ValueError("event_commit_store_corrupt")
        return int(payload["committedByteLength"])

    def _write_committed_length(self, committed_byte_length: int) -> None:
        if committed_byte_length < 0:
            raise ValueError("event_commit_store_corrupt")
        self._atomic_write_json(
            self.commit_marker,
            {
                "schema": EVENT_COMMIT_SCHEMA,
                "committedByteLength": committed_byte_length,
            },
        )

    def _advance_committed_length(
        self,
        *,
        base_committed_byte_length: int,
        target_byte_length: int,
    ) -> None:
        try:
            self._write_committed_length(target_byte_length)
            return
        except BaseException:
            pending = self._load_pending_commit()
            committed = self._load_committed_length()
            actual_size = self._event_log_size()
            if (
                pending is None
                or pending.base_committed_byte_length != base_committed_byte_length
                or pending.target_byte_length != target_byte_length
                or committed != target_byte_length
                or not self._pending_target_matches(pending, actual_size)
            ):
                raise
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
        )
        if (
            not isinstance(payload, dict)
            or set(payload)
            != {
                "schema",
                "baseCommittedByteLength",
                "targetByteLength",
                "tailSha256",
                "eventCount",
            }
            or payload.get("schema") != EVENT_PENDING_COMMIT_SCHEMA
            or any(
                not isinstance(payload.get(field), int) or isinstance(payload.get(field), bool)
                for field in integer_fields
            )
            or payload["baseCommittedByteLength"] < 0
            or payload["targetByteLength"] <= payload["baseCommittedByteLength"]
            or payload["eventCount"] <= 0
            or not self._is_sha256(payload.get("tailSha256"))
        ):
            raise ValueError("event_commit_store_corrupt")
        return _PendingCommit(
            base_committed_byte_length=int(payload["baseCommittedByteLength"]),
            target_byte_length=int(payload["targetByteLength"]),
            tail_sha256=str(payload["tailSha256"]),
            event_count=int(payload["eventCount"]),
        )

    def _write_pending_commit(self, pending: _PendingCommit) -> None:
        self._atomic_write_json(
            self.pending_commit,
            {
                "schema": EVENT_PENDING_COMMIT_SCHEMA,
                "baseCommittedByteLength": pending.base_committed_byte_length,
                "targetByteLength": pending.target_byte_length,
                "tailSha256": pending.tail_sha256,
                "eventCount": pending.event_count,
            },
        )

    def _clear_pending_commit(self) -> None:
        try:
            self.pending_commit.unlink()
        except FileNotFoundError:
            return
        self._fsync_directory()

    def _read_log_range(self, start: int, end: int) -> bytes:
        if start < 0 or end < start:
            raise ValueError("event_commit_store_corrupt")
        length = end - start
        if length == 0:
            return b""
        try:
            with self.log.open("rb") as handle:
                handle.seek(start)
                value = handle.read(length)
        except FileNotFoundError as exc:
            raise ValueError("event_commit_store_corrupt") from exc
        if len(value) != length:
            raise ValueError("event_commit_store_corrupt")
        return value

    def _pending_target_matches(self, pending: _PendingCommit, actual_size: int) -> bool:
        if pending.target_byte_length > actual_size:
            return False
        tail = self._read_log_range(
            pending.base_committed_byte_length,
            pending.target_byte_length,
        )
        return hashlib.sha256(tail).hexdigest() == pending.tail_sha256

    def _visible_committed_length_unlocked(self) -> int:
        actual_size = self._event_log_size()
        committed = self._load_committed_length()
        pending = self._load_pending_commit()
        if committed is None:
            if pending is not None:
                raise ValueError("event_commit_store_corrupt")
            return actual_size
        if pending is None:
            if committed > actual_size:
                raise ValueError("event_commit_store_corrupt")
            return committed
        if committed == pending.base_committed_byte_length:
            if committed > actual_size:
                raise ValueError("event_commit_store_corrupt")
            return committed
        if committed == pending.target_byte_length:
            if not self._pending_target_matches(pending, actual_size):
                raise ValueError("event_commit_store_corrupt")
            return committed
        raise ValueError("event_commit_store_corrupt")

    def _stored_log(self) -> _StoredLog:
        committed_byte_length = self._visible_committed_length_unlocked()
        if committed_byte_length == 0:
            return _StoredLog((), 0)
        rows: list[_StoredRow] = []
        try:
            handle = self.log.open("rb")
        except FileNotFoundError as exc:
            raise ValueError("event_commit_store_corrupt") from exc
        running_high_water = 0
        with handle:
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
                explicit_position = self._explicit_position(row)
                position = max(explicit_position or 0, running_high_water + 1, line_number)
                running_high_water = position
                row["serverSequence"] = position
                rows.append(_StoredRow(row=row, position=position, line_number=line_number))
        return _StoredLog(tuple(rows), running_high_water)

    def _stored_rows(self) -> list[_StoredRow]:
        return list(self._stored_log().rows)

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
                dict(stored.row)
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
        sanitized = self._sanitizer(deepcopy(source)) if self._sanitizer is not None else deepcopy(source)
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
            prepared.append(_PreparedEvent(sanitized, identity, _sha256(sanitized)))
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
        return _sha256(event) if FileEventStore._is_legacy_compatible_event(event) else None

    def _preflight_request(
        self,
        *,
        round_id: str,
        request_key: str,
        request_hash: str,
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
        if reservation is not None and reservation["requestHash"] != request_hash:
            raise ValueError("idempotency_key_body_mismatch")
        if row_request_hashes and row_request_hashes != {request_hash}:
            raise ValueError("idempotency_key_body_mismatch")
        if legacy_request_rows:
            if row_request_hashes:
                raise ValueError("idempotency_key_body_mismatch")
            legacy_hashes = [
                self._event_hash(stored.row)
                for stored in sorted(legacy_request_rows, key=lambda stored: (stored.position, stored.line_number))
            ]
            incoming_hashes = [item.event_hash for item in prepared]
            if None in legacy_hashes or legacy_hashes != incoming_hashes:
                raise ValueError("idempotency_key_body_mismatch")
            request_preexisting = True
        elif matching_request_rows:
            request_preexisting = True

        incoming_identities: dict[tuple[str, str, str], str] = {}
        for item in prepared:
            if not item.identity[2]:
                continue
            previous_hash = incoming_identities.get(item.identity)
            if previous_hash is not None and previous_hash != item.event_hash:
                raise ValueError("identity_envelope_mismatch")
            incoming_identities[item.identity] = item.event_hash

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

    def _truncate_event_log(self, committed_byte_length: int) -> None:
        actual_size = self._event_log_size()
        if actual_size < committed_byte_length:
            raise ValueError("event_commit_store_corrupt")
        if actual_size == committed_byte_length:
            return
        try:
            with self.log.open("r+b") as handle:
                handle.truncate(committed_byte_length)
                handle.flush()
                os.fsync(handle.fileno())
        except FileNotFoundError as exc:
            raise ValueError("event_commit_store_corrupt") from exc
        self._fsync_directory()

    def _recover_event_log_unlocked(self) -> int:
        actual_size = self._event_log_size()
        committed = self._load_committed_length()
        pending = self._load_pending_commit()
        if committed is None:
            if pending is not None:
                raise ValueError("event_commit_store_corrupt")
            self._write_committed_length(actual_size)
            return actual_size
        if pending is None:
            if committed > actual_size:
                raise ValueError("event_commit_store_corrupt")
            self._truncate_event_log(committed)
            return committed
        if committed == pending.base_committed_byte_length:
            if committed > actual_size:
                raise ValueError("event_commit_store_corrupt")
            self._truncate_event_log(committed)
            self._clear_pending_commit()
            return committed
        if committed == pending.target_byte_length:
            if not self._pending_target_matches(pending, actual_size):
                raise ValueError("event_commit_store_corrupt")
            self._truncate_event_log(committed)
            self._clear_pending_commit()
            return committed
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
            prepared = self._prepare_events(round_key, events)
            request_hash = _sha256(
                {"roundId": round_key, "events": [item.event for item in prepared]}
            )
            stored_log = self._stored_log()
            stored_rows = list(stored_log.rows)
            reservations = self._load_reservations()
            request_preexisting = self._preflight_request(
                round_id=round_key,
                request_key=idempotency_key,
                request_hash=request_hash,
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

            self._recover_event_log_unlocked()

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
            self._append_rows(rows_to_append)
            return AppendBatchResult(tuple(receipts), high_water)

    def _append_row(self, row: dict[str, Any]) -> None:
        self._append_rows([row])

    def _append_rows(self, rows: list[dict[str, Any]]) -> None:
        if not rows:
            return
        encoded_rows = [
            json.dumps(row, ensure_ascii=False, sort_keys=True).encode("utf-8") + b"\n"
            for row in rows
        ]
        self._ensure_root_durable()
        committed_byte_length = self._load_committed_length()
        if committed_byte_length is None or self._load_pending_commit() is not None:
            raise ValueError("event_commit_store_corrupt")
        if self._event_log_size() != committed_byte_length:
            raise ValueError("event_commit_store_corrupt")
        with self.log.open("a+b") as handle:
            separator = b""
            if committed_byte_length:
                handle.seek(committed_byte_length - 1)
                if handle.read(1) != b"\n":
                    separator = b"\n"
            tail_digest = hashlib.sha256()
            tail_digest.update(separator)
            tail_byte_length = len(separator)
            for encoded in encoded_rows:
                tail_digest.update(encoded)
                tail_byte_length += len(encoded)
            target_byte_length = committed_byte_length + tail_byte_length
            self._write_pending_commit(
                _PendingCommit(
                    base_committed_byte_length=committed_byte_length,
                    target_byte_length=target_byte_length,
                    tail_sha256=tail_digest.hexdigest(),
                    event_count=len(rows),
                )
            )
            handle.seek(0, os.SEEK_END)
            if handle.tell() != committed_byte_length:
                raise ValueError("event_commit_store_corrupt")
            if separator:
                handle.write(separator)
            for encoded in encoded_rows:
                handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        self._fsync_directory()
        self._advance_committed_length(
            base_committed_byte_length=committed_byte_length,
            target_byte_length=target_byte_length,
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
                or payload.get("schema") != ACK_SCHEMA
                or not isinstance(payload.get("acks"), dict)
            ):
                raise ValueError
            acks: dict[str, dict[str, Any]] = {}
            for key, row in payload["acks"].items():
                if not isinstance(row, dict):
                    raise ValueError
                round_id = row.get("roundId")
                client_id = row.get("clientId")
                if not isinstance(round_id, str) or not isinstance(client_id, str):
                    raise ValueError
                if str(key) != self._ack_key(round_id, client_id):
                    raise ValueError
                try:
                    position = int(row.get("serverSequence") or 0)
                except (TypeError, ValueError, OverflowError) as exc:
                    raise ValueError from exc
                if position < 0:
                    raise ValueError
                clean_row = dict(row)
                clean_row["serverSequence"] = position
                acks[str(key)] = clean_row
            return acks, None
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
            return ({}, raw) if strict else ({}, None)

    def read_ack(self, round_id: str, consumer_id: str) -> int:
        acks, _corrupt = self._load_acks(strict=False)
        row = acks.get(self._ack_key(str(round_id), str(consumer_id)), {})
        return max(0, int(row.get("serverSequence") or 0))

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
            if requested > self._high_water_unlocked():
                raise ValueError("consumer_ack_ahead_of_stream")
            with self._locked(self.ack_lock):
                acks, corrupt = self._load_acks(strict=True)
                if corrupt is not None:
                    self._quarantine_corrupt_ack(corrupt)
                    acks = {}
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
        missing: list[Path] = []
        current = self.root
        while not current.exists():
            missing.append(current)
            parent = current.parent
            if parent == current:
                break
            current = parent
        for directory in reversed(missing):
            try:
                directory.mkdir()
            except FileExistsError:
                if not directory.is_dir():
                    raise
            self._fsync_directory(directory.parent)

    def _fsync_directory(self, directory: Path | None = None) -> None:
        target = self.root if directory is None else directory
        flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
        descriptor = os.open(target, flags)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
