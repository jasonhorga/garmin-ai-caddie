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
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import UTC, datetime
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


def _corrections_path(player_id: str, round_ref: str, root: Path | str | None = None) -> Path:
    safe = _SAFE_REF.sub("_", str(round_ref)) or "round"
    return _root(root) / "data" / "players" / str(player_id) / "corrections" / f"{safe}.jsonl"


def load_correction_events(player_id: str, round_ref: str, *, root: Path | str | None = None) -> list[dict[str, Any]]:
    path = _corrections_path(player_id, round_ref, root)
    if not path.exists():
        return []
    events: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return events


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


def append_correction(
    player_id: str, round_ref: str, event: dict[str, Any], *, root: Path | str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """追加一条修改事件(幂等 on clientMutationId)。返回落库后的事件(带 seq/ts)。"""
    _validate(event)
    existing = load_correction_events(player_id, round_ref, root=root)
    cmid = event.get("clientMutationId")
    if cmid:
        for e in existing:
            if e.get("clientMutationId") == cmid:
                return e  # 幂等:重复提交返回已存的那条,不写重复
    stored = {k: v for k, v in event.items() if v is not None or k == "value"}
    stored["seq"] = len(existing) + 1
    stored["ts"] = (now or datetime.now(UTC)).isoformat()
    path = _corrections_path(player_id, round_ref, root)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(stored, ensure_ascii=False) + "\n")
    return stored


# ---------------------------------------------------------------------------
# apply(纯函数):把事件盖到原始 shot 列表上
# ---------------------------------------------------------------------------
def _int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def apply_corrections(shots: list[dict[str, Any]], events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """删=去掉该 shotId;改=把 club→clubName / lie→start.lie 覆盖掉(带 provenance)。
    最后一次操作胜出(op 日志按序回放)。孤儿 shotId 对不上就跳过、不报错。"""
    if not events:
        return shots
    deleted: dict[str, bool] = {}       # shotId -> 是否已删(restoreShot 可翻回来)
    edits: dict[str, dict[str, Any]] = {}  # shotId -> {field: value}
    for e in events:
        op = e.get("op")
        sid = e.get("shotId")
        if op == "deleteShot" and sid:
            deleted[sid] = True
        elif op == "restoreShot" and sid:
            deleted[sid] = False
        elif op == "editField" and sid and e.get("field") in EDITABLE_FIELDS:
            edits.setdefault(sid, {})[e["field"]] = e.get("value")

    out: list[dict[str, Any]] = []
    for shot in shots:
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
        elif op == "replaceHoleShots" and _int(e.get("hole")) == h:
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


def reorder_map(events: list[dict[str, Any]]) -> dict[str, int]:
    """落点顺序覆盖:最后一条 reorderShot 的 shotId→位次;无则 {}(shotmap 排序时:有覆盖用覆盖)。"""
    order: list[str] = []
    for e in events:
        if e.get("op") == "reorderShot" and isinstance(e.get("order"), list):
            order = [str(s) for s in e["order"]]
    return {sid: i for i, sid in enumerate(order)}
