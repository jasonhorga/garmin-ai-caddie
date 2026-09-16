"""Durable, bounded background jobs for provider synchronisation.

The HTTP request that starts a Garmin pull must not own the provider socket or the
history/statistics rebuild.  This small file-backed queue deliberately has one
worker: Garmin writes are process-global and the shared volume lock already
serialises cron/API writers.  Job records are JSON and atomically replaced, so a
restart can recover queued work without inventing a second queue service.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import queue
import threading
import time
import uuid
from typing import Any, Callable

from ai_caddie.core.data import ROOT, atomic_write_json


ACTIVE_STATES = frozenset({"queued", "running"})
TERMINAL_STATES = frozenset({"ready", "no_data", "reauth_required", "error"})
JOB_SCHEMA = "ai-caddie-garmin-sync-job-v1"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _safe_player_id(value: object) -> str:
    text = str(value or "").strip()
    # Player ids are generated server-side. Keep a conservative filename-safe form even
    # when a malformed record was left behind by an interrupted old process.
    return text if text and all(ch.isalnum() or ch in "-_" for ch in text) else "me"


class RetrySyncJob(Exception):
    """The shared Garmin writer is busy; keep the job queued and try again."""


Runner = Callable[[dict[str, Any]], dict[str, Any]]


class GarminSyncJobStore:
    """A one-worker durable queue scoped to the API data root."""

    def __init__(self, *, root: Path = ROOT) -> None:
        self.root = Path(root)
        self.directory = self.root / "data" / "sync" / "jobs"
        self.directory.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._queue: queue.Queue[str] = queue.Queue()
        self._queued_ids: set[str] = set()
        self._runner: Runner | None = None
        self._worker: threading.Thread | None = None

    def _path(self, job_id: str) -> Path:
        return self.directory / f"{job_id}.json"

    def _read(self, job_id: str) -> dict[str, Any] | None:
        try:
            value = json.loads(self._path(job_id).read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, ValueError, TypeError):
            return None
        return value if isinstance(value, dict) else None

    def _write(self, record: dict[str, Any]) -> dict[str, Any]:
        record = dict(record)
        record["schema"] = JOB_SCHEMA
        record["updatedAt"] = _utc_now()
        # atomic_write_json creates parent directories and uses an atomic rename. Do not expose
        # runner exceptions, request headers, or arbitrary callback objects in this file.
        atomic_write_json(self._path(str(record["jobId"])), record)
        return record

    def _records(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for path in sorted(self.directory.glob("*.json")):
            row = self._read(path.stem)
            if row and row.get("jobId") == path.stem:
                rows.append(row)
        return rows

    def _ensure_worker(self, runner: Runner | None = None) -> None:
        with self._lock:
            if runner is not None:
                self._runner = runner
            if self._runner is None:
                return
            if self._worker is not None and self._worker.is_alive():
                return
            self._worker = threading.Thread(
                target=self._run,
                name="garmin-sync-job-worker",
                daemon=True,
            )
            self._worker.start()

    def start(self, runner: Runner) -> None:
        """Attach the process runner and recover unfinished records."""
        with self._lock:
            self._runner = runner
            for row in self._records():
                if row.get("state") == "running":
                    row["state"] = "queued"
                    row["detail"] = "同步任务已恢复，等待后台执行。"
                    row["startedAt"] = None
                    self._write(row)
                if row.get("state") == "queued":
                    self._enqueue_id(str(row["jobId"]))
        self._ensure_worker()

    def _enqueue_id(self, job_id: str) -> None:
        if job_id in self._queued_ids:
            return
        self._queued_ids.add(job_id)
        self._queue.put(job_id)

    def enqueue(
        self,
        *,
        player_id: str,
        with_shots: bool,
        force_refresh_auth: bool,
        ensure_geometry: bool,
        status_url: str,
        runner: Runner | None = None,
    ) -> dict[str, Any]:
        """Create or reuse the active job for a player and return its public record."""
        clean_player = _safe_player_id(player_id)
        with self._lock:
            # A player has one provider account and one shared writer. Reuse any active job for
            # that account, even when a duplicate click uses a different optional flag.
            for row in sorted(self._records(), key=lambda item: str(item.get("createdAt") or ""), reverse=True):
                if row.get("playerId") == clean_player and row.get("state") in ACTIVE_STATES:
                    self._ensure_worker(runner)
                    return dict(row)
            now = _utc_now()
            job_id = f"garmin-sync-{uuid.uuid4().hex}"
            record: dict[str, Any] = {
                "schema": JOB_SCHEMA,
                "jobId": job_id,
                "playerId": clean_player,
                "connector": "garmin_cn_web_session",
                "state": "queued",
                "detail": "Garmin 同步已加入后台队列。",
                "reauthRequired": False,
                "errorCode": None,
                "snapshot": None,
                "safeMeta": {},
                "statusUrl": status_url,
                "createdAt": now,
                "updatedAt": now,
                "startedAt": None,
                "completedAt": None,
                "request": {
                    "withShots": bool(with_shots),
                    "forceRefreshAuth": bool(force_refresh_auth),
                    "ensureGeometry": bool(ensure_geometry),
                },
                "retryCount": 0,
            }
            self._write(record)
            self._enqueue_id(job_id)
            self._ensure_worker(runner)
            return dict(record)

    def get(self, job_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._read(str(job_id))
            return dict(row) if row else None

    def _update(self, job_id: str, **changes: Any) -> dict[str, Any] | None:
        with self._lock:
            row = self._read(job_id)
            if row is None:
                return None
            row.update(changes)
            return self._write(row)

    def _run(self) -> None:
        while True:
            job_id = self._queue.get()
            with self._lock:
                self._queued_ids.discard(job_id)
                row = self._read(job_id)
                runner = self._runner
            if row is None or row.get("state") not in ACTIVE_STATES or runner is None:
                self._queue.task_done()
                continue
            try:
                started = self._update(
                    job_id,
                    state="running",
                    detail="正在从 Garmin 获取数据。",
                    startedAt=_utc_now(),
                    completedAt=None,
                )
                if started is None:
                    continue
                result = runner(dict(started))
                if not isinstance(result, dict):
                    raise RuntimeError("sync runner returned an invalid result")
                state = str(result.get("state") or "error")
                if state not in TERMINAL_STATES:
                    raise RuntimeError(f"sync runner returned unsupported state: {state}")
                # ``runner`` owns the terminal state in its result. Passing the same keyword a
                # second time raises before the record is persisted, turning every successful
                # provider pull into a generic ``error`` job.
                self._update(
                    job_id,
                    **{**result, "state": state, "completedAt": _utc_now()},
                )
            except RetrySyncJob:
                retry_count: int | None = None
                with self._lock:
                    current = self._read(job_id)
                    if current is not None:
                        retry_count = int(current.get("retryCount") or 0) + 1
                        self._write(
                            {
                                **current,
                                "state": "queued",
                                "detail": "后台同步资源忙，稍后自动重试。",
                                "retryCount": retry_count,
                                "startedAt": None,
                            }
                        )
                if retry_count is not None:
                    # A short bounded delay avoids a hot loop when the cron writer owns the
                    # shared lock. Do not hold the store lock while sleeping: status polling and
                    # account cancellation must remain responsive during the backoff.
                    time.sleep(min(5.0, 0.5 + retry_count * 0.25))
                    with self._lock:
                        self._enqueue_id(job_id)
            except Exception:
                # Keep the public record useful but never persist traceback paths, credentials, or
                # arbitrary exception text from a provider library.
                self._update(
                    job_id,
                    state="error",
                    detail="Garmin 同步失败，请稍后重试。",
                    errorCode="sync_failed",
                    reauthRequired=False,
                    snapshot=None,
                    safeMeta={},
                    completedAt=_utc_now(),
                )
            finally:
                self._queue.task_done()
