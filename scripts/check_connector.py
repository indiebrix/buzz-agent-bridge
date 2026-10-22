#!/usr/bin/env python3
"""Inspect and install the independent connector with no Buzz runtime present."""
import argparse
import ast
from email.parser import BytesParser
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile
import venv
import zipfile

from check_distribution import check_names


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    parser.add_argument('--example', type=Path, default=Path('examples/non_buzz_connector.py'))
    args = parser.parse_args()
    wheels, sources = list(args.directory.glob('*.whl')), list(args.directory.glob('*.tar.gz'))
    assert len(wheels) == len(sources) == 1
    with zipfile.ZipFile(wheels[0]) as archive:
        names = archive.namelist(); check_names(names)
        metadata = BytesParser().parsebytes(archive.read(next(n for n in names if n.endswith('/METADATA'))))
        assert metadata['Name'] == 'chatgpt-dots-connector' and metadata['License-Expression'] == 'MIT'
        assert not metadata.get_all('Requires-Dist')
        assert any(n.endswith('/licenses/LICENSE') for n in names)
        for name in names:
            assert not name.startswith(('buzz_agent_bridge/', 'tests/', 'examples/'))
            if name.endswith('.py'):
                tree = ast.parse(archive.read(name))
                imports = {n.module.split('.')[0] for n in ast.walk(tree)
                           if isinstance(n, ast.ImportFrom) and n.module and n.level == 0}
                imports |= {a.name.split('.')[0] for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
                assert not imports & {'buzz_agent_bridge', 'acp', 'coincurve'}
    with tarfile.open(sources[0]) as archive:
        check_names(m.name for m in archive.getmembers())
        assert all(m.isfile() or m.isdir() for m in archive.getmembers())
    with tempfile.TemporaryDirectory(prefix='dots-install-', dir='/tmp') as temporary:
        root = Path(temporary).resolve()
        environment = root / 'clean connector venv'
        venv.EnvBuilder(with_pip=True).create(environment)
        python = environment / 'bin/python'
        clean_env = {'PATH': '/usr/bin:/bin', 'HOME': str(root), 'PYTHONNOUSERSITE': '1',
                     'PIP_DISABLE_PIP_VERSION_CHECK': '1'}
        def run(argv):
            result = subprocess.run([str(x) for x in argv], cwd=root, env=clean_env,
                                    capture_output=True, text=True, timeout=60)
            if result.returncode:
                raise RuntimeError(result.stderr)  # Synthetic/offline test processes only.
            return result.stdout
        run([python, '-m', 'pip', 'install', '--no-index', '--no-deps', wheels[0].resolve()])
        run([python, '-m', 'pip', 'check'])
        result = json.loads(run([python, '-I', '-c',
            'import importlib.util,json,chatgpt_dots; from importlib.metadata import version; '
            'assert all(importlib.util.find_spec(n) is None for n in ("buzz_agent_bridge","acp","coincurve")); '
            'assert version("chatgpt-dots-connector")==chatgpt_dots.VERSION; '
            'print(json.dumps({"version":chatgpt_dots.VERSION,"module":chatgpt_dots.__file__}))']))
        assert Path(result['module']).resolve().is_relative_to(environment.resolve())
        example = root / 'non_buzz_connector.py'
        shutil.copyfile(args.example.resolve(), example)
        evidence = json.loads(run([python, '-I', example]))
        assert evidence['non_buzz_integration'] == 'passed' and evidence['remote_dot_acceptance'] is False
        print(json.dumps({'independent_install': 'passed', 'version': result['version'],
                          'buzz_installed': False, **evidence}, sort_keys=True))


if __name__ == '__main__': main()
