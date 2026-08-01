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
| 04-spec-describe | spec.describe | 1.0 | Spec self-description — compared by shape, not bytes (see Comparison modes) |
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

## Two layers, and why both exist

**Layer 1 — fixtures** (`./conformance.sh`) compare a runtime's output against
recorded expected streams. Excellent at catching *divergence between
implementations*.

**Layer 2 — invariants** (`scripts/check-invariants.py`) assert properties taken
from the **spec prose**, not from any recorded byte:

```bash
python3 scripts/check-invariants.py bash /tmp/happi.md run
python3 scripts/check-invariants.py runners/hal-py.sh
```

Layer 2 exists because layer 1 alone is circular. The expected streams were
recorded *from* the reference runtime, so if the reference regressed tomorrow
and the fixtures were re-recorded, the suite would go green on the new wrong
answer. The invariants cannot be re-recorded — they are the guarantees the spec
states, so they fail on a reference regression that re-recording would hide.

Currently asserted: a runtime reports its own version (not the envelope's); a
`happi/1.0` envelope is accepted; an out-of-range version is rejected; exactly
one outcome event per stream; `idr` follows the outcome; `context` follows the
outcome; **a fabricated quote is never `verified` or `fuzzy`**; strict mode
gates the build.

The `cite` one is load-bearing, and it is verified to actually fail: a
deliberately non-conforming runtime that marks fabricated quotes `verified` is
caught with `cite: FABRICATED quote resolved to 'verified' — it must be
not_found`. A check that cannot fail proves nothing.

### Three results, not two

A check reports `HOLDS`, `VIOLATION`, or `NOT-IMPLEMENTED`.

The third exists because a runtime that has not implemented a command still
answers with an `error` event and still exits non-zero — for `unsupported_cmd`.
From the outside that is indistinguishable from a correctly working safety
gate, so "strict mode gates the build" was reporting `HOLDS` against a runtime
that could not gate anything. A check that passes because the feature is
*missing* is worse than no check, because it reads as assurance.

### What layer 2 caught

The argument above is not hypothetical. Layer 2's first real finding was a bug
in the reference runtime itself.

HAPPI.md says a `context` event is "a non-streaming terminator emitted after
`completed`/`error`", and its falsification clause names the exact violation:
"the `context` event arrives before `completed`/`error`". The reference emits
it *before*. The same file gets the twin case right — the audit `idr` is
correctly emitted after the outcome — so the runtime is internally
inconsistent rather than following a different convention.

Layer 1 could never have found this. `fixtures/expected/07-context-append.ndjson`
was recorded *from* the reference, so it captures the wrong order as the
expected order, and the byte comparison agrees with it forever.

Scores as a result:

| Runtime | Fixtures | Invariants |
|---|---|---|
| reference | 9/9 | 7/8 — fails context ordering |
| hal-py | 8/9 — fails 07 | 8/8 |
| hal-go | 8/9 — fails 07 | 8/8 |

Two implementations written independently from the spec satisfy every property
the spec states. The one that violates a property is the reference — which is
also the one every fixture was recorded from. Both new runtimes fail fixture 07
precisely *because* they follow the spec.

So the recorded suite currently rewards copying the bug and penalises
correctness. Tracked as issue #2, along with the four steps a fix has to land
together. When the reference is corrected and fixture 07 re-recorded, both
runtimes reach 9/9 with no code change.

## Comparison modes

Fixtures are compared byte-for-byte after normalisation, with two deliberate
exceptions.

**Key order is normalised away.** A JSON object is unordered by definition. Go
sorts map keys alphabetically; the Python reference emits them in declaration
order. Comparing raw text reported two semantically identical events as
different — and since the recordings come from the reference, *every* correct
implementation that was not the reference failed *every* fixture. hal-go scored
0/9 when three were genuinely correct. Both sides now pass through `jq -S`.

**Self-describing output is compared by shape.** A fixture can opt in with a
sibling `<name>.mode` file containing `structural`, which reduces both sides to
their event-type sequence with runs collapsed. Only `04-spec-describe` uses it,
because that command asks a runtime to describe *itself*, including the line
`Cmds (this runtime): ...`. Byte-comparing that requires every implementation
to recite the reference's command list — that is, to misreport its own
capabilities in order to score as conforming.

This weaker check is applied narrowly and does not become a free pass: a
runtime that does not implement `spec.describe` at all still fails, because it
answers with an error rather than `started -> delta -> completed`. The check
distinguishes "describes itself differently" from "does not have this command".

## CI

`.github/workflows/conformance.yml` currently obtains the reference runtime by
checking out `CodeTonight-SA/HAL` with `actions/checkout`. **HAL is a private
repository**, and the default `GITHUB_TOKEN` is scoped to the current repo
only — so that step cannot succeed without a PAT, and the workflow has failed
on every run since it was added.

The fix needs no credentials: `scripts/fetch-reference-runtime.sh` pulls the
same runtime from its public gist mirror.

**The download is checksum-pinned, and that is not optional.** The fetched file
is then *executed* (`bash happi.md run`). Pulling an unpinned script over HTTPS
and running it would make CI compromisable by anyone who can write to the gist —
a stolen token becomes arbitrary code execution in a job that can read repo
secrets. TLS authenticates the *server*; it says nothing about the *content*. So
the content hash is pinned in the script, a mismatch is a hard failure, and
updating the pin is a deliberate reviewable commit (`--print-sha` reads the
current upstream value).

Replace the HAL checkout step with:

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
