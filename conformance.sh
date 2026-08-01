#!/usr/bin/env bash
# hal-conformance runner — diff a runtime's output against canonical expected.
# Usage: ./conformance.sh runners/<runner>.sh
#
# Exit status: 0 = all fixtures pass; non-zero = count of failures.

set -euo pipefail

if [[ $# -lt 1 ]]; then
  printf 'usage: %s <runner.sh>\n' "$0" >&2
  exit 2
fi

RUNNER="$1"
if [[ ! -x "$RUNNER" ]]; then
  printf 'runner not executable: %s\n' "$RUNNER" >&2
  exit 2
fi

if ! command -v jq >/dev/null 2>&1; then
  printf 'jq required (brew install jq)\n' >&2
  exit 2
fi

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ENV_DIR="$SCRIPT_DIR/fixtures/envelopes"
EXP_DIR="$SCRIPT_DIR/fixtures/expected"

PASS=0
FAIL=0
FAILED_NAMES=()

# Strip ts (timestamps are run-dependent) and SORT KEYS.
#
# Sorting matters as much as stripping. A JSON object is unordered by
# definition, so two runtimes that emit the same event may serialise its keys
# in different orders — Go's encoding/json sorts map keys alphabetically,
# while the Python reference emits v,id,type,ts in declaration order. Without
# -S, a byte comparison reports a semantically IDENTICAL event as a mismatch,
# which would fail every conforming implementation that is not the reference
# and make the whole suite meaningless as a cross-runtime check.
#
# The `|| true` matters: under `set -o pipefail` a non-zero jq propagates out
# of the pipeline and `set -e` then aborts the entire run.
strip_ts() {
  jq -S -c 'del(.ts)' 2>/dev/null || true
}

# Strip volatile fields from idr_ref (sha256 depends on the run's ts buffer).
strip_idr_volatile() {
  jq -S -c 'if .type == "idr" then .idr_ref.sha256 = "<sha256>" else . end' 2>/dev/null || true
}

for env_file in "$ENV_DIR"/*.json; do
  name="$(basename "$env_file" .json)"
  expected_file="$EXP_DIR/$name.ndjson"

  if [[ ! -f "$expected_file" ]]; then
    printf '[SKIP] %s — no expected file\n' "$name"
    continue
  fi

  # Run the runtime
  actual_raw="$("$RUNNER" < "$env_file" 2>/dev/null || true)"

  # Normalise: strip ts, then strip idr.sha256 (run-dependent)
  actual="$(printf '%s\n' "$actual_raw" | strip_ts | strip_idr_volatile)"
  expected="$(strip_ts < "$expected_file" | strip_idr_volatile)"

  if [[ "$actual" == "$expected" ]]; then
    printf '[PASS] %s\n' "$name"
    PASS=$((PASS + 1))
  else
    printf '[FAIL] %s\n' "$name"
    # `diff` exits 1 exactly when it finds a difference — which is the branch
    # we are in. Without `|| true`, `set -o pipefail` plus `set -e` made the
    # FIRST failing fixture kill the run: the remaining fixtures never
    # executed and the summary below never printed, so a red suite reported
    # one failure when it may have had six.
    diff <(printf '%s\n' "$expected") <(printf '%s\n' "$actual") | head -12 || true
    FAIL=$((FAIL + 1))
    FAILED_NAMES+=("$name")
  fi
done

printf '\n=== conformance summary ===\n'
printf 'runner:  %s\n' "$RUNNER"
printf 'passed:  %d\n' "$PASS"
printf 'failed:  %d\n' "$FAIL"
if (( FAIL > 0 )); then
  printf 'failures: %s\n' "${FAILED_NAMES[*]}"
fi

exit "$FAIL"
