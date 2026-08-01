#!/usr/bin/env bash
# Fetch the canonical reference happi.md from its PUBLIC gist mirror, and
# refuse to hand back anything whose checksum we did not expect.
#
# Why this exists: the CI workflow used to obtain the reference runtime by
# checking out CodeTonight-SA/HAL with actions/checkout. HAL is a PRIVATE
# repo, and the default GITHUB_TOKEN is scoped to the current repository
# only — so that checkout could never succeed without a PAT, and the
# conformance workflow failed on every run from the day it was added.
#
# Why the checksum is mandatory: the file this script downloads is then
# EXECUTED (`bash happi.md run`). Fetching an unpinned script over HTTPS and
# running it makes CI trivially compromisable by anyone who can write to the
# gist — a stolen token or a hijacked account becomes arbitrary code
# execution on every conformance run, in a job that can see repo secrets.
# TLS authenticates the SERVER; it says nothing about the CONTENT. So the
# content is pinned, and a mismatch is a hard failure, never a warning.
#
# Updating the pin is a deliberate, reviewable act: run --print-sha to read
# the current upstream value, confirm the change is the intended spec
# revision, then commit the new EXPECTED_SHA256.
#
# Usage:
#   scripts/fetch-reference-runtime.sh [destination]
#   scripts/fetch-reference-runtime.sh --print-sha
#   HAPPI_MD="$(scripts/fetch-reference-runtime.sh /tmp/happi.md)"
#
# Prints the destination path on stdout so it can be captured directly.

set -euo pipefail

# Canonical public mirror. Kept in sync with the private canonical copy by
# HAL's sync-happi-gist.sh, which sha256-asserts each push.
GIST_RAW_URL="${HAPPI_GIST_URL:-https://gist.githubusercontent.com/LaurieScheepers/2483d5c218c21ecc931130bcee7dee83/raw/happi.md}"

# Pinned content hash of the reference runtime (happi/1.3).
# Override for a deliberate spec bump: HAPPI_SHA256=<hex> ...
EXPECTED_SHA256="${HAPPI_SHA256:-b59525f102dd4beb76732bc8d5f24bed652ed3a4440c4ca2edca256e6bc9bfc0}"

need() {
  command -v "$1" >/dev/null 2>&1 || { printf '%s required\n' "$1" >&2; exit 2; }
}
need curl

# sha256sum on Linux/CI, shasum on macOS. Fail loudly if neither exists —
# silently skipping the check would defeat the entire point of this script.
sha256_of() {
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$1" | awk '{print $1}'
  elif command -v shasum >/dev/null 2>&1; then
    shasum -a 256 "$1" | awk '{print $1}'
  else
    printf 'no sha256 tool found (need sha256sum or shasum)\n' >&2
    exit 2
  fi
}

if [[ "${1:-}" == "--print-sha" ]]; then
  TMP="$(mktemp)"
  trap 'rm -f "$TMP"' EXIT
  curl -fsSL "$GIST_RAW_URL" -o "$TMP"
  sha256_of "$TMP"
  exit 0
fi

DEST="${1:-${TMPDIR:-/tmp}/happi.md}"

if ! curl -fsSL "$GIST_RAW_URL" -o "$DEST"; then
  printf 'failed to fetch reference runtime from %s\n' "$GIST_RAW_URL" >&2
  exit 1
fi

if [[ ! -s "$DEST" ]]; then
  printf 'fetched reference runtime is empty: %s\n' "$DEST" >&2
  exit 1
fi

ACTUAL_SHA256="$(sha256_of "$DEST")"
if [[ "$ACTUAL_SHA256" != "$EXPECTED_SHA256" ]]; then
  # Delete it before failing: a rejected file must not be left on disk where
  # a later step could pick it up regardless.
  rm -f "$DEST"
  printf 'reference runtime checksum MISMATCH — refusing to use it\n' >&2
  printf '  expected: %s\n' "$EXPECTED_SHA256" >&2
  printf '  actual:   %s\n' "$ACTUAL_SHA256" >&2
  printf '  source:   %s\n' "$GIST_RAW_URL" >&2
  printf 'If the spec legitimately changed, verify the new content and update\n' >&2
  printf 'EXPECTED_SHA256 in this script (or pass HAPPI_SHA256=<hex>).\n' >&2
  exit 1
fi

# Prove it actually runs before declaring success — a downloaded file that
# does not dispatch is worse than no file, because the suite would then
# report protocol failures for what is really a broken download.
if ! printf '%s\n' '{"v":"happi/1.0","id":"fetch-check","cmd":"version"}' \
  | bash "$DEST" run >/dev/null 2>&1; then
  printf 'fetched reference runtime does not dispatch: %s\n' "$DEST" >&2
  exit 1
fi

printf '%s\n' "$DEST"
