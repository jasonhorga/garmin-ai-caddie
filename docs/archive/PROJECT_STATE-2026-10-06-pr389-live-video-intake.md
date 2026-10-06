# HISTORICAL ARCHIVE — NON-AUTHORITATIVE

Verbatim state superseded by completed video download and partial visual review.

**Updated:** 2026-10-06 19:30 UTC

Download five live evidence ZIPs, retaining logs.

Local review copies `.codex-pr389-56022d32-live-review` planned for visual
inspection; remote sheets/index remain canonical, copies expire Oct 7 21:15.
Failed selection was not saved as a PNG; video 11443055917 is necessary.

- Capacity baseline: 67 GiB root/3.3 GiB shm/3.9 GiB available RAM.

Previous reviewed head `4e7e7eb16632db849c7b806b3096489482d3eaf1` fixes P2 6020952816
(real foreground installer and automatic worker dequeue gate bypass).
Prior P2 `6021873468` on 4e7e7eb1: retained explicit requests cannot resume through the
start gate; stale-worker cleanup precedes generation check; account rebind
retains intent; active-row early return skips registration. No merge.
Author reply `6021043095` read; do not answer it twice.

Exact-head evidence complete; evidence verdict `6022166928` handled:
- Source `37498292084` / Native `37498292248` passed.
- Independent 130 tests, 18.573 s, OK; read-only Build80 image, no network.
- All three ZIP digests verified; all 89 iOS/47 Watch design PNGs equal the
  individually reviewed #387 baseline byte-for-byte.
- Native compiled merge `83a473d2b2f164e8359821088426ce8c324979f4` has no
  mobile/ios diff from reviewed head; real foreground/per-job XTests passed.
- Exact source backup verified; snapshot/container/tmpfs closed.
- Final full live run waits for corrected head; original assertion intact.
- Review record: `docs/operations/2026-10-06-pr389-download-intent-lifetime-review.md`.

Earlier heads/comments consumed; detailed proof archived:
- #389 af7a837e: Source 37491131543 / Native 37491131642 / 130 OK /
  136 matching PNGs. P2 6020952816 / evidence 6021181763 handled.
- #389 87a00b3a: Source 37473708159 / Native 37473708114 / 129 OK /
  136 matching PNGs; P2 6019848254 / evidence 6020049168 handled.
- Author replies 6019989194/6020075979 handled. Intermediate 41857121
  runs 37490470913/37490470917 cancelled, superseded; do not reopen.
- #388 merge 9f56c35b, final 4a1108aa; original 9 + extended 15 tests OK.
  P2 6018586650 / fix 6018681148 / verdict 6019983448 handled.
- #387 merge c07114b3, final 4504b299; 130 OK/all design+Watch frames reviewed.
  Full live 37456686597 Watch passed; iOS failed missing prep-library row.
  RCA 6017108044 proved pre-existing race, product repair belongs to #389.
  Comments 6015347738/6016542546/6017410544/6019856320 handled.
  RCA supersedes 6016510080. Old review_pr376 is complete/resources closed.

Local copies `.codex-pr389-56022d32-live-review`: Watch sheets 1–2 (13 frames)
and iOS sheets 1–6 (36 frames) reviewed; iOS 7–15 (50 frames) pending.

Trace event-latency-50615 shows home package activation 60 s after first
Hub appearance; causal link unproven. Extract video interval before RCA.

- `PR-389-HALF-START-ENROLLMENT-REVIEW` — `in-progress`: review 56022d32 fix.
  Re-test manual pause/real foreground resume with gate pending; automatic
  jobs still wait. Check stale-worker/account intent and active-row request.
  Then exact tests/Native artifacts and one final full live on Build80:
  fixture=false, capture_scope=full, live preflight=true; original assertion
  unchanged. Inspect queue latency trace, 后九→前九/relaunch prep journey,
  iOS/Watch runtime screenshots and Watch rendered marker before merging.

P2 review/evidence/resource closure and verbatim archives pushed as **927042e8**.
Inspect full live failure at course selection, actual iOS/Watch screenshots,
helper tap/scroll and catalogue facts. Preserve original journey assertions
on retained Build80 backend when code findings clear. Uncommitted wait-start state/
archive accompanies next real work (git add -f ignored dated archive).
