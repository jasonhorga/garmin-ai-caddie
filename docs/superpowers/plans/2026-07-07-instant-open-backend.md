# 「打开即用」后端核心 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 新数据一落地(定时同步/手动记分/启动),后端自动把「最近一盘」要用的东西(这盘球场的球洞图 topo + 统计)提前渲好缓存,并把频率提到每小时——网页复盘 + 统计打开即秒开,用户零操作。

**Architecture:** 一个可复用的后端活 `prepare_recent_round(player_id)` = 定位最近一盘的球场+洞 → 预热这些洞的 topo(复用现有 `_prewarm_course_topo`,已自带"缓存命中即跳过") + 烤统计(复用现有 `warm_stats_cache`)。挂到三个自动触发点(启动 / 记分落地 / 新端点)+ `auto_sync.sh` 尾巴调用并提频到每小时。**幂等靠现有缓存天然实现**(topo 磁盘缓存 + 统计文件指纹),重跑零成本,无需额外标记。

**Tech Stack:** Python 3.12,FastAPI(`server_v2`),PIL/numpy 渲染,unittest(CI 权威),`uv run python -m unittest` Tokyo 预验。

## Global Constraints

- 测试框架 **unittest**(不是 pytest);CI 权威,Tokyo 用 `uv run python -m unittest discover -s tests` 预验。见 [[ci-uses-unittest-not-pytest]]。
- **绝不造假**:准备只是预填缓存,永不改变任何端点会产出的响应内容;任何失败都 swallow,**预热失败绝不能弄崩同步响应或后台线程**(镜像现有 `warm_stats_cache` 的 best-effort 语义)。
- **按人隔离**:`prepare_recent_round(player_id)` 用该玩家自己的数据;新端点 member-scoped、只准备调用者自己的最近一盘。见 [[multi-user-redesign]]。
- **新 POST 路由必须过路由护栏** `tests/test_codex_sec2.py::test_every_api_route_has_explicit_auth_policy`:归类到 `is_player_scoped_route`(写调用者自己分区,同 `POST /annotations`)。见 [[multi-user-redesign]] 的路由分类教训。
- 设计文档:`docs/superpowers/specs/2026-07-07-instant-open-design.md`(funnel `/instant.html`)。

---

## File Structure

- **Create** `ai_caddie/rounds/prepare_recent.py` — 定位最近一盘的 topo 目标 + 编排准备(纯逻辑,渲染/烤统计以参数注入 → 可测)。
- **Modify** `server_v2/main.py` — 新端点 `POST /api/v2/history/prepare-recent`;启动 lifespan + 记分落地处调用 prepare。
- **Modify** `server_v2/players_api.py` — `is_player_scoped_route` POST 分支加 `/history/prepare-recent`。
- **Modify** `ops/auto_sync.sh` — 同步尾巴 curl prepare-recent;cron 注释改每小时 + 成本回退说明。
- **Create** `tests/test_prepare_recent.py` — 纯逻辑单测(目标定位 + 编排 + best-effort)。

---

## Task 1: 定位「最近一盘」要预热的 topo 目标

**Files:**
- Create: `ai_caddie/rounds/prepare_recent.py`
- Test: `tests/test_prepare_recent.py`

**Interfaces:**
- Consumes: `ai_caddie.rounds.round_shot_map._geometry_target(row, hole) -> (gid|None, localHole)`(前后九感知,已存在);`HistoryData.rounds`(每 round 是 dict,含 `date`、`holePars` 字符串、course gid 字段)。
- Produces: `recent_round_topo_targets(data) -> list[tuple[int, list[int]]]`——最近一盘按物理球场 gid 分组的 `[(gid, [localHole,...]), ...]`;无可用数据返回 `[]`。

- [ ] **Step 1: 写失败测试**

```python
# tests/test_prepare_recent.py
from __future__ import annotations
import unittest
from ai_caddie.history.history import HistoryData
from ai_caddie.rounds import prepare_recent as pr


def _data(rounds):
    return HistoryData(raw_rounds=[], rounds=rounds, shots=[])


class RecentTargetsTests(unittest.TestCase):
    def test_newest_round_grouped_by_course(self):
        rounds = [
            {"id": "old", "date": "2026-06-01", "globalId": 111, "holePars": "4" * 9},
            {"id": "new", "date": "2026-07-05", "globalId": 222, "holePars": "4" * 18},
        ]
        targets = pr.recent_round_topo_targets(_data(rounds))
        # 最新那盘(222,18 洞);前九=222 本身,后九无 back gid → 也落 222,共 18 洞。
        self.assertEqual(len(targets), 1)
        gid, holes = targets[0]
        self.assertEqual(gid, 222)
        self.assertEqual(holes, list(range(1, 19)))

    def test_empty_history_returns_empty(self):
        self.assertEqual(pr.recent_round_topo_targets(_data([])), [])
```

- [ ] **Step 2: 跑测试,确认失败**

Run: `cd <repo> && uv run python -m unittest tests.test_prepare_recent -v`
Expected: FAIL,`ModuleNotFoundError: ai_caddie.rounds.prepare_recent` 或 `AttributeError: recent_round_topo_targets`。

- [ ] **Step 3: 写最小实现**

```python
# ai_caddie/rounds/prepare_recent.py
"""「打开即用」:准备「最近一盘」——定位最新那盘的球场+洞,预热 topo + 烤统计。
纯编排,渲染/烤统计以参数注入,best-effort(失败 swallow,绝不弄崩触发它的响应/线程)。"""
from __future__ import annotations

from typing import Any, Callable

from ai_caddie.history.history import HistoryData
from ai_caddie.rounds.round_shot_map import _geometry_target


def _newest_round(data: HistoryData) -> dict[str, Any] | None:
    rounds = [r for r in data.rounds if r.get("date")]
    if not rounds:
        return None
    return max(rounds, key=lambda r: str(r.get("date")))


def recent_round_topo_targets(data: HistoryData) -> list[tuple[int, list[int]]]:
    """最新一盘按物理球场 gid 分组的 [(gid, [localHole,...])];无数据 → []。"""
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
```

- [ ] **Step 4: 跑测试,确认通过**

Run: `uv run python -m unittest tests.test_prepare_recent -v`
Expected: PASS(2 tests)。

- [ ] **Step 5: 提交**

```bash
git add ai_caddie/rounds/prepare_recent.py tests/test_prepare_recent.py
git commit -m "feat(instant): 定位最近一盘的 topo 预热目标"
```

---

## Task 2: `prepare_recent_round` 编排(预热 topo + 烤统计,best-effort)

**Files:**
- Modify: `ai_caddie/rounds/prepare_recent.py`
- Test: `tests/test_prepare_recent.py`

**Interfaces:**
- Consumes: Task 1 的 `recent_round_topo_targets`;注入的 `prewarm(gid, holes)` 与 `warm_stats()`(生产环境分别是 `server_v2.main._prewarm_course_topo` 与 `server_v2.history_stats.warm_stats_cache`)。
- Produces: `prepare_recent_round(data, *, prewarm, warm_stats) -> dict`——返回 `{"courses": [gid...], "holes": <总洞数>}`;每步 best-effort(单洞/单步失败被 swallow,不抛)。

- [ ] **Step 1: 写失败测试**

```python
class PrepareOrchestrationTests(unittest.TestCase):
    def _data_one_course(self):
        return _data([{"id": "r", "date": "2026-07-05", "globalId": 222, "holePars": "4" * 3}])

    def test_prewarms_each_target_and_warms_stats(self):
        calls = []
        warmed = []
        out = pr.prepare_recent_round(
            self._data_one_course(),
            prewarm=lambda gid, holes: calls.append((gid, holes)),
            warm_stats=lambda: warmed.append(True),
        )
        self.assertEqual(calls, [(222, [1, 2, 3])])
        self.assertEqual(warmed, [True])
        self.assertEqual(out["courses"], [222])
        self.assertEqual(out["holes"], 3)

    def test_best_effort_prewarm_failure_does_not_crash_and_still_warms_stats(self):
        warmed = []
        def boom(gid, holes):
            raise RuntimeError("render blew up")
        out = pr.prepare_recent_round(
            self._data_one_course(), prewarm=boom, warm_stats=lambda: warmed.append(True),
        )
        self.assertEqual(warmed, [True])   # 统计照烤
        self.assertEqual(out["holes"], 3)  # 报告的是"目标"洞数

    def test_empty_history_is_a_noop(self):
        calls = []
        out = pr.prepare_recent_round(_data([]), prewarm=lambda *a: calls.append(a), warm_stats=lambda: None)
        self.assertEqual(calls, [])
        self.assertEqual(out, {"courses": [], "holes": 0})
```

- [ ] **Step 2: 跑测试,确认失败**

Run: `uv run python -m unittest tests.test_prepare_recent -v`
Expected: FAIL,`AttributeError: prepare_recent_round`。

- [ ] **Step 3: 写最小实现(追加到 prepare_recent.py)**

```python
import logging

logger = logging.getLogger(__name__)


def prepare_recent_round(
    data: HistoryData,
    *,
    prewarm: Callable[[int, list[int]], None],
    warm_stats: Callable[[], None],
) -> dict[str, Any]:
    """预热最近一盘的 topo + 烤统计。每步 best-effort。"""
    targets = recent_round_topo_targets(data)
    for gid, holes in targets:
        try:
            prewarm(gid, holes)
        except Exception:  # noqa: BLE001 - 预热 best-effort,绝不弄崩触发它的响应/线程
            logger.exception("topo prewarm failed for gid=%s", gid)
    try:
        warm_stats()
    except Exception:  # noqa: BLE001
        logger.exception("stats warm failed")
    return {"courses": [gid for gid, _ in targets], "holes": sum(len(h) for _, h in targets)}
```

- [ ] **Step 4: 跑测试,确认通过**

Run: `uv run python -m unittest tests.test_prepare_recent -v`
Expected: PASS(5 tests)。

- [ ] **Step 5: 提交**

```bash
git add ai_caddie/rounds/prepare_recent.py tests/test_prepare_recent.py
git commit -m "feat(instant): prepare_recent_round 编排(预热 topo + 烤统计,best-effort)"
```

---

## Task 3: 端点 + 挂三个触发点 + 路由护栏

**Files:**
- Modify: `server_v2/main.py`(端点 + lifespan 启动 + 记分落地处)
- Modify: `server_v2/players_api.py`(`is_player_scoped_route`)
- Test: `tests/test_prepare_recent_api.py`(新)+ 现有 `tests/test_codex_sec2.py` 必须仍绿

**Interfaces:**
- Consumes: `prepare_recent.prepare_recent_round`;`server_v2.main._prewarm_course_topo`;`server_v2.history_stats.warm_stats_cache`;`load_history_data(player_id)`(取该玩家 HistoryData)。
- Produces: `POST /api/v2/history/prepare-recent` → `{"schema": "ai-caddie-prepare-recent-v1", "queued": bool}`(fire-and-forget,BackgroundTasks);一个内部 `_prepare_recent_bg(player_id)` 供启动/记分/端点复用。

- [ ] **Step 1: 写失败测试(端点 fire-and-forget + 路由分类)**

```python
# tests/test_prepare_recent_api.py
from __future__ import annotations
import unittest
from fastapi.testclient import TestClient
from server_v2.main import app
from server_v2.players_api import is_player_scoped_route


class PrepareRecentApiTests(unittest.TestCase):
    def test_route_is_player_scoped(self):
        # 无 target-player、写调用者自己缓存 → member-scoped(过路由护栏)。
        self.assertTrue(is_player_scoped_route("POST", "/api/v2/history/prepare-recent"))

    def test_endpoint_returns_queued_shape(self):
        client = TestClient(app)
        resp = client.post("/api/v2/history/prepare-recent")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["schema"], "ai-caddie-prepare-recent-v1")
        self.assertIn("queued", body)
```

- [ ] **Step 2: 跑测试,确认失败**

Run: `uv run python -m unittest tests.test_prepare_recent_api -v`
Expected: FAIL(404 未注册 / `is_player_scoped_route` 返回 False)。

- [ ] **Step 3: 实现——`players_api.is_player_scoped_route` POST 分支加一行**

在 `server_v2/players_api.py` 的 `if m == "POST":` return 元组里,`reports/generate` 那条后面加(镜像 corrections 的加法):

```python
            or (path.startswith("/api/v2/reports/") and path.endswith("/generate"))
            # 「打开即用」准备最近一盘:写调用者自己的缓存分区,无 target-player → 自限,同 POST /annotations。
            or path == "/api/v2/history/prepare-recent"
```

- [ ] **Step 4: 实现——`server_v2/main.py` 加内部函数 + 端点**

在 `main.py`(靠近 `_prewarm_course_topo`)加:

```python
def _prepare_recent_bg(player_id: str) -> None:
    """后台准备最近一盘:预热其 topo + 烤统计。best-effort;绝不抛。"""
    from ai_caddie.history.history import load_history_data
    from ai_caddie.rounds.prepare_recent import prepare_recent_round
    from server_v2.history_stats import warm_stats_cache
    try:
        data = load_history_data(player_id=player_id)
    except Exception:
        logger.exception("prepare-recent: load history failed for %s", player_id)
        return
    prepare_recent_round(data, prewarm=_prewarm_course_topo, warm_stats=warm_stats_cache)
```

端点(放在 `history_summary` 附近):

```python
@app.post("/api/v2/history/prepare-recent")
def history_prepare_recent(
    background_tasks: BackgroundTasks, player_id: str = Depends(current_player_id)
) -> dict:
    """「打开即用」触发器:fire-and-forget 后台准备调用者的最近一盘(预热 topo + 烤统计),
    立即返回。定时同步尾巴 + 未来「拉一下最新」按钮都打这个。写调用者自己分区,member 可用。"""
    background_tasks.add_task(_prepare_recent_bg, player_id)
    return {"schema": "ai-caddie-prepare-recent-v1", "queued": True}
```

- [ ] **Step 5: 挂启动 + 记分落地**

lifespan 启动处(`warm_stats_cache_in_background()` 之后)追加 owner 预热:

```python
    warm_stats_cache_in_background()
    # 「打开即用」:启动即准备 owner 最近一盘(topo 预热在后台,失败 swallow)。
    import threading
    threading.Thread(target=_prepare_recent_bg, args=(OWNER_ID,), name="prepare-recent-boot", daemon=True).start()
```

记分落地处(`ingest_player_round` 里现有 `warm_stats_cache_in_background()` 附近,line ~1239 那处):在其后追加

```python
        background_tasks.add_task(_prepare_recent_bg, target_player_id)
```

(若该处 handler 无 `background_tasks` 形参,则改用 `threading.Thread(target=_prepare_recent_bg, args=(target_player_id,), daemon=True).start()`。实现时按现场签名二选一。)

- [ ] **Step 6: 跑测试(端点 + 路由护栏)**

Run: `uv run python -m unittest tests.test_prepare_recent_api tests.test_codex_sec2 -v`
Expected: PASS(端点 2 个 + 护栏 `test_every_api_route_has_explicit_auth_policy` 仍绿)。

- [ ] **Step 7: 全套回归**

Run: `uv run python -m unittest discover -s tests 2>&1 | tail -3`
Expected: `OK`(无回归)。

- [ ] **Step 8: 提交**

```bash
git add server_v2/main.py server_v2/players_api.py tests/test_prepare_recent_api.py
git commit -m "feat(instant): prepare-recent 端点 + 挂启动/记分触发 + 路由护栏归类"
```

---

## Task 4: `auto_sync.sh` 尾巴调用 + 提频每小时

**Files:**
- Modify: `ops/auto_sync.sh`

**说明:** shell 运维脚本,无单测;靠 Task 3 的端点测试 + 人工核对。改动最小、幂等安全(重跑靠缓存)。

- [ ] **Step 1: 同步成功后追加一发 prepare-recent**

在 `ops/auto_sync.sh` 现有 `curl … /api/v2/history/stats?window=$w` 循环之后追加:

```bash
# 「打开即用」:数据落地后,顺带准备最近一盘(预热其 topo,让复盘打开即秒开)。best-effort。
curl -sf -o /dev/null -m 300 -X POST "$API/api/v2/history/prepare-recent" || true
```

- [ ] **Step 2: cron 注释改每小时 + 成本回退说明**

把脚本顶部 crontab 示例从"北京 13:37/21:37 各一次"改为**每小时一次**,并加一行说明:

```bash
# crontab(UTC 机器,每小时一次;北京时间即每小时的 :37):
#   37 * * * * /home/ubuntu/claude-web-data/repo/garmin-ai-caddie/ops/auto_sync.sh
# 成本:多数是轻量增量拉;只有 cookie 过期才触发较重的 xvfb 自愈。若实测过重,
# 退回每 2–3 小时(如 `37 */2 * * *`)或只白天时段。见设计 §8-②。
```

> 注意:改 crontab 本身是**部署动作**(user-gated),这一步只改脚本里的**注释/文档**;真正把 cron 从两次改成每小时,等负责人在 homeserver 上手动改(见 [[homeserver-access]])。

- [ ] **Step 3: 提交**

```bash
git add ops/auto_sync.sh
git commit -m "ops(instant): 同步尾巴调用 prepare-recent + cron 提频每小时(文档)"
```

---

## Self-Review(对着 spec 核一遍)

**Spec 覆盖:**
- §2 触发器挂三个自动点 + 手动端点 → Task 3(启动/记分/端点)+ Task 4(同步尾巴);手动「拉一下」按钮的**端点**在 Task 3(按钮 UI 后续)。✓
- §2 提频每小时 → Task 4(脚本注释,真部署 user-gated)。✓
- §3 准备什么:烤统计(Task 2 warm_stats)+ 预热这盘 topo(Task 1/2)+ 逐杆复盘(网页复盘底图=topo,已随 topo 预热而秒开,§8-① 已核实旧图仅 0.48s、非瓶颈)。✓
- §4 不重复瞎算 → 靠现有 topo 磁盘缓存 + 统计指纹缓存天然幂等(计划 Architecture 已说明,`_prewarm_course_topo` 缓存命中即跳过)。✓
- §1 A 模式 → 本计划是"后端把缓存备好";"先给缓存后台刷"的客户端行为在现有读路径已是缓存优先,无需后端改。✓

**留给后续 plan(客户端,本计划不含,已在设计 §6/§7 标为后置):**
- iOS 复盘底图从旧图 `map.image` 换成预热好的 topo(更好看 + 更即时;现 0.48s 已可接受)。
- 首页「最近一盘」卡接**真实球道预览图** + 保证点进去秒开(iOS + 网页 UI)。
- 「拉一下最新」**按钮 UI**(端点已在 Task 3)。
- 每小时同步真实成本上线后观测(§8-②)。

**占位扫描:** 无 TBD/TODO;Task 3 Step 5 的"二选一"是明确的现场分支(按 handler 是否有 background_tasks 形参),非占位。

**类型一致:** `recent_round_topo_targets(data)->list[(int,[int])]`、`prepare_recent_round(data,*,prewarm,warm_stats)->dict` 在 Task 1/2/3 用法一致;端点 schema `ai-caddie-prepare-recent-v1` 一致。

**范围:** 单一后端子系统(准备+触发),各任务独立可测、可独立 review。客户端 UI 已拆出为后续 plan。
