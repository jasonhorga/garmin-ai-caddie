# Card #432 — Readiness image contract

Every repository path that `server_v2/readiness.py` reads for a check that feeds
`runtimeStatus` must be shipped in the runtime stage of `Dockerfile`. #428 showed
the failure mode (`mobile/contracts/` missing from the image, readiness
`degraded` in production, all tests green).

Touches: `tests/test_deployment_manifests.py`, `Dockerfile`, `tests/acceptance/test_card_432_readiness_image_paths.py`, `.agent/contracts/card-432.md`

Acceptance tests: `tests/acceptance/test_card_432_readiness_image_paths.py` (29 cases)

## Revision 6 (owner request: narrow the supported syntax)

Revisions 4 and 5 asked the guard to copy more and more of Docker's grammar:
`filepath.Clean` normalisation, `**`, character classes, backslash escapes and
JSON/exec-form `COPY`. The owner narrowed the scope. The guard now has to
understand only the syntax that `Dockerfile` and `.dockerignore` use today. On
anything else it **fails closed** with one assertion:

```
unsupported Dockerfile/.dockerignore syntax: <line>; extend the guard
```

What stays:

- the core goal: every runtime path readiness reads is copied into the final
  stage (G1, G2);
- the instruction-word rule `line.split(None, 1)[0].upper()`;
- comment detection on the **raw** line, before any stripping: a line is a
  comment only when its first character is `#`.

What goes, and why it no longer counts as a finding:

- full Docker grammar, JSON/exec-form `COPY`, `.dockerignore` character
  classes, backslash escapes, `**`, `?`, and normalising unclean patterns.
  Code for these must be removed (G2.5). If the guard rejects one of these
  constructs with the assertion above, that is the intended behaviour. A review
  finding that the guard "does not support" such a construct is **out of
  scope**.

Changes to the cases:

- conditions 20–22 changed from "match like Docker" to "rejected with the
  assertion";
- conditions 23–29 are new (G3).

Codex must not touch `tests/acceptance/`.

All 29 cases fail on `main`, where the guard test does not exist (unittest
reports `FAILED (errors=1)`). I could not run Python in the contract sandbox.
The expectations below come from reading the code by hand, not from runs.

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
acceptance tests locally, or the copy will not contain it.

The guard must:

- find the repository root from the test file or the working directory. Do not
  hard-code an absolute path;
- read `Dockerfile` and `.dockerignore` from that root;
- **run** `build_readiness_response()` in a fresh child interpreter
  (`subprocess.run([sys.executable, "-c", <script>], cwd=root, …)`):
  - pass on the parent's environment and put the root first on `PYTHONPATH`;
  - in the child, import `server_v2.readiness` normally, then install the
    recorders, then run readiness;
  - report `{label: [paths]}` to the parent on stdout, behind a marker line;
  - only reads made while readiness runs count; reads made while modules
    import do not;
  - if the child exits non-zero or prints no result, fail with an assertion
    that includes the end of the child's stderr. Never raise an error and never
    skip;
- in the child, record every repository path the run:
  - **opens**: any `open`, including `Path.read_text`/`read_bytes`/`open`,
    builtin `open` and `os.open`;
  - **probes**: any `stat` or access check, including
    `Path.exists`/`is_file`/`is_dir`/`stat`/`lstat`,
    `os.path.exists`/`isfile`/`isdir`/`islink`, `os.stat`, `os.lstat` and
    `os.access`;
  - **lists**: `Path.iterdir`/`glob`/`rglob`, `os.listdir`, `os.scandir`,
    `os.walk` and `glob.glob`. Record the listed directory.

  Inspecting the module's path constants alone is not enough: the acceptance
  tests insert plain statements into readiness;
- attribute each recorded path to a check label:
  - a path recorded since the previous `_check` call goes to the label of the
    next `_check` call;
  - a path recorded after the last `_check` call, still pending when
    `build_readiness_response()` returns, is in scope. Report it under a label
    that is not in `readiness.PACKAGING_LABELS` and never drop it;
  - keep only paths whose label is **not** in `readiness.PACKAGING_LABELS`. A
    path used by both a runtime and a packaging check stays in scope;
- parse `Dockerfile` and `.dockerignore` under the supported-syntax rules
  below, and fail closed on anything else (G3);
- be a single test. Every failure is an assertion failure (unittest reports
  `FAILED (failures=1)`), never an error:
  - an uncovered path: the failure names every uncovered path,
    repository-relative and POSIX (for example
    `mobile/contracts/live_round_event.schema.json`);
  - unsupported syntax or a parse error: see G3. This assertion replaces the
    coverage result, so the guard does not also list uncovered paths.

Do not edit `server_v2/readiness.py`. The acceptance tests rewrite these lines
of a copy, so they must stay as they are:

- the module-level line `LIVE_ROUND_EVENT_CONTRACT = Path("mobile/contracts/live_round_event.schema.json")`;
- `def _contract_event_kinds() -> …:` (runtime, label `mobile_events`) and
  `def _external_release_evidence() -> …:` (packaging, label
  `external_release`), each a one-line signature with no arguments;
- `from pathlib import Path`, imported at module level;
- the first statement after the final `_check` call inside
  `build_readiness_response()`, which begins with the line
  `    runtime_checks = [` (four-space indent).

In `Dockerfile`, do not widen these lines, and keep each on one line:

- the explicit `COPY mobile/contracts/ ./mobile/contracts/`;
- `COPY ops/ ./ops/`.

Keep `WORKDIR /app` as the only `WORKDIR` of the runtime stage.

## Scope rules for the guard

- **In scope:** every repository path opened, probed or listed while readiness
  evaluates a check whose label is not in `readiness.PACKAGING_LABELS` (today:
  service, mobile, secret_handling, history, sync, course_reference,
  mobile_package, mobile_events, media_context, reports). This includes every
  path recorded after the final `_check` call. Scope depends on the label, not
  the directory, so it includes directories that packaging checks also use,
  such as `ops/`.
- **Out of scope (packaging/evidence):** paths used only by checks in
  `PACKAGING_LABELS` (`native_mobile`, `external_release`,
  `roadmap_completion`, `operations`, `private_snapshot_acceptance`), such as
  `mobile/ios/**`, `docs/**`, `render.yaml` and `web_v2/vercel.json`. They are
  excluded by label, not by a path list, and must not fail the guard.
- **The only path-based exclusions allowed:**
  - the private runtime root `data`, `.garmin_tokens`, `output`, `logs`,
    `backups` and `clubs.json`, and everything below them. `ops/start_api.sh`
    symlinks these into `AI_CADDIE_PRIVATE_ROOT`, so they are not image
    content;
  - image-built environments (`.venv`, `node_modules`);
  - Python bytecode caches (`__pycache__/`, `*.pyc`);
  - the repository root itself and paths outside it.

  No other prefix lists (no `ops`, `docs`, `mobile/ios`, …).

## Supported syntax (revision 6)

The guard must accept everything the repository's `Dockerfile` and
`.dockerignore` contain today, and nothing else. Every rule below either
accepts a line or rejects it with the G3 assertion. No rule may silently skip
or mis-read a line.

### `Dockerfile`

- **Lines.** Read the file as UTF-8.
  - A raw line whose first character is `#` is a comment and is skipped.
    Check this before stripping anything. The exception is a parser directive
    that changes parsing: a comment matching `#\s*escape\s*=` (any case) is
    unsupported.
  - A line that is empty after stripping is skipped.
  - Otherwise strip the line. If it ends in `\`, drop the `\` and join the next
    line onto it with one space. Keep joining while the joined line ends in
    `\`. Comment and empty lines inside a continuation are skipped as above.
  - A continuation still open at the end of the file is unsupported.
- **Instruction word.** It is `line.split(None, 1)[0].upper()` of the joined
  line. A line that a continuation swallowed is part of the previous
  instruction, never an instruction of its own. So an indented `#` line is not
  a comment: its instruction word is `#`, which is unsupported.
- **Supported instructions:** `FROM`, `WORKDIR`, `COPY`, `RUN`, `ENV`,
  `EXPOSE`, `CMD`. Any other word, including `ADD`, `ARG`, `USER`, `ONBUILD`
  and `#`, is unsupported.
- **`FROM`:**
  - `FROM <image>` or `FROM <image> AS <name>`, with `AS` in any case;
  - `<image>` matches `[A-Za-z0-9._/:@-]+` and `<name>` matches
    `[A-Za-z0-9._-]+`;
  - anything else is unsupported, including flags and `$`.
  - Each `FROM` starts a new stage, and the `WORKDIR` resets to `/`.
- **`WORKDIR`:**
  - exactly one argument, absolute, matching `/[A-Za-z0-9._/-]*`;
  - a missing argument, a relative path, extra words or `$` are unsupported;
  - the value replaces the current `WORKDIR`.
- **`COPY` (shell form only):**
  - Split the arguments on whitespace.
  - At most one flag is allowed: `--from=<stage>` as the first word, where
    `<stage>` matches `[A-Za-z0-9._-]+`. Any other word starting with `--` is
    unsupported, including `--chown`, `--chmod`, `--link` and a second flag.
  - After the flag come at least two words, each matching `[A-Za-z0-9._/-]+`.
    So quotes, wildcards, `$`, `\` and the JSON/exec form (`COPY [...]`) are
    unsupported.
  - In a `COPY` without `--from=`, a source that starts with `/` or has a `..`
    segment is unsupported.
  - A `COPY --from=` ships nothing from the context. The guard validates it
    and otherwise ignores it.
- **`RUN`, `ENV`, `EXPOSE`, `CMD`:**
  - their arguments are not interpreted (the existing JSON-form `CMD` is fine);
  - an argument containing `<<` (a heredoc) is unsupported, because heredoc
    body lines would be read as instructions.
- **Every stage is validated,** not only the final one.

### `.dockerignore`

- **Lines.** Read the file as UTF-8.
  - A raw line whose first character is `#` is a comment and is skipped.
    Check this before stripping.
  - Otherwise strip surrounding whitespace, and skip the line if it is empty.
  - A line starting with `!` is a re-inclusion. Validate its pattern like any
    other, then ignore it: the path stays excluded. That is a fail-closed known
    limit, and the repository has `!.env.example`.
- **Supported pattern** (after the optional `!`):
  - only `[A-Za-z0-9._/*-]` characters;
  - no `**`;
  - split on `/`, every segment is non-empty and is neither `.` nor `..`. So
    there is no leading or trailing `/` and no `//`.

  Everything else is unsupported, for example:
  - `?`, character classes `[...]`, backslash escapes, `**`;
  - `./`, a leading `/`, a trailing `/`;
  - spaces and an indented `#`.

  No normalisation is done.
- **Matching.** Anchor the pattern at both ends of the whole repo-relative
  POSIX path. `*` matches any run of characters except `/` (`[^/]*`), and
  every other character matches itself. A path is excluded when the pattern
  matches the path or one of its parent directories.
- **A missing `.dockerignore`** means no patterns. A missing `Dockerfile`
  ships nothing: the guard reports the runtime paths as uncovered, with the
  normal coverage assertion.

### Shipped

A path `P` counts as shipped only when both of these hold:

1. There is a `COPY` in the **final** `FROM` stage, without `--from=`, with a
   source `S` equal to `P` or a parent directory of `P`. That `COPY` must place
   `P` at `<runtime root>/P`:
   - The **runtime root** is the `WORKDIR` in effect at the end of the final
     stage, or `/` if there is none.
   - Normalise each source: drop a leading `./` and a trailing `/`, and treat
     an empty result as `.`.
   - Resolve the destination `D`: join a relative `D` onto the `WORKDIR` in
     effect at that `COPY`, then normalise it.
   - **Directory source** (`S` is a directory in the tree, or `.`): its
     contents land in `D`, so `P` lands at `D/<P relative to S>`.
   - **File source:** if the raw destination ends in `/`, is `.`, or the `COPY`
     has several sources, the file lands at `D/<basename of S>`. Otherwise it
     lands at `D`.
   - Examples with `WORKDIR /app`:
     - these qualify: `COPY mobile/contracts/ ./mobile/contracts/`,
       `COPY mobile/contracts /app/mobile/contracts`, `COPY alembic.ini ./`,
       and a `COPY` split over two lines with `\`;
     - these do not: `COPY mobile/contracts/ ./`, and the sequence
       `WORKDIR /srv`, `COPY mobile/contracts/ /srv/mobile/contracts/`,
       `WORKDIR /app`;
     - a `COPY` in an earlier build stage does not count.
2. No `.dockerignore` exclusion pattern excludes `P`.

## Dockerfile

Static tracing on `main` found no runtime path missing from the image today.
`mobile/contracts/` (#428), `contracts/canonical/`, `ai_caddie/`, `server_v2/`
and `ops/` are all copied to their own paths under `/app`. In fixture mode the
runtime checks also list and probe directories under `data/` and `output/`.
Those are private-root paths and are excluded.

If the guard reports any other path, add the missing `COPY <dir>/ ./<dir>/` to
the runtime stage in this PR. Leave all other Dockerfile lines alone, and do
not change `.github/workflows/ci.yml`. Today's `Dockerfile` and `.dockerignore`
must parse under the supported syntax unchanged (G2.1).

### G1 — A repository test guards readiness runtime paths against the image

Pass conditions (each a case in the acceptance module):

- **"Fails the same way"** means a non-zero exit, `Ran 1 test`,
  `FAILED (failures=1)`, and the output names the given path.
- **"Passes"** means exit 0, `Ran 1 test`, not skipped.

1. The test id above exists, runs as one test, and does not skip.
2. On a copy with the `COPY mobile/contracts/ …` line removed from
   `Dockerfile`, it fails and names `mobile/contracts`.
3. On a copy where that `COPY` line is moved into the first (`node-deps`)
   build stage, it fails the same way and names `mobile/contracts`.
4. On a copy where that line becomes `COPY mobile/contracts/ ./`, it fails the
   same way and names `mobile/contracts`.
5. On a copy where that line becomes
   `COPY mobile/contracts /app/mobile/contracts` (`WORKDIR /app`), it passes.
6. On a copy where `.dockerignore` gains the line `mobile/contracts`, it fails
   the same way and names `mobile/contracts`.
7. On a copy where `readiness.LIVE_ROUND_EVENT_CONTRACT` points at
   `relocated_contracts/live_round_event.schema.json` (the file exists there),
   it fails the same way and names `relocated_contracts`.
8. On a copy where `_contract_event_kinds()` (runtime) first reads
   `runtime_probe/extra.json` (the file exists, nothing copies it), it fails
   the same way and names `runtime_probe/extra.json`.
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
    `COPY mobile/contracts/ /srv/mobile/contracts/` and `WORKDIR /app`, it
    fails the same way and names `mobile/contracts`.
17. On a copy where `_contract_event_kinds()` first runs
    `__import__("os").access("runtime_probe/access_only.json", 4)` (exists, not
    copied), it fails the same way and names `runtime_probe/access_only.json`.
18. On a copy where readiness gains a module-level
    `functools.lru_cache`-wrapped `_card432_cached_probe()` that reads
    `runtime_probe/cached.json` (exists, not copied), and
    `_contract_event_kinds()` calls it first: in the warm form (readiness
    already evaluated once in the same interpreter before the guard runs), it
    fails the same way and names `runtime_probe/cached.json`.
19. On a copy where `build_readiness_response()` gets the statement
    `Path("runtime_probe/after_final_check.json").read_text(encoding="utf-8")`
    directly above `    runtime_checks = [`, after the final `_check` call (the
    file exists, nothing copies it), it fails the same way and names
    `runtime_probe/after_final_check.json`.

### G2 — The production image ships every runtime path readiness reads

Pass conditions:

1. On an unchanged copy of the checkout's tracked files, the guard passes
   (exit 0, `Ran 1 test`, not skipped). This includes today's `Dockerfile` and
   `.dockerignore` parsing under the supported syntax with no rejection.
2. Any path the guard reported was fixed by adding a `COPY` to the runtime
   stage of `Dockerfile`, not by adding the path to an exclusion list.
3. The existing `tests/test_deployment_manifests.py` tests and the rest of the
   backend suite stay green in fixture mode, including when the guard runs
   inside the full `unittest discover -s tests` run.
4. After release, production `/api/v2/health` reports the merged revision, and
   readiness `runtimeStatus` is still `ready`. The release-tier run checks this
   read-only.
5. **No dead helpers or dead helper tests** in
   `tests/test_deployment_manifests.py`. The reviewer checks this; there is no
   acceptance case for it.
   - Every module-level helper added for this card is called by the guard.
   - Every helper unit test exercises a helper the guard calls.
   - Remove the code that is out of scope now:
     - `.dockerignore` normalisation (`_normalise_dockerignore_pattern`) and
       its test `test_dockerignore_root_pattern_is_normalized`;
     - character-class, backslash-escape and `**` handling in
       `_dockerignore_matches`;
     - the JSON-form `COPY` branch;
     - `shlex` parsing of `COPY` and `WORKDIR`.
   - Helper tests for the new line validators are welcome.
   - Keep `test_docker_instruction_word_accepts_tab_separated_from_and_copy`
     green. Comment detection moves to the raw line, so the instruction-word
     helper itself no longer treats a stripped `#…` line as a comment.

### G3 — The guard reads only the repository's current syntax and fails closed on anything else

The guard must apply the rules in "Supported syntax (revision 6)". It also
fails closed on **any** exception raised while reading or parsing `Dockerfile`
or `.dockerignore`, for example a decode error or an `IndexError` from a short
line. The guard's own assertion is the only exception that passes through.

Every rejection is exactly one assertion failure (`FAILED (failures=1)`, never
`errors=`) with the message:

```
unsupported Dockerfile/.dockerignore syntax: <line>; extend the guard
```

What `<line>` is:

- the offending line with surrounding whitespace stripped;
- for a `Dockerfile` instruction continued over several lines, the joined
  instruction;
- for an error that has no line in hand (for example a file that is not
  UTF-8), the file name, `Dockerfile` or `.dockerignore`.

How the guard reports it:

- It stops at the first unsupported line: `Dockerfile` in file order, then
  `.dockerignore` in file order.
- The message appears once in the output.
- It does not also report uncovered paths.

**"Rejected"** below means: a non-zero exit, `Ran 1 test`,
`FAILED (failures=1)`, and the output contains that message for the given
`<line>` exactly once.

20. `.dockerignore` gains `/./mobile/./contracts//`: rejected with that line.
    *(changed in revision 6)*
21. `.dockerignore` gains `mobile/**/contracts`: rejected with that line.
    *(changed)*
22. The `COPY mobile/contracts/ …` line becomes
    `COPY ["mobile/contracts/", "./mobile/contracts/"]`: rejected with that
    line. *(changed)*
23. `.dockerignore` gains `mobile/[c]ontracts`: rejected with that line.
    *(new)*
24. `.dockerignore` gains `mobile/contract\s`: rejected with that line.
    *(new)*
25. The `COPY mobile/contracts/ …` line becomes
    `ADD mobile/contracts/ ./mobile/contracts/`: rejected with that line.
    *(new)*
26. The line `    # card432 indented comment` is inserted above the unchanged
    `COPY mobile/contracts/ …` line: rejected with
    `# card432 indented comment`. *(new)*
27. The line `# card432 comment` (column 1) is inserted above the unchanged
    `COPY mobile/contracts/ …` line, and `.dockerignore` gains
    `#mobile/contracts`: it **passes**. Both are raw-line comments. *(new)*
28. A bare `WORKDIR` line is inserted above the unchanged
    `COPY mobile/contracts/ …` line: rejected with `WORKDIR`. *(new)*
29. `.dockerignore` gains a line holding the bytes `\xff\xfe`, which are not
    UTF-8: non-zero exit, `Ran 1 test`, `FAILED (failures=1)`, and the output
    matches
    `unsupported Dockerfile/\.dockerignore syntax: [^\n]*; extend the guard`.
    Either `<line>` = `.dockerignore` or a rejected decoded line is fine.
    *(new)*

**Out of scope.** A finding that the guard does not support full Docker
grammar, JSON/exec-form `COPY`, `.dockerignore` character classes, backslash
escapes, `**`, `?`, pattern normalisation, or other `COPY` flags is out of
scope when the guard rejects that construct with the G3 assertion. Supporting
it is a later card, written when the repository starts to use it.

## Not in scope

No app, Watch, web, migration, auth or deploy-script changes, and no change to
`server_v2/readiness.py`. Do not edit the pinned files or `tests/acceptance/`.

Known limits this card does not cover:

- `RUN` steps that delete copied files;
- `.dockerignore` re-inclusion with `!` (validated, then treated as still
  excluded);
- reads that happen while modules import;
- syntax outside "Supported syntax (revision 6)", which is rejected rather
  than interpreted.
