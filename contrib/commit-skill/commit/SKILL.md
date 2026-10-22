---
name: commit
description: Prepare and execute Conventional Commits linked to GitHub Issues, assess compatibility and SemVer, and record immutable completion tags. Use when the user invokes /commit or asks to commit, finish a tracked unit, tag, or prepare a release.
---

# Commit and complete a GitHub work unit

1. Discover the current repository's instructions, plan, release policy, and linked issue.
   Read `AGENTS.md`, `CONTRIBUTING.md`, and relevant release docs when present.
   Follow explicit repository policy and current user authorization; do not assume
   another project's paths, organization, product, version, language, or bot identity.
   Inspect `git status`, staged and unstaged diffs, recent commits, branches, tags,
   and remote issue/PR/release state. Preserve unrelated user changes.
2. Reuse the matching GitHub issue by its stable work-unit marker or URL. Before
   creating anything, search open and closed issues and the named organization
   Project. Match owner, repository, title, and marker; do not guess an issue number.
   Keep a local title/body/acceptance draft if the approved publishing path is unavailable.
   Default to GitHub Issues for this workflow. If the repository explicitly uses
   another tracker, honor that policy rather than silently migrating it.
3. Review the actual diff and compatibility contract. Run the relevant tests and
   required package/secret checks. Record passes, skips, and unresolved gates in
   the issue and repository progress record. A note is not acceptance evidence.
4. Stage only the files for this unit. Verify author, committer, signing method,
   and remote actor against the approved publishing identity. Never copy keys,
   invent an identity, spoof an App author, or change Git identity automatically.
5. Honor authorization already given in this session. Ask only for a genuinely
   missing destructive action or publishing identity approval, after preparing
   a concrete diff and message. Use a branch and draft PR for a large replacement.
6. Commit with a message file or quoted heredoc, preserving actual newlines.
   Link the real issue with `Refs: #123`; use `Fixes: #123` in the integrating PR
   only when its completion criteria are met. Never substitute a draft work ID for
   a real GitHub issue number.
7. At verified unit completion, create the immutable annotated work tag described
   below. Re-read remote refs before creating it. If a tag exists at the expected
   commit, reuse it; if it differs, stop that operation and report the conflict.
   Never move/delete an existing tag, force-push, or purge repository history.
8. After an authorized push, verify remote commit attribution/signature, PR head,
   issue/Project linkage, tag target, and release target. Report exact IDs/URLs.
   Keep any incomplete gate pending; do not claim remote success from local output.

## Message format

```text
<type>(<scope>): <imperative description>

Optional explanation of the behavior and relevant verification.

Refs: #123
```

Use a colon followed by a space and a blank line before body/footer. Scope is
optional. Use `feat` for a new capability, `fix` for a bug correction, and the most
accurate of `docs`, `style`, `refactor`, `perf`, `test`, `build`, `ci`, or `chore`
otherwise. Follow the repository's language policy; use imperative English or
short Korean phrases with normal spacing, as appropriate to the requested language.
Use `!` and a `BREAKING CHANGE:` footer for incompatible behavior; describe the old
and new contracts and link the migration. Other footer tokens use hyphens.

Never add `Co-Authored-By` automatically. Add it only for an actual contributor
whose identity/address and attribution consent are verified. Do not invent a model
email or use a person's identity simply because their account provides access.

## Compatibility and versions

Discover the repository's compatibility and release policy; no particular policy
file is required to use this skill. If none exists, apply the defaults below and
record the decision in the tracked work. Assess public APIs/CLI/config, wire
formats, documented extension points, stored data and identifiers, authentication,
authorization, and operational behavior that existing consumers rely on.

- Any incompatible change requires MAJOR, including `0.x -> 1.0.0`. Do not use the
  pre-1.0 allowance to hide a break. Supply migration, state/rollback constraints,
  and negative as well as compatibility tests before calling the unit complete.
- Backward-compatible `feat` requires MINOR; compatible `fix` requires PATCH.
  Choose the highest required bump across the release. A security correction that
  restores an already documented fail-closed contract is a fix; document rejected
  previously invalid inputs. Do not misclassify a new restriction as a mere fix.
- Docs/test/CI-only units do not bump the product version. Use a work tag.
  Runtime refactoring/build changes released on their own require at least PATCH.
- Work tags use `work/issue-<number>/<unit>-r<N>`. The annotation records issue,
  PR, commit, acceptance evidence, and product version impact. Create a new r<N>
  for later completed work; never retarget an earlier annotation.
- Product release tags use `vMAJOR.MINOR.PATCH` (or an explicit prerelease suffix).
  Match package metadata and runtime version. A work tag is not a product release.
  Publish a GitHub Release only at the approved, verified release commit. Registry
  publishing is a separate action. Do not release merely to mark blocked work done.

## Interrupted or blocked work

Keep a local work manifest with planned commit message, issue draft, checks, and
pending tags when the approved publishing path is unavailable. Do not mint false
issue numbers or claim a local tag is on GitHub. On resumption, reconcile remote
state before retrying a write; uncertain writes require readback first. Record
whether the action was denied, pending, or has an uncertain outcome.

Never stage credentials, personal deployment files, state databases, callback
URLs, token-bearing logs, or unrelated changes. Preserve the project's actual license, attribution
and approved publishing provenance; do not impose another project's choices. Keep a local patch/bundle for authorized
publication when needed; scan that exact deliverable before transfer.
