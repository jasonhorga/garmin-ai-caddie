# Offline backend tests

Run a module with `python -m unittest tests.test_course_reference`. For discovery,
use `python -m unittest discover -s tests -t .` (the CI command). The explicit top
level makes unittest import `tests/__init__.py` before loading test modules;
`discover -s tests` alone does not guarantee that package initialization.

`tests.offline` blocks real urllib and requests traffic to Garmin CN/COM hosts,
including subdomains, and blocks Playwright and xvfb login launches. It raises
`GarminNetworkBlocked` (an `URLError`) for urllib/browser calls and
`requests.ConnectionError` for requests. Production callers can use their normal
offline/no-data fallback. Explicit fake transports still work without an opt-in.

For an intentionally selected live integration test, wrap the request in
`with tests.offline.allow_garmin_network():`. This opt-in is nested, restores on
exceptions and does not propagate to background threads. Do not use real player
accounts in tests. The normal suite has no live integration tests.

Default release, courseData, course-par, geometry download/export and raster caches use a
unique `.test-cache-*` temporary directory per interpreter, deleted at exit.
Keeping it below the repository preserves geometry exports' relative path
contract; the real `ROOT/data/courseview` cache is neither a source nor a write
target. Explicit temporary roots and per-test path patches retain their scope.
The prep-cache fingerprint reads the same disposable CourseView directory.
Fixtures and the production `ROOT` constants are unchanged.

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
