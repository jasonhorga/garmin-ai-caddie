# Card #432 — Readiness image contract

Every repository path that `server_v2/readiness.py` reads for a check that feeds
`runtimeStatus` must be shipped in the runtime stage of `Dockerfile`. #428 showed
the failure mode (`mobile/contracts/` missing from the image, readiness
`degraded` in production, all tests green).

Touches: `tests/test_deployment_manifests.py`, `Dockerfile`, `tests/acceptance/test_card_432_readiness_image_paths.py`, `.agent/contracts/card-432.md`

Acceptance tests: `tests/acceptance/test_card_432_readiness_image_paths.py` (22 cases)

## Revision 5 (after review of edc640d)

At `edc640d` the guard passes all 18 revision-4 cases (CI green). Re-reading
`tests/test_deployment_manifests.py` at that head turned up four more real
defects and some dead test code. Cases 19–22 are new and cover the defects;
G2.5 covers the dead code.

1. **Reads after the final `_check` are dropped.** The trace gives every path
   recorded since the previous `_check` call to the next call's label. Anything
   recorded after the last `_check` (today `operations`), such as a read while
   `runtime_checks` / `runtimeStatus` is computed, is still in `observed` when
   readiness returns, and the guard throws it away (condition 19).
2. **`.dockerignore` patterns are not normalised the way Docker does it.**
   `_normalise_dockerignore_pattern` removes one leading `./`, then one `/`,
   then trailing `/`. Docker runs `filepath.Clean` first. So
   `/./mobile/./contracts//` excludes `mobile/contracts` in Docker, but the
   guard reads it as `./mobile/./contracts` and finds no match (condition 20).
3. **`.dockerignore` matching uses `fnmatch`, not Docker's matcher.** In Docker,
   `**/` matches zero or more directories, so `mobile/**/contracts` excludes
   `mobile/contracts`. `fnmatch` needs at least one directory between them and
   finds no match (condition 21). Also, Docker's `*` and `?` never match `/`,
   while `fnmatch`'s do.
4. **The JSON-array form of `COPY` is split with `shlex`.**
   `COPY ["mobile/contracts/", "./mobile/contracts/"]` is valid and ships the
   directory. The guard gets the tokens `[mobile/contracts/,` and
   `./mobile/contracts/]`, so it rejects a correct Dockerfile (condition 22).
5. **Dead helpers and helper tests.**
   - `_relative_copy_destination` is never used by the guard, and
     `test_copy_outside_stage_root_is_uncovered` tests only that helper.
   - `test_no_argument_directory_listing_records_current_repository_directory`
     tests its own copy of an audit hook, not the guard's trace script.

   Both pass whatever the guard does (G2.5).

Codex must not touch `tests/acceptance/`. Revision 3 already replaced the edits
Codex commit `9d07b30` made there.

All 22 cases fail on `main`, where the guard test does not exist (unittest
reports `FAILED (errors=1)`). By reading the code, conditions 19–22 also fail on
`edc640d`: the guard passes where 19–21 expect a failure, and fails where 22
expects a pass. Conditions 1–18 should still pass there. I could not run Python
in the contract sandbox, so these results are traced by hand, not observed.

## Interface

Add this test method, exactly this id:

```
tests.test_deployment_manifests.DeploymentManifestTests.test_readiness_runtime_paths_are_copied_into_image
```

Small helper unit tests next to it are fine if they stay green and test code
the guard really uses (G2.5).

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
  imports `server_v2.readiness` normally, then installs the recorders, then
  runs readiness. It reports `{label: [paths]}` to the parent on stdout, behind
  a marker line. Only reads made while readiness runs count; reads made while
  modules import do not. If the child exits non-zero or prints no result, the
  guard fails with an assertion that includes the end of the child's stderr. It
  never raises an error and never skips;
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
  tests insert plain statements into readiness;
- attribute each recorded path to a check label:
  - a path recorded since the previous `_check` call goes to the label of the
    next `_check` call;
  - **new in revision 5:** a path recorded after the last `_check` call, still
    pending when `build_readiness_response()` returns, is in scope. Report it
    under a label that is not in `readiness.PACKAGING_LABELS` (for example
    `<after-final-check>`). Never drop it;
  - keep only paths whose label is **not** in `readiness.PACKAGING_LABELS`. A
    path used by both a runtime and a packaging check stays in scope;
- be a single test. When it fails, use an assertion failure (unittest reports
  `FAILED (failures=1)`), not an error, and name every uncovered path,
  repository-relative and POSIX (for example
  `mobile/contracts/live_round_event.schema.json`).

Do not edit `server_v2/readiness.py`. The acceptance tests rewrite these lines
of a copy, so they must stay as they are:

- the module-level line `LIVE_ROUND_EVENT_CONTRACT = Path("mobile/contracts/live_round_event.schema.json")`;
- `def _contract_event_kinds() -> …:` (runtime, label `mobile_events`) and
  `def _external_release_evidence() -> …:` (packaging, label
  `external_release`), each a one-line signature with no arguments;
- `from pathlib import Path` stays imported at module level;
- inside `build_readiness_response()`, the first statement after the final
  `_check` call begins with the line `    runtime_checks = [` (four-space
  indent). Condition 19 inserts a statement just above it.

In `Dockerfile`, keep the explicit `COPY mobile/contracts/ ./mobile/contracts/`
and `COPY ops/ ./ops/` lines, each on one line, and do not widen either. Keep
`WORKDIR /app` as the only `WORKDIR` of the runtime stage.

## Scope rules for the guard

- **In scope:** every repository path opened, probed or listed while readiness
  evaluates a check whose label is not in `readiness.PACKAGING_LABELS` (today:
  service, mobile, secret_handling, history, sync, course_reference,
  mobile_package, mobile_events, media_context, reports). This includes every
  path recorded after the final `_check` call, and it holds whatever directory
  the path is in, including directories that packaging checks also use, such
  as `ops/`.
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
- **Reading `COPY` arguments** (*JSON form new in revision 5*):
  - First take the leading `--` flags off the arguments (`--from=`,
    `--chown=`, `--chmod=`, `--link` and any other `--` flag). Flags are never
    sources. A `COPY` with `--from=` ships nothing from the context.
  - If what is left starts with `[` and parses with `json.loads` as a list of
    two or more strings, that list is the sources followed by the destination
    (exec form). For example, `COPY ["mobile/contracts/", "./mobile/contracts/"]`
    has source `mobile/contracts/` and destination `./mobile/contracts/`.
  - Otherwise split it into words the shell way. If that fails, the `COPY`
    ships nothing.
- **Shipped.** A path `P` counts as shipped only when both of these hold:
  1. There is a `COPY` instruction in the **final** `FROM` stage, without
     `--from=`, with a source `S` equal to `P` or a parent directory of `P`.
     That `COPY` must place `P` at `<runtime root>/P`:
     - The **runtime root** is the `WORKDIR` in effect at the end of the final
       stage (`/` if there is none). Track `WORKDIR` through the stage: an
       absolute value replaces it, a relative value joins onto it.
     - Normalise each source: drop a leading `./` and a trailing `/`, and treat
       an empty result as `.`.
     - Resolve the destination `D` to an absolute path. Join a relative `D`
       onto the `WORKDIR` in effect at that `COPY`, then normalise it.
     - Directory source (`S` is a directory in the tree, or `.`): its contents
       land in `D`, so `P` lands at `D/<P relative to S>`.
     - File source: if the raw destination ends in `/`, is `.`, or the `COPY`
       has several sources, the file lands at `D/<basename of S>`. Otherwise
       it lands at `D`.
     - Examples with `WORKDIR /app`:
       - these qualify: `COPY mobile/contracts/ ./mobile/contracts/`,
         `COPY mobile/contracts /app/mobile/contracts`,
         `COPY ["mobile/contracts/", "./mobile/contracts/"]`,
         `COPY alembic.ini ./`, and a COPY split over two lines with `\`;
       - these do not: `COPY mobile/contracts/ ./`, and
         `WORKDIR /srv` + `COPY mobile/contracts/ /srv/mobile/contracts/` +
         `WORKDIR /app`;
       - a `COPY` in an earlier build stage does not count.
  2. No `.dockerignore` exclusion pattern matches `P` or one of its parent
     directories. Docker's rules apply (*new in revision 5*; this replaces
     `fnmatch`):
     - **Reading lines.** A line whose first character is `#` is a comment.
       Otherwise strip surrounding whitespace and skip empty lines. A line
       that starts with `!` is a re-inclusion; the guard ignores it (known
       limit below).
     - **Normalising.** Clean the pattern the way Go's `filepath.Clean` does:
       collapse repeated `/`, remove `.` elements, resolve `..` lexically, and
       drop the trailing `/`. Then, if the result is longer than one character
       and starts with `/`, drop that `/`. For example,
       `/./mobile/./contracts//`, `./mobile//contracts/` and `/mobile/contracts`
       all become `mobile/contracts`. Note that `posixpath.normpath` keeps a
       leading `//`; collapse that too.
     - **Matching.** Match the cleaned pattern against the whole
       repo-relative POSIX path, anchored at both ends:
       - `**` followed by `/` matches zero or more whole directories
         (regex `(.*/)?`, with the `/` consumed);
       - `**` at the end matches anything (`.*`);
       - `*` matches any run of characters except `/` (`[^/]*`);
       - `?` matches one character except `/` (`[^/]`);
       - `[...]` is a character class and `\` escapes the next character, as
         in Go's `filepath.Match`;
       - every other character matches itself.

       So `mobile/**/contracts` matches `mobile/contracts` and
       `mobile/a/b/contracts`. `*/live_round_event.schema.json` matches only
       one directory level, and `__pycache__` matches only the top-level
       directory.

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
19. On a copy where `build_readiness_response()` gets the statement
    `Path("runtime_probe/after_final_check.json").read_text(encoding="utf-8")`
    directly above `    runtime_checks = [`, after the final `_check` call (the
    file exists, nothing copies it), it fails the same way and names
    `runtime_probe/after_final_check.json`. *(new in revision 5)*
20. On a copy where `.dockerignore` gains the line `/./mobile/./contracts//`,
    it fails the same way and names `mobile/contracts`. *(new)*
21. On a copy where `.dockerignore` gains the line `mobile/**/contracts`, it
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
5. **No dead helpers or dead helper tests** in
   `tests/test_deployment_manifests.py` (*new in revision 5*; the reviewer
   checks this, there is no acceptance case for it):
   - every module-level helper added for this card is called by the guard;
   - every helper unit test exercises a helper the guard calls, or the
     guard's own trace script;
   - remove `_relative_copy_destination` and
     `test_copy_outside_stage_root_is_uncovered`;
   - remove `test_no_argument_directory_listing_records_current_repository_directory`,
     or rewrite it to run the guard's real trace script, for example by moving
     the script into a module-level constant that both the guard and the test
     use, rather than a copy of the hook;
   - update `test_dockerignore_root_pattern_is_normalized` to the
     Docker-style normalisation. Helper tests for the new `.dockerignore`
     matcher and the JSON-form `COPY` parser are welcome.

## Not in scope

No app, Watch, web, migration, auth or deploy-script changes, and no change to
`server_v2/readiness.py`. Do not edit the pinned files or `tests/acceptance/`.
Known limits this card does not cover:

- `RUN` steps that delete copied files;
- `ADD` instructions (treated as not shipping anything);
- `.dockerignore` re-inclusion with `!` (treated as still excluded);
- reads that happen while modules import.
