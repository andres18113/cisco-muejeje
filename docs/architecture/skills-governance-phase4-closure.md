# Skills governance restructuring — Phase 4 behavioral closure

## Closure result

The Skills governance restructuring is **CLOSED** as of 2026-08-20. This record
contains the durable summary of authenticated fresh-client evidence. Raw JSONL
client logs, prompts, the PID ledger, and generated reports remain external
audit artifacts; their hashes are recorded below.

This closure changes no Packet Tracer product/runtime behavior, capability
claim, E9.5 gate, CP3-HARD result, or E10 prerequisite.

~~~text
SKILLS_GOVERNANCE_RESTRUCTURING = CLOSED
BEHAVIORAL_VALIDATION            = PASS
E9_5                             = OPEN
CP3_HARD                         = FAIL / UNCHANGED
E10                              = NOT_STARTABLE
~~~

## Authenticated isolation

| Item | Evidence |
| --- | --- |
| NEW baseline | 8638271b9ab2a5841dfac6ef59576956c6f25c84 |
| OLD baseline | 84df62be5530aa792c04a4b97f2bd4904d57180f |
| Client | codex-cli 0.148.0 |
| Model | gpt-5.6-sol, low reasoning effort |
| Fresh context | One codex exec --ephemeral thread per scenario |
| Skill discovery | Project-scoped .agents/skills projection |
| Auth isolation | One audit-owned CODEX_HOME using an isolated copy of the current file-backed cache |
| Process ownership | 38 recorded disposable PIDs, 38 completions, 0 timeouts, 0 surviving owned processes |
| Global state | Global auth hash unchanged; no logout, account replacement, global state write, or pre-existing process termination |

The previous 401 was an evaluation-infrastructure failure: the isolated fresh
client had no usable bearer source, and the server reported “Missing bearer or
basic authentication in header.” It was not a repository Skill defect. The
smallest safe repair was to copy the current file-backed cache into the
audit-owned CODEX_HOME and force file-backed credential storage there. A login
status check, a cheap layout smoke, an explicit packet-tracer-layout/SKILL.md
read, a model response, and token usage then proved the isolated mechanism
before the matrix ran.

NEW was exported deterministically for the operation audience and contained 16
ACTIVE Skills; network-autofix was absent. OLD used the bounded legacy/manual
projection from the immutable baseline and contained 17 Skill directories,
including network-autofix.

## NEW behavioral result

The 26-scenario matrix covers the required collision classes, clear positives,
hard near misses, multi-domain handoffs, single-domain non-orchestration,
PLANNED-remediation suppression, typed/raw boundaries, and current
source-of-truth behavior.

~~~text
INITIAL_RESULT                  = 25/26 PASS
FINAL_RESULT                    = 26/26 PASS
CORRECT_ACTIVE_PRIMARY          = 23/23
FORBIDDEN_SKILL_AVOIDANCE       = 26/26
NEAR_MISS_AVOIDANCE             = 17/17
PLANNED_AUTOFIX_SUPPRESSION     = 3/3
RAW_BOUNDARY                    = 4/4
SOURCE_FRESHNESS                = 11/11
MAX_DIRECT_SKILL_READS          = 3
DIRECT_SKILL_READ_HISTOGRAM     = 19x one, 5x two, 2x three
NEW_TOTAL_TOKENS                = 1,653,015
NEW_INPUT_TOKENS                = 1,633,609
NEW_OUTPUT_TOKENS               = 19,406
NEW_TOTAL_DURATION              = 697,261 ms
~~~

| ID | Expected primary | Final observed primary | Direct Skill reads | Result |
| --- | --- | --- | --- | --- |
| P01 | enterprise-orchestrator | enterprise-orchestrator | orchestrator | PASS |
| P02 | enterprise-network-design | enterprise-network-design | design | PASS |
| P03 | enterprise-ipam-capacity | enterprise-ipam-capacity | IPAM/capacity | PASS |
| P04 | enterprise-hardware | enterprise-hardware | hardware, capabilities | PASS |
| P05 | packet-tracer-capabilities | packet-tracer-capabilities | capabilities | PASS |
| P06 | enterprise-configuration | enterprise-configuration | configuration, runtime | PASS |
| P07 | campus-layer2 | campus-layer2 | Layer 2 | PASS |
| P08 | first-hop-redundancy | first-hop-redundancy | FHRP, capabilities, runtime | PASS |
| P09 | routing-igp | routing-igp | IGP, runtime | PASS |
| P10 | enterprise-services | enterprise-services | services | PASS |
| P11 | enterprise-voice | enterprise-voice | voice | PASS after fix/rerun |
| P12 | packet-tracer-runtime | packet-tracer-runtime | runtime | PASS |
| P13 | packet-tracer-layout | packet-tracer-layout | layout | PASS |
| P14 | network-acceptance | network-acceptance | acceptance | PASS |
| P15 | network-diagnosis | network-diagnosis | diagnosis | PASS |
| P16 | no current autofix primary | enterprise-configuration safe alternative | orchestrator, configuration, runtime | PASS with fan-out flag |
| P17 | no current autofix primary | none | hardware | PASS |
| P18 | enterprise-security | enterprise-security | security | PASS |
| P19 | routing-igp | routing-igp | IGP | PASS |
| P20 | routing-igp | routing-igp | IGP, capabilities | PASS |
| P21 | packet-tracer-capabilities | packet-tracer-capabilities | capabilities | PASS |
| P22 | enterprise-orchestrator | enterprise-orchestrator | orchestrator | PASS |
| P23 | enterprise-security | enterprise-security | security | PASS |
| P24 | no current autofix primary | none | orchestrator | PASS |
| P25 | network-diagnosis | network-diagnosis | diagnosis | PASS |
| P26 | routing-igp | routing-igp | IGP, runtime | PASS |

P16 loaded the orchestrator and its workflow reference before selecting the
typed configuration/runtime boundary. The semantic result was safe and the
total Skill fan-out remained within three, but the run is explicitly flagged
UNNECESSARY_ORCHESTRATOR and UNNECESSARY_REFERENCE_FANOUT. It does not
invalidate closure because the requested automatic mutation was refused,
network-autofix was not present or loaded, and no raw fallback was offered.

P17 called pt_fix_plan a raw offline helper in its output schema. That helper
is not the prohibited raw IOS, raw JavaScript, pt_send_raw, or developer
compatibility surface. It remained a bounded offline TopologyPlan correction
and did not activate network-autofix.

## Defect and rerun

P11 initially loaded enterprise-voice and network-diagnosis but incorrectly
made generic diagnosis primary for a failed phone registration. This was an
ordinary routing-description defect, not a governance contradiction.

The smallest fix:

- makes enterprise-voice explicitly own failed phone registration;
- makes network-diagnosis explicitly defer registration and call failures to
  enterprise-voice;
- adds the exact near-miss fixture and a focused regression.

The regression failed before the prose change and passed afterward. The
authenticated P11 rerun loaded only enterprise-voice, selected it as primary,
preserved the non-mutating evidence boundary, and used no raw or PLANNED
workflow.

## NEW versus OLD

The identical 10-case comparison subset measured semantic behavior and context
cost under the same client, model, reasoning effort, prompt protocol, auth
isolation, and machine.

| Measure | NEW | OLD |
| --- | ---: | ---: |
| Semantic result | 10/10 | 8/10 |
| Total tokens | 663,593 | 735,293 |
| Input tokens | 656,065 | 725,891 |
| Output tokens | 7,528 | 9,402 |
| Duration | 264,849 ms | 329,645 ms |

NEW used 71,700 fewer total tokens (-9.75%) and completed 19.66% faster on
that subset. These are observations, not causal claims, because native
Skill-load attribution is unavailable.

OLD failed P09 by declaring that routing-igp did not own RIPv2 inspection.
OLD failed P16 by activating network-autofix and declaring three supporting
Skills. OLD also declared 14 supporters for P01 and eight for P22, while NEW
kept orchestrator responsibility and specialist handoffs bounded.

## Observability and limits

~~~text
SKILL_LOAD_OBSERVABILITY = PARTIAL
~~~

The client emitted no native skill.load lifecycle event. Direct command reads
of the selected SKILL.md files are visible in every final NEW scenario and are
the load evidence used here. No invocation is inferred merely from answer
resemblance.

No Packet Tracer mutation or webview verification occurred. The matrix proves
Skill routing, boundaries, source-selection methodology, and output behavior;
it does not promote Packet Tracer capabilities or runtime evidence.

## Validation and artifacts

~~~text
SKILL_GOVERNANCE_VALIDATOR = PASS
FOCUSED_SKILL_TESTS         = 46 passed
FULL_PYTEST                 = reused prior governed 2474-test green evidence
PRODUCT_PYTHON_CHANGES      = NONE
~~~

| Artifact | SHA-256 |
| --- | --- |
| Behavioral matrix | C10808B128C4C7CB5FA5C2C3658B956C092C4BD0152AE9B550AE427285AF74B5 |
| Normalized grading | E4BB9858167962320DFC04482ECCED4103FBCAD1122C9B2367F2FAC371D370F4 |
| Initial NEW observations | 623C345F10A97F9F4B89195E805386F349ACEA998878A76CF6A8F0CFA9C462DA |
| OLD observations | 743B654AFC3D44C0BDFF0FF3FF520CEF0D529354844A7B38870D210DBA3A8E41 |
| PID ledger | 78DC734473B28C801A2A7F04FDCFFA244D042B8228ED29F5B2668C0F5A5E3C27 |
