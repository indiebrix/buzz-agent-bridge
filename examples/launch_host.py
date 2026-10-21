"""Example: consume two existing secret-manager-injected values; never print them."""
import os
import sys

from buzz_agent_bridge.secret_launcher import launch_host


def main():
    if len(sys.argv) != 2:
        print("Usage: launch_host.py /absolute/path/bridge.json", file=sys.stderr)
        return 2
    try:
        payload = {"storage_key": os.environ.pop("BRIDGE_STORAGE_KEY"),
                   "mcp_token": os.environ.pop("BRIDGE_MCP_TOKEN")}
    except KeyError:
        print("Inject the approved storage key and MCP token first.", file=sys.stderr)
        return 2
    return launch_host(sys.argv[1], payload)


if __name__ == "__main__":
    raise SystemExit(main())
