#!/usr/bin/env bash
# hal-js runner stub — invokes the JavaScript/TypeScript idiom library.
# Plug in once hal-js exposes a `node bin/hal-js` or `bunx hal-js` CLI.

set -euo pipefail

if command -v node >/dev/null 2>&1; then
  exec node "$(dirname "$0")/../node_modules/hal-js/dist/cli.js"
elif command -v bun >/dev/null 2>&1; then
  exec bunx hal-js
else
  printf 'node or bun required\n' >&2
  exit 2
fi
