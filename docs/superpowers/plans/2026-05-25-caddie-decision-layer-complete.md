# Caddie Decision Layer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expand the deterministic caddie decision layer into tee, approach, and recovery contracts with auditability.

**Architecture:** Keep deterministic decision logic in Python. AI explains decisions through the fact-bound review layer, but selected plans and confidence must come from structured facts.

**Tech Stack:** Python 3.12, existing `ai_caddie/decision.py`, unittest, FastAPI.

---

## Files

Modify:

- `ai_caddie/decision.py`
- `tests/test_decision_layer.py`

Create:

- `ai_caddie/decision_api.py`
- `server_v2/caddie.py`
- `tests/test_server_v2_caddie.py`

Modify:

- `server_v2/models.py`
- `server_v2/main.py`
- `tests/test_server_v2_health.py`

## Task 1: Decision Contract Versioning

- [ ] Add tests for decision payload schema:
  - `ai-caddie-decision-v2`
  - `shotType=tee|approach|recovery`
  - `options`
  - `selected`
  - `avoidZones`
  - `evidence`
  - `confidence`
  - `missingData`
  - `auditCriteria`
- [ ] Refactor existing decision output into that contract without removing current tests.
- [ ] Run:

```bash
uv run python -m unittest tests.test_decision_layer -v
```

- [ ] Commit:

```bash
git add ai_caddie/decision.py tests/test_decision_layer.py
git commit -m "feat: version caddie decision contract"
```

## Task 2: Approach And Recovery Decisions

- [ ] Add synthetic tests for:
  - approach with green/hazard evidence
  - recovery from rough or blocked view
  - missing geometry returns low confidence
  - low club sample returns missing data
- [ ] Implement `recommend_approach()` and `recommend_recovery()` in `ai_caddie/decision.py`.
- [ ] Use the same safe/stock/attack vocabulary across tee, approach, recovery.
- [ ] Run decision tests.
- [ ] Commit:

```bash
git add ai_caddie/decision.py tests/test_decision_layer.py
git commit -m "feat: add approach and recovery decisions"
```

## Task 3: Decision API

- [ ] Create `ai_caddie/decision_api.py` with `build_decision_request_from_fixture()` and request validation helpers.
- [ ] Add `POST /api/v2/caddie/decision`.
- [ ] Tests patch deterministic request data; no live GPS/geometry required.
- [ ] Endpoint returns 422 for invalid shot type.
- [ ] Run:

```bash
uv run python -m unittest tests.test_server_v2_caddie tests.test_decision_layer -v
```

- [ ] Commit:

```bash
git add ai_caddie/decision_api.py server_v2/caddie.py server_v2/models.py server_v2/main.py tests/test_server_v2_caddie.py tests/test_server_v2_health.py
git commit -m "feat: expose caddie decision API"
```

## Task 4: Decision Audit

- [ ] Add audit function:

```python
audit_decision(decision, actual_shot) -> dict
```

- [ ] Audit classifications:
  - `execution`
  - `strategy`
  - `info_gap`
  - `unknown`
- [ ] Tests cover player taking selected option, riskier option, and missing first shot.
- [ ] Commit:

```bash
git add ai_caddie/decision.py tests/test_decision_layer.py
git commit -m "feat: add decision audit classification"
```

## Task 5: Verification

- [ ] Run backend full tests.
- [ ] Run `py_compile` on decision modules and server endpoint.
