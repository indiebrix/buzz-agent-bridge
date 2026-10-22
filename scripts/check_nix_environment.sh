#!/usr/bin/env bash
# Run inside `nix develop`; all installation/testing state is temporary.
set -euo pipefail

python - <<'PY'
from pathlib import Path
import sys
assert sys.version_info[:2] == (3, 11), sys.version
assert str(Path(sys.executable).resolve()).startswith('/nix/store/'), sys.executable
print('Nix Python:', sys.version.split()[0])
PY
git --version
direnv version
gitleaks version
shellcheck --shell=bash .envrc scripts/check_nix_environment.sh

scratch=$(mktemp -d)
trap 'rm -rf "$scratch"' EXIT
python -m venv "$scratch/venv"
venv_python="$scratch/venv/bin/python"
"$venv_python" -m pip install -r requirements-dev.lock
"$venv_python" -m pip install --no-build-isolation --no-deps -e packages/chatgpt-dots
"$venv_python" -m pip install --no-build-isolation --no-deps -e .
umask 077
"$venv_python" -m unittest discover -s tests -v
"$venv_python" scripts/build_all.py --outdir "$scratch/dist"
"$venv_python" -m pip download -r requirements.lock --only-binary=:all: --dest "$scratch/wheelhouse"
"$venv_python" scripts/clean_install.py "$scratch"/dist/*.whl \
  --constraints requirements.lock --tests tests --wheelhouse "$scratch/wheelhouse"
