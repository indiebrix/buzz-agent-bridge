# Installation

## Requirements and scope

Use a Unix host. The deployment path was developed against Buzz Desktop 0.5.28;
Windows is not supported by the Unix-socket and process-lock implementation.
Use Python 3.11 or newer. The configurable package has a clean installation check
on Python 3.11/macOS arm64; the original runtime was validated on Python 3.14.8.
The ACP SDK is pinned to 0.12.1. Build prerequisites for `coincurve` depend on your Python
and platform; use a supported wheel or follow the dependency's official build
instructions instead of weakening signature verification.

This guide uses one managed Buzz identity, one owner, one private channel, and one
existing ChatGPT Dot. Do not run a second receiver or publisher for that identity.
Keep existing working configuration and encrypted state available for rollback.

## 1. Install the package

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -c requirements.lock .
```

Use the resulting absolute `buzz-agent-bridge` executable path in Buzz. Do not put
credentials in its command-line arguments or the custom harness definition.

## 2. Register the custom harness and managed agent

In Buzz, open **Settings → Agents → Agent runtimes → Add runtimes** and add a
custom ACP harness:

- Name: `Buzz Agent Bridge`
- ID: `buzz-agent-bridge`
- Command: the absolute path to `.venv/bin/buzz-agent-bridge`
- Arguments: `managed`, `--config`, the absolute path to your future `bridge.json`
- Environment: no credentials

Model discovery works before this configuration file or an agent identity exists.
Create a managed agent with your chosen display name, select this harness and the
`ChatGPT Dot` model, set **owner-only** access, and use one instance. Leave automatic
start off until setup is verified. Buzz creates and stores its managed key using
its own secret-store policy; inspect that policy for your platform. This package
does not provide a 1Password-only replacement for Buzz's managed secret store.

Add the managed agent to your private test channel. Record only its **public** key,
the owner's public key, and the channel identifier for the next step.

## 3. Configure the deployment

Copy `examples/bridge.json.example` outside the checkout. Replace every placeholder
with your own values. Use an absolute, short state path owned by the current user;
the state directory must have mode `0700`. Keep configuration non-world-writable
(recommended `0600`). `buzz_cli` is the official Buzz executable that supports
`messages send`; `relay_url` is that deployment's HTTPS origin.

```sh
chmod 600 /absolute/path/bridge.json
.venv/bin/buzz-agent-bridge check-config --config /absolute/path/bridge.json
```

This command validates structure only. It does not authenticate or contact a relay.
Alternatively, `buzz-agent-bridge init --output /absolute/path/bridge.json` asks for
the public values and writes the correct file permissions without overwriting any
existing configuration. `doctor --config ...` checks executable and state paths
without prompting for secrets or connecting to the network.

## 4. Start the durable host

### Receiver behavior

The host's configured channel does not configure the separate Buzz receiver.
By default, the managed `buzz-acp` receiver requires mentions. To receive the
configured owner's messages without mentions in exactly one channel, run:

```sh
buzz-agent-bridge receiver-config --config /absolute/path/bridge.json \
  --output /absolute/path/receiver.toml --receive owner-messages
```

The helper validates the existing public configuration and channel UUID, creates
a new owner-only `0600` file, and prints the two environment settings to apply.
It refuses an existing output or symlink and never contacts Buzz or a secret store.
The file uses the `[[rules]]` syntax read by Buzz 0.5.28's `load_rules` function:

```toml
[[rules]]
name = "bridge-channel"
channels = ["11111111-1111-4111-8111-111111111111"]
kinds = [9]
require_mention = false
```

The UUID above is synthetic. Use the generated file for your deployment. In that
agent's **Edit → Advanced → Environment variables**, set `BUZZ_ACP_SUBSCRIBE` to
`config` and `BUZZ_ACP_CONFIG` to the generated absolute path. Keep the existing
owner-only author setting, single instance, and channel membership. Do not add
reserved identity/author-gate environment variables or edit managed-agent storage.
Do not put these settings in global agent defaults. Config mode scopes channels
through its rules; `--channels` alone is not a substitute for a scoped rule.

Save and restart only the selected agent if a restart has not already happened.
A running receiver does not automatically reload this TOML. Keep the durable host
running so the existing identity handoff succeeds. No extra receiver or publisher
is needed. Creating the file is not proof that the live receiver uses it.

After restart, check that the receiver reports `subscribe=Config`, `respond_to=owner-only`,
one instance, and the expected channel rule. Send one **new**, authorized owner
message without a mention and verify its request ID/generation, completion, and
signed relay reply. Do not replay an old message. Local helper tests validate file
generation and boundaries; they do not replace this real acceptance test.

To restore mention-only behavior, generate a different output with `--receive mentions`,
apply that path and restart the same agent. Alternatively restore the exact previous
two environment settings. Keep keys, the host ledger, subscriptions, and history.

The pinned upstream [README](https://github.com/block/buzz/blob/f87c10895ea35a9a2cea629fef1d7532a3fecbc5/crates/buzz-acp/README.md)
shows a `[channel.UUID]` example, but that version's
[parser](https://github.com/block/buzz/blob/f87c10895ea35a9a2cea629fef1d7532a3fecbc5/crates/buzz-acp/src/config.rs)
reads a `rules` array. This helper follows the parser. Recheck the installed Buzz
version and parser when upgrading; an empty rules list can silently receive nothing.

### Host startup

Provision a 32-byte encryption key and a high-entropy MCP bearer token through your
approved secret manager. Do not commit them or send them in chat. The host accepts
their JSON representation only over an inherited anonymous pipe:

```json
{"storage_key": "<64 hexadecimal characters>", "mcp_token": "<high-entropy token>"}
```

`examples/launch_host.py` illustrates a launcher that consumes already-injected
`BRIDGE_STORAGE_KEY` and `BRIDGE_MCP_TOKEN`, removes them from its environment, and
sends them to the host through that pipe. The example does not create credentials,
read a vault, install a service, or configure a tunnel.

Start the host, then start the managed agent in Buzz within 180 seconds. Buzz passes
its managed signing key and owner attestation to the launcher. They go over an
owner-only Unix socket into host memory. The ACP frontend is then executed with a
clean environment and no signing credentials. The host checks the exact managed
identity and current channel membership before serving jobs.

The MCP listener binds only to `127.0.0.1:<mcp_port>`. Provide your own approved HTTPS
reverse proxy or tunnel, preserving authorization and the expected Host header.
The bridge does not configure public exposure. Do not disable authentication.

### Secret sources and 1Password-free setup

1Password is optional. Neither the package nor `examples/launch_host.py` imports
a 1Password SDK or invokes `op`. The following interfaces are implemented:

| Source/interface | What is included |
| --- | --- |
| Existing environment injection | `launch_host.py` consumes `BRIDGE_STORAGE_KEY` and `BRIDGE_MCP_TOKEN`, removes them from its environment, and passes their values to the child over a pipe. |
| Custom launcher with an anonymous pipe | The host accepts the documented two-field JSON on `--secrets-fd`; the argument contains a descriptor number, never a secret. |
| Existing 1Password CLI setup | An optional `op run` example and reference-only environment template; install and authorize the CLI separately if you choose it. |
| macOS default Keychain | Optional `host-keychain` reads two exact, dedicated generic-password items and uses the same pipe launcher. Mock-tested; real Keychain acceptance is pending. |
| Other OS stores or secret managers | An approved external launcher can retrieve values and feed either interface. Direct Windows/Linux store adapters are not included. |

For a 1Password-free deployment, use your existing approved environment injector
to supply the two variable names, then run:

```sh
.venv/bin/python examples/launch_host.py /absolute/path/bridge.json
```

Do not put literal values before this command, in shell history, or in a repository
`.env` file. Provision values through your chosen store's secure workflow first.
The bridge does not generate credentials or install a secret provider. Passing the
launcher test verifies the transfer contract; it does not certify an external
injector's storage, authentication, or process-environment protections.

This choice is separate from the managed Buzz signing key. Buzz owns that key's
persistence, including its platform Keychain/fallback policy, regardless of which
source supplies the bridge's two host secrets.

For the optional macOS reader, follow [macOS Keychain setup](macos-keychain.md).
The explicit command selects that source for one launch; neither `init` nor
`doctor` reads Keychain items, and existing environment/pipe deployments keep their
current behavior.

## 5. Connect the existing ChatGPT Dot

Use the official [custom MCP plugin registration guide](https://developers.openai.com/plugins/deploy/connect-chatgpt)
and [MCP Events guide](https://developers.openai.com/plugins/build/mcp-events).
Register the approved HTTPS `/mcp` URL with the host's bearer token. Confirm that
all five tools listed in [the job contract](architecture.md#job-contract) are
available in the actual target conversation.

Subscribe to `buzz.message.created` with `arguments.channel` set to your exact test
channel. Configure an event automation in the existing Dot to:

1. Call `buzz_jobs_pending`, verify the source, and use the returned request ID and
   current generation.
2. Record execution through `buzz_job_start` with the real remote execution ID.
3. Answer with `buzz_job_complete`, then check `buzz_job_status` until delivery is
   confirmed or requires explicit reconciliation. Never equate `queued` with
   `delivered`; never use a second direct-send path.

Availability of MCP Events and custom plugins varies by account. If this interface
is unavailable, setup is incomplete; this package does not fall back to private
session scraping or copied browser credentials.

## 6. Verify and operate

Send one new owner-authored mention in the test channel. Check that one job appears,
one completion is recorded, and `delivery=delivered` includes a reply event ID.
Confirm that the relay event has the expected agent signature, body, channel, and
thread routing, and that the visible reply appears once. Check that one receiver
and one broker/publisher are running.

Do not replay old source events to test a cutover. Stop the old receiver before
starting a replacement. If a publication becomes `uncertain`, inspect the relay
first; do not retry or create another completion to hide the uncertainty.

Back up the encrypted state and preserve its encryption key separately. Restored
state needs explicit operator review; copying a database back cannot prove that
external messages were undone. A provider change requires a separate state
directory. See [security](../SECURITY.md) for remaining operational limitations.
