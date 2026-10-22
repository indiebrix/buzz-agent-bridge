# ADR 0002: Independent Dot transport and a Buzz application

Status: implemented candidate; release acceptance is recorded separately.
Date: 2026-10-22. Supersedes ADR 0001's single-distribution decision.

## Goal and evidence

An operator must be able to connect an existing Dot to an external system, and
install Buzz Agent Bridge as a standard custom ACP runtime. A connector must be
usable without installing Buzz. No preference for MCP, CLI, skills or hooks is
assumed. The decision follows supported capabilities, installation burden,
failure semantics, independent consumption and maintenance cost.

The raw inputs are the actual source at PR #8, built distribution dependencies,
the installed Buzz 0.5.28 contract and official interface documentation. A package
name or an import-boundary test alone does not establish a usable connector.
Acceptance requires a separate clean installation, a non-Buzz event/tool consumer,
unchanged Buzz contracts and real provider evidence for the advertised live path.

## Compare layers before choosing a transport

| Method | Role and capability | Setup and operating cost | Fit for this goal |
| --- | --- | --- | --- |
| MCP Events + tools | An external event reaches the subscribed chat/Dot; authenticated tools expose application work/results. | Account eligibility, connection, HTTPS/tunnel and explicit subscription; durable uncertainty and authorization remain application work. | Use for current existing-Dot ingress and tools, based on documented semantics and live evidence. |
| CLI | Install, configure and inspect a local service; `codex exec/resume` runs/resumes a Codex session. | Simple local automation, but computer/process lifetime and credentials must be managed. | Use for operators. Reviewed CLI documentation does not establish attachment to the same personal Dot; a separate Codex agent is another target. |
| Skill | Reusable instructions around available tools and a task's workflow. | Low packaging overhead; depends on the model and tools already available. | Optional setup/completion guidance. It does not implement event ingress, durable state or authorization. |
| Lifecycle hook | Runs at supported agent-loop events. | Host-specific trust/configuration and cloud restrictions; failures need explicit handling. | Optional local workflow integration. It does not independently wake an existing Dot from an external system. |
| Direct API/webhook | Useful where the target exposes an authenticated session/event endpoint. | Could remove protocol layers if same-Dot semantics exist; a custom endpoint still needs authentication, state and recovery. | No equivalent existing-Dot inbound endpoint was established in reviewed official API/CLI documentation. Re-evaluate if one is documented. |

Primary source excerpts:

- MCP Events: “ChatGPT receives the event in the subscribed chat.” The documented
  flow includes discovery, subscription and callback verification, not arbitrary
  polling or local shell invocation. [Official MCP Events](https://developers.openai.com/plugins/build/mcp-events).
- `codex exec` and `codex exec resume` operate on Codex runs/sessions.
  [Official non-interactive mode](https://learn.chatgpt.com/docs/non-interactive-mode).
- Skills provide reusable workflows around tools.
  [Official skills concepts](https://developers.openai.com/plugins/concepts/skills).
- Hooks run within the agent lifecycle. Cloud Work/Dot local access has distinct
  restrictions; documented enterprise remote MCP hooks are not a personal-account
  general inbound API. [Hooks](https://learn.chatgpt.com/docs/hooks),
  [cloud local-access restrictions](https://learn.chatgpt.com/docs/enterprise/cloud-local-access).
- Buzz: “Buzz Desktop supports registering any ACP-speaking agent tool as a
  selectable runtime without a PR.” Custom harness JSON has command/args/env;
  Tier 3 does not auto-install software.
  [Pinned upstream README](https://github.com/block/buzz/blob/f87c10895ea35a9a2cea629fef1d7532a3fecbc5/crates/buzz-acp/README.md#bring-your-own-harness-byoh).

There is no comparative latency/cost benchmark across hypothetical implementations.
Choosing MCP here is an interface-fit decision, not a claim that it is universally
faster or preferred. Reusing tested transport reduces implementation risk, but
would not justify it if another supported route met the same semantics more simply.

## Decision and responsibility

Keep one repository with **two separately installable distributions**. The explicit
requirement for external systems beyond Buzz and the executable non-Buzz consumer
justify a packaging boundary now. A second repository would add synchronized PR,
release and provenance work without improving that boundary. A submodule would
make installation harder and would not express runtime dependency compatibility.

| Component | Owns | Outside its responsibility |
| --- | --- | --- |
| `chatgpt-dots-connector` / `chatgpt_dots` | Configurable event definition, scope and payload validation; callback registration/refresh/signing; authenticated MCP transport; host-supplied tool dispatch. | Buzz/ACP/Nostr, source authenticity, model creation, job lifecycle, application publication and secret provisioning. |
| `buzz-agent-bridge` | Standard ACP harness, Buzz identity/source/receipt checks, durable jobs and generations, uncertainty, result tools and the sole Buzz publisher. | Generic connector installation internals or new Dot sessions. |
| External consumer | Its event source, current authorization, durable intent/deduplication, tool semantics, correlation, cancellation and result effects. | Reimplementation of callback verification or MCP transport. |

The connector deliberately does not duplicate the durable broker as a second job
engine. It is an embedding component with a concrete event/tool API, not a hosted
universal automation service. The build-review example demonstrates non-Buzz
composition through real authenticated loopback HTTP and independently checked
webhook signatures; its callback is synthetic, not a second live account claim.
One subscription service advertises one event type and named scope. Multiple
active Dots for the same scope fail closed. Unsupported providers remain rejected.

Buzz's five tools, event name/filter/payload, current subscription IDs and encrypted
rows, compatibility imports and schema-2 jobs remain unchanged. The extracted
delivery layer also binds subscription selection to event type, so two event
definitions sharing a store cannot receive one another's messages.

## Installation and release

The connector has no third-party Python dependencies; its encrypted store accepts
host-supplied AEAD functions and uses Unix locks. The bridge pins connector 1.0.0.
Release assets supply both wheels plus checksums; consumers install both in one
command. Source users install `./packages/chatgpt-dots` and `.` together. No PyPI
publication or registry name ownership is implied.

Both packages start this release at 1.0.0. Buzz's highest change relative to the
0.2.0 baseline is already major. These are additions to the unreleased
candidate, not a new minor release after 1.0.0. Future independent changes follow
strict SemVer and tested dependency compatibility. Existing tags are immutable.

For operator usability, the public host now emits redacted stage diagnostics;
`status` uses peer-authenticated local IPC and checks the configured identity.
`resume-wake` exposes only the existing one-time, never-attempted blocked-wake
recovery. It cannot rearm cancelled, quarantined, expired, sending, uncertain or
completed work. No automatic retry or new external tool permission is added.

Actual implementation, package installation, provider-account acceptance and
publication remain separate entries in the validation record.
