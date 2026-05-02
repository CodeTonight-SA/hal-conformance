# hal-conformance — HAPPI/1.0 + 1.1 Cross-Runtime Conformance Suite

This repository defines the **HAPPI-compliant** standard mark, analogous to
"ACID-compliant" or "POSIX-compliant". A HAPPI runtime claims compliance by
processing all canonical fixtures and producing matching event streams.

Canonical reference: [`happi.md`](https://github.com/CodeTonight-SA/HAL/blob/main/happi.md)
Possibilities whitepaper: HAPPI/1.0 Protocol & Possibilities (CodeTonight, April 2026)

## Quickstart

```bash
# Run the reference runtime against all fixtures
./conformance.sh runners/reference.sh

# Run any HAPPI-compliant runtime
./conformance.sh runners/hal-py.sh
./conformance.sh runners/hal-js.sh
./conformance.sh runners/hal-go.sh
```

Exit status: 0 if all fixtures pass, non-zero otherwise (count of failures).

## The contract

A HAPPI-compliant runtime, given any envelope in `fixtures/envelopes/`, MUST
produce an NDJSON event stream that matches `fixtures/expected/` modulo the
`ts` field (timestamps are run-dependent).

Two fixture categories:

- **`fixtures/envelopes/01..05`**: byte-identical (after `ts` strip) match required.
- **`fixtures/envelopes/06-idr-audit.json`**: structural check only — `sha256` in
  `idr_ref` is run-dependent because audit buffers include `ts` in their hash
  input. Conformance verifies presence + shape of `idr_ref`, not its hash value.

## Fixture inventory (v0.1)

| Fixture | cmd | v | Purpose |
|---|---|---|---|
| 01-version-v10 | version | 1.0 | Backward-compat baseline |
| 02-version-v11 | version | 1.1 | v1.1 version dispatch |
| 03-echo | echo | 1.0 | Args-as-deltas correctness |
| 04-spec-describe | spec.describe | 1.0 | Spec-self-description |
| 05-envelope-validate | envelope.validate | 1.0 | Schema validation result |
| 06-idr-audit | echo + audit | 1.1 | v1.1 IDR emission (structural) |

v0.2 will add 19 more fixtures covering: error cases (parse_error,
unsupported_cmd, runtime_error), `idr.emit` cmd, `sub_request` recursion,
data_residency / cost_governance flags, and adversarial inputs (oversized
envelopes, malformed JSON, unicode edge cases).

## Adding a runner

Each runner in `runners/` is a single executable that reads one HAPPI envelope
from stdin and emits NDJSON events on stdout. The HAPPI/1.0 axiom 1
("CLI/stdio is the canonical transport") makes this trivially universal:

```bash
#!/bin/bash
exec /path/to/your/hal-runtime "$@"
```

## Origin

Created 2026-05-03 as part of HAPPI v1.1 promotion. The April 2026 MESH
possibilities whitepaper §10.2 ("Provider Certification") motivated the
"HAPPI-compliant" mark; this is its first instance.

## Licence

MIT. See [LICENSE](LICENSE).
