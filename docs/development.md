# Development

## Nix and direnv

The preferred contributor environment is `nix develop --no-update-lock-file`.
The checked-in `flake.lock` pins one nixpkgs release archive and its NAR hash.
The same declaration provides Python 3.11, Git, direnv, Gitleaks and ShellCheck
for `x86_64-linux`, `aarch64-linux`, `x86_64-darwin` and `aarch64-darwin`.
CI exercises x86-64 Linux and arm64 macOS; the other declared architectures
remain unverified until tested. Python runtime/build dependencies are installed
from the existing lock files, separately from the pinned development tools.
This pins versions and sources, not byte-identical cross-platform wheels.

Install Nix and direnv using your host's approved setup process if absent. Nix
needs the `nix-command` and `flakes` experimental features enabled. This repository
does not install a daemon, change shell profiles, or grant directory trust.
See the official [Nix setup](https://nix.dev/install-nix.html),
[direnv shell hook](https://direnv.net/docs/hook.html) and
[flake support](https://direnv.net/man/direnv-stdlib.1.html).

Review `.envrc`, `flake.nix` and `flake.lock` first. After approving execution of
that repository code on this machine, run `direnv allow .`. This is a local trust
decision, separate from reading or syntax-checking those files; automation must
not grant it on a developer host without authorization. `direnv deny .` revokes
the directory's trust. Re-review changes to the flake and lock too: direnv's
watching/reload is not a fresh approval for every transitive input.

`.envrc` uses direnv's built-in `use flake`, prevents implicit lock updates and
watches the Python lock files. No nix-direnv plugin is required. It does not load
`.env` secrets, run pip, activate a virtualenv, or start a service. Automatic
entry requires an already installed shell hook; otherwise use `nix develop`
explicitly. The shell performs no project setup on entry.

Inside either entry path, create and activate a project-local environment, then
run the commands below. A virtualenv made with another interpreter should be
preserved or removed explicitly before recreating it; do not reuse it blindly
after changing the Nix pin. `.venv`, `.direnv` and Nix result links are ignored.

```sh
nix develop --no-update-lock-file
python -m venv .venv
source .venv/bin/activate
```

From the repository root, run Nix acceptance with:

```sh
nix flake check --no-update-lock-file
nix develop --no-update-lock-file --command bash scripts/check_nix_environment.sh
git diff --exit-code -- flake.lock
```

The script checks the actual Nix interpreter and tools, creates a temporary venv,
runs tests, builds/inspects artifacts and repeats isolated installed-wheel tests.
It uses public package downloads but no provider credentials or production relay.
`nix flake check` checks the current platform's tool derivation; it is not a
substitute for running the complete acceptance script on each target platform.
CI also checks direnv entry after granting trust only in its disposable runner
and temporary direnv configuration. That does not approve a developer's machine.

Update inputs deliberately with `nix flake update nixpkgs`; review the resulting
revision/hash and run Linux/macOS acceptance before committing the changed lock.
Python dependency updates remain explicit changes to their own lock files.
New Nix files must be Git-tracked before Git-based flake evaluation sees them.
Lock provenance and current unexecuted gates are in
[Nix validation](project/nix-development.md).

## Python-only setup and package installation

Nix is optional for package consumers. On a non-Nix host with Python 3.11+,
the following existing path remains supported. Do not call its results Nix
validation. The wheel has no Nix runtime dependency. Use Python 3.11 or 3.12 for
the tested dependency set; mini reported a coincurve build failure on Python
3.14. `requires-python` is a metadata floor, not proof for every newer interpreter.

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.lock
.venv/bin/python -m pip install --no-build-isolation --no-deps -e packages/chatgpt-dots
.venv/bin/python -m pip install --no-build-isolation --no-deps -e .
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python scripts/build_all.py
.venv/bin/python scripts/clean_install.py dist/*.whl --constraints requirements.lock --tests tests
```

Tests use generated public fixtures, temporary encrypted stores, local sockets,
mock callbacks and a mock CLI. They never read a vault or contact a production
relay. On a host with Buzz installed, set `BUZZ_ACP_BINARY` to its `buzz-acp`
executable to include the installed-protocol gate. Without it, that gate skips.
Some sandboxed environments need permission to bind local Unix/loopback sockets.

Keychain tests replace every Security query with a mock. The macOS-only ABI test
loads framework symbols and builds CoreFoundation values, but replaces
`SecItemCopyMatching` before use and never obtains a real Keychain reference. This
does not prove first-run consent, real item accessibility, or behavior on every
macOS release. Do not add a real-item test to the default suite. A separate manual
acceptance test needs explicit approval for its dedicated item names and actions.

The package imports no vault SDK and opens no network connection on import. Keep
device supervisors, personal paths, real public keys, channel IDs, ledger files,
and provider credentials outside the product tree.

## Before a release

Run the tests on the intended Python/platform combination and inspect both wheel
and source archive. Run a secret scanner such as Gitleaks against the exact release
tree, and manually review the files, dependency licenses, examples, and attribution.
Do not widen scanner exceptions to make a finding disappear.

The public package is a configurable extraction of a privately exercised runtime.
Passing local tests is not proof of a clean install's remote authentication,
subscription lifecycle, or delivery. Record those outcomes separately after an
authorized real end-to-end test.

Repository publication must use the approved maintainer/bot identity and signing
method. Verify the remote commit's attribution and signature result. Package
registry publication is a separate operation; do not imply a PyPI release merely
because a GitHub repository exists.

## Reproducible acceptance

Use a clean `dist` directory for each candidate. The artifact checker inspects
wheel/sdist members, MIT metadata, version coherence and expected modules. The
clean-install script creates a second environment outside the checkout (including
a space in its path), installs only the wheel under runtime constraints, and runs
public setup, doctor, receiver-config and ACP discovery with a clean environment.
It does not contact a provider or load a real credential.

Run the tests under `umask 077` as CI does. Permission rejection fixtures explicitly
set the intended mode so host umask cannot accidentally turn a negative case into
a safe directory. CI is read-only and uses pinned action revisions, Python 3.11/3.12
on Linux/macOS, plus built-wheel smoke checks. A checked-in workflow has not run
until GitHub records a successful run on the proposed commit.

Set `BUZZ_ACP_BINARY` to an independently obtained official executable to run the
real local ACP gate. The test uses synthetic input and loopback only. Full Rust
receiver-file loading and live Dot/relay acceptance are distinct gates; see
[upstream contracts](project/upstream-contracts.md) and [validation](project/validation.md).

Follow this project's [release policy](releases/policy.md) for Issue/PR/tag linkage,
strict SemVer and approved release identity. These requirements apply regardless
of which user-level tools are installed.

For a fully offline clean-install phase, predownload the pinned runtime wheels in
an approved build environment and pass `--wheelhouse /absolute/path/to/wheelhouse`
to `scripts/clean_install.py`. The installer then uses `--no-index` and a clean
environment, without inheriting personal pip configuration or injected secrets.
The copied tests/examples exercise the installed wheel; no source tree is copied.
