# Release and work-unit policy

Track each unit in a real GitHub Issue in the organization's `buzz-agent-bridge`
Project. Search by stable unit marker before creating it. Link the issue, review
PR, commit, acceptance evidence and immutable tag in both directions. Local issue
drafts and pending IDs are not GitHub records. Preserve history and existing tags.

Use Conventional Commits. An incompatible CLI/config, tool/event/schema, identity,
state, documented Python extension or delivery/recovery behavior requires MAJOR,
even before 1.0. A compatible `feat` requires MINOR; a compatible `fix` requires
PATCH. Choose the highest required increment in the release. Runtime refactoring
or build changes released on their own require at least PATCH. Docs/test/CI-only
work does not bump the product. Every break needs migration and rollback limits.

Use annotated `work/issue-<number>/<unit>-r<N>` tags for completed units, including
documentation. Record real issue/PR URLs, target commit, acceptance evidence and
version impact in the annotation. If an existing tag has the expected target,
reuse it. If it differs, report the conflict; never retarget it. Create a new unit
revision only for newly verified work. Work tags are not product releases.

Use `vMAJOR.MINOR.PATCH` only for approved product releases; prereleases must have
an explicit suffix. Runtime and package metadata must agree with the tag. Verify
the remote tag, Release target, commit attribution and signature. A GitHub Release
does not imply a registry publication. No PyPI publishing is included here.

Large replacements use a review branch and draft PR. Before merging, inspect the
complete diff, compatibility evidence, clean installed artifacts, secret scan and
remaining account/platform acceptance. Use only the authorized Alita GitHub App
path. Do not copy keys, spoof the App, use a human credential as a substitute,
force-push, purge history, delete the repository or alter old tags.

These project requirements apply independently of any installed personal skill.
The shared commit workflow must discover this repository's policy; it must not
hardcode this project's identity, paths or license into other projects.
