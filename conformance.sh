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
UNIMPL=0
FAILED_NAMES=()
UNIMPL_NAMES=()

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

# Reduce a stream to its SHAPE: the sequence of event types, with runs of the
# same type collapsed. "started, delta, delta, delta, completed" becomes
# "started delta completed".
#
# Used only for fixtures whose output is a runtime describing ITSELF. The
# obvious case is spec.describe, whose deltas list "Cmds (this runtime): ...".
# Byte-comparing that across implementations asks every runtime to recite the
# REFERENCE's command list — that is, to misreport its own capabilities in
# order to score as conforming. A conformance suite must not reward that. The
# property that genuinely holds for every conforming runtime is the shape:
# started, then one or more deltas, then an outcome.
#
# This is deliberately the weaker comparison, applied narrowly. Everything
# else stays a byte comparison, because for every other fixture the content IS
# the contract.
shape_only() {
  jq -r '.type' 2>/dev/null | uniq || true
}

# Did the runtime answer "I do not have this command"?
#
# A runtime is allowed to implement a SUBSET of HAPPI, so a fixture for a cmd it
# lacks must not be scored as a failure — that is a false red, and it punishes an
# honest partial implementation exactly as hard as a wrong one.
#
# It must not be scored as a PASS either. The invariant layer already learned this
# lesson the hard way (see "Three results, not two" in the README): an unimplemented
# cmd still emits an `error` and still exits non-zero, which from the outside is
# byte-identical to a correctly-gating implementation. Reporting that as success
# claims coverage the run does not have.
#
# So it gets its own state. Counted separately, printed distinctly, and excluded
# from the exit status — which stays the count of genuine failures.
#
# Guarded by the expected stream: a fixture whose EXPECTED output is itself an
# unsupported_cmd error is testing the error path on purpose, so it is compared
# normally rather than being excused.
answered_unsupported_cmd() {
  printf '%s\n' "$1" | jq -e -s 'any(.[]; .type == "error" and .code == "unsupported_cmd")' >/dev/null 2>&1
}

# A fixture opts into shape comparison with a sibling <name>.mode file
# containing the word "structural". Kept next to the fixture so the weaker
# check is visible to anyone reading it, never hidden in a central list.
compare_mode() {
  local mode_file="$EXP_DIR/$1.mode"
  if [[ -f "$mode_file" ]] && grep -qi 'structural' "$mode_file"; then
    printf 'structural'
  else
    printf 'exact'
  fi
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

  if answered_unsupported_cmd "$actual_raw" \
     && ! answered_unsupported_cmd "$(cat "$expected_file")"; then
    printf '[NOT-IMPLEMENTED] %s — runtime does not support this cmd; nothing was tested\n' "$name"
    UNIMPL=$((UNIMPL + 1))
    UNIMPL_NAMES+=("$name")
    continue
  fi

  mode="$(compare_mode "$name")"
  if [[ "$mode" == "structural" ]]; then
    actual="$(printf '%s\n' "$actual_raw" | shape_only)"
    expected="$(shape_only < "$expected_file")"
  else
    # Normalise: strip ts, then strip idr.sha256 (run-dependent)
    actual="$(printf '%s\n' "$actual_raw" | strip_ts | strip_idr_volatile)"
    expected="$(strip_ts < "$expected_file" | strip_idr_volatile)"
  fi

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
if (( UNIMPL > 0 )); then
  printf 'untested: %d (cmd not implemented: %s)\n' "$UNIMPL" "${UNIMPL_NAMES[*]}"
fi
if (( FAIL > 0 )); then
  printf 'failures: %s\n' "${FAILED_NAMES[*]}"
fi

exit "$FAIL"
