# Photo And Video Context Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Attach photo/video context to shot or hole records and analyze it as evidence with confidence, not automatic truth.

**Architecture:** Store media metadata and model findings separately. The AI provider layer supplies vision interpretation; deterministic caddie logic consumes only confirmed findings and confidence labels.

**Tech Stack:** Python 3.12, FastAPI multipart upload metadata, provider abstraction, local file storage for private use.

---

## Files

Create:

- `ai_caddie/media.py`
- `ai_caddie/vision_context.py`
- `tests/test_media_context.py`
- `tests/test_vision_context.py`
- `server_v2/media.py`
- `tests/test_server_v2_media.py`

Modify:

- `server_v2/models.py`
- `server_v2/main.py`
- `tests/test_server_v2_health.py`

## Task 1: Media Metadata Store

- [ ] Add tests for attach/list media metadata:
  - target type
  - target id
  - media kind: photo/video
  - local path
  - captured at
  - privacy state
- [ ] Store metadata under:

```text
data/media/media_index.jsonl
```

- [ ] Do not store binary bytes in JSONL.
- [ ] Commit:

```bash
git add ai_caddie/media.py tests/test_media_context.py
git commit -m "feat: add media metadata store"
```

## Task 2: Vision Findings

- [ ] Add `VisionFinding` contract:
  - finding type
  - evidence text
  - confidence
  - missing info
  - provider/model
- [ ] Add static provider tests.
- [ ] Implement `analyze_media_context(media, provider)`.
- [ ] Findings allowed:
  - poor lie
  - blocked view
  - visible water
  - visible bunker
  - slope clue
  - uncertainty
- [ ] Commit:

```bash
git add ai_caddie/vision_context.py tests/test_vision_context.py
git commit -m "feat: add vision context findings"
```

## Task 3: Media API

- [ ] Add:
  - `POST /api/v2/media`
  - `GET /api/v2/media/target/{target_type}/{target_id}`
  - `POST /api/v2/media/{media_id}/analyze`
- [ ] Tests use temp file metadata and static provider.
- [ ] Endpoint responses must not expose absolute private filesystem paths; return media ids and relative paths only.
- [ ] Commit:

```bash
git add server_v2/media.py server_v2/models.py server_v2/main.py tests/test_server_v2_media.py tests/test_server_v2_health.py
git commit -m "feat: expose media context API"
```

## Task 4: Verification

- [ ] Run backend full tests.
- [ ] Confirm no media response contains token/cookie/secret/absolute home path.
