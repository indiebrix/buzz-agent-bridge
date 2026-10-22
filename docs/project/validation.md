# Validation record

Candidate: 1.0.0, based on `694642933a791c20d9d85254cd9b61afc3ae5be8`.
Initial validation environment: Linux x86-64, CPython 3.12.14. Fixtures are synthetic.
All local checks below completed before the publication handoff; remote acceptance
is deliberately separate.

## Subsequent macOS acceptance (2026-10-22)

The Nix-amended candidate was independently materialized and checked on macOS
arm64. Its 84 source hashes and 17-file amendment matched the reviewed handoff.
The pinned Nix archive and NAR hash were verified; `nix flake check
--no-update-lock-file` passed. The locked Python 3.11.16 shell passed all 64 source
tests, including the installed official Buzz ACP gate, plus package build and
isolated wheel installation checks. Source and distribution scans found no
secrets. Developer-host `direnv allow` was not executed.

A separate Rust harness compiled the byte-identical `load_rules` function and
rule types from official Buzz `desktop-v0.5.28`, commit
`f87c10895ea35a9a2cea629fef1d7532a3fecbc5`. Two tests passed: candidate-generated
synthetic single-channel TOML loaded, and malformed or unsupported configuration
was rejected. This is not a build of the entire Buzz workspace or a live receiver
and relay test.

Product runtime, product tests, dependencies and Nix inputs remain identical to
that candidate. Publication documentation and the CI installation harness have
subsequent changes recorded below.
Remote CI on the draft head is recorded on GitHub. Candidate live Dot/relay
acceptance is still blocked by the acceptance deployment's missing managed-agent
configuration. Previous-version live results are not reused. Optional real macOS
Keychain credential access and other platform acceptance remain separate gates.

The following sections retain the original Linux evidence and its environment
limits; later macOS results above supersede its pending macOS/Nix statements.

## Baseline evidence

- Pinned editable install succeeded in a fresh virtual environment.
- Initial suite: 54 tests, two failures, two skips. Both failures came from tests
  requesting mode 0755 under umask 077, which actually created mode 0700.
- Baseline with umask 022 and official Buzz binary: 54 tests, no failures,
  one macOS-only skip. The local installed ACP gate passed.
- Independent baseline reproduction: acceptance plus an event ID without signed
  readback incorrectly set `delivery=delivered`; incoming reply-only markers were
  rejected and root-only markers returned the foreign root. New regressions cover
  these observed failures.

## Current checks

Commands run in the development virtual environment with pinned runtime/build
constraints; the optional installed gate uses official Buzz desktop-v0.5.28.

| Check | Outcome |
| --- | --- |
| Full unit/integration/crash suite | 64 run: 63 passed, 1 macOS-only skip; official Buzz ACP gate included. |
| Restrictive and ordinary umask | 63-test suite passed under 077 and 022; final 64-test suite passed under 077. |
| Wheel/sdist build and inventory | Passed: 1.0.0; 36 wheel members, 104 sdist members; MIT/version/modules verified. |
| Wheel installation outside checkout | Passed offline with pinned dependency wheels, clean environment and space-containing path. Installed suite: 64 run, 62 passed, 2 skips (Buzz gate not supplied and macOS-only). |
| Gitleaks exact source/artifacts/patch | v8.24.3 with verified download checksum; final source, unpacked distributions and patch scanned with no findings. No exclusions added. |
| Commit skill validator | Passed for the self-contained user-level source; actual mini installation/discovery pending. |
| Independent skill scenarios | Passed docs-only/no bump, strict 0.x major, App-only publishing, tag conflict and uncertain write handling; generic source now discovers each repository's policy instead of requiring a fixed path. |
| Official-source review | [Recorded](upstream-contracts.md) |
| GitHub workflow runs | Not run; workflow prepared only |

Do not substitute these checks for a live provider test. The Rust receiver loader
is source-reviewed but not executed through a connected relay. macOS real Keychain
access, clean macOS/3.11 installations for this candidate, authentication/tunnel,
real existing-Dot subscription and one newly authorized private-channel round trip
remain external acceptance gates. No mini deployment was touched.

## Reproduction commands

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.lock
.venv/bin/python -m pip install --no-build-isolation --no-deps -e .
umask 077
BUZZ_ACP_BINARY=/absolute/path/to/official/buzz-acp .venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m build --no-isolation
.venv/bin/python scripts/check_distribution.py dist
.venv/bin/python -m pip download -r requirements.lock --only-binary=:all: --dest /absolute/path/to/wheelhouse
.venv/bin/python scripts/clean_install.py dist/*.whl --constraints requirements.lock --tests tests --wheelhouse /absolute/path/to/wheelhouse
```

The first clean-environment online pip attempt failed. The successful path used
predownloaded public dependency wheels and `--no-index`; it did not inherit user
pip settings, credentials or proxy variables. Both setup smoke and the copied
full suite then exercised the installed wheel outside the checkout. An initial
copy omitted the launcher example and a mock CLI used an unquoted Python shebang;
those harness assumptions were corrected, and the full isolated suite passed.

The baseline wire-schema snapshot was generated from the exact public baseline,
not from the new implementation. Independent reproduction against that baseline
confirmed the unsigned-receipt and thread-marker defects before the fixes.

The final source-tree/patch/archive hashes belong in the external handoff manifest
to avoid a self-referential hash inside the patch. Remote CI, App attribution and
Issue/PR/tag/Release readback must be recorded by the publishing session.

## User-level skill distribution amendment

No product runtime changed for this amendment. The active repository skill was
removed and a self-contained source moved to `contrib/commit-skill`. Static skill
validation and installer sandbox checks cover read-only preflight, successful copy,
idempotent reinstall, conflicting personal edits and a same-name symlink in a
second discovery root. Existing files remain intact on conflicts. The final source
distribution and handoff were rebuilt, inventoried and scanned after this change.
An independent dry-run of the generic skill also preserved another repository's
BSD license, German language and own service identity, with no fixed policy-file
dependency. Actual mini installation, host selector uniqueness and invocation
remain pending for the installing parent. No global registration is claimed.

## Version 2: Nix/direnv amendment revalidation

The following checks were executed again after adding the flake, lock, hook,
CI declaration and distribution changes on 2026-10-22. They do not inherit the
version-1 pass claim. Cloud Python remains 3.12.14; the Nix shell declares 3.11.16.

| Check | Version-2 result |
| --- | --- |
| Source suite, umask 077, official Buzz binary | 64 run: 63 passed, 1 macOS-only skip |
| Rebuilt wheel, isolated offline install and copied tests | 64 run: 62 passed, 2 environment skips; setup/doctor/discovery passed |
| Wheel/sdist members, version and MIT license | Passed; source includes Nix files, wheel remains Python-only |
| Nix grammar | tree-sitter-nix 0.1.0 / tree-sitter 0.26.0 passed; not Nix evaluation |
| Shell static checks | Bash syntax and ShellCheck 0.11.0 passed for .envrc and Nix acceptance script |
| Workflow/action references | YAML parsed; action refs are full commit SHAs |
| Input provenance | nixpkgs node exactly matches official Nix lock at recorded commit |
| Nix evaluation/build/direnv | Not run: executables absent in cloud; no system install or local trust grant |
| NAR rehash | Not run: pinned archive download returned HTTP 403 |

Version 2 adds a Linux/macOS Nix CI job but no remote run is claimed. Mini's
reported macOS/Python 3.11 version-1 result is preserved separately in
[nix-development.md](nix-development.md); it does not prove this amendment's
Nix acceptance. Handoff manifests record exact final scan and patch/delta
application/hash results. The standalone skill source has not changed.

## First remote CI and installation-harness correction

[Initial CI run](https://github.com/indiebrix/buzz-agent-bridge/actions/runs/39761929947)
on the initial review commit passed both Linux package jobs, both Nix jobs
(Linux and macOS, including disposable direnv), and the secret scan. Both macOS
package jobs passed source tests/build but failed the clean-install path assertion.
The installed module and its temporary virtual environment used equivalent
`/private/tmp` and `/tmp` spellings.

The installation harness now canonicalizes the temporary root and compares
resolved module/environment paths. Two added regression checks accept an alias to
the same environment and reject both an outside module and a symlink escape.
Those checks pass locally and run in each package CI job. Runtime security checks
are unchanged. The follow-up head's complete remote result must be read from the
PR; the initial failed run is not reported as a full pass.

The corrected harness was then executed on macOS against a freshly rebuilt wheel:
installation outside the checkout passed, and its copied suite ran 64 tests with
63 passes and one optional installed-Buzz skip. The two containment regressions
also passed. Distribution inspection retained MIT and version 1.0.0. No provider
credentials, operational messages or running deployment were used.
