# Campaign SERVER-PT-DHCP-FASTLOOP-01: episode 1 evidence

Byte-for-byte copies of every artifact of LIVE episode 1, taken after the
episode closed. `MANIFEST.sha256` holds the SHA-256 of each file, with its path
relative to this directory. Directory names are kept short so a clone stays
within the Windows path limit; every file name and byte is the original. The interpretation, the chronology and the claim
boundaries are in the
[DHCP fast-loop brief](../../../../engineering/change-briefs/server-pt-dhcp-fastloop.md),
sections *LIVE episode 1* and *Measured results per M-DHCP identifier*.

| Path | Origin |
| --- | --- |
| `e1/` | lead files: the episode plan and closing, the launch capture, the exact qualification argv, each command's stdout, stderr and exit code (`01` open episode, `02` launch, `03` record launch, `04` qualification, `05` retire, `07` close episode) and `06-exit-observation.json`, the read-only census after the operator answered the save prompt |
| `store/` | `data/commissioning/SERVER-PT-DHCP-FASTLOOP-01/` of the executing checkout: the four ledger records, the launch record, the qualification status and its archive admission, the refused retirement attempt, the source reference to the qualification record, the current status and the hash index |
| `record/` | the immutable qualification record `q3-fl-c1-2026-09-25T03-12-05Z-97cc881e.json` |

Scope: checkpoint `5df8d05`, Packet Tracer 9.0.1.0858, file channel, one blank
campaign-owned laboratory. The retirement attempt is refused, because the
campaign never forces. The process exit followed the operator's answer to
Packet Tracer's save prompt. It is lead-observed and is not a campaign
retirement record. No capability is promoted by anything here.
