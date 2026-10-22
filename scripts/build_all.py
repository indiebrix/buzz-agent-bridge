#!/usr/bin/env python3
"""Build and inspect both distributions with the existing pinned build tools."""
import argparse
from pathlib import Path
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--outdir', type=Path, default=Path('dist'))
    args = parser.parse_args()
    out = args.outdir.resolve()
    if out.exists() and any(out.iterdir()):
        raise SystemExit('Use a new empty output directory; existing artifacts are preserved.')
    def run(*argv):
        subprocess.run([sys.executable, *map(str, argv)], check=True)
    run('-m', 'build', '--no-isolation', '--outdir', out / 'connector', 'packages/chatgpt-dots')
    run('-m', 'build', '--no-isolation', '--outdir', out)
    run('scripts/check_distribution.py', out)
    run('scripts/check_connector.py', out / 'connector')


if __name__ == '__main__': main()
