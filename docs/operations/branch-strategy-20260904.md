# Branch Strategy and Historical Inventory

Date: 2026-09-04 UTC
Owner: Codex
Review input: Fable 5.1 branch assessment; document integrated by Codex

## Decision

Keep `integration/v2` as the canonical development and release-validation
branch for the current product push. Do not merge every old branch into it,
rename it to `main`, or force-reset either branch as part of this audit.

`main` is the original v2 fork point and is now an archival ancestor. The
current naming is technical debt, but changing the default branch is a
separate migration with CI, deployment, release-documentation, and clone
compatibility consequences. Revisit that migration only after the recorded
whole-repository audits and the open physical release gates are closed.

## Evidence at `f0b193a2`

| Relationship | Verified fact |
| --- | --- |
| `main` -> `integration/v2` | Merge base is `0f696b88`; `integration/v2` is 1,781 commits ahead and 0 behind. |
| MAP1 and old integration | At merge base `a0c0fca8`, MAP1 had 287 unique commits and old `integration/v2` had 46. |
| History-only merge | `79ee08cd` has parents MAP1 `d26feaba` and old integration `b5e17d31`; its tree is the MAP1 tree. |
| Reconciliation merge | `1775d87a` has first parent old integration `b5e17d31` and second parent reconciliation/MAP1 line `a331281a`. Its product tree is MAP1, with the intentional authority, test, and operations additions recorded in the reconciliation document. |
| Current tip at inventory | `integration/v2` pointed to `f0b193a2`, which recorded the Cloud audit start after the reconciliation; the later `6593b95e` commit adds this policy record and the corrected parent-order wording only. |

The parent order matters for first-parent release history. The normal merge
preserves both histories; it does not mean that every old branch's tree should
be replayed.

## Ref inventory

The following counts are a snapshot of `refs/remotes/origin/*` at `f0b193a2`,
excluding `origin/HEAD`. “Reachable” means the branch tip is already an
ancestor of `integration/v2`; it does not claim that every intermediate change
was semantically useful.

| Namespace | Refs | Reachable tips | Not reachable | Default treatment |
| --- | ---: | ---: | ---: | --- |
| `codex/*` | 31 | 3 | 28 | Review by issue/owner; port selected commits only. |
| `superpowers/*` | 202 | 192 | 10 | Treat as short-lived historical feature refs; do not bulk-merge. |
| `evidence/*` | 27 | 0 | 27 | Preserve until the whole-repository reports and artifact hashes are archived; never merge as product code. |
| `feature/*` | 2 | 0 | 2 | Review individually; archive or port a tested change. |
| `fix/*` | 3 | 3 | 0 | Already represented in the canonical history; candidates for post-audit ref cleanup. |
| `integration/*` | 2 | 2 | 0 | Reconciliation refs are historical; expire after the documented review window. |
| `main` | 1 | 1 | 0 | Keep as the tagged historical fork point until a separate rename project. |

The ten currently unmerged `superpowers/*` refs are:

```text
superpowers/fix-offline-driver-carry
superpowers/hole-render-frame
superpowers/multi-user-redesign-spec
superpowers/spec-maint
superpowers/topo-tee-notch
superpowers/unified-tri-surface-spec
superpowers/watch-hero-distances
superpowers/watch-holeview-redesign
superpowers/watch-render-all
superpowers/watch-shell-combined
```

These names are a review queue, not an approval to merge. The open-PR state,
release-tag dependencies, and owner decision must be checked again immediately
before any ref is archived.

At the inventory time, the only open PRs for those ten refs were:

| PR | Head | Decision needed |
| ---: | --- | --- |
| #176 | `superpowers/multi-user-redesign-spec` | Owner decides whether the design is still in scope. |
| #218 | `superpowers/watch-holeview-redesign` | Keep as design preview or port a current, tested slice. |
| #219 | `superpowers/fix-offline-driver-carry` | Rebase and test only if the current caddie contract still needs it. |
| #291 | `superpowers/watch-hero-distances` | Compare with the MAP1 watch surface before any port. |

The other six refs in the list have no open PR at this snapshot (some have
closed historical PRs). This is evidence for cleanup planning, not permission
to delete them during either whole-repository audit.

GitHub reports both `integration/v2` and `main` as unprotected at this snapshot.
Adding required checks and a protected environment is a separate owner-approved
repository-settings change; it is not silently folded into branch deletion or a
future `main` rename.

## What a branch is for

* A `feature/<issue>-<slug>` or `fix/<issue>-<slug>` branch isolates one
  change while the canonical line remains releasable. It should end in a PR,
  required CI, and deletion after merge.
* A `release/<version>` branch is appropriate only for a short stabilization
  or rollback window. The immutable release tag, not a moving branch, is the
  long-term release anchor.
* An `evidence/<run>-<purpose>` ref records a test or artifact boundary. It is
  not a product integration lane and must not be merged merely to make the
  graph look tidy.
* A `reconcile/<date>` branch is a one-time ancestry operation. It gets an
  expiry date and is closed only after the target merge, both audit handoffs,
  and an owner-approved cleanup decision.

Branches are useful when work needs isolation, parallel review, a release
freeze, or a recoverable experiment. They are unnecessary for every small edit;
the cost is review drift, stale bases, duplicate CI, and uncertainty about
which tree is releasable.

## Executed policy

1. Keep `integration/v2@6593b95e` as the single canonical line (the
   `f0b193a2` reference below is historical inventory context).
2. Keep the MAP1 and old integration ancestry through the normal merge
   `1775d87a`; do not replay the 46 old integration-only commits.
3. Keep old refs, PRs, release tags, and evidence refs through both audit
   handoffs and the owner cleanup decision.
4. Port a branch only when a current product owner selects a concrete change;
   rebase or cherry-pick it onto `integration/v2`, add focused tests, and run
   the required CI on the resulting commit.
5. Do not upload, deploy, or synchronize as a side effect of branch cleanup.

## Post-audit cleanup gate

After both whole-repository reports and their hashes are archived, cleanup may
proceed only in a separate owner-approved allow-listed operation:

1. Verify the ref tip is reachable (or create an archival tag/bundle for every
   unique commit), has no open PR, and is not a release/deployment anchor.
2. Delete only merged, owner-approved short-lived refs. Preserve evidence and
   unmerged product refs until their owner decision is recorded.
3. Record the exact deleted-ref list, retained tags, and bundle/tag hashes in a
   dated cleanup document. Never use a global prune or an unbounded ref glob.

## Optional `main` migration (later project)

Renaming the canonical line can make the repository conventional, but the
benefit is mostly naming clarity. The costs include changing the GitHub default
branch, PR bases, workflow branch filters, protected environments, deployment
scripts, release provenance, local clones, and external links. If it is later
approved, freeze the release, tag the exact current commit, update every
consumer and protection rule, run source/native/release CI on the new default,
then retain an immutable archive ref for `integration/v2`. Until those checks
are planned and owned, the current arrangement is safer and internally
consistent.
