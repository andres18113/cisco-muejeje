# DIAG-0EA-01 correction 02: source and time of the closeout claims

This additive correction supersedes only the source claims named below. The
original campaign ZIP, attempt files, `ADDENDUM-01.sha256`, `verification-01.json`
and earlier addendum remain unchanged. This correction grants no LIVE attempt,
process action, capability promotion or publication.

## The historical census claim

The earlier addendum called each attempt's `processes-postrun.json` a retained
post-restart census. Those files were taken at the **end of each attempt** and
still listed Packet Tracer processes. The D-WEB file lists PIDs 7704 and 33352.
They cannot be the missing later zero-process observation. The current-only
census recorded in `verification-01.json` was taken at
`2026-09-21T21:53:27Z` and establishes only that later instant. The author of
the prior addendum reported 62 matching digest comparisons against the
operator-held package; this correction does not repeat or invalidate that
reported verification. The original ZIP and a distinct historical post-restart
zero-process census were unavailable in this checkout. The claimed historical
zero-process state and its timestamp remain **not independently verifiable**
from the retained files accessible here.

## Original attempt-marker bytes

The files in [`markers/`](markers/) are byte-for-byte copies read from
`%LOCALAPPDATA%\packet-tracer-mcp\bridge\campaign\` for this correction.
All three were 160 bytes and matched the digests already recorded in
`verification-01.json` and the earlier manifest. Their source filesystem
modification times, measured in UTC, are:

| Marker | Source modified UTC | SHA-256 |
| --- | --- | --- |
| `attempt-1cec3a925255de16907519d1c2919fed.json` | `2026-09-21T19:09:40.1876241Z` | `7d31cc42e809663868674d5c95f1546c2811f61b482a7f6a1a17f7d866aaaadb` |
| `attempt-08a06b738839b6f48f4b24516089ac09.json` | `2026-09-21T20:01:43.4054748Z` | `3b102060e2dce6f0eccec5fd5dcfec2de4d51b18539e552383a6cdf742910aa1` |
| `attempt-f2148bbd568a49391a26e83c6efcc67e.json` | `2026-09-21T20:09:01.3587591Z` | `95e2de984b48ba37501b0ab4132d4e743e030e5636c3b05cc79ca01697149992` |

The original local files were read only. The copies preserve their content;
this directory does not recreate attempt identities or reset counters.

## Authorization provenance

The two D-DHCP authorization envelopes recorded `force_termination_authorized`
as false. The later retirement-observation and D-WEB envelope recorded true;
the retirement observation also recorded `force_termination_performed=false`.
These are dated agent-authored statements about authorization state, not the
operator's permission message. The prior addendum says the campaign index
contains the operator's grant and receiver-risk acceptance, but that index is
inside the unavailable operator-held ZIP, and no separate direct permission
message or lifecycle amendment was available in this checkout. The precise
grant source and time therefore remain **not independently verifiable** here.
The prior author's reported authorization is preserved as a reported claim,
without inferring a grant time from changes in envelope flags.
