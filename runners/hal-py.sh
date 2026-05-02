#!/usr/bin/env bash
# hal-py runner stub — invokes the Python idiom library.
# Plug in once hal-py exposes a `python -m hal_py.run` CLI.

set -euo pipefail

if ! command -v python3 >/dev/null 2>&1; then
  printf 'python3 required\n' >&2
  exit 2
fi

if ! python3 -c "import hal_py" 2>/dev/null; then
  printf 'hal-py not installed (pip install hal-py)\n' >&2
  exit 2
fi

exec python3 -m hal_py.run
