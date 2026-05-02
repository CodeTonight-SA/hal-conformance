#!/usr/bin/env bash
# Reference runner — invokes the canonical happi.md from ~/.hal/.
# Used to generate expected outputs and as the conformance baseline.

set -euo pipefail

HAPPI_MD="${HAPPI_MD:-$HOME/.hal/happi.md}"

if [[ ! -f "$HAPPI_MD" ]]; then
  printf 'reference happi.md not found at %s\n' "$HAPPI_MD" >&2
  printf 'set HAPPI_MD=/path/to/happi.md or clone CodeTonight-SA/HAL\n' >&2
  exit 2
fi

exec bash "$HAPPI_MD" run
