#!/usr/bin/env python3
"""A deliberately NON-CONFORMING runtime: it fakes axiom 3.

This exists so the `sub_request recurses through the same runtime` invariant can
be observed FAILING. A check that has never been seen to fail is an oracle, not a
test, and its green tells you nothing.

What it does, and why it is the interesting kind of wrong: it emits a perfectly
well-formed `sub_request` event and then serves the child from a PRIVATE inner
handler that skips validation entirely. For a single well-formed child the output
is indistinguishable from a conforming runtime — which is exactly why "did a
sub_request appear?" is not a sufficient check.

It is caught only by the consequence a shared code path cannot avoid: this
runtime REJECTS `happi/0.9` on stdin and ACCEPTS it as a child.

Not wired into any runner and never run by CI. Invoke it explicitly:

    python3 scripts/check-invariants.py scripts/nonconforming/privileged-inner-interface.py
"""
import json
import sys

VERSION = "happi/1.3"
ACCEPTED = ("happi/1.0", "happi/1.1", "happi/1.2", "happi/1.3")


def emit(**fields):
    print(json.dumps({"v": VERSION, "ts": 0, **fields}, separators=(",", ":")), flush=True)


def serve_child_privileged(child):
    """The defect: a second, softer dispatcher reachable only by children.

    No version check, no cmd lookup — it simply asserts success. A child that
    the front door would have refused sails straight through here.
    """
    emit(id=child.get("id", "?"), type="started")
    emit(id=child.get("id", "?"), type="delta", text=VERSION)
    emit(id=child.get("id", "?"), type="completed")


def main():
    try:
        env = json.loads(sys.stdin.read())
    except json.JSONDecodeError as exc:
        emit(id="req-invalid", type="error", code="parse_error", message=str(exc))
        return 1

    if env.get("v") not in ACCEPTED:
        emit(id=env.get("id", "?"), type="error", code="parse_error",
             message="unsupported version: " + repr(env.get("v")))
        return 1

    env_id = env["id"]
    emit(id=env_id, type="started")
    cmd = env.get("cmd")

    if cmd == "version":
        emit(id=env_id, type="delta", text=VERSION)
        emit(id=env_id, type="completed")
        return 0
    if cmd == "echo":
        for a in env.get("args", []):
            emit(id=env_id, type="delta", text=str(a))
        emit(id=env_id, type="completed")
        return 0
    if cmd == "compose":
        for child in (env.get("flags") or {}).get("envelopes") or []:
            emit(id=env_id, type="sub_request", envelope=child)
            serve_child_privileged(child)
        emit(id=env_id, type="completed", usage={"children": 1})
        return 0

    emit(id=env_id, type="error", code="unsupported_cmd",
         message="cmd " + repr(cmd) + " not supported by this runtime")
    return 1


if __name__ == "__main__":
    sys.exit(main())
