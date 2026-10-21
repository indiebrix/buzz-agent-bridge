# Adding a provider

Only `chatgpt-dot` is registered today. Grok Bot and Meta Muse are roadmap targets,
not implemented providers. Do not add a selector entry for a provider
whose authentication and event path do not work. A synthetic second adapter in
the tests demonstrates the extension boundary without claiming Grok support.

An adapter implements `AgentProvider` in `providers.py`:

- `info`: stable ID, display name, description, and optional legacy model IDs.
- `bind(...)`: receives the encrypted subscription store, authorization callback,
  bounded HTTPS client, clock, public identity, and subscription lock.
- `ProviderBinding.registration`: a `handle(principal, method, params)` RPC handler.
- `ProviderBinding.wake`: `prepare(job, entry)` and `send(plan, lease_fd)` methods.

`prepare` builds a persistable plan and must not cause an external effect. It may
raise `NotReady` before any attempt. The plan must contain destination references,
not plaintext credential copies. `send` makes one attempt and returns an explicit
acceptance result. A timeout with a possible external effect remains uncertain.
Neither method may publish a Buzz response or report remote completion based on
an HTTP acknowledgement.

The common broker owns source validation, generation checks, cancellation fences,
encrypted state, outbox ownership, and verified publication. A provider cannot
silently consume another provider's ledger. Inject adapters explicitly from
reviewed code; the package does not load arbitrary modules named in configuration.

For a Grok Bot adapter, first establish a supported inbound-event mechanism tied
to the intended existing bot/conversation, callback authentication, completion
identity, and cancellation behavior. Remote MCP tool support alone does not prove
that events can wake an existing bot. Document account requirements and test the
real provider before advertising support.

Adapter changes need tests for wrong principal/destination, forged or expired
callbacks, replay, ambiguous network outcomes, crash recovery, stale generation,
and cancellation. Use synthetic identities locally. Run a separately authorized
private-channel end-to-end test for a new real integration.
