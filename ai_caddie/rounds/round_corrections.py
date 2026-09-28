"""复盘修改层:把用户对某局逐杆的「增 / 改 / 删 / 手填罚杆」记成一本 append-only 的账,
读取复盘时盖在只读的原始数据(Garmin 同步 / 手动 ingest)之上。**原始数据一个字不动。**

设计见 docs/superpowers/specs/2026-07-05-review-v2-design.md:
- **稳定身份证号**(``mint_shot_id``):优先用 Garmin 原生 shot id(按 scorecard 命名空间化,全局唯一);
  没有原生 id(老导出 / 手动局)时退回「内容哈希」(scorecard+洞+order+起止坐标)——只要这杆内容
  没变,重同步后 id 不变,挂在它上面的修改就不丢。
- **op 事件日志**:``deleteShot / restoreShot / editField / setHolePenalty``(``addShot`` 后续),每条
  带 ``clientMutationId``(幂等)。存 ``data/players/<player_id>/corrections/<round_ref>.jsonl``,
  按人隔离(镜像 round_ingest 的 per-player 存储 + ``history.ROOT`` 约定,测试可 patch 重指向)。
- **apply 是纯函数**:把事件日志盖到原始 shot 列表上(删=去掉、改=覆盖 clubName/lie),孤儿引用
  (原始因重同步变了、id 对不上)不报错、也不静默丢账——只是这条这次盖不上,账仍在日志里。
- **B0d-2 纠错日志**:写入走 ``correction_audit``(每人一把审计锁、全局 ``auditSeq``、审计与事件同一行)。
  文件里的行带 ``recordType``;这里的读取只认 ``correction`` 和没有类型的旧行,``auditRepair`` 只给日志读。
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from ai_caddie.history import history as _history

SCHEMA = "ai-caddie-round-correction-v1"

VALID_OPS = {
    "deleteShot",
    "restoreShot",
    "editField",
    "setHolePenalty",
    "addShot",
    "reorderShot",
    "replaceHoleShots",
    "replaceHoleFacts",
}
# 只允许改这两样(球位纯描述、球杆展示用);其余字段不给编辑,守「不造假 + 极简」。
EDITABLE_FIELDS = {"club", "lie", "position"}  # club/lie 走纯 apply;position 要几何,在 round_shot_map 生效
_SAFE_REF = re.compile(r"[^A-Za-z0-9_.-]")


class CorrectionError(Exception):
    """事件不合法(未知 op / 缺必填字段 / 非法字段)。"""


# ---------------------------------------------------------------------------
# 稳定身份证号
# ---------------------------------------------------------------------------
def mint_shot_id(shot: dict[str, Any]) -> str:
    """给一杆铸一个稳定 id。优先 Garmin 原生 id(namespaced by scorecard),否则内容哈希。"""
    sid = shot.get("scorecardId")
    native = shot.get("id")
    if native not in (None, "", 0, "0"):
        return f"s:{sid}:{native}"
    start = shot.get("start") or {}
    end = shot.get("end") or {}
    sig = json.dumps(
        [sid, shot.get("hole"), shot.get("order"),
         start.get("lat"), start.get("lon"), end.get("lat"), end.get("lon")],
        sort_keys=True, separators=(",", ":"),
    )
    return "h:" + hashlib.sha1(sig.encode()).hexdigest()[:16]


# ---------------------------------------------------------------------------
# 存储(per-player,append-only jsonl)
# ---------------------------------------------------------------------------
def _root(root: Path | str | None) -> Path:
    # 默认 history.ROOT,让写入落在读取层能读到的地方(测试 mock.patch.object(history,"ROOT",tmp) 同样重指向)。
    return Path(root) if root is not None else _history.ROOT


RECORD_CORRECTION = "correction"
RECORD_REPAIR = "auditRepair"


def corrections_dir(player_id: str, root: Path | str | None = None) -> Path:
    return _root(root) / "data" / "players" / str(player_id) / "corrections"


def _legacy_corrections_path(player_id: str, round_ref: str, root: Path | str | None = None) -> Path:
    # Pre-B0d-2 name: replacing unsafe characters can alias two refs, so it is read-only now.
    safe = _SAFE_REF.sub("_", str(round_ref)) or "round"
    return corrections_dir(player_id, root) / f"{safe}.jsonl"


def _corrections_path(player_id: str, round_ref: str, root: Path | str | None = None) -> Path:
    """Collision-resistant file for new writes: a readable prefix plus a digest of the exact ref."""
    safe = (_SAFE_REF.sub("_", str(round_ref)) or "round")[:80]
    digest = hashlib.sha256(str(round_ref).encode("utf-8")).hexdigest()[:16]
    return corrections_dir(player_id, root) / f"{safe}--{digest}.jsonl"


def correction_files(player_id: str, round_ref: str, root: Path | str | None = None) -> list[Path]:
    """Legacy file first (its events replay first), then the digest-named file."""
    legacy = _legacy_corrections_path(player_id, round_ref, root)
    current = _corrections_path(player_id, round_ref, root)
    return [path for path in (legacy, current) if path.exists()]


def _legacy_event_id(file_name: str, line_number: int, raw: bytes) -> str:
    blob = file_name.encode("utf-8") + b"\n" + str(line_number).encode("ascii") + b"\n" + raw
    return "legacy:" + hashlib.sha256(blob).hexdigest()[:16]


def read_records(path: Path) -> tuple[list[dict[str, Any]], int]:
    """Every parseable line of one JSONL store (legacy lines get a deterministic ``eventId``),
    plus the number of skipped unparseable lines."""
    records: list[dict[str, Any]] = []
    skipped = 0
    if not path.exists():
        return records, skipped
    for line_number, raw in enumerate(path.read_bytes().split(b"\n"), start=1):
        if not raw.strip():
            continue
        try:
            record = json.loads(raw)
        except (json.JSONDecodeError, UnicodeDecodeError):
            skipped += 1
            continue
        if not isinstance(record, dict):
            skipped += 1
            continue
        if not record.get("eventId"):
            record["eventId"] = _legacy_event_id(path.name, line_number, raw)
        records.append(record)
    return records, skipped


def load_correction_records(
    player_id: str, round_ref: str, *, root: Path | str | None = None
) -> tuple[list[dict[str, Any]], int]:
    """All records for a round across the legacy and digest-named files, including audit repairs."""
    records: list[dict[str, Any]] = []
    skipped = 0
    for path in correction_files(player_id, round_ref, root):
        rows, bad = read_records(path)
        records.extend(rows)
        skipped += bad
    return records, skipped


def load_correction_events(player_id: str, round_ref: str, *, root: Path | str | None = None) -> list[dict[str, Any]]:
    """Correction events in replay order. Audit repair records are never correction events."""
    records, _skipped = load_correction_records(player_id, round_ref, root=root)
    return [record for record in records if record.get("recordType") in (None, RECORD_CORRECTION)]


def load_round_records(
    player_id: str, refs: list[str], *, root: Path | str | None = None
) -> tuple[list[dict[str, Any]], int]:
    """Records of one physical round stored under any of its refs (a merged round's canonical id and
    its member ids). Order: legacy records without ``auditSeq`` first (by ``ts``, then file order),
    then every audited record by ``auditSeq`` — the one total order all writers share."""
    merged: list[tuple[tuple, dict[str, Any]]] = []
    seen: set[str] = set()
    skipped = 0
    position = 0
    for ref in dict.fromkeys(str(value) for value in refs):
        rows, bad = load_correction_records(player_id, ref, root=root)
        skipped += bad
        for record in rows:
            event_id = str(record.get("eventId"))
            if event_id in seen:
                continue
            seen.add(event_id)
            audit_seq = record.get("auditSeq")
            key = (1, audit_seq, "", position) if isinstance(audit_seq, int) else (0, 0, str(record.get("ts") or ""), position)
            merged.append((key, record))
            position += 1
    merged.sort(key=lambda item: item[0])
    return [record for _key, record in merged], skipped


def load_round_events(player_id: str, refs: list[str], *, root: Path | str | None = None) -> list[dict[str, Any]]:
    records, _skipped = load_round_records(player_id, refs, root=root)
    return [record for record in records if record.get("recordType") in (None, RECORD_CORRECTION)]


def validate_correction(event: dict[str, Any]) -> None:
    """Public validation entry (the route validates before resolving the round)."""
    _validate(event)


def _validate(event: dict[str, Any]) -> None:
    op = event.get("op")
    if op not in VALID_OPS:
        raise CorrectionError(f"未知操作 {op!r}")
    if op in {"deleteShot", "restoreShot", "editField"} and not event.get("shotId"):
        raise CorrectionError(f"{op} 需要 shotId")
    if op == "editField":
        if event.get("field") not in EDITABLE_FIELDS:
            raise CorrectionError(f"不可编辑的字段 {event.get('field')!r}(只允许 {sorted(EDITABLE_FIELDS)})")
    if op == "setHolePenalty":
        if event.get("hole") is None:
            raise CorrectionError("setHolePenalty 需要 hole")
        try:
            int(event.get("value"))
        except (TypeError, ValueError):
            raise CorrectionError("setHolePenalty 的 value 必须是整数杆数")
    if op == "reorderShot" and not isinstance(event.get("order"), list):
        raise CorrectionError("reorderShot 需要 order 列表")
    if op == "addShot" and not (isinstance(event.get("px"), list) and len(event.get("px")) == 2):
        raise CorrectionError("addShot 需要 px=[x,y]")
    if op == "replaceHoleShots":
        hole = _int(event.get("hole"))
        if hole is None or not 1 <= hole <= 36:
            raise CorrectionError("replaceHoleShots 需要 1..36 的 hole")
        shots = event.get("shots")
        if not isinstance(shots, list) or len(shots) > 100:
            raise CorrectionError("replaceHoleShots 需要不超过 100 杆的 shots 列表")
        penalty = _int(event.get("manualPenalty"))
        if penalty is None or not 0 <= penalty <= 100:
            raise CorrectionError("replaceHoleShots 需要 0..100 的 manualPenalty")
        seen_ids: set[str] = set()
        for index, shot in enumerate(shots):
            if not isinstance(shot, dict):
                raise CorrectionError(f"replaceHoleShots shots[{index}] 必须是对象")
            shot_id = str(shot.get("id") or "").strip()
            if not shot_id or len(shot_id) > 200 or shot_id in seen_ids:
                raise CorrectionError(f"replaceHoleShots shots[{index}] 的 id 缺失、过长或重复")
            seen_ids.add(shot_id)
            for field in ("start", "end"):
                pair = shot.get(field)
                if pair is None:
                    continue
                if not (
                    isinstance(pair, list)
                    and len(pair) == 2
                    and all(
                        isinstance(value, (int, float))
                        and not isinstance(value, bool)
                        and math.isfinite(float(value))
                        for value in pair
                    )
                ):
                    raise CorrectionError(
                        f"replaceHoleShots shots[{index}].{field} 必须是有限像素 [x,y] 或 null"
                    )
    if op == "replaceHoleFacts":
        hole = _int(event.get("hole"))
        if hole is None or not 1 <= hole <= 36:
            raise CorrectionError("replaceHoleFacts 需要 1..36 的 hole")
        shots = event.get("shots")
        if not isinstance(shots, list) or len(shots) > 100:
            raise CorrectionError("replaceHoleFacts 需要不超过 100 杆的 shots 列表")
        penalty = _int(event.get("manualPenalty"))
        if penalty is None or not 0 <= penalty <= 100:
            raise CorrectionError("replaceHoleFacts 需要 0..100 的 manualPenalty")
        allowed = {"id", "club", "lie", "clubSource", "lieSource"}
        seen_ids: set[str] = set()
        for index, shot in enumerate(shots):
            if not isinstance(shot, dict):
                raise CorrectionError(f"replaceHoleFacts shots[{index}] 必须是对象")
            extra = set(shot) - allowed
            if extra:
                raise CorrectionError(
                    f"replaceHoleFacts shots[{index}] 含位置或未知字段 {sorted(extra)}"
                )
            shot_id = str(shot.get("id") or "").strip()
            if not shot_id or len(shot_id) > 200 or shot_id in seen_ids:
                raise CorrectionError(f"replaceHoleFacts shots[{index}] 的 id 缺失、过长或重复")
            seen_ids.add(shot_id)
            for field, limit in (("club", 200), ("lie", 64)):
                value = shot.get(field)
                if value is not None and (not isinstance(value, str) or len(value) > limit):
                    raise CorrectionError(
                        f"replaceHoleFacts shots[{index}].{field} 必须是字符串或 null"
                    )
            for field in ("clubSource", "lieSource"):
                if shot.get(field) not in (None, "manual"):
                    raise CorrectionError(
                        f"replaceHoleFacts shots[{index}].{field} 只允许 manual 或 null"
                    )


def append_correction(
    player_id: str, round_ref: str, event: dict[str, Any], *, root: Path | str | None = None,
    now: datetime | None = None, data_loader: Any = None,
) -> dict[str, Any]:
    """追加一条修改事件(幂等 on clientMutationId)。返回落库后的事件(带 seq/ts/eventId/auditSeq/audit)。

    The only writer of this store: it takes the player's audit lock itself (see ``correction_audit``),
    so tests and jobs calling it directly cannot bypass the lock.
    """
    _validate(event)
    from ai_caddie.rounds import correction_audit  # round_shot_map imports this module

    return correction_audit.write_correction(
        player_id, round_ref, event, root=root, now=now, data_loader=data_loader,
    )


# ---------------------------------------------------------------------------
# apply(纯函数):把事件盖到原始 shot 列表上
# ---------------------------------------------------------------------------
def _int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def apply_corrections(
    shots: list[dict[str, Any]],
    events: list[dict[str, Any]],
    *,
    hole: int | None = None,
) -> list[dict[str, Any]]:
    """删=去掉该 shotId;改=把 club→clubName / lie→start.lie 覆盖掉(带 provenance)。
    最后一次操作胜出(op 日志按序回放)。孤儿 shotId 对不上就跳过、不报错。"""
    if not events:
        return shots
    requested_hole = _int(hole)
    fact_snapshot = (
        latest_hole_fact_snapshot(events, requested_hole)
        if requested_hole is not None
        else None
    )
    active_shots = list(shots)
    active_events = events
    if fact_snapshot is not None:
        snapshot_index, snapshot = fact_snapshot
        by_id = {mint_shot_id(shot): shot for shot in shots}
        active_shots = []
        snapshot_facts = snapshot.get("shots") or []
        for fact in snapshot_facts:
            if not isinstance(fact, dict):
                continue
            source = by_id.get(str(fact.get("id") or ""))
            if source is None:
                # A stable id that no longer exists is an orphan, not a licence to invent GPS.
                continue
            shot = dict(source)
            source_start = source.get("start") if isinstance(source.get("start"), dict) else {}
            shot["clubName"] = fact.get("club")
            shot["start"] = {**source_start, "lie": fact.get("lie")}
            if fact.get("clubSource") == "manual":
                shot["clubSource"] = "manual"
            else:
                shot.pop("clubSource", None)
            if fact.get("lieSource") == "manual":
                shot["lieSource"] = "manual"
            else:
                shot.pop("lieSource", None)
            active_shots.append(shot)
        if snapshot_facts and not active_shots:
            # A later Garmin resync can orphan every old hash id. Match granular-correction behaviour:
            # keep the current source rows visible instead of turning an identity miss into deletion.
            active_shots = list(shots)
        # A whole-hole fact snapshot supersedes every older granular fact edit. Newer legacy clients
        # may still append granular ops, so continue replaying only the tail after this snapshot.
        active_events = events[snapshot_index + 1 :]
    deleted: dict[str, bool] = {}       # shotId -> 是否已删(restoreShot 可翻回来)
    edits: dict[str, dict[str, Any]] = {}  # shotId -> {field: value}
    latest_order: list[str] | None = None
    for e in active_events:
        op = e.get("op")
        sid = e.get("shotId")
        if op == "deleteShot" and sid:
            deleted[sid] = True
        elif op == "restoreShot" and sid:
            deleted[sid] = False
        elif op == "editField" and sid and e.get("field") in EDITABLE_FIELDS:
            edits.setdefault(sid, {})[e["field"]] = e.get("value")
        elif op == "reorderShot" and isinstance(e.get("order"), list):
            latest_order = [str(value) for value in e["order"]]

    out: list[dict[str, Any]] = []
    for shot in active_shots:
        sid = mint_shot_id(shot)
        if deleted.get(sid):
            continue
        fields = edits.get(sid)
        if fields:
            shot = dict(shot)
            if "club" in fields:
                shot["clubName"] = fields["club"]
                shot["clubSource"] = "manual"
            if "lie" in fields:
                shot["start"] = {**(shot.get("start") or {}), "lie": fields["lie"]}
                shot["lieSource"] = "manual"
        out.append(shot)
    if latest_order is not None:
        positions = {shot_id: index for index, shot_id in enumerate(latest_order)}
        out.sort(key=lambda shot: positions.get(mint_shot_id(shot), len(positions)))
    for index, shot in enumerate(out):
        # Derived display order lives only in this corrected copy. Garmin's original `order` and both
        # WGS84 endpoints remain untouched, including for a fact-only reorder.
        shot = dict(shot)
        out[index] = shot
        shot["_displayOrder"] = index + 1
    return out


def hole_penalty(events: list[dict[str, Any]], hole: int) -> int:
    """某洞手填的罚杆数(最后一次 setHolePenalty 胜出;默认 0)。"""
    val = 0
    h = _int(hole)
    for e in events:
        op = e.get("op")
        if op == "setHolePenalty" and _int(e.get("hole")) == h:
            v = _int(e.get("value"))
            if v is not None:
                val = v
        elif op in {"replaceHoleShots", "replaceHoleFacts"} and _int(e.get("hole")) == h:
            v = _int(e.get("manualPenalty"))
            if v is not None:
                val = v
    return val


def latest_hole_shot_snapshot(events: list[dict[str, Any]], hole: int) -> tuple[int, dict[str, Any]] | None:
    """Return the latest atomic whole-hole edit snapshot and its event index, if one exists."""
    requested = _int(hole)
    result: tuple[int, dict[str, Any]] | None = None
    for index, event in enumerate(events):
        if event.get("op") == "replaceHoleShots" and _int(event.get("hole")) == requested:
            result = (index, event)
    return result


def latest_hole_fact_snapshot(events: list[dict[str, Any]], hole: int) -> tuple[int, dict[str, Any]] | None:
    """Return the latest geometry-independent whole-hole fact snapshot for this hole."""
    requested = _int(hole)
    result: tuple[int, dict[str, Any]] | None = None
    for index, event in enumerate(events):
        if event.get("op") == "replaceHoleFacts" and _int(event.get("hole")) == requested:
            result = (index, event)
    return result


def latest_hole_snapshot(events: list[dict[str, Any]], hole: int) -> tuple[int, dict[str, Any]] | None:
    """Latest whole-hole snapshot of either kind; a newer fact snapshot overrides an old pixel one."""
    requested = _int(hole)
    result: tuple[int, dict[str, Any]] | None = None
    for index, event in enumerate(events):
        if (
            event.get("op") in {"replaceHoleShots", "replaceHoleFacts"}
            and _int(event.get("hole")) == requested
        ):
            result = (index, event)
    return result


def reorder_map(events: list[dict[str, Any]]) -> dict[str, int]:
    """落点顺序覆盖:最后一条 reorderShot 的 shotId→位次;无则 {}(shotmap 排序时:有覆盖用覆盖)。"""
    order: list[str] = []
    for e in events:
        if e.get("op") == "reorderShot" and isinstance(e.get("order"), list):
            order = [str(s) for s in e["order"]]
    return {sid: i for i, sid in enumerate(order)}
