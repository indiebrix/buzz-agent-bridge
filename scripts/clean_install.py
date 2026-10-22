#!/usr/bin/env python3
"""Install a built wheel outside the checkout and exercise secret-free setup."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import tomllib
import venv


def assert_installed_location(module, environment):
    # macOS may report /private/tmp while a temporary path uses the /tmp alias.
    # Resolve both sides, retaining the rejection of links outside the venv.
    assert Path(module).resolve(strict=True).is_relative_to(
        Path(environment).resolve(strict=True)), 'Installed module escaped the clean environment'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('wheel', type=Path)
    parser.add_argument('--constraints', type=Path, required=True)
    parser.add_argument('--tests', type=Path, help='Copy and run the synthetic suite outside the checkout')
    parser.add_argument('--wheelhouse', type=Path, help='Install offline from predownloaded dependency wheels')
    parser.add_argument('--connector-wheel', type=Path, help='Matching independent connector wheel')
    args = parser.parse_args()
    wheel, constraints = args.wheel.resolve(strict=True), args.constraints.resolve(strict=True)
    connectors = [args.connector_wheel.resolve(strict=True)] if args.connector_wheel else list(
        (wheel.parent / 'connector').glob('chatgpt_dots_connector-*.whl'))
    assert len(connectors) == 1, 'Provide exactly one connector wheel'
    with tempfile.TemporaryDirectory(prefix='bab-install-', dir='/tmp') as temporary:
        root = Path(temporary).resolve(strict=True)
        environment = root / 'clean venv'
        venv.EnvBuilder(with_pip=True).create(environment)
        python = environment / 'bin/python'
        command = environment / 'bin/buzz-agent-bridge'
        # No user config, signing key, provider token, PYTHONPATH or injected secrets.
        clean_env = {'PATH': '/usr/bin:/bin', 'HOME': str(root),
                     'PIP_DISABLE_PIP_VERSION_CHECK': '1', 'PYTHONNOUSERSITE': '1'}
        def run(argv, stdin=None):
            return subprocess.run([str(x) for x in argv], cwd=root, env=clean_env,
                input=stdin, capture_output=True, text=True, check=True, timeout=120).stdout
        install_args = [python, '-m', 'pip', 'install', '-c', constraints]
        if args.wheelhouse:
            install_args += ['--no-index', '--find-links', args.wheelhouse.resolve(strict=True)]
        run([*install_args, connectors[0], wheel])
        run([python, '-m', 'pip', 'check'])
        installed = json.loads(run([python, '-I', '-c',
            'import json,buzz_agent_bridge as b; from importlib.metadata import version; '
            'assert version("buzz-agent-bridge")==b.VERSION; '
            'print(json.dumps({"version":b.VERSION,"module":b.__file__}))']))
        assert_installed_location(installed['module'], environment)
        assert run([command, '--version']).strip() == installed['version']
        config = root / 'bridge.json'
        harness = json.loads(run([command, 'harness', '--config', config]))
        assert harness['env'] == {} and harness['command'] == str(command)
        assert not config.exists()
        run([command, 'init', '--output', config,
             '--relay-url', 'https://relay.example.invalid',
             '--owner-pubkey', 'ab' * 32, '--agent-pubkey', 'cd' * 32,
             '--channel', '11111111-1111-4111-8111-111111111111',
             '--state-directory', root / 'state', '--buzz-cli', python])
        assert config.stat().st_mode & 0o777 == 0o600
        run([command, 'check-config', '--config', config])
        doctor = json.loads(run([command, 'doctor', '--config', config]))
        assert doctor['configuration'] == 'valid' and doctor['state_directory_safe']
        assert not any(doctor[x] for x in ['runtime_checked','credentials_checked','network_checked'])
        output = root / 'receiver.toml'
        receiver = json.loads(run([command, 'receiver-config', '--config', config, '--output', output]))
        rule, = tomllib.loads(output.read_text())['rules']
        assert rule['kinds'] == [9] and rule['require_mention'] is True
        assert rule['channels'] == ['11111111-1111-4111-8111-111111111111']
        assert receiver['required_buzz_author_gate'] == 'owner-only'
        discovery = json.loads(run([command, 'managed', '--config', root / 'absent.json'],
            json.dumps({'jsonrpc':'2.0','id':1,'method':'initialize','params':{'protocolVersion':1}})+'\n'))
        assert discovery['result']['agentInfo']['name'] == 'buzz-agent-bridge'
        assert not (root / 'state').exists()
        suite = 'not requested'
        if args.tests:
            shutil.copytree(args.tests.resolve(strict=True), root / 'tests',
                            ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
            # The source suite also verifies the distributable launcher example.
            shutil.copytree(args.tests.resolve().parent / 'examples', root / 'examples',
                            ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
            completed = subprocess.run([str(python), '-m', 'unittest', 'discover', '-s', 'tests', '-v'],
                cwd=root, env=clean_env, capture_output=True, text=True, timeout=120)
            if completed.returncode:
                raise RuntimeError(completed.stderr)
            suite = completed.stderr.strip().splitlines()[-1]
            print('\n'.join(completed.stderr.strip().splitlines()[-4:]))
        print(json.dumps({'clean_install':'passed','version':installed['version'],
                          'working_directory':'outside checkout', 'credentials_used':False,
                          'installed_suite':suite, 'provider_acceptance':'not tested'}))


if __name__ == '__main__': main()
