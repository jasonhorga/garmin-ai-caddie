"""「打开即用」:准备「最近一盘」—— 定位最新那盘的球场+洞,预热 topo + 烤统计。

纯编排:渲染(prewarm)与烤统计(warm_stats)以参数注入,便于测试。每步 best-effort
(失败 swallow),**绝不弄崩触发它的响应或后台线程**(镜像现有 warm_stats_cache 的语义)。
幂等靠现有缓存天然实现(topo 磁盘缓存命中即跳过 + 统计文件指纹),重跑零成本。
"""
from __future__ import annotations

import logging
from typing import Any, Callable

from ai_caddie.history.history import HistoryData
from ai_caddie.rounds.round_shot_map import _geometry_target

logger = logging.getLogger(__name__)


def _newest_round(data: HistoryData) -> dict[str, Any] | None:
    rounds = [r for r in data.rounds if r.get("date")]
    if not rounds:
        return None
    return max(rounds, key=lambda r: str(r.get("date")))


def recent_round_topo_targets(data: HistoryData) -> list[tuple[int, list[int]]]:
    """最新一盘按物理球场 gid 分组的 [(gid, [localHole,...])];无数据 → []。

    前后九感知(复用 round_shot_map._geometry_target):一场组合 18 洞可能落在两个 gid。
    """
    row = _newest_round(data)
    if row is None:
        return []
    n = len(str(row.get("holePars") or "")) or 18
    by_gid: dict[int, list[int]] = {}
    for hole in range(1, n + 1):
        gid, local = _geometry_target(row, hole)
        if gid is None:
            continue
        by_gid.setdefault(int(gid), []).append(int(local))
    return [(gid, holes) for gid, holes in by_gid.items()]


def prepare_recent_round(
    data: HistoryData,
    *,
    prewarm: Callable[[int, list[int]], None],
    warm_stats: Callable[[], None],
    ensure_geometry: Callable[[int, list[int]], None] | None = None,
) -> dict[str, Any]:
    """预热最近一盘的 topo + 烤统计。每步 best-effort。返回 {"courses": [...], "holes": N}。

    ``ensure_geometry(gid, holes)``(可选):在 prewarm 之前,把这盘缺的球道几何按需从 Garmin
    CourseView 取 + 解码下来(**新球场自动补**,以后复盘落点图就有几何了)。同样 best-effort,
    取不到(如 Garmin 已下架该球场 → 404)就留空、绝不崩。"""
    targets = recent_round_topo_targets(data)
    for gid, holes in targets:
        if ensure_geometry is not None:
            try:
                ensure_geometry(gid, holes)
            except Exception:  # noqa: BLE001 - 按需取几何 best-effort,绝不弄崩
                logger.exception("geometry ensure failed for gid=%s", gid)
        try:
            prewarm(gid, holes)
        except Exception:  # noqa: BLE001 - 预热 best-effort,绝不弄崩触发它的响应/线程
            logger.exception("topo prewarm failed for gid=%s", gid)
    try:
        warm_stats()
    except Exception:  # noqa: BLE001
        logger.exception("stats warm failed")
    return {"courses": [gid for gid, _ in targets], "holes": sum(len(h) for _, h in targets)}
