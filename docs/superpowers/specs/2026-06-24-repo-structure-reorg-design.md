# Repo structure reorg — ai_caddie/ domain subpackages + root-script relocation

- **Date:** 2026-06-24
- **Branch model:** per-task `superpowers/**` → PR → `integration/v2`
- **Status:** design approved (staged). Phase 1 first; Phase 2 separate PR.
- **Independent review:** codex (gpt-5.5) reviewed the original single-PR plan → **VERDICT: RECONSIDER**, recommended staging. Findings folded in (see Appendix). This design adopts staging and the concrete fixes codex surfaced.

## 1. Motivation

The repo root holds **11 loose scripts** (9 `.py` + 2 `.js`) — the first thing anyone sees, and the main "messy" signal. `ai_caddie/` is a flat package of ~40 modules. Goal: a navigable tree where the root holds only config files + directories, and the engine package is grouped by domain. Behaviour is unchanged — this is a pure move + import-rewrite refactor.

## 2. Target structure (end state — both phases)

| subpackage | modules |
|---|---|
| `ai_caddie/garmin/` | **fetch · garmin_auth · garmin_playwright_login** (ex-root) |
| `ai_caddie/geometry/` | **inspect_courseview_release · batch_prodgeometry_course · measure_prodgeometry_distances · export_prodgeometry_hazards · overlay_prodgeometry_on_raster · decode_courseview_geometry.js · fetch_courseview_geometry_key.js** (ex-root) + geometry_evidence · geometry_sync · hole_render · elevation · shot_projection |
| `ai_caddie/courses/` | course_prep · course_reference · course_search · prep_cache · prep_tips |
| `ai_caddie/history/` | history · history_drilldown · history_round_detail · history_stats · stats_cache · mobile_stats |
| `ai_caddie/caddie/` | decision · decision_api · caddie_context · mobile_live · mobile_reconciliation · issue_taxonomy · analysis · club_bag |
| `ai_caddie/reports/` | reports · report_labels_zh · annotations |
| `ai_caddie/rounds/` | players · round_ingest · round_shot_map |
| `ai_caddie/llm/` | llm · llm_providers · vision_context · weather_context |
| `ai_caddie/core/` | config · data · fixtures · media |

- **Stays at `ai_caddie/` root:** `pipeline.py` (preserves `python -m ai_caddie.pipeline`, used by `ops/auto_sync.sh` + homeserver `~/aicaddie-sync.sh`), `__init__.py`.
- **Unchanged:** `ai_caddie/connectors/`, `ai_caddie/scrapers/` (already tidy subpackages).
- **`ai_caddie_web.py`** (legacy v1 web UI, root) → `tools/legacy/` (only `tests/test_decision_layer.py` imports `INDEX_HTML`; not runtime).
- **`__init__.py` files stay empty** (no re-exports) — required to avoid the domain import cycles codex found (see Appendix MED-cycles).

## 3. Staging (codex: not one big PR)

- **Phase 1 (this PR):** relocate the 11 root scripts into `ai_caddie/garmin/` + `ai_caddie/geometry/`; `ai_caddie_web.py` → `tools/legacy/`. Cleans the root. Contained importer set (~11 sites). Full Docker + prodgeometry smoke.
- **Phase 2 (separate PR):** subpackage the remaining 31 flat `ai_caddie/` modules (courses/history/caddie/reports/rounds/llm/core) via the full codemod (3 import forms + ~20 `patch()` string targets). `__init__` stays empty.

Rationale: Phase 1 delivers the visible win at contained risk and proves the move mechanics (ROOT/subprocess/Docker) on the geometry chain — the riskiest part — before the high-churn codemod of Phase 2.

## 4. Phase 1 — detailed scope

### 4.1 Moves (git mv)
- `ai_caddie/garmin/`: `fetch.py`, `garmin_auth.py`, `garmin_playwright_login.py`
- `ai_caddie/geometry/`: `inspect_courseview_release.py`, `batch_prodgeometry_course.py`, `measure_prodgeometry_distances.py`, `export_prodgeometry_hazards.py`, `overlay_prodgeometry_on_raster.py`, `decode_courseview_geometry.js`, `fetch_courseview_geometry_key.js`
- `tools/legacy/`: `ai_caddie_web.py`
- Add empty `__init__.py` to `ai_caddie/garmin/`, `ai_caddie/geometry/`, `tools/`, `tools/legacy/`.

### 4.2 Import rewrites — all three forms (codex HIGH)
A codemod must handle every form, not just `from X import`:
- `import fetch` / `import fetch as m` → `from ai_caddie.garmin import fetch` / `... as m`
- `from fetch import Y` → `from ai_caddie.garmin.fetch import Y`
- (`from ai_caddie import fetch` form does not occur for the root modules, but the codemod handles it generically for Phase 2.)
- Mapping: `fetch`/`garmin_auth`/`garmin_playwright_login` → `ai_caddie.garmin.*`; `inspect_courseview_release`/`batch_prodgeometry_course`/`measure_prodgeometry_distances`/`export_prodgeometry_hazards`/`overlay_prodgeometry_on_raster` → `ai_caddie.geometry.*`; `ai_caddie_web` → `tools.legacy.ai_caddie_web`.

Known importer sites (grep `^(import|from) <mod>`): `ai_caddie/connectors/garmin_cn.py`, `ai_caddie/geometry_sync.py`, `ai_caddie/course_search.py`, `ai_caddie/course_reference.py`, `ai_caddie/hole_render.py`, `ai_caddie/analysis.py`; tests: `test_garmin_playwright_login.py`, `test_garmin_cn_connector.py`, `test_decision_layer.py`, `test_courseview_par.py`, `test_ai_caddie.py`. (Plan re-greps to confirm none missed.)

### 4.3 String targets (codex MED) — must be codemodded, not git-mv'd
Grep and rewrite: `patch("fetch`, `patch('fetch`, and same for `garmin_auth`, `garmin_playwright_login`, `inspect_courseview_release`, `batch_prodgeometry_course`, `measure_prodgeometry_distances`, `export_prodgeometry_hazards`, `overlay_prodgeometry_on_raster`; plus any `importlib.import_module("...")` and `Path("...py")` string referencing a moved file. (Phase 2 owns the ~20 enumerated `patch("ai_caddie.*")` targets.)

### 4.4 Path / subprocess fixes (codex HIGH — exact lines)
- Each moved script computes repo root as `ROOT = Path(__file__).parent` for `data/`,`output/` — now wrong (points at the subpackage). Change to `ROOT = Path(__file__).resolve().parents[2]` (`ai_caddie/<pkg>/x.py` → repo root; correct locally and in Docker `/app`). Files: `fetch.py:21`, `garmin_auth.py:23`, `garmin_playwright_login.py:39`, `inspect_courseview_release.py:14`, `measure_prodgeometry_distances.py:18`, `export_prodgeometry_hazards.py:18`, `overlay_prodgeometry_on_raster.py:25`, `batch_prodgeometry_course.py:27`.
- `batch_prodgeometry_course.py`: add `SCRIPT_DIR = Path(__file__).resolve().parent`; the 5 bare-name subprocess invocations (`:132,153,167,178,190` — `node *.js`, `sys.executable *.py`) → `str(SCRIPT_DIR / "<name>")`. Removes the `cwd=ROOT` dependency entirely.

### 4.5 Dockerfile
- Drop `COPY *.py ./` and `COPY *.js ./` (lines 30–31). The relocated scripts now arrive via the existing `COPY ai_caddie/ ./ai_caddie/`. `ai_caddie_web.py` leaves the image (only test-referenced; not runtime). Confirm the 11 root scripts were the *only* consumers of the glob.

### 4.6 package.json (codex LOW)
- Update script paths (`:5,7,8`) that point at root `*.js` → `ai_caddie/geometry/*.js`.

### 4.7 README
- Replace the "必须留根" section with the new layout description.

## 5. Verification gates (Phase 1, pre-merge)
1. `uv run python -m unittest discover -s tests` green — Tokyo pre-check + CI (catches import + `patch()` breakage).
2. `docker compose build api` **and** `docker build -f Dockerfile.sync -t aicaddie-sync:verify .` succeed (catches COPY/runtime-import issues).
3. **prodgeometry single-hole smoke** on the homeserver — exercises the `node` + `sys.executable` subprocess chain + `ROOT`/`SCRIPT_DIR` fixes (unittest will NOT catch this).
4. `python -m ai_caddie.pipeline --help` imports clean.
5. CI backend + frontend green.

## 6. Out of scope / rollback
- **Out:** historical docs (`docs/superpowers/{specs,plans,reviews}` — point-in-time records, left as-is); `server_v2/`, `mobile/`, `web_v2/`; `connectors/`, `scrapers/`; all Phase 2 modules.
- **Rollback:** pure file moves + import rewrites → a single `git revert` of the PR restores the prior layout. The codemod script is committed in the PR for reproducibility/re-run.

## Appendix — codex review findings (folded in)
- **HIGH** third import form `from ai_caddie import X` (Phase 2) + the runtime sites using it → codemod must cover all forms; keep `__init__` empty (no re-exports).
- **HIGH** `batch_prodgeometry_course` ROOT-vs-script-dir conflation + 5 bare-name subprocess calls → §4.4.
- **MED** domain cycles `caddie↔history`, `history↔reports`, `core→history` exposed by package boundaries → keep `__init__` empty (module-level lazy resolution keeps them working); optionally rebalance `fixtures`/decision-audit/report split in Phase 2.
- **MED** ~20 `patch("ai_caddie.*")` string targets across the test suite (Phase 2) — enumerated in the codex output; §4.3 handles the Phase 1 subset.
- **MED** packaging is `virtual` (`uv.lock` `source = { virtual = "." }`) — runtime uses the source checkout, not a wheel; subpackages are importable with `__init__.py`; the `.js` ship via `COPY ai_caddie/`. No build-system change needed for the current Docker runtime.
- **LOW** `tests/test_llm_providers.py:418` reads `Path("ai_caddie/llm_providers.py")` (Phase 2); `package.json` js paths (§4.6).
- **LOW** CI path filters: only `native-mobile.yml` is path-filtered and it is not keyed to backend paths; `tests/test_ci_workflow.py:141` asserts `ai_caddie/**` is *not* in it — unaffected.
