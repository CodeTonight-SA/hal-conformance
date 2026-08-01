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


def inv_records_follow_outcome(runner: list[str]) -> list[str]:
    """spec: idr/context are emitted AFTER the outcome, never before it."""
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
    """spec: strict=true turns any not_found into an error + non-zero exit."""
    events, code = dispatch(runner, cite_envelope(strict=True))
    bad: list[str] = []
    if not any(e.get("type") == "error" for e in events):
        bad.append("cite-strict: a not_found citation did not emit an error event")
    if code == 0:
        bad.append("cite-strict: exited 0 despite an unverified citation "
                   "(the build gate does not gate)")
    return bad


INVARIANTS: list[tuple[str, Callable[[list[str]], list[str]]]] = [
    ("runtime reports its own version", inv_runtime_reports_own_version),
    ("happi/1.0 envelope accepted (back-compat)", inv_v10_envelope_accepted),
    ("out-of-range version rejected", inv_out_of_range_version_rejected),
    ("exactly one outcome event", inv_exactly_one_outcome),
    ("idr/context follow the outcome", inv_records_follow_outcome),
    ("fabricated quote is never verified", inv_fabricated_quote_never_verified),
    ("strict mode gates the build", inv_strict_mode_fails_build),
]


def run_one(name: str, check: Callable[[list[str]], list[str]],
            runner: list[str]) -> int:
    """Run one invariant, print its result, return the violation count."""
    try:
        found = check(runner)
    except Exception as exc:  # noqa: BLE001 — a crashing check IS a failure
        found = [f"{name}: check raised {type(exc).__name__}: {exc}"]
    if not found:
        print(f"[HOLDS] {name}")
        return 0
    detail = "\n".join(f"    {line}" for line in found)
    print(f"[VIOLATION] {name}\n{detail}")
    return len(found)


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__, file=sys.stderr)
        return 2
    runner = argv[1:]
    violations = sum(run_one(name, check, runner) for name, check in INVARIANTS)

    print("\n=== invariant summary ===")
    print(f"runner:     {' '.join(runner)}")
    print(f"invariants: {len(INVARIANTS)}")
    print(f"violations: {violations}")
    return violations


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
