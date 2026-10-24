#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
venv_path="$project_root/.venv"
requirements_file="$project_root/requirements.txt"

if ! command -v uv >/dev/null 2>&1; then
  printf 'uv is required to create the isolated Python environment.\n' >&2
  exit 1
fi

if [[ ! -x "$venv_path/bin/python" ]]; then
  uv venv --python python3 "$venv_path"
fi

uv pip install --python "$venv_path/bin/python" --requirement "$requirements_file"
printf 'Python dependencies are installed in %s\n' "$venv_path"
