# Phase 5 Course Prep Productization Evidence

- Date: 2026-06-06
- Branch: `integration/v2`

## Scope

Implemented Phase 5 from `docs/superpowers/specs/2026-06-06-phase-5-course-prep-productization-design.md`.

## Evidence

- `ai_caddie.course_prep` now returns structured source-bound DTO rows with route coordinates, geometry coverage, source refs, missing-data rows, candidate routes, and carry targets.
- `/api/v2/courses/{global_id}/prep` preserves requested holes with missing geometry instead of dropping them.
- Mobile course/live packages can include optional `coursePrep` data for offline prep.
- Web v2 renders candidate routes, missing-data rows, source refs, and interactive route/hazard yardages from DTOs.
- iOS source contracts decode the new course prep fields and keep legacy decode compatibility for missing optional DTO members.
- Standalone untracked `course_review/*.html` remains untouched and is no longer the product dependency for this phase.

## Verification

```bash
uv run python -m unittest tests.test_course_prep tests.test_course_prep_api tests.test_mobile_contracts tests.test_server_v2_mobile -v
```

Result: PASS, 122 tests in 246.220s.

```bash
cd web_v2 && npm exec --yes --package=node@24 -- npm test -- --run CoursePrepPanel MobilePackagePrepPanel
```

Initial result: FAIL, 1 timeout in `CoursePrepPanel.test.tsx` under the default 5s Vitest test timeout.

Fix: set the integration-style CoursePrepPanel render test timeout to 10s. The test passed in isolation with behavior intact and failed only when paired with the adjacent mobile package test file.

Final result: PASS, 2 test files, 10 tests in 22.95s.

```bash
cd web_v2 && npm exec --yes --package=node@24 -- npm run lint
```

Result: PASS, exit 0.

```bash
cd web_v2 && npm exec --yes --package=node@24 -- npm run build
```

Result: PASS. Vite built `dist/` successfully.

```bash
cd web_v2 && npm exec --yes --package=node@24 -- npm run test:e2e
```

Result: PASS, 2 Playwright tests in 55.0s.

```bash
git diff --check
```

Result: PASS.

## Known Constraints

- Native iOS/Watch simulator tests require macOS/Xcode and were not executable in this Linux workspace.
- The local system Node is `v18.19.1`; Web verification used the temporary Node 24 prefix.
- GitHub Actions were not run for this local validation pass.
