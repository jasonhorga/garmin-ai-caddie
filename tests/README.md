# Offline backend tests

## Layered tests (docs/test-plan.md 3.1-3.3, card C390)

New tests live in size directories; the legacy `tests/test_*.py`, `tests/product/`
and `tests/acceptance/` modules stay where they are and keep their behaviour until K13.

| Directory | Contents | Per-test hard limit | Layer budget | Collected by `discover -s tests -t .` |
| --- | --- | --- | --- | --- |
| `tests/small/` | pure in-memory tests, every class subclasses `tests.support.hermetic.SmallTestCase` | 1 s | 45 s | yes |
| `tests/medium/` | in-process HTTP, `$TMPDIR` files, local subprocesses, threads | 30 s | 135 s | yes |
| `tests/large/` | real ports, Docker, cross-process smoke | 300 s | 360 s | only with `AI_CADDIE_TEST_LAYER=slow` |
| `tests/quarantine/` | unstable tests awaiting a fix (test-plan section 5) | — | — | never; run a module by name |
| `tests/support/` | `FakeClock`, the small-layer guard, layer helpers — not tests | | | |

Each test directory has its own `_bootstrap/`, like the directories below.
`tests/large/__init__.py` and `tests/quarantine/__init__.py` define a package-level
`load_tests`: discovery imports the package, hands it to that hook and does not
recurse, so their modules are not even imported unless selected. The host CD command
`python -m tests.check_isolation discover -s tests -t .` therefore needs no change.

Entry point: `python -m tests.run --layer fast|slow|all` (`fast` is exactly the host
CD discovery; `slow` is `tests/large`; `all` is both). `--changed`/`--shard` come
with C401.

Budgets: the `tests.check_isolation` child runner times every test with an
injectable clock. A small/medium/large test over its hard limit fails with
`BudgetExceeded`; a layer over its total budget makes the run exit non-zero
(`FAILED (over_budget=...)`). The run prints a "Layer budget report" and writes
per-file seconds to `$TMPDIR/test-durations.json` (the system temporary
directory when `TMPDIR` is unset). Legacy modules are timed but never budgeted.

Small-layer guard: while a `SmallTestCase` runs (including `setUpClass` /
`tearDownClass`, and also when run by name with plain `python -m unittest`),
repository code reading the real clock (`time.time`/`monotonic`/`perf_counter`,
`datetime.now`/`utcnow`/`today`, `date.today`), `time.sleep`, disk writes (`open`
in a write mode, `os` create/remove/rename, `tempfile`) and network access
(`socket` connect/sendto, `create_connection`, `getaddrinfo`) raise
`HermeticViolation`. A violation that the code under test catches still fails the
test. Use `tests.support.clock.FakeClock` instead. The guard touches only the
thread running the small test, restores every replaced object afterwards, and
leaves library internals such as logging timestamps alone. Under discovery,
`tests/small/__init__.py` turns the gate red for a test that does not subclass
`SmallTestCase`. Not covered: clock functions captured before the test runs
(e.g. a default argument `now=datetime.now`); inject them instead.

Traceability (docs/test-plan.md section 9): a layered test names the goals it
covers at the start of its docstring, `"""S-11 S-27 [main]: ..."""` (a class
docstring applies to all its tests); a Swift test uses `// goals: I-10 [main]` on
the line above it. `tests/medium/test_traceability_repository.py` (rules
self-checked in `tests/small/test_traceability.py`) fails, listing the IDs,
when a section 2 goal has no test, no or several `[main]` tests, a D3 goal has
fewer than four tests, or a tag names an unknown ID. It also rejects test files
named `test_c<number>` and test code that reads `server_v2`/`ai_caddie`/`mobile`
source text. Quarantined tests do not count; a goal whose main test is quarantined
shows as a skip. Goals still being built are listed in
`tests/support/traceability_allowed_missing.txt`. Delete a goal's line when its
main test lands (a stale entry fails). The list only shrinks:
`tests/medium/test_traceability_allowance.py` fails when it gains an ID that main
did not have.

## Legacy suite

Run a module with `python -m unittest tests.test_course_reference`. For discovery,
use `python -m unittest discover -s tests -t .`. CI wraps this command with
`python -m tests.check_isolation discover -s tests -t . -v`.
`python -m unittest discover -s tests` also installs the offline defaults:
without `-t .`, unittest treats `tests/` as its top level, skips its
`__init__.py`, and imports modules as `test_xxx`. It still visits packages in
sorted order, independently of the `-p` file pattern. `tests/_bootstrap/` sorts
before the test modules and other test packages and imports `tests.offline`
through its canonical package name. Both entry points install the guard once,
before importing tests. Product and acceptance directories have the same
`_bootstrap/` entry point for standalone `discover -s tests/product` and
`discover -s tests/acceptance` (without `-t`). Keep a bootstrap package first in
every test directory's discovery order. The discovery regression automatically
enumerates all directories containing `test*.py` and checks guard installation
before the first test import, so newly added directories are covered too.

`tests.offline` blocks real urllib and requests traffic to Garmin CN/COM hosts,
including subdomains, and blocks Playwright and xvfb login launches. It raises
`GarminNetworkBlocked` (an `URLError`) for urllib/browser calls and
`requests.ConnectionError` for requests. Production callers can use their normal
offline/no-data fallback. Explicit fake transports still work without an opt-in.

API lifespan background work is disabled by default with
`AI_CADDIE_BOOT_BACKGROUND_WORK=0`: stats/prepare-recent warmers, sync recovery and
course-install recovery must not outlive a test and consume another test's mocks.
Startup wiring tests explicitly set it to `1` within a scoped environment patch
and mock `server_v2.main._start_boot_background_work`. Ordinary service processes
start all four tasks by default. Security validation and logging still run during
test lifespans.

For an intentionally selected live integration test, wrap the request in
`with tests.offline.allow_garmin_network():`. This opt-in is nested, restores on
exceptions and does not propagate to background threads. Do not use real player
accounts in tests. The normal suite has no live integration tests.

These default paths use one `.test-cache-*` directory per interpreter in the
system temporary directory, deleted on normal exit. SIGKILL can leave temporary
files there, outside the checkout:

- Release, courseData, course-par, downloaded geometry, exported meshes,
  hazards and batch summaries; prep-cache fingerprints read those same files.
- Garmin raster and overlay raster caches, overlay exports, vector-prep JSON,
  default topo and green-detail PNG caches.
- Decision ledgers/audits, mobile event logs/acks and their event/package locks,
  including member partitions.
- Connector status, sync locks and durable sync jobs; report ledgers, the player
  registry and the default SQLite identity database. These defaults are patched
  before the API module constructs its sync job store. Explicit temporary roots
  and database URL overrides retain their scope; no database URL is set globally.

Explicit temporary roots, per-test path patches and topo environment overrides
retain their scope. `core.data.ROOT` and batch scripts/snapshot anchors still refer
to the source tree. Test-side `batch.ROOT` is redirected because it anchors
relative export paths and `output/.prodgeometry-staging`; `topo_render.ROOT` is
redirected for its default cache path. Production root-resolution tests read the
unmodified domain constants in clean children which never import `tests`.
Only batch's `subprocess.run` / `Popen` calls receive a source-tree `PYTHONPATH`
through an explicit child environment, so exporters remain importable from the
temporary cwd. The parent environment and unrelated children keep their original
`PYTHONPATH` and `AI_CADDIE_TOPO_CACHE_DIR`. Snapshot status suffixes remain
relative so explicit `root / STATUS_FILE` scopes still work; their default root
is disposable. CI rejects any persistent change under repository `data/` or
`output/`, including stores newly introduced by tests. New production defaults
must be redirected here or explicitly patched to a temporary root by their tests.

`test_offline_followups` exercises successful cache/export/ledger writes and
event-store lock creation and compares `git status --ignored` for `data/` and
`output/` before/after. To apply the same check to any modules (or CI discovery):

```sh
python -m tests.check_isolation tests.test_geometry_authority
python -m tests.check_isolation discover -s tests -t . -v
```

The checker preserves unittest's failure status and also fails on new or
changed repository artifacts, including rewritten ignored files whose git status
is unchanged. Failures list only this run's changed paths. Discovery regression
tests run it in a fresh interpreter; CI also uses it around the full backend suite.
The checker detects changes using file metadata, including modification time
(`mtime`). Another process writing `data/` or `output/` in the same checkout can
therefore cause a local false positive. Run isolation checks in a checkout without
other writers, or use a separate clone for concurrent work.

Provider entry points and their offline callers:

| Entry point | Callers exercised by tests |
| --- | --- |
| `inspect_courseview_release.fetch_bytes` / `load_release_pb` / `load_layout_by_date` | `course_reference`, `course_search`, `geometry_sync`; course-reference/search/tees/geometry tests; J4's synthetic 81001 and 82001–82003; mobile course/round/package/background preparation (123, 900001, 31870, 99999 and fixture layouts); C33/C36 product tests |
| `courseview_core._fetch_course_data_bytes` | courseData cache, lightweight prep and mobile package tests; C36 cold-start tests |
| `batch_prodgeometry_course.fetch_bytes` | geometry ZIP downloads and geometry-authority/export tests |
| `garmin_raster.urlopen`, `overlay_prodgeometry_on_raster.fetch_raster` | raster downloads and raster acceptance tests |
| `garmin.fetch` / `garmin_auth` requests calls, via `GarminCnFetchTransport` | connector, bag, sync, session/self-bind and C16a product tests (fake sessions/adapters) |
| `garmin_oauth.UrlLibOAuthClient` | OAuth feasibility tests (fake HTTP client) |
| Playwright `_login_once` / `_reexec_under_xvfb` | login/refresh tests (`FakePage` and fake launch boundary) |

Legacy CourseView tools also use the guarded clients:
`tools/courseview/fetch_courseview.py` (release and IMG download, requests) and
`tools/courseview/overlay_img_on_garmin_raster.py` (raster, urllib). No current
backend tests call these download paths.

Add explicit fixtures at these boundaries when a test needs provider facts;
never depend on internet availability or a previously downloaded cache.
