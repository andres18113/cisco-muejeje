# poe3a-20260907T213914Z-20f42991 — classification

```text
MEASUREMENT = VALID
PRODUCTIVE AUTHORITY = NO
```

This file qualifies the run beside its own bytes. Nothing in `evidence.json`
or the raw captures has been altered; they are the record of what happened.

## What the run established

A governed PSE measurement of the exact canonical binding, LIVE from
`e4b0d1479cd2fe10a6c97b446d3a7b87ee421415` with Actions 4/4 on that SHA:

```text
3560-24PS  FastEthernet0/1  ->  7960  Switch

AUTO_1   auto on 10.0   IP Phone 7960   class 3     delivering
NEVER    row absent                                 not delivering
AUTO_2   auto on 10.0   IP Phone 7960   class 3     delivering
```

Two captures per state, all eight completeness gates true on each, auto
restored with a fresh read-back, fixture deleted, Packet Tracer's own residue
retired, inventory fingerprint identical before and after, Realtime restored,
mailbox clean, same two PT processes, nothing saved, frozen source unchanged,
`problems: []`.

That measurement stands. It is real, fresh, exact and reproducible from the
persisted raw bytes.

## What the run did not establish, and cannot

Its `pse_dimensions` were produced under **PSE schema 1**, which carried a
field of its own:

```text
poe_pse_live_safety = admitted
```

That was a design defect. A measurement cannot attest its own LIVE admission;
admission has exactly one authoritative source, the real
`LiveSessionSafetyEvidence` on the probe's context, judged by
`validate_live_session_positive_admission`. The bundle recorded
`productive=false` and `integration_result=NOT_ATTEMPTED` at the time, so the
contradiction never produced a claim — but the contract allowed a record to
say something it had no standing to say.

**PSE schema 2 removes the field.** These dimensions therefore no longer
decode, by design and not by accident: replaying them through the productive
composition yields `supports_poe = UNKNOWN` and no authorized bindings, even
when admitted safety evidence is supplied alongside. That behaviour is
asserted in `tests/test_poe3a_hardening.py`, against these committed bytes.

## Why the run is kept

Because it is the evidence. The measurement is valid and the defect is part of
its history; rewriting `evidence.json` to look as though it had always been
correct would destroy the traceability this directory exists for.

If a productive PSE claim for this binding is ever wanted, it comes from a new
run under schema 2 with a LIVE session whose safety evidence is genuinely
admitted — not from reinterpreting these bytes under rules they were never
written against.
