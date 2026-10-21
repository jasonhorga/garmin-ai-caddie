# Card #451 — Boot recovery: a systemd user unit and a runbook section

Card #447 added `ops/agenthub_deploy.py up`, and #448 made its release selection strict. Both are
merged. `up` brings the stack back in order: the Docker daemon, then the database, then the serving
release under the sync lock. Nothing runs it yet. This card adds a systemd **user** unit that runs
`up` once at boot from a pinned installed copy of the script. It also adds a runbook section that
says how to install the unit and how to read its log.

Touches: `ops/systemd/aicaddie-stack-up.service`, `docs/operations/runbook.md`, `tests/acceptance/test_card_451_stack_up_unit.py`, `.agent/contracts/card-451.md`

Acceptance tests (Claude-owned; Codex must not edit `tests/acceptance/`):
`tests/acceptance/test_card_451_stack_up_unit.py` (5 tests). They run offline. The runs of `up` use
fake `docker` and `curl` executables first on `PATH`. The runbook's install block runs with fake
`systemctl`, `loginctl`, `journalctl` and `sudo`, which only record their arguments. No real
container, systemd manager or home directory is touched.

This card does **not** change `ops/agenthub_deploy.py`. It is a pinned file, and no re-pin is
needed. If the tests seem to need a change there, report it on the card instead.

## Interface

### The unit file

`ops/systemd/aicaddie-stack-up.service` is exactly these lines. Each line ends with one newline,
and there is no comment line and no other line:

```
[Unit]
Description=Start the AI Caddie database and API after boot
After=network-online.target

[Service]
Type=oneshot
ExecStart=/usr/bin/python3 %h/.local/lib/aicaddie/agenthub_deploy.py up
TimeoutStartSec=1320

[Install]
WantedBy=default.target
```

Why these values:
- **`ExecStart`** runs the installed copy under `%h` (the user's home), not a checkout. A checkout
  changes with every pull, but the copy changes only when the owner reinstalls it. The interpreter
  is given explicitly, so the copy does not need an executable bit.
- **`TimeoutStartSec=1320`.** A `Type=oneshot` unit has no start timeout by default. `up` has four
  default waits:
  - Docker daemon: 300 s;
  - database health: 180 s;
  - sync lock: 600 s;
  - API health: 180 s.

  They add up to 1260 s, and 60 s more is allowed for listing and polling. The card names three
  waits (daemon, database, health: 660 s). This value covers those three and the lock wait as well.
- **No `Environment=`.** `up` uses its production defaults. Anything else comes from the user
  manager's environment.
- **`After=network-online.target`** is what the card asks for. A user manager has no
  `network-online.target`, so in practice this ordering does nothing there. That is safe because
  `up` itself waits up to 300 s for the Docker daemon. `Wants=` is left out on purpose.

### The runbook

`docs/operations/runbook.md` gets one level-2 section, `## Boot recovery`. It runs from that
heading to the next `## ` heading, and it can go anywhere in the runbook. The section must contain
each of these texts, written exactly like this:

| Text | What it covers |
|---|---|
| `ops/systemd/aicaddie-stack-up.service` | the unit file in the repository |
| `agenthub_deploy.py up` | the command the unit runs |
| `.local/lib/aicaddie/agenthub_deploy.py` | the install location of the pinned copy |
| `.config/systemd/user` | the unit directory |
| `systemctl --user enable` | enabling the unit |
| `loginctl enable-linger` | needed because without linger a user unit does not start at boot |
| `journalctl --user -u aicaddie-stack-up` | reading the unit's log |
| `sync lock` (any case) | `up` waits for the sync lock before it starts a stopped API |

**Paths.** Every occurrence of `.local/lib/aicaddie/` and of `.config/systemd/user` in the section
comes right after `~/` (in shell examples and prose) or `%h/` (when quoting the unit). Do not use
`$HOME/`, an absolute home path, a user name or a host name.

**Install block.** The section has a fenced code block with the info string `bash` that contains
`systemctl --user enable`. The test runs the first such block as follows:
- with `bash -e -u -o pipefail -c <block>`;
- from the repository root;
- with `HOME` set to a temporary directory and `USER` set to a test name;
- twice, so it must work again for a re-install after a release.

The block must:
- copy `ops/agenthub_deploy.py` to `~/.local/lib/aicaddie/agenthub_deploy.py` as a regular file
  (`install` or `cp`; not a symlink);
- copy `ops/systemd/aicaddie-stack-up.service` to
  `~/.config/systemd/user/aicaddie-stack-up.service` as a regular file (not `systemctl link`);
- create the directories it needs (`mkdir -p`);
- call `systemctl` only with `--user`, and enable `aicaddie-stack-up.service` (or
  `aicaddie-stack-up`);
- call `loginctl enable-linger` with no argument or with `"$USER"`. `$(whoami)` is not accepted,
  because the test sets `USER` and not the real account;
- contain no `sudo`, no `<placeholder>` and nothing else that fails when run as written.

A block that would pass:

```bash
mkdir -p ~/.local/lib/aicaddie ~/.config/systemd/user
install -m 0755 ops/agenthub_deploy.py ~/.local/lib/aicaddie/agenthub_deploy.py
install -m 0644 ops/systemd/aicaddie-stack-up.service ~/.config/systemd/user/aicaddie-stack-up.service
systemctl --user daemon-reload
systemctl --user enable aicaddie-stack-up.service
loginctl enable-linger
```

Other blocks or prose may say where to run it: from the root of a clean export of the deployed
revision (`git archive <sha>`, as in "Manual invocation"). They may also say that the copy must be
reinstalled whenever `ops/agenthub_deploy.py` changes. Placeholders are fine outside the install
block.

**Environment table.** The `### Environment` table under `## agenthub executor deploy` gets one row
per new `up` variable. Each row has the existing three columns (Variable, Meaning, Default), a
meaning that is not empty, and a default cell that starts with the value in backticks:

| Variable | Default cell starts with |
|---|---|
| `AICADDIE_DB_CONTAINER` | `` `garmin-ai-caddie-db-1` `` |
| `AICADDIE_DB_READY_TIMEOUT_SECONDS` | `` `180` `` |
| `AICADDIE_UP_DOCKER_TIMEOUT_SECONDS` | `` `300` `` |

Each variable has exactly one row in that table.

## Goals and pass conditions

### G1 — A systemd user unit runs `up` at boot from a pinned installed copy

1. `test_unit_file_has_exactly_the_contract_lines`: `ops/systemd/aicaddie-stack-up.service`
   exists and its lines are exactly the ones above, ending with one newline.
2. `test_unit_exec_start_brings_a_stopped_stack_up_from_the_pinned_copy`: the setup is:
   - the script is copied to `<tmp-home>/.local/lib/aicaddie/agenthub_deploy.py`;
   - the unit's `ExecStart` has `/usr/bin/python3` replaced by the test runtime and `%h` replaced
     by `<tmp-home>`;
   - it runs with `<tmp-home>` as the working directory.

   The argv must be exactly `[<runtime>, <tmp-home>/.local/lib/aicaddie/agenthub_deploy.py, up]`.
   The fake starts with the database stopped (it still shows a stale `healthy`) and two exited
   release containers. The production defaults apply, except for a private sync lock path and a
   0.05 s poll. Then:
   - exit 0, with exactly one `result=ok` line carrying `action=up` and `container=<serving release>`;
   - the starts are `[db, serving release]`, in that order;
   - when the API started, the database was `healthy` and the sync lock was held;
   - local health reported the serving release's revision;
   - afterwards exactly the database and the serving release are running;
   - only `info`, `version`, `ps`, `inspect`, `image` and `start` were called on `docker`, and the
     output has no traceback.
3. Test 4 below also runs the `ExecStart` of the unit that the install block **installed**, with
   the same checks.

### G2 — The runbook says how to install the unit and read it

4. `test_runbook_boot_recovery_section_names_every_item`: there is exactly one `## Boot recovery`
   section. It contains every text in the table above, and "sync lock". Every `.local/lib/aicaddie/`
   and `.config/systemd/user` in it comes right after `~/` or `%h/`.
5. `test_runbook_install_block_installs_and_enables_the_unit`: the install block runs twice and
   exits 0 both times. Afterwards:
   - `~/.local/lib/aicaddie/agenthub_deploy.py` and
     `~/.config/systemd/user/aicaddie-stack-up.service` are regular files, byte-identical to
     `ops/agenthub_deploy.py` and `ops/systemd/aicaddie-stack-up.service`;
   - every `systemctl` call has `--user`, and one of them enables `aicaddie-stack-up`;
   - `loginctl enable-linger` was called, with no argument or only the test user;
   - `sudo` was never called.

   Then the installed unit's `ExecStart` brings the stack up, with the checks of test 2.
6. `test_environment_table_lists_the_up_variables`: the `### Environment` table has one row for
   each of the three variables above, with three cells, a meaning, and the default in backticks at
   the start of the last cell.

## Free choices (not tested)

- The rest of the `## Boot recovery` text: its order, any extra commands (for example
  `systemctl --user start` for a manual test, or `systemctl --user status`), and the explanation of
  linger and of the sync lock wait.
- Whether the install block runs `systemctl --user daemon-reload` and uses `enable --now`.
- `install` or `cp`, and the file modes.
- The wording of the Meaning cells, and where the three rows go in the table.
- Whether the `### Contract` code block also lists `ops/agenthub_deploy.py up`. Adding it is
  welcome.

## Not covered (other cards; do not change here)

- `ops/agenthub_deploy.py` and how `up` behaves (#447, #448, and later `up` cards).
- `docker-compose.yml`, the images, and the restart policies.
- A system-level unit, a timer, or an `ExecStartPre`.
- Text elsewhere in the runbook. That includes an existing absolute home path in
  `### Homeserver Sync Cron`, which a separate hygiene card can replace with a placeholder.

## Gate notes

All five tests fail on `main` (`c24063c`):
- G1: `ops/systemd/aicaddie-stack-up.service` does not exist. Test 1 fails on the missing file, and
  test 2 errors when it reads the unit.
- G2: the runbook has no `## Boot recovery` section, and the Environment table has no row for the
  three `up` variables.

G1's entry-point test is test 2, which runs the script as a subprocess through the unit's
`ExecStart`. G2's entry-point test is test 5, which runs the runbook's install block with bash and
then the installed unit's `ExecStart`. Running Python was refused in this sandbox. I checked the
tests by tracing them against `main`'s `up` (`select_up_api`, `SyncLock`, `wait_up_database`,
`wait_health`). The gate's run is the authority. If a case looks wrong against this contract,
report it on the card. Never edit the tests.
