## Verdict

Both drafts are unusually careful — the P0/P1/P2/P3 classes, the "backup that has never been restored is not evidence of recoverability" rule, and the refusal to auto-prune named volumes are the right instincts, and I'd approve the *policy* with the fixes below. I would **not** approve the migration table as written: it has at least one silent-data-loss path (Compose project name), one bridge that would delete a directory (`aicaddie-data`), and no quiesce step for cron. Everything below is derived from the two files only — I ran no commands and inspected no host state, so every claim about `/home/jason`, systemd, or Docker is an **assumption to verify**, marked as such.

## Must-fix

1. **Docker Compose project name (data loss, unverified but high impact).** *Fact:* the protected list contains `garmin-ai-caddie_ai-caddie-private` — a Compose-generated name, whose prefix defaults to the compose file's *directory name*. *Assumption:* Compose currently runs from a directory that the migration renames or moves. If so, the next `docker compose up` creates **new empty volumes**, Postgres initialises blank, and the real data is orphaned but invisible. Neither draft mentions this. Before any move, pin `name:` in the compose file (or `COMPOSE_PROJECT_NAME` in an env file committed alongside it), restart once, and confirm the same volume names are still attached.

2. **`aicaddie-data` bridge destroys the parent (data loss).** *Fact:* layout row 3 moves only `/home/jason/aicaddie-data/evidence` but specifies "symlink for old `aicaddie-data` root". Replacing the root with a symlink deletes/hides every sibling of `evidence/`. Bridge must be `aicaddie-data/evidence` → new path, and the parent stays a real directory until separately audited.

3. **Cron is not quiesced (corruption + half-migrated state).** *Fact:* two cron-driven entrypoints move. If the sync job fires mid-move it runs a half-updated tree, or rebuilds paths you just moved. Add: disable the cron entries (comment, `crontab -l` captured to `manifests/`), confirm no run in flight via lockfile/`pgrep`, migrate, update paths, re-enable, then watch one full cycle. Also enumerate *all* schedulers — user crontab, `/etc/cron.d`, `/etc/cron.{daily,hourly}`, systemd timers — §8.3 says "cron entry" and will miss timers.

4. **Script relocation via symlink breaks self-location.** *Assumption:* `aicaddie-sync.sh`/`prepare-recent.sh` resolve siblings with `$0`/`dirname "$0"`. Invoked through the old-path symlink, `$0` is the *old* path and relative lookups (build context, `.env`, log paths) break or write back to `/home/jason`. Read both scripts first; if they self-locate, either update cron to the new absolute path and skip the symlink, or make the bridge a two-line wrapper `exec /home/jason/garmin-ai-caddie/services/sync/aicaddie-sync.sh "$@"`.

5. **Caddy config under `/home/jason` will likely fail to load (service outage).** *Fact:* the row says "current Caddyfile" with no path. *Assumption:* it is `/etc/caddy/Caddyfile` served by the packaged `caddy.service`, whose upstream unit sets `ProtectHome=true` and runs as user `caddy`. Both the sandbox and `/home/jason` traversal permissions would make the symlink target unreachable — and the failure surfaces on next reboot, not at reload. Verify `systemctl cat caddy` and the runtime user before choosing this. Also: use `caddy validate` then **`reload`**, never `restart` (restart drops connections and can re-trigger ACME).

6. **`:latest` as rollback alias and cron target (rollback loss).** *Fact:* `garmin-ai-caddie-api:latest`/`rollback-a6d5ec5` and `aicaddie-sync:latest` are both listed as protected roles. A subsequent build retags `latest`, the rollback image becomes dangling, and §5.6's builder/image prune can reap it. Rollback must be pinned by **digest** in the manifest; cron should reference an immutable tag promoted deliberately, not `latest`.

7. **Docker rules are host-wide but §9 scoping is not.** *Fact:* §9 forbids touching `sat-coach-*`, `health`, `bs-companion`, `actions-runner`; *fact:* `docker builder prune` and image removal are global and will hit those projects' caches and images. Add to §5.5: an image is removable only after checking that **no other project's** compose/scripts reference it by tag, and note that builder prune is a host-wide, cross-project action requiring the same gate.

8. **tmpfs sizing ignores other `/dev/shm` consumers.** *Fact:* §3 gates on `df -h /dev/shm` and `free -h`. *Fact:* the protected list includes `aicaddie-pw-profile` (Playwright) and PostgreSQL — both heavy `/dev/shm` users; browser suites are the classic `/dev/shm` exhaustion case. A 2 GiB snapshot that fits today can OOM a test run later. Add: never create a snapshot while a browser suite or DB-heavy job is running, and state explicitly that **`/dev/shm` is lost on reboot and must never hold the sole copy** (§3 says this for `/tmp` only — and these very drafts currently live only in `/dev/shm/aicaddie-policy-review-20260822-r2`).

9. **`actions-runner` shares the UID (permissions).** *Assumption:* it runs as `jason`. Then workflow code has write access to the new `persistent/` tree, which contradicts §1's "not a second uncontrolled source repository". Set `persistent/` to `0700`, state the intended owner/mode for every top-level dir, and record the runner as an accepted risk or scope it out.

10. **`evidence/public-staging` vs `demos` (exposure).** Caddy's `file_server` follows symlinks. Rule: the public directory must contain **copies only, never symlinks** into the project root, and `browse` must stay off — otherwise a bridge symlink can walk into `persistent/`.

## Optional

- Specify the move mechanism. Same-filesystem `mv` is an atomic rename (assumption: all paths are on `/home`); anything cross-device should be `rsync -aHAX` + checksum verify + delete, never `mv`.
- P2 TTLs (24 h / 7 d) have no mechanism. A cron that *reports* expired items and never deletes would make them real.
- §2 requires a manifest from "every session that creates anything" while §6 makes reviews read-only — say where a read-only review's manifest goes (one line appended to `manifests/`, or nothing at all).
- §3's "20% of available RAM" — pick `MemAvailable` explicitly.
- §1 mandates `/home/jason/<project>` but the layout draft references `/home/codex`; note it as a sanctioned exception.
- The layout has no location for the code checkout itself (no `repo/`/`src/`), yet lists `.venv`/`node_modules` as P3.

## Safe sequence

1. Preflight capture → `manifests/` (crontab + `/etc/cron.d` + timers, `systemctl cat caddy`, `docker compose config`, volume list + mounts, `df -hP /`, `/dev/shm` usage, SHA-256 of the two scripts and Caddyfile).
2. Read both `.sh` scripts for `$0`-relative behaviour; pin the Compose project name; restart once and confirm identical volume names. **Nothing has moved yet.**
3. Create the empty tree with intended ownership/modes.
4. Quiesce cron; confirm no run in flight.
5. Move P0 data (`garmin-ai-caddie-data`, `aicaddie-production-backups`) with a verified test restore *first*; add bridges; verify checksums.
6. Move service entrypoints; update cron to absolute new paths; re-enable; observe one full cycle.
7. Caddyfile last, and only if step 2 showed the runtime user can read the new path: `validate` → `reload` → confirm a live URL.
8. Logs and legacy evidence.
9. Docker candidates — separate change window, after 7 quiet days.

## Docker candidates

Agree with holding all four. `aicaddie-sync:28a9d18-candidate`: keep until `6a6080c` has run unattended for a week. The two preflight volumes: "zero-byte" needs its evidence recorded (`docker volume` reports no size, so this presumably came from `du` on `/var/lib/docker/volumes`) — a zero-byte `pgdata` means the cluster never initialised, which supports removal, but record `docker volume inspect` output first. `alpine:latest` — 13 MB is not worth the risk; it is a common base/`FROM` and a healthcheck helper. Keep. BuildKit ~2.5 GB: the only genuinely worthwhile reclaim; age-filtered prune, no build running.

## Exact changes

- Layout table row 3, "Compatibility bridge" → `symlink at old aicaddie-data/evidence path; parent directory stays in place, audited separately`.
- Layout table rows 5–6, bridge → `wrapper script or updated absolute cron path; symlink only if the script is verified location-independent`.
- Layout table row 9, "Current path" → replace `current Caddyfile` with the absolute path, and add `verify caddy runtime user + ProtectHome before symlinking into /home`; change "restart" to `validate then reload`.
- Add a Preflight bullet: `Compose project name pinned and volume identity re-confirmed after pinning`.
- Add a Preflight bullet: `all schedulers enumerated (user crontab, /etc/cron.d, /etc/cron.*, systemd timers) and quiesced`.
- Policy §3, after "consume memory" → `/dev/shm is cleared on reboot and shared with PostgreSQL and browser suites; never the sole copy, never created while a browser suite is running`.
- Policy §5.5, append → `and no other project references the tag`.
- Policy §5, new rule 8 → `Rollback images are pinned by digest in the manifest. :latest is never a rollback or cron target.`
- Policy §8.3, replace "cron entry" with `cron entry (user, /etc/cron.d, /etc/cron.*) or systemd timer`.
- Policy §9, append → `Public delivery directories contain copies only, never symlinks into a project root; directory browsing stays disabled.`
- Layout, new top-level section: intended owner/mode per directory, with `persistent/ 0700`.

## User decisions

1. Where does the Garmin **code checkout** live — `/home/codex`, or a new `repo/` under the root? The layout is silent.
2. Does `actions-runner` run as `jason`? If yes: accept the shared-UID risk, or move it off this host.
3. Caddyfile — leave at `/etc/caddy` with a checked-in *copy* under `services/caddy/`, or symlink into the home tree (only viable if step 2 clears)?
4. How long do the compatibility symlinks live before they are removed and the migration is declared closed?
5. Is `aicaddie-sync:28a9d18-candidate` still a rollback you'd actually deploy, or superseded?
