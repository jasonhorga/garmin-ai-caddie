# Card #432 — Readiness image contract

Every repository path that `server_v2/readiness.py` reads for a check that feeds
`runtimeStatus` must be shipped in the runtime stage of `Dockerfile`. #428 showed
the failure mode (`mobile/contracts/` missing from the image, readiness
`degraded` in production, all tests green).

Touches: `tests/test_deployment_manifests.py`, `Dockerfile`, `tests/acceptance/test_card_432_readiness_image_paths.py`

Acceptance tests: `tests/acceptance/test_card_432_readiness_image_paths.py`

## Revision 5 (after gate on dbb5b0a: red, adversarial)

I could not read the gate report from the contract sandbox, and I could not run
Python there either. This revision comes from reading the guard at `dbb5b0a`
against the spec. These defects still get past it, and four new cases cover
them:

1. **Reads after the last `_check` are dropped.** The trace gives each path to
   the next `_check` call. A path read after the final `_check` (`operations`)
   is never given to any label, so the guard ignores it. Readiness still reads it
   on every request, and if the file is missing the response fails. Such reads
   now count as runtime (condition 19).
2. **`.dockerignore` patterns are not cleaned.** Docker runs each pattern through
   `filepath.Clean`, so `mobile//contracts/` excludes `mobile/contracts`. The
   guard only strips a prefix and a suffix, so it counts the path as shipped
   (condition 20).
3. **`**/` must also match zero directories.** In Docker,
   `**/mobile/contracts` excludes `mobile/contracts` at the context root.
   `fnmatch` needs a `/` before `mobile`, so the guard counts the path as
   shipped (condition 21).
4. **The JSON form of `COPY` is rejected.** For
   `COPY ["mobile/contracts/", "./mobile/contracts/"]`, `shlex` yields the
   sources `[mobile/contracts/,`, so the guard rejects a correct Dockerfile
   (condition 22).

Two review findings are not mechanical, but they are part of G2 (condition
G2.5):

- `_relative_copy_destination` is not used by the guard, and
  `test_copy_outside_stage_root_is_uncovered` tests only that unused helper;
- `test_no_argument_directory_listing_records_current_repository_directory`
  tests its own copy of the audit hook, not the hook the guard uses.

**On the red result.** Reading the code, I expect conditions 1–18 to pass on
`dbb5b0a` and all 22 to fail on `main`, where the guard test does not exist. I
cannot confirm what made the gate red. One possibility I cannot measure is the
total runtime: the module runs readiness in a subprocess once per case, and the
recorders call `os.path.realpath` on every stat. G2.6 asks Codex to keep the
trace cheap and to report the module's wall time. If the gate report names a
failing case, that report wins over this note.

Earlier revisions: revision 4 added conditions 14–18 (line continuations,
WORKDIR tracking, `os.access`, warm caches) and moved every case, including the
baseline, onto a copy of the tracked files. Codex commit `9d07b30` once edited
`tests/acceptance/`. Revision 3 superseded those edits. Codex must not touch
`tests/acceptance/`.

## Interface

Add this test method, exactly this id:

```
tests.test_deployment_manifests.DeploymentManifestTests.test_readiness_runtime_paths_are_copied_into_image
```

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
  parent's environment and put the root first on `PYTHONPATH`. The child
  imports `server_v2.readiness` normally, installs the recorders, and runs
  readiness. It reports its result to the parent on stdout, behind a marker
  line. Only reads made while readiness runs count; reads made while modules
  import do not. If the child exits non-zero or prints no result, the guard
  fails with an assertion that includes the end of the child's stderr. It never
  raises an error and never skips;
- in the child, record every repository path the run
  - **opens**: any `open`, including `Path.read_text`/`read_bytes`/`open`,
    builtin `open` and `os.open`;
  - **probes**: any `stat` or access check, including
    `Path.exists`/`is_file`/`is_dir`/`stat`/`lstat`,
    `os.path.exists`/`isfile`/`isdir`/`islink`, `os.stat`, `os.lstat` and
    `os.access`;
  - **lists**: `Path.iterdir`/`glob`/`rglob`, `os.listdir` (also with no
    argument), `os.scandir`, `os.walk` and `glob.glob`. Record the listed
    directory.

  Inspecting the module's path constants alone is not enough. The acceptance
  tests insert plain statements into readiness;
- attribute each recorded path to the label of the next `_check` call. Paths
  recorded after the last `_check` call of the run have no label and count as
  **runtime**. Keep every path whose label is not in
  `readiness.PACKAGING_LABELS`, plus the unlabelled ones. A path used by both a
  runtime and a packaging check stays in scope;
- be a single test. When it fails, use an assertion failure (unittest reports
  `FAILED (failures=1)`), not an error. Name every uncovered path,
  repository-relative and POSIX (for example
  `mobile/contracts/live_round_event.schema.json`).

Helper unit tests next to the guard are allowed only if they call the code the
guard itself uses (a module-level helper, or the trace script held as a
module-level constant). Delete helpers the guard does not call, and tests that
check a copy of guard logic.

Suggested approach (not mandatory):

- Keep the recorders cheap. Store each recorded path as
  `os.path.normpath(os.path.join(os.getcwd(), raw))` in a set, and run
  `realpath` and the root-relative mapping once per unique path after
  readiness returns, instead of on every call.
- After `build_readiness_response()` returns, move whatever is still pending
  into an unlabelled bucket. Report it to the parent, for example as label
  `null` or under a separate key, and have the parent treat it as runtime.
- `.dockerignore`: parse each pattern the way Docker does. Strip it, skip
  comments and `!` lines, run `posixpath.normpath`, and drop a leading `/`.
  Then match with a translated regex in which `**/` stands for zero or more
  directories, or with fnmatch over the pattern and its variants that drop
  `**/` segments.
- `COPY` JSON form: after the leading `--` flags, if the rest starts with `[`,
  parse it with `json.loads` into a list of strings. If that fails, treat the
  line as shell form.

Do not edit `server_v2/readiness.py`. The acceptance tests rewrite these lines
of a copy, so keep them exactly as they are:

- the module-level line `LIVE_ROUND_EVENT_CONTRACT = Path("mobile/contracts/live_round_event.schema.json")`;
- `def _contract_event_kinds() -> …:` (runtime, label `mobile_events`) and
  `def _external_release_evidence() -> …:` (packaging, label
  `external_release`), each a one-line signature with no arguments;
- the line `    runtime_checks = [check for check in checks if check.get("label") not in PACKAGING_LABELS]`
  in `build_readiness_response()`, after the last `_check` call;
- `from pathlib import Path` stays imported at module level.

In `Dockerfile`, keep the explicit `COPY mobile/contracts/ ./mobile/contracts/`
and `COPY ops/ ./ops/` lines, each on one line, and do not widen either. Keep
`WORKDIR /app` as the only `WORKDIR` of the runtime stage.

## Scope rules for the guard

- **In scope:** every repository path opened, probed or listed while readiness
  runs, unless every use of it belongs to a check whose label is in
  `readiness.PACKAGING_LABELS`. Today the runtime labels are service, mobile,
  secret_handling, history, sync, course_reference, mobile_package,
  mobile_events, media_context and reports. Reads after the last `_check` call
  are in scope too. The directory does not matter: `ops/` counts even though
  packaging checks also use it.
- **Out of scope (packaging/evidence):** paths used only by checks in
  `PACKAGING_LABELS` (`native_mobile`, `external_release`,
  `roadmap_completion`, `operations`, `private_snapshot_acceptance`), such as
  `mobile/ios/**`, `docs/**`, `render.yaml` and `web_v2/vercel.json`. They are
  excluded by label, not by a path list, and must not fail the guard.
- **The only path-based exclusions allowed:**
  - the private runtime root: `data`, `.garmin_tokens`, `output`, `logs`,
    `backups`, `clubs.json` and everything below them. `ops/start_api.sh`
    symlinks these into `AI_CADDIE_PRIVATE_ROOT`, so they are not image
    content;
  - environments the image builds itself (`.venv`, `node_modules`);
  - Python bytecode caches (`__pycache__/`, `*.pyc`), since the image compiles
    its own;
  - the repository root itself, and paths outside it.

  No other prefix lists (no `ops`, `docs`, `mobile/ios`, …).
- **Reading `Dockerfile`.** Before interpreting instructions, apply Docker's
  default line handling:
  - join a line that ends in `\` with the following line, and keep joining
    while the joined line still ends in `\`;
  - inside a continuation, drop empty lines and lines whose first non-blank
    character is `#`;
  - outside a continuation, skip comment lines and empty lines.

  The instruction is the first whitespace-separated word of each joined line,
  compared case-insensitively. A line that a continuation swallows is part of
  the previous instruction, never an instruction of its own. The arguments of
  `COPY` come in two forms. In shell form they are split like `shlex.split`. In
  JSON form the text after the leading `--` flags starts with `[` and is
  parsed as a JSON array of strings.
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
     - File source: the file lands at `D/<basename of S>` if the raw
       destination ends in `/`, is `.`, or the `COPY` has several sources.
       Otherwise it lands at `D`.
     - Examples with `WORKDIR /app`:
       - these qualify: `COPY mobile/contracts/ ./mobile/contracts/`,
         `COPY mobile/contracts /app/mobile/contracts`,
         `COPY ["mobile/contracts/", "./mobile/contracts/"]`,
         `COPY alembic.ini ./`, and a COPY split over two lines with `\`;
       - these do not: `COPY mobile/contracts/ ./`, and
         `WORKDIR /srv` + `COPY mobile/contracts/ /srv/mobile/contracts/` +
         `WORKDIR /app`;
       - a `COPY` in an earlier build stage does not count.
  2. No `.dockerignore` pattern excludes `P` or one of its parent directories.
     Ignore empty lines, comments and `!` lines. Normalise each pattern the
     way Docker does: strip it, run `posixpath.normpath`, and drop a leading
     `/`. Match it against the repo-relative POSIX path with `fnmatch`
     semantics, where `**/` also matches zero directories (so
     `**/mobile/contracts` and `mobile/**/contracts` both match
     `mobile/contracts`).

## Dockerfile

Static tracing on main found no runtime path missing from the image today.
`mobile/contracts/` (#428), `contracts/canonical/`, `ai_caddie/`, `server_v2/`
and `ops/` are all copied to their own paths under `/app`. In fixture mode the
runtime checks also list and probe directories under `data/` and `output/`.
Those are private-root paths and are excluded. If the guard reports any other
path, add the missing `COPY <dir>/ ./<dir>/` to the runtime stage in this PR.
Leave all other Dockerfile lines alone, and do not change
`.github/workflows/ci.yml`.

### G1 — A repository test guards readiness runtime paths against the image

Pass conditions (each a case in the acceptance module). "Fails the same way"
means: non-zero exit, `Ran 1 test`, `FAILED (failures=1)`, and the output names
the given path. "Passes" means: exit 0, `Ran 1 test`, no `skipped=`.

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
15. On a copy where the line `RUN true \` is inserted directly above the
    unchanged `COPY mobile/contracts/ …` line, it fails the same way and names
    `mobile/contracts`.
16. On a copy where that line becomes the three lines `WORKDIR /srv`,
    `COPY mobile/contracts/ /srv/mobile/contracts/` and `WORKDIR /app`, it fails
    the same way and names `mobile/contracts`.
17. On a copy where `_contract_event_kinds()` first runs
    `__import__("os").access("runtime_probe/access_only.json", 4)` (exists, not
    copied), it fails the same way and names `runtime_probe/access_only.json`.
18. On a copy where readiness gains a module-level
    `functools.lru_cache`-wrapped `_card432_cached_probe()` that reads
    `runtime_probe/cached.json` (exists, not copied), and
    `_contract_event_kinds()` calls it first: run in the warm form, with
    readiness evaluated once in the same interpreter before the guard, it fails
    the same way and names `runtime_probe/cached.json`.
19. On a copy where `build_readiness_response()` reads
    `runtime_probe/tail.json` (exists, not copied) right before its
    `runtime_checks = […]` line, after the last `_check` call, it fails the
    same way and names `runtime_probe/tail.json`. *(new in revision 5)*
20. On a copy where `.dockerignore` gains the line `mobile//contracts/`, it fails
    the same way and names `mobile/contracts`. *(new)*
21. On a copy where `.dockerignore` gains the line `**/mobile/contracts`, it
    fails the same way and names `mobile/contracts`. *(new)*
22. On a copy where the `COPY mobile/contracts/ …` line becomes
    `COPY ["mobile/contracts/", "./mobile/contracts/"]`, it passes. *(new)*

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
5. (Review) No dead helpers and no tests of copied logic in
   `tests/test_deployment_manifests.py`. Each helper test calls code the guard
   itself uses.
6. (Review) The PR body reports the wall time of one guard run and of the whole
   acceptance module, or says exactly which of them could not run in the
   session sandbox and why.

## Not in scope

No app, Watch, web, migration, auth or deploy-script changes, and no change to
`server_v2/readiness.py`. Do not edit the pinned files or `tests/acceptance/`.

Known limits this card does not cover. The guard need not handle them, and a
review should not fail it for them:

- `RUN` steps that delete copied files;
- `ADD` instructions (treated as not shipping anything);
- `.dockerignore` re-inclusion with `!` (treated as still excluded);
- the `# escape=` parser directive, heredocs, `COPY --parents`, and variable
  expansion in `WORKDIR` or `COPY` (the guard may treat values literally);
- a container command that changes directory before starting the API;
- reads made while modules import, reads by threads or subprocesses readiness
  starts, and reads made after `build_readiness_response()` returns;
- attribution when a runtime read is followed by a packaging `_check` call
  before its own `_check` (today's code has no such ordering);
- repository symlinks whose target lies elsewhere in the repository (the
  target path is recorded).
