#!/usr/bin/env python3
"""Inspect actual wheel and sdist members and version/license coherence."""
import argparse
import ast
from email.parser import BytesParser
import json
from pathlib import Path, PurePosixPath
import tarfile
import zipfile


def check_names(names):
    for name in names:
        p = PurePosixPath(name)
        assert not p.is_absolute() and '..' not in p.parts, name
        assert not any(x in p.parts for x in ('.git','.venv','.direnv','__pycache__','state')), name
        assert not p.name.endswith(('.pyc','.sqlite3','.db','.log','.pem','.key')), name
        assert p.name not in ('.env','bridge.json'), name


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    args=parser.parse_args()
    wheels=list(args.directory.glob('*.whl')); sources=list(args.directory.glob('*.tar.gz'))
    assert len(wheels)==len(sources)==1, 'Use a clean artifact directory'
    with zipfile.ZipFile(wheels[0]) as archive:
        names=archive.namelist(); check_names(names)
        for file in ('core/broker.py','core/contracts.py','adapters/buzz/source.py',
                     'adapters/buzz/publisher.py','adapters/chatgpt/events.py',
                     'adapters/chatgpt/wake.py','broker.py','events.py','transports.py'):
            assert 'buzz_agent_bridge/'+file in names, file
        metadata=BytesParser().parsebytes(archive.read(next(n for n in names if n.endswith('/METADATA'))))
        assert metadata['License-Expression']=='MIT'
        assert any(n.endswith('/licenses/LICENSE') for n in names)
        tree=ast.parse(archive.read('buzz_agent_bridge/__init__.py'))
        runtime=next(ast.literal_eval(n.value) for n in tree.body if isinstance(n,ast.Assign)
                     and any(isinstance(t,ast.Name) and t.id=='VERSION' for t in n.targets))
        assert runtime==metadata['Version']
        assert 'chatgpt-dots-connector==1.0.0' in metadata.get_all('Requires-Dist', [])
        assert not any(n.startswith('chatgpt_dots/') for n in names), 'Independent package must not be vendored'
        assert not any(n.startswith(('tests/','.agents/','scripts/')) for n in names)
        wheel_count=len(names)
    with tarfile.open(sources[0]) as archive:
        members=archive.getmembers(); check_names(m.name for m in members)
        assert all(m.isdir() or m.isfile() for m in members), 'No linked/special files'
        names=[str(PurePosixPath(m.name).relative_to(PurePosixPath(m.name).parts[0])) for m in members]
        for name in ('LICENSE','README.md','requirements.lock','requirements-dev.lock',
                     'contrib/commit-skill/commit/SKILL.md','docs/releases/migration-1.0.md',
                     'scripts/clean_install.py','tests/test_portable_contracts.py',
                     'flake.nix','flake.lock','.envrc','scripts/check_nix_environment.sh'):
            assert name in names, name
        assert not any(n.startswith('.agents/skills/') for n in names)
        metadata=BytesParser().parsebytes(archive.extractfile(next(m for m in members if m.name.count('/')==1 and m.name.endswith('/PKG-INFO'))).read())
        assert metadata['Version']==runtime
        source_count=len(members)
    print(json.dumps({'distribution':'passed','version':runtime,
                      'wheel_members':wheel_count,'sdist_members':source_count,'license':'MIT'}))


if __name__=='__main__': main()
