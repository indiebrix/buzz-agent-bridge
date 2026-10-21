# Optional macOS Keychain source

This adapter reads the bridge's **storage encryption key** and **MCP bearer token**.
It is separate from the signing key that Buzz manages for its agent. 1Password,
environment injection, and direct-pipe launchers remain optional alternatives.

Implementation and mock tests are complete. Real Keychain item access, first-run
setup, and an external message round trip through this source are **not yet
validated**. Treat it as an experimental option until your deployment completes
an explicitly authorized acceptance check.

## Prepare the exact two items

Use your approved credential-provisioning process to place two generic-password
items in the current default file-based Keychain, normally the login Keychain.
Review that destination yourself; the adapter does not change your default store.
Use a dedicated service for each deployment:

| Attribute | Storage item | MCP item |
| --- | --- | --- |
| Service | `buzz-agent-bridge.my-dot` | `buzz-agent-bridge.my-dot` |
| Account | `storage_key` | `mcp_token` |
| Password value | 32 random bytes encoded as 64 lowercase hexadecimal characters | Your existing high-entropy MCP bearer token, at least 32 characters |

Replace `my-dot` with your deployment label using lowercase letters, numbers,
dots, or hyphens. The prefix and two account names are enforced in code. Empty
names, wildcards, `buzz-desktop`, and general-purpose secret collections are rejected.
Do not put a signing key or a JSON bundle of unrelated credentials in these items.

Keychain Access can manage generic-password items; use its secure UI or another
approved provisioner without exposing values in terminal arguments, shell history,
logs, or Git. Verify the actual service/account attributes. The bridge does not
create these items, generate new keys, grant access, or copy values from 1Password.
When migrating an existing encrypted ledger, retain the same storage key; making
a new key will not decrypt existing state. Provisioning or migration is a separate
operator action, not an automatic setup step.

## Launch explicitly

First validate your public configuration without reading any secrets:

```sh
.venv/bin/buzz-agent-bridge doctor --config /absolute/path/bridge.json
```

When the dedicated items and their existing access policy are ready, choose the
source for this launch:

```sh
.venv/bin/buzz-agent-bridge host-keychain --config /absolute/path/bridge.json \
  --service buzz-agent-bridge.my-dot
```

Only the service name appears in the command. The reader requests the two fixed
accounts, validates the values, and transfers them to one host child over an
anonymous pipe. Secret values are absent from the child's environment and arguments.
Start the managed agent in Buzz within 180 seconds as in the main installation guide.
Do not run this host alongside another publisher for the same identity.

## Failure behavior and recovery

- **Locked or unreadable default Keychain:** stop before reading item values.
  Unlock it yourself through the normal macOS interface if that is intended.
- **Missing item:** stop. Check the exact service, account, and default store.
  No search across other Keychains or unrelated services is attempted.
- **Access denied or an authentication prompt required:** stop without retrying,
  automatically approving, unlocking, or modifying ACLs. Review the requesting
  executable and item access policy through your normal administrative process;
  do not broadly allow every application as a troubleshooting shortcut.
- **Malformed value or partial read:** stop before starting the host. No value or
  raw native error is printed. There is no plaintext-file or environment fallback.
- **Unsupported OS/framework:** stop. Use the existing explicit environment/pipe
  interface instead. Native Windows and Linux store readers are not implemented.

Stopping this launcher/host does not remove or alter Keychain items. Returning to
an existing source means stopping this host first, preserving state and its key,
and explicitly launching with that source. The adapter never changes a live
deployment's secret source on its own.

## Scope and implementation limits

The reader uses Apple's `SecItemCopyMatching` with exact generic-password class,
service, account, one-result limit, non-synchronizing selection, and a search list
containing only the current default Keychain. It does not support the iCloud/Data
Protection Keychain or arbitrary Keychain paths in this release.

File-based Keychain compatibility uses Apple's deprecated `SecKeychainCopyDefault`,
status, and process-interaction APIs to bind the store, reject a locked state, and
prevent optional authentication UI. The previous process-interaction setting is
restored after both reads, including failures. No persistent security setting is
changed. These compatibility APIs may require future replacement; there is no
claim of compatibility with every future macOS version.

Tests cover scope rejection, exact query construction, missing/denied/locked
behavior, partial failures, fixed diagnostics, and environment-free pipe transfer.
They do not inspect a user's Keychain, create fixtures in it, or exercise real ACLs.
Python/native memory copies may exist while the launcher runs; clearing references
is not a secure-erasure guarantee.

References: [Apple's Keychain API overview](https://developer.apple.com/documentation/technotes/tn3137-on-mac-keychains),
[SecItemCopyMatching](https://developer.apple.com/documentation/security/secitemcopymatching(_:_:)),
and the installed Apple SDK declarations for `SecItem.h` and `SecKeychain.h`.
