# Prior Codex-Only Whole-Repository Audit

> Provenance correction (2026-09-04): this was a Codex-run, read-only
> control-plane snapshot inspection. It was not a Claude, Fable, or "Cloud"
> model session. The filename is retained for historical link stability.

Date: 2026-09-04 UTC
Mode: read-only
Snapshot: `/dev/shm/garmin-ai-caddie-cloud-audit-20260904`
Snapshot HEAD: `04ab1da8b77950d0cdf3dde09174f2c76460f0ec`
Snapshot expiry: 2026-09-05T03:29:05Z

## Finding

### P2 - Reconciliation parent order was misstated in the live state document

The snapshot's `docs/operations/PROJECT_STATE.md:84-89` said that PR #331
preserved the old `integration/v2` line as the second parent of merge
`1775d87a`. The Git object record proves the actual order:

1. `b5e17d31` - old `integration/v2` line (first parent)
2. `a331281a` - reconciliation/MAP1 line (second parent)

The inconsistency could mislead first-parent release-history analysis and a
future reconciliation, but does not alter the product tree or runtime
behavior. The related `docs/operations/branch-reconciliation-20260904.md`
description of the earlier `79ee08cd` parent order was correct. The live state
document and branch strategy record were corrected in `6593b95e`.

## Reviewed scope

- Git refs, merge bases, merge parents, tags, and MAP1 reconciliation history.
- `docs/operations/PROJECT_STATE.md` and branch reconciliation records.
- Canonical contract authority files and `tools/contracts/check_authority.py`.
- Mobile live-round and Watch input schemas, generated Swift contract paths,
  Python/server serializers, and the sync-marker/server-sequence boundary.
- iOS start/map/precision paths and Watch start/map/course-library/model paths.
- CI and release workflow inventory, with targeted inspection of backend route,
  authentication, member-isolation, session/media path, and package/map code.

No builds, tests, dependency installation, browser automation, services,
containers, ports, credentials, or production data were used. No source files
in the snapshot were modified.

## Remaining unknowns

The read-only source pass cannot prove physical S70 Digital Crown/touch feel,
paired-device behavior, GPS hardware behavior, or production network outcomes.
The targeted auth/route and event-contract inspection was not expanded into a
runtime test, so absence of an additional defect is not a full security or
compatibility certification.

## Resource handoff

- Created resource: the temporary read-only snapshot above (approximately
  32 MiB); no other project resources were created.
- The report is now the repository archive copy; its SHA-256 is recorded in
  `docs/operations/PROJECT_STATE.md` after the archive commit. The earlier
  temporary-copy hash was superseded when the provenance wording was corrected.
- Cleanup: Codex removed the snapshot and temporary report after handoff and
  archival; no containers, services, ports, dependencies, or caches were left
  behind.
