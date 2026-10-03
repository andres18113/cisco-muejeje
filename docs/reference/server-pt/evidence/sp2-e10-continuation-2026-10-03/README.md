# SP-2 E9 continuation: E10 checkpoint report

Status: **ACTIVE_CONTINUATION_NOT_PHASE_ACCEPTANCE**. The implemented discriminator
and its private native measurement are delivered for review. The SP-2 phase is
incomplete; this report does not claim `READY_FOR_REVIEW` or public support.

## Source and evidence identity

- Checkout: `Cisco-MCP-server-services-goal-foundations`.
- Branch: `feature/server-pt-goal-foundations`; authoritative remote: `cisco`.
- Reviewed starting checkpoint: `2d38364dfc5269accc427ae1a99b359b3132d366`.
- Implementation commit: `f4496f24bee4ef3b322f0d7c8edf93c1b4f37970`.
- Corrected-test and actual E10 execution commit:
  `40d6cfc46f23a44c9e087c484664808324fe8436`.
- E10 execution tree: `566f4635697484f328c3514f4a1b4b1d443620bf`.
- E10 build/channel: Packet Tracer `9.0.1.0858`, `file`.
- Stage: `SP2-ELIGIBLE-ACQUISITION`, profile v2.
- Attempt: `cc423f961af6c86f4917687541af4133`, campaign episode 10.
- Exact execution-source CI: [37153740989](https://github.com/andres18113/cisco-muejeje/actions/runs/37153740989), six successful jobs.
- The archive publication successor changes documentation and evidence only.
  Its final SHA and exact CI are reported with delivery; it is not the native
  execution source. Historical E9 retains its original `ec3b01f...` identity.

[The immutable E10 archive](../sp2-generalized-dhcp-relay-01/e10/README.md)
contains 248 hashed files. Its complete manifest has SHA-256
`055fadc591055c6b89b2846eaa6d114bb5e866ce93104b2dee2876942b5f223a`.
[Whole-archive verification](checkpoint-manifest-validation.json) proves the
exact published file set, every content hash and equality with the sealed copy.
The post-E9 passive inspection remains a
[separately dated supplement](../sp2-e9-supplement-2026-10-03/README.md), outside
E9's manifest; it does not establish E9's failure cause.

## Implemented behavior

The separate v2 discriminator compares eligible APIPA clients under fixed
explicit-start/control assignments. Assigned clients remain observations;
unknown client state and shared policy, pool or identity contradictions cannot
authorize intervention or causal credit. Every effect requires fresh shared
observations and a typed acquisition guard inside the actual generated script.
That guard reads DHCP mode, address and mask before claiming or calling
`dhcpRun`; spontaneous prior acquisition becomes an observer, without restart.
The existing v1 protocol and ordinary typed acquisition default remain intact.

The retained shared window records real elapsed reads and effects, preserves
uncertain dispatch as a stop, and revokes conclusions after contradictory
shared observations. A separate common-session correction forwards the E6 wait
allowance. E9's qualification already supplied that allowance; the correction
is not an explanation of E9. Tests use generated scripts, retained/reloaded
records and negative cases; simulated event schedules are offline evidence.

## Native result and limits

E10 used 18 targets, 17 links and 11 clients. Four fixed explicit-start subjects
acquired stable usable leases with exact intended-pool joins:

| Subject | Observed address | First usable sample |
| --- | --- | --- |
| BR1-DEFAULT-PC-01 | 10.80.16.2 | 1 |
| BR2-DEFAULT-PC-01 | 10.80.33.75 | 1 |
| HQ-DEFAULT-PC-02 | 10.80.1.100 | 1 |
| HQ-DEFAULT-PC-03 | 10.80.1.101 | 2 |

All four effects had known single typed dispatch. Seven untouched controls
stayed unassigned. Later shared reads preserved the required server policy,
client identity, address/mask/gateway/resolver and lease joins. The observed
pattern is `explicit_start_only`, `SUPPORTED_IN_SAMPLE`. This contrast supports
choosing a maintained acquisition-lifecycle correction within the measured
scope; it does not establish a universal `dhcpRun` mechanism.

The **original product record is `failed`, `product_accepted=false`**: all 11
clients were APIPA before intervention, so dependent service requests were
withheld. The acquisition measurement's supported conclusion is a different
field. Post-intervention cold HTTP was not demonstrated. Registered default-
catalog mixed acceptance, native capacity, renewal, giaddr, exclusive serving,
universal table-end/absence and broader build/channel support remain unverified.

Qualification completed with 574 operations, 1,319.875 seconds elapsed and a
337.453 seconds of accumulated local authority observations. The separate
shared acquisition window lasted 139.531 seconds (recorded elapsed boundaries
1,104.5 to 1,244.031 seconds). There was no primary/secondary failure
or refused qualification call, and restoration was proven. The qualification's
top-level dirty-state field remains `unknown`; the later closing record and
owned retirement/exit census independently prove final cleanup `verified_clean`.
The owned cohort exited, with no process, mailbox command or campaign lock left.

## Verification

The complete local suite on execution source `40d6cfc` passed **8,893 tests**,
with six skips and three existing warnings in 1,556.47 seconds. Local skips were
two symlink-privilege cases, two absent ignored historical voice artifacts and
two unset opt-in native-window cases. The 256-case affected suite passed.
Quality, docs, namespace, whitespace and the clean exact-delivery gate passed.
The initial architecture-inventory failure was retained and reproduced; its
expected successor-handler table was corrected without weakening assertions.

[Per-job execution-source CI results and every skip reason](source-ci-test-results.json):

| Job | Passed | Skipped | Skip reasons |
| --- | ---: | ---: | --- |
| Windows / Python 3.11 | 8,893 | 6 | machine-local DHCP record 1; ignored voice artifacts 2; opt-in native windows 2; docs extra absent 1 |
| Windows / Python 3.13 | 8,893 | 6 | same six individually recorded reasons |
| Ubuntu / Python 3.11 | 8,877 | 22 | same six; Windows-only receiver reads 3 and Win32 ctypes cases 13 |
| Ubuntu / Python 3.13 | 8,877 | 22 | same 22 individually recorded reasons |

Actual offline loads constructed 2, 21, 201 and 997 clients; all four cases
passed. At 997: ten group scans, 6,020 dispatches, 3,559,991 response bytes,
24,607,650 serialized record bytes, 54.70 seconds and 184.3 MiB peak.
These substituted-component measurements do not prove native capacity.

## Campaign accounting and remaining requirements

The verified post-E10 ledger has no index findings or open episode. Cumulative
charged use is 3,192 operations and 9,018.09912 seconds; ordinary remaining
resources are 15,808 operations and 11,981.90088 seconds. E10's enclosing lifecycle
charge is 574 operations and 2,601.965429 seconds, including work outside its
qualification interval. The protected 1,000-operation/600-second finalization
reserve is excluded from the ordinary balance. These are observed balances,
not a new resource grant; any next effect needs fresh admission.

| Continuation requirement | Result |
| --- | --- |
| Preserve E9 and publish passive investigation with provenance | Completed; separate supplement |
| Prospectively answer the eligible acquisition question | Implemented and measured privately in E10 |
| Fresh guarded effects, shared evidence and negatives | Implemented, tested and independently reviewed |
| Actual offline scale and execution-source verification | Completed; 997 constructed clients and green exact-source CI |
| Maintained public product acquisition-lifecycle integration | Pending |
| Registered four-argument/default-catalog mixed 5 + 3 + 3 acceptance | Pending |
| Simultaneous native 36-client local demand | Pending |
| Phase-wide supported/refused scope and final independent review | Pending; no phase acceptance or merge |

The next engineering work is to integrate the measured guarded acquisition
policy into the maintained product's application frontier, including fresh
eligibility, cache invalidation and a positively evidenced no-recovery-needed
disposition for already assigned clients. Then qualify fresh public default-
catalog mixed and local-36 fixtures under the existing charter. The current
private discriminator does not promote generic DHCP/relay capabilities.
