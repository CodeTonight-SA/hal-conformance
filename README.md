# hal-conformance — HAPPI/1.0–1.3 Cross-Runtime Conformance Suite

This repository defines the **HAPPI-compliant** standard mark, analogous to
"ACID-compliant" or "POSIX-compliant". A HAPPI runtime claims compliance by
processing all canonical fixtures and producing matching event streams.

Canonical reference: [`happi.md`](https://gist.github.com/LaurieScheepers/2483d5c218c21ecc931130bcee7dee83) (public gist mirror)
Possibilities whitepaper: HAPPI Protocol & Possibilities (CodeTonight, April 2026)

## Quickstart

```bash
# Run the reference runtime (the pinned spec committed in this repo) against all fixtures
HAPPI_MD="$PWD/spec/happi-1.3.md" ./conformance.sh runners/reference.sh

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
| 10-compose-sub-request | compose | 1.3 | Axiom 3 — a parent envelope recursing through the same runtime, with each child's events inlined behind a `sub_request` marker |

Fixtures 08–09 are the load-bearing v1.3 pair. A runtime passes only if a quote
absent from its source resolves to `not_found` — never `verified` or `fuzzy`.
That is the guarantee `cite.verify` exists to provide, so a runtime that fudges
it is not HAPPI-compliant.

Still to add: error cases (`parse_error`, `unsupported_cmd`, `runtime_error`),
the `idr.emit` cmd, data_residency / cost_governance flags, and adversarial
inputs (oversized envelopes, malformed JSON, unicode edge cases).

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
gates the build; **`sub_request` recurses through the same runtime**; exactly
one outcome per envelope **id**.

The `cite` one is load-bearing, and it is verified to actually fail: a
deliberately non-conforming runtime that marks fabricated quotes `verified` is
caught with `cite: FABRICATED quote resolved to 'verified' — it must be
not_found`. A check that cannot fail proves nothing.

The `sub_request` one is load-bearing for the same reason, and is the harder of
the two to check honestly. Axiom 3 says the protocol is fractal with *no
privileged inner interface* — a claim about the code path, which is not visible
from outside. A runtime can emit a flawless `sub_request` event and then serve
the child from a private handler; for one level, on the wire, that is
indistinguishable. So asking "did a `sub_request` appear?" tests nothing.

What a shared path cannot fake is how a child FAILS. The invariant hands the
runtime an out-of-range version twice — once on stdin, once as a child — and
requires the same verdict. A relaxed inner path diverges immediately.

Verified to fail, three ways, each against a runtime that implements `compose`
so the check is genuinely reached rather than skipped
(`scripts/nonconforming/privileged-inner-interface.py`):

| Mutation | Reported |
|---|---|
| child served by a private handler that skips validation | `an out-of-range version was REFUSED at the top level but ACCEPTED as a child` |
| marker carries the child as `child` instead of `envelope` | `marker has no \`envelope\` field (got ['child'])` |
| parent emits both `error` and `completed` | `envelope 'inv-compose' terminated 2 times (error, completed)` |

### One outcome per envelope ID, not per stream

Recursion separates two things that used to coincide. A `compose` stream carries
the parent's outcome and every child's, so the older "exactly one outcome event"
check — which probes a flat `version` dispatch — is correct but no longer
sufficient. The property that survives contact with the fractal case is per
envelope id, and it is now asserted in that stronger form. A client counting
outcomes per stream misreads every recursive stream.

### A note on the `sub_request` payload field

The event table in the spec names the field `envelope`:

| `sub_request` | `envelope` | Child HAPPI envelope dispatched |

`lib/hal/happi/events.py` in the HAL repo emits it as `child`. The invariant
asserts the spec's name, because axiom 4 makes that document the contract. This
is a real divergence between the spec and a shipped library, surfaced rather
than accommodated — an invariant written to accept both could never fail on the
thing it just found.

### Three results, not two

A check reports `HOLDS`, `VIOLATION`, or `NOT-IMPLEMENTED`.

**Layer 1 now has the same three states**, for the mirror-image reason. A runtime
is allowed to implement a subset of HAPPI, so scoring a fixture as `FAIL` because
the command does not exist is a false red — it punishes an honest partial
implementation exactly as hard as a wrong answer. It is reported as
`[NOT-IMPLEMENTED]`, counted separately, and excluded from the exit status, which
remains the count of genuine failures. It is never counted as a pass. A fixture
whose *expected* output is itself an `unsupported_cmd` error is compared normally
rather than excused.

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

**That table is out of date for the reference row.** Re-measured against the
pinned spec on 2026-08-12, `context follows the outcome` now reports `[HOLDS]`,
so the reference scores 8/8 on the invariants it is subject to — the ordering
bug described above has since been fixed upstream. The hal-py and hal-go rows
are left as recorded: those runners are stubs that exit 2 unless the SDK is
installed, so nothing was re-measured for them here and no claim is made either
way.

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

`.github/workflows/conformance.yml` runs the suite against
[`spec/happi-1.3.md`](spec/happi-1.3.md) — the exact reference spec, committed
to this repository. CI is fully self-contained: no private-repo checkout, no
network fetch, no credentials.

### Pin status for the `sub_request` coverage

Fixture `10-compose-sub-request` and the two `sub_request` invariants report
`NOT-IMPLEMENTED` against the spec currently pinned in `spec/happi-1.3.md`,
because that build of the reference has no `compose` cmd. That is the correct
reading, not a gap being papered over: the property genuinely was not tested,
and it is reported as untested rather than as a pass.

They turn into a real `PASS`/`HOLDS` the moment the pin is bumped to a reference
build that implements it — verified locally against the branch behind
[HAL#523](https://github.com/CodeTonight-SA/HAL/pull/523), which scores 10/10
fixtures and 10/10 invariants.

The pin is deliberately **not** bumped in this change. Bumping it is its own
reviewed step, it has to happen after HAL#523 merges, and doing it here would
tie this suite to an unmerged branch.

Worth noting while looking at the pin: it is already behind. `spec/happi-1.3.md`
is `29ccfadf…`, while HAL `origin/main` currently carries `600fb8e4…`, so the
line above describing the pin as exported byte-for-byte from `origin/main` is
true of when it was taken rather than of today.

**Why pin the spec in-repo?** A conformance suite certifies against a *fixed*
spec version — "HAPPI/1.3-compliant" must mean the same thing on every run.
Pinning the reference bytes (sha256 recorded in
[`spec/README.md`](spec/README.md)) makes every CI run reproducible and makes
bumping the pin a deliberate, reviewed change rather than a silent upstream
drift. The pinned file is also *executed* (`bash happi.md run` — it is a
polyglot spec), so committing the bytes removes the entire
fetch-and-execute-remote-content risk class: what CI runs is what review saw.

For running against a *different* spec revision locally, set
`HAPPI_MD=/path/to/happi.md`. `scripts/fetch-reference-runtime.sh` can still
fetch the checksum-pinned public gist mirror for that purpose.

## Origin

Created 2026-05-03 as part of HAPPI v1.1 promotion. The April 2026 MESH
possibilities whitepaper §10.2 ("Provider Certification") motivated the
"HAPPI-compliant" mark; this is its first instance.

## Licence

GNU Affero General Public License v3.0 only (AGPL-3.0-only). See
[LICENSE](LICENSE).

Copyright (C) 2024-2026 Lourens Cornelius Scheepers / CodeTonight (Pty) Ltd

If you run a modified version of this software as a network service, the AGPL
requires you to offer the complete corresponding source of your modified
version to the users of that service.

**Commercial licences.** If the AGPL's network-use obligation does not fit your
deployment, a commercial licence is available — contact licensing@codetonight.co.za.
