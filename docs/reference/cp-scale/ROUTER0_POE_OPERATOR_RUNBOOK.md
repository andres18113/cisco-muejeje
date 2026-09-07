# Operator runbook: the one governed PoE observation that needs a person

Everything that can be automated is done. `GovernedPoEDeliveryObserver` turns
exactly one synchronous, identity-bound visual receipt into evidence, and the
contract deliberately admits no substitute: delivery may not be inferred from
catalog metadata, link state, DHCP, forwarding, `getPower()`, `isPowerOn()` or
an administrative power state. Somebody has to look at the endpoints.

This runbook is the mechanical form of that step. It authorizes nothing new;
it records how to spend an authorization that already exists.

## Which episode to run first, and why

Run the access-point episode. It is the smallest fixture — 4 devices, 2 links —
and it is the one whose outcome decides whether Router0 is reachable at all.

Factory structure already shows that no generic Packet Tracer access point
accepts `eAccessPointPowerAdaptor`, while the `7960` that already qualified
does accept `eIpPhonePowerAdapter`. If a receipt records both arms powered,
that converts a structural finding into a behavioural one and settles the 11
access-point bindings. If it records the candidate powered and the control not
powered, the structural reading is wrong and the whole design reopens.

Either way one receipt is decisive, which is not true of any other episode.

## Before starting

No test run may be in flight in **any** checkout on this machine. The bridge
port `54321` is fixed on both sides and process-wide, so a test that binds it
steals Packet Tracer's poller and the episode will see no polling. That is
exactly what blocked the previous session.

Packet Tracer `9.0.1.0858` open, Realtime, workspace empty of semantic devices.

## Run it

From the `cplive-ripv2` worktree, with its own interpreter:

```powershell
.\.venv\Scripts\python.exe tmp\router0_poe_acquire.py --group mls6 --execute
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

The exact bindings for this group, rederived from source:

| Arm | Switch | Port | Endpoint | Endpoint port |
| --- | --- | --- | --- | --- |
| candidate | `3560-24PS` | `FastEthernet0/13` | `AccessPoint-PT` | `Port 0` |
| control | `2960-24TT` | `FastEthernet0/1` | `AccessPoint-PT` | `Port 0` |

## Observe, then write the receipt

Look at both access points in Packet Tracer and record what is actually on
screen. Write `receipt.json` **inside the run's own `output` directory**, then
type `receipt.json` on the harness's stdin before the deadline. Typing `abort`
ends the episode cleanly.

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
        "candidate_port": "FastEthernet0/13",
        "comparison_port": "FastEthernet0/1",
        "endpoint_model": "AccessPoint-PT",
        "endpoint_port": "Port 0"
      },
      "candidate": {
        "switch_name": "<exact name from the fixture>",
        "switch_model": "3560-24PS",
        "switch_port": "FastEthernet0/13",
        "endpoint_name": "<exact name from the fixture>",
        "endpoint_model": "AccessPoint-PT",
        "endpoint_port": "Port 0",
        "state": "powered",
        "visible_indicator": "<what you saw, in your words>",
        "switch_ready": true,
        "link_ready": true
      },
      "comparison": {
        "switch_name": "<exact name from the fixture>",
        "switch_model": "2960-24TT",
        "switch_port": "FastEthernet0/1",
        "endpoint_name": "<exact name from the fixture>",
        "endpoint_model": "AccessPoint-PT",
        "endpoint_port": "Port 0",
        "state": "powered",
        "visible_indicator": "<what you saw, in your words>",
        "switch_ready": true,
        "link_ready": true
      }
    }
  ]
}
```

Rules the validator enforces, so they are worth knowing before you type:

- `method` must be exactly `manual_visible_power_state`.
- `captured_at` must be UTC with a zero offset.
- `simultaneous` must be `true`, and it must be true: both arms seen in one
  episode, not one after the other.
- `observer_id` must be non-empty and unpadded.
- every name, model and port must match the fixture exactly.

`state` is one of `powered`, `not_powered`, `unobservable`. Record what you
see. **Both arms powered is a real and useful result** — it is the outcome the
factory evidence predicts, and reporting it settles the question. Do not adjust
an observation to make a run look successful, and use `unobservable` when the
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

One receipt for this binding does not admit Router0. Admission needs 43 exact
bindings — 30 on `3560-24PS` with 23 simultaneous on one device, and 13 on
`3650-24PS` with 12 simultaneous — and `poe_ports` is 1 today. This episode
settles whether the 11 access-point bindings among them are reachable at all,
which decides whether the remaining phone episodes are worth running.
