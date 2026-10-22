# Personal commit skill distribution

This directory is a standalone install source, not an active repository skill.
The `commit/` directory contains the generic SKILL.md. It does not depend on Buzz,
Alita, this repository's release policy path, or the MIT license. Each repository
supplies its own policy. Preserve this source and manifest for later reinstalls.

Actual user-level installation on mini is performed by the parent task. No cloud
user-level installation, account-wide synchronization, or all-device installation
is claimed. Copying files does not by itself prove the host discovered the skill.

## Identify and inspect the consuming machine

The [official skills guide](https://learn.chatgpt.com/docs/build-skills) identifies
`$HOME/.agents/skills` as the current Codex user scope. Repository `.agents/skills`
directories from the working directory up to the repo root are also scanned.
Duplicate names can both appear; do not rely on precedence or merging. Confirm the
actual mini host/version, configured skill locations and existing user edits first.
Older hosts or explicit configuration may expose additional locations; inspect them
instead of installing another copy blindly.

Inspect the current user's skill list, relevant `skills.config` entries, user root,
repository discovery roots, and any active legacy/admin/plugin roots. Include
symlinked skills and folders with a different folder name but `name: commit`.
The helper only checks roots explicitly supplied; it does not discover every host's
plugin/system configuration or edit that configuration for you.

## Check, then install

Run from this extracted distribution, substituting the confirmed user root and all
applicable additional discovery roots. Paths below are placeholders, not defaults.

```sh
python3 install.py --skills-root /absolute/user/skills \
  --check-root /absolute/repository/.agents/skills \
  --check-root /absolute/other/active/skills
```

The default is read-only. It verifies `manifest.json`, checks duplicate names and
reports the intended destination. If conflicts exist, it exits without writing.
Do not overwrite an existing personal skill or delete user changes to make this
pass. Compare contents, preserve a backup outside active discovery roots, and have
the installing parent reconcile or disable the explicitly identified old version.
A backup still inside `.agents/skills` can itself remain discoverable.

After resolving conflicts and confirming the authorized target, repeat the same
command with `--apply`. The helper refuses overwrites and symlink payloads. An
identical installed directory is reused; a different or partially installed target
blocks. It never installs dependencies, edits host configuration or writes GitHub.

```sh
python3 install.py --skills-root /absolute/user/skills \
  --check-root /absolute/repository/.agents/skills \
  --check-root /absolute/other/active/skills --apply
```

## Verify discovery and reinstall safely

1. Repeat the read-only check and compare installed file hashes to the manifest.
2. Refresh/restart the actual consuming host as needed. Open its skills selector
   and verify exactly one active `commit`, with the expected user-level source.
3. From an unrelated test repository, invoke `$commit` for a dry-run docs-only
   commit plan. Verify that it reads that repository's policy and does not require
   Buzz paths, Alita identity or this repository. Then check a breaking 0.x change,
   conflicting work tag and uncertain publication result without making writes.
4. Record host, resolved source path, checksums and selector/dry-run outcome in the
   parent task's private installation record. Do not put personal paths in Git.
5. For reinstall, reuse this source plus manifest, recheck conflicts, and compare
   any installed user edits before replacement. Do not force an automatic upgrade.

The repository patch removes its generated `.agents/skills/commit` copy and retains
this non-discovered source. When applying the patch to a different checkout,
inspect any independently modified repository copy before removing it. Global
Skills-page synchronization and installation on other devices are separate actions.
