#!/usr/bin/env bash
# hal-go runner stub — invokes the Go idiom library.
# Plug in once hal-go ships a `cmd/hal-go` binary.

set -euo pipefail

BIN="${HAL_GO_BIN:-$(command -v hal-go || true)}"

if [[ -z "$BIN" || ! -x "$BIN" ]]; then
  printf 'hal-go binary not found (set HAL_GO_BIN or put hal-go on PATH)\n' >&2
  printf 'install: go install github.com/CodeTonight-SA/hal-go/cmd/hal-go@latest\n' >&2
  exit 2
fi

exec "$BIN"
