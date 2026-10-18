# Card #432 — Readiness image contract

Every repository path that `server_v2/readiness.py` reads for a check that feeds
`runtimeStatus` must be in the production API image. #428 showed the failure
mode (`mobile/contracts/` missing from the image, readiness `degraded` in
production, all tests green).

Touches: `ops/readiness_runtime_paths.py`, `.github/workflows/ci.yml`, `tests/test_deployment_manifests.py`, `tests/test_readiness_runtime_paths.py`, `Dockerfile` (only if CI verification reports a missing path), `tests/acceptance/test_card_432_readiness_image_paths.py`, `.agent/contracts/card-432.md`

Acceptance tests: `tests/acceptance/test_card_432_readiness_image_paths.py` (24 tests)

## Revision 9: acceptance hardened after the adversarial gate

The gate's adversarial check failed on head `19000fc`. The 19 revision-8 tests
were too weak: an implementation could pass them while breaking the interface
below. Revision 9 keeps the design and the interface, and makes the tests
hold the implementation to them:

- **Probe names change on every run.** Each probe lives under a fresh
  `probe_<random>/` directory. One probed path appears only inside a data file
  that readiness reads, never in its source. Matching names or scanning source
  can no longer pass.
- **Labels are compared exactly.** A probe read by only one check must carry
  exactly that check's label.
- **More collector behaviour is tested:** every listed open/probe/list call;
  every private-root name, plus `build_environment` and `bytecode`;
  `packagingLabels` read from readiness; the forced fixture environment; root
  selection; stdout output; and three fail-closed cases.
- **More verifier behaviour is tested:** every problem is reported, in path
  order; both kind mismatches; more invalid manifests; validation finishes
  before any image path is checked.
- **CI is checked structurally.** Verification must run in the image built in
  that job, with the image's own script, nothing mounted over `/app`, the
  manifest that collect wrote, and no shell construct that lets a failure pass.
- **Codex's repository tests are required.** `tests.test_readiness_runtime_paths`
  must exist and pass.

From reading the code, head `19000fc` already meets every revision-9 condition.
No implementation change is expected. If a new case fails, fix
`ops/readiness_runtime_paths.py` or `ci.yml`, not the tests. Codex must not
touch `tests/acceptance/`. All 24 tests fail on `main`, because the collector,
its repository tests and the CI steps don't exist there. I could not run Python
in the contract sandbox, so these results come from reading the code, not from
running it.

## Interface

### Script

`ops/readiness_runtime_paths.py`. `ops/` is copied into the image
(`COPY ops/ ./ops/`), so the verifier is available inside the image.

- Module level imports the **standard library only**. It never imports
  `server_v2` or `ai_caddie` in its own process.
- `def main(argv: list[str] | None = None) -> int`. It returns the exit code
  and does not call `sys.exit` itself. The file ends with
  `if __name__ == "__main__": raise SystemExit(main())`. Loading it with
  `runpy.run_path(..., run_name="other")` must not run anything.
- Exit codes: `0` on success; non-zero on any failure. argparse usage errors
  may return `2`.
- Status and error text go to stderr. When `--output` is omitted or `-`, the
  manifest JSON is the **only** thing on stdout (`json.loads(stdout)` must
  succeed).

### `collect`

```
python ops/readiness_runtime_paths.py collect [--root DIR] [--output FILE|-]
```

- `--root` is the tree to collect. Without it, the script's own checkout
  (`Path(__file__).resolve().parents[1]`) is collected, not the working
  directory. With it, that tree is collected, whichever checkout the script
  lives in. The working directory does not matter.
- It **always** runs `build_readiness_response()` in a **fresh child
  interpreter**, even when `main()` is called inside a process that has already
  imported and run readiness (warm `lru_cache`). The child is started like this:
  - `subprocess.run([sys.executable, "-c", <script>], cwd=root, …)`;
  - the environment is the parent's, with `root` first on `PYTHONPATH`, so the
    child imports readiness from `root` even under `PYTHONSAFEPATH=1` with
    another checkout on the caller's `PYTHONPATH`;
  - `AI_CADDIE_DATA_MODE=fixture` is forced, whatever the caller set;
  - `AI_CADDIE_PRIVATE_ROOT` is removed.

  The collector never reads or writes private data.
- In the child: import `server_v2.readiness` first, then install the recorders,
  then call `build_readiness_response()` once. Reads made while modules import
  do not count. Record every path the call
  - **opens**: builtin `open`, `os.open`, and `Path.open`/`read_text`/`read_bytes`;
  - **probes**: `Path.exists`/`is_file`/`is_dir`/`is_symlink`/`stat`,
    `os.stat`, `os.lstat`, `os.access`, and `os.path.exists`/`isfile`/`isdir`/`islink`;
  - **lists**: `Path.iterdir`/`glob`/`rglob`, `os.listdir`, `os.scandir`,
    `os.walk` and `glob.glob`. Record the listed directory.

  This includes paths that readiness computes from data it has read.
- **Attribution** works by wrapping `readiness._check`:
  - paths recorded since the previous `_check` call go to the label of the
    next `_check` call;
  - paths still pending when `build_readiness_response()` returns get the label
    `<after-final-check>`, which counts as runtime.

  A path keeps **every** label it was recorded under, and no others.
- **Normalisation.** Paths are made relative to the resolved root, in POSIX
  form. Drop the root itself and paths outside it. No manifest path is empty,
  `.`, absolute, contains a `..` segment, or contains `\`.
- **Classification.** Each path goes into exactly one section, decided in this
  order:
  1. `excluded`, with a `reason`, whether or not the path exists, when the path
     or one of its parents is:
     - `private_root`: the first segment is exactly one of `data`,
       `.garmin_tokens`, `output`, `logs`, `backups`, `clubs.json` (these are
       linked to `AI_CADDIE_PRIVATE_ROOT` by `ops/start_api.sh`). This reason
       wins over the other two. `data_x/…` and `x/data/…` are not excluded;
     - `build_environment`: any segment is `.venv` or `node_modules`;
     - `bytecode`: any segment is `__pycache__`, or the path ends in `.pyc`.

     There are no other path-based exclusions: no `ops`, `docs`, `mobile/ios`
     and so on.
  2. Otherwise, when at least one label is **not** in
     `readiness.PACKAGING_LABELS`, it is a runtime path. The set is read from
     readiness in the child, as it is in that tree, never from a list kept in
     the collector. A path used by both a runtime and a packaging check is
     runtime. It goes into:
     - `runtime`, if it exists in the tree after the readiness call;
     - `absent`, if it does not exist. Absent paths are reported, not
       required.
  3. Otherwise it goes into `packaging`. Packaging paths include `render.yaml`,
     `web_v2/vercel.json`, `docs/**` and `mobile/ios/**`.
- **Manifest** (UTF-8 JSON). Every section is sorted by `path` (Python string
  order). Every `runtime`, `packaging` and `absent` entry has a non-empty,
  sorted `labels` list.

  ```json
  {
    "schema": "ai-caddie-readiness-runtime-paths-v1",
    "packagingLabels": ["external_release", "native_mobile", "operations", "private_snapshot_acceptance", "roadmap_completion"],
    "runtime":   [{"path": "mobile/contracts/live_round_event.schema.json", "kind": "file", "sha256": "<hex>", "labels": ["mobile_events"]},
                  {"path": "some/dir", "kind": "dir", "labels": ["…"]}],
    "packaging": [{"path": "render.yaml", "labels": ["operations"]}],
    "absent":    [{"path": "…", "labels": ["…"]}],
    "excluded":  [{"path": "data/…", "reason": "private_root"}]
  }
  ```

  - `packagingLabels` is `sorted(readiness.PACKAGING_LABELS)` as read in the
    child.
  - `kind` is `file` or `dir`.
  - `sha256` is required for files: 64 lowercase hex characters, the SHA-256
    of the file's bytes after readiness returns.
- **Failure.** The collection fails when the child:
  - exits non-zero, **even if it printed a result first** (for example,
    readiness registers an `atexit` handler that exits 7);
  - times out;
  - exits 0 without printing a result.

  A failed collection exits non-zero, prints the tail of the child's stderr on
  stderr, and writes no manifest. Do not create, truncate or overwrite the
  `--output` file before success: an existing file keeps its content.
- The collector reads neither `Dockerfile` nor `.dockerignore`. Deleting both
  leaves the manifest unchanged.

### `verify`

```
python ops/readiness_runtime_paths.py verify --manifest FILE|- --image-root DIR
```

- Reads the manifest from a file, or from stdin when given `-`.
- **Validates first, completely.** Each of these is a failure, reported with a
  line containing `invalid manifest`, never a traceback:
  - a manifest file that cannot be read;
  - JSON that does not parse, or a top level that is not an object;
  - a `schema` other than the one above;
  - a `runtime` that is missing, not a list, or empty;
  - an entry without `path`, or with `kind` missing or not `file`/`dir`;
  - a `file` without a `sha256` of 64 lowercase hex characters.

  A runtime path that is absolute, contains a `..` segment or `\`, or is
  empty or `.` is reported as `invalid manifest path: <path>`. In every one of
  these cases, no image path is checked, even for entries that come before the
  bad one. No `missing from image` or `differs in image` line may appear.
- Checks **only** `runtime` entries. It ignores `packaging`, `absent` and
  `excluded`. For each entry, let `P = <image-root>/<path>`:
  - `kind: file`: `P` must be a regular file (a directory is
    `missing from image: <path>`), and its SHA-256 must equal `sha256`, or it
    prints `differs in image: <path>`;
  - `kind: dir`: `P` must be a directory (a file is
    `missing from image: <path>`).
- It checks every entry and prints every problem, one line each, sorted by
  path, then exits non-zero. With no problems it exits 0.

### Repository tests (Codex)

`tests/test_readiness_runtime_paths.py` holds focused tests of the script.
`python -m unittest -v tests.test_readiness_runtime_paths` must run at least
one test and pass offline in fixture mode. It stays green under
`unittest discover -s tests`.

## CI: verify the built image

In `.github/workflows/ci.yml`, job `docker`, keep the job names `backend`,
`frontend` and `docker`, and keep the existing steps. The `docker` job has no
`if:` and no `continue-on-error`. After the `docker build -f Dockerfile … -t
<tag> …` step:

1. **Collect** the manifest from this PR's checkout with
   `ops/readiness_runtime_paths.py collect`. The command line starts with
   `docker run`, `docker exec`, `uv run` or a Python interpreter. It writes the
   manifest to a file with `--output FILE` (or `> FILE`). The file name is not
   a tracked file in the repository.
2. **Verify** that file inside the built image. The command line:
   - starts with `docker run`;
   - names the `<tag>` the build step used;
   - mounts nothing at `/`, at `/app` or under `/app/` (`-v`, `--volume`,
     `--mount`), and has no `--volumes-from`;
   - runs the image's copy, `/app/ops/readiness_runtime_paths.py verify`, with
     `--image-root /app`;
   - contains the collect output's file name (for example
     `--manifest - … < "$RUNNER_TEMP/<name>"`).

   The verify step comes after the build step, and not before the collect step.

The collect and verify steps:

- have no `if:` and no `continue-on-error`;
- run under bash: no `shell:`, or `shell: bash`;
- contain no `set +e`, `set +o errexit`, `set +o pipefail` or `trap`;
- run the script as one plain command per logical line (backslash
  continuations joined):
  - none of `|`, `&`, `;`, backticks or `$(`;
  - the line does not begin with `!`, `if`, `elif`, `while` or `until`.

A verification failure must fail the `docker` check.

Head `19000fc` already does all of this:
- collect: `docker run --rm -v "$PWD:/src" -v "$RUNNER_TEMP:/evidence" -w /src garmin-ai-caddie-api:latest /app/.venv/bin/python ops/readiness_runtime_paths.py collect --root /src --output /evidence/readiness-runtime-paths.json`;
- verify: `docker run --rm -i garmin-ai-caddie-api:latest /app/.venv/bin/python /app/ops/readiness_runtime_paths.py verify --manifest - --image-root /app < "$RUNNER_TEMP/readiness-runtime-paths.json"`.

The existing `test -s /app/mobile/contracts/…` smoke lines may stay. The test
`test_api_image_packages_and_smokes_canonical_contracts` still asserts them.

## Dockerfile

From reading the code: every runtime path is already shipped. The `docker`
check is green on `19000fc`, and the acceptance layout `IMAGE_LAYOUT` mirrors
today's runtime-stage `COPY` lines.

If the CI verification reports a missing path, add the missing
`COPY <dir>/ ./<dir>/` to the runtime stage in this PR. Do not add the path to
an exclusion. Say in the PR body which path it was, so that Claude can add it
to `IMAGE_LAYOUT`.

### G1 — The collector reports the paths readiness reads, attributed to runtime or packaging

Every collection in these tests is also checked for the manifest invariants:
- exit 0, and the schema above;
- `packagingLabels` sorted;
- every section sorted by path, and every path normalised and in exactly one
  section;
- every labelled entry has non-empty, sorted labels;
- runtime `kind` is `file`/`dir`, and every runtime file has a 64-hex `sha256`;
- every excluded entry has one of the three reasons.

1. On an unchanged copy, `runtime` holds
   `mobile/contracts/live_round_event.schema.json`:
   - with `kind: file`, the correct `sha256` and the label `mobile_events`;
   - every runtime entry has at least one non-packaging label and a correct
     `sha256` for files;
   - no runtime path is under a private root or is bytecode;
   - `packagingLabels` contains `operations`, `external_release` and
     `native_mobile`, and not `mobile_events`.
2. On an unchanged copy:
   - `render.yaml`, `web_v2/vercel.json` and `docs/security/secrets.md` are in
     `packaging` with `operations`;
   - `mobile/ios/project.yml` is in `packaging` with `native_mobile`;
   - `backups/latest.json` and `logs/private_trial_smoke_latest.json` are
     `excluded` with `private_root`;
   - no runtime path is under `docs/` or `mobile/ios/`.
3. When `_contract_event_kinds()` first runs each call listed under
   opens/probes/lists, on its own probe, each path is in `runtime` with labels
   exactly `["mobile_events"]`:
   - files have `kind: file` and the correct `sha256`;
   - listed or `is_dir`/`isdir`-probed directories have `kind: dir`.

   So is a file whose name readiness reads from a pointer file.
4. When `LIVE_ROUND_EVENT_CONTRACT` points at
   `relocated_contracts/live_round_event.schema.json`, that path is in
   `runtime` with the label `mobile_events`.
5. A file read only by `_external_release_evidence()` is in `packaging` with
   labels exactly `["external_release"]`, and not in `runtime`.
6. When `_contract_event_kinds()` reads `ops/smoke_private_trial.sh` (which the
   `operations` check also reads), the file is in `runtime`, and its labels
   include both `mobile_events` and `operations`.
7. Runtime probes are `excluded` with these reasons, even though none of the
   files exist:
   - `private_root`: `data/…`, `.garmin_tokens/…`, `output/…`, `logs/…`,
     `clubs.json` and `backups/…/__pycache__/x.pyc`;
   - `build_environment`: `…/node_modules/…` and `…/.venv/…`;
   - `bytecode`: `…/__pycache__/…` and `….pyc`.

   Read files at `data_<probe>/…` and `<probe>/data/…` are in `runtime`.
8. A read inserted directly above `    runtime_checks = [` is in `runtime` with
   labels exactly `["<after-final-check>"]`.
9. A runtime `Path(…/never_created.json).exists()` lands in `absent` with labels
   exactly `["mobile_events"]`, and not in `runtime`.
10. Calling `main(["collect", …])` through `runpy`, in an interpreter that has
    already run readiness, still reports in `runtime` a file read by an
    `lru_cache` helper.
11. With `Dockerfile` and `.dockerignore` deleted, it collects the same
    runtime paths as an unchanged copy, and neither file appears in any
    section. This test also covers G4.
12. Each of these exits non-zero and leaves `--output` alone:
    - readiness raises at import (`card432 readiness boom`, which must appear
      in the output). The output file is not created;
    - the child exits 0 without a result. An existing output file keeps its
      content;
    - the child exits 7 from `atexit` after printing its result. An existing
      output file keeps its content.
13. With `PACKAGING_LABELS` changed in the copy to add `mobile_events` and drop
    `operations`:
    - `packagingLabels` follows the change;
    - a file read only by `_contract_event_kinds()` is in `packaging` with
      `["mobile_events"]`;
    - `render.yaml` is in `runtime` with `operations` and the correct `sha256`.
14. Called with `AI_CADDIE_DATA_MODE=local`, `AI_CADDIE_PRIVATE_ROOT` set,
    `PYTHONSAFEPATH=1` and the real checkout first on `PYTHONPATH`:
    - the child sees `AI_CADDIE_DATA_MODE=fixture` and no private root, and
      runs the copy's readiness (probes in `absent` with `["mobile_events"]`);
    - nothing is written into the private root.
15. Root selection:
    - the copy's script, with no `--root` and `--output -`, collects the copy;
    - the checkout's script with `--root <copy>` and no `--output` also
      collects the copy;
    - both print only the manifest on stdout.

### G2 — The verifier proves every runtime path is in an image root

16. Collect, then verify against an image root assembled from today's
    runtime-stage layout (`IMAGE_LAYOUT`: `pyproject.toml`, `uv.lock`,
    `package.json`, `package-lock.json`, `ai_caddie/`, `contracts/canonical/`,
    `mobile/contracts/`, `server_v2/`, `ops/`, `alembic.ini`, `migrations/`).
    It exits 0, with no `missing from image` and no `differs in image`
    message. This test also covers G3.
17. With `mobile/contracts/` removed from that root, it exits non-zero and
    prints `missing from image: mobile/contracts/live_round_event.schema.json`.
18. With that file's content changed in the root, it exits non-zero and prints
    `differs in image: mobile/contracts/live_round_event.schema.json`.
19. A hand-made manifest, read from stdin (`--manifest -`), whose `packaging`,
    `absent` and `excluded` paths are missing from the root still passes.
    Each of these added runtime entries fails with
    `missing from image: <path>`:
    - a `dir` entry that is a file in the root;
    - a `file` entry that is a directory in the root.
20. Five runtime entries are given in reverse order: one fine, one dir-is-file,
    one file-is-dir, one differing and one missing. The output has exactly the
    four problem lines, sorted by path, and the exit code is non-zero.
21. Each case in the `verify` validation list fails non-zero, with
    `invalid manifest`, no traceback, and no `missing from image` or
    `differs in image` line. That includes an unreadable manifest file, a
    non-object top level, a non-list `runtime`, a missing `kind`, an unknown
    `kind` and a non-hex `sha256`. Each case puts a valid entry missing from
    the image before the bad one. Bad paths also print
    `invalid manifest path: <path>`.
22. `python -m unittest -v tests.test_readiness_runtime_paths` exits 0 and runs
    at least one test. This test also covers G1.

### G3 — CI runs the verifier against the actual built API image

23. `.github/workflows/ci.yml` meets every rule in "CI: verify the built
    image", checked structurally. Case 16 runs the same collect → verify
    sequence through the CLI.

- The `docker` check is green on the PR head. The reviewer reads the step log
  to confirm that the verify step ran against `/app` and listed the runtime
  paths it checked. There is no acceptance case for this check.
- After release, production `/api/v2/health` reports the merged revision, and
  readiness `runtimeStatus` is still `ready`. The release-tier run checks this
  read-only.

### G4 — The superseded static parser and its tests are removed

24. On an unchanged copy, `python -m unittest -v tests.test_deployment_manifests`
    exits 0 and runs at least one test. Its output names none of these tests:
    - `test_readiness_runtime_paths_are_copied_into_image`;
    - `test_dockerignore_rejects_patterns_outside_the_supported_syntax`;
    - `test_dockerfile_copies_reject_unsupported_instructions_per_line`;
    - `test_docker_instruction_word_accepts_tab_separated_from_and_copy`.

    The file no longer mentions these names or the string `dockerignore`:
    `UNSUPPORTED_SYNTAX`, `_docker_instruction_word`, `_dockerignore_matches`,
    `_docker_instructions`, `_plain_words`, `_docker_destination`,
    `_dockerfile_copies`, `_dockerignore_patterns`.

    The collector source does not mention `dockerignore`. No test file outside
    `tests/acceptance/` contains `unsupported Dockerfile/.dockerignore syntax`.

The reviewer also checks, without an acceptance case, that these are gone:

- the now-unused module-level regexes `_PLAIN_WORD`, `_IMAGE_WORD`,
  `_DOCKERIGNORE_SEGMENT`, `_PARSER_DIRECTIVE` and `_OPAQUE_INSTRUCTIONS`;
- the imports that only they or the old guard used.

`json` stays, because the Vercel test uses it. All other existing tests in
`tests/test_deployment_manifests.py` stay unchanged and green.

## Readiness lines the tests rely on

The acceptance tests rewrite these lines in a copy, so they must stay as they
are. Do not edit `server_v2/readiness.py`:

- the one-line module constant `LIVE_ROUND_EVENT_CONTRACT = Path("mobile/contracts/live_round_event.schema.json")`;
- the one-line, argument-free signatures `def _contract_event_kinds() -> …:`
  and `def _external_release_evidence() -> …:`;
- the module-level `from pathlib import Path`, and the module-level
  `PACKAGING_LABELS`, read at call time;
- the line `    runtime_checks = [` after the final `_check` call.

## Not in scope

No app, Watch, web, migration, auth or deploy-script changes, and no change to
`server_v2/readiness.py`. Do not edit the pinned files (`ops/agenthub_deploy.py`,
`ops/build_sync_image.sh`, `ops/complete_homeserver_api_deploy.sh`, the
TestFlight files) or `tests/acceptance/`. `Dockerfile.sync` is unchanged.

Known limits:

- collection runs in fixture mode only. Production (`local_or_fixture` with a
  private root) can take code paths that fixture data never reaches;
- reads during module import are not collected, and nor are reads made by
  child processes that readiness starts;
- a `RUN` step that deletes or rewrites a copied file is caught only if the
  file is in the manifest (then `differs`/`missing`).
