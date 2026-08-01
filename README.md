# hal-conformance — HAPPI/1.0–1.3 Cross-Runtime Conformance Suite

This repository defines the **HAPPI-compliant** standard mark, analogous to
"ACID-compliant" or "POSIX-compliant". A HAPPI runtime claims compliance by
processing all canonical fixtures and producing matching event streams.

Canonical reference: [`happi.md`](https://gist.github.com/LaurieScheepers/2483d5c218c21ecc931130bcee7dee83) (public gist mirror)
Possibilities whitepaper: HAPPI Protocol & Possibilities (CodeTonight, April 2026)

## Quickstart

```bash
# Fetch the reference runtime (public — no credentials needed)
HAPPI_MD="$(scripts/fetch-reference-runtime.sh /tmp/happi.md)"
export HAPPI_MD

# Run the reference runtime against all fixtures
./conformance.sh runners/reference.sh

# Run any HAPPI-compliant runtime
./conformance.sh runners/hal-py.sh
./conformance.sh runners/hal-js.sh
./conformance.sh runners/hal-go.sh
```

Exit status: 0 if all fixtures pass, non-zero otherwise (count of failures).

## Protocol versions

Fixtures span `happi/1.0` through `happi/1.3`. Envelopes deliberately carry a
range of versions, because full back-compat is a HAPPI guarantee: a v1.3
runtime must accept a v1.0 envelope.

Note what the expected streams show — **the runtime stamps events with its own
version, not the envelope's.** Fixture `01-version-v10` sends a `happi/1.0`
envelope and expects `happi/1.3` events back. A client that compares the wire
version for exact equality against a single constant will fail this fixture,
which is the point: that check breaks against every runtime but one.

## The contract

A HAPPI-compliant runtime, given any envelope in `fixtures/envelopes/`, MUST
produce an NDJSON event stream that matches `fixtures/expected/` modulo the
`ts` field (timestamps are run-dependent).

Two fixture categories:

- **Most fixtures**: byte-identical (after `ts` strip) match required.
- **`fixtures/envelopes/06-idr-audit.json`**: structural check only — `sha256` in
  `idr_ref` is run-dependent because audit buffers include `ts` in their hash
  input. Conformance verifies presence + shape of `idr_ref`, not its hash value.

The `context_ref.sha256` in fixture 07 and the per-source `sha256` in fixtures
08–09 are **not** volatile: both are content addresses over stable input, so
they are compared exactly.

## Fixture inventory

| Fixture | cmd | v | Purpose |
|---|---|---|---|
| 01-version-v10 | version | 1.0 | Backward-compat baseline — v1.0 in, current-version events out |
| 02-version-v11 | version | 1.1 | v1.1 version dispatch |
| 03-echo | echo | 1.0 | Args-as-deltas correctness |
| 04-spec-describe | spec.describe | 1.0 | Spec-self-description |
| 05-envelope-validate | envelope.validate | 1.0 | Schema validation result |
| 06-idr-audit | echo + audit | 1.1 | v1.1 IDR emission (structural) |
| 07-context-append | context.append | 1.2 | v1.1/1.2 memory-chain `context` record |
| 08-cite-verify | cite.verify | 1.3 | v1.3 citation provenance — one real quote, one fabricated |
| 09-cite-verify-strict | cite.verify | 1.3 | Strict mode: a fabricated quote must emit `error` and exit non-zero |

Fixtures 08–09 are the load-bearing v1.3 pair. A runtime passes only if a quote
absent from its source resolves to `not_found` — never `verified` or `fuzzy`.
That is the guarantee `cite.verify` exists to provide, so a runtime that fudges
it is not HAPPI-compliant.

Still to add: error cases (`parse_error`, `unsupported_cmd`, `runtime_error`),
the `idr.emit` cmd, `sub_request` recursion, data_residency / cost_governance
flags, and adversarial inputs (oversized envelopes, malformed JSON, unicode
edge cases).

## Adding a runner

Each runner in `runners/` is a single executable that reads one HAPPI envelope
from stdin and emits NDJSON events on stdout. The HAPPI/1.0 axiom 1
("CLI/stdio is the canonical transport") makes this trivially universal:

```bash
#!/bin/bash
exec /path/to/your/hal-runtime "$@"
```

## CI

`.github/workflows/conformance.yml` currently obtains the reference runtime by
checking out `CodeTonight-SA/HAL` with `actions/checkout`. **HAL is a private
repository**, and the default `GITHUB_TOKEN` is scoped to the current repo
only — so that step cannot succeed without a PAT, and the workflow has failed
on every run since it was added.

The fix needs no credentials: `scripts/fetch-reference-runtime.sh` pulls the
same runtime from its public gist mirror. Replace the HAL checkout step with:

```yaml
      - name: Fetch reference happi.md (public gist mirror)
        run: echo "HAPPI_MD=$(scripts/fetch-reference-runtime.sh "${{ runner.temp }}/happi.md")" >> "$GITHUB_ENV"
```

and drop the `HAPPI_MD: ${{ github.workspace }}/HAL/happi.md` env override on
the conformance step. The script verifies the download actually dispatches
before returning, so a broken fetch fails loudly instead of being reported as
a protocol failure.

## Origin

Created 2026-05-03 as part of HAPPI v1.1 promotion. The April 2026 MESH
possibilities whitepaper §10.2 ("Provider Certification") motivated the
"HAPPI-compliant" mark; this is its first instance.

## Licence

MIT. See [LICENSE](LICENSE).
