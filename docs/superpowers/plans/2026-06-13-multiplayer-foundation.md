# 多球员地基 + 手机局落库后端 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development(推荐)或 superpowers:executing-plans。Steps 用 checkbox(`- [ ]`)跟踪。需求来源:`docs/superpowers/specs/2026-06-13-multiplayer-foundation-design.md`。

**Goal:** 把单人产品扩成"个人+好友"的按人隔离本地库——每球员一套数据根 + 一条专属 bearer token 网址(无切换器),owner 用 admin token 管理球员;新增手机局落库后端(逐杆事件→Garmin 同构 scorecard+shots)。

**Architecture:** 数据按 `data/players/<id>/` 分根(owner=`me` 仍读既有扁平 `data/`,零迁移);加载层 `load_history_data(player_id)` 选根;访问层用 per-player bearer token 反查 player_id 严格作用域,admin token 仅管理;stats 缓存按 `(player_id, 指纹)` 隔离。访问模型为将来登录预留。

**Tech Stack:** Python 3.12 / FastAPI / unittest(CI=`unittest discover`,无 pytest);React 19+TS+Vite(web_v2,Node 24 @ `~/node24/bin`);uv。

> **环境硬规矩(每个执行者必读):** 后端测试 `uv run python -m unittest`;前端先 `export PATH="$HOME/node24/bin:$PATH"` 再 `npm test -- --run`/`npm run lint`/`npx tsc -b --noEmit`/`npm run test:e2e`。**绝不打印/提交 token/cookie/密钥。** 真实数据只读、勿拷进仓库。Playwright 截图遵低内存守则(可用内存≥600MB、单页单浏览器、不与 vitest 并行)。

---

## 文件结构(决定分解)

**后端新增:**
- `ai_caddie/players.py` — 球员注册表 + token(建/查/列/删/rotate;token 生成+哈希+反查)。**单一职责:球员身份与凭证。**
- `server_v2/players_api.py` — admin 管理端点 + 球员侧鉴权依赖 + 落库端点的响应构造。
- `ai_caddie/round_ingest.py` — 采集事件 → Garmin 同构 scorecard+shots 的转换 + 幂等落盘。

**后端修改:**
- `ai_caddie/history.py` — `load_raw_rounds/load_shot_history/load_history_data` 加 `player_id` 参数 + 选根逻辑 + owner 合并去重。
- `ai_caddie/stats_cache.py` — key 加 player 维度。
- `server_v2/main.py` — 历史类端点改为按 token 解析球员;挂 players_api 路由。

**前端修改/新增:**
- `web_v2/src/playerContext.ts`(新) — 从网址取 token、暴露当前球员。
- `web_v2/src/api.ts` — 所有请求带 player bearer token。
- `web_v2/src/App.tsx` — 无 token→提示页;顶部当前球员只读条。
- `web_v2/src/components/PlayerAdminPage.tsx`(新) — owner 管理页。
- `web_v2/src/components/InvalidLinkPage.tsx`(新) — 无效链接页。

**ops:** `ops/export_snapshot.py` — 纳入 `data/players/**`。

---

## Task 1: 球员注册表 + token 模块

**Files:**
- Create: `ai_caddie/players.py`
- Test: `tests/test_players.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_players.py
from __future__ import annotations
import unittest
from pathlib import Path
import tempfile
from ai_caddie import players


class PlayersRegistryTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        # owner registry is auto-seeded on first load
    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_first_load_seeds_owner_me(self) -> None:
        reg = players.load_registry(root=self.root)
        ids = [p["id"] for p in reg["players"]]
        self.assertIn("me", ids)
        owner = next(p for p in reg["players"] if p["id"] == "me")
        self.assertTrue(owner["isOwner"])

    def test_create_player_returns_plaintext_token_once(self) -> None:
        created = players.create_player("老王", root=self.root)
        self.assertTrue(created["id"].startswith("p_"))
        self.assertGreaterEqual(len(created["token"]), 43)  # 32 bytes urlsafe b64
        # registry stores only the hash, never plaintext
        reg = players.load_registry(root=self.root)
        row = next(p for p in reg["players"] if p["id"] == created["id"])
        self.assertNotIn("token", row)
        self.assertTrue(row["tokenHash"].startswith("sha256:"))

    def test_resolve_token_to_player_id(self) -> None:
        created = players.create_player("老王", root=self.root)
        self.assertEqual(players.resolve_token(created["token"], root=self.root), created["id"])
        self.assertIsNone(players.resolve_token("wrong-token", root=self.root))

    def test_rotate_token_invalidates_old(self) -> None:
        created = players.create_player("老王", root=self.root)
        rotated = players.rotate_token(created["id"], root=self.root)
        self.assertIsNone(players.resolve_token(created["token"], root=self.root))
        self.assertEqual(players.resolve_token(rotated["token"], root=self.root), created["id"])

    def test_delete_player_removes_and_blocks_owner(self) -> None:
        created = players.create_player("老王", root=self.root)
        players.delete_player(created["id"], root=self.root)
        self.assertIsNone(players.resolve_token(created["token"], root=self.root))
        with self.assertRaises(players.PlayerError):
            players.delete_player("me", root=self.root)
```

- [ ] **Step 2: 跑测试看它失败**

Run: `uv run python -m unittest tests.test_players -v`
Expected: FAIL（`ModuleNotFoundError: ai_caddie.players` 或属性缺失）

- [ ] **Step 3: 实现 `ai_caddie/players.py`**

```python
"""Player registry + per-player capability tokens (private, owner-issued)."""
from __future__ import annotations
import hashlib, json, secrets, shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ai_caddie.data import ROOT  # repo root; data/ lives under it

OWNER_ID = "me"


class PlayerError(Exception):
    pass


def _players_dir(root: Path | str | None) -> Path:
    base = Path(root) if root is not None else ROOT
    return base / "data" / "players"


def _registry_path(root: Path | str | None) -> Path:
    return _players_dir(root) / "registry.json"


def _hash_token(token: str) -> str:
    return "sha256:" + hashlib.sha256(token.encode("utf-8")).hexdigest()


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_registry(root: Path | str | None = None) -> dict[str, Any]:
    path = _registry_path(root)
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    reg = {
        "schema": "ai-caddie-players-v1",
        "players": [
            {"id": OWNER_ID, "name": "我", "isOwner": True, "createdAt": _now(),
             "avatar": None, "tokenHash": None, "tokenLast4": None},
        ],
    }
    _save_registry(reg, root)
    return reg


def _save_registry(reg: dict[str, Any], root: Path | str | None) -> None:
    path = _registry_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(reg, ensure_ascii=False, indent=2), encoding="utf-8")


def _issue_token() -> str:
    return secrets.token_urlsafe(32)


def create_player(name: str, *, avatar: str | None = None, root: Path | str | None = None) -> dict[str, Any]:
    reg = load_registry(root)
    pid = "p_" + secrets.token_hex(4)
    token = _issue_token()
    row = {"id": pid, "name": name, "isOwner": False, "createdAt": _now(),
           "avatar": avatar, "tokenHash": _hash_token(token), "tokenLast4": token[-4:]}
    reg["players"].append(row)
    _save_registry(reg, root)
    return {"id": pid, "name": name, "token": token}  # plaintext returned ONCE


def rotate_token(player_id: str, *, root: Path | str | None = None) -> dict[str, Any]:
    reg = load_registry(root)
    row = _find(reg, player_id)
    token = _issue_token()
    row["tokenHash"] = _hash_token(token)
    row["tokenLast4"] = token[-4:]
    _save_registry(reg, root)
    return {"id": player_id, "token": token}


def resolve_token(token: str | None, *, root: Path | str | None = None) -> str | None:
    if not token:
        return None
    target = _hash_token(token)
    for row in load_registry(root)["players"]:
        stored = row.get("tokenHash")
        if stored and secrets.compare_digest(stored, target):
            return row["id"]
    return None


def delete_player(player_id: str, *, root: Path | str | None = None) -> None:
    if player_id == OWNER_ID:
        raise PlayerError("owner cannot be deleted")
    reg = load_registry(root)
    _find(reg, player_id)  # raises if missing
    reg["players"] = [p for p in reg["players"] if p["id"] != player_id]
    _save_registry(reg, root)
    pdir = _players_dir(root) / player_id
    if pdir.exists():
        shutil.rmtree(pdir)


def _find(reg: dict[str, Any], player_id: str) -> dict[str, Any]:
    for row in reg["players"]:
        if row["id"] == player_id:
            return row
    raise PlayerError(f"unknown player {player_id}")
```

- [ ] **Step 4: 跑测试看通过**

Run: `uv run python -m unittest tests.test_players -v`
Expected: PASS（5 tests）

- [ ] **Step 5: 提交**

```bash
git add ai_caddie/players.py tests/test_players.py
git commit -m "feat(players): 球员注册表 + per-player capability token"
```

---

## Task 2: 按球员选数据根的加载层

**Files:**
- Modify: `ai_caddie/history.py`（`load_raw_rounds` :283、`load_shot_history` :380、`load_history_data` :432）
- Test: `tests/test_history_player_scope.py`

> 现状:三者无参,从模块级 ROOT 读 `data/scorecards`、`data/shots`、`data/summary.json`。改成接受 `player_id="me"`:`me` 读既有扁平 `data/`(零迁移);其它读 `data/players/<id>/`。

- [ ] **Step 1: 写失败测试**

```python
# tests/test_history_player_scope.py
from __future__ import annotations
import json, tempfile, unittest
from pathlib import Path
from unittest import mock
from ai_caddie import history


def _write_round(base: Path, rid: str, date: str, course: str, strokes: int) -> None:
    sc = base / "scorecards"; sc.mkdir(parents=True, exist_ok=True)
    (sc / f"{rid}.json").write_text(json.dumps({
        "id": rid, "date": date, "course": course, "strokes": strokes,
        "holePars": "4"*18, "holes": [{"number": n, "strokes": 4} for n in range(1, 19)],
        "hasShots": False, "shotStatus": "none",
    }), encoding="utf-8")


class HistoryPlayerScopeTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        _write_round(self.root / "data", "100", "2026-05-01T08:00:00", "Owner Course", 80)
        _write_round(self.root / "data" / "players" / "p_friend", "900",
                     "2026-05-02T08:00:00", "Friend Course", 95)
    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_me_reads_flat_data(self) -> None:
        with mock.patch.object(history, "ROOT", self.root):
            rounds = history.load_raw_rounds(player_id="me")
        self.assertEqual([r["id"] for r in rounds], ["100"])

    def test_friend_reads_player_dir(self) -> None:
        with mock.patch.object(history, "ROOT", self.root):
            rounds = history.load_raw_rounds(player_id="p_friend")
        self.assertEqual([r["id"] for r in rounds], ["900"])

    def test_default_is_me(self) -> None:
        with mock.patch.object(history, "ROOT", self.root):
            self.assertEqual(history.load_raw_rounds(), history.load_raw_rounds(player_id="me"))
```

> 注:若 `history.py` 内部不直接用名为 `ROOT` 的变量定位 scorecards,执行者先 grep 确认实际用的路径常量名,并把测试与实现里的 `ROOT`/路径拼接对齐(保持"me=扁平 data/、其它=data/players/<id>/"的语义不变)。

- [ ] **Step 2: 跑测试看失败**

Run: `uv run python -m unittest tests.test_history_player_scope -v`
Expected: FAIL（`load_raw_rounds() got unexpected keyword 'player_id'`）

- [ ] **Step 3: 实现选根**

在 `history.py` 顶部加 helper,并给三个函数加 `player_id` 参数:

```python
def _player_data_dir(player_id: str = "me"):
    # me 读既有扁平 data/(零迁移);其它读 data/players/<id>/
    base = ROOT / "data"
    return base if player_id == "me" else base / "players" / player_id

# load_raw_rounds(player_id="me"): 把内部对 data/scorecards 的定位改为
#   _player_data_dir(player_id) / "scorecards";summary.json 同理。
# load_shot_history(raw_rounds=None, player_id="me"): data/shots 同理改为
#   _player_data_dir(player_id) / "shots"。
# load_history_data(player_id="me"):
#   raw = load_raw_rounds(player_id=player_id)
#   shots = load_shot_history(raw, player_id=player_id)
#   return HistoryData(raw_rounds=raw, rounds=merge_same_day_halves(raw), shots=shots)
```

执行者按实际代码把"数据目录定位"集中过一遍(可能散在 `load_raw_rounds` 内的 glob);保证 `me` 行为与改前**逐字节一致**(回归)。

- [ ] **Step 4: 跑测试看通过 + 全量回归**

Run: `uv run python -m unittest tests.test_history_player_scope -v`
Expected: PASS
Run: `uv run python -m unittest discover`
Expected: 既有用例全绿(me 路径未回归)。

- [ ] **Step 5: 提交**

```bash
git add ai_caddie/history.py tests/test_history_player_scope.py
git commit -m "feat(history): 按 player_id 选数据根(me=扁平 data/,其它=players/<id>/)"
```

---

## Task 3: owner 合并去重(扁平 data/ + players/me/,Garmin 优先)

**Files:**
- Modify: `ai_caddie/history.py`（`load_raw_rounds` 的 me 分支)
- Test: `tests/test_history_owner_merge.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_history_owner_merge.py —— me 同时有扁平(garmin)和 players/me(manual)
# 1) 两边不同局 → 合并出现两局,各带 source
# 2) 同天同球场冲突 → garmin 优先,manual 被标 supersededBy 不计入
# (用上面的 _write_round 加 source 字段:扁平写 source="garmin",players/me 写 source="manual")
```

实现:`load_raw_rounds("me")` = 读扁平(标 `source` 缺省 `garmin`)+ 读 `players/me`(`source="manual"`),按 `(date[:10], courseKey)` 去重,冲突保留 garmin、给 manual 加 `supersededBy`;`merge_same_day_halves`/统计需跳过 `supersededBy` 的局(执行者确认下游过滤)。

- [ ] **Step 2-5:** 跑失败 → 实现 → `uv run python -m unittest tests.test_history_owner_merge discover` 全绿 → commit `feat(history): owner 合并扁平/手机补录局 + 同场去重(Garmin 优先)`。

---

## Task 4: stats 缓存按球员隔离

**Files:**
- Modify: `ai_caddie/stats_cache.py`（`_fingerprint` / `cached_load_history_data` / `clear`）
- Test: `tests/test_stats_cache_player.py`

- [ ] **Step 1: 写失败测试**

```python
# 两个球员各自 build_history_stats,缓存命中互不串(球员 A 改数据不影响 B 的命中);
# clear() 清空全部;启动预热只热 me(断言其它球员首次为未命中冷算)。
# 断言方式:patch 计数底层 build 次数,验证 (player_id, fingerprint) 维度命中。
```

实现:缓存 key 从单指纹改为 `(player_id, fingerprint)`;`cached_*`/`build` 包装接受 `player_id`,各球员独立条目;`_LOAD_DIRS` 按球员推导(me=扁平,其它=players/<id>)。

- [ ] **Step 2-5:** 失败→实现→`uv run python -m unittest tests.test_stats_cache_player discover`(注意 `tests/conftest.py` 的 autouse `stats_cache.clear()` 仍生效)→ commit `feat(cache): stats 缓存按 (player_id, 指纹) 隔离`。

---

## Task 5: 访问鉴权依赖(bearer→player,admin 闸门)

**Files:**
- Create: `server_v2/players_api.py`（鉴权依赖部分)
- Test: `tests/test_players_api_auth.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_players_api_auth.py
import os, unittest
from unittest import mock
from fastapi.testclient import TestClient
from ai_caddie import players
from server_v2.main import app


class PlayerAuthTests(unittest.TestCase):
    # 用 mock 让 players.resolve_token 在测试根上工作;private profile 开启
    def test_history_overview_requires_player_token(self) -> None:
        client = TestClient(app)
        r = client.get("/api/v2/history/overview")  # 无 token
        self.assertEqual(r.status_code, 401)

    def test_valid_player_token_scopes_to_that_player(self) -> None:
        # 建球员→拿 token→带 Authorization: Bearer 取 overview→200 且只含该球员
        ...

    def test_admin_endpoints_reject_player_token(self) -> None:
        # 用 player bearer 访问 /api/v2/admin/players → 401/403
        ...
```

- [ ] **Step 2-5:** 实现 FastAPI 依赖 `current_player_id()`:读 `Authorization: Bearer` 或 `?key=` → `players.resolve_token` → player_id;失败 401。`require_admin`(复用 `require_admin_token`)。失败→实现→测试通过→commit `feat(api): per-player bearer 鉴权依赖 + admin 闸门`。

---

## Task 6: 历史类端点按 token 作用域

**Files:**
- Modify: `server_v2/main.py`（history/overview|rounds|stats|drilldown、courses prep/prep-tips、reports 等)
- Test: 扩 `tests/test_players_api_auth.py` + 现有 history 端点测试

- [ ] **Step 1: 写失败测试** —— 球员 A 的 token 取 overview/rounds/stats 只见 A 的局;用 A token 取不到 B 的任何数据(B 的 roundId 不出现)。
- [ ] **Step 2-5:** 把这些端点签名加上 `player_id: str = Depends(current_player_id)`,并把 `load_history_data()`/`build_history_stats()` 调用透传 `player_id`(经 Task 2/4)。删除任何"调用方指定球员"的入口。失败→实现→`uv run python -m unittest discover` 全绿(注意既有端点测试可能需要在 private profile 下补 token,属台账迁移、只改鉴权不删行为断言)→ commit `feat(api): 历史类端点按 token 解析球员、严格隔离`。

---

## Task 7: owner 管理端点

**Files:**
- Modify: `server_v2/players_api.py` + 在 `server_v2/main.py` 挂路由
- Test: `tests/test_players_admin_api.py`

- [ ] **Step 1: 写失败测试** —— `POST /api/v2/admin/players {name}` 返回一次性 `token`+`url`,再 `GET /api/v2/admin/players` 列表**不含明文 token**(只 tokenLast4);`rotate-token` 使旧 token resolve 失败;`DELETE` 移除且 owner 不可删(400);全部需 admin token,缺失 401。
- [ ] **Step 2-5:** 实现 5 个 admin 端点(见 spec §5.3),`url` = `f"{request.base_url}p/{token}"`(或配置的公开前缀)。失败→实现→测试通过→commit `feat(api): owner 球员管理端点(建/列/改/rotate/删)`。

---

## Task 8: 手机局落库(事件→Garmin 同构 scorecard+shots)

**Files:**
- Create: `ai_caddie/round_ingest.py`
- Modify: `server_v2/main.py`（挂 `POST /api/v2/players/{id}/rounds`)
- Test: `tests/test_round_ingest.py` + `tests/test_round_ingest_api.py`

- [ ] **Step 1: 写失败测试(转换核心)**

```python
# tests/test_round_ingest.py
# 给一组事件(逐杆 location+club、score、putt、penalty;courseGlobalId、前后九、tee、teeTime)
# → ingest_round 落出:
#   scorecards/<rid>.json: id/date/course?/holePars/holes[].strokes/hasShots=True/source="manual"
#   shots/<rid>.json: 逐杆 {hole, club, lat, lon, ...} 与 Garmin shots schema 同构
# 断言:洞数、每洞 strokes=该洞 score 事件、shots 条数=location 事件数、source=manual。
# 幂等:同 idempotency_key 二次 ingest 不新增文件、返回同 rid。
```

执行者**先读** `data/shots/*.json` 与 `data/scorecards/*.json` 的真实字段(只读真实数据目录,勿拷贝坐标进仓库;或读 `ai_caddie/fixtures.py` 的同构样例),确保落出的 JSON 能被 `load_raw_rounds`/`load_shot_history`/`shot_projection` 正常消费。

- [ ] **Step 2: 跑失败** → `uv run python -m unittest tests.test_round_ingest -v`
- [ ] **Step 3: 实现 `round_ingest.py`** —— `ingest_round(player_id, events, meta, *, idempotency_key, root=None) -> dict`:校验事件 → 组装 holePars(来自 courseGlobalId 的 course_reference,缺则 None)、holes[].strokes、逐杆 shots(坐标半圆/度按现有 shot schema)→ 写入该球员数据根 → 增量更新 summary.json → `stats_cache.clear()`(或按球员失效)。`source="manual"`。
- [ ] **Step 4: 跑通** → 全绿。
- [ ] **Step 5: 提交** `feat(ingest): 手机采集事件→Garmin 同构 scorecard+shots(幂等)`

- [ ] **Step 6: API 测试 + 端点** —— `tests/test_round_ingest_api.py`:`POST /api/v2/players/{id}/rounds`(球员 bearer 时 `{id}` 须=token 球员,否则 403;owner admin 可给任意球员)→ 201 + round 摘要;`Idempotency-Key` 重复不重复落库;落库后该球员 `/history/overview` 多一局。实现端点(依赖 Task 5 鉴权 + Task 8 ingest)→ 全绿 → commit `feat(api): POST /players/{id}/rounds 落库端点(鉴权+幂等)`。

---

## Task 9: 备份纳入 players/

**Files:**
- Modify: `ops/export_snapshot.py`（`DATA_PATHS` 加 `Path("data")/"players"`)
- Test: `tests/test_export_snapshot.py`(若存在则扩;否则新建)

- [ ] **Step 1-5:** 写测试:导出 tar 含某球员的 `data/players/<id>/scorecards/*.json`;实现把 `data/players` 纳入(沿用既有目录遍历,跳过 symlink);全绿;commit `feat(ops): 快照纳入 data/players/**`。

---

## Task 10: 前端 token 解析 + 全请求带 token

**Files:**
- Create: `web_v2/src/playerContext.ts`
- Modify: `web_v2/src/api.ts`（getJson/postJson 带 `Authorization: Bearer <token>`)
- Test: `web_v2/src/playerContext.test.ts` + `api.test.ts` 扩

- [ ] **Step 1: 写失败测试**

```ts
// playerContext.test.ts —— 从 location 解析 token
// '/p/<tok>' 与 '?key=<tok>' 两种形式都取到 tok;都没有 → null。
// api.test.ts —— 设了 token 后,getJson 的请求头带 Authorization: Bearer <tok>。
```

- [ ] **Step 2-5:** 实现 `readPlayerToken()`(优先 path `/p/:token`,回退 `?key=`);`api.ts` 从 playerContext 取 token 注入 `Authorization`。失败→实现→`npm test -- --run`(Node24)→ commit `feat(web): 从网址解析 player token 并注入请求`。

---

## Task 11: 无效链接提示页

**Files:**
- Create: `web_v2/src/components/InvalidLinkPage.tsx`
- Modify: `web_v2/src/App.tsx`（无 token 或首个鉴权 401 → 渲染该页,不暴露任何球员信息)
- Test: `web_v2/src/components/InvalidLinkPage.test.tsx` + App.test 扩

- [ ] **Step 1-5:** 测试:无 token 时渲染「需要有效链接」页、不发数据请求、不显示任何球员名;实现;`npm test -- --run`;commit `feat(web): 无效/缺失链接的干净提示页`。

---

## Task 12: owner 管理页

**Files:**
- Create: `web_v2/src/components/PlayerAdminPage.tsx`
- Modify: `web_v2/src/api.ts`(admin players CRUD 调用)、`navigation.ts`/设置区入口
- Test: `web_v2/src/components/PlayerAdminPage.test.tsx`

- [ ] **Step 1-5:** 测试:列球员(名字+tokenLast4+局数/来源占比)、建球员后**显示一次性专属网址 + 复制**、rotate、删除(owner 不可删按钮禁用);**管理页不渲染任何人的成绩分析**;实现(admin token 来自现有 Settings/同步面板的 admin token 输入);`npm test -- --run`;commit `feat(web): owner 球员管理页(建/发链接/rotate/删)`。

---

## Task 13: 当前球员只读条 + 手动局标注

**Files:**
- Modify: `web_v2/src/App.tsx`(顶部只读"当前是谁")、`web_v2/src/components/RoundCard.tsx`/`HistoryTimeline.tsx`(`source==='manual'` 加「手动」chip)
- Test: 对应组件测试扩

- [ ] **Step 1-5:** 测试:顶部显示当前球员名/头像、**无下拉**;手动局渲染「手动」标、Garmin 局不渲染;实现(复用 W4a chip 样式);`npm test -- --run` + `npx tsc -b --noEmit` + `npm run lint`;commit `feat(web): 当前球员只读条 + 手动局标注`。

---

## Task 14: e2e 隔离走查

**Files:**
- Modify: `web_v2/e2e/history-visual.smoke.spec.ts`(或新 spec)
- 后端真实/mock:沿用现有 e2e 的 `mockApi` 模式,加 admin players + bearer 作用域 mock

- [ ] **Step 1-5:** 走查:owner 管理页建球员→拿到 `/p/<tok>` 网址→访问该网址只见该球员→(mock 落库一局)历史可见;用球员 A 的 token 看不到 B 的 roundId;无 token→提示页。内存预检后跑 `npm run test:e2e`(2 projects 绿)。commit `test(web): 多球员隔离 e2e 走查`。

---

## Task 15: 全量门禁 + 收口

- [ ] **Step 1:** 后端 `uv run python -m unittest discover` 全绿(含新用例;me 路径零回归)。
- [ ] **Step 2:** 前端(Node24)`npm test -- --run`、`npx tsc -b --noEmit`、`npm run lint`、内存预检后 `npm run test:e2e` 全绿。
- [ ] **Step 3:** `git status` 仅本期文件;真实数据未入库;无 token/密钥泄漏(grep 自查)。
- [ ] **Step 4:** 控制器真实数据视觉验收(起后端+web,Playwright 截图:某球员网址的概览/历史/管理页/无效链接页;低内存守则),肉眼过。
- [ ] **Step 5:** 提交收口 `chore(multiplayer): 阶段一门禁全绿`。

---

## Self-review

- **Spec 覆盖:** §3 存储→T2/T3;§3.2 注册表+token→T1;§4 来源/去重→T3;§5 访问模型→T5/T6,管理→T7,落库→T8;§6 引擎作用域→T2/T4/T6;§7 UI→T10-T13;§8 非目标(不写回 Garmin/不做登录)→本计划不含,符合;§9 备份→T9;§10 安全(token 哈希、compare_digest、隔离、403)→T1/T5/T6/T8;§11 登录预留→T5 的标准 bearer 模型天然满足。无遗漏。
- **占位扫描:** T3/T4/T5 的 Step 2-5 给的是精确契约 + 关键实现指引而非整段代码(因强依赖既有真实 schema/函数,执行者须先读真代码再落地);其余给了可直接跑的测试。无 TODO/TBD。
- **类型一致:** `player_id`(str)、`resolve_token`/`create_player`/`rotate_token`/`delete_player`/`load_registry` 签名跨 T1/T5/T7 一致;`source ∈ {garmin, manual}`、`supersededBy` 跨 T3/T8 一致;`ingest_round(player_id, events, meta, *, idempotency_key, root)` 跨 T8 一致。
