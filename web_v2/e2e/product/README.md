# Web product tests

Run from `web_v2`, using the installed Playwright package and Chromium:

```sh
heavy-lock npx playwright test e2e/product
```

The existing `playwright.config.ts` starts the Vite servers and runs desktop
and mobile Chromium projects, with one worker. These tests use the existing
e2e `page.route` fixture API pattern. Every `/api/**` request is intercepted;
unhandled operations fail the test. External HTTP requests are blocked. No
Garmin login, model provider, live API, package installation or browser download
is needed during a run with the dependencies already present.

## Coverage and boundaries

| Promise | Page behavior |
| --- | --- |
| 9.1 | Career/recent scores, known and unknown performance metrics, two prep holes, sandbox distances and strategy recomputation match handwritten numbers. |
| 9.2 | Reauthentication disables sync; successful import clears pasted fields and enables a real sync request; rejected import keeps sync disabled and preserves the form. |
| 9.3 | Web deletion submits the exact fixed shot sequence and fetches the saved projection; an App-originated snapshot displays the same independent golden; reopening retains it. Failed saves retain the draft and allow cancellation. |
| 9.4 | Default owner and member views hide diagnostics; owner opt-in reveals actual source references. Member settings omit owner controls. |
| 9.5 | A valid legacy `/p/<token>` link can open a populated review with no diagnostics or mutation controls; requests retain that link's bearer. A revoked link returns to sign-in with no product data. |

This is the W layer: the backend projections are synthetic, including the
snapshot representing an App correction. These tests do not run Swift, verify
server persistence/authorization, or prove cross-client calculations. Align
the projections and the independent assertions with the C16b/C16c handwritten
goldens when those are available. Do not replace the oracle with output from
product code.

The share promise deliberately requires read-only behavior on the current
legacy link entry. A failure caused by visible edit/annotation controls is a
product gap, not grounds to skip the test or weaken that requirement. A
single-round share capability and server-side denial of other round IDs need
their own backend coverage; a route mock cannot establish that boundary.

## Handwritten oracle

Three synthetic rounds on one course:

| Round | Holes | Par | Score | Putts |
| --- | ---: | ---: | ---: | ---: |
| Latest | 18 | 72 | 72 | 36 |
| Previous | 18 | 72 | 90 | 54 |
| Nine only | 9 | 36 | 40 | 18 |

Every hole is Par 4. The first round has eighteen 4s; the second eighteen 5s;
the nine-hole round has four 5s and five 4s. Thus there are 45 holes, 23 pars
and 22 bogeys. Eighteen-hole mean = `(72 + 90) / 2 = 81`; the nine-hole 40
never enters that mean or the eighteen-hole best (72). Recent 10/20 both
contain the same two eligible rounds. Handicap and penalties are unknown.

The fixture's recorded phase counts are 24/45 fairways (53% rounded), 18/45
GIR (40%), and 108 putts over three recorded rounds (36 per round). Par 4
average to-par is `22/45`, displayed as 0.5; par-or-better is `23/45 = 51.1%`.
The partial shot files contain nine recorded shots in total; they are not the
source of the complete scorecard/putting aggregates.

The prep projection intentionally covers just two holes. Hole 1 is 300 m
(328 yd) with a 200 m landing (219 yd), recommending 1D. Hole 2 is 200 m
(219 yd) with a 150 m landing (164 yd), recommending 7I. The displayed prep
total is Par 8 and `328 + 219 = 547 yd`. The sandbox starts on each tee;
stock carry is 200 m (219 yd), attack carry is 220 m (241 yd).

The review map uses 1 pixel per metre. Deleting s2 leaves s1 from
`(150,450)` to `(150,250)` and s3 from `(150,250)` to `(150,150)`.
The fixed post-edit timeline is therefore 1D/200 m (219 yd), then PW/100 m
(109 yd), numbered continuously. The post-save response is a separately
written snapshot; it never echoes the submitted request as its oracle.

Assertions observe DOM values, accessible controls, outbound operations and
refreshed views. They do not compare screenshot pixels or inspect source or
configuration text. Chinese strings identify controls and meaningful data
states; explanatory prose is not asserted verbatim.
