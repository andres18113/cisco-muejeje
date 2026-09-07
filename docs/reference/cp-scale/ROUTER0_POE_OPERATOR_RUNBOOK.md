# Operator runbook: the governed PoE observations that need a person

`GovernedPoEDeliveryObserver` turns exactly one synchronous, identity-bound
visual receipt per episode into evidence, and the contract admits no substitute
today: delivery may not be inferred from catalog metadata, link state, DHCP,
forwarding, `getPower()`, `isPowerOn()` or an administrative power state. So
somebody has to look at the endpoints, and the IpcAPI offers nothing else to
look at — its whole power surface is those administrative booleans.

That constraint is about the endpoint side. A switch-side observable is being
pursued separately; until one is qualified, this runbook is the procedure.

This runbook is the mechanical form of that step. It authorizes nothing new;
it records how to spend an authorization that already exists.

## The access-point question is settled

Run `r0poe-mls6-a1e7aa15` asked it with somebody watching. Both arms came back
powered, so the differential was not supplied and `supports_poe` stayed UNKNOWN.
`AccessPoint-PT` is lit the moment it exists, with or without inline power, so
the eleven access-point bindings among the 43 cannot be covered by *this*
method — see
[POE_ACCESSPOINT_DIFFERENTIAL_20260907.md](POE_ACCESSPOINT_DIFFERENTIAL_20260907.md).

Do not re-run an access-point episode with this fixture. It has an answer.
Closing those bindings needs an observable read at the delivering end instead;
`show power inline` through the registered IOS query mechanism is the named
candidate, and it is not qualified yet.

## Which episode to run, and why

A scope fails as a whole: one binding whose control is lit invalidates the
entire episode it sits in. So every remaining episode is phone-only.

| Episode | Candidate | Bindings | What it establishes |
| --- | --- | --- | --- |
| `3560-phones` | `3560-24PS` | 23 | all 21 demanded `7960/Switch` triples, and capacity 23 |
| `3650-phones` | `3650-24PS` | 12 | all 11 demanded `7960/Switch` triples, and capacity 12 |

Each covers every demanded phone triple for its model and then extends, with
the same `7960`, onto further exact access ports of the same switch until the
episode reaches the simultaneous capacity the design demands of that model.
`3650` evidence is acquired independently; nothing is derived from the `3560`.

## Before starting

No test run may be in flight in **any** checkout on this machine. The bridge
port `54321` is fixed on both sides and process-wide, so a test that binds it
steals Packet Tracer's poller and the episode will see no polling. That is
exactly what blocked the previous session.

Packet Tracer `9.0.1.0858` open, Realtime, workspace empty of semantic devices.

## Run it

From the `cplive-ripv2` worktree, with its own interpreter:

```powershell
.\.venv\Scripts\python.exe tmp\poe_acquire_governed.py --episode 3560-phones --window-seconds 1800 --execute
```

The harness enforces every gate before it mutates anything: clean worktree,
HEAD equal to `cisco/feature/runtime-ripv2`, Actions 4/4 success on that exact
SHA, canonical `.pts` hash, Packet Tracer build, import isolation, fresh
authenticated bridge, empty semantic baseline, Realtime, and file/runtime
safety. It refuses rather than proceeds if any of them fails.

It then builds the fixture and prints one line:

```json
{"event": "CAPTURE_PENDING", "run_id": "...", "output": "...", "deadline": "...", "fixture": {...}}
```

The exact bindings are rederived from source on every invocation and printed
before anything is created; run without `--execute` to see them first.

## Observe, then return the receipt

Each arm now occupies its own band on the canvas: candidates on the left,
controls on the right, each block led by its switch. Read the two blocks and
record what is actually on screen.

Write `receipt.json` **inside the run's own `output` directory**, then create an
empty `receipt.ready` beside it before the deadline. Creating a file named
`abort` instead ends the episode cleanly. The window is a bounded CLI argument
capped at one hour; nothing arriving inside it still fails closed to UNKNOWN.

```json
{
  "request_id": "<copy from capture-request.json>",
  "capture_id": "<any unique id for this capture>",
  "fixture_fingerprint": "<copy from capture-request.json>",
  "observer_id": "<who looked>",
  "captured_at": "2026-09-07T00:00:00+00:00",
  "method": "manual_visible_power_state",
  "simultaneous": true,
  "bindings": [
    {
      "binding": {
        "candidate_port": "FastEthernet0/1",
        "comparison_port": "FastEthernet0/1",
        "endpoint_model": "7960",
        "endpoint_port": "Switch"
      },
      "candidate": {
        "switch_name": "<exact name from the fixture>",
        "switch_model": "3560-24PS",
        "switch_port": "FastEthernet0/1",
        "endpoint_name": "<exact name from the fixture>",
        "endpoint_model": "7960",
        "endpoint_port": "Switch",
        "state": "powered",
        "visible_indicator": "<what you saw, in your words>",
        "switch_ready": true,
        "link_ready": true,
        "endpoint_settled": true
      },
      "comparison": {
        "switch_name": "<exact name from the fixture>",
        "switch_model": "2960-24TT",
        "switch_port": "FastEthernet0/1",
        "endpoint_name": "<exact name from the fixture>",
        "endpoint_model": "7960",
        "endpoint_port": "Switch",
        "state": "not_powered",
        "visible_indicator": "<what you saw, in your words>",
        "switch_ready": true,
        "link_ready": true,
        "endpoint_settled": true
      }
    }
  ]
}
```

One such entry per binding, so a 23-binding episode carries 23 of them, each
echoing its own exact ports. `capture-request.json` in the run directory holds
every name to copy.

Rules the validator enforces, so they are worth knowing before you type:

- `method` must be exactly `manual_visible_power_state`.
- `captured_at` must be UTC with a zero offset.
- `simultaneous` must be `true`, and it must be true: both arms seen in one
  episode, not one after the other.
- `observer_id` must be non-empty and unpadded.
- `switch_ready`, `link_ready` and `endpoint_settled` all default to `false`
  and all three must be `true`. Omitting `endpoint_settled` is the easy way to
  turn a good reading into `unobservable`.
- every name, model and port must match the fixture exactly.

`state` is one of `powered`, `not_powered`, `unobservable`. Record what you
see, per binding. A partial result — some candidates lit and some dark — is a
real measurement of capacity and must be reported as it is. Do not adjust an
observation to make a run look successful, and use `unobservable` when the
indicator genuinely cannot be read.

## After the receipt

The harness closes the boundary itself: it deletes the fixture endpoint-first,
restores the semantic inventory and Realtime, finalizes file/runtime safety,
persists the decision through the governed mechanism, and recomposes to report
whether product admission changed. Nothing further is required from the
operator.

If the deadline passes with no receipt, the episode returns `None`, cleans up,
and records UNKNOWN. That is not a failure of the product and it must not be
retried unchanged — four such episodes already exist. Only start a run when
somebody can watch the screen for the next five minutes.

## What this does not do

These two episodes do not admit Router0. Admission needs all 43 exact bindings
— 30 on `3560-24PS` with 23 simultaneous on one device, and 13 on `3650-24PS`
with 12 simultaneous — and 11 of those 43 are access points that cannot be
qualified at all. What the phone episodes can do is remove the phone side as a
blocker, raise `poe_ports` from 1, and leave the access-point gap as the single
named reason the composition is still refused.
