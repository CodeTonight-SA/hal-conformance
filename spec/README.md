# spec/ — pinned reference specification

`happi-1.3.md` is the exact reference `happi.md` this suite certifies against,
exported byte-for-byte from `CodeTonight-SA/HAL` `origin/main`.

sha256: `29ccfadff930da72790598a1f31290297c7ecef7a6efa8ac0502acbde78f3a5c`

Pinned reference — a conformance suite certifies against a FIXED spec version;
bumping the pin is a reviewed change. CI runs against this committed file, so
the suite is self-contained: no private-repo checkout, no network fetch.

Note: two lines in the spec cite `drafts/happi-context-event-memory-chain-design.md`
(a gitignored design note). That is a documented known-gap pending a public home
for the design doc — the citation text is deliberate, not a leak.
