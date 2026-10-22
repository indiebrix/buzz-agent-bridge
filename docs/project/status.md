# Portable bridge progress

Updated 2026-10-22. Baseline: `694642933a791c20d9d85254cd9b61afc3ae5be8`.
Review branch: `refactor/portable-bridge`. Candidate version: `1.0.0`.
This is a review candidate; no 1.0.0 release or merge is claimed.

| Unit | Issue | Current evidence and remaining gate |
| --- | --- | --- |
| Architecture and compatibility | [#1](https://github.com/indiebrix/buzz-agent-bridge/issues/1) | ADR, protocol source review and migration prepared. |
| Commit skill and release policy | [#2](https://github.com/indiebrix/buzz-agent-bridge/issues/2) | Generic distribution and installer validated; user-level installation remains an operator action. |
| Core, source and provider adapters | [#3](https://github.com/indiebrix/buzz-agent-bridge/issues/3) | Local synthetic and crash tests pass; candidate live Dot/relay acceptance remains pending. |
| MCP contracts | [#4](https://github.com/indiebrix/buzz-agent-bridge/issues/4) | Schema compatibility, refresh and rotation tests pass locally. |
| CI and distributions | [#5](https://github.com/indiebrix/buzz-agent-bridge/issues/5) | Build and isolated installation pass locally; remote CI is checked on the draft PR head. |
| Reviewed release | [#6](https://github.com/indiebrix/buzz-agent-bridge/issues/6) | Draft review only. Merge, completion tags and release remain gated. |
| Nix and direnv | [#7](https://github.com/indiebrix/buzz-agent-bridge/issues/7) | macOS arm64 Nix realization and locked shell pass; remote matrix and disposable direnv exercise remain CI gates. |

All seven issues are tracked in the existing organization Project. Reuse these
records; do not create replacements on an uncertain response. See
[validation](validation.md) for executed checks and their limits.

## Live acceptance boundary

The candidate has not completed a real ChatGPT Dot and Buzz relay round trip.
The private acceptance deployment is blocked by an unresolved managed-agent
configuration in Buzz; registration recovery is being handled separately from
product publication. No identity, credentials, private configuration, message
content or operational state is included in this repository. A historical test
of 0.2.0 does not validate 1.0.0.

Before release, obtain a new authorized source, verify its current request and
generation, and confirm delivered status with a signed relay event and no duplicate
reply. Preserve the single receiver/publisher and do not replay pending work.

## Publication rules

Publish through the authorized App, verify remote author/signature and exact tree,
and inspect CI on the current PR head. Keep this change in draft review until
remaining acceptance gates are met. Do not merge, force-push, replace tags or
publish a completed release merely to mark preparation finished.
