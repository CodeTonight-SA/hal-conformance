#!/usr/bin/env python3
"""Spec-level invariant checks — the non-circular half of conformance.

The fixture suite compares a runtime's output against recorded expected
streams. Those recordings came from the reference runtime, which makes them
excellent at catching DIVERGENCE between implementations and useless at
catching a REGRESSION IN THE REFERENCE ITSELF: if the reference started
returning the wrong answer tomorrow and we re-recorded, the suite would go
green on the new wrong answer.

This file closes that hole. Every check below is derived from a property
stated in the SPEC PROSE, not from any recorded byte, so it holds for any
conforming runtime and fails on a reference regression that re-recording
would otherwise bake in.

Usage:  check-invariants.py <runner-command...>
        check-invariants.py bash /path/to/happi.md run
        check-invariants.py runners/reference.sh

Exit 0 if every invariant holds; non-zero = number of violations.
"""
from __future__ import annotations

import json
import subprocess
import sys
from typing import Any, Callable

# A source and two citations: one verbatim, one deliberately fabricated.
SOURCE_TEXT = "The Limitation Act 1980 bars the claim after six years."
REAL_QUOTE = "bars the claim after six years"
FAKE_QUOTE = "bars the claim after three years"

Events = list[dict[str, Any]]

# A runtime that has not implemented a command answers with this error code.
UNSUPPORTED_CMD = "unsupported_cmd"


class NotImplementedByRuntime(Exception):
    """The runtime does not implement the command this invariant probes.

    Raised so the runner can report a THIRD state. Two states are not enough:
    an unimplemented command still emits an `error` event and still exits
    non-zero, which is byte-for-byte what a correctly-gating implementation
    looks like from the outside. Collapsing that into HOLDS would let a
    runtime score green on a feature it does not have — the exact theatre
    these spec-level checks exist to prevent.
    """

    def __init__(self, cmd: str) -> None:
        super().__init__(cmd)
        self.cmd = cmd


def unsupported(events: Events) -> bool:
    """True if the runtime answered with an unsupported_cmd error."""
    return any(
        e.get("type") == "error" and e.get("code") == UNSUPPORTED_CMD
        for e in events
    )


def dispatch(runner: list[str], envelope: dict[str, Any]) -> tuple[Events, int]:
    """Send one envelope, return (parsed events, exit code)."""
    proc = subprocess.run(
        runner,
        input=json.dumps(envelope),
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    events: Events = []
    for line in proc.stdout.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        try:
            events.append(json.loads(stripped))
        except json.JSONDecodeError:
            continue  # non-JSON noise is not an event
    return events, proc.returncode


def cite_envelope(strict: bool) -> dict[str, Any]:
    """Build a cite.verify envelope with one real and one fabricated quote."""
    flags: dict[str, Any] = {
        "sources": [{"id": "s1", "text": SOURCE_TEXT}],
        "citations": [
            {"id": "c1", "source_id": "s1", "quote": REAL_QUOTE},
            {"id": "c2", "source_id": "s1", "quote": FAKE_QUOTE},
        ],
    }
    if strict:
        flags["strict"] = True
    return {"v": "happi/1.3", "id": "inv-cite", "cmd": "cite.verify", "flags": flags}


def compose_envelope(*children: dict[str, Any], envelope_id: str = "inv-compose") -> dict[str, Any]:
    """Build a compose envelope carrying the given child envelopes."""
    return {"v": "happi/1.3", "id": envelope_id, "cmd": "compose",
            "flags": {"envelopes": list(children)}}


def outcomes_by_id(events: Events) -> dict[str, list[str]]:
    """Map envelope id -> the outcome event types emitted for it."""
    seen: dict[str, list[str]] = {}
    for e in events:
        if e.get("type") in ("completed", "error"):
            seen.setdefault(str(e.get("id")), []).append(str(e.get("type")))
    return seen


# --- invariants -------------------------------------------------------------
# Each returns a list of violation strings (empty list = the invariant holds).


def inv_runtime_reports_own_version(runner: list[str]) -> list[str]:
    """spec: emitted events carry the RUNTIME's version, not the envelope's.

    Sent as happi/1.0; every event must still carry the runtime's own version,
    and the `version` delta must echo that same value.
    """
    events, _ = dispatch(runner, {"v": "happi/1.0", "id": "inv-v", "cmd": "version"})
    if not events:
        return ["version: runtime produced no events"]
    bad: list[str] = []
    versions = {e.get("v") for e in events}
    if len(versions) != 1:
        bad.append(f"version: events carry mixed versions {versions}")
    deltas = [e for e in events if e.get("type") == "delta"]
    if not deltas:
        bad.append("version: no delta event")
    elif deltas[0].get("text") != events[0].get("v"):
        bad.append(
            f"version: delta text {deltas[0].get('text')!r} != event version "
            f"{events[0].get('v')!r} (a runtime must report its own version)"
        )
    return bad


def inv_v10_envelope_accepted(runner: list[str]) -> list[str]:
    """spec: full back-compat — a v1.3 runtime accepts a v1.0 envelope."""
    events, code = dispatch(runner, {"v": "happi/1.0", "id": "inv-bc", "cmd": "version"})
    completed = any(e.get("type") == "completed" for e in events)
    if code != 0 or not completed:
        return ["back-compat: a happi/1.0 envelope was not accepted"]
    return []


def inv_out_of_range_version_rejected(runner: list[str]) -> list[str]:
    """spec: versions outside the accepted range are refused, not tolerated."""
    events, code = dispatch(runner, {"v": "happi/0.9", "id": "inv-bad", "cmd": "version"})
    if not any(e.get("type") == "error" for e in events):
        return ["version-range: happi/0.9 was accepted; it must be rejected"]
    if code == 0:
        return ["version-range: rejected happi/0.9 but exited 0"]
    return []


def inv_exactly_one_outcome(runner: list[str]) -> list[str]:
    """spec: every stream carries exactly one outcome event (completed|error)."""
    events, _ = dispatch(runner, {"v": "happi/1.3", "id": "inv-out", "cmd": "version"})
    outcomes = [e for e in events if e.get("type") in ("completed", "error")]
    if len(outcomes) != 1:
        return [f"outcome: expected exactly 1 completed/error, got {len(outcomes)}"]
    return []


def inv_context_follows_outcome(runner: list[str]) -> list[str]:
    """spec: a context event is a TERMINATOR — it follows completed/error.

    HAPPI.md CONTEXT section: "a non-streaming terminator emitted after
    `completed`/`error`", and its falsification clause (b) names the exact
    violation: "the `context` event arrives before `completed`/`error` (it
    must be a terminator)".

    Kept separate from the idr check rather than folded into it. The idr
    check exits early when a runtime declines the opt-in audit flag, and
    reusing that early exit would silently skip the context case too —
    which is how this violation stayed invisible: every recorded fixture
    was captured FROM the runtime that has the bug, so the byte comparison
    agreed with it.
    """
    events, _ = dispatch(runner, {
        "v": "happi/1.3", "id": "inv-ctx", "cmd": "context.append",
        "args": ['{"decision":"probe","rationale":"ordering check"}'],
        "flags": {"kind": "context-delta", "model_versions": ["test"]},
    })
    if unsupported(events):
        raise NotImplementedByRuntime("context.append")
    types = [e.get("type") for e in events]
    if "context" not in types:
        return ["context: context.append emitted no context event"]
    outcome_at = next(
        (i for i, t in enumerate(types) if t in ("completed", "error")), None)
    if outcome_at is None:
        return ["context: a context was emitted with no outcome event"]
    if types.index("context") < outcome_at:
        return [
            "context: context was emitted BEFORE the outcome event "
            f"(order: {' -> '.join(t or '?' for t in types)}). HAPPI.md "
            "CONTEXT falsifier (b): it must be a terminator, emitted after "
            "completed/error."
        ]
    return []


def inv_records_follow_outcome(runner: list[str]) -> list[str]:
    """spec: idr is emitted AFTER the outcome, never before it."""
    events, _ = dispatch(runner, {
        "v": "happi/1.1", "id": "inv-idr", "cmd": "echo", "args": ["x"],
        "flags": {"audit": True, "model_versions": ["test"]},
    })
    types = [e.get("type") for e in events]
    if "idr" not in types:
        return []  # audit is opt-in; a runtime may legitimately not emit one
    outcome_at = next(
        (i for i, t in enumerate(types) if t in ("completed", "error")), None)
    if outcome_at is None:
        return ["idr-order: an idr was emitted with no outcome event"]
    if types.index("idr") < outcome_at:
        return ["idr-order: idr was emitted BEFORE the outcome event"]
    return []


def inv_fabricated_quote_never_verified(runner: list[str]) -> list[str]:
    """spec: a quote absent from its source can never be verified or fuzzy.

    This is the whole guarantee cite.verify exists to provide. It is asserted
    from the spec's own words, not from recorded output, so a reference
    regression that started passing fabricated quotes would fail HERE even if
    every byte-fixture had been re-recorded around it.
    """
    events, _ = dispatch(runner, cite_envelope(strict=False))
    if unsupported(events):
        raise NotImplementedByRuntime("cite.verify")
    completed = [e for e in events if e.get("type") == "completed"]
    if not completed:
        return ["cite: no completed event for cite.verify"]
    usage = completed[0].get("usage") or {}
    citations = {c.get("id"): c for c in usage.get("citations", [])}
    bad: list[str] = []
    fake = citations.get("c2")
    if fake is None:
        bad.append("cite: fabricated citation c2 missing from provenance record")
    elif fake.get("status") != "not_found":
        bad.append(
            f"cite: FABRICATED quote resolved to {fake.get('status')!r} — it must "
            "be not_found. This breaks the core cite.verify guarantee."
        )
    real = citations.get("c1")
    if real is None:
        bad.append("cite: verbatim citation c1 missing from provenance record")
    elif real.get("status") not in ("verified", "fuzzy"):
        bad.append(
            f"cite: verbatim quote resolved to {real.get('status')!r} — a quote "
            "that IS present must be located."
        )
    return bad


def inv_strict_mode_fails_build(runner: list[str]) -> list[str]:
    """spec: strict=true turns any not_found into an error + non-zero exit.

    Guarded by an unsupported-cmd check for a reason. A runtime that has not
    implemented cite.verify at all ALSO emits an error and exits non-zero —
    for `unsupported_cmd`. Without the guard this invariant reports HOLDS on a
    runtime that cannot gate anything, which is worse than reporting nothing:
    a check that passes because the feature is MISSING is false assurance.
    """
    events, code = dispatch(runner, cite_envelope(strict=True))
    if unsupported(events):
        raise NotImplementedByRuntime("cite.verify")
    bad: list[str] = []
    if not any(e.get("type") == "error" for e in events):
        bad.append("cite-strict: a not_found citation did not emit an error event")
    if code == 0:
        bad.append("cite-strict: exited 0 despite an unverified citation "
                   "(the build gate does not gate)")
    return bad


def inv_sub_request_recurses_through_same_runtime(runner: list[str]) -> list[str]:
    """spec axiom 3: "`sub_request` recurses through the same runtime. The
    protocol is fractal; no privileged inner interface."

    The wording is a claim about the code path, and a code path is not visible
    from outside — so this checks the consequences that only a SHARED path can
    produce, rather than checking that a `sub_request` event appeared.

    A runtime could emit `sub_request` and then serve the child from a private
    inner handler. For one level, on the wire, that is indistinguishable. What
    is NOT indistinguishable is how the child fails: routed through the same
    validator and the same handler table, a child must be refused for exactly
    the reasons, and with exactly the codes, that the same bytes would be
    refused for arriving on stdin. So the child here is deliberately given an
    out-of-range version, and its error is compared against dispatching that
    identical envelope at the top level. A relaxed inner path diverges here.

    Also asserted, from the spec's own event table
    ("| `sub_request` | `envelope` | Child HAPPI envelope dispatched |"), that
    the marker carries the child under the field name `envelope`.
    """
    child = {"v": "happi/1.3", "id": "inv-kid", "cmd": "version"}
    events, _ = dispatch(runner, compose_envelope(child))
    if unsupported(events):
        raise NotImplementedByRuntime("compose")

    bad: list[str] = []

    markers = [e for e in events if e.get("type") == "sub_request"]
    if not markers:
        return ["sub_request: compose emitted no sub_request event"]
    if "envelope" not in markers[0]:
        bad.append(
            f"sub_request: marker has no `envelope` field (got "
            f"{sorted(k for k in markers[0] if k not in ('v', 'id', 'type', 'ts'))}). "
            "The event table names the payload field `envelope`."
        )

    # The child's OWN events must be inlined into the parent stream — that is
    # what "recurses through the same runtime" produces, as against a runtime
    # that merely announces a child it then handles out of band.
    child_events = [e for e in events if e.get("id") == "inv-kid"]
    if not child_events:
        return bad + ["sub_request: the child produced no events in the stream"]
    if not any(e.get("type") == "completed" for e in child_events):
        bad.append("sub_request: the child never reached an outcome")

    # Back-compat must hold THROUGH recursion, not just at the top level.
    parent_version = events[0].get("v")
    child_versions = {e.get("v") for e in child_events}
    if child_versions != {parent_version}:
        bad.append(
            f"sub_request: child events carry {child_versions}, parent carries "
            f"{parent_version!r} — a child must be stamped by the same runtime"
        )

    # THE discriminator: same validator, or a privileged inner one?
    rejected = {"v": "happi/0.9", "id": "inv-old", "cmd": "version"}
    top_events, _ = dispatch(runner, rejected)
    top_err = next((e for e in top_events if e.get("type") == "error"), None)
    nested_events, _ = dispatch(runner, compose_envelope(rejected))
    nested_err = next((e for e in nested_events if e.get("type") == "error"), None)
    if top_err is None:
        bad.append("sub_request: cannot compare — an out-of-range version was "
                   "accepted at the top level")
    elif nested_err is None:
        bad.append(
            "sub_request: an out-of-range version was REFUSED at the top level "
            "but ACCEPTED as a child. The child is not going through the same "
            "validator, which is the privileged inner interface axiom 3 forbids."
        )
    elif top_err.get("code") != nested_err.get("code"):
        bad.append(
            f"sub_request: the same bad envelope yields {top_err.get('code')!r} "
            f"at the top level and {nested_err.get('code')!r} as a child; a "
            "shared dispatch path must produce one verdict, not two."
        )
    return bad


def inv_one_outcome_per_envelope_id(runner: list[str]) -> list[str]:
    """spec: exactly one outcome event per envelope — per ID, not per stream.

    The existing "exactly one outcome event" invariant probes a flat `version`
    dispatch, where stream and envelope coincide. Recursion separates them: a
    compose stream carries the parent's outcome AND every child's, so counting
    per stream is wrong the moment the protocol is used fractally. The property
    that survives is per id, and this asserts that stronger form.
    """
    events, _ = dispatch(runner, compose_envelope(
        {"v": "happi/1.3", "id": "inv-c1", "cmd": "version"},
        {"v": "happi/1.0", "id": "inv-c2", "cmd": "echo", "args": ["x"]},
    ))
    if unsupported(events):
        raise NotImplementedByRuntime("compose")
    bad: list[str] = []
    seen = outcomes_by_id(events)
    for env_id, got in sorted(seen.items()):
        if len(got) != 1:
            bad.append(
                f"outcome-per-id: envelope {env_id!r} terminated {len(got)} "
                f"times ({', '.join(got)}); each id must terminate exactly once"
            )
    for expected_id in ("inv-compose", "inv-c1", "inv-c2"):
        if expected_id not in seen:
            bad.append(f"outcome-per-id: envelope {expected_id!r} never terminated")
    return bad


INVARIANTS: list[tuple[str, Callable[[list[str]], list[str]]]] = [
    ("runtime reports its own version", inv_runtime_reports_own_version),
    ("happi/1.0 envelope accepted (back-compat)", inv_v10_envelope_accepted),
    ("out-of-range version rejected", inv_out_of_range_version_rejected),
    ("exactly one outcome event", inv_exactly_one_outcome),
    ("idr follows the outcome", inv_records_follow_outcome),
    ("context follows the outcome", inv_context_follows_outcome),
    ("fabricated quote is never verified", inv_fabricated_quote_never_verified),
    ("strict mode gates the build", inv_strict_mode_fails_build),
    ("sub_request recurses through the same runtime",
     inv_sub_request_recurses_through_same_runtime),
    ("exactly one outcome per envelope id", inv_one_outcome_per_envelope_id),
]


def run_one(name: str, check: Callable[[list[str]], list[str]],
            runner: list[str]) -> tuple[int, int]:
    """Run one invariant, print its result.

    Returns (violations, skipped). Three outcomes, not two:

      HOLDS           the property was tested and it held
      NOT-IMPLEMENTED the command does not exist here, so nothing was tested
      VIOLATION       the property was tested and it failed

    NOT-IMPLEMENTED does not count as a violation (a runtime is allowed to
    implement a subset) but it must never be printed as HOLDS either, or the
    summary would claim coverage it does not have.
    """
    try:
        found = check(runner)
    except NotImplementedByRuntime as skip:
        print(f"[NOT-IMPLEMENTED] {name}\n    runtime does not support "
              f"{skip.cmd!r}; this property was NOT tested")
        return 0, 1
    except Exception as exc:  # noqa: BLE001 — a crashing check IS a failure
        found = [f"{name}: check raised {type(exc).__name__}: {exc}"]
    if not found:
        print(f"[HOLDS] {name}")
        return 0, 0
    detail = "\n".join(f"    {line}" for line in found)
    print(f"[VIOLATION] {name}\n{detail}")
    return len(found), 0


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__, file=sys.stderr)
        return 2
    runner = argv[1:]
    results = [run_one(name, check, runner) for name, check in INVARIANTS]
    violations = sum(v for v, _ in results)
    skipped = sum(s for _, s in results)

    print("\n=== invariant summary ===")
    print(f"runner:     {' '.join(runner)}")
    print(f"invariants: {len(INVARIANTS)}")
    print(f"tested:     {len(INVARIANTS) - skipped}")
    if skipped:
        print(f"untested:   {skipped} (command not implemented by this runtime)")
    print(f"violations: {violations}")
    return violations


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
