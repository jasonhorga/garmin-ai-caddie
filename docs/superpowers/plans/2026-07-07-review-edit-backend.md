# 复盘编辑 — 后端 op 扩展 实现计划

> **2026-07-16 AUTHORITY CORRECTION — HISTORICAL IMPLEMENTATION PLAN：**本计划不再是 domain contract 或实施授权。其 `addShot` 示例把同一个 `lie` 同时写入 `start.lie` 与 `endLie`，违反 L06“startLie 描述本杆起始球位、endLie 独立”；后续实现必须按当前 canonical contract 重写。现行裁决见[Watch 决策账本](../../reviews/2026-07-15-watch-decision-and-task-tracker.md)与[全仓 Owner-gate 审计](../../reviews/2026-07-16-repository-wide-owner-gate-authority-and-drift-audit.md)。

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 给已有的复盘 op-based 修改层补上「加杆 / 拖动改位置 / 手动重排」三个操作 + 像素↔世界坐标逆投影,让 iOS 满屏编辑有可用的后端(网页仍只读)。

**Architecture:** 复用 #250/#263/#265 的修改层。**纯逻辑**(校验、重排的顺序覆盖)进 `round_corrections.py`;**要几何的**(加杆按像素反投影成世界坐标、拖动改坐标)进 `build_round_hole_shot_map`(它已加载该洞投影)。加杆造一杆合成落点、插进顺序,shotmap 按序画线就自动连上前后。iOS 送**像素**(点/拖的位置),后端反投影成 lat/lon 存,和 Garmin 原始杆同坐标空间、统一。

**Tech Stack:** Python 3.12,PIL/numpy 几何,FastAPI,unittest(CI 权威;Tokyo `uv run python -m unittest` 预验)。

## Global Constraints

- 测试框架 **unittest**(非 pytest);见 [[ci-uses-unittest-not-pytest]]。CI 权威,Tokyo 预验:`cd <repo> && uv run python -m unittest discover -s tests`。
- **不造假**:推测/手填的东西只按用户明确操作落库;球杆推测只做默认高亮不写死(本计划不碰球杆推测,那在 iOS 侧);删除不写原因、不做撤销(负责人定,§8)。
- **按人隔离**:所有 op 写调用者自己的修改日志(端点已 member-scoped,过路由护栏 `test_codex_sec2`);新增字段不改这一点。
- **永不变砖**:加杆必须能作用在"空洞"(该洞 0 杆)上——apply 不能假设至少有一杆。
- 设计文档:`docs/superpowers/specs/2026-07-07-review-edit-ui-design.md`(funnel `/edit.html`),§10 列了这四样。
- 现有地基:`ai_caddie/rounds/round_corrections.py`(`VALID_OPS` 含 `addShot` 但 apply 未实现;`apply_corrections` 现只处理 delete/restore/editField(club·lie));`round_shot_map.build_round_hole_shot_map(data, ref, hole, corrections=)` 按 `order` 排、投影、画线;`shot_projection.project_world_to_pixel(lat, lon, *, ref_lat, ref_lon, to_px)` = `to_px(world_to_local(...))`;`hole_render.overlay_projector(by, route)` 返回 `to_px((localx,localy))->(px,py)`。

---

## File Structure

- **Modify** `ai_caddie/geometry/hole_render.py` — `overlay_projector` 旁加一个 `overlay_unprojector(by, route)` 返回 `from_px((px,py))->(localx,localy)`(现有 `project` 仿射的逆)。
- **Modify** `ai_caddie/geometry/shot_projection.py` — 加 `pixel_to_world(px, py, *, ref_lat, ref_lon, from_px)`(= `local_to_world(from_px((px,py)))`),`project_world_to_pixel` 的逆;若无 `local_to_world` 则一并加(`world_to_local` 的逆)。
- **Modify** `ai_caddie/rounds/round_corrections.py` — `_validate` 认 `addShot`(要 px+club/lie+insertAfterShotId)、`editField field="position"`(要 px)、`reorderShot`(要 order 列表);`apply_corrections` 加 `reorderShot` 的顺序覆盖 + `editField position` 记录待改坐标(纯部分)。
- **Modify** `ai_caddie/rounds/round_shot_map.py` — `build_round_hole_shot_map` 里:纯 apply 后,用逆投影处理 `addShot`(px→world 造合成杆插进序)与 `editField position`(px→world 改坐标);应用 `reorderShot` 的顺序。
- **Modify** `server_v2/models.py` — `RoundCorrectionRequest` 加可选字段 `px: list[float] | None`、`insertAfterShotId: str | None`、`order: list[str] | None`。
- **Test** `tests/test_projection_roundtrip.py`(新)、`tests/test_round_corrections.py`(扩)、`tests/test_round_shot_map_corrections.py`(扩)。

---

## Task 1: 像素→世界坐标 逆投影

**Files:**
- Modify: `ai_caddie/geometry/hole_render.py`(加 `overlay_unprojector`)
- Modify: `ai_caddie/geometry/shot_projection.py`(加 `pixel_to_world` + 必要的 `local_to_world`)
- Test: `tests/test_projection_roundtrip.py`

**Interfaces:**
- Produces: `hole_render.overlay_unprojector(by, route) -> Callable[[tuple[float,float]], tuple[float,float]]`(px→local);`shot_projection.pixel_to_world(px, py, *, ref_lat, ref_lon, from_px) -> tuple[float,float]`(px→(lat,lon))。
- Consumes: 现有 `hole_render._frame`(给出 `project` 仿射 + `SS`)、`shot_projection.world_to_local`。

- [ ] **Step 1: 写 round-trip 失败测试**(用真几何,和现有 topo 测试同法软链几何)

```python
# tests/test_projection_roundtrip.py
from __future__ import annotations
import unittest
from ai_caddie.geometry import hole_render, shot_projection
from ai_caddie.courses import course_prep


class ProjectionRoundTripTests(unittest.TestCase):
    def test_world_to_px_to_world_is_identity(self):
        gid, hole = 2625, 1
        md, by = hole_render.load_mesh(gid, hole)
        route, _rlen = course_prep.derive_route(md)
        to_px = hole_render.overlay_projector(by, route)
        from_px = hole_render.overlay_unprojector(by, route)
        ref_lat = float((md.get("hole") or {})["RefLat"])
        ref_lon = float((md.get("hole") or {})["RefLon"])
        lat0, lon0 = ref_lat + 0.0009, ref_lon + 0.0007  # ~100m off the ref, on the hole
        px, py = shot_projection.project_world_to_pixel(lat0, lon0, ref_lat=ref_lat, ref_lon=ref_lon, to_px=to_px)
        lat1, lon1 = shot_projection.pixel_to_world(px, py, ref_lat=ref_lat, ref_lon=ref_lon, from_px=from_px)
        # 回到 <0.5m(纬度 1e-5 度 ≈ 1.1m,所以 5e-6 度足够严)
        self.assertAlmostEqual(lat0, lat1, delta=5e-6)
        self.assertAlmostEqual(lon0, lon1, delta=5e-6)
```

- [ ] **Step 2: 跑,确认失败**

Run: `cd <repo> && uv run python -m unittest tests.test_projection_roundtrip -v`(需软链几何:`mkdir -p output && ln -s <主 checkout>/output/prodgeometry output/prodgeometry`,同 topo 测试)
Expected: FAIL(`overlay_unprojector` / `pixel_to_world` 未定义)。

- [ ] **Step 3: 实现逆**

`hole_render._frame` 的 `project((x,y))` 是仿射(平移+缩放,可能带旋转)。在 `overlay_projector` 旁加:

```python
def overlay_unprojector(by, route):
    """overlay_projector 的逆:post-downsample 像素 (px,py) → 本地 2D 米 (x,y)。"""
    project, _sc, _w, _h, _margin = _frame(by, route)
    # project 是仿射。用三个已知点(原点、+X 单位、+Y 单位)求出 2x2 线性 + 平移,再解逆。
    import numpy as np
    o = np.array(project((0.0, 0.0)))           # 像素(未 /SS)
    ex = np.array(project((1.0, 0.0))) - o       # +1m local x → 像素向量
    ey = np.array(project((0.0, 1.0))) - o
    M = np.column_stack([ex, ey])                # 2x2:local→px(未 /SS)
    Minv = np.linalg.inv(M)

    def from_px(pt):
        p = np.array([pt[0] * SS, pt[1] * SS]) - o  # 还原 *SS,减平移
        xy = Minv @ p
        return (float(xy[0]), float(xy[1]))
    return from_px
```

`shot_projection.py` 加(若无 `local_to_world` 就照 `world_to_local` 的逆写):

```python
def local_to_world(x: float, y: float, *, ref_lat: float, ref_lon: float) -> tuple[float, float]:
    """world_to_local 的逆:本地米 (x,y) → (lat,lon)。与 world_to_local 用同一等距近似。"""
    # 读 world_to_local 的实现,严格取其逆(通常:x=东向米、y=北向米;
    # lat = ref_lat + (y_north / 111320); lon = ref_lon + (x_east / (111320*cos(ref_lat))))
    # —— 实现时以 world_to_local 的实际公式为准,round-trip 测试兜底。
    ...

def pixel_to_world(px: float, py: float, *, ref_lat: float, ref_lon: float, from_px) -> tuple[float, float]:
    x, y = from_px((px, py))
    return local_to_world(x, y, ref_lat=ref_lat, ref_lon=ref_lon)
```

> 实现 `local_to_world` 时**必须读 `world_to_local` 的真实公式取严格逆**(别照抄上面注释的通用式);round-trip 测试(Step 1)是正确性判据。

- [ ] **Step 4: 跑,确认通过**

Run: `uv run python -m unittest tests.test_projection_roundtrip -v`
Expected: PASS。

- [ ] **Step 5: 提交**

```bash
git add ai_caddie/geometry/hole_render.py ai_caddie/geometry/shot_projection.py tests/test_projection_roundtrip.py
git commit -m "feat(复盘编辑): 像素→世界坐标逆投影(round-trip 校验)"
```

---

## Task 2: `reorderShot`(手动重排,纯逻辑)

**Files:**
- Modify: `ai_caddie/rounds/round_corrections.py`
- Modify: `ai_caddie/rounds/round_shot_map.py`
- Test: `tests/test_round_corrections.py`

**Interfaces:**
- Produces: `round_corrections.reorder_map(events) -> dict[str, int]`(shotId → 覆盖后的顺序位;最后一条 `reorderShot` 胜出);`build_round_hole_shot_map` 排序时:有覆盖用覆盖、否则用 raw `order`,**稳定 shotId 不变**。
- Op 形状:`{"op": "reorderShot", "order": ["s:1:5", "s:1:3", ...]}`(该洞落点的目标顺序,按 shotId 列出)。

- [ ] **Step 1: 写失败测试**

```python
# 追加到 tests/test_round_corrections.py
class ReorderTests(unittest.TestCase):
    def test_reorder_map_last_wins(self):
        events = [
            {"op": "reorderShot", "order": ["a", "b", "c"]},
            {"op": "reorderShot", "order": ["c", "a", "b"]},
        ]
        self.assertEqual(rc.reorder_map(events), {"c": 0, "a": 1, "b": 2})

    def test_reorder_map_empty(self):
        self.assertEqual(rc.reorder_map([]), {})

    def test_validate_reorder_requires_order_list(self):
        with self.assertRaises(rc.CorrectionError):
            rc.append_correction("me", "42", {"op": "reorderShot"})  # 缺 order
```

- [ ] **Step 2: 跑,确认失败** — `uv run python -m unittest tests.test_round_corrections -v` → FAIL(`reorder_map` 未定义 / 校验没拦)。

- [ ] **Step 3: 实现** — `round_corrections.py`:`_validate` 加 `if op == "reorderShot" and not isinstance(event.get("order"), list): raise CorrectionError("reorderShot 需要 order 列表")`;加

```python
def reorder_map(events: list[dict[str, Any]]) -> dict[str, int]:
    """最后一条 reorderShot 的 shotId→位次;无则 {}。"""
    order: list[str] = []
    for e in events:
        if e.get("op") == "reorderShot" and isinstance(e.get("order"), list):
            order = [str(s) for s in e["order"]]
    return {sid: i for i, sid in enumerate(order)}
```

`round_shot_map.build_round_hole_shot_map`:排序前算 `rmap = round_corrections.reorder_map(corr)`,把 `key=lambda s: _int(s.get("order")) or 0` 换成:

```python
        rmap = round_corrections.reorder_map(corr)
        shots = sorted(
            (s for s in data.shots if str(s.get("scorecardId")) in round_ids and _int(s.get("hole")) == hole),
            key=lambda s: (rmap.get(round_corrections.mint_shot_id(s), 10_000 + (_int(s.get("order")) or 0))),
        )
```

(有覆盖用覆盖位次;没覆盖的排在覆盖项之后、内部仍按 raw order。)

- [ ] **Step 4: 跑,确认通过 + 现有 shotmap 测试不回归** — `uv run python -m unittest tests.test_round_corrections tests.test_round_shot_map tests.test_round_shot_map_corrections -v` → PASS。

- [ ] **Step 5: 提交** — `git commit -m "feat(复盘编辑): reorderShot 顺序覆盖(纯逻辑,稳定 shotId)"`

---

## Task 3: `addShot`(点地图加一杆,几何)

**Files:**
- Modify: `ai_caddie/rounds/round_corrections.py`(校验)
- Modify: `ai_caddie/rounds/round_shot_map.py`(apply:反投影 + 造合成杆 + 插序)
- Test: `tests/test_round_shot_map_corrections.py`

**Interfaces:**
- Op 形状:`{"op": "addShot", "px": [x, y], "club": "9号铁"|null, "lie": "fairway"|null, "insertAfterShotId": "s:1:3"|null}`(`insertAfterShotId=null` = 插在最前 / 空洞的第一杆)。
- `build_round_hole_shot_map`:纯 apply(删/改)后,对每条 `addShot`:`overlay_unprojector`→`pixel_to_world` 把 px 反投影成 (lat,lon);造一杆 `{"scorecardId": ref, "hole": hole, "id": <new>, "order": <插在 insertAfter 之后>, "start": <前杆落点或该点>, "end": {"lat","lon"}, "clubName": club, "start.lie"/"endLie": lie, "synthetic_manual": True}`;插进 shots 列表。shotmap 按序画线自动连前后。**空洞也能加**(shots 为空时直接成第一杆)。

- [ ] **Step 1: 写失败测试**(几何 mock 里加 `overlay_unprojector` + `pixel_to_world`)

```python
# tests/test_round_shot_map_corrections.py 追加;_geometry_mocks 补 unprojector/pixel_to_world
class AddShotTests(unittest.TestCase):
    def test_add_shot_inserts_between_and_appears_in_output(self):
        shots = [
            {"id": 1, "scorecardId": "r1", "hole": 1, "order": 1, "clubName": "一号木", "type": "TEE",
             "start": {"lat": 40.0, "lon": 116.5, "lie": "TeeBox"}, "end": {"lat": 40.02, "lon": 116.5}},
            {"id": 2, "scorecardId": "r1", "hole": 1, "order": 2, "clubName": "推杆",
             "start": {"lat": 40.03, "lon": 116.5, "lie": "Green"}, "end": {"lat": 40.03, "lon": 116.5}},
        ]
        corr = [{"op": "addShot", "px": [360, 500], "club": "七号铁", "lie": "fairway", "insertAfterShotId": "s:r1:1"}]
        out = self._build(corr, shots=shots)
        clubs = [s.get("club") for s in out["shots"]]
        # 新的一杆(七号铁)出现在 一号木 和 推杆 之间
        self.assertIn("七号铁", clubs)
        self.assertLess(clubs.index("七号铁"), clubs.index("推杆"))

    def test_add_shot_on_empty_hole_does_not_crash(self):
        corr = [{"op": "addShot", "px": [360, 500], "club": "七号铁", "lie": "fairway", "insertAfterShotId": None}]
        out = self._build(corr, shots=[])  # 空洞:永不变砖
        self.assertTrue(any(s.get("club") == "七号铁" for s in out["shots"]))
```

- [ ] **Step 2: 跑,确认失败** — FAIL(addShot 未被 apply)。

- [ ] **Step 3: 实现** — `round_corrections._validate`:`if op == "addShot" and not (isinstance(event.get("px"), list) and len(event["px"]) == 2): raise CorrectionError("addShot 需要 px=[x,y]")`。

在 `round_shot_map.build_round_hole_shot_map` 里,拿到 `to_px`/`by`/`route`/`ref_lat`/`ref_lon` 之后、投影各杆之前,插入合成杆:

```python
    from_px = hole_render.overlay_unprojector(by, route)
    _added = 0
    for e in corr:
        if e.get("op") != "addShot":
            continue
        px = e.get("px") or []
        if len(px) != 2:
            continue
        lat, lon = shot_projection.pixel_to_world(float(px[0]), float(px[1]), ref_lat=ref_lat, ref_lon=ref_lon, from_px=from_px)
        after = e.get("insertAfterShotId")
        idx = 0
        if after:
            for i, s in enumerate(shots):
                if round_corrections.mint_shot_id(s) == after:
                    idx = i + 1
                    break
        prev = shots[idx - 1] if idx > 0 else None
        start = dict(prev.get("end") or {}) if prev else {"lat": lat, "lon": lon}
        synthetic = {
            "id": f"m{_added}", "scorecardId": str(row.get("id")), "hole": hole,
            "order": (prev.get("order") if prev else 0),
            "start": {**start, "lie": e.get("lie")}, "end": {"lat": lat, "lon": lon},
            "endLie": e.get("lie"), "clubName": e.get("club"), "type": "MANUAL", "manualAdded": True,
        }
        shots.insert(idx, synthetic)
        _added += 1
```

(合成杆的 `id="m{n}"` 让 `mint_shot_id` 出 `s:{ref}:m{n}` 稳定;`order` 借前杆的,真正排序在 reorder/插入位置。插在 shots 列表的物理位置即顺序。)

- [ ] **Step 4: 跑,确认通过 + 全套回归** — `uv run python -m unittest tests.test_round_shot_map_corrections && uv run python -m unittest discover -s tests 2>&1 | grep -E "^Ran|^OK|FAILED"` → PASS + OK。

- [ ] **Step 5: 提交** — `git commit -m "feat(复盘编辑): addShot 点地图加杆(px 反投影+插序+自动连线;空洞不崩)"`

---

## Task 4: `editField position`(拖动改落点坐标,几何)

**Files:**
- Modify: `ai_caddie/rounds/round_corrections.py`(校验放行 field="position")
- Modify: `ai_caddie/rounds/round_shot_map.py`(apply:px→world 改该杆 end 坐标)
- Test: `tests/test_round_shot_map_corrections.py`

**Interfaces:**
- Op 形状:`{"op": "editField", "shotId": "s:r1:2", "field": "position", "value": [px_x, px_y]}`。
- apply(在 round_shot_map,需几何):对匹配 shotId 的杆,把 px 反投影成 (lat,lon) 写进它的 `end`(落点),重算距离/连线随之。

- [ ] **Step 1: 写失败测试**

```python
    def test_edit_position_moves_landing(self):
        shots = [{"id": 1, "scorecardId": "r1", "hole": 1, "order": 1, "clubName": "七号铁",
                  "start": {"lat": 40.0, "lon": 116.5, "lie": "Fairway"}, "end": {"lat": 40.02, "lon": 116.5}}]
        corr = [{"op": "editField", "shotId": "s:r1:1", "field": "position", "value": [400, 300]}]
        out = self._build(corr, shots=shots)
        # 落点像素应≈ mock 投影下 (400,300) 对应处;这里只断言"变了"(端点像素不等于原始投影)
        shot = next(s for s in out["shots"] if s.get("id") == "s:r1:1")
        self.assertIsNotNone(shot["end"])
```

- [ ] **Step 2: 跑,确认失败** — FAIL(现 `EDITABLE_FIELDS={club,lie}`,position 被 `_validate` 拦 / apply 不认)。

- [ ] **Step 3: 实现** — `round_corrections.py`:`EDITABLE_FIELDS` 加 `"position"`;但 `apply_corrections`(纯)对 `position` **不处理**(它要几何),只处理 club/lie(现状)。在 `round_shot_map.build_round_hole_shot_map`,纯 apply 后、投影前,处理 position:

```python
    pos_edits = {}  # shotId -> [px_x, px_y](最后一条胜出)
    for e in corr:
        if e.get("op") == "editField" and e.get("field") == "position" and e.get("shotId"):
            v = e.get("value") or []
            if len(v) == 2:
                pos_edits[e["shotId"]] = v
    if pos_edits:
        for s in shots:
            v = pos_edits.get(round_corrections.mint_shot_id(s))
            if v:
                lat, lon = shot_projection.pixel_to_world(float(v[0]), float(v[1]), ref_lat=ref_lat, ref_lon=ref_lon, from_px=from_px)
                s["end"] = {**(s.get("end") or {}), "lat": lat, "lon": lon, "posSource": "manual"}
```

(注:`apply_corrections` 的 `EDITABLE_FIELDS` 放行 position 让端点/校验通过,但 position 的实际生效在 round_shot_map;确保 `apply_corrections` 里 `if f in EDITABLE_FIELDS` 分支对 position 不误当 club/lie 覆盖——加 `and f in ("club","lie")` 守一下。)

- [ ] **Step 4: 跑,确认通过 + 全套回归** — PASS + OK。

- [ ] **Step 5: 提交** — `git commit -m "feat(复盘编辑): editField position 拖动改落点(px 反投影写坐标)"`

---

## Task 5: 端点/模型 接住新 op 形状

**Files:**
- Modify: `server_v2/models.py`(`RoundCorrectionRequest`)
- Test: `tests/test_prepare_recent_api.py` 同目录新增 `tests/test_corrections_api_ops.py`(或扩现有 corrections API 测试)

**Interfaces:**
- `RoundCorrectionRequest` 加可选:`px: list[float] | None = None`、`insertAfterShotId: str | None = None`、`order: list[str] | None = None`。端点 `add_round_correction` 已 `body.model_dump()` 落库,新字段自动带上;`_validate` 已在前面几任务放行。

- [ ] **Step 1: 写失败测试**

```python
# tests/test_corrections_api_ops.py
from __future__ import annotations
import tempfile, unittest
from unittest import mock
from fastapi.testclient import TestClient
from server_v2.main import app
from ai_caddie.history import history as _history


class CorrectionsApiOpsTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._p = mock.patch.object(_history, "ROOT", __import__("pathlib").Path(self._tmp.name)); self._p.start()
    def tearDown(self):
        self._p.stop(); self._tmp.cleanup()

    def test_addshot_op_accepted_and_persisted(self):
        c = TestClient(app)
        r = c.post("/api/v2/history/rounds/42/corrections",
                   json={"op": "addShot", "px": [360, 500], "club": "七号铁", "lie": "fairway", "insertAfterShotId": "s:42:1"})
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.json()["stored"]["op"], "addShot")
        self.assertEqual(r.json()["stored"]["px"], [360, 500])

    def test_reorder_op_accepted(self):
        c = TestClient(app)
        r = c.post("/api/v2/history/rounds/42/corrections", json={"op": "reorderShot", "order": ["s:42:2", "s:42:1"]})
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.json()["stored"]["order"], ["s:42:2", "s:42:1"])
```

- [ ] **Step 2: 跑,确认失败** — FAIL(model 无 px/order 字段 → 被 Pydantic 丢弃或 422)。

- [ ] **Step 3: 实现** — `server_v2/models.py` 的 `RoundCorrectionRequest` 加:

```python
    px: list[float] | None = None
    insertAfterShotId: str | None = None
    order: list[str] | None = None
```

- [ ] **Step 4: 跑,确认通过 + 全套回归** — `uv run python -m unittest tests.test_corrections_api_ops && uv run python -m unittest discover -s tests 2>&1 | grep -E "^Ran|^OK|FAILED"` → PASS + OK。

- [ ] **Step 5: 提交** — `git commit -m "feat(复盘编辑): 端点/模型接住 addShot/reorderShot/position 字段"`

---

## Self-Review(对着 spec §10 核)

- §10-① addShot apply → Task 3 ✓;空洞不变砖 → Task 3 test_add_shot_on_empty_hole ✓。
- §10-② 改坐标(拖动)→ Task 4 ✓。
- §10-③ reorderShot 顺序覆盖 + 稳定 shotId 共存 → Task 2 ✓(覆盖用覆盖、否则 raw order,mint_shot_id 不变)。
- §10-④ 像素→世界逆投影 → Task 1 ✓(round-trip 校验)。
- 端点接住 → Task 5 ✓。
- **删除不写原因/不撤销**:现有 `deleteShot` 已支持(reason 可选、不发即无);iOS 不发 reason、不做撤销即可——**无需后端改**,本计划不含。✓
- **网页只读**:不改网页(#265 只读展示已上线)。✓
- **占位扫描**:Task 1 Step 3 的 `local_to_world` 要求"读 world_to_local 真实公式取逆"是明确指令 + round-trip 兜底,非占位;其余均有实码。
- **类型一致**:`overlay_unprojector`/`pixel_to_world`/`reorder_map` 在 Task 1/2/3/4 用法一致;op 字段 `px`/`order`/`insertAfterShotId` 在 model 与 apply 一致。

**留给后续 plan(iOS,本计划不含)**:满屏编辑模式 + 手势(空白点=加/按手柄=拖/点杆=弹框)+ 放大镜 + 落点列表重排 UI + 罚杆计数器 UI + 缺杆默认高亮;这些消费本计划的后端 op,靠 native-mobile CI 编译 + 快照验,真手感真机/TestFlight。
