# S70 Unified Golf Program Execution Index

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:subagent-driven-development` task by task. This file is the
> program routing and evidence index; the four 2026-07-18 engineering dossiers
> retain detailed research and task material without becoming line-by-line
> completion authorities.

**Goal:** Deliver an honest, S70-behavioral-parity golf product whose Watch,
iOS, Web, and backend share course facts, round events, guidance semantics, and
recovery behavior, beginning with the locked first production milestone.

**Architecture:** One serial contract-owner lane protects canonical sources and
generated outputs. Product delivery proceeds in vertical slices; Deep Mine runs
as a non-blocking research lane, and only individually promoted capabilities may
enter product snapshots or Guidance.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy, PostgreSQL, Swift 5.9,
SwiftUI/watchOS, TypeScript, React, canonical JSON/typed IDs, immutable course
snapshots, deterministic reducers, and remote verification on `homeserver`.

---

## 1. Locked product outcome

- Apple Watch is the on-course primary surface and must eventually search,
  select layout/Tee, install a real course, start without iPhone, and complete a
  full round offline.
- iOS is the on-course control/deep-edit surface and also supports phone-only
  play. Web remains preparation, review, statistics, and governance rather than
  a live-round recorder.
- S70 parity means observable task flow and progressive disclosure: permanent
  facts, a conditional truthful current-shot recommendation, and a full Caddie
  detail surface. It does not mean copying pixels, proprietary assets, or an
  unknown Garmin algorithm.
- Recommendations never become actual shots or clubs. Missing evidence produces
  an honest unavailable/zero state, never fabricated precision.
- Wind, air density, fake success probability, and putting-grade contours are
  outside v1. AutoShot is last and cannot block the manual path.

Authority sources:

- `docs/reviews/2026-07-15-watch-decision-and-task-tracker.md`
- `docs/reviews/2026-07-16-repository-wide-owner-gate-authority-and-drift-audit.md`
- `docs/reviews/2026-07-16-s70-virtual-caddie-and-map-mechanisms-evidence.md`
- `docs/superpowers/specs/2026-07-18-course-data-platform-and-unified-surfaces-design.md`

## 2. First production milestone

```text
search one real course
→ build and atomically install a complete CourseSnapshot
→ start on Watch without iPhone
→ record manual score and manual shot
→ recover after force-kill/restart
→ finish the full round offline
→ synchronize through iOS/server
→ deep-edit on iOS
→ deterministically recompute statistics
```

Deep Mine produces replayable evidence beside this path. Unknown advanced
assets do not block baseline distance, map, scoring, or installation.

## 3. Document roles

| Document | Role | Completion authority |
|---|---|---|
| `2026-07-18-phase0-canonical-round-runtime.md` | Plan 1 engineering dossier | No |
| `2026-07-18-course-acquisition-snapshot-installer.md` | Plan 2 engineering dossier | No |
| `2026-07-18-deep-mine-research-lab.md` | Plan 3 research dossier | No |
| `2026-07-18-s70-experience-capability-promotion.md` | Plan 4 experience dossier | No |
| This index | Scope, order, status, and evidence routing | Yes |
| Production source + tests + commit | Implemented behavior | Yes |

The dossiers remain intact. Their invariants, failure cases, fixtures, and test
ideas are inputs to a task card. Embedded production sketches must be checked
against the live repository and never copied merely because a mechanical prose
gate accepts them.

## 4. Status vocabulary

- `CANDIDATE_IMPLEMENTED`: production commits exist, but current requirements
  and remote tests have not yet independently proved the task complete.
- `IN_PROGRESS`: one bounded task card is being implemented or reviewed.
- `VERIFIED`: production code, requirement-level review, relevant remote tests,
  and a commit all exist with no open Critical/Important review issue.
- `PENDING`: no sufficient implementation evidence yet.
- `RESEARCH`: may proceed independently but is not a product gate.
- `OWNER_DECISION`: work would change a locked product promise, scope, order, or
  external/public behavior and must stop for the Owner.

Plan prose, a green text checker, an agent report, or an intended commit is not
enough to mark `VERIFIED`.

## 5. Current implementation ledger

| Slice | Status | Current evidence | Next proof |
|---|---|---|---|
| Plan 1 Task 1 authority gate | `VERIFIED` | `41fca67`, `3f6016e`, `362f26c`, `a28ae70`, `819f9f2`, `71149b7`; [verification record](../reviews/2026-07-23-plan1-task1-authority-gate-verification.md) | POP → verify/fix Plan 1 Task 2 |
| Plan 1 Task 2 CanonicalJSON/typed IDs | `CANDIDATE_IMPLEMENTED` | `07bcb61`, `c00ebef` | Requirement audit, cross-language fixtures, remote focused tests |
| Plan 1 Task 3 registries/generated declarations | `CANDIDATE_IMPLEMENTED` | `cfac7cf`, `7a6fa22` | Registry/codegen audit and remote drift tests |
| Plan 1 Task 4 mobile event durability | `CANDIDATE_IMPLEMENTED` | `964fef2` through `8ef2996` | Recovery/ordering requirement audit and native/static evidence |
| Plan 1 Tasks 5–14 including 13a | `PENDING` | Dossier only | Extract the next bounded task card after Tasks 1–4 are verified |
| Plan 2 B1–B17 | `PENDING` | Dossier and pre-existing reusable code only | Baseline acquisition/install dependency audit |
| Plan 3 C1–C16 | `RESEARCH` | Dossier and historical parsers/data | Run without blocking baseline product; promote per capability only |
| Plan 4 D00–D15 | `PENDING` | Dossier and pre-existing UI/runtime code only | Move manual milestone path as early as real dependencies allow |

Older May plans and `docs/superpowers/specs/work-board.md` are historical
implementation/reuse evidence. They do not override this ledger.

## 6. Execution rules

1. Only one implementation task owns shared canonical/registry/generated files
   at a time.
2. Before editing, extract one short task card from the relevant dossier:
   outcome, owned files, invariants, failing test, verification command, and
   explicit exclusions.
3. Apply test-driven development for every behavior change: observe RED, make
   the smallest production change, observe GREEN, then refactor.
4. Run tests, builds, dependency work, broad lint/typecheck, and native tooling
   only on `homeserver`; local work is limited to reads, edits, Git inspection,
   and SSH orchestration.
5. A fresh implementer is followed by a fresh specification reviewer and then
   a code-quality reviewer. Agent completion returns automatically; do not poll
   or call `wait_agent`.
6. Reviewer findings are classified against the locked outcome. A real bug or
   missing approved requirement is fixed. A new product/architecture requirement
   enters candidate backlog and cannot silently expand the active task.
7. Deep Mine cannot gate baseline course acquisition, known-good map/distance,
   scoring, or installation. A product capability depending on newly decoded
   evidence waits only for that capability's promotion gate.
8. AutoShot cannot write canonical facts until the complete manual path and its
   recovery behavior are verified.

## 7. Definition of done per task

A task is `VERIFIED` only when the ledger can point to all of:

- the exact approved requirements and exclusions;
- production source implementing them;
- a test that was observed failing for each new behavior or bug;
- focused and relevant regression commands completed on `homeserver`;
- specification-compliance approval;
- code-quality approval with all Critical and Important issues closed;
- a dedicated commit containing no unrelated user changes.

## 8. Overall return points

- **Overall:** deliver the locked S70 unified product and all retained program
  capabilities.
- **Current phase:** prove and finish the canonical reliability foundation.
- **Current drill-down:** Plan 1 Tasks 1–4 requirement-by-requirement audit.
- **POP:** after each verified task, return here and select the next dependency
  on the first production milestone rather than following the deepest document
  branch.
- **Owner decision:** none currently open.
- **External blocker:** none currently known.

## 9. Immediate task order

1. Verify/fix Plan 1 Task 1.
2. Verify/fix Plan 1 Task 2.
3. Verify/fix Plan 1 Task 3.
4. Verify/fix Plan 1 Task 4.
5. Extract and implement Plan 1 Task 5 as the next bounded vertical slice.
6. Recompute the first-milestone dependency path before selecting each later
   slice; do not reinstate the obsolete global `Plan 3 C1–C16 before Plan 2 B8`
   gate.
