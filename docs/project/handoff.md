# Maintainer publication checklist

The review candidate targets 1.0.0 with the breaking thread-routing correction
explained in [migration](../releases/migration-1.0.md). Preserve existing history,
MIT licensing, public compatibility contracts and operator state.

1. Read [status](status.md), [validation](validation.md) and current remote state.
   Reuse Issues #1–#7 and the existing organization Project.
2. Verify the reviewed source inventory and secret scan. Exclude deployment files,
   credentials, private identifiers, conversations and operational ledgers.
3. Compare the current base before creating a review branch. If it changed,
   reconcile rather than resetting or force-pushing.
4. Use Conventional Commits and the approved App identity. Confirm the remote
   author, committer, signature, parent and tree; local author text is not proof.
5. Open or reuse the draft PR. Link the real issues without claiming incomplete
   acceptance criteria are fixed. Run CI against the current head.
6. Keep actual live provider/relay acceptance distinct from mock tests, the
   installed ACP help contract and the isolated official Rust loader harness.
7. Merge and publish only after the release gates and authorization are satisfied.
   Product tags and immutable work tags have different meanings; never move them.
8. After an uncertain external write, inspect remote state before retrying.

The personal commit skill under `contrib/commit-skill` is a separately installable
source, not an automatically active repository skill. Follow its conflict checks
and preserve existing user customizations. The project requirements in AGENTS.md
and the release policy apply without personal skill installation.
