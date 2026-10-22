# Architecture

See [components and deployment boundaries](components.md) for the included MCP
server, required external services, and options for a future reusable package.

## Boundaries

The official `buzz-acp` process is the sole incoming receiver. A thin ACP stdio
frontend extracts source IDs from current Buzz event envelopes; it never trusts
the prompt body as source evidence. The frontend submits admission requests to a
same-user Unix socket and ends the ACP interaction after durable acceptance.

The separate host re-fetches each event, verifies its Nostr ID and Schnorr
signature, and checks the configured owner, channel, and activation window. It
commits jobs and outbox intents together in an encrypted SQLite transaction.

The provider adapter owns remote registration and wake-up serialization. ChatGPT
Dot uses MCP Events. The provider does not acquire the managed Buzz key or publish
to Buzz. Remote completion is recorded through authenticated job tools, and the
host's sole CLI publisher verifies the exact signed relay result.

## Job contract

All tools require the connection's authenticated principal and fixed channel.
Remote code must use IDs and generation values returned by the broker.

| Tool | Meaning |
| --- | --- |
| `buzz_jobs_pending` | Fetch eligible work and re-verified source information |
| `buzz_job_status` | Inspect execution, dispatch, delivery, and reply event ID |
| `buzz_job_start` | Record the existing remote execution identifier |
| `buzz_job_complete` | Persist one completion and queue a response, if applicable |
| `buzz_job_cancel` | Fence later completion/publication by advancing generation |

Inspect `tools.py` for the authoritative JSON schemas. `dot_job_id` remains the
wire name for the remote execution identifier for compatibility; it is not a new
model or a command to launch a conversation.

Separate identifiers exist for the source Nostr event, ACP session, JSON-RPC
request, durable job, generation, remote execution, and published reply event.
Do not substitute one for another.

## External effects and uncertainty

Every external attempt has a persisted outbox intent. The process lease is inherited
by the CLI child so a surviving publisher prevents a replacement broker from
starting. Interrupted `sending` work is recovered as `uncertain`, not retried.

An HTTP acknowledgement confirms wake-up acceptance only. A CLI acknowledgement
alone also does not mark delivery complete: the host re-fetches the reply and
checks its signature, agent public key, body, kind, channel, and thread tags.
The library's reconciliation path accepts explicit signed receipt evidence and
performs no send. An operator-facing reconciliation CLI remains future work.

Cancellation before admission can prevent intake. Cancellation after admission
fences future effects but cannot assert that a remote provider has stopped. The
current ChatGPT adapter has no remote execution-stop API.

## State and lifecycle

The state directory is `0700`, files and sockets `0600`, and Unix peers must have
the same UID. Jobs and subscriptions use authenticated encryption with an injected
key. SQLite uses synchronous commits. Provider, principal, owner, channel, and
activation are scoped; changing the provider requires separate state.

The host and ACP frontend have independent lifetimes. Model discovery needs no
secret or running host. Managed startup transfers the exact expected identity
and its verified owner attestation into host memory, then executes the frontend
with a clean environment. The frontend cannot publish directly.

Backups do not roll back external effects. Operators must explicitly quarantine
restored work; arbitrary rollback cannot be detected without an external monotonic
authority. Capacity is bounded at 10,000 jobs until a reviewed retention policy
exists. See [security](../SECURITY.md).

## Internal source and provider boundaries

`core/broker.py` consumes `SourcePolicy.read` and an immutable `VerifiedSource`.
The trusted `adapters/buzz/source.py` policy re-fetches signed evidence and enforces
owner, channel, kind, time and thread interpretation. The lifecycle rechecks
authorization and stable source fields. `adapters/buzz/publisher.py` alone sends
via the official CLI and checks the exact signed receipt. A signed-readback flag
is a contract between reviewed local components, never proof from remote content.

`adapters/chatgpt` owns registration and signed wake-up; it never obtains the Buzz
key or starts another Dot. The callback verification cache and signing overlap
last at most five minutes. Expired subscriptions cannot wake jobs. HTTP receipt
remains acknowledgement only. Legacy module paths are forwarding facades.

Schema 2, job IDs and original source snapshots remain stable. Current verified
source routing is used in ephemeral publication/reconciliation plans. See the
[1.0 migration](releases/migration-1.0.md) for the deliberate major change to
reply-only and root-only source semantics.
