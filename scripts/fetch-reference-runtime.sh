#!/usr/bin/env bash
# Fetch the canonical reference happi.md from its PUBLIC gist mirror.
#
# Why this exists: the CI workflow used to obtain the reference runtime by
# checking out CodeTonight-SA/HAL with actions/checkout. HAL is a PRIVATE
# repo, and the default GITHUB_TOKEN is scoped to the current repository
# only — so that checkout could never succeed without a PAT, and the
# conformance workflow failed on every run from the day it was added.
#
# The reference runtime is itself published as a public gist, so fetching it
# from there needs no credentials and leaks nothing: it is already public.
#
# Usage:
#   scripts/fetch-reference-runtime.sh [destination]
#   HAPPI_MD="$(scripts/fetch-reference-runtime.sh /tmp/happi.md)"
#
# Prints the destination path on stdout so it can be captured directly.

set -euo pipefail

# Canonical public mirror. The gist is kept in sync with the private
# canonical copy by HAL's sync-happi-gist.sh, which sha256-asserts each push.
GIST_RAW_URL="${HAPPI_GIST_URL:-https://gist.githubusercontent.com/LaurieScheepers/2483d5c218c21ecc931130bcee7dee83/raw/happi.md}"

DEST="${1:-${TMPDIR:-/tmp}/happi.md}"

if ! command -v curl >/dev/null 2>&1; then
  printf 'curl required\n' >&2
  exit 2
fi

if ! curl -fsSL "$GIST_RAW_URL" -o "$DEST"; then
  printf 'failed to fetch reference runtime from %s\n' "$GIST_RAW_URL" >&2
  exit 1
fi

if [[ ! -s "$DEST" ]]; then
  printf 'fetched reference runtime is empty: %s\n' "$DEST" >&2
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
