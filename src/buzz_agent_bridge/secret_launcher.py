"""Transfer already-authorized host secrets to one child without secret argv/env."""
import json
import os
import subprocess
import sys

from .config import validate_secrets


def launch_host(config_path, payload):
    child = None
    try:
        encoded = json.dumps(validate_secrets(payload)).encode()
        if len(encoded) > 8192:
            raise ValueError("Secret payload too large")
        reader, writer = os.pipe()
        try:
            child = subprocess.Popen([sys.executable, "-m", "buzz_agent_bridge.cli", "host",
                "--config", str(config_path), "--secrets-fd", str(reader)], pass_fds=(reader,),
                env={"PATH": "/usr/bin:/bin", "PYTHONDONTWRITEBYTECODE": "1"})
        except BaseException:
            os.close(writer)
            raise
        finally:
            os.close(reader)
        try:
            with os.fdopen(writer, "wb") as stream:
                stream.write(encoded)
        except BaseException:
            child.terminate()
            child.wait(timeout=5)
            raise
        finally:
            encoded = b""
    finally:
        payload.clear()
    return child.wait()
