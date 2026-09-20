# Campaign `SERVER-PT-D02-Q3-Q1-AUTOFIX-01`, amendment 01 and focused closure 01

Navigation and provenance only. Nothing here authorizes a run.

The campaign's own package stays outside this repository, exactly as the
operator holds it: `SERVER-PT-D02-Q3-Q1-AUTOFIX-01.zip`, 127,800 bytes,
SHA-256 `1b71018ac383db84fa3ba64e58fa5a020e180e0d0b0d37cd2120e5d4e75dfa2f`,
whose 80 files total 318,993 bytes. It carries the three LIVE attempt
directories and the first three correction-ledger entries. This directory adds
to that chain and replaces none of it: the original package, its attempts and
its entries are unmodified, and the records that called the campaign terminal
remain historical facts.

| File | What it is |
| --- | --- |
| `amendment-ledger.jsonl` | appended entries `seq` 4 and 5; seq 5 links to seq 4 entry hash `5a2480e4…5b911` |
| `AMENDMENT-01.sha256` | digests of the archived amendment, the unmodified original package and the ledger entry |
| `FOCUSED-CLOSURE-01.sha256` | digests of the review addendum, amendment 01, the unmodified original package and the two-entry ledger |
| [`../../assignments/Codex_Continuation_A1_Q3_Q1_S1b.md`](../../assignments/Codex_Continuation_A1_Q3_Q1_S1b.md) | the amendment itself, archived byte-for-byte (16,758 bytes, SHA-256 `70f2b7ad…6e9040`) |
| [`../../assignments/Codex_243_Focused_Closure_and_Remaining_LIVE.md`](../../assignments/Codex_243_Focused_Closure_and_Remaining_LIVE.md) | focused review addendum, archived byte-for-byte (14,426 bytes, SHA-256 `4a5f96a1…5442a5`) |

## What the amendment changed, and what it did not

It authorizes the contract changes recorded as Block F of the
[current brief](../../../../engineering/change-briefs/server-pt-services.md):
typed native-default coexistence for Q3, one bounded readiness gate before any
network attempt, classifying E5 before E6, the explicit M-DHCP-3 omission, and
S1b offline on the measured `shared_content` branch. It also authorizes
fast-forward publication of `feature/server-pt-s3-dhcp` for exact-SHA CI and
the two successor attempts of its section 7.

It resets no attempt counter, grants no retrospective approval and promotes no
capability. Q3 keeps one unused attempt of its original three and Q1 one of its
original two; this amendment consumed neither. Q0, Q2 and Q1b remain out of
scope, as do pool removal, `dhcpRelease`, any reset, claim deletion and a merge
to `main`.

Focused closure entry `seq` 5 records the F1 through F4 corrections reviewed
against `243ddc8`: admitted shared-content writer projection, hard readiness
deadlines before Q3 client activation, strict later default snapshots and exact
staged-result reuse. Its offline behavior head is `35cbc7c` (tree `b534a2c`),
with Q3's recalculated planned worst case 59 of the unchanged 60-operation
ceiling. It records no LIVE attempt and promotes no capability.

## The two measurements this work is built on

Both are accepted only within their own scope, and neither is generalized.

- **One shared page store.** Q1 ordinal 1, record
  `q1-2026-09-19T23-00-53Z-b17240ad`
  (`7f7a4d91f4bf359a6cc56aa6ccb8a12d8fc08b5aabe9bfca6871c07e554a54cf`) wrote
  the existing `index.html` through each of a Server-PT's two web handles and
  read the change back through the other: distinct process objects, one page
  table, on build 9.0.1.0858 over the file channel at `c0307ca`. It does not
  demonstrate arbitrary page creation and it does not demonstrate protocol
  isolation. Its listener behavior stayed inconclusive: the HTTP positive
  control returned nothing within the deadline, so neither negative ran.
- **One native default pool.** Q3 ordinal 2, record
  `q3-2026-09-19T22-52-28Z-6d12894c`
  (`b303bd9dea2749c763ec53bac72b6f737cc695ed499da84b8ea965937f38d79b`)
  observed a disabled DHCP process holding exactly one pool: `serverPool`,
  with network, mask, gateway, DNS and start all `0.0.0.0`, end `0.0.2.0` and
  512 users. Two pools in one process are not two independent DHCP servers,
  and which pool a native server allocates from is unqualified. The record's
  MAC and mode rows prove the sampled getters, including a `false` mode and
  the `0.0.0.0` address and mask; they are not a true-mode bootstrap and not
  an acquisition.

Q3 ordinal 1 (`c3aa5707…4166a6`) stopped because the DHCP manager was
requested from the wrong receiver. Its process-exit observation remains
unconfirmed at its original deadline, and a later process disappearance does
not rewrite that artifact.
