# Upstream contract evidence

Inspected 2026-10-22. Product baseline:
`694642933a791c20d9d85254cd9b61afc3ae5be8` (Alita App author; GitHub verification
`verified=true`, `reason=valid`). Source review and execution are separate gates.

## Buzz

Official release `desktop-v0.5.28` resolves to
`f87c10895ea35a9a2cea629fef1d7532a3fecbc5`. Also inspected upstream main
`347ce88d5dd8bc631c073f1947fea6b75d5a43c0`; the release is the compatibility target.

| Contract | Direct source and finding | Executable evidence |
| --- | --- | --- |
| Receiver file | [config.rs](https://github.com/block/buzz/blob/f87c10895ea35a9a2cea629fef1d7532a3fecbc5/crates/buzz-acp/src/config.rs): `load_rules`, `TomlConfig`, `BUZZ_ACP_SUBSCRIBE` and `BUZZ_ACP_CONFIG`. | Generated TOML parsed with Python tomllib; installed CLI help confirms option/environment selection. Full Rust receiver-file loader not run. |
| Channel and mention policy | [filter.rs](https://github.com/block/buzz/blob/f87c10895ea35a9a2cea629fef1d7532a3fecbc5/crates/buzz-acp/src/filter.rs): `SubscriptionRule` and `ChannelScope`; one UUID, kind 9 and explicit mention flag match generated output. Owner-only authorization is a separate required gate. | Synthetic setup checks exact scope and no runtime mutation. |
| Thread ancestry | [nip10.rs](https://github.com/block/buzz/blob/f87c10895ea35a9a2cea629fef1d7532a3fecbc5/crates/buzz-core/src/nip10.rs): `ThreadMarkers.resolve` distinguishes direct/nested/top-level. | New four-case source tests; legacy schema-2 routing/reconciliation regression. |
| Publication tags | [builders.rs](https://github.com/block/buzz/blob/f87c10895ea35a9a2cea629fef1d7532a3fecbc5/crates/buzz-sdk/src/builders.rs): `thread_tags` emits reply-only for direct replies, root+reply for nested. | Signed direct/nested receipt tests, wrong-content/tag rejection. |
| ACP intake | [lib.rs](https://github.com/block/buzz/blob/f87c10895ea35a9a2cea629fef1d7532a3fecbc5/crates/buzz-acp/src/lib.rs) and installed `buzz-acp run`. | Official Linux binary runs the Python ACP frontend to durable admission with synthetic data. This does not test the relay receive loop. |

The full receiver loader runs after relay connection and channel discovery.
Starting a service with real credentials to reach it is not part of offline tests.
Do not describe tomllib parsing or `--help` as executing Rust `load_rules`.

## OpenAI

The official [MCP Events guide](https://developers.openai.com/plugins/build/mcp-events)
requires MCP 2.0 `2026-07-28`, `server/discover`, webhook discovery/subscription,
a signed callback challenge, persistent subscriptions, bounded verification caching,
secret rotation, and distinct acknowledgement/completion. Tests cover discovery,
five unchanged tool schemas, callback failure, independent HMAC verification,
restart/refresh/rotation, expiry, revocation and unsubscribe. Polling, streaming
and replay are not advertised; ambiguous deliveries are never retried automatically.

The [connection guide](https://developers.openai.com/plugins/deploy/connect-chatgpt)
describes authenticated endpoint or Secure MCP Tunnel registration and account
controls. The bridge exposes only loopback HTTP and consumes an explicitly supplied
bearer token. OAuth, proxy/tunnel provisioning, account entitlement and a real Dot
subscription must be accepted in the intended account. Offline protocol tests do
not prove these. Existing Dot context remains with the selected subscribed chat.

## Exact release artifact used for the local ACP gate

The [official Linux deb](https://github.com/block/buzz/releases/download/desktop-v0.5.28/Buzz_0.5.28_amd64.deb)
was extracted into a separate validation directory, not installed as a service.
SHA-256: `53609fa586a787871f080b0bfce679633e457f650982411c81ba104648c388cb`.
Its `buzz-acp` has no `--version` flag; provenance comes from the release artifact.
Only public scalar-one fixtures and loopback endpoints were used by the ACP test.
