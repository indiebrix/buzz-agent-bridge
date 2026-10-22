# Portable Buzz Agent Bridge execution plan

Status: planned with Astra before implementation; local implementation and validation
completed, remote/external acceptance pending. See [validation](../project/validation.md).
Planning baseline: public `main` at
`694642933a791c20d9d85254cd9b61afc3ae5be8`; working branch:
`refactor/portable-bridge`. Decision: [ADR 0001](../adr/0001-portable-core-boundaries.md).

## Outcome and limits

Make the existing Buzz Agent Bridge easier to install, inspect, and extend from
its public MIT repository, with a small executable boundary between durable work
and Buzz source validation. Keep one repository, distribution, and product name.
The work does not create a new assistant, copy Dot memory, or replace the existing
Dot conversation. “Dots Connector” is an unconfirmed name, not a product decision.

Do not modify a mini/live installation, replay its messages, copy credentials or
state, generate secrets, create public endpoints, grant privileges, add services,
or provision a provider. Use synthetic fixtures and temporary local state only.
Preserve public history and every existing tag. Do not import private history.
Prepare a reviewable branch and draft PR; report results before any replacement
of `main`. Publication must retain the authorized Alita GitHub App provenance.
Human GitHub authentication does not establish authorization to publish as Alita.

## What the code actually supports

| Area | Observed baseline | Consequence |
| --- | --- | --- |
| `providers.py` | `AgentProvider.bind` supplies registration and wake transports; only `chatgpt-dot` is selectable. | A real provider boundary already exists; do not invent speculative provider implementations. |
| `broker.py` | Durable states and generation fences coexist with kind `9`, Nostr IDs, `h` tags, owner checks and `thread_root`. | Calling the broker transport-neutral today would be inaccurate. Extract source policy before making reuse claims. |
| `events.py` | MCP Events registration/signing, Buzz payloads and NIP-10 thread interpretation share a module. | Separate Buzz source semantics from provider protocol implementation; keep wire payloads compatible. |
| `transports.py` | Dot webhooks and the sole Buzz CLI publisher share a module. | Split implementations behind existing import paths; never give the provider the publisher or managed signing key. |
| `http.py` | Encrypted subscriptions, bearer authentication, bounded HTTPS and RPC/HTTP dispatch share a module and import event `VERSION`. | These are mixed responsibilities, not a finished reusable connector SDK. Avoid an unrelated wholesale rewrite. |
| `tools.py` | Five `buzz_*` tools use `dot_job_id` and Buzz source fields. | Preserve the wire contract and existing Dot execution. Internal abstractions do not authorize renaming these fields. |
| `setup.py` | Helpers write public configuration and one-channel receiver rules without runtime changes. | Keep setup non-destructive and report exactly what doctor has and has not checked. |
| Publication proof | `CliTransport` verifies signed relay readback; `Broker.drain_one` currently accepts a response receipt with only `accepted` and an event ID. | Strengthen the broker contract to reject a receipt lacking explicit verified-readback evidence; acknowledgement is not delivery. |

## Evidence policy

Use four distinct statuses: **verified locally**, **verified against an official
source**, **pending external acceptance**, and **blocked**. A test skip is never a
pass. A prior private deployment is context, not evidence for a clean installation.
Each recorded result needs the command or source, revision/version, outcome and
limitations. Never include credentials, callbacks, actual messages, or live state.

The parent's baseline run collected 54 tests: 50 passed, two failed and two
skipped. Both failures concern insecure-directory fixtures: process umask `077`
turns requested mode `0755` into `0700`. Set the intended fixture mode explicitly
and rerun under restrictive and ordinary umasks. Do not weaken production checks.
The initial skipped gates were installed Buzz and macOS Security ABI acceptance.
The parent subsequently reports the suite passing under umask `022` with the
official installed ACP gate enabled (54 collected, one macOS skip). Record the
post-fix restrictive-umask result in the final acceptance report.

Source questions to resolve in P0:

| Claim | Required evidence | Initial status |
| --- | --- | --- |
| Receiver `[[rules]]`, `channels`, `kinds`, `require_mention`, and environment selection | Exact official Buzz parser and configuration-selection code at a recorded commit; generated fixture parsed with that implementation where available. | Parser structure verified at Buzz `347ce88d5dd8bc631c073f1947fea6b75d5a43c0`; execution against official binary pending. |
| ACP event framing and reply tags | Official Buzz producer/parser and thread-tag implementation at the supported revision, including single/batch/steer/context envelopes and direct/nested replies. | Desktop 0.5.28 thread resolver/builders verified; incoming direct-reply and root-only normalization mismatch found. Correction and durable-state regression required below. |
| Existing Dot can receive the advertised MCP Events contract | Official OpenAI event and plugin docs: version, discovery, subscribe/unsubscribe, callback challenge/signature, TTL, payload, authentication and account prerequisites. | Official event protocol retrieved; actual account connection and delivery remain pending. |
| HTTP/MCP lifecycle | Official protocol applicable to the actual plugin connection. | Official Events guide uses MCP 2.0 `2026-07-28` and `server/discover`; do not manufacture an `initialize` gap from unrelated MCP versions. Execute local wire contracts and keep external connection acceptance separate. |
| Referenced Library attachment | Readable original contents through a supported access route. | Parent obtained the full 106-line source body after materialization failures; approved source-body fallback can support a derivative skill. Exact file materialization remains blocked. |
| Authorized publication | Verified Alita App installation route, repository permission and remote attribution/signature evidence. | Cloud App route blocked; parent reports existing mini Alita session owns Project/Issue/publication work. Prepare a secret-free patch or bundle for that route; create no duplicate remote work items. |

Official parser evidence: [Buzz `load_rules`](https://github.com/block/buzz/blob/347ce88d5dd8bc631c073f1947fea6b75d5a43c0/crates/buzz-acp/src/config.rs#L1290)
deserializes `rules`, checks names and validates channel scope;
[SubscriptionRule](https://github.com/block/buzz/blob/347ce88d5dd8bc631c073f1947fea6b75d5a43c0/crates/buzz-acp/src/filter.rs#L83)
declares the emitted fields. This source revision is distinct from desktop
`0.5.28`; record the exact binary version for executed acceptance.
The [official OpenAI MCP Events guide](https://developers.openai.com/plugins/build/mcp-events)
documents the current event discovery and signed webhook protocol. It does not
establish successful registration for a particular account.

The parent has also verified desktop `0.5.28` revision
`f87c10895ea35a9a2cea629fef1d7532a3fecbc5` and executed its ACP integration gate
locally. That is distinct from executing the receiver TOML parser: `load_rules`
runs after channel discovery. Source comparison and ordinary TOML parsing do not
establish an executed official receiver-parser gate. Keep that limitation explicit
unless an isolated, credential-free harness proves it.

### Verified thread mismatch and revised version decision

At desktop `0.5.28`, [ThreadMarkers.resolve](https://github.com/block/buzz/blob/f87c10895ea35a9a2cea629fef1d7532a3fecbc5/crates/buzz-core/src/nip10.rs)
defines root+reply as nested, reply-only as a direct reply whose target is the
root, and root-only/neither as top-level. The [SDK thread builder](https://github.com/block/buzz/blob/f87c10895ea35a9a2cea629fef1d7532a3fecbc5/crates/buzz-sdk/src/builders.rs)
emits reply-only for a direct reply. The bridge currently rejects incoming
reply-only sources and interprets root-only as nested ancestry. Correct both
cases while retaining the bridge's stricter rejection of malformed and duplicate
marked references; upstream ignoring malformed tags or selecting the last duplicate
does not require relaxing the bridge admission policy.

This changes the exposed normalized `source.thread_root` and the interpretation
of existing durable root-only jobs. Under the requested strict compatibility
policy, the combined candidate is therefore **1.0.0**, superseding the earlier
0.2.1 refactor-only classification. A major version is a compatibility signal,
not a claim of audit, universal provider availability or operational maturity.

The smallest safe state transition requires no bulk database rewrite or schema
bump. Before response preparation and explicit reconciliation, use the returned
freshly signature-verified source in an ephemeral job copy passed to the publisher.
The baseline calls source verification but discards its normalized result. Preserve
the persisted snapshot and historical statuses; check the stable source fields
(message ID, author, channel, text and timestamp) agree, allowing only the derived
thread root to normalize under the corrected policy. Any other mismatch fails
closed. Do not infer new ancestry from the stored root alone because raw signed
tags are not persisted there.

Pending publication can use this corrected source under its existing intent.
Uncertain publication stays uncertain and is never requeued; explicit reconciliation
may mark delivery only after the existing reply passes corrected signed-content
and thread checks. Already delivered/cancelled/quarantined records retain their
history. No new job ID, generation change, provider switch or Dot replacement is
needed solely for normalization. New admissions store the corrected source.

Upgrade host and frontend together while stopped. Preserve encrypted state and
its separately held key using the existing operator backup procedure; this work
does not copy either from a live deployment. Do not claim downgrade compatibility:
the old code cannot process newly admitted reply-only jobs correctly. Restoring
an older snapshot does not undo external sends and must use existing restore
quarantine. Never replay jobs to make a downgrade appear successful.

Record verified URLs, exact revisions, relevant symbols and short findings in the
implementation report. If a source is unavailable or contradicts the code, keep
the affected compatibility claim pending and implement only independently
justified local work. Do not fill gaps with scraped private protocols.

## Finite implementation units

Work in order; each unit ends with a reviewable diff and recorded acceptance.
Stop adding abstractions once P3 proves the boundary. P4 is a focused component
split, not a mandate to reorganize every file.

### P0 — Freeze contracts and verify upstream assumptions

- Read repository instructions and inspect code, configuration, wire schemas,
  installed dependencies, public history and tags. Record the baseline revision.
- Resolve the official-source questions above. Separate protocol fact from local
  policy and from account-dependent behavior.
- Capture synthetic compatibility fixtures for generated receiver configuration,
  all five tool schemas, event discovery/subscription/wake envelopes, ACP model
  selection, job IDs, status fields and schema-2 state.
- Run the existing suite with pinned dependencies; retain pass/skip/error counts.
- Correct only the two umask-sensitive fixtures by setting their intended unsafe
  modes explicitly; verify under both `022` and `077` umasks. Execute the official
  extracted `buzz-acp` parser without credentials or network effects when possible.

Acceptance: baseline report, source matrix with no unsupported “verified” claims,
and fixtures that express public behavior. Any parser mismatch gets a focused
regression and a correction before it is advertised as supported.

### P1 — Close the publication-proof contract gap

- Add a negative contract test: a response transport returning only
  `accepted=True` and a plausible event ID must not mark delivery complete.
- Require explicit `signed_readback is True` as well as the accepted receipt and
  valid event ID in the broker response gate, matching reconciliation's existing
  requirement. Keep verification in the trusted Buzz publisher.
- Preserve wake acknowledgement semantics. On missing/invalid response proof,
  persist uncertainty with no retry. Do not mistake a boolean for cryptographic
  verification of an arbitrary plugin: only reviewed, explicitly composed code
  can supply a publisher.

Acceptance: negative test fails on baseline and passes after the fix; real signed
synthetic direct/nested replies still deliver; mismatched receipts remain uncertain;
no extra CLI or webhook attempt occurs.

### P2 — Extract Buzz source validation behind an explicit contract

- Introduce a small internal source-policy contract accepting the authenticated
  principal, exact source identifier and freshness context. Its result is verified
  source data, never prompt text presented as evidence.
- Move Nostr signature/ID, owner, kind, channel-tag, activation/freshness and NIP-10
  thread checks into a Buzz implementation. Keep authorization rechecks at the
  broker's existing admission, pending, completion and effect boundaries.
- Keep the existing normalized source dictionary and durable representation in
  this increment; do not migrate jobs or recompute request IDs. A typed immutable
  internal representation is optional only if its serialization is unchanged.
- Apply the verified thread normalization correction and ephemeral source refresh
  described above. Do not overwrite historical source snapshots or reset outbox
  states. Reconciliation must use the same corrected source contract as first send.
- Inject the policy from `Application`. Preserve existing constructor/import
  entry points with a Buzz compatibility facade if needed. New generic internal
  code must not silently default to trusting unverified data.

Acceptance: existing wrong author/signature/channel/time/thread tests pass through
the Buzz adapter; one synthetic non-Nostr source-policy test exercises admission,
completion and fencing without Buzz parsing or network access. This proves a seam,
not support for another product. Assert current source/status/ledger bytes or
decoded shapes and request IDs remain compatible.
Add synthetic schema-2 fixtures with legacy root-only ancestry in pending and
uncertain response states. Prove pending publication verifies the actual official
reply shape; uncertain reconciliation performs no send; unavailable or mismatched
source evidence cannot authorize an effect. Cover incoming reply-only, root-only,
root+reply, no-marker, malformed and duplicate-marker cases. Existing delivered,
cancelled and quarantined histories must not be reinterpreted as fresh work.

### P3 — Prove the durable boundary with executable contracts

- Add focused contract coverage for a source-policy stub and independent provider
  fixture: source revalidation after admission, revocation before an effect,
  stale generation, duplicate completion, cancellation, callback uncertainty and
  response proof rejection.
- Preserve encrypted atomic job/outbox commits, provider/scope binding, exclusive
  publisher lease, crash recovery and explicit restore quarantine.
- Assert the core contract layer imports no Buzz framing, relay, CLI, ACP frontend
  or provider implementation. A compatibility facade may compose defaults outside
  that layer. Do not claim the entire distribution is dependency-free.
- Keep remote execution separate from delivery and from ACP completion. The
  provider fixture must not acquire credentials or publish a reply itself.

Acceptance: meaningful behavior tests demonstrate a source-policy substitution
and existing Dot flow with identical state transitions; crash and inherited-lease
tests still pass. An import check supplements these tests but cannot replace them.

### P4 — Make the real adapter and host boundaries visible

- Place Buzz source/thread and CLI publication implementations together under an
  explicit internal Buzz adapter namespace; keep relay/framing/managed handoff
  clearly identified as Buzz-specific.
- Place Dot MCP Events registration and wake implementation together under an
  explicit internal provider namespace. Preserve `chatgpt-dot`, event/tool names,
  subscription identity derivation, webhook signing and bounded callback transport.
- Retain old import paths as lightweight forwarding modules when moving an
  exposed symbol. Preserve `NotReady` class identity across imports.
- Keep host assembly, encrypted storage and credential injection separate from
  provider code. Split HTTP helpers only where required to eliminate a concrete
  dependency cycle or protocol coupling; parameterize protocol version only with
  an evidence-backed default. Do not create a general plugin loader.

Acceptance: existing imports and executable entry point work; component map
matches actual imports; old/new package integration fixtures use the same tools,
events and encrypted-state formats. Installation remains one package.

### P5 — Document installation, compatibility and versioning

- Update README, architecture, components, providers and development documents to
  describe implemented boundaries and exact account/platform prerequisites.
- Provide a public-input-only fresh setup example; keep doctor offline and explicit
  about unchecked runtime/authentication. Preserve the same existing Dot path.
- Add a compatibility/release record using the policy below. Mark external plugin
  registration and real delivery as pending when they have not been exercised.
- Add bounded recovery guidance and clean-install CI covering supported local
  checks, with optional real-provider gates clearly separated.
- Prepare the approved derivative user-level commit skill from the retrieved source body,
  retaining its actual requirements and provenance. Keep a non-discovered reinstall
  source under `contrib/commit-skill`, with a separate installable artifact; remove
  the generated repo-discovered copy. Actual mini registration is parent-owned and
  pending. Record the failed original
  materialization separately. Prepare unit issue titles, bodies and acceptance
  criteria for the existing mini Alita session; do not create duplicate Issues or
  Projects in cloud.
- Keep MIT and original attribution; document dependencies without bundling private
  launchers, assets, histories, credentials or related-project code.

Acceptance: every advertised command exists, synthetic setup writes only the
chosen new files, and documentation distinguishes implementation, installation
and real provider acceptance. Product and package names remain Buzz Agent Bridge
and `buzz-agent-bridge`.

### P6 — Verify the distribution and prepare review

- Run the full test suite and package build following `docs/development.md` in a
  virtual environment with the pinned dependency constraints. Record skips.
- Inspect wheel and sdist file lists, licenses and examples. Install the built
  wheel into an isolated environment and run version/harness/doctor smoke checks
  with synthetic paths and public identities.
- Run a secret scanner on the exact proposed release tree and built distributions;
  inspect findings without printing secret material or broadening exclusions.
- Review the complete diff, public history/tag preservation and release version.
  Prepare the draft PR title/body and evidence report locally even if publication
  is blocked. Do not mint commits/tags under an unauthorized identity.

Acceptance: reproducible command results, clean artifact inventory and scanner
findings, compatibility verdict and explicit external/identity blockers. A draft
PR is complete only when the authorized remote operation succeeds and its URL,
head, attribution and signature/verification status are inspected.

For the current split of work, assemble a secret-free patch or bundle and its
manifest for Library transfer to mini. Mini verifies and publishes through its
existing Alita App session. Packaging this handoff does not authorize modifying
mini's live runtime. Cloud must not substitute human credentials or duplicate
the Project/Issue creation owned by that session.

## Compatibility and strict version policy

The baseline package is `0.2.0`. Treat CLI commands and defaults, public
configuration, ACP model selection, MCP events/tools, documented Python extension
interfaces, state formats, identity binding and operational semantics as protected
contracts. A module move is compatible only if required imports keep working.
The new source seam is internal, not a newly supported public SDK. The original
compatible refactor/receipt-fix candidate was `0.2.1`. Verified thread normalization
and its durable-state implications supersede it with candidate `1.0.0`; document
the corrected behavior and upgrade/rollback limits rather than claiming a new SDK.
Keep `dot_job_id` on the wire and in existing state; an internal neutral alias is
not a migration. Keep the same Dot, principal, owner, channel and state scope.

Apply strict SemVer even before 1.0:

- A breaking change requires a major increment (`0.2.0` to `1.0.0`, not `0.3.0`).
  Include an explicit migration, rollback limits and compatibility evidence.
- A backward-compatible feature uses a minor increment (for example `0.3.0`).
- A compatible bug fix uses a patch increment (for example `0.2.1`).
- A pure internal refactor or documentation change does not automatically require
  a product release. Choose the final product version from the actual combined
  behavior change, and synchronize package/runtime version declarations.

Reserve product tags for `vMAJOR.MINOR.PATCH`. All unit milestones, including
documentation/planning, use immutable annotated tags in the registered commit
skill's namespace `work/issue-<number>/<unit>-r<N>`. They are work markers, never
installable product version claims. Do not create or move any tag during this
planning task. Never rewrite existing public tags/history.
Version equality is currently used at IPC and managed handoff, so mixed-version
host/frontend operation must remain rejected or gain an explicitly tested policy;
do not claim rolling upgrade compatibility without evidence.

## Completion ledger

Update this table as implementation proceeds; checked means evidence exists.

| Unit | State | Evidence / remaining gate |
| --- | --- | --- |
| Planning and ADR | Complete | Repository code inspected; this plan and ADR created before implementation. |
| P0 Contracts and upstream evidence | Verified locally/source-reviewed | Baseline rerun and official source matrix recorded; full connected receiver loader and real account remain external. |
| P1 Publication-proof gate | Verified locally | Baseline defect reproduced; strict receipt gate, uncertainty and no retry tested. |
| P2 Source-policy extraction | Verified locally | Injected policy, four marker cases, legacy schema-2 pending/reconciliation and stable evidence tests; major candidate 1.0.0. |
| P3 Durable contracts | Verified locally | Non-Nostr substitution plus full fencing/recovery/lease suite passes. |
| P4 Adapter boundaries | Verified locally | Actual namespaces, compatibility facades, core import rule and frozen wire schemas tested. |
| P5 Public docs/version policy | Complete locally | Migration, recovery limits, strict version/work-tag policy, validated personal-skill distribution and issue drafts; mini skill registration pending. |
| P6 Distribution/review | Local verification complete; remote review pending | Built artifacts, isolated wheel suite and scans pass; authorized draft PR/CI/publication remains mini-owned. |
| External provider acceptance | Pending; outside current local work | New authorized private source message, existing Dot, verified relay readback; no live change implied. |
| Alita publication/main replacement | Cloud blocked; mini handoff pending | Existing mini Alita session owns publication; secret-free handoff and inspected remote provenance required; report results before main replacement. |

## Release and completion gates

The local restructuring can be reported complete once P0–P6's local evidence is
recorded, with unresolved remote actions named accurately. Do not conflate that
with a published release, working new installation, or main replacement.

1. **Design:** plan and ADR exist before implementation; unsupported names and
   provider promises are absent.
2. **Behavior:** local contracts, baseline regressions, signed receipt checks,
   uncertainty and cancellation remain sound; optional skips are visible.
3. **Artifact:** pinned build and clean installation pass; exact shipped files,
   dependency licenses and secret scan are reviewed.
4. **Compatibility:** strict SemVer classification, state/IPC policy and preserved
   history/tags are documented. No implicit live migration is included.
5. **Review/provenance:** branch and draft PR are reviewable through the authorized
   Alita GitHub App route; remote attribution and verification are checked.
6. **Operational claims:** current official protocol evidence and separately
   authorized real provider acceptance support any stronger readiness claim.
7. **Main/release:** report the completed results and remaining limits first;
   update `main` or publish a release only within the user's authorization and
   approved identity route. Never substitute a human token for a blocked App.

If blocked, record the exact action, target, reason, completed independent work,
and whether it was denied, pending or uncertain. An uncertain remote mutation
requires readback before any retry. Keep local review preparation moving.

## Authorized amendment: Nix flake and direnv (U07)

The user subsequently selected Nix flake plus direnv for the development
environment. This does not change the product architecture or the 1.0.0 candidate.
Pin a single nixpkgs input, use the same Python 3.11/developer-tool declaration
on Linux/macOS, and keep the existing Python lock/install path available without
Nix. Do not introduce private paths, keys, automatic services or secret loading.

Deliver `flake.nix`, `flake.lock`, a reviewed minimal `.envrc`, explicit setup
documentation and Linux/macOS Nix CI. Check flake syntax and upstream lock
provenance independently; distinguish them from successful Nix realization.
Acceptance requires unchanged-lock `nix flake check`, tests/build/clean install
through `nix develop`, and approved direnv entry/exit on the intended hosts.
System installation and `direnv allow` are separate host trust actions.

Cloud has neither executable and cannot fetch the pinned release archive (HTTP
403). Continue static and non-Nix package verification; hand the remaining Nix
execution gates to mini/CI without claiming completion. Re-run affected checks
after changes instead of inheriting version 1's results. Record evidence in
`docs/project/nix-development.md` and the separate U07 Issue draft.

Since mini already received Library version 1, supply a version-1-based delta
with file preimage/postimage hashes as well as the cumulative baseline patch.
Do not overwrite mini's newly recorded issue URLs or validation results on
conflict. This development-only unit uses a work tag and adds no product version
bump; product release remains gated by the earlier plan and this acceptance.
