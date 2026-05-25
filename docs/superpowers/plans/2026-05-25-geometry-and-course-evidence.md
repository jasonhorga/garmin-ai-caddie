# Geometry And Course Evidence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn existing prodgeometry validation into a tested evidence layer for course, hole, shot surface, hazards, and missing-geometry confidence.

**Architecture:** Add a lightweight geometry evidence module over existing `hazard_path()`, `mesh_path()`, and analysis helpers. Do not rewrite the prodgeometry decoder in this plan.

**Tech Stack:** Python 3.12, existing prodgeometry JSON outputs, FastAPI.

---

## Files

Create:

- `ai_caddie/geometry_evidence.py`
- `tests/test_geometry_evidence.py`
- `server_v2/geometry.py`
- `tests/test_server_v2_geometry.py`

Modify:

- `server_v2/models.py`
- `server_v2/main.py`
- `tests/test_server_v2_health.py`

## Task 1: Evidence Model

- [ ] Write tests for:
  - missing geometry returns `coverage="missing"`
  - fixture geometry row returns hazard/mesh path refs without exposing absolute secret paths
  - shot surface classification degrades when meshes are absent
- [ ] Implement `ai_caddie/geometry_evidence.py` with:
  - `geometry_coverage_for_hole(global_id, local_hole)`
  - `geometry_coverage_for_course(global_id, holes=range(1, 19))`
  - `build_hole_geometry_evidence(round_row)`
- [ ] Return contract:

```python
{
  "schema": "ai-caddie-geometry-evidence-v1",
  "globalId": 31795,
  "localHole": 2,
  "coverage": "ready|partial|missing",
  "hasHazards": true,
  "hasMeshes": true,
  "evidence": [],
  "missingData": []
}
```

- [ ] Run:

```bash
uv run python -m unittest tests.test_geometry_evidence -v
```

- [ ] Commit:

```bash
git add ai_caddie/geometry_evidence.py tests/test_geometry_evidence.py
git commit -m "feat: add geometry evidence layer"
```

## Task 2: Geometry Coverage API

- [ ] Add `GET /api/v2/geometry/course/{global_id}/coverage`.
- [ ] Add `GET /api/v2/geometry/hole/{global_id}/{local_hole}`.
- [ ] Tests must patch filesystem paths or use temp dirs; no live prodgeometry download.
- [ ] Add service index entries:
  - `geometryCourseCoverage`
  - `geometryHoleEvidence`
- [ ] Run:

```bash
uv run python -m unittest tests.test_server_v2_geometry tests.test_server_v2_health -v
```

- [ ] Commit:

```bash
git add server_v2/geometry.py server_v2/models.py server_v2/main.py tests/test_server_v2_geometry.py tests/test_server_v2_health.py
git commit -m "feat: expose geometry evidence API"
```

## Task 3: Course/Hole Stats Integration

- [ ] Add geometry coverage summary to `ai_caddie/history_stats.py` courses and holes.
- [ ] Tests assert fixture rows include `geometryCoverage` with `missing|partial|ready`.
- [ ] Missing geometry must not fail stats.
- [ ] Run:

```bash
uv run python -m unittest tests.test_history_stats_core tests.test_geometry_evidence -v
```

- [ ] Commit:

```bash
git add ai_caddie/history_stats.py tests/test_history_stats_core.py
git commit -m "feat: include geometry coverage in history stats"
```

## Task 4: Verification

- [ ] Run backend full tests.
- [ ] Run `py_compile` on geometry modules.
- [ ] HTTP smoke:

```bash
curl -s http://127.0.0.1:9000/api/v2/geometry/course/31795/coverage | uv run python -m json.tool
```
