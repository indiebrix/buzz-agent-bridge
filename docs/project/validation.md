# Validation record

Updated 2026-10-22. Candidate: 1.0.0; baseline
`694642933a791c20d9d85254cd9b61afc3ae5be8`. This record separates source checks, installation and actual
provider acceptance. Publication is recorded by the tagged GitHub Release.

## Accepted independent-connector composition

macOS arm64, Python 3.11.16, pinned dependencies. All test inputs are synthetic.

| Check | Executed result |
| --- | --- |
| Source suite with official installed Buzz 0.5.28 ACP | 79 tests passed, no skips. |
| Two wheel/sdist builds and metadata inventory | Passed for the tested build; bridge pins connector 1.0.0 and does not vendor it. Exact-source and unpacked-distribution Gitleaks 8.30.1 scans passed with no findings or added exceptions. |
| Bridge clean wheel installation outside checkout | 79 run: 78 passed, one optional installed-Buzz skip. Clean environment, offline pinned wheels, path containing spaces. |
| Independent connector installation | Passed with only the connector wheel; no Buzz, ACP, Nostr or third-party runtime dependency. |
| Non-Buzz integration | Real authenticated loopback MCP HTTP, a custom build event/scope/tool, independent callback HMAC verification, unsubscribe and unauthorized-request rejection passed. Callback is synthetic, not a second real Dot account. |
| Compatibility | Existing discovery/tool/event schemas, subscription IDs, encrypted store and schema-2 jobs retained; cross-event routing rejected. |
| Operator boundary | Same-UID IPC and configured identity checks; metadata-only diagnostics; guarded pre-attempt resume; signed readback and duplicate/forgery rejection. |
| Locked macOS Nix shell | Flake check and the complete development script passed; both source and clean-install runs passed 78 tests with one unconfigured official-Buzz skip. No developer direnv trust was granted. |
| Exact runtime-head CI | [`a739867b`](https://github.com/indiebrix/buzz-agent-bridge/commit/a739867b1dae072f9b935fe93d9f44d9742aa794), [run 39782986254](https://github.com/indiebrix/buzz-agent-bridge/actions/runs/39782986254): all seven jobs passed. Final documentation and merge commits receive the same CI gate. |
| Actual installation and provider acceptance | The two release wheels were installed together; 45 installed files matched their archive members. Existing identity and configuration were retained, with one receiver/publisher and health/readiness HTTP 200. A new authorized source caused one automatic wake and one response attempt; generation 1 reached succeeded/acknowledged/delivered. Public `verify-delivery` independently re-fetched signed source/receipt evidence, exact body/routing and one matching response within 100 events. No replay, recovery or verifier publication occurred. |

The release checksums identify the exact accepted wheels. Documentation-only
closure changes do not alter their runtime members; the source inventory records
the complete release tree. This is acceptance of one installed deployment and
one new request, not a guarantee for every account or future request.

## Earlier published-head acceptance

Head `8b276ff3b843a8a9867a99d820ef3693dbc92296` has verified Alita App attribution.
[CI run 39768959729](https://github.com/indiebrix/buzz-agent-bridge/actions/runs/39768959729)
passed seven jobs: Linux/macOS package checks on Python 3.11/3.12, Linux/macOS
Nix/direnv checks, and source secret scanning. That head's macOS source suite passed
69 tests including official installed Buzz ACP; clean wheel installation passed
68 tests with one optional installed-Buzz skip.

### Recovered request

A verified request was blocked before any webhook attempt. The original failure
detail was not retained, so its historical cause is not asserted. Explicit one-time
recovery revalidated current signed source, authorization, scope and generation;
attempted, uncertain, cancelled, quarantined and completed work remained ineligible.
The same generation received one accepted wake and produced one signed relay reply.
This demonstrates recovery, separately from fresh first-attempt delivery.

### Fresh first-attempt request

A subsequent new authorized owner message triggered the webhook automatically,
without recovery or replay. One completion call reached `delivery=delivered`.
Independent read-only relay verification confirmed the expected agent identity,
channel, signed event, exact body/routing and one matching response in a bounded
100-event query. The verifier did not publish or resend any message. This proves
that request on the published candidate, not all future requests or the amended
package composition. Private identifiers and content remain outside this repository.

## Official Buzz and development environment

- Official `desktop-v0.5.28`, commit
  `f87c10895ea35a9a2cea629fef1d7532a3fecbc5`, is the compatibility target.
- A separate Rust harness compiled the byte-identical `load_rules` and rule types
  from that commit. Two tests passed: generated single-channel configuration with
  explicit mention policy loaded; malformed/unsupported configurations failed.
  This is actual Rust loader execution, not a complete Buzz workspace build.
- Signed direct/nested reply and source-marker tests cover official routing
  semantics. The installed ACP test exercises actual frontend admission with
  synthetic data; real relay acceptance is recorded separately above.
- The locked Nix input archive/NAR hash, macOS flake evaluation and Python 3.11.16
  shell were verified. Prior remote Nix jobs exercised disposable direnv trust.
  Developer-host `direnv allow` was not run. Amended scripts were also verified in the locked macOS shell.

[Upstream contracts](upstream-contracts.md) records primary source locations.

## Personal commit skill

The self-contained distribution is under `contrib/commit-skill`, outside repository
skill discovery. Installer checks cover dry-run, identical reinstall, user edits,
symlink and duplicate-root conflicts without overwrites. User-level installation
and file readback passed. Separately, a supported-model Codex invocation in an
unrelated repository discovered the installed skill and interpreted that
repository's own language/license/identity policy without committing or accessing
credentials. File installation and actual model discovery are distinct evidence.

## Earlier validation and resolved harness failures

Initial Linux Python 3.12 checks exposed umask-sensitive fixtures, unsigned receipt
acceptance and incorrect thread-marker handling. Independent baseline reproduction
preceded fixes. The 64-test Nix candidate passed on macOS, with distribution scans
and isolated offline installation. Initial cloud Nix evaluation was blocked by
missing Nix and HTTP 403; later macOS realization and remote CI resolved that gap.

The first remote macOS clean-install assertion rejected equivalent `/tmp` and
`/private/tmp` paths. Canonical containment now accepts aliases while rejecting
outside modules and symlink escapes; regression checks and later CI passed.
Earlier records and source manifests remain in the private handoff/history.

## Reproduce

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.lock
.venv/bin/python -m pip install --no-build-isolation --no-deps -e packages/chatgpt-dots -e .
umask 077
BUZZ_ACP_BINARY=/absolute/path/to/official/buzz-acp .venv/bin/python -m unittest discover -s tests -v
.venv/bin/python scripts/build_all.py
.venv/bin/python -m pip download -r requirements.lock --only-binary=:all: --dest /absolute/path/to/wheelhouse
.venv/bin/python scripts/clean_install.py dist/*.whl --constraints requirements.lock --tests tests --wheelhouse /absolute/path/to/wheelhouse
```

Run inside the locked Nix shell where available; see [development](../development.md).
Release checks additionally scan the exact source and unpacked artifacts. Optional
real macOS Keychain access is still unverified and documented as such. The connector
is a host-embedded transport component: host durability, authorization and effects
remain required. No additional provider or account entitlement is claimed.
