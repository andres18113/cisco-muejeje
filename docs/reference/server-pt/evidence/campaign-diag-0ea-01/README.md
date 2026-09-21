# Campaign `SERVER-PT-DIAG-0EA-01`: additive closeout addendum

Navigation, provenance and one verification result. Nothing here authorizes a
run, promotes a capability or changes an earlier record.

The campaign's own package stays outside this repository, exactly as the
operator holds it: `SERVER-PT-DIAG-0EA-01-FINAL-5296984.zip`, 39,180 bytes,
SHA-256 `d30eeabc3fbb034e851e9519451fe1d8c196c7151c900e85e52b5af280755c11`,
whose 30 members total 223,052 bytes across three attempt directories, a
campaign index and a final manifest. This directory adds to that chain and
replaces none of it. The package, its attempt files, its per-attempt manifests
and `FINAL-MANIFEST.sha256` are unmodified, and the records that called each
attempt `stopped` or `completed` remain historical facts.

| File | What it is |
| --- | --- |
| `ADDENDUM-01.sha256` | digests of this addendum, the archived work order, the unmodified package and the three recovered attempt markers |
| `verification-01.json` | the result of recomputing 62 digests against the package's own manifests, plus the read-only census this delivery took |
| [`../../assignments/Codex_Next_Product_Readiness_5296984.md`](../../assignments/Codex_Next_Product_Readiness_5296984.md) | the work order this addendum answers, archived byte-for-byte |
| [`../../assignments/Codex_ServerPT_Diagnostic_Goal_DRAFT.md`](../../assignments/Codex_ServerPT_Diagnostic_Goal_DRAFT.md) | the pre-authorization campaign proposal, archived byte-for-byte; its own header says `READY_FOR_AUTHORIZATION - NOT A LIVE GRANT` |

## What this addendum verified

Every digest below was recomputed from the bytes on disk. Nothing was taken on
the strength of a number quoted elsewhere, including by the work order.

| Check | Scope | Result |
| --- | --- | --- |
| Archive identity | the delivered ZIP | measured SHA-256 equals both the work order's statement and the operator's sidecar `.sha256` |
| `FINAL-MANIFEST.sha256` | 7 entries | 7 match |
| Per-attempt `manifest.sha256.json` | 8 + 9 + 8 entries | 25 match |
| Archive against the extracted tree | 30 members | every member byte-identical |
| **Total** | **62 comparisons** | **0 mismatches, 0 missing** |

## The three permanent attempt markers

They were never lost. The coordinator deliberately leaves an attempt marker in
place after release, because an attempt identity that has been used must never
be reservable again, and `FINAL-MANIFEST.sha256` names each one by its exact
`%LOCALAPPDATA%` path. All three are present, 160 bytes each, and match the
digests the manifest already held.

| Marker | Manifest SHA-256 | Recomputed | Runner PID | Claimed at |
| --- | --- | --- | --- | --- |
| `attempt-1cec3a925255de16907519d1c2919fed.json` | `7d31cc42...aaaadb` | equal | 34708 | `2026-09-21T19:09:40.187624+00:00` |
| `attempt-08a06b738839b6f48f4b24516089ac09.json` | `3b102060...910aa1` | equal | 39124 | `2026-09-21T20:01:43.405474+00:00` |
| `attempt-f2148bbd568a49391a26e83c6efcc67e.json` | `95e2de98...149992` | equal | 57572 | `2026-09-21T20:09:01.358759+00:00` |

Each marker also binds to exactly one delivered record through
`authorization.attempt_id`, one-to-one with nothing left over on either side.
That binding holds independently of the manifest, which is why it is recorded
here as well as the digest comparison.

## The post-restart census was retained, and is separate from today's

`processes-postrun.json`, `mailbox-postrun.json` and `campaign-postrun.json`
exist for all three attempts and are covered by the verified per-attempt
manifests. The historical observation therefore needed no reconstruction and
none was attempted. They record each attempt's Packet Tracer instance cohort
(parent PIDs 50940, 25248 and 7704 with their child renderer processes, all
from `C:\Program Files\Cisco Packet Tracer 9.0.1\bin\PacketTracer.exe`) and a
mailbox holding only `alive.txt` at each attempt's end.

This delivery also took a new read-only OS census. It establishes **current
state only** and is recorded as such: at `2026-09-21T21:53:27Z` no Packet
Tracer process is running, the three runner PIDs and the three instance PIDs
are absent, and the mailbox holds no `req_*` and no `res_*`, only `alive.txt`
last written `2026-09-21T20:12:43Z` beside the campaign subdirectory. That the
attempt-1 instance is absent **now** is a later fact about a different moment.
It is not evidence about how that process ended.

## The force-termination sequence, preserved rather than reconciled

Four dated statements, each left exactly as its own artifact records it:

| When | Artifact | What it says |
| --- | --- | --- |
| `2026-09-21T19:09:39Z` | D-DHCP attempt 1 `authorization.json` | `force_termination_authorized: false` |
| `2026-09-21T20:01:40Z` | D-DHCP attempt 2 `authorization.json` | `force_termination_authorized: false` |
| `2026-09-21T20:07:16Z` | D-DHCP attempt 2 `retirement-observation.json` | `authorized_force_termination: true`, `force_termination_performed: false`, reason `exact_primary_absent_before_action`, empty process list |
| `2026-09-21T20:08:58Z` | D-WEB `authorization.json` | `force_termination_authorized: true` |

The operator lifecycle permission arrived between `20:01:40Z` and `20:07:16Z`.
The retirement record states in its own fields that the exactly identified
process was already absent before any action, so force termination was
**authorized and not performed**. No earlier envelope is edited to agree with a
later one, and consent is not inferred from an envelope's own fields.
`CAMPAIGN-INDEX.md` carries the operator's acceptance of the local
receiver-gate limitation and the grant of D-DHCP v3 and D-WEB v3, and is itself
covered by the verified manifest.

## What the carried-forward evidence still does not say

Unchanged by this addendum, and repeated because the verification above makes
it tempting to read more into the readings than they contain.

- D-DHCP attempt 1 stays immutable and is not reinterpreted. Its retained
  postflight response and `restoration_proven=false` are what it says.
- D-DHCP attempt 2 localizes the first native-default difference to the WHOLE
  `configurePcIp` interval on exactly four fields. **No client acquisition was
  measured.** The native default and the intended pool share subnet
  `192.0.2.0/24` and the realigned native range `192.0.2.0`-`192.0.3.255`
  contains the intended pool's single address `192.0.2.100`, so stored
  coexistence is not proof that the intended pool would serve a client.
- D-WEB's `FWD` sample belongs to W5 AFTER the fetch. There is no
  "ping caused STP forwarding", no cold-path success and no product-level
  cause. W1 observed `LIS` on VLAN 1 `Fa0/1`-`Fa0/3` and is explicitly
  inconclusive.
- Offline evidence does not establish LIVE Packet Tracer behaviour. The product
  forwarding prerequisite delivered alongside this addendum is verified offline
  only; its LIVE behaviour stays unverified until a separately authorized and
  observed run exists.

## What this addendum is not

It resets no attempt counter, grants no retrospective approval, promotes no
capability and authorizes no merge or publication. D-DHCP used both of its
permitted attempts and D-WEB used one of two; this addendum consumes neither
and revives neither. No Packet Tracer launch, contact, termination, command
publication, wildcard cleanup or marker recreation was needed or performed.
