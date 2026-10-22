# ChatGPT Dots Connector

A small Python connection layer for external systems that need to send events to
an existing ChatGPT Dot and expose authenticated tools to that same Dot. This is
an independent community project, with no official affiliation. Account access
to custom MCP connections and MCP Events is required; model API access alone
does not provide access to an existing Dot.

Install the `chatgpt_dots_connector` wheel from the project's GitHub release in a
Python 3.11+ virtual environment. This distribution uses the Python standard
library and has no dependency on Buzz, ACP, Nostr, a vault client or a model SDK.
The encrypted subscription store is Unix-only and requires host-supplied
authenticated-encryption functions; it never generates or looks up keys.

## Composition

```python
from chatgpt_dots.definition import EventDefinition
from chatgpt_dots.events import Subscriptions
from chatgpt_dots.delivery import Delivery
from chatgpt_dots.http import RPC, PublicHTTPS, http_server

definition = EventDefinition.string_fields(
    "build.finished", "A build is ready for review.", "project",
    ("build_id", "result", "summary"),
)
# Supply an encrypted store, current authorization policy, authenticated
# principal mapping, application tools, clock, and one shared lock.
# Serialize subscription RPC and Delivery.send with that lock.
subscriptions = Subscriptions(definition, store, authorize, PublicHTTPS(), now)
delivery = Delivery(definition, store, PublicHTTPS(), authorize, now, lock)
rpc = RPC(subscriptions, tools)
event = definition.event("build-42", now(), {
    "build_id": "42", "result": "passed", "summary": "Ready for review",
})
plan = delivery.prepare(principal, "example-project", event)
# Persist a sending intent under the application's exclusive effect lease.
receipt = delivery.send(plan)  # One attempt; an ACK is not execution/delivery.
```

The snippet is a composition contract, not a runnable deployment: the host must
supply the explicitly named objects. See the repository's runnable, synthetic
`examples/non_buzz_connector.py` for an independent integration check.

Each subscription service advertises one event type with one named string scope.
Payloads can be arbitrary JSON objects: use `EventDefinition` with an accurate
`payload_schema` and a validator returning exactly `True` for valid data.
`string_fields` supplies both for the common fixed-string-field case. The host
owns schema/validator agreement and source authenticity. No source IDs need to
be Nostr hashes, and event names, scope names and tool names are application-owned.

Hosts must provide durable admission, deduplication, generation fencing, result
authorization and publication appropriate to their own system. This package
does not claim delivery from a callback ACK, copy Dot memory, create model sessions,
retry uncertain sends, or publish messages on the application's behalf.

## Registration and transport

Expose the loopback `/mcp` listener through an already approved HTTPS endpoint or
supported secure MCP tunnel. Register that connection in ChatGPT and ask the
intended Dot to subscribe to the advertised event with the intended scope. Supply
only the application's approved completion workflow and tools. Connection and
subscription are separate steps. A live callback verification challenge and
subsequent real event are required for account acceptance.

The service implements MCP Events version `2026-07-28`, callback verification,
bounded refresh/rotation and authenticated tool dispatch. The `PublicHTTPS`
transport validates and pins a public address, verifies TLS and rejects redirects.
Use the same lock around registration/unsubscription and delivery. Recheck
authorization for subscription and every send. Store callbacks and signing
secrets only in encrypted application state outside source control.

A lost or failed send response can leave remote receipt uncertain. Persist that
uncertainty in the host and reconcile through provider evidence; do not simply
call `send` again. Multiple active subscriptions for the same principal/scope
fail closed instead of choosing a Dot arbitrarily. Cancellation and application
result tools remain the host's responsibility.

MCP Events is the current supported Dot ingress. A CLI is useful for host setup
and diagnosis; skills supply workflow instructions; lifecycle hooks run inside a
supported agent session. They are different layers, not equivalent ways to attach
an external event to an existing Dot. See the repository's architecture decision
for sources, alternatives and the conditions for revisiting this choice.
