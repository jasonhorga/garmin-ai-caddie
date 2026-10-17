# Card #432 — Readiness image contract

Every repository path that `server_v2/readiness.py` reads for a check that feeds
`runtimeStatus` must be shipped in the runtime stage of `Dockerfile`. #428 showed
the failure mode (`mobile/contracts/` missing from the image, readiness
`degraded` in production, all tests green).

Touches: `tests/test_deployment_manifests.py`, `Dockerfile`, `tests/acceptance/test_card_432_readiness_image_paths.py`, `.agent/contracts/card-432.md`

Acceptance tests: `tests/acceptance/test_card_432_readiness_image_paths.py` (33 cases)

## Revision 7: narrowed syntax, fail closed

This revision replaces the revision 5 and 6 rules that asked the guard to copy
Docker's parser: the JSON (exec) form of `COPY`, `filepath.Clean`
normalisation, and the full `.dockerignore` glob language (`**`, `?`, `[...]`
classes, `\` escapes). The owner asked for the opposite. The guard supports
**only the Dockerfile and `.dockerignore` syntax this repository uses today**.
Any other construct it meets, and any internal parse error, makes it fail
closed with exactly this sentence:

```
unsupported Dockerfile/.dockerignore syntax: <line>; extend the guard
```

**Out of scope when rejected.** The guard does not need to interpret JSON/exec
`COPY`, bracket character classes, escapes, heredocs, variable substitutions,
parser directives, `**` or `?` patterns, uncleaned patterns, unknown
instructions or `COPY` flags, or any other construct not listed under
"Supported syntax". Rejecting them with the sentence above is the required
behaviour. Supporting one of them later means extending the guard and this
contract in a new card.

These stay as they were: the core goal (runtime-path `COPY` coverage, G1 and
G2), instruction-word parsing (the first word of each joined line, compared
case-insensitively), and the `.dockerignore` comment rule (a comment is a line
whose **raw** first character is `#`).

Changes to the acceptance cases:

- Conditions 20–22 are inverted. `/./mobile/./contracts//`, `mobile/**/contracts`
  and `COPY ["mobile/contracts/", "./mobile/contracts/"]` must now be
  **rejected** with the sentence. They are no longer emulated or accepted.
- G3 conditions 23–33 are new.

Codex must not touch `tests/acceptance/`.

All 33 cases fail on `main`, where the guard test does not exist (unittest
reports `FAILED (errors=1)`). Reading the code at `8f3bba1`, the guard there
fails conditions 20–30 and 32: it accepts or emulates the construct, or for
condition 30 raises `IndexError` (an error, not a failure). It should pass
conditions 1–19, 31 and 33. I could not run Python in the contract sandbox, so
these results are traced by hand, not observed.

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
  - a path recorded after the last `_check` call, still pending when
    `build_readiness_response()` returns, is in scope. Report it under a label
    that is not in `readiness.PACKAGING_LABELS`. Never drop it;
  - keep only paths whose label is **not** in `readiness.PACKAGING_LABELS`. A
    path used by both a runtime and a packaging check stays in scope;
- be a single test. When it fails, use an assertion failure (unittest reports
  `FAILED (failures=1)`), not an error. The failure message must
  - name every uncovered path, repository-relative and POSIX (for example
    `mobile/contracts/live_round_event.schema.json`);
  - contain the unsupported-syntax sentence verbatim for every rejected line,
    in file order. Build the message as plain text (for example with
    `self.fail("\n".join(...))`), not as the `repr` of a list, so that
    backslashes and tabs are not escaped.

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
`WORKDIR /app` as the only `WORKDIR` of the runtime stage. Do not introduce any
construct outside "Supported syntax" into `Dockerfile` or `.dockerignore`.

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

## Supported syntax (revision 7)

This is the whole language the guard understands. It covers every construct in
today's `Dockerfile` and `.dockerignore`. Everything else is rejected.

### `Dockerfile` lines

- **Joining.** A line whose text ends in `\` (after trailing whitespace is
  removed) is joined with the following line, and joining continues while the
  joined line still ends in `\`. Inside a continuation, empty lines and lines
  whose first non-blank character is `#` are dropped. The joined *logical
  line* is each part stripped of surrounding whitespace, with the trailing `\`
  removed, joined by single spaces.
- **Skipped.** Outside a continuation, empty lines and lines whose first
  non-blank character is `#` are skipped. Exception: a comment line before the
  first instruction that has the parser-directive form `# <name>=<value>`
  (for example `# syntax=…`, `# escape=…`) is **rejected**.
- **Instruction word.** The instruction is the first whitespace-separated word
  (spaces or tabs) of the logical line, compared case-insensitively. A line a
  continuation swallows is part of the previous instruction, never an
  instruction of its own. The arguments are the remaining words, split on runs
  of whitespace (no shell quoting, no `shlex`, no JSON).
- **Supported instructions:** `FROM`, `WORKDIR`, `COPY`, `RUN`, `ENV`,
  `EXPOSE` and `CMD`. Any other instruction word (`ADD`, `ARG`, `USER`,
  `LABEL`, `SHELL`, `ONBUILD`, `VOLUME`, `ENTRYPOINT`, a stray word, …) is
  rejected.
- **Heredocs.** A logical line of any instruction that contains `<<` is
  rejected.
- **Opaque instructions.** `RUN`, `ENV`, `EXPOSE` and `CMD` are otherwise not
  interpreted. Their arguments may contain anything, for example `&&`, `$`,
  or `CMD ["sh", "ops/start_api.sh"]`.
- A **plain word** matches `[A-Za-z0-9_./-]+`. `FROM`, `WORKDIR` and `COPY`
  accept only these forms; anything else in them is rejected. That includes
  `$`/`${…}` substitutions, quotes, `\` escapes, `[`/JSON exec form, glob
  characters `*` `?` `[` `]`, and a missing or extra argument:
  - `FROM <image>` or `FROM <image> AS <name>` (`AS` in any case). `<image>`
    matches `[A-Za-z0-9_./:@-]+` and `<name>` is a plain word. A `FROM` starts
    a new stage and resets `WORKDIR` to `/`;
  - `WORKDIR <plain word>`, with exactly one argument. An absolute value
    replaces the current `WORKDIR` and a relative one joins onto it;
  - `COPY [--from=<plain word>] <source plain word>… <destination plain word>`.
    That is at most one leading flag, and the only supported flag is
    `--from=`. Then at least two plain words. Any other `--` flag
    (`--chown`, `--chmod`, `--link`, `--exclude`, `--parents`, …) is rejected.
    A `COPY --from=` ships nothing from the build context.
- These rules apply to every stage, not only the final one.

### `.dockerignore` lines

- **Comments (raw rule).** A line whose first character, before any
  whitespace is removed, is `#` is a comment. A `#` after leading whitespace is
  pattern text, and pattern text cannot contain `#`, so that line is rejected.
- Otherwise strip surrounding whitespace and skip empty lines.
- A leading `!` marks a re-inclusion. The rest of the line must still be a
  supported pattern. The guard then ignores it, so the path stays excluded
  (a known limit that errs on the side of failing).
- A **supported pattern** is one or more segments joined by single `/`. Each
  segment matches `[A-Za-z0-9_.*-]+`, is not `.` or `..`, and does not contain
  `**`. So a leading or trailing `/`, `//`, `./`, `**`, `?`, `[`, `]`, `\`,
  `#`, spaces and every other character are rejected.
- **Matching.** A pattern excludes a path when it fully matches the path or
  one of its parent directories, as a repository-relative POSIX path. `*`
  matches any run of characters except `/`. Every other character matches
  itself. For example, `data` excludes `data/x.json` but not `ops/data`, and
  `*.pyc` excludes only top-level `.pyc` names.

### Fail-closed reporting

- A rejected line is reported as
  `unsupported Dockerfile/.dockerignore syntax: <line>; extend the guard`.
  `<line>` is the `Dockerfile` logical line as defined above, or the
  `.dockerignore` line stripped of surrounding whitespace (with its `!`, if it
  has one).
- **Internal parse errors** are reported the same way: any exception raised
  while reading or interpreting one `Dockerfile` logical line or `.dockerignore`
  line. Catch it per line and report that line with the same sentence. The
  test must never end as an error. A file that is not valid UTF-8 also fails as
  an assertion; the message names the file.
- Any rejected line fails the guard, even when every runtime path would
  otherwise be covered. The guard may also report uncovered paths in the same
  failure.
- A missing `Dockerfile` fails the guard. A missing `.dockerignore` means no
  exclusions.

### Shipped

A path `P` counts as shipped only when both of these hold, given that no line
was rejected:

1. There is a `COPY` in the **final** `FROM` stage, without `--from=`, with a
   source `S` equal to `P` or to a parent directory of `P`. That `COPY` must
   place `P` at `<runtime root>/P`:
   - The **runtime root** is the `WORKDIR` in effect at the end of the final
     stage (`/` if there is none).
   - Normalise each source: drop a leading `./` and a trailing `/`, and treat
     an empty result as `.`.
   - Resolve the destination `D` to an absolute path. Join a relative `D` onto
     the `WORKDIR` in effect at that `COPY`, then normalise it.
   - Directory source (`S` is a directory in the tree, or `.`): its contents
     land in `D`, so `P` lands at `D/<P relative to S>`.
   - File source: if the raw destination ends in `/`, is `.`, or the `COPY`
     has several sources, the file lands at `D/<basename of S>`. Otherwise it
     lands at `D`.
   - Examples with `WORKDIR /app`:
     - these qualify: `COPY mobile/contracts/ ./mobile/contracts/`,
       `COPY mobile/contracts /app/mobile/contracts`, `COPY alembic.ini ./`,
       `copy<TAB>mobile/contracts/<TAB>./mobile/contracts/`, and a `COPY` split
       over two lines with `\`;
     - these do not: `COPY mobile/contracts/ ./`, and
       `WORKDIR /srv` + `COPY mobile/contracts/ /srv/mobile/contracts/` +
       `WORKDIR /app`;
     - a `COPY` in an earlier build stage does not count.
2. No supported `.dockerignore` exclusion pattern matches `P` or one of its
   parent directories.

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
    `runtime_probe/after_final_check.json`.

Condition 33 (instruction words, below) also covers G1.

### G2 — The production image ships every runtime path readiness reads

Pass conditions:

1. On an unchanged copy of the checkout's tracked files, the guard passes
   (exit 0, `Ran 1 test`, not skipped). This also proves that today's
   `Dockerfile` and `.dockerignore` sit entirely inside "Supported syntax".
2. Any path it reported was fixed by adding a `COPY` to the runtime stage of
   `Dockerfile`, not by adding the path to an exclusion list.
3. The existing `tests/test_deployment_manifests.py` tests and the rest of the
   backend suite stay green in fixture mode, including when the guard runs
   inside the full `unittest discover -s tests` run.
4. After release, production `/api/v2/health` reports the merged revision, and
   readiness `runtimeStatus` is still `ready`. The release-tier run checks this
   read-only.
5. **No dead helpers or dead helper tests** in
   `tests/test_deployment_manifests.py`. There is no acceptance case for this;
   the reviewer checks it.
   - Every module-level helper added for this card is called by the guard.
   - Every helper unit test exercises a helper the guard calls, or the guard's
     own trace script.
   - Remove the code that revision 7 makes unnecessary: JSON parsing of
     `COPY`, `shlex` splitting of `COPY`/`WORKDIR`, `posixpath.normpath`
     pattern cleaning (`_normalise_dockerignore_pattern`), and the `**`, `?`,
     character-class and escape branches of `_dockerignore_matches`. Drop the
     `json`/`shlex`/`posixpath` imports if nothing else uses them. (`json`
     stays if the trace payload still needs it.)
   - Remove `test_dockerignore_root_pattern_is_normalized`, or rewrite it to
     assert that the uncleaned pattern is rejected. Helper tests for the
     supported-syntax validator are welcome.

### G3 — Unsupported Dockerfile/.dockerignore syntax fails closed

"Rejected" means: non-zero exit, `Ran 1 test`, `FAILED (failures=1)`, and the
output contains verbatim
`unsupported Dockerfile/.dockerignore syntax: <line>; extend the guard` for the
given `<line>`. "Passes" is as in G1.

20. `.dockerignore` gains `/./mobile/./contracts//`: rejected, line
    `/./mobile/./contracts//`.
21. `.dockerignore` gains `mobile/**/contracts`: rejected, line
    `mobile/**/contracts`.
22. The `COPY mobile/contracts/ …` line becomes
    `COPY ["mobile/contracts/", "./mobile/contracts/"]` (JSON/exec form):
    rejected, line `COPY ["mobile/contracts/", "./mobile/contracts/"]`.
23. `.dockerignore` gains `mobile/[c]ontracts` (bracket class): rejected, line
    `mobile/[c]ontracts`.
24. `.dockerignore` gains `mobile/contract\s` (escape): rejected, line
    `mobile/contract\s`.
25. That `COPY` line becomes `COPY mobile/contracts/ ./mobile/contract\s/`
    (escape): rejected, that line.
26. That `COPY` line becomes the three lines `RUN <<EOF`, the original `COPY`
    line and `EOF` (heredoc): rejected, line `RUN <<EOF`.
27. That `COPY` line becomes `COPY mobile/contracts/ ${APP_DIR}/mobile/contracts/`
    (substitution): rejected, that line.
28. That `COPY` line becomes `ADD mobile/contracts/ ./mobile/contracts/`
    (unsupported instruction): rejected, that line.
29. That `COPY` line becomes `COPY --exclude=*.md mobile/contracts/ ./mobile/contracts/`
    (unsupported flag): rejected, that line.
30. A bare `WORKDIR` line is inserted directly above the unchanged `COPY` line
    (malformed instruction, an internal parse error at `8f3bba1`): rejected,
    line `WORKDIR`.
31. `.dockerignore` gains `#mobile/contracts` (raw leading `#`, a comment):
    passes.
32. `.dockerignore` gains `  #mobile/contracts` (`#` after whitespace, pattern
    text): rejected, line `#mobile/contracts`.
33. That `COPY` line becomes `copy<TAB>mobile/contracts/<TAB>./mobile/contracts/`
    (instruction word in lower case, tab-separated words): passes.

## Not in scope

No app, Watch, web, migration, auth or deploy-script changes, and no change to
`server_v2/readiness.py`. Do not edit the pinned files or `tests/acceptance/`.
Out of scope for the parser, provided the guard rejects them as G3 requires:
JSON/exec `COPY`, bracket classes, escapes, heredocs, substitutions, parser
directives, `**`/`?`/uncleaned `.dockerignore` patterns, unknown instructions
and flags, and any other construct not under "Supported syntax". Known limits
this card does not cover:

- `RUN` steps that delete copied files;
- `.dockerignore` re-inclusion with `!` (validated, then treated as still
  excluded);
- reads that happen while modules import.
