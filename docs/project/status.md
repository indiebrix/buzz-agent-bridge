# Product completion status

Updated 2026-10-22. Scope: **1.0.0** for both distributions.
[PR #8](https://github.com/indiebrix/buzz-agent-bridge/pull/8) records integration,
and the [GitHub Release](https://github.com/indiebrix/buzz-agent-bridge/releases/tag/v1.0.0)
records the authoritative release target and assets. The accepted runtime head is
`a739867b1dae072f9b935fe93d9f44d9742aa794`; final closure changes update documentation.

## Deliverables

- One repository, two independently installable distributions: generic
  `chatgpt-dots-connector` and Buzz-specific `buzz-agent-bridge`.
- Official Buzz custom ACP harness, scoped receiver configuration and documented
  setup. Local status, guarded wake recovery and signed delivery verification.
- MCP Events for existing-Dot ingress, CLI for operators and optional skills for
  workflows. This choice follows supported semantics; there is no MCP preference.
  See [ADR 0002](../adr/0002-independent-dot-connector.md).
- Separate implementation, clean installation, actual provider acceptance and
  publication evidence. See [validation](validation.md).

| Unit | Issue | Acceptance evidence |
| --- | --- | --- |
| Architecture and contracts | [#1](https://github.com/indiebrix/buzz-agent-bridge/issues/1) | Official-source comparison, migration and independent connector decision. |
| Personal commit skill | [#2](https://github.com/indiebrix/buzz-agent-bridge/issues/2) | User-level installation, conflict checks and discovery in a separate repository. |
| Core and adapters | [#3](https://github.com/indiebrix/buzz-agent-bridge/issues/3) | Recovery and fresh automatic delivery separately verified; final two-wheel composition also passed a fresh round trip. |
| MCP contracts | [#4](https://github.com/indiebrix/buzz-agent-bridge/issues/4) | Schema, refresh, rotation, expiry and cross-event isolation checks. |
| CI and distributions | [#5](https://github.com/indiebrix/buzz-agent-bridge/issues/5) | Independent wheel installs, inspected archives, clean secret scans and seven successful runtime-head CI jobs. |
| Release | [#6](https://github.com/indiebrix/buzz-agent-bridge/issues/6) | Strict major version and migration; remote merge, annotated tags and release asset checks are recorded on this issue and the Release. |
| Nix/direnv | [#7](https://github.com/indiebrix/buzz-agent-bridge/issues/7) | Locked macOS development script and Linux/macOS CI; developer-host direnv trust remains an explicit local decision. |
| Connector and operators | [#9](https://github.com/indiebrix/buzz-agent-bridge/issues/9) | Independent non-Buzz integration, guarded operator tests, exact installed-file comparison and fresh signed relay delivery. |

Issues 1–7 and 9 are linked to the existing organization Project. Their completion
records link immutable annotated work tags, the integrating PR and release commit.
No new repository or package-registry publication is implied by the package split.

## Scope and limits

The generic connector is a host-embedded event/tool transport. The host still owns
authorization, durability and effects. Only ChatGPT Dot is implemented as a remote
provider; synthetic non-Buzz integration is not a second live account acceptance.
Real optional macOS Keychain item access and other declared Nix architectures are
unverified. A build does not establish account eligibility or live delivery.

Public evidence omits personal paths, identity values, credentials and messages.
The release workflow gates publication on exact-head CI, App attribution, accepted
wheel hashes, a new authorized source and independent signed relay readback.
