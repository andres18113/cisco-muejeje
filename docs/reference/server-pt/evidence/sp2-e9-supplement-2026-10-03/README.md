# Post-E9 investigation supplement (2026-10-03)

This supplement preserves a later passive investigation. It is outside E9's
sealed archive and does not add observations to its historical manifest.
E9 executed `ec3b01f84896c9a392f7cc142443460c9d76b8eb`, tree
`dabbfd0a848e145e049f283073023f32dd842e07`; its published archive checkpoint is
`2d38364dfc5269accc427ae1a99b359b3132d366`. Neither identity changes here.

[Original investigation](original-investigation.md) was recovered byte for byte
from `data/services/sp2-governed/e9/root-cause/investigation.md`, 6,392 bytes,
last written `2026-10-03T16:53:24Z`. SHA-256:
`35437b945aa75358cfa0a1b08e5198d57857a6bd0e108427b194ee7648f91337`.

[Passive command and result](passive-listener-inspection.jsonl) preserve exactly
two original JSONL entries from session
`01a10229-9239-7dd3-ada3-f5becce6b6d6`, source lines 1091 and 1094:

- Command: `2026-10-03T16:36:29.627Z`, call
  `call_VPrDQLw4UXQadDeQ25uL9OeL`, read-only listener enumeration.
- Result: `2026-10-03T16:36:32.504Z`, exit 0, HTTP port 54321 listener count 0.
- Extract SHA-256:
  `246239b708476442f647d121b0449baa418ebe6f9fd43cfdeb82253686820237`.

The original session file was
`rollout-2026-10-03T09-27-21-01a10229-9239-7dd3-ada3-f5becce6b6d6.jsonl`
under the local Codex session folder for 2026-10-03. Adjacent session content
was excluded. The extraction preserves complete command/result entries without
reconstructing event timing.

The report's phrase “confirmed acquisition-order gap” identifies observed
lifecycle ordering and the missing intervention; it is not a proven native
cause. Its reconstructed timeline and recommendations retain their original
wording. Current continuation authority permits prospective eligible-cohort or
initial-order experiments without general reauthorization; packet events and
the old all-client APIPA oracle are not unconditional prerequisites.

The passive listener result describes the host after E9 retirement. E9 used
the file channel. It does not explain E9's simulated client HTTP behavior or
the reported UI Offline indicator. PC02's later positive samples establish
retained usable state, while E9's aggregate product status remains failed and
the ten other clients' dependent service requests were withheld. No native
retry, intervention, renewal, capacity or public capability is promoted here.
