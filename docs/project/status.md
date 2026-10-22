# Product completion status

Updated 2026-10-22. Candidate: **1.0.0**, not yet released.
[PR #8](https://github.com/indiebrix/buzz-agent-bridge/pull/8) remains a draft.
Its published head `8b276ff3b843a8a9867a99d820ef3693dbc92296` has seven successful
CI jobs and a verified App commit. The independent-connector amendment is local;
that head's CI and live results do not certify the amendment.

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

| Unit | Issue | Evidence and remaining work |
| --- | --- | --- |
| Architecture and contracts | [#1](https://github.com/indiebrix/buzz-agent-bridge/issues/1) | Source-based comparison and migration recorded; connector decision added locally. |
| Personal commit skill | [#2](https://github.com/indiebrix/buzz-agent-bridge/issues/2) | Installed at user level, conflict checks and separate-repository discovery passed. Completion tag pending. |
| Core and adapters | [#3](https://github.com/indiebrix/buzz-agent-bridge/issues/3) | Recovery and a fresh automatic round trip verified on the published candidate. Amendment acceptance pending. |
| MCP contracts | [#4](https://github.com/indiebrix/buzz-agent-bridge/issues/4) | Schema, refresh, rotation, expiry and cross-event isolation checks pass locally. |
| CI and distributions | [#5](https://github.com/indiebrix/buzz-agent-bridge/issues/5) | Two wheels build and install independently; final artifacts and source/artifact scans pass locally; exact-head CI remains a gate. |
| Release | [#6](https://github.com/indiebrix/buzz-agent-bridge/issues/6) | Merge, immutable work tags and release assets pending. |
| Nix/direnv | [#7](https://github.com/indiebrix/buzz-agent-bridge/issues/7) | Locked macOS shell and prior Linux/macOS CI passed; amended build script also passes in the locked macOS shell. |
| Connector and operators | [#9](https://github.com/indiebrix/buzz-agent-bridge/issues/9) | Independent non-Buzz integration and operator regressions pass. Exact-head publication and live-composition gates remain. |

Issues 1–7 and 9 use the existing organization Project. Reconcile stable markers before
creating any record; pending IDs are not remote work. No new repository or registry
publication is implied by the package split.

## Remaining release sequence

1. Preserve final source/artifact inspection, secret scan and clean-install receipts.
2. Publish the reviewed amendment to PR #8 and read its exact-head CI results.
3. Install the exact accepted composition and record its provider acceptance,
   preserving one managed receiver and publisher. Earlier events are never replayed.
4. Verify App attribution, merge, create immutable work/release tags, upload both
   distributions and constraints/checksums, and verify remote results.

Public evidence omits personal paths, identity values, credentials and message
content. Optional real Keychain access and unimplemented providers are not release
claims. A successful build does not establish account eligibility or live delivery.
