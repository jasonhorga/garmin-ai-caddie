# Card #432 — Readiness image contract

Every repository path that `server_v2/readiness.py` reads for a check that feeds
`runtimeStatus` must be shipped in the runtime stage of `Dockerfile`. #428 showed
the failure mode (`mobile/contracts/` missing from the image, readiness
`degraded` in production, all tests green).

Touches: `tests/test_deployment_manifests.py`, `Dockerfile`

Acceptance tests: `tests/acceptance/test_card_432_readiness_image_paths.py`

## Revision 2 (after gate on 86baa35)

The first round's guard passed the first five acceptance cases but scoped paths
by a hard-coded path-prefix list, including `ops`, instead of by check label.
With that list, a runtime check reading a file under `ops/` would never be
caught, and a packaging check reading a new uncopied file would fail the guard.
A guard that only looked at the two `LIVE_ROUND_*` constants would also have
passed the first five cases. Four cases were added (G1 conditions 6–9). Both
the scope rules and the interface below now require label-based attribution.

## Interface

Add one test method, exactly this id:

```
tests.test_deployment_manifests.DeploymentManifestTests.test_readiness_runtime_paths_are_copied_into_image
```

The acceptance tests run that id with `python -m unittest <id>` in a subprocess
(`AI_CADDIE_DATA_MODE=fixture`, no `AI_CADDIE_PRIVATE_ROOT`, cwd and
`PYTHONPATH` = the tree under test). They run it once on the checkout and once
each on a temporary full copy of the checkout with one change. The copy leaves
out `.git`, `.venv`, `node_modules`, bytecode caches and the private-root names.
The guard must:

- find the repository root from the test file or the working directory (both are
  the copy's root in the mutation runs). Do not hard-code an absolute path;
- read `Dockerfile` and `.dockerignore` from that root;
- import `server_v2.readiness` normally and **run** `build_readiness_response()`
  with the working directory at the root, recording the repository files that
  the run reads or probes. Inspecting the module's path constants alone is not
  enough: the acceptance tests insert plain `Path("…").read_text()` calls into
  readiness helpers;
- attribute each recorded path to the check label it was read for, and keep
  only paths read for labels **not** in `readiness.PACKAGING_LABELS`;
- be a single test that does not skip. When it fails, use an assertion failure
  (unittest reports `FAILED (failures=1)`), not an error, and name every
  uncovered path, repository-relative and POSIX (for example
  `mobile/contracts/live_round_event.schema.json`).

Suggested attribution (not mandatory): `build_readiness_response()` gathers each
check's evidence and then calls `readiness._check(label, …)`. Wrap
`readiness._check` for the duration of the run, so that every path recorded
since the previous `_check` call is attributed to the label of the next call.
Record with `sys.addaudithook` (`open` events; audit hooks cannot be removed, so
gate the hook with an "active" flag) plus wrappers on `Path.exists`/`is_file`/
`read_text`/`open`, as the round-1 guard did. Restore every patch in `finally`.

Do not edit `server_v2/readiness.py`. The acceptance tests rewrite these lines
of a copy, so they must stay as they are:

- the module-level line `LIVE_ROUND_EVENT_CONTRACT = Path("mobile/contracts/live_round_event.schema.json")`;
- `def _contract_event_kinds() -> …:` (runtime, label `mobile_events`) and
  `def _external_release_evidence() -> …:` (packaging, label
  `external_release`), each a one-line signature with no arguments.

In `Dockerfile`, keep the explicit `COPY mobile/contracts/ ./mobile/contracts/`
and `COPY ops/ ./ops/` lines and do not widen either.

## Scope rules for the guard

- **In scope:** every repository path read or probed while readiness evaluates a
  check whose label is not in `readiness.PACKAGING_LABELS` (today: service,
  mobile, secret_handling, history, sync, course_reference, mobile_package,
  mobile_events, media_context, reports). This holds whatever directory the
  path is in, including directories that packaging checks also use, such as
  `ops/`.
- **Out of scope (packaging/evidence):** paths read only for checks in
  `PACKAGING_LABELS` (`native_mobile`, `external_release`, `roadmap_completion`,
  `operations`, `private_snapshot_acceptance`), such as `mobile/ios/**`,
  `docs/**`, `render.yaml` and `web_v2/vercel.json`. They are excluded by
  label, not by a path list. These must not fail the guard.
- **The only path-based exclusions allowed:**
  - the private runtime root `data`, `.garmin_tokens`, `output`, `logs`,
    `backups` and `clubs.json` and everything below them. `ops/start_api.sh`
    symlinks these into `AI_CADDIE_PRIVATE_ROOT`, so they are not image
    content;
  - image-built environments (`.venv`, `node_modules`);
  - Python bytecode caches (`__pycache__/`, `*.pyc`), since the image compiles
    its own.

  No other prefix lists (no `ops`, `docs`, `mobile/ios`, …).
- A path counts as shipped only when both of these hold:
  - a `COPY` instruction in the **final** `FROM` stage, without `--from=`, has
    a source equal to the path or to one of its parent directories;
  - no non-negated, non-comment `.dockerignore` pattern matches the path or one
    of its parent directories (`fnmatch` against the repo-relative POSIX path).

  A `COPY` in an earlier build stage does not count.

## Dockerfile

Static tracing on main found no runtime path missing from the image today:
`mobile/contracts/` (#428), `contracts/canonical/`, `ai_caddie/`, `server_v2/`
and `ops/` are all copied. If the guard reports a path, add the missing
`COPY <dir>/ ./<dir>/` to the runtime stage in this PR. Leave all other
Dockerfile lines alone and do not change `.github/workflows/ci.yml`.

### G1 — A repository test guards readiness runtime paths against the image

Pass conditions (each a case in the acceptance module):

1. The test id above exists, runs as one test, and does not skip.
2. On a copy with the `COPY mobile/contracts/ …` line removed from `Dockerfile`,
   it fails with `FAILED (failures=1)` and its output contains
   `mobile/contracts`.
3. On a copy where that `COPY` line is moved into the first (`node-deps`)
   build stage, it fails the same way and names `mobile/contracts`.
4. On a copy where `.dockerignore` gains the line `mobile/contracts`, it fails
   the same way and names `mobile/contracts`.
5. On a copy where `readiness.LIVE_ROUND_EVENT_CONTRACT` points at
   `relocated_contracts/live_round_event.schema.json` (the file exists there),
   it fails the same way and names `relocated_contracts`.
6. On a copy where `_contract_event_kinds()` (runtime) first reads
   `runtime_probe/extra.json` (the file exists, nothing copies it), it fails the
   same way and names `runtime_probe/extra.json`.
7. On a copy where `_contract_event_kinds()` reads `ops/start_api.sh` and the
   `COPY ops/ ./ops/` line is removed, it fails the same way and names
   `ops/start_api.sh`.
8. On a copy where `_external_release_evidence()` (packaging) reads
   `packaging_probe/extra.json` (exists, not copied), it passes: exit 0,
   `Ran 1 test`, not skipped.
9. On a copy where `_contract_event_kinds()` reads `data/card432_probe.json`
   (exists, private root), it passes the same way.

### G2 — The production image ships every runtime path readiness reads

Pass conditions:

1. On the checkout itself the guard passes (exit 0, `Ran 1 test`, not skipped).
2. Any path it reported was fixed by adding a `COPY` to the runtime stage of
   `Dockerfile`, not by adding the path to an exclusion list.
3. The existing `tests/test_deployment_manifests.py` tests and the rest of the
   backend suite stay green in fixture mode.
4. After release, production `/api/v2/health` reports the merged revision, and
   readiness `runtimeStatus` is still `ready`. The release-tier run checks this
   read-only.

## Not in scope

No app, Watch, web, migration, auth or deploy-script changes, and no change to
`server_v2/readiness.py`. Do not edit the pinned files.
