# Components and deployment boundaries

The MCP server is included in this repository. A name shown in ChatGPT's plugin
settings is the installed connection's display name, not another required software
package. Registration, credentials, event subscriptions, and the running server
are separate parts of a deployment.

| Layer | Included implementation | Operator-supplied dependencies |
| --- | --- | --- |
| ChatGPT integration | `adapters/chatgpt/events.py`, `adapters/chatgpt/wake.py`, `http.py`, `tools.py`, and `ChatGPTDot` implement event discovery/subscription, signed webhook delivery, authenticated MCP tools, and callback validation. | An eligible Dot account, plugin connection/registration, and user-authorized event task. |
| Durable work | `core/broker.py`, `core/contracts.py`, `ledger.py`, and `application.py` implement admission, encrypted jobs/outbox, generation fencing, uncertainty, and a single publisher. | Host storage and explicitly supplied encryption/authentication secrets. |
| Buzz adapter | `adapters/buzz/source.py`, `adapters/buzz/publisher.py`, `frontend.py`, `managed.py`, and `relay.py` connect ACP, managed identity handoff, signed relay reads, and official CLI publication. | Buzz Desktop/relay/CLI, the managed identity, and approved owner/channel membership. |
| Deployment | `cli.py`, setup/doctor helpers, and examples provide host entry points and secret-input contracts. | Process supervision, supported managed-agent UI actions, and an approved HTTPS proxy or tunnel. |

An operator may keep a private launcher that binds paths, identities, vault
references, and a tunnel to a particular computer. Such a launcher is not a hidden
Python dependency of this package. Its operational choices must be supplied and
validated independently. Do not copy live launchers, plugin credentials, callbacks,
private configuration, ledgers, or internal runbooks into this repository.

## Reuse and naming

The current package is Buzz Agent Bridge. It includes the MCP surface needed by its
ChatGPT Dot provider. The lifecycle now consumes an explicit verified-source policy and has a synthetic
non-Nostr contract test. It is not a standalone transport-neutral connector: event
names, channel filters, job source data, and publication verification still express
Buzz concepts. A future neutral layer could have a separate community product name,
but changing a connection label alone does not implement that layer or confer
official affiliation. No separate connector repository is required today.

| Organization | Benefits | Costs and suitable trigger |
| --- | --- | --- |
| One repository with explicit modules | Atomic changes and one tested installation; simplest current release. | Maintain clear contracts so Buzz-specific source/receipt rules do not leak into reusable provider code. |
| Independently versioned package/repository | Independent reuse and release by multiple working adapters. | Requires stable contracts, compatibility testing, provenance, and a pinned dependency. Consider after a second integration is implemented. |
| Git submodule | Pins a source revision for joint source development. | Requires recursive checkout and separate build/release handling; does not install Python dependencies or ensure compatibility by itself. Avoid as the default consumer install. |

Before extraction, define and test provider discovery/auth/subscription/wake and
job completion/cancellation contracts; isolate Buzz source and signed-receipt
validation; review dependencies and license attribution; scan the exact distribution;
and test installation, HTTPS registration, callback verification, fresh message
delivery, duplicate handling, cancellation, and crash recovery from a clean setup.
Preserve identity and authorization boundaries. Until those checks pass, document
the extraction as planned rather than an independently deployable product.

The public distribution and a private installation can be at different revisions.
Local unit tests and a running process do not prove that a new user can complete
the external plugin subscription or message round trip.

The chosen single-package boundary is recorded in [ADR 0001](adr/0001-portable-core-boundaries.md).
Legacy `broker`, `events` and `transports` imports remain compatibility facades.
The internal lifecycle imports no Buzz/provider implementation; its normalized
record names and 64-hex source identifiers intentionally retain the current wire
contract. This is tested reuse inside one product, not an independently supported SDK.
