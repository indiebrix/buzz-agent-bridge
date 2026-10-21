# Development

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -e . build
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m build
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
