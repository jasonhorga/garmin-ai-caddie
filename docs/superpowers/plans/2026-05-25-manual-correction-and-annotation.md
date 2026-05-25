# Manual Correction And Annotation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add audit-safe manual notes, issue tags, corrections, and caddie feedback without mutating raw Garmin data.

**Architecture:** Store annotations as local JSON records under `data/annotations/` first. Derived stats read annotations through explicit aggregation rules, while raw snapshots remain immutable.

**Tech Stack:** Python 3.12, FastAPI, JSON storage, unittest.

---

## Files

Create:

- `ai_caddie/annotations.py`
- `tests/test_annotations.py`
- `server_v2/annotations.py`
- `tests/test_server_v2_annotations.py`

Modify:

- `server_v2/models.py`
- `server_v2/main.py`
- `tests/test_server_v2_health.py`

## Task 1: Annotation Store

- [ ] Tests cover creating:
  - round note
  - hole note
  - shot note
  - issue tag
  - club correction
  - lie correction
  - penalty correction
  - caddie feedback
- [ ] Implement append-only JSONL store:

```text
data/annotations/annotations.jsonl
```

- [ ] Each record includes:
  - `id`
  - `createdAt`
  - `targetType`
  - `targetId`
  - `kind`
  - `payload`
  - `source="manual"`
- [ ] Run:

```bash
uv run python -m unittest tests.test_annotations -v
```

- [ ] Commit:

```bash
git add ai_caddie/annotations.py tests/test_annotations.py
git commit -m "feat: add annotation store"
```

## Task 2: Annotation API

- [ ] Add:
  - `GET /api/v2/annotations`
  - `POST /api/v2/annotations`
  - `GET /api/v2/annotations/target/{target_type}/{target_id}`
- [ ] Tests use temp root and do not touch private data.
- [ ] POST validates target and kind.
- [ ] Run:

```bash
uv run python -m unittest tests.test_server_v2_annotations -v
```

- [ ] Commit:

```bash
git add server_v2/annotations.py server_v2/models.py server_v2/main.py tests/test_server_v2_annotations.py tests/test_server_v2_health.py
git commit -m "feat: expose annotation API"
```

## Task 3: Stats Integration

- [ ] Add annotation counts to `history_stats` data quality.
- [ ] Add issue tags from annotations into issue stats with `source="manual"`.
- [ ] Tests assert manual issue tags appear beside deterministic issue tags.
- [ ] Commit:

```bash
git add ai_caddie/history_stats.py tests/test_history_stats_core.py tests/test_annotations.py
git commit -m "feat: include annotations in derived stats"
```

## Task 4: Verification

- [ ] Run backend full tests.
- [ ] Run HTTP smoke for annotation create/list against temp test app or patched root.
