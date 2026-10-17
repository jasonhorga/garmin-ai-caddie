# Card #432 — Readiness image contract

Every repository path that `server_v2/readiness.py` reads for a check that feeds
`runtimeStatus` must be shipped in the runtime stage of `Dockerfile`. #428 showed
the failure mode (`mobile/contracts/` missing from the image, readiness
`degraded` in production, all tests green).

Touches: `tests/test_deployment_manifests.py`, `Dockerfile`, `tests/acceptance/test_card_432_readiness_image_paths.py`

Acceptance tests: `tests/acceptance/test_card_432_readiness_image_paths.py`

## Revision 4 (after gate on 4d691cd: red, adversarial)

I still could not read the gate report from the contract sandbox, so this
revision comes from re-reading the guard at `4d691cd` against the card. These
real defects still get past it, and the new cases cover them:

1. **Line continuations.** The guard reads `Dockerfile` line by line. A
   `RUN true \` line followed by the unchanged `COPY mobile/contracts/ …` line
   makes Docker treat the COPY as an argument of `RUN`, so nothing is copied,
   but the guard counts it as shipped (condition 15). The opposite also
   happens: a valid COPY split over two lines with `\` makes `shlex` fail, and
   the guard rejects a correct Dockerfile (condition 14).
2. **Absolute destination under a different WORKDIR.** With `WORKDIR /srv`,
   `COPY mobile/contracts/ /srv/mobile/contracts/` and then `WORKDIR /app`, the
   files land in `/srv`. Readiness runs from `/app`, but the guard counts the
   path as shipped (condition 16).
3. **`os.access` probes are not recorded** (condition 17).
4. **Warm caches hide reads.** The guard traces readiness inside the test
   process. In the full CI suite readiness and its `lru_cache` loaders have
   already run, so a runtime read behind a cache is never seen.
   `canonical_objects._schema_registry` and `analysis.load_geometry` already
   have this shape. Condition 18 runs readiness once in the same interpreter
   before the guard.

**A likely cause of the red result.** Condition G2.1 used to run the guard on
the live checkout. In a sandboxed run, the agent home, temp area, tool caches or
runtime can sit inside the checkout. If readiness touches any of them, the
guard reports a non-image path. Every case, including the baseline, now runs on
a temporary copy of the checkout's **tracked** files. The copy step uses
`git ls-files --cached`. When git is unavailable it falls back to a filtered
copy that leaves out top-level hidden directories and any temp or home
directory inside the checkout.

**History note.** Codex commit `9d07b30` edited
`tests/acceptance/test_card_432_readiness_image_paths.py`. Revision 3
superseded those edits. Codex must not touch `tests/acceptance/` again.

All 18 cases fail on `main`, where the guard test does not exist. On `4d691cd`,
conditions 14–18 fail. The baseline (G2.1) should pass on `4d691cd` unless the
live-checkout environment was the red cause.

## Interface

Add this test method, exactly this id:

```
tests.test_deployment_manifests.DeploymentManifestTests.test_readiness_runtime_paths_are_copied_into_image
```

Small helper unit tests next to it, such as the existing
`test_dockerignore_root_pattern_is_normalized`, are fine if they stay green.

The acceptance tests run that id in a subprocess
(`AI_CADDIE_DATA_MODE=fixture`, no `AI_CADDIE_PRIVATE_ROOT`, cwd and
`PYTHONPATH` set to the tree under test). There are two forms:

- `python -m unittest <id>`;
- for condition 18 only, `python -c` with a script that imports
  `server_v2.readiness`, calls `build_readiness_response()` once, and then runs
  `unittest.main(module=None, argv=['unittest', '<id>'])` in the **same**
  interpreter.

The tree is always a temporary copy of the checkout's tracked files, either
unchanged or with one change. Stage any new file (`git add`) before running the
acceptance tests locally, or the copy will not contain it. The guard must:

- find the repository root from the test file or the working directory. Do not
  hard-code an absolute path;
- read `Dockerfile` and `.dockerignore` from that root;
- **run** `build_readiness_response()` in a fresh child interpreter
  (`subprocess.run([sys.executable, "-c", <script>], cwd=root, …)`). Pass on the
  parent's environment and put the root first on `PYTHONPATH`. Running in a
  child keeps caches, imports and patches from the test process out of the
  trace. The child imports `server_v2.readiness` normally, then installs the
  recorders, then runs readiness. It reports `{label: [paths]}` to the parent
  on stdout, behind a marker line so log output cannot confuse the parser. Only
  reads made while readiness runs count; reads made while modules import do
  not. If the child exits non-zero or prints no result, the guard fails with
  an assertion that includes the end of the child's stderr. It never raises an
  error and never skips;
- in the child, record every repository path the run
  - **opens**: any `open`, including `Path.read_text`/`read_bytes`/`open`,
    builtin `open` and `os.open`;
  - **probes**: any `stat` or access check, including
    `Path.exists`/`is_file`/`is_dir`/`stat`/`lstat`,
    `os.path.exists`/`isfile`/`isdir`/`islink`, `os.stat`, `os.lstat` and
    `os.access`;
  - **lists**: `Path.iterdir`/`glob`/`rglob`, `os.listdir`, `os.scandir`,
    `os.walk` and `glob.glob`. Record the listed directory.

  Inspecting the module's path constants alone is not enough. The acceptance
  tests insert plain statements into readiness helpers;
- attribute each recorded path to the check label it was used for. Keep only
  paths used for labels **not** in `readiness.PACKAGING_LABELS`. A path used by
  both a runtime and a packaging check stays in scope;
- be a single test. When it fails, use an assertion failure (unittest reports
  `FAILED (failures=1)`), not an error, and name every uncovered path,
  repository-relative and POSIX (for example
  `mobile/contracts/live_round_event.schema.json`).

Suggested approach (not mandatory):

- Keep the current recorders (the gated `sys.addaudithook` for `open`,
  `os.listdir` and `os.scandir`, the `os.stat`/`os.lstat` wrappers, the `Path`
  method wrappers and the re-entry guard). Add an `os.access` wrapper and move
  all of it into the child script.
- Keep the `_check` attribution: every path recorded since the previous `_check`
  call goes to the next call's label.
- The child can print `json.dumps({"labels": …})` after a fixed marker line,
  for example `CARD432-TRACE:`. The parent takes the last such line.

Do not edit `server_v2/readiness.py`. The acceptance tests rewrite these lines
of a copy, so they must stay as they are:

- the module-level line `LIVE_ROUND_EVENT_CONTRACT = Path("mobile/contracts/live_round_event.schema.json")`;
- `def _contract_event_kinds() -> …:` (runtime, label `mobile_events`) and
  `def _external_release_evidence() -> …:` (packaging, label
  `external_release`), each a one-line signature with no arguments;
- `from pathlib import Path` stays imported at module level. Condition 18
  appends a module-level function that uses `Path`.

In `Dockerfile`, keep the explicit `COPY mobile/contracts/ ./mobile/contracts/`
and `COPY ops/ ./ops/` lines, each on one line, and do not widen either. Keep
`WORKDIR /app` as the only `WORKDIR` of the runtime stage.

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
- **Reading `Dockerfile`.** Before interpreting instructions, apply Docker's
  default line handling:
  - join a line that ends in `\` with the following line, and keep joining
    while the joined line still ends in `\`;
  - inside a continuation, drop empty lines and lines whose first non-blank
    character is `#`;
  - outside a continuation, skip comment lines and empty lines.

  The instruction is the first word of each joined line, compared
  case-insensitively. A line that a continuation swallows is part of the
  previous instruction, never an instruction of its own.
- **Shipped.** A path `P` counts as shipped only when both of these hold:
  1. There is a `COPY` instruction in the **final** `FROM` stage, without
     `--from=`, with a source `S` equal to `P` or a parent directory of `P`.
     That `COPY` must place `P` at `<runtime root>/P`:
     - The **runtime root** is the `WORKDIR` in effect at the end of the final
       stage (`/` if there is none). Track `WORKDIR` through the stage: an
       absolute value replaces it, a relative value joins onto it.
     - Normalise each source: drop a leading `./` and a trailing `/`, and treat
       an empty result as `.`. Skip `--chown=`, `--chmod=`, `--link` and other
       `--` flags; they are not sources.
     - Resolve the destination `D` to an absolute path. Join a relative `D`
       onto the `WORKDIR` in effect at that `COPY`, then normalise it.
     - Directory source (`S` is a directory in the tree, or `.`): its contents
       land in `D`, so `P` lands at `D/<P relative to S>`.
     - File source: if the raw destination ends in `/`, is `.`, or the `COPY`
       has several sources, the file lands at `D/<basename of S>`. Otherwise
       it lands at `D`.
     - Examples with `WORKDIR /app`:
       - these qualify: `COPY mobile/contracts/ ./mobile/contracts/`,
         `COPY mobile/contracts /app/mobile/contracts`, `COPY alembic.ini ./`,
         and a COPY split over two lines with `\`;
       - these do not: `COPY mobile/contracts/ ./`, and
         `WORKDIR /srv` + `COPY mobile/contracts/ /srv/mobile/contracts/` +
         `WORKDIR /app`;
       - a `COPY` in an earlier build stage does not count.
  2. No non-negated, non-comment `.dockerignore` pattern matches `P` or one of
     its parent directories. Use `fnmatch` against the repo-relative POSIX
     path, after dropping a leading `/` or `./` and a trailing `/` from the
     pattern.

## Dockerfile

Static tracing on main found no runtime path missing from the image today.
`mobile/contracts/` (#428), `contracts/canonical/`, `ai_caddie/`, `server_v2/`
and `ops/` are all copied to their own paths under `/app`. In fixture mode the
runtime checks also list and probe directories under `data/` and `output/`.
Those are private-root paths and are excluded. If the guard reports any other
path, add the missing `COPY <dir>/ ./<dir>/` to the runtime stage in this PR.
Leave all other Dockerfile lines alone and do not change
`.github/workflows/ci.yml`.

### G1 — A repository test guards readiness runtime paths against the image

Pass conditions (each a case in the acceptance module). "Fails the same way"
means: non-zero exit, `Ran 1 test`, `FAILED (failures=1)`, and the output names
the given path. "Passes" means: exit 0, `Ran 1 test`, not skipped.

1. The test id above exists, runs as one test, and does not skip.
2. On a copy with the `COPY mobile/contracts/ …` line removed from `Dockerfile`,
   it fails and names `mobile/contracts`.
3. On a copy where that `COPY` line is moved into the first (`node-deps`)
   build stage, it fails the same way and names `mobile/contracts`.
4. On a copy where that line becomes `COPY mobile/contracts/ ./`, it fails the
   same way and names `mobile/contracts`.
5. On a copy where that line becomes `COPY mobile/contracts /app/mobile/contracts`
   (`WORKDIR /app`), it passes.
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
10. On a copy where `_contract_event_kinds()` first runs
    `list(Path("runtime_probe_dir").iterdir())` (the directory holds one file;
    nothing copies it), it fails the same way and names `runtime_probe_dir`.
11. On a copy where `_contract_event_kinds()` reads `ops/start_api.sh` and the
    `COPY ops/ ./ops/` line is removed, it fails the same way and names
    `ops/start_api.sh`.
12. On a copy where `_external_release_evidence()` (packaging) reads
    `packaging_probe/extra.json` (exists, not copied), it passes.
13. On a copy where `_contract_event_kinds()` reads `data/card432_probe.json`
    (exists, private root), it passes.
14. On a copy where the `COPY mobile/contracts/ …` line is split into
    `COPY mobile/contracts/ \` and `    ./mobile/contracts/`, it passes.
    *(new in revision 4)*
15. On a copy where the line `RUN true \` is inserted directly above the
    unchanged `COPY mobile/contracts/ …` line, it fails the same way and names
    `mobile/contracts`. *(new)*
16. On a copy where that line becomes the three lines `WORKDIR /srv`,
    `COPY mobile/contracts/ /srv/mobile/contracts/` and `WORKDIR /app`, it fails
    the same way and names `mobile/contracts`. *(new)*
17. On a copy where `_contract_event_kinds()` first runs
    `__import__("os").access("runtime_probe/access_only.json", 4)` (exists, not
    copied), it fails the same way and names `runtime_probe/access_only.json`.
    *(new)*
18. On a copy where readiness gains a module-level
    `functools.lru_cache`-wrapped `_card432_cached_probe()` that reads
    `runtime_probe/cached.json` (exists, not copied), and
    `_contract_event_kinds()` calls it first: run in the warm form, with
    readiness evaluated once in the same interpreter before the guard, it fails
    the same way and names `runtime_probe/cached.json`. *(new)*

### G2 — The production image ships every runtime path readiness reads

Pass conditions:

1. On an unchanged copy of the checkout's tracked files, the guard passes
   (exit 0, `Ran 1 test`, not skipped).
2. Any path it reported was fixed by adding a `COPY` to the runtime stage of
   `Dockerfile`, not by adding the path to an exclusion list.
3. The existing `tests/test_deployment_manifests.py` tests and the rest of the
   backend suite stay green in fixture mode, including when the guard runs
   inside the full `unittest discover -s tests` run.
4. After release, production `/api/v2/health` reports the merged revision, and
   readiness `runtimeStatus` is still `ready`. The release-tier run checks this
   read-only.

## Not in scope

No app, Watch, web, migration, auth or deploy-script changes, and no change to
`server_v2/readiness.py`. Do not edit the pinned files or `tests/acceptance/`.
Known limits this card does not cover: `RUN` steps that delete copied files,
`ADD` instructions (treated as not shipping anything), `.dockerignore`
re-inclusion with `!` (treated as still excluded), and reads that happen
while modules import.
