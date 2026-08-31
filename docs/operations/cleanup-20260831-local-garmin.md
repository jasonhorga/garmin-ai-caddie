# Local Garmin workspace cleanup - 2026-08-31

This is the explicit allow-list for reducing the local Garmin workspace while
keeping the canonical source, durable project memory, user rounds, and
credentials intact.  It is intentionally separate from the release cleanup
record in `cleanup-20260831-build46.md`.

## Baseline

- Canonical checkout: `/home/ubuntu/claude-web-data/repo/garmin-ai-caddie`
- Branch: `codex/p0-p1-p2-checkpoint-20260823`
- Baseline commit at planning time: `4e7faf535273cd2db800150a3092c8799174d90c`
- Canonical worktree was clean and matched its GitHub remote.
- Local filesystem before this cleanup: 58 GiB total, about 6.9 GiB free.
- Homeserver target: `/home/jason/garmin-ai-caddie-data/imports/local-cache-20260831`
- Post-cleanup local Garmin footprint: canonical checkout about 64 MB and
  retained user data about 179 MB; no duplicate Garmin checkout remains.

## Physical worktrees

The branch refs remain available for history and rollback.  Only the physical
checkout directories are removed after the no-open-file check.  `git cherry`
and the current source were used to avoid merging an older snapshot back into
the canonical branch.

| Physical path (relative to `repo/`) | Tip | Decision | Reason |
| --- | --- | --- | --- |
| `garmin-ai-caddie-caddie-sequence-fix` | `a9ac1540` | remove checkout | Patch is already equivalent in canonical history (`8ca32ae2`/later fixture commits). |
| `garmin-ai-caddie-caddie-surface-fix` | `f364f662` | remove checkout | Safe-area fix is in canonical history (`76ab2354`). |
| `garmin-ai-caddie-course-reconcile-20260829` | `8955b851` | remove checkout | Reconciliation and bounded geometry lookup are integrated (`affb58df`). |
| `garmin-ai-caddie-fastlane-syntax-fix-20260829` | `84283b96` | remove checkout | Tip is an ancestor/equivalent of canonical release documentation. |
| `garmin-ai-caddie-ios-caddie-request-fix` | `1c85a6be` | remove checkout | Auth-boundary fix is integrated; the old `1e87d36d` patch is superseded by `e237f41f`. |
| `garmin-ai-caddie-native-tee-flow-20260829` | `c28a9315` | remove checkout | Tee profile seed is integrated (`5d52d6e6` and later). |
| `garmin-ai-caddie-p2-prep-hazard-20260828` | `d2313ba2` | remove checkout | Fixture hazard repair is integrated (`9bff8293`). |
| `garmin-ai-caddie-tee-meta-fix` | `d41a818e` | remove checkout | Tee metadata fixes are integrated (`4b4b1b1c`/later). |
| `garmin-ai-caddie-testflight-internal-20260830` | `c17aa02e` | remove checkout | TestFlight group gate is integrated (`b4492a63`/later). |
| `garmin-ai-caddie-r2-timeout-fix` | `ee615a23` | remove checkout | One uncommitted stale test edit; canonical source already has the exact-round lookup behavior. Do not merge. |
| `garmin-ai-caddie-product-results-20260812` | `75f276df` | remove checkout; keep branch | Old 272-file fork with substantial deletions and no unique required implementation. Do not merge. Its small review note is retained in the remote legacy archive manifest. |
| `.claude/worktrees/superpowers+web-redesign-w4a` | `a5fb9435` | remove checkout | Historical Claude worktree; its tracked specs are present in canonical form. Do not merge. |
| `.claude/worktrees/watch-map` | `a69d9677` | remove checkout | Historical prototypes are superseded by current Watch map sources. Do not merge. |

No worktree was found as the current working directory of a process.  Other
project worktrees and all branch refs are outside this allow-list.

## Data migration (completed)

The following generated geometry/data directories are copied to the remote
project data area, verified there, and only then removed locally:

| Local path | Baseline size/files | Remote action |
| --- | ---: | --- |
| `data/garmin-ai-caddie/output/prodgeometry` | 2.9G / 4,557 | Copy under `imports/local-cache-20260831/output/prodgeometry`; do not overwrite the active Docker volume. |
| `data/garmin-ai-caddie/output/prodgeometry_hazards` | 245M / 1,519 | Copy under the matching import path; do not overwrite active geometry. |
| `data/garmin-ai-caddie/output/topo_render_cache` | 2.9M / 10 | Copy as disposable derived cache for reference. |
| `data/garmin-ai-caddie/data/courseview` | 994M / 25,869 | Copy under the matching import path; unique CourseView files are preserved for a later explicit merge. |

The destination is an additive import/archive, not the running API volume.  The
active volume already contains a newer/overlapping geometry set; conflicting
files are preserved in this import and were not silently replaced.  The four
copies completed and matched their source inventories; `rsync --checksum
--dry-run` reported zero regular-file transfers before deletion.  The detailed
execution record is at
`/home/jason/garmin-ai-caddie-data/cleanup-manifests/20260831T-local-garmin-cleanup/`.

The source directories were removed only after the no-open-handle check and
the remote count/byte/checksum checks.  They are now available at
`/home/jason/garmin-ai-caddie-data/imports/local-cache-20260831/`.

The following smaller local user data stays in place: `data/decisions`,
`data/reports`, `data/shots`, `data/scorecards`, `data/courses`, sync/weather/
media, `downloads`, and `logs`.  The entire `.garmin_tokens` directory stays
local with its existing restrictive permissions and is never copied to the
archive.

## Transcript cleanup (completed)

Only closed, Garmin-owned transcripts were eligible.  The four exact targets
below were checked for open handles, recorded in
`session-delete.allowlist`, and removed:

- Delete `/home/ubuntu/.codex/sessions/2026/05/23/rollout-2026-05-23T16-21-33-019e55a4-54a6-7900-9625-dffc00491ed3.jsonl` (about 149M).
- Delete `/home/ubuntu/.codex/sessions/2026/07/15/rollout-2026-07-15T18-22-22-019f6703-fc34-7ae1-92ce-c901588791d8.jsonl` (about 76M; completed subagent transcript).
- Delete the closed Claude project tree
  `/home/ubuntu/.claude/projects/-home-ubuntu-claude-web-data-repo-garmin-ai-caddie-web-v2-src`
  (about 785M; last activity 2026-07-18, no open handles).
- Delete the closed Claude worktree project tree
  `/home/ubuntu/.claude/projects/-home-ubuntu-claude-web-data-repo-garmin-ai-caddie--claude-worktrees-superpowers-web-redesign-w4a`
  (about 25M; no open handles).

The active 3G Codex transcript, all files currently open by the main Codex
process, the canonical Garmin Claude project and its `memory/` files, and all
Notebook/Health/Gomoku sessions remain explicitly protected.  Durable state is
kept in `docs/operations/PROJECT_STATE.md` and the committed review/spec
documents; raw transcripts were not copied to a second location.

The old `r2-timeout-fix` worktree contained one uncommitted test-only edit.  It
was not merged into the current source; its exact diff is preserved at
`/home/jason/garmin-ai-caddie-data/archives/local-garmin-worktrees-20260831/r2-timeout-fix/`.

## Generated evidence and build output (completed)

The local `review-artifacts` directory (5,393 files, 899,355,285 bytes) and
the canonical `.codex-tmp` directory (260 files, 84,119,309 bytes) were
archived and checksum-verified at
`/home/jason/garmin-ai-caddie-data/archives/local-generated-20260831/`, then
removed locally.  The local `review-tools` directory remains because it
contains reusable review scripts; its small contact-sheet folders are not
source data.  Rebuildable `web_v2/node_modules`, `dist`, `test-results`, and
`playwright-report` were also removed; lockfiles and source remain.

## Explicitly protected

- Canonical source checkout, Git metadata, and all remote branch refs.
- Garmin token files and all credentials.
- User score/shot/decision data retained locally.
- The active API, database, web containers, named volumes, and rollback image.
- Other projects, their worktrees, sessions, and services.
- `/home/jason/garmin-ai-caddie-data/archives/local-generated-20260831/`
  (archived review evidence and diagnostics).
- The currently active Codex session and any file with an open process handle.

## Execution record

The remote execution manifest, archive checksums, deletion allow-lists, and
post-copy checksums are stored under
`/home/jason/garmin-ai-caddie-data/cleanup-manifests/20260831T-local-garmin-cleanup/`.
All allow-listed operations in this run are complete.
The post-cleanup homeserver check returned HTTP 200 from `/api/v2/health`
with revision `1af378b811cd25edae12285c5745aef1b57d7faf`; the API, web, and
database containers remained healthy.  The earlier `/healthz` probe was simply
an invalid route for this service.

## Ongoing directory rule

- Keep the local canonical checkout focused on source, tests, committed docs,
  and small user data needed for editing.  Run builds, browser tests, imports,
  and servers on homeserver.
- Put durable generated course/geometry data under
  `/home/jason/garmin-ai-caddie-data/`; put disposable remote work under a
  uniquely named `/home/jason/codex-runs/<project>-<session>` directory.
- Keep review evidence and large diagnostics in a dated homeserver archive;
  do not leave them in a worktree or the local repository.  Delete a scratch
  directory only after its result is committed or archived and its owner is
  recorded.
- Never copy or clean `.garmin_tokens`, credentials, another project's
  checkout/session, or an open process target.  Keep branch refs for history,
  but remove completed physical worktrees once their patches are merged or
  explicitly archived.
