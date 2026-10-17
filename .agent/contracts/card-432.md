# Card #432 — Readiness image contract

Every repository path that `server_v2/readiness.py` reads for a check that feeds
`runtimeStatus` must be shipped in the runtime stage of `Dockerfile`. #428 showed
the failure mode (`mobile/contracts/` missing from the image, readiness
`degraded` in production, all tests green).

Touches: `tests/test_deployment_manifests.py`, `Dockerfile`, `tests/acceptance/test_card_432_readiness_image_paths.py`

Acceptance tests: `tests/acceptance/test_card_432_readiness_image_paths.py`

## Revision 3 (after gate on 554777e: red, adversarial)

I could not read the gate report from the contract sandbox, so I re-read the
round-2 guard (`33fbdc1`) against the card. It still lets three real defects
through:

1. **Destination ignored.** `COPY mobile/contracts/ ./` counts as shipping
   `mobile/contracts/…`, but Docker copies a directory's *contents* to the
   destination, so the files land at `/app/live_round_event.schema.json` and
   readiness, which reads `mobile/contracts/…` from `/app`, reports `degraded`.
2. **`os.path` probes not recorded.** `os.path.isfile("x")` / `os.path.exists`
   call `os.stat` directly; neither the `Path` wrappers nor the `open` audit
   event see them. An exists-gated runtime check, which is exactly #428's shape
   (`… if LIVE_ROUND_EVENT_CONTRACT.exists() else []`), could slip through when
   it uses `os.path`.
3. **Directory listings not recorded.** A runtime check that lists a directory
   (`Path.iterdir`, `glob`, `os.scandir`) depends on that directory being in the
   image, and no `open` event fires for it.

The acceptance module now has four more cases (G1 conditions 4, 5, 9 and 10).
It also copies the checkout more safely: it uses `git ls-files` when it can and
never copies a temp directory that sits inside the checkout, such as
`.codex-tmp/`, into itself. A copy into itself was a likely cause of the red
result in sandboxed runs. All 13 cases fail on `main`, where the guard test does
not exist. On `554777e`, conditions 4, 9 and 10 fail because the guard does not
do this yet; Codex must change the guard. Condition 5 and the others should
already pass.

## Interface

Add one test method, exactly this id:

```
tests.test_deployment_manifests.DeploymentManifestTests.test_readiness_runtime_paths_are_copied_into_image
```

The acceptance tests run that id with `python -m unittest <id>` in a subprocess
(`AI_CADDIE_DATA_MODE=fixture`, no `AI_CADDIE_PRIVATE_ROOT`, cwd and
`PYTHONPATH` = the tree under test). They run it once on the checkout and once
each on a temporary copy of the checkout with one change. The copy has the
tracked and untracked-but-not-ignored files. It leaves out `.git`, `.venv`,
`node_modules`, bytecode caches, agent temp/home directories and the
private-root names. The guard must:

- find the repository root from the test file or the working directory (both are
  the copy's root in the mutation runs). Do not hard-code an absolute path;
- read `Dockerfile` and `.dockerignore` from that root;
- import `server_v2.readiness` normally and **run** `build_readiness_response()`
  with the working directory at the root. Record every repository path the run
  - **opens** (any `open`, including `Path.read_text`/`read_bytes`/`open` and
    builtin `open`),
  - **probes** (any `stat`, including `Path.exists`/`is_file`/`is_dir`/`stat`
    and `os.path.exists`/`isfile`/`isdir`), or
  - **lists** (`Path.iterdir`/`glob`/`rglob`, `os.listdir`, `os.scandir`; record
    the listed directory).

  Inspecting the module's path constants alone is not enough. The acceptance
  tests insert plain statements into readiness helpers;
- attribute each recorded path to the check label it was used for. Keep only
  paths used for labels **not** in `readiness.PACKAGING_LABELS`. A path used by
  both a runtime and a packaging check stays in scope;
- be a single test that does not skip. When it fails, use an assertion failure
  (unittest reports `FAILED (failures=1)`), not an error, and name every
  uncovered path, repository-relative and POSIX (for example
  `mobile/contracts/live_round_event.schema.json`).

Suggested approach (not mandatory):

- Keep round 2's attribution: wrap `readiness._check` and give every path
  recorded since the previous `_check` call to the next call's label.
- For recording, these are enough together:
  - `sys.addaudithook`, gated by an "active" flag because audit hooks cannot be
    removed, handling the `open`, `os.listdir` and `os.scandir` events;
  - a temporary wrapper on `os.stat`, restored in `finally`, which covers
    `Path.exists`/`is_file`/`stat` and `os.path.exists`/`isfile`/`isdir`;
  - the existing `Path` method wrappers.
- Guard against re-entry: `os.path.realpath` inside the recorder must not
  record itself.

Do not edit `server_v2/readiness.py`. The acceptance tests rewrite these lines
of a copy, so they must stay as they are:

- the module-level line `LIVE_ROUND_EVENT_CONTRACT = Path("mobile/contracts/live_round_event.schema.json")`;
- `def _contract_event_kinds() -> …:` (runtime, label `mobile_events`) and
  `def _external_release_evidence() -> …:` (packaging, label
  `external_release`), each a one-line signature with no arguments.

In `Dockerfile`, keep the explicit `COPY mobile/contracts/ ./mobile/contracts/`
and `COPY ops/ ./ops/` lines, each on one line, and do not widen either. Keep
`WORKDIR /app` in the runtime stage.

## Scope rules for the guard

- **In scope:** every repository path opened, probed or listed while readiness
  evaluates a check whose label is not in `readiness.PACKAGING_LABELS` (today:
  service, mobile, secret_handling, history, sync, course_reference,
  mobile_package, mobile_events, media_context, reports). This holds whatever
  directory the path is in, including directories that packaging checks also
  use, such as `ops/`.
- **Out of scope (packaging/evidence):** paths used only for checks in
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
    its own;
  - the repository root itself and paths outside it.

  No other prefix lists (no `ops`, `docs`, `mobile/ios`, …).
- **Shipped.** A path `P` counts as shipped only when both of these hold:
  1. There is a `COPY` instruction in the **final** `FROM` stage, without
     `--from=`, with a source `S` that is equal to `P` or is a parent directory
     of `P`, and that `COPY` places `S` at `S` relative to the stage's
     `WORKDIR`:
     - Normalise sources and the destination `D`: drop a leading `./` and a
       trailing `/`, and treat an empty result as `.`. If `D` is absolute,
       resolve it against the stage's last absolute `WORKDIR` before the
       `COPY`, so `/app/x` becomes `x` and `/app` becomes `.`; an absolute
       `D` outside the `WORKDIR` places nothing. Skip `--chown=`, `--chmod=`,
       `--link` and other `--` flags; they are not sources.
     - Directory source (`S` is a directory in the tree, or `.`): its contents
       land in `D`. It places `S` at `S` only when `D == S`.
       `COPY mobile/contracts/ ./mobile/contracts/` and
       `COPY mobile/contracts /app/mobile/contracts` qualify;
       `COPY mobile/contracts/ ./` does not.
     - File source: if the raw destination ends in `/`, is `.`, or the `COPY`
       has several sources, the file lands at `D/<basename of S>`; otherwise
       it lands at `D`. It qualifies when that equals `S`.
       `COPY alembic.ini ./` qualifies.
     - A `COPY` in an earlier build stage does not count.
  2. No non-negated, non-comment `.dockerignore` pattern matches `P` or one of
     its parent directories (`fnmatch` against the repo-relative POSIX path).

## Dockerfile

Static tracing on main found no runtime path missing from the image today:
`mobile/contracts/` (#428), `contracts/canonical/`, `ai_caddie/`, `server_v2/`
and `ops/` are all copied to their own paths under `/app`. In fixture mode the
runtime checks also list and probe directories under `data/` and `output/`.
Those are private-root paths and are excluded. If the stricter guard reports any
other path, add the missing `COPY <dir>/ ./<dir>/` to the runtime stage in this
PR. Leave all other Dockerfile lines alone and do not change
`.github/workflows/ci.yml`.

### G1 — A repository test guards readiness runtime paths against the image

Pass conditions (each a case in the acceptance module):

1. The test id above exists, runs as one test, and does not skip.
2. On a copy with the `COPY mobile/contracts/ …` line removed from `Dockerfile`,
   it fails with `FAILED (failures=1)` and its output contains
   `mobile/contracts`.
3. On a copy where that `COPY` line is moved into the first (`node-deps`)
   build stage, it fails the same way and names `mobile/contracts`.
4. On a copy where that line becomes `COPY mobile/contracts/ ./`, it fails the
   same way and names `mobile/contracts`. *(new in revision 3)*
5. On a copy where that line becomes `COPY mobile/contracts /app/mobile/contracts`
   (`WORKDIR /app`), it passes: exit 0, `Ran 1 test`, not skipped. *(new)*
6. On a copy where `.dockerignore` gains the line `mobile/contracts`, it fails
   the same way and names `mobile/contracts`.
7. On a copy where `readiness.LIVE_ROUND_EVENT_CONTRACT` points at
   `relocated_contracts/live_round_event.schema.json` (the file exists there),
   it fails the same way and names `relocated_contracts`.
8. On a copy where `_contract_event_kinds()` (runtime) first reads
   `runtime_probe/extra.json` (the file exists, nothing copies it), it fails the
   same way and names `runtime_probe/extra.json`.
9. On a copy where `_contract_event_kinds()` first runs
   `__import__("os").path.isfile("runtime_probe/stat_only.json")` (exists, not
   copied), it fails the same way and names `runtime_probe/stat_only.json`.
   *(new)*
10. On a copy where `_contract_event_kinds()` first runs
    `list(Path("runtime_probe_dir").iterdir())` (the directory holds one file;
    nothing copies it), it fails the same way and names `runtime_probe_dir`.
    *(new)*
11. On a copy where `_contract_event_kinds()` reads `ops/start_api.sh` and the
    `COPY ops/ ./ops/` line is removed, it fails the same way and names
    `ops/start_api.sh`.
12. On a copy where `_external_release_evidence()` (packaging) reads
    `packaging_probe/extra.json` (exists, not copied), it passes: exit 0,
    `Ran 1 test`, not skipped.
13. On a copy where `_contract_event_kinds()` reads `data/card432_probe.json`
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
