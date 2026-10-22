# Upgrade from 0.2.0 to 1.0.0

1.0.0 changes incoming Buzz thread interpretation to match the official Buzz 0.5.28
parser. This affects routing and the derived `source.thread_root` shown by job
tools, so the project uses a major version even though the old behavior was a bug.

| Source markers | 0.2.0 | 1.0.0 |
| --- | --- | --- |
| Neither | Source itself | Source itself |
| `reply` only | Rejected | Reply target is the thread root |
| `root` and `reply` | Explicit root | Explicit root |
| `root` only | Explicit root | Source itself; top-level |

Malformed or repeated markers remain rejected by the bridge. This is deliberately
stricter than Buzz's last-valid-marker policy. The publisher still verifies exact
signed channel, author, content and direct/nested reply tags. An acceptance result
without explicit signed readback remains uncertain, even with an event ID.

The five MCP tools, event name, subscription IDs, `chatgpt-dot` model, `dot_job_id`,
configuration keys, request IDs and schema-2 encrypted records remain unchanged.
Existing import paths are compatibility facades. No new Dot, new conversation,
copied memory, replacement key, state rewrite or connection recreation is required.
MCP refresh adds a bounded callback verification cache and five-minute dual signing
window when a subscription changes its signing secret; old subscription records
are accepted and reverified on refresh. Secrets stay in the encrypted store.

## Coordinated cutover

1. Record the old package version and stop the managed agent, then its host. Ensure
   no CLI child still holds the publisher lease. Never run two publishers.
2. Back up the encrypted state while stopped; retain its key separately in the
   approved secret manager. Do not share the database or configuration.
3. Install the reviewed 1.0.0 artifact in a separate virtual environment. Run
   `--version`, `harness`, `check-config` and `doctor` using the same public scope.
   Doctor is offline and cannot validate credentials or provider authorization.
4. Point the host and managed frontend to the same installed version. IPC and
   handoff require exact version agreement; mixed-version rolling upgrades fail.
5. Start the host, then the managed agent. Keep the same owner, channel, principal,
   provider, Dot and encrypted state. Verify one newly authorized test message.

Historical source snapshots and delivered records are preserved. For a pending
publication or explicit uncertain-delivery reconciliation, 1.0.0 re-fetches the
signed source, requires stable ID/author/channel/body/time, and derives fresh
routing for that attempt only. If evidence is unavailable or differs, it fails
closed. Uncertain jobs are never automatically resent. A receipt for an old wrong
thread does not become correct because a new version can parse its source.

## Recovery and rollback limits

- A normal restart reopens the current state; interrupted sends become uncertain.
- For an uncertain reply, inspect the relay and call the existing reviewed
  `Broker.reconcile_delivery` embedding API with the exact receipt. It verifies
  evidence and never sends. There is no operator reconciliation CLI in this release.
- Restoring a backup can hide external effects. The embedding `restored=True`
  option quarantines unfinished work; the host CLI does not expose it. Do not
  replace a live state directory with a backup and start the normal host.
- After new direct-reply jobs are admitted, 0.2.0 cannot safely interpret all new
  work. Do not downgrade or replay old source events. Stop both processes and
  obtain a reviewed recovery plan based on external receipts and current state.
- Changing provider or scope requires separate state. Copying a database cannot
  change its identity binding or revoke an external delivery.

This repository's tests use synthetic sources and keys. No existing deployment
was upgraded as part of the implementation. Live cutover and a real account round
trip remain explicit operator acceptance steps.
