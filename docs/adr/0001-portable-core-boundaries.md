# ADR 0001: Portable internal boundaries in one Buzz Agent Bridge package

Status: historical initial decision. The module/policy boundaries remain;
[ADR 0002](0002-independent-dot-connector.md) supersedes the single-distribution
decision after an explicit independent-consumption requirement.
Date: 2026-10-22.
Baseline: `694642933a791c20d9d85254cd9b61afc3ae5be8`.

## Context

Buzz Agent Bridge connects an existing ChatGPT Dot to Buzz. ACP intake, remote
execution, webhook acceptance and verified message delivery are separate events.
The encrypted broker owns generation fencing and the sole publisher. The provider
owns registration and wake-up. It must not own the Buzz signing key or publish
responses independently.

The existing provider protocol is genuine: `FixtureProvider` exercises a second
registration/wake implementation through the common jobs. It does not prove a
generic messaging core. `Broker.source` still validates Nostr signatures, kind 9,
owner, channel tags and activation, and imports NIP-10 logic from `events.py`.
That module also contains MCP Events and Buzz payload serialization. HTTP dispatch
imports its protocol version, while `transports.py` contains both Dot wake-up and
Buzz CLI publication. Configuration, tools and durable source records retain Buzz
concepts. Moving files alone cannot make these contracts transport-neutral.

There is one working provider and one messaging platform. No supported Grok or
Meta adapter, independent neutral connector, or new conversation product has been
established. “Dots Connector” is not a confirmed product name. Existing Dot
context must stay with that same Dot; no model session or memory copy is needed.

## Options considered

| Option | Benefits | Costs and risks | Decision |
| --- | --- | --- | --- |
| One repository, one distribution, explicit internal modules | Atomic source/provider/host changes; one installation; current tests exercise the composition; preserves provenance and compatibility cheaply. | Internal contracts need enforcement; package dependencies remain shared. | Use now. |
| One repository with independent distributions | Separate dependency sets and potential reusable core releases. | Multiple build roots and versions, release-order and compatibility matrix, unclear public API before a second consumer. | Defer until real independent consumption justifies it. |
| Independent repositories/packages | Independent ownership and releases, smaller downstream dependency surface. | Cross-repository changes, pinned dependency and provenance management, duplicated CI and unstable contracts. | Defer; require a stable contract plus a second working consumer. |
| Git submodule | Pins source commits and can support coordinated source development. | Recursive checkout, separate provenance and release workflows; does not install a Python dependency or test compatibility by itself. | Reject as the default installation mechanism. |

## Decision

Keep the public MIT repository, package `buzz-agent-bridge`, runtime name Buzz
Agent Bridge, and one product version. Preserve public history/tags and Alita App
publication provenance. Do not publish private history or operational material.

Extract the smallest useful seam: an explicit verified-source policy consumed by
the durable broker, with the current signature, owner, channel, freshness and
thread checks implemented by a Buzz adapter. Keep the normalized source and
persisted job representations unchanged for this increment. A synthetic alternate
source implementation must demonstrate that the lifecycle can execute without
Nostr parsing; it is contract evidence, not a newly supported integration.

Maintain these boundaries:

| Boundary | Owns | Must not own |
| --- | --- | --- |
| Durable contracts and lifecycle | Job identity, authorization checkpoints, atomic outbox, generation fences, state/uncertainty transitions and effect serialization. | Buzz envelope/tag parsing, callback signing, CLI invocation or secret acquisition. |
| Buzz adapter | Signed source/readback verification, owner/channel/time/thread policy, relay reads, ACP framing and official CLI publisher. | Provider conversation creation, provider credentials or bypass of broker fences. |
| ChatGPT Dot provider | MCP Events registration, subscription/wake serialization and authenticated completion surface using existing wire contracts. | Buzz key, direct publication, duplicate retry loop or claims that HTTP ACK proves execution. |
| Host composition | Explicit reviewed adapters, encrypted stores, process locks, loopback server, injected credentials and configured limits. | Automatic permissions, endpoint provisioning, credential copying or hidden deployment state. |
| Setup | New public configuration files, scoped receiver configuration and honest offline diagnostics. | Editing a running agent, restarting services, provisioning keys or authenticating providers. |

The separation is an internal implementation boundary. Existing five `buzz_*`
tools, `buzz.message.created`, `chatgpt-dot`, `dot_job_id`, configuration fields,
request IDs, schema-2 records and scope binding remain protected contracts.
Re-export moved public symbols where necessary, including a single `NotReady`
class identity. An old-compatible constructor may compose Buzz defaults outside
the neutral lifecycle layer. Do not add a dynamic module loader.

Strengthen the response receipt gate before broadening composition: a response
requires accepted status, a valid event ID and explicit signed-readback evidence.
The trusted Buzz publisher performs actual signature and exact-content checks.
A flag from arbitrary untrusted plugin code is not proof. Wake acknowledgements
remain separate from execution and delivery; uncertain effects are not retried.

Do not split every generic-looking utility for aesthetic symmetry. Extract only
what removes a demonstrated dependency across the chosen boundary. In particular,
splitting storage, crypto or every HTTP helper into a connector SDK is not required
for this increment. Unix process/lease assumptions and Buzz-shaped compatibility
records remain documented limitations.

## Evidence required

- Existing synthetic tests continue to prove owner/channel/signature/time checks,
  admission atomicity, duplicate suppression, cancellation, generation fencing,
  state encryption, crash recovery and inherited publisher lease.
- New source-policy substitution tests exercise lifecycle behavior without Nostr
  parsing, while the Buzz policy rejects all existing invalid source cases.
- A transport receipt containing only acceptance and an event ID cannot mark a
  reply delivered. Verified direct and nested synthetic replies still can.
- Compatibility tests preserve tools/events, request IDs, state reopening and
  scope binding. No live fixture or credential copy is permitted.
- Import direction checks show that the contract/lifecycle layer does not import
  Buzz or provider implementations; executable behavior remains the main proof.
- Exact official Buzz parser and OpenAI plugin/event documentation support the
  advertised protocol. Missing source/account acceptance stays visibly pending.
- Wheel/sdist inspection, clean install and secret scanning validate the actual
  artifact. Alita remote attribution and verification validate publication.

The finite units, evidence matrix, release gates and completion ledger are in the
[execution plan](../plans/portable-bridge.md). No local test authorizes modifying a
mini/live deployment or proves that a new user's provider account can connect.

## Compatibility and release consequences

Use strict SemVer, including during `0.x`: a breaking change increments the major
version; a compatible feature increments minor; a compatible fix increments patch.
All unit work markers, including documentation, use immutable annotated tags
`work/issue-<number>/<unit>-r<N>` as required by the registered commit skill.
Only releases use `vMAJOR.MINOR.PATCH`. Keep existing history and tags intact.
The source seam is internal rather than a supported public SDK. The earlier
`0.2.1` candidate covered only a compatible refactor and receipt fix. Subsequent
official thread-resolution evidence changes that classification to **1.0.0**:
normalized source ancestry and existing durable-job interpretation change under
the user's strict semantic compatibility policy. This major increment does not
claim a security audit or externally verified account readiness.
Version-gated IPC and handoff must remain explicit; a compatible refactor does not
establish mixed-version runtime support. New package boundaries must not require
an unannounced state migration or replacement Dot connection.

### Thread normalization correction and durable-state handling

Verified against desktop `0.5.28`, revision
`f87c10895ea35a9a2cea629fef1d7532a3fecbc5`,
[ThreadMarkers.resolve](https://github.com/block/buzz/blob/f87c10895ea35a9a2cea629fef1d7532a3fecbc5/crates/buzz-core/src/nip10.rs)
uses the root marker when root and reply coexist, the reply target when only a
reply marker exists, and the source event itself for root-only or no markers.
[SDK thread_tags](https://github.com/block/buzz/blob/f87c10895ea35a9a2cea629fef1d7532a3fecbc5/crates/buzz-sdk/src/builders.rs)
emits reply-only for a direct reply. The bridge's existing root-only ancestry and
rejection of reply-only input are incorrect. Preserve stricter duplicate/malformed
reference rejection as a documented local admission policy.

Correct the derived value at the Buzz source adapter. Keep schema 2 and old
snapshots intact. For response preparation and explicit reconciliation, pass a
job copy containing freshly reverified normalized source; check stable source
fields agree with the authenticated stored snapshot. Only derived ancestry may
differ. The existing verification call's return value must not be discarded.
This avoids a bulk migration requiring relay access at startup and prevents
stale cached ancestry from defeating correct signed receipt verification.

Pending intents keep their identities and may use corrected verified ancestry.
Uncertain intents never retry; only explicit signed receipt reconciliation can
resolve them. Historical delivered/cancelled/quarantined states remain historical.
New direct-reply admissions and old root-only pending/uncertain fixtures need
regression coverage. Missing or inconsistent source proof blocks the action.

Require coordinated stopped host/frontend upgrades; mixed-version operation is
not supported. Old code cannot safely process newly admitted direct-reply jobs,
so do not promise downgrade compatibility merely because the database opens.
Restored snapshots require quarantine and cannot reverse external publication.
The same Dot, identity, principal and scope remain unchanged.

This decision reduces coupling and makes the current product reviewable without
claiming a standalone reusable connector. Revisit independent packages only after
a second working consumer requires separate installation/versioning and the shared
API has executable compatibility, licensing and release evidence. Revisit protocol
details when official upstream evidence changes; do not generalize from speculation.
