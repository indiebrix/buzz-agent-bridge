#!/usr/bin/env python3
"""Check a standalone commit skill and optionally install it without overwriting."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys


SOURCE = Path(__file__).resolve().parent / 'commit'


def inventory(directory):
    result = {}
    for path in directory.rglob('*'):
        if path.is_symlink():
            raise ValueError('Skill payload must not contain symlinks')
        if path.is_file():
            result[str(path.relative_to(directory))] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


def named_commit(path):
    try:
        text = path.read_text(encoding='utf-8')
    except (OSError, UnicodeError):
        return False
    if not text.startswith('---\n'):
        return False
    frontmatter = text.split('---', 2)[1]
    return re.search(r'''(?m)^name:\s*(?:commit|"commit"|'commit')(?:\s+#.*)?\s*$''', frontmatter) is not None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--skills-root', type=Path, required=True,
                        help='Confirmed user-level skill root on the consuming machine')
    parser.add_argument('--check-root', action='append', type=Path, default=[],
                        help='Additional discovery root to check; repeat for repo/admin/legacy roots')
    parser.add_argument('--apply', action='store_true', help='Install only after a clean check')
    args = parser.parse_args()
    root = args.skills_root.expanduser().absolute()
    if not args.skills_root.expanduser().is_absolute():
        parser.error('--skills-root must be absolute')
    if any(not p.expanduser().is_absolute() for p in args.check_root):
        parser.error('--check-root must be absolute')
    expected = json.loads((SOURCE.parent / 'manifest.json').read_text())['skill_files']
    if inventory(SOURCE) != expected or not named_commit(SOURCE / 'SKILL.md'):
        raise ValueError('Skill payload checksum/name mismatch')
    target = root / 'commit'
    roots = list(dict.fromkeys([root, *[p.expanduser().absolute() for p in args.check_root]]))
    conflicts = []
    identical = target.is_dir() and not target.is_symlink() and inventory(target) == expected
    for discovery in roots:
        if not discovery.exists():
            continue
        if not discovery.is_dir():
            raise ValueError('Discovery root is not a directory')
        for entry in discovery.iterdir():
            if named_commit(entry / 'SKILL.md'):
                if entry == target and identical:
                    continue
                conflicts.append(str(entry / 'SKILL.md'))
    if (target.exists() or target.is_symlink()) and not identical and str(target / 'SKILL.md') not in conflicts:
        conflicts.append(str(target))
    result = {'target':str(target), 'checked_roots':[str(p) for p in roots],
              'conflicts':conflicts, 'status':'already identical' if identical else 'ready',
              'installed':False, 'runtime_discovery_verified':False}
    if conflicts:
        result['status']='blocked: preserve existing skills and resolve duplicates first'
        print(json.dumps(result,indent=2)); return 2
    if args.apply and not identical:
        root.mkdir(parents=True,exist_ok=True)
        # Exclusive mkdir refuses a competing install; no overwrite/remove path exists.
        target.mkdir(mode=0o700)
        for relative in sorted(expected):
            destination=target/relative; destination.parent.mkdir(parents=True,exist_ok=True)
            with destination.open('xb') as stream:
                stream.write((SOURCE/relative).read_bytes())
        if inventory(target) != expected:
            raise ValueError('Installed checksum mismatch; preserve partial target for review')
        result.update(status='installed on this machine; runtime discovery still pending',installed=True)
    print(json.dumps(result,indent=2)); return 0


if __name__=='__main__':
    try:
        raise SystemExit(main())
    except (OSError,ValueError,KeyError) as error:
        print(f'Install stopped: {type(error).__name__}; inspect destination before retrying.',file=sys.stderr)
        raise SystemExit(1)
