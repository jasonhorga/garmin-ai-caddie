# Web product tests (C16g)

Use the installed dependencies and Chromium, from `web_v2`:

```sh
heavy-lock npx playwright test e2e/product
npm run test:e2e -- --list
npx eslint e2e/product
```

For a local run, set `use.launchOptions.executablePath` in an external
Playwright config to the already installed `chrome-headless-shell` executable
(including when its revision differs from Playwright's default). Preserve the
repository config's projects and web servers; if the external config is outside
`web_v2`, point its `testDir` at this repository's `web_v2/e2e`. Run it from
`web_v2` with `heavy-lock npx playwright test e2e/product --config <external-config>`.
Do not run `playwright install`.

The existing Playwright configuration starts Vite and runs desktop/mobile
Chromium with one worker. The CI `test:e2e` entrypoint discovers all 30 product
cases (15 data rows × 2 projects). No configuration changes are required.
These tests follow the existing e2e `page.route` fixture API pattern: every API
operation is intercepted, unexpected operations fail, and external HTTP is
blocked. The fixture runs no live backend, Garmin login or model request.

## Final spec coverage

Numbering follows `docs/product/2026-10-23-product-test-spec.md`.

| Promise | Primary test | Rows | Page behavior |
| --- | --- | ---: | --- |
| 9.1 | `j9_1_web_numbers_match_handwritten_golden` | 3 | Scores/performance, unknown phases, prep/sandbox; all equal explicit numbers below. |
| 9.2 | `j9_2_corrections_use_same_fixed_projection` | 4 | Web deletion, App-originated saved snapshot, rejected save, already-loaded statistics after saving. |
| 9.3 | `j9_3_session_import_preserves_sync_state` | 3 | Successful import enables sync; failed first import stays disabled; failed replacement preserves usable sync. |
| 9.4 | `j9_4_diagnostics_are_owner_only` | 4 | Owner default/opt-in, member with a forged diagnostic flag, legacy player link with a forged flag. |
| 9.5 | `j9_5_review_has_single_round_share_entry` | 1 | Creates a round share, opens its page in a fresh unauthenticated context, and checks the fixed read-only scorecard. |

This is the W layer. API projections are synthetic, including the snapshot
representing a prior App correction. They establish page behavior against an
independent oracle; they do not establish Swift execution, backend persistence,
append-only history, resync survival, or server authorization. The card allows
an initial small handwritten scores fixture; the C16b 30-round fixture has not
yet been substituted. The first prep/sandbox hole matches C16c's new shared
`h1_tee_0` golden for distance and opening clubs/carries. The second hole is a
small independent navigation fixture, not C16c's second hole.

The read-only share view uses the C28a token contract. The review button creates
the token-backed `/s/<t>` page URL, and the 9.5 test opens that URL in a fresh
unauthenticated context. It checks the fixed 72/Par72/18-hole snapshot, absence of
diagnostics and mutation controls, and refusal to display the 90-stroke fixture
round. The legacy `/p/<player-token>` remains a player capability, not a round
share; backend scope enforcement is covered by C28a.

## Handwritten oracle

| Round | Holes | Par | Score | Putts |
| --- | ---: | ---: | ---: | ---: |
| Latest | 18 | 72 | 72 | 36 |
| Previous | 18 | 72 | 90 | 54 |
| Nine only | 9 | 36 | 40 | 18 |

Every hole is Par 4. The latest round has eighteen 4s, the previous eighteen
5s, and the nine-hole round four 5s plus five 4s: 45 holes, 23 pars, 22 bogeys.
Complete-round mean = `(72 + 90) / 2 = 81`, best = 72. Nine-hole 40 is excluded.
Recent 10/20 both contain these same two eligible rounds. Handicap and
penalties are unknown and must not display zero.

Recorded phases: fairways `24/45 = 53%` rounded; GIR `18/45 = 40%`; putts
`(36 + 54 + 18) / 3 = 36` per round. Par-4 mean to-par `22/45` displays 0.5;
par-or-better `23/45 = 51.1%`. The unknown-phases row removes phase/putting
coverage, requiring unknown markers for all four phases. Partial shot files
contain only nine recorded shots, independent of complete scorecards/putts.

Prep covers two holes, each Par4. Hole 1 is 300m (328yd), recommending stock
6I at 150m (164yd). Hole 2 is 200m (219yd), recommending 9I at 100m (109yd).
Total = Par8 and `328 + 219 = 547yd`. Sandbox tee distances are 328yd/219yd.
On the first hole, safe = 9I/100m/109yd, stock = 6I/150m/164yd, attack =
3W/200m/219yd. Each strategy must request and display its own fixed result.

The review's input geometry has one coordinate unit per metre. Deleting s2
leaves s1 `(150,450) → (150,250)` and s3 `(150,250) → (150,150)`, numbered
1/2. The fixed timeline is 1D/200m/219yd, PW/100m/109yd. The request is compared
with this handwritten snapshot; the fake backend returns a separately written
saved snapshot, never the request itself. Before deletion each of 1D/7I/PW has
three samples; afterwards 7I has two and total shot count is eight. An
App-originated correction starts at that same fixed saved projection.

Assertions observe rendered data, accessible controls, outbound operations and
refreshed views. They do not compare image pixels or inspect source/config
text. Chinese labels locate controls; explanatory prose is not a golden.

## Known red and verification limits

See `tests/product/known-red/C16g.md` for the reproduced gaps (9.2
cached-statistics is fixed; 9.5 share-entry is covered here).
Expected-failure annotations occur immediately
before the specific failing assertion, after review/edit setup succeeds. A
fixed assertion produces an unexpected pass so the annotation must be removed.
Do not count browser-launch errors as product failures or mutation kills.

The project console ran both projects with installed
`chromium_headless_shell-1234`, selected through an external config's
`launchOptions.executablePath`: all 30 cases completed successfully (26 passed,
4 expected failures), and all five fault patches made their target tests red.
The 9.5 mutation covers the review prerequisite, not share authorization.
`tests/product/faults/C16g.md` records those results and exact target rows.
The execution sandbox still has no visible browser cache; its local checks
cover collection and lint. No browser was downloaded.
