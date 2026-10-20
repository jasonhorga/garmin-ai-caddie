# Card #448 — `up` refuses ambiguous or malformed release candidates

Card #447 added `ops/agenthub_deploy.py up`. It starts the database first and then the release
container that was serving. That release is the newest stopped one by `FinishedAt` that passes
`assert_layout`. This card makes that choice strict. `up` never guesses which release to start. It
refuses a candidate whose revision label is malformed, refuses a tie, and decides on what it reads
while it holds the sync lock.

Touches: `ops/agenthub_deploy.py`, `tests/test_agenthub_deploy.py`, `tests/test_agenthub_up_regressions.py`, `tests/acceptance/test_card_448_up_selection.py`, `.agent/contracts/card-448.md`

Acceptance tests (Claude-owned; Codex must not edit `tests/acceptance/`):
`tests/acceptance/test_card_448_up_selection.py` (5 tests). Every test runs the real script as a
subprocess, with fake `docker` and `curl` executables first on `PATH`, as in card #447. No real
containers are used.

PR body: `ops/agenthub_deploy.py` is a pinned release file. Write
"re-pin required: ops/agenthub_deploy.py".

## Interface

Only `up` changes. `deploy`, `rollback` and their helpers (`previous_release`, `select_rollback`,
`cleanup`) behave exactly as they do today, and their tests in `tests/test_agenthub_deploy.py` keep
passing unchanged. Everything in the card #447 contract still holds for `up`: the order of work,
the timeouts, the Docker command surface, the result line and output hygiene. The #447 acceptance
tests must keep passing.

### Configured values

`up` uses only the configured values for its selection:

| Variable | Default |
|---|---|
| `AICADDIE_CONTAINER_PREFIX` | `aicaddie-release-` |
| `AICADDIE_API_PORT` | `39055` |
| `AICADDIE_PRIVATE_VOLUME` | `garmin-ai-caddie_ai-caddie-private` |
| `AICADDIE_DEPLOY_NETWORK` | `garmin-ai-caddie_default` |
| `AICADDIE_DB_CONTAINER` | `garmin-ai-caddie-db-1` |

All five are read through the existing `Config`/`UpConfig`. A container that matches only the
defaults is not a candidate when other values are configured. It is never started, never counted in
a tie, never named in a refusal, and never health-checked. Its port is never read. A release that
runs on another port is not the release on the configured port: `up` does not check it and does not
refuse because of it.

### A valid release

A release container is **valid** when:
- its name starts with the configured prefix;
- its `ai.caddie.source-revision` label fully matches `[0-9a-f]{40}`, the existing `SHA_PATTERN`
  with `fullmatch`. A missing label, a null `Labels` map, an empty value, upper case, 39 or 41
  characters, non-hex characters and a trailing newline are all invalid;
- it passes the existing `assert_layout`: exactly one mount, of the configured volume, at
  `/var/lib/ai-caddie`, read-write, on the configured network.

A **stopped candidate** is a valid, stopped release container that publishes the configured port.

### Selection

Selection works on one listing of the containers:

1. **Something runs on the configured port.** The existing `find_current` decides, and it still
   fails closed on a non-release container or on several release containers.
   - If the release running there is valid: start nothing, and run `wait_health` for its revision.
   - If it is not valid: exit 1, `part=api`, `container=<its name>`. It is left running (`up` never
     stops anything), nothing is started, and **its local health is not read**.
2. **Nothing runs on the port.** Ignore every stopped container that is not a stopped candidate. A
   newer invalid one is skipped, not refused. Among the stopped candidates, take those with the
   latest `FinishedAt`:
   - **Compared as a time.** Use the existing `_finished_key`, which has a numeric fraction, or an
     equivalent. `.5Z`, `.50Z` and `.500Z` are the same time. `.9Z` and `.1Z` in the same second
     are different times.
   - **Exactly one:** that release is selected.
   - **Two or more:** this is a tie. Exit 1, `part=api`, `container=none`. The result line names
     every tied release, anywhere after `reason=`. Nothing is started and no local health is read.
     Only the tied candidates are named. Invalid releases and containers that match only the
     defaults are not counted and not named.
   - Name, Id and listing order never decide. Only the latest time matters: a tie among older
     candidates is ignored.
   - **None:** exit 1, `part=api`, `container=none`, as in #447.

### Re-selection under the sync lock

When step 2 selected a stopped release, `up` takes `SyncLock`. While holding it, `up` lists the
containers again and repeats the whole selection: steps 1 and 2, with validation and tie detection.
**The repeated selection decides:**
- a valid release now runs on the port, whether it is the one picked before or another one: start
  nothing, and `wait_health` for its revision; exit 0 with `container=<it>`;
- an invalid release now runs on the port: refuse it as in step 1;
- the earlier pick is gone, or a newer candidate appeared: start what the repeated selection picks;
- a tie now: refuse it as in step 2;
- no candidate now: exit 1, `container=none`.

Then `docker start` the selected release, while still holding the lock, and `wait_health` for its
revision, as in #447.

While `up` waits for the lock it makes no `docker` call. The existing `SyncLock` already works this
way. The test detects the wait by a quiet period of 0.7 s with no docker call after the database
start.

### Result line

The same as in #447: one `agenthub-deploy: result=` line, `action=up`. Every refusal in this card
is `result=failed`, `part=api`, exit 1, with ` reason=` followed by some text. `container` is the
refused running release, or `none` for a tie or when there is no candidate.

## Goals and pass conditions

"Start calls" means every `docker start` the script asked for, failed ones included, in order. Every
run also passes the #447 hygiene checks:
- exactly one result line;
- only `info`, `version`, `ps`, `inspect`, `image inspect` and `start`;
- no canary and no traceback in the output;
- no sync-script run and no public health request.

### G1 — Only a release with a valid revision label and layout is selected

1. `test_stopped_release_without_a_valid_revision_label_is_skipped`. A newer stopped release has
   each bad label in turn: none, null `Labels`, empty, upper case, 39 hex, 41 hex, non-hex, trailing
   newline. The older valid release `OLDER` is the one started:
   - the start calls are `[db, OLDER]`;
   - exit 0 with `container=OLDER`;
   - health is read for `OLDER`'s revision;
   - the newer release stays stopped.

   A case with an even newer wrong-volume release above the unlabelled one also starts `OLDER`.
2. `test_running_release_without_a_valid_label_or_layout_is_refused`. The release running on the
   port has each bad label in turn, or each bad layout: wrong volume, wrong network, read-only
   mount, wrong destination, an extra mount, no mount. A valid stopped release sits next to it.
   Each case gives:
   - exit 1, `part=api`, `container=<the running release>`;
   - no start call;
   - the running release still running and the stopped one still stopped;
   - no local health read.

   With the database stopped, the start calls are `[db]` and nothing else changes.

### G2 — The configured prefix, port, volume, network and database decide

3. `test_drill_configuration_ignores_containers_that_match_only_production_defaults`. The drill
   configuration sets all five variables to non-default values. The containers include:
   - the production database, running;
   - an unlabelled release running on the production port `39055`;
   - a newer production-prefix release with the drill layout;
   - newer drill-prefix releases with the production volume, the production network, or the
     production port, and one with no label;
   - a production-prefix release that ends at the same time as the newest valid drill release.

   Then:
   - the start calls are `[drill-db-1, <newest valid drill release>]`, and that release was
     started after the drill database was `healthy`;
   - exit 0 with that container, and health read on the drill port for its revision;
   - no health read on the production port, and the production containers are untouched.

   A second case has two valid drill releases tied, with a production-prefix release at the same
   time. Its result:
   - exit 1, `container=none`, naming both drill releases and not the production one;
   - the start calls are `[drill-db-1]`;
   - no health read.

### G3 — A tie among the newest valid releases is refused

4. `test_tie_among_the_newest_valid_releases_is_refused`. Each case runs in both listing orders.
   - **Refused:** exit 1, `part=api`, `container=none`, every tied name on the result line, start
     calls `[db]`, no API start and no health read. The cases:
     - two releases with the same `FinishedAt` text;
     - `.5Z` and `.500Z`;
     - three releases at `.25Z`, `.250Z` and `.2500Z`;
     - two tied releases below a newer release with an empty label.
   - **Not a tie:** start calls `[db, <expected>]`, exit 0 with it, and health read for its
     revision. The cases:
     - a valid release tied with an upper-case-label release and a wrong-network release: start the
       valid one;
     - two tied older releases below a newer one: start the newer one;
     - `.9Z` and `.1Z` in the same second: start `.9Z`.

### G4 — Under the sync lock the selection is repeated and decides

5. `test_selection_is_repeated_under_the_sync_lock`. The test holds the sync lock while `up`
   starts the database and picks `SERVING`. It waits for the quiet period, changes the model, and
   releases the lock. Every API start that happens must have been made while the lock was held.

   | Change while `up` waits | Result | Start calls |
   |---|---|---|
   | `SERVING` now runs on the port | exit 0 `container=SERVING`, health read for its revision | `[db]` |
   | another valid release now runs on the port | exit 0 with it, health read for its revision; `SERVING` stays stopped | `[db]` |
   | `SERVING` was removed | exit 0 `container=OLDER` | `[db, OLDER]` |
   | a newer valid stopped release appeared | exit 0 with it; `SERVING` stays stopped | `[db, <newer>]` |
   | a release tied with `SERVING` (`.500Z` against `.5Z`) appeared | exit 1 `container=none` naming both, no health read | `[db]` |
   | an unlabelled release now runs on the port | exit 1 `container=<it>`, left running, no health read | `[db]` |

## Free choices (not tested)

- Whether `up` takes the lock and re-reads when the first selection already refuses (tie, no
  candidate, invalid running release) or finds a valid running release.
- Whether the database health is checked again under the lock.
- Extra read calls (`ps`, `inspect`, `image inspect`).
- The wording of `reason=` and the order of the tied names in it.
- Log lines before the result line that mention skipped releases.
- Comparing `FinishedAt` through `_finished_key` or through any other parse that orders by time.

## Not covered (other cards; do not add here)

- A malformed or zero `FinishedAt`.
- Output redaction, signal handling, the deploy/rollback database guard, the systemd unit and the
  runbook.
- Any change to `deploy`, `rollback`, `previous_release`, `select_rollback` or `cleanup`.

## Gate notes

All five tests fail on `main` (`109bc27`):
- G1: `up` starts a newer unlabelled stopped release. It accepts any release running on the port,
  because the fake health echoes the container's own label, so even an empty label "matches".
- G2: the newest drill-prefix release has no label, and `main` starts it. `main` already honours
  the five variables for its existing filters. The test pins that they also govern the new rules:
  validation and ties.
- G3: `main` starts one of the tied releases.
- G4: `main` starts its earlier pick even though `SERVING` is already running.

I could not run Python in this sandbox, so I checked the tests by reading them against `main`'s
script. The gate's run is the authority. If a case looks wrong against this contract, report it on
the card. Never edit the tests.
