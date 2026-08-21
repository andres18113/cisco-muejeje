# EIGRP runtime qualification — CP3-HARD

Date: 2026-08-20

Packet Tracer: `9.0.1.0858` on Windows 11 Pro 64-bit

Qualified model: `1941` only

Transport: governed file bridge

## Purpose and claim boundary

This qualification resolves the two E10-blocking rows identified by the E9.5
canonicalization audit: `EIGRP adjacency` and `EIGRP routes`. It also measures
forwarding as a separate behavioral claim. It does not enter E10, qualify EIGRP
on 2911, qualify failover, or promote configuration acceptance into operational
evidence.

The claims remain distinct:

```text
configured EIGRP process != adjacency
adjacency                != learned route
learned route             != forwarding
```

## Governed runner and isolation

The reproducible operator entrypoint is
`tools/eigrp_runtime_qualification.py`. It requires `--execute`, refuses a
workspace containing any semantic device or link, uses typed production actions
and registered IOS queries only, never saves a `.pkt`, and removes every created
semantic device in `finally`.

The final run established before mutation, in the process performing mutation:

```text
sys.executable             = checkout-local .venv/Scripts/python.exe
packet_tracer_mcp.__file__ = this worktree/src/packet_tracer_mcp/__init__.py
loaded package namespaces = packet_tracer_mcp only
import isolation          = ISOLATED
baseline inventory        = 0 semantic devices; 0 links; 1 backend PDD
```

The disposable slice identity was `cp3-eigrp-topology-v1`: two 1941 routers,
two PC-PT endpoints, two /24 LANs, one /30 Ethernet transit, and EIGRP AS 100.
The exact routed addresses were:

| Object | Address |
| --- | --- |
| R1 LAN / PC-A | `198.18.210.1/24` / `198.18.210.10/24` |
| R2 LAN / PC-B | `198.18.211.1/24` / `198.18.211.10/24` |
| R1 / R2 transit | `198.18.212.1/30` / `198.18.212.2/30` |

No separate physical hash was emitted. The evidence instead records the exact
typed topology identity, seven physical mutations, six foundational typed
configuration actions, two typed EIGRP actions, fresh inventory before and
after, and exact cleanup targets.

## Fresh observations

Configuration/application was only `APPLIED`: both typed EIGRP actions were
accepted by the product channel. Verification came from later independent
registered observations:

| Layer | Result | Fresh evidence |
| --- | --- | --- |
| Process | 2/2 `VERIFIED` | `fresh_show_ip_protocols_eigrp`; AS 100 and router IDs `198.18.210.1` / `198.18.211.1` |
| Adjacency | 2/2 `VERIFIED` | Complete `show ip eigrp neighbors` windows; each router had the exact transit peer, queue count 0, and the peer router ID was independently corroborated from the peer process |
| Learned route | 2/2 core claims verified in one read | Complete `show ip route eigrp` windows; R1 learned `198.18.211.0/24` via `198.18.212.2`, and R2 learned `198.18.210.0/24` via `198.18.212.1`, both code `D` |
| Forwarding negative control | 2/2 fresh unreachable | Before EIGRP, PC-A to PC-B and PC-B to PC-A each returned 0/4 received (100% loss) |
| Forwarding positive control | 2/2 fresh reachable | After EIGRP, the same two typed flows each returned 4/4 received (0% loss), with `confirmed_unique` source provenance |

The route observer's aggregate is deliberately `PARTIAL`: protocol, network,
prefix length, and wildcard are `VERIFIED`, while `segment_id` is
`UNOBSERVABLE` because it is semantic plan metadata rather than an IOS device
property. That ceiling does not weaken the learned-route claim: the exact
EIGRP RIB prefix and mask are directly verified in both directions.

The fixture-backed negative controls also establish the product semantics:
a fresh supported-empty neighbor or EIGRP route table fails a required
adjacency/route expectation; it is not classified `UNSUPPORTED` or silently
promoted.

## Cleanup and durable evidence

The runner observed cleanup twice, then a separate checkout-local production
process independently observed it again:

```text
first final inventory  = 0 semantic devices; 0 links; 1 backend PDD
second final inventory = 0 semantic devices; 0 links; 1 backend PDD
independent inventory  = 0 semantic devices; 0 links; 1 backend PDD
cleanup verified       = YES
```

The machine-local full evidence packet is intentionally gitignored at
`data/eigrp-runtime-qualification.json`. Its final SHA-256 is
`E08874E717C29ED8145F66F28449B958BDFBA64D52C9DD87A7E607E312387541`.
The observed row shapes are preserved as regressions in
`tests/test_ios_terminal.py`; typed observer semantics and negative controls are
preserved in `tests/test_enterprise_control_plane_runtime.py` and
`tests/test_eigrp_runtime_qualification.py`.

Full governed regression after the implementation change:

```text
2483 tests; 0 failures; 0 errors; 0 skipped
```

## Classification and gate result

```text
EIGRP configuration capability, 1941 = SUPPORTED
EIGRP process state, 1941            = VERIFIED / 2 OF 2
EIGRP adjacency                       = FIXED_AND_VERIFIED / 2 OF 2
EIGRP learned routes                  = FIXED_AND_VERIFIED / 2 OF 2 CORE CLAIMS
EIGRP forwarding                      = NOT_REPRODUCED_WITH_EVIDENCE / 2 OF 2
EIGRP failover                        = UNKNOWN / NOT QUALIFIED HERE
2911 EIGRP capability                 = UNKNOWN / UNCHANGED
```

The defect was not a Packet Tracer observability ceiling. Current output was
available, but the product parsers returned no rows and the control-plane
runtime deliberately issued no EIGRP read-back. Fixture-backed parsers, typed
observers, exact peer dependencies, model-scoped capability evidence, and
focused regressions now close that gap.

Applying the literal current CP3-HARD contract after this qualification:

```text
P0 open debt                                      = 0
P1 correctness/evidence debt affecting E9.5      = 0
UNKNOWN states invalidating final E9.5 claims     = 0
debt blocking E10                                 = 0
contained explicit backend limitations           = 2 / unchanged

CP3_HARD                                          = PASS
E9_5                                              = CLOSED
E10_STARTABLE                                     = YES / NOT_ENTERED
```
