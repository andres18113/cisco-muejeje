# POE-2: the access point, asked from the delivering end — 2026-09-07

Checkout `cplive-ripv2`, branch `feature/runtime-ripv2`, frozen source
`888178008b31734d61c7fc5d8c544e8049a983de`, GitHub Actions 4/4 success on that
exact SHA (run `34147815905`), worktree clean, Packet Tracer `9.0.1.0858`.

Router0 was not executed. `3650-24PS` was not touched. `poe_ports`,
`supports_poe` and `_AUTHORIZED_OBSERVATION_METHODS` are unchanged by this
record.

## 1. The question this record closes

`POE_ACCESSPOINT_DIFFERENTIAL_20260907.md` ended on a named, unobserved
candidate. The endpoint-side contract could not decide the access-point
bindings, because `AccessPoint-PT` is lit the moment it exists and the required
dark control state is unattainable. Its §3 proposed the one surface that does
not care whether the powered device has a supply of its own:

> An observable read at the delivering end does not care whether the powered
> device has its own supply, so it is the one candidate that could close the
> access-point bindings rather than route around them.

POE-2 asked exactly that, on the exact binding the physical design demands on
`MLS6`, rederived from `cp_scale_physical_design()` at the frozen SHA:

| Switch | Port | Endpoint | Endpoint port |
| --- | --- | --- | --- |
| `3560-24PS` | `FastEthernet0/13` | `AccessPoint-PT` | `Port 0` |

Identity comes from the fixture, never from the CLI `Device` column.

The answer is **NEGATIVE**. The 3560 delivers nothing to the access point.

## 2. What was measured

Run `poe2-20260907T173336Z-b4d3459e`, three states, two captures each for
stability, read through `observe_poe_inline_status()`:

| State | `Fa0/13` row | Delivery |
| --- | --- | --- |
| `AUTO_1` | `auto off 0.0 n/a n/a 15.4` | `not_delivering` |
| `NEVER` | row absent | `not_delivering` |
| `AUTO_2` | `auto off 0.0 n/a n/a 15.4` | `not_delivering` |

`Available:370.0(w) Used:0.0(w) Remaining:370.0(w)` throughout, every one of the
24 rows `off 0.0`.

The sharpest statement of the finding is a hash. `auto_1.txt`, `auto_2.txt` and
the restore read-back are **byte-identical** to the supplemental calibration's
`pd_absent.txt` — the capture taken with the powered device physically removed
and its absence independently proven (`endpoint_absent`, `links == 0`):

```text
d338b3213b4ca316a8132bd56540d13edf6e2dcfc5c61abbae425e46f6855e11
```

From the PSE's point of view, connecting an `AccessPoint-PT` to `Fa0/13` is
indistinguishable from connecting nothing at all.

## 3. Why the absence is attributable and not an acquisition failure

A zero is only a result if the apparatus is known to be able to print a
non-zero. Three independent controls establish that here.

**The port was driven.** Under `power inline never` the `Fa0/13` row disappears
from the table entirely, and returns under `auto`. The switch was listening.

**The same port on the same model delivers.** The supplemental calibration
(`poe2-off-calibration-7bb812cdf106`, non-productive, committed) put a `7960` on
a `3560-24PS` `Fa0/13` and measured `auto on 10.0` → device removed
`auto off 0.0` → reconnected `auto on 10.0`. The PSE, the model and the port are
all proven capable of delivery.

**Packet Tracer treated both endpoints alike at creation.** It attached a power
distribution device of its own in both runs — `Power Distribution Device4` for
the phone, `Power Distribution Device5` for the access point, both retired at
teardown. The phone still drew 10.0W. So the residue does not explain the
access point's zero.

Every capture, including the restore read-back, carries all eight gates true:
`observer_complete`, `all_pagers_traversed`,
`expected_privileged_prompt_reached`, `no_pending_continuation`,
`attributable`, `stable`, `dispatch_integrity_valid`, `fresh`. This is the run
where the prompt gate actually held; the earlier `poe2-20260907T164304Z-496d77e1`
attempt is retained as `UNKNOWN` and is not reused.

The negative is not an inference from an uncharacterised zero, and the code
refuses to let it be one. Strip the calibration reference from the bundle and
validation fails with `No calibrated causal result`. That is asserted in
`tests/test_poe2_ap_bundle_artifact.py`, not merely stated here.

## 4. What this settles, and what it does not

**Settles.** The switch-side observable — the one candidate POE-1 named for
closing the access-point bindings — does not close them. It answers, cleanly and
repeatably, that there is no delivery to observe on this binding. `AccessPoint-PT`
is not a powered device to a Packet Tracer `9.0.1.0858` PSE. Both ends of the
question now agree: the endpoint has no dark state to show, and the switch has
no wattage to report.

**Does not settle.** This is one exact binding. It is not permission to record
`supports_poe = UNSUPPORTED` for any switch, not a statement about
`3650-24PS`, not a statement about `AccessPoint-PT-A`/`-N`/`-AC`, and not a
statement about any other port. No extrapolation is made and the bundle is
pinned so none can be added quietly.

**Authority.** `INTEGRATION_RESULT = NOT_ATTEMPTED`. A negative authorizes
nothing, so nothing was integrated. `_AUTHORIZED_OBSERVATION_METHODS` remains
`{"manual_visible_power_state"}`, the eleven `AccessPoint-PT` bindings stay
UNKNOWN, and `HardwarePlan` admission remains unreachable through them.

## 5. The PSE observable itself came out intact

Worth separating from the access-point verdict: the observable works. It
distinguished delivering from not-delivering across six governed captures, it
survived the pager and prompt gates, and its typed reading agreed with its raw
bytes every time.

What POE-2 measured is that this particular endpoint has nothing to deliver to.
A PSE-based positive is still constructible for the phone bindings, where
delivery demonstrably occurs — and that is the shape that would let E5 authorize
PoE without requiring a human to look at a phone, by converging validated manual
evidence and validated PSE evidence on one exact authorized claim rather than by
widening the manual allowlist. That integration is a separate ticket with its
own RED-first tests; it is not started here, because this experiment returned
NEGATIVE and a negative earns no authority.

The frontier it would have to respect is already pinned, outcome-independently,
in `tests/test_poe2_pse_authority_boundary.py`.

## 6. Evidence

```text
docs/reference/cp-scale/canonical-live-evidence/poe2-20260907T173336Z-b4d3459e/
  evidence.json   9355a78a25ba406785ecac083de9185df8f15a6819c5f6a7bc2b648c326eb834
  auto_1.txt      d338b3213b4ca316a8132bd56540d13edf6e2dcfc5c61abbae425e46f6855e11
  never.txt       1baec69545dbf387e76dd486fcf9e71ddb5a0c9def2c150da7c068c90d4a2379
  auto_2.txt      d338b3213b4ca316a8132bd56540d13edf6e2dcfc5c61abbae425e46f6855e11
  restore.txt     d338b3213b4ca316a8132bd56540d13edf6e2dcfc5c61abbae425e46f6855e11
```

Supporting, non-productive:

```text
docs/reference/cp-scale/canonical-live-evidence/poe2-off-calibration-7bb812cdf106/
  evidence.json   34673ae29106fee49570233b05b72f778314d01b4e9d7af35dc5ad94cf3ea68b
docs/reference/cp-scale/canonical-live-evidence/poe-inline-calibration-poe1-c5626851.json
  SHA256          f870b200d14e79c6a11bd656664f543fa5b91da9c41ab6310cf1ff3cd4584dd8
```

## 7. Boundary

Fixture removed endpoint-first, both disposables deleted, PT's own residue
retired, inventory fingerprint identical before and after
(`6dcf441925b41cd5b1aa575f810a273ab617588f8ce8746627214dd48298f6ea|`), Realtime
restored, mailbox clean, heartbeat fresh, the same two PT processes (12960,
28932) before and after, no save issued and `saved_filename` still empty, frozen
source unchanged, `transport_problems` empty.

Transport is recorded as it was: IPC over the user-ACL file mailbox, plus a
fresh authenticated HTTP listener on 54321 whose gate was exercised (401 without
token, 200 with). No webview HTTP connection is claimed.
