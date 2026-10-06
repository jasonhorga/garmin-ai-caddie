# PR #389: download-intent lifetime review

Reviewed head: `4e7e7eb16632db849c7b806b3096489482d3eaf1`.
Status: P2, awaiting author fix; no merge or final full-live dispatch.

The prior foreground-installer and running-worker dequeue bypasses are fixed.
The original missing-prep-row journey assertion remains intact.

## Remaining finding

[P2 review](https://github.com/jasonhorga/garmin-ai-caddie/pull/389#issuecomment-6021873468):
an explicitly requested job retains its ID when paused, but foreground restart
checks only the current method argument and cannot restart it while fresh
entry remains pending. The old worker also cleans shared intent before checking
generation, account rebinding retains the intent set, and the already-active
download early return skips intent registration.

Require behavior proof for manual pause/foreground resume with gate still
pending, while automatic jobs remain blocked; cover stale/account intent too.
These are code-path findings, not failures of the existing green tests.

## Verification

- Source `37498292084` and Native `37498292248` passed.
- Independent read-only homeserver verification: 130 tests, 18.573 seconds, OK.
  Modules: `tests.test_mobile_contracts`, `tests.test_native_visual_parity`.
  Existing Build 80 API venv; network disabled; isolated `/review/data` tmpfs.
- Native compiled merge `83a473d2b2f164e8359821088426ce8c324979f4` has no
  changed mobile/ios files relative to the reviewed PR head.
- ZIP digests verified for native-build-evidence, design-snapshots and
  watch-snapshots. Every one of 89 iOS and 47 Watch design PNGs matches the
  individually reviewed #387 baseline byte-for-byte.
- Actual foreground and per-dequeue XCTest regressions passed. Full live
  back-nine/front-nine journey is reserved for the corrected final head.

Evidence directory:
`/home/jason/garmin-ai-caddie-data/operations/pr389-4e7e7eb1-20261006`.
Initial interrupted ZIP download was resumed and fully verified. Exact source
backup verified; snapshot/test container/data tmpfs closed at 17:44:19 UTC.
No new service, port, dependencies, worktree, tunnel or named volume.
Six local helpers removed after byte-identical remote backup verification;
allow-list retained. Production and retained Build80 health both HTTP 200.

Existing Build 80 candidate/tunnel remain for owner testing and final live
verification. Native evidence is simulator evidence. All historical ledger
detail is preserved verbatim in dated, non-authoritative state archives.
