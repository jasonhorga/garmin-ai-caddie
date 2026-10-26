# Offline backend tests

Run a module with `python -m unittest tests.test_course_reference`. For discovery,
use `python -m unittest discover -s tests -t .` (the CI command).
`python -m unittest discover -s tests` also installs the offline defaults:
without `-t .`, unittest treats `tests/` as its top level, skips its
`__init__.py`, and imports modules as `test_xxx`. It still visits packages in
sorted order, independently of the `-p` file pattern. `tests/_bootstrap/` sorts
before the test modules and other test packages and imports `tests.offline`
through its canonical package name. Both entry points install the guard once,
before importing tests. Keep that bootstrap package first in discovery order.

`tests.offline` blocks real urllib and requests traffic to Garmin CN/COM hosts,
including subdomains, and blocks Playwright and xvfb login launches. It raises
`GarminNetworkBlocked` (an `URLError`) for urllib/browser calls and
`requests.ConnectionError` for requests. Production callers can use their normal
offline/no-data fallback. Explicit fake transports still work without an opt-in.

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
  topo and green-detail PNG caches (`AI_CADDIE_TOPO_CACHE_DIR`).
- Decision ledgers/audits, mobile event logs/acks and their event/package locks,
  including member partitions.

Explicit temporary roots, per-test path patches and topo environment overrides
retain their scope. Fixture/source roots stay intact. Only the batch exporter’s
test-side `ROOT` is redirected too, because it anchors relative export paths and
`output/.prodgeometry-staging`. Its scripts/snapshot anchors still refer to the
source tree; test `PYTHONPATH` lets exporter children import from that tree while
running in the temporary directory. Other application stores are outside this
list; these defaults do not promise to redirect every filesystem write.

`test_offline_followups` exercises successful cache/export/ledger writes and
event-store lock creation and compares `git status --ignored` for `data/` and
`output/` before/after. To apply the same check to any modules (or CI discovery):

```sh
python -m tests.check_isolation tests.test_geometry_authority
python -m tests.check_isolation discover -s tests -t . -v
```

The checker preserves unittest's failure status and also fails on new or
changed repository artifact status, including ignored files. Discovery regression
tests run it in a fresh interpreter; no CI workflow change is needed.

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
