# Card #432 — Readiness image contract

Every repository path that `server_v2/readiness.py` reads for a check that feeds
`runtimeStatus` must be shipped in the runtime stage of `Dockerfile`. #428 showed
the failure mode (`mobile/contracts/` missing from the image, readiness
`degraded` in production, all tests green).

Touches: `tests/test_deployment_manifests.py`, `Dockerfile`

Acceptance tests: `tests/acceptance/test_card_432_readiness_image_paths.py`

## Interface

Add one test method, exactly this id:

```
tests.test_deployment_manifests.DeploymentManifestTests.test_readiness_runtime_paths_are_copied_into_image
```

The acceptance tests run that id with `python -m unittest <id>` in a subprocess
(`AI_CADDIE_DATA_MODE=fixture`, no `AI_CADDIE_PRIVATE_ROOT`). They run it once on
the checkout and once each on a temporary full copy of the checkout with one
defect. So the guard must:

- find the repository root from the test file or the working directory (both are
  the copy's root in the mutation runs). Do not hard-code an absolute path;
- read `Dockerfile` and `.dockerignore` from that root;
- import `server_v2.readiness` normally (the copy's `server_v2` is first on
  `sys.path`);
- be a single test that does not skip. When it fails, use an assertion failure
  (unittest reports `FAILED (failures=1)`), not an error, and name every
  uncovered path, repository-relative and POSIX (for example
  `mobile/contracts/live_round_event.schema.json`).

How it collects paths is up to the implementation. It must come from readiness
itself, not from a hard-coded list in the test. Either of these works:

- run `build_readiness_response()` with the packaging-label checks excluded and
  record the repository files it opens (for example with `sys.addaudithook` on
  `open`); or
- inspect readiness's module-level path constants plus the paths its runtime
  checks use.

Keep the existing `LIVE_ROUND_EVENT_CONTRACT = Path("mobile/contracts/live_round_event.schema.json")`
assignment as a single module-level line in `server_v2/readiness.py`. One
acceptance case rewrites that line in a copy. Also keep the explicit
`COPY mobile/contracts/ ./mobile/contracts/` line in `Dockerfile`, and do not
widen it to `COPY mobile/ …`.

## Scope rules for the guard

- **In scope:** paths read by checks whose label is not in
  `readiness.PACKAGING_LABELS` (today: service, mobile, secret_handling, history,
  sync, course_reference, mobile_package, mobile_events, media_context, reports).
- **Out of scope (packaging/evidence):** paths used only by checks in
  `PACKAGING_LABELS` (`native_mobile`, `external_release`, `roadmap_completion`,
  `operations`, `private_snapshot_acceptance`), such as `mobile/ios/**`,
  `docs/**`, `render.yaml` and `web_v2/vercel.json`. These must not fail the
  guard.
- **Out of scope (private runtime root):** `data`, `.garmin_tokens`, `output`,
  `logs`, `backups` and `clubs.json`. `ops/start_api.sh` symlinks these into
  `AI_CADDIE_PRIVATE_ROOT`, so they are not image content. Image-built
  environments (`.venv`, `node_modules`) are also out of scope.
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

Pass conditions:

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
6. Packaging/evidence paths and private-root paths never fail it.

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

No app, Watch, web, migration, auth or deploy-script changes. Do not edit the
pinned files.
