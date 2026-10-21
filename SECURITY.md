# Security

This is an early-stage integration, not an independently audited security product.
Use a private test channel and a narrowly scoped managed identity first.

## Trust model

- The Unix account running the host is trusted. Same-UID IPC is not protection
  from malware running as that same user.
- The bridge authorizes one configured owner and channel, and re-fetches signed
  source events. Forwarded message text is untrusted content, not authority to
  expand permissions or disclose secrets.
- The managed Buzz key and owner attestation are handled in memory. Buzz itself
  owns persistent key storage; its platform fallback policy still applies.
- The storage key and MCP bearer token are supplied over an anonymous pipe by an
  approved launcher. No credential generation, vault setup, token issuance, public
  listener, or network-policy change is performed by this package.
- The optional macOS reader accepts only a `buzz-agent-bridge.<deployment>` service
  and the fixed `storage_key` / `mcp_token` accounts in the current default Keychain.
  It requests one exact generic-password match per account. It never queries Buzz's
  signing-key collection, enumerates other items, creates/unlocks stores, or changes
  ACLs. Locked, missing, denied, or malformed items stop startup without fallback.
  A process-local compatibility guard suppresses optional authentication UI during
  these reads and restores the previous setting; it does not weaken persistent
  authentication policy. See the adapter's [limits](docs/macos-keychain.md).
- The MCP listener is loopback-only. The operator owns TLS/tunnel configuration,
  connection authentication, and access revocation. Do not put bearer tokens in
  URLs, repository files, command arguments, or logs.
- Callback delivery permits public HTTPS destinations, pins a validated IP, rejects
  private addresses and redirects, and limits payload size and connection time.

## Data handling

Channel content and subscription secrets are encrypted at rest in owner-only state
files. Encryption does not protect a running host from a compromised account or
from an attacker who also has the storage key. Back up keys and encrypted state
separately. Keep crash dumps, terminal captures, and operating-system backups in
mind; clearing Python references is not a guarantee of secure memory erasure.

No telemetry is included. Do not share real state directories, config files,
identities, callback URLs, source messages, or logs in bug reports. Tests use
explicit synthetic fixtures.

## Delivery and cancellation limits

The broker does not promise exactly-once effects across an unobservable network
failure. It makes one attempt, records uncertainty, and requires signed evidence
before reconciliation. Do not manually repeat an uncertain request.

Local cancellation prevents later accepted effects where possible. It does not
prove that a remote assistant stopped running. The ledger is bounded; long-term
retention and arbitrary rollback detection are not solved by this release.

## Reporting

If GitHub private vulnerability reporting is enabled for this repository, use
**Security → Report a vulnerability**. Otherwise contact the repository maintainers
to arrange a private channel before sending exploit details or sensitive data.
Do not post credentials or production conversation content in public issues.

If a credential is exposed, revoke it at its issuer and replace it through your
approved secret workflow. Deleting the text from Git does not restore its secrecy.
