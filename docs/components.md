# Components and deployment boundaries

This repository builds two separately installable Python distributions. The
[architecture decision](adr/0002-independent-dot-connector.md) records the transport
comparison, responsibility boundary and independent-consumption evidence.

| Component | Implementation | Operator supplies |
| --- | --- | --- |
| ChatGPT Dots Connector | `packages/chatgpt-dots`: configurable event schemas and scope, callback verification/refresh/signing, authenticated MCP HTTP and host tool dispatch. No Buzz, ACP or Nostr dependency. | Eligible existing Dot, connection/subscription, application authorization and tools, durable effect ownership, encrypted store functions and approved HTTPS/tunnel. |
| Buzz Agent Bridge | ACP/managed identity, signed source and receipt policy, encrypted jobs, generation/cancellation/uncertainty, single publisher, operator CLI. | Official Buzz Desktop/CLI, configured owner/channel, approved secret injection and process supervision. |
| Private deployment | Optional host/secret/tunnel supervision using documented public interfaces. | Machine paths, provisioned keys, service lifecycle and local trust choices. |

The bridge pins the connector distribution. Install both release wheels, or both
local source projects. The connector can be installed alone by another application;
its build-review example exercises a non-Buzz event, filter and tool over real
loopback MCP, using a synthetic callback. That is installation/protocol evidence,
not a second live provider deployment. Current Buzz account acceptance remains a
separate end-to-end gate.

The connector owns connection mechanics. An external application owns source
validation, durable jobs/results, deduplication and publication. It is an embedding
component, not a model runtime or a hosted automation service. Skill instructions
and lifecycle hooks can assist a workflow but do not replace its event ingress.
The independent package contains no secret-manager or model-client dependency.

One repository keeps related compatibility changes atomic and shares CI. Separate
wheels express the demonstrated installation boundary. A second repository is
useful when release/ownership cadence actually diverges; a Git submodule does not
supply a Python dependency or make end-user installation simpler.

Buzz's existing tools/event names and encrypted job/subscription data remain
compatible. The Buzz application and its internal broker records still use Buzz
semantics; those records are not advertised as the generic connector API. The
independent event definition accepts application-owned names, IDs, scope and data.

Public packages and a private deployment can run at different revisions. Source
and wheel checks do not prove real account registration or delivery. Record each
layer against its exact version and source hash, and keep deployment state out of
public source, fixtures, issues and releases.
