You are implementing slice S0 ("Observation integrity") of the plan "Server-PT services for
PC-PT clients", revision 2.2 (Server-PT-Services-Plan-rev2.2.md, status READY_FOR_REVIEW), in
the repository andres18113/cisco-muejeje. Execution of this prompt requires that revision 2.2
has been approved by the technical director; the existence of this prompt authorizes nothing.
Any LIVE Packet Tracer action needs a separate, exact-scope authorization; this slice is
offline only and must never contact a running Packet Tracer instance or start a bridge for
product use.

Baseline: main at 6263344e31ba3b0de6539d652f2cd06fc73a3562. Before editing: verify checkout,
branch and starting SHA; confirm the alias of the authoritative main in your checkout (this
maintainer checkout calls it `cisco`, a standard clone `origin`; never infer it from a feature
branch upstream); read AGENTS.md, CLAUDE.md and docs/engineering/standards.md from this
checkout; run /context in a fresh session and record the result (pending if unobservable).
Create a feature branch; do not touch other worktrees.

Exclusions that apply to every slice: no muejeje.pts, Runtime V6, new .pts, dispatcher,
protocol version, replacement transport or new bridge endpoint; IoT and feature/iot-connectivity
untouched; no CP-LIVE, voice, PoE or namespace work reopened; no NTP/TFTP features; no GUI
automation; no commits to main; no Packet Tracer execution; no changes to EXTENSION/.
S0 additionally excludes: new ServiceType, action or expectation members; mutation_replay.py;
service_capabilities.py; evidence.py; service_plan.py; tool_registry.py; any MCP tool; the
E5 compiler, applicator and runtime; the security runtime; pyproject.toml. The two shared
domain DTO files below (execution.py, configuration_runtime.py) are the explicit exception to
"no E5 file": they are shared models, and every change to them is additive with legacy
defaults proven by table tests.

Risk: L (shared domain vocabulary, journal semantics, transport contract, evidence semantics).

Boundary of S0: the whole fact chain from transport to the E6 result, including its journal
and evidence representation, plus the test inventory that makes the chain checkable.

1. Domain facts. In src/packet_tracer_mcp/domain/enterprise/models/execution.py add
   `DispatchFact` {NOT_SUBMITTED, REJECTED, ACCEPTED, ACCEPTANCE_UNKNOWN, UNSPECIFIED},
   `ResultFact` {CORRELATED, ENGINE_ERROR, MALFORMED, NOT_OBSERVED, LOST, NOT_APPLICABLE},
   `PostconditionFact` {SATISFIED, UNSATISFIED, UNOBSERVED, NOT_APPLICABLE},
   `TransitionFact` {UNCHANGED, CHANGED, UNOBSERVED, NOT_APPLICABLE} (the transition of the
   state actually read) and `FootprintFact` {COVERED, PARTIAL, NOT_APPLICABLE} (whether that
   state covers everything the setter is documented to change) (execution.py is imported by
   configuration_runtime.py, so the facts live here to avoid a cycle). Add to
   `ExecutionJournalEntry`: `dispatch: DispatchFact = UNSPECIFIED`, `result: ResultFact =
   NOT_APPLICABLE`, `residual_change: bool = False`, `cause: str = ""`; make
   `journal_from_action_results` copy them with getattr defaults and keep its baseline
   `disposition_from_status` fallback: a fact-bearing result always carries an explicit
   disposition (UNKNOWN included), and the table test proves that the fallback never turns the
   UNKNOWN disposition of an APPLIED or PARTIAL result into a mutation. Extend
   `_derive_dirty_state` by exactly one rule: a FAILED entry with `residual_change=True` counts
   as a mutation, so a failed operation that left an observed unintended change yields
   DIRTY_RECOVERABLE when its inverse is available and DIRTY_UNRECOVERABLE otherwise; every
   other input maps as at the baseline (table test over the full product of dispositions,
   inverse flags and residual_change values, with the baseline function copied into the test as
   the oracle for residual_change=False only). `residual_change=True` is an observed fact and
   `False` is only the absence of that observation: unknown residue is carried by disposition
   UNKNOWN plus `cause`, never by `residual_change=False`. In configuration_runtime.py add to
   `RuntimeActionMutation` the observation fields `dispatch`, `result`, `postcondition:
   PostconditionFact = NOT_APPLICABLE`, `transition: TransitionFact = NOT_APPLICABLE`,
   `footprint: FootprintFact = NOT_APPLICABLE`, `attempted: bool | None = None` and `cause: str =
   ""` (no `residual_change` input: residue is a decision output); add the same seven fields
   plus `residual_change: bool = False` to `ActionApplicationResult`; add
   `ConfigurationFailureCode.OUTCOME_UNKNOWN`, `RESPONSE_MALFORMED` and
   `POSTCONDITION_UNSATISFIED`. Add `MutationDecision` (frozen dataclass: status, disposition,
   failure_code, residue in {NONE, CHANGED, UNKNOWN}, frontier: bool, sticky: bool, cause: str,
   row: str) and `decide_mutation(mutation) -> MutationDecision`, the single decision table of
   plan section 4.5, evaluated in this order: (a) legacy detection: every new fact at its
   default (dispatch UNSPECIFIED; result, postcondition, transition and footprint
   NOT_APPLICABLE; attempted None) selects row 16, the baseline rule on `applied` and the given
   `disposition`, frontier `satisfies_apply_dependency(status)`, residue NONE, not sticky;
   (b) admission: the tuple (dispatch, result, postcondition, transition, footprint, attempted,
   applied) must match exactly one of rows 1 to 15 and 17 to 20 of the table; (c) any other
   tuple, including one whose `applied` disagrees with `dispatch is ACCEPTED`, SATISFIED with a
   dispatch other than ACCEPTED, or CORRELATED without ACCEPTED, yields UNKNOWN, disposition
   UNKNOWN, OUTCOME_UNKNOWN, residue UNKNOWN, frontier closed, sticky, cause
   `inconsistent_facts`; the received fields stay on the row as diagnostics and grant nothing.
   `mutation_execution_status(mutation)` becomes `decide_mutation(mutation).status` and stays
   the only status entry point for baseline callers; rows with every new field at its default
   map exactly as the baseline (table test over every baseline disposition and both `applied`
   values, with the baseline function copied into the test as the oracle for those rows only).
   The decision-table test enumerates the full product of the seven inputs and asserts safety
   predicates rather than equality with a copy of the table: frontier open only on a validated
   SATISFIED postcondition or a legacy row; a single-entry journal CLEAN only with residue NONE
   and no sticky; every unlisted tuple UNKNOWN, closed and sticky; row 15 UNKNOWN with
   SESSION_FAILED; rows 3 to 8, 10, 15 and 19 sticky; the UNKNOWN disposition of rows 9, 10, 18 and
   19 preserved through the real `journal_from_action_results`. Convert the `(str, Enum)`
   classes of both files to `StrEnum` with `__str__ = Enum.__str__` (precedent:
   ImportIsolationState) and prove per enum that str(), format(), f-string, json.dumps,
   equality with the value, dict-key lookup, pydantic model_dump(mode="json") and round-trip
   identity are unchanged. Apply the same form to RequestDisposition in file_bridge.py. No
   `# noqa` anywhere in this slice. JSON compatibility: `ActionApplicationResult`,
   `ExecutionJournalEntry` and `ApplicationExecutionJournal` gain keys in model_dump output;
   prove that a baseline-shaped JSON fixture without the new keys still validates to defaults
   (shape of infrastructure/persistence/cp_scale_stage_evidence.py:78 output) and that every
   compact_summary() output is byte-identical to the baseline for legacy rows.

2. HTTP transport, src/packet_tracer_mcp/infrastructure/execution/live_bridge.py. Add
   `correlated_http_dispatch(js, timeout, *, base_url, port, token, http_connect_post, http_get)
   -> BridgeDispatchOutcome`, a frozen dataclass in the new
   infrastructure/execution/transport_outcome.py with fields dispatch, result, body,
   disposition (the RequestDisposition value as a string; transport_outcome imports only
   domain facts, file_bridge and live_bridge import transport_outcome, never the reverse)
   and detail (sanitized, bounded). Classification: POST /queue 200 -> ACCEPTED (acceptance by
   the local bridge queue, not by Packet Tracer); 400, 401, 409 or 503 -> REJECTED; a failure
   before the request bytes were sent (connection refused, name resolution) -> NOT_SUBMITTED;
   any failure after sending (read timeout, reset, disconnect) or an undecidable phase ->
   ACCEPTANCE_UNKNOWN. GET /result 200 -> CORRELATED; 204 -> NOT_OBSERVED; 404 or 410 -> LOST;
   socket error -> NOT_OBSERVED with detail "socket_error". Implement the phase split with a
   connect-then-send helper (http.client with an explicit connect(), or equivalent); the
   existing `_http_post`, `_http_get` and `correlated_http_send_and_wait` keep their
   signatures. Re-express `correlated_http_send_and_wait` as a wrapper and add a differential
   characterization test over every (status_post, status_get, body) combination against the
   frozen baseline body; that test is a regression guard, not the oracle. Add
   `PacketTracerHttpTransport.dispatch_and_wait`. The safety oracle is an independent truth
   table plus real-socket tests on an ephemeral port with PT_MCP_BRIDGE_TOKEN set (patterns:
   tests/test_bridge_security.py, tests/test_bridge_results.py): closed port -> NOT_SUBMITTED;
   a fake server that reads the request and closes without responding -> ACCEPTANCE_UNKNOWN;
   PTCommandBridge with no webview -> ACCEPTED plus NOT_OBSERVED; duplicate rid -> REJECTED; a
   result posted after the timeout is refused by the bridge (410) and never attributed.

3. File transport, src/packet_tracer_mcp/infrastructure/execution/file_bridge.py. Add
   `FileBridge.dispatch_and_wait -> BridgeDispatchOutcome`. Phases: `_ensure()` or
   `tmp.write_bytes` OSError -> NOT_SUBMITTED (discard any .tmp residue best effort);
   `os.replace` OSError -> ACCEPTED if the req_ path exists afterwards, else NOT_SUBMITTED;
   replace succeeded -> ACCEPTED; response read -> CORRELATED; read or unlink OSError after
   publication -> keep polling until the deadline, then NOT_OBSERVED; deadline -> NOT_OBSERVED
   carrying the per-call RequestDisposition from `_cancel`. `last_disposition` and
   `send_and_wait` are unchanged. Tests: failure before publication leaves no req_ file and
   reports NOT_SUBMITTED; failure after publication reports NOT_OBSERVED with a disposition; a
   second call after a failed first call never reports the first call's disposition;
   `proves_no_execution` stays False for every disposition. State in a comment that the engine
   filter `req_*.js` (EXTENSION/script-engine/main.js:179) is why a `.tmp` residue is not
   executable; do not test the engine.

4. Runtime, src/packet_tracer_mcp/infrastructure/execution/enterprise_service_runtime.py.
   Replace `_json_result` with `_observe(js, timeout) -> BridgeObservation(kind, payload,
   message, outcome)`; `{}` never stands for a failure. Accept `dispatch_and_wait` as an
   optional constructor argument; when only the legacy `send_and_wait` is given, wrap it: a
   body maps to result, engine_error or malformed, and None maps to ACCEPTANCE_UNKNOWN plus
   NOT_OBSERVED (never NOT_SUBMITTED). Mutation script (B1, C1): for every action the batch
   script performs a typed pre-read, the setter and an unconditional typed post-read, each
   inside its own try/catch, and reports
   `var r={id,attempted:false,skip_reason:"",call_error:"",call_result:null,pre_read:false,post_read:false,ok:null,changed:null,pre:null,post:null};`
   Pre-read: the typed value (`!!p.isEnabled()`, `!!p.isHttpsEnabled()`,
   `String(p.getPage(path))`, `!!p.getARecordWithAddress(h,a)`) is kept in a script variable;
   `pre_read=true` and `pre` = its digest only when the read completed. Ensure-present family
   (AddDnsRecord): when `pre_read` is true and the wanted record is present, the add is not
   called and `skip_reason="already_satisfied"`; otherwise `attempted=true` before the call,
   the native return is recorded as `call_result` (boolean) and never used for `ok`, and a
   bounded `call_error` is recorded on exception. Every other family always calls its setter
   (`attempted=true`). PublishTftpFile reports the declined row (`attempted=false`,
   `skip_reason="family_not_implemented"`, no reads), preserving its baseline FAILED outcome.
   Post-read: unconditional; `post_read=true` and `post` = its digest only when it completed;
   `ok` is the postcondition computed from the actual typed post value (`=== true` for a flag,
   `=== content` for the page string, `=== true` for the membership) and null when the
   post-read failed; `changed` is `preValue !== postValue` on the actual typed values and null
   when either read failed. Digests: booleans as "0"/"1"; strings as an FNV-1a 32-bit hash plus
   length computed by a helper defined once in the batch script; never a credential (no S0
   family carries one; record the rule for S2). Digests are bounded diagnostics with no
   authority: Python never compares them and derives no fact from them; equal hashes, equal
   lengths or a true `call_result` are never UNCHANGED, SATISFIED or CLEAN (the collision pair
   `yI76Uj5ZfPNL` / `qx51K0WT5Lj1`, both `1bb90b62:12`, is a harness scenario). Row validation
   (`row_invalid:<check>`, row 7): `results` must be a list of objects with `id` in the batch;
   `attempted`, `pre_read`, `post_read` bool; `ok` and `changed` bool or null; `pre`, `post`
   string or null; `call_result` bool or null; `call_error`, `skip_reason` string; `post_read`
   false requires `ok` and `changed` null; `pre_read` false requires `changed` null; both reads
   true require `ok` and `changed` non-null; `attempted` false requires `skip_reason` in
   {already_satisfied, family_not_implemented}, `call_result` null and `call_error` empty;
   `already_satisfied` requires `pre_read` true and either `ok` true or `post_read` false (a
   skipped row whose post-read contradicts its pre-read is invalid); `family_not_implemented`
   requires no reads; `attempted` true requires an empty `skip_reason`; a non-list or duplicate
   ids -> every action result MALFORMED; a missing id -> that action MALFORMED; foreign ids
   ignored and named in the message. Row -> facts for a CORRELATED batch, with footprint
   COVERED for every family except an attempted AddDnsRecord (PARTIAL,
   `footprint_partial:dns_a_record_table`) and COVERED for any skipped row (no call): invalid
   row -> row 7; declined -> row 20; `post_read` false -> postcondition UNOBSERVED, transition
   UNOBSERVED, cause `post_read_failed` (+ `call_error`), row 8; `post_read` true ->
   postcondition SATISFIED when `ok` else UNSATISFIED; `pre_read` false -> transition
   UNOBSERVED, cause `pre_read_failed`, rows 9/10; both reads -> transition CHANGED or
   UNCHANGED, rows 11 to 14 (COVERED, attempted), 17 (skipped) or 18/19 (PARTIAL); `cause`
   carries the bounded `call_error` when present. The runtime sets only the observation fields
   and `applied` (True for every ACCEPTED dispatch); status, disposition, failure_code,
   residue, frontier and sticky come from `decide_mutation` in the applicator. Whole-batch
   outcomes: ENGINE_ERROR, MALFORMED, NOT_OBSERVED, LOST -> every action postcondition
   UNOBSERVED, transition UNOBSERVED, footprint NOT_APPLICABLE, attempted None, applied per
   dispatch (rows 3 to 6). A transition observed between the two bracketing reads is reported
   as exactly that, within the observed scope of the family; it is never a claim of execution
   count, of sole causation or of anything outside that scope. Verification facts (B3): add
   `observation: ObservationFact` with members OBSERVED, CONTRADICTED, INCONCLUSIVE,
   SUBJECT_NOT_FOUND, MALFORMED, ENGINE_ERROR, NOT_OBSERVED, LOST, ACCEPTANCE_UNKNOWN,
   NOT_SUBMITTED, REJECTED, NOT_ATTEMPTED and UNSPECIFIED (the default, meaning "producer did
   not state a fact"), plus `cause: str = ""`, `claim_level: str = ""` and `limitations:
   list[str]` on RuntimeServiceVerification in domain/enterprise/models/service_runtime.py; the
   runtime never sets failure_code (the applicator derives it, so ServiceVerificationResult is
   built without a duplicate keyword). Status mapping: OBSERVED -> VERIFIED, fresh_evidence
   True; CONTRADICTED -> FAILED, fresh_evidence True (a fresh observed contradiction is fresh
   negative evidence); INCONCLUSIVE -> UNKNOWN, fresh False; SUBJECT_NOT_FOUND, MALFORMED,
   ENGINE_ERROR -> UNOBSERVABLE, fresh False; NOT_OBSERVED, LOST, ACCEPTANCE_UNKNOWN,
   NOT_SUBMITTED, REJECTED -> UNKNOWN, fresh False, with cause. Direct read-back: fresh iff
   the read was CORRELATED and parsed to the typed shape and located its subject; found False
   or process missing -> SUBJECT_NOT_FOUND; a matching read of an unchanged value ->
   OBSERVED; a mismatching complete read -> CONTRADICTED; the generated getter payload is
   byte-identical to the baseline (golden test). DNS behavior: a complete fresh window
   ("packets: sent" or a not-found line) with the wrong address or a not-found line for a
   positive expectation -> CONTRADICTED; a complete not-found window for the negative control
   -> OBSERVED; an incomplete window at the deadline -> INCONCLUSIVE; pager active or command
   not started -> INCONCLUSIVE with cause (not FAILED). HTTP behavior: content changed and
   marker present -> OBSERVED; content changed and marker absent -> CONTRADICTED; marker
   present before the request -> INCONCLUSIVE with cause "marker_present_before_request";
   no content change by the deadline -> INCONCLUSIVE with cause
   "no_response_within_deadline"; go() false -> INCONCLUSIVE with cause "client_go_false";
   the http-scheme scripts (start, inspect, release) stay byte-identical to the baseline
   (golden test). HTTPS: on the https scheme only, the start script calls setHttps(true)
   before go() and reports `https_mode` from isHttps() in the same payload; `https_mode`
   true -> continue; false -> CONTRADICTED "https_mode_not_confirmed"; absent or non-boolean
   -> MALFORMED (missing is neither false nor true). An empty marker never yields VERIFIED for
   https: PARTIAL with observation OBSERVED and limitations ["no_https_marker"]. Release the
   owned client on every exit path and record released, release_failed or release_unverified
   in observed. A verify() exception is caught inside the runtime and yields UNKNOWN with
   cause "exception:<TypeName>".

5. Applicator, src/packet_tracer_mcp/application/use_cases/apply_services.py. For every
   mutation row call `decide_mutation` once and build ActionApplicationResult from the received
   facts (dispatch, result, postcondition, transition, footprint, attempted, cause) plus the
   decision outputs (status, disposition, failure_code, residual_change = residue is CHANGED);
   no consumer in this module or downstream reads `applied` or the raw `postcondition` to decide
   anything. An exception from runtime.apply_actions yields, for every action in the batch, the
   row 15 fact tuple (dispatch UNSPECIFIED, result NOT_APPLICABLE, postcondition UNOBSERVED,
   transition UNOBSERVED, footprint NOT_APPLICABLE, attempted None, applied False, cause
   "exception:<TypeName>") passed through the same decision: status UNKNOWN, SESSION_FAILED,
   never applied=False/FAILED. A missing mutation row yields the row 7 tuple with cause
   "row_missing": status APPLIED, disposition UNKNOWN, RESPONSE_MALFORMED, sticky. Keep a
   runtime-supplied failure_code only for legacy rows (only NONE is replaced: NONE with applied
   -> NONE, NONE without applied -> APPLICATION_FAILED). Effect uncertainty: call
   execution_journal.mark_transport_unknown() exactly when any decision has sticky True (rows 3
   to 8, 10, 15, 19 and every inconsistent tuple); no field predicate re-derives it. Residue:
   for every decision with residue UNKNOWN add the limitation `residue_unknown:<id>:<cause>` to
   the E6 result; the journal entry carries disposition UNKNOWN and the cause, so `dirty_state`
   is UNKNOWN by the baseline rule and `residual_change=False` on such an entry is never read
   as "nothing changed". Frontier: `effect_established(result)` is the decision's `frontier` (a
   validated SATISFIED postcondition, or `satisfies_apply_dependency(status)` for a legacy
   row); dependents of an action that is not established become DEPENDENCY_BLOCKED with message
   "prerequisite_outcome_unknown:<id>" (UNOBSERVED or inconsistent facts) or
   "prerequisite_unsatisfied:<id>" (UNSATISFIED); independent actions and services continue.
   Verification admission: an ACTION_APPLIED prerequisite is satisfied only by
   `effect_established`; when it is not, an expectation whose kind is read-only or
   owned-temporary (module constant VERIFICATION_EFFECT_CLASSES: DIRECT_SERVICE_STATE
   read-only; DNS_RESOLUTION, DNS_NEGATIVE_CONTROL, HTTP_FETCH, HTTPS_FETCH, HTTP_BY_HOSTNAME
   owned-temporary; NTP_SYNC, TFTP_RETRIEVE read-only) still runs as a recovery read and its
   row carries the limitation "recovery_read_after_unresolved_action:<id>"; a user-state kind
   (none in S0) is DEPENDENCY_BLOCKED. A recovery read never changes the action row, never
   clears transport_unknown and never claims an execution count. Verification failure codes
   derive from status: VERIFIED -> NONE; FAILED -> VERIFICATION_FAILED (direct) or
   BEHAVIORAL_VERIFICATION_FAILED; UNKNOWN -> OUTCOME_UNKNOWN; UNOBSERVABLE ->
   DIRECT_READBACK_UNOBSERVABLE (direct) or OBSERVABILITY_LIMITATION; PARTIAL ->
   OBSERVABILITY_LIMITATION. A verify() exception reaching the applicator yields UNKNOWN with
   SESSION_FAILED, not FAILED. Aggregation: `_overall` returns FAILED with APPLICATION_FAILED
   when any action is FAILED; FAILED with POSTCONDITION_UNSATISFIED when any critical action
   is PARTIAL with that code; never VERIFIED while transport_unknown is set (PARTIAL, with
   limitations naming the action ids); a run whose only uncertainty is residue (rows 9 and 18)
   may be VERIFIED and reports `dirty_state` UNKNOWN with the `residue_unknown` limitation; a
   direct contradiction (direct FAILED with fresh evidence) caps usability_status at PARTIAL
   even when behavior is VERIFIED; direct PARTIAL or UNOBSERVABLE keeps the existing rule.
   Evidence: add `evidence_from_service_verification` in
   domain/enterprise/models/service_runtime.py; for observation UNSPECIFIED it delegates to the
   existing evidence_from_legacy_result (legacy producers keep their exact records); for
   explicit facts it sets observation_status OBSERVED (OBSERVED, CONTRADICTED), PROBE_FAILED
   (ENGINE_ERROR, MALFORMED, SUBJECT_NOT_FOUND, and, with limitation "transport:<fact>",
   NOT_OBSERVED, LOST, ACCEPTANCE_UNKNOWN, INCONCLUSIVE), NOT_ATTEMPTED (NOT_ATTEMPTED,
   NOT_SUBMITTED, REJECTED) and verification_status VERIFIED only for VERIFIED with
   fresh_evidence True. Do not modify evidence.py. Round-trip test: build runtime rows, pass
   them through the real ServiceApplicator, serialize the result with model_dump_json, validate
   it back, and assert that dispatch, result, postcondition, transition, footprint, attempted,
   residual_change and cause on action results, the journal entries' facts and UNKNOWN
   dispositions, the `residue_unknown` limitations, the verification rows' observation and
   cause, and the evidence records' observation_status and limitations are all still
   accessible and that `decide_mutation` on the validated-back facts returns the same decision;
   assert status agreement by behavior (an UNKNOWN row with a PROBE_FAILED evidence record is
   consistent), not vocabulary identity.

6. Generated-script harness. Add tests/test_service_mutation_script_harness.py following
   tests/test_typed_ping.py:196-276: a Node program that installs stub `ipc.network()`,
   device and process objects over an in-memory state, captures reportResult, and evaluates
   the actual batch script produced by PacketTracerEnterpriseServiceRuntime (captured through
   a recording dispatch callable). Scenarios: unchanged success, changed success, unchanged
   failure (setter is a no-op), changed-to-wrong (setter stores a different value),
   digest-collision pair (setter stores a different string whose FNV-1a digest and length equal
   the original: `yI76Uj5ZfPNL` -> `qx51K0WT5Lj1`), setter effect followed by a thrown
   exception, getter failure (pre, post, both), AddDnsRecord whose native add returns true
   while the membership getter reports missing, AddDnsRecord whose add leaves a different
   record for the same name (membership false before and after, table changed), AddDnsRecord
   that replaces an existing record with a different address (membership false then true, old
   record gone), AddDnsRecord skipped because the record is already present (NO_OP, no add
   call in the stub's call log), and a skipped row whose post-read contradicts its pre-read
   (row invalid). Feed the harness output to the runtime's row-to-facts mapping and assert the
   derived facts, the decision and the journal dirty_state through the real applicator; every
   expected value comes from the stub's actual state before and after and from its call log,
   never from the reported row, a digest or a fake disposition. Skip only when Node is absent
   locally; when the GITHUB_ACTIONS environment variable is set the test fails instead of
   skipping, so CI is the oracle. pyproject.toml is not changed.

7. Test inventory and authorized changes. Before implementation, list every assertion and
   fixture contract in tests/test_service_runtime.py, tests/test_service_application.py and
   tests/test_e95_service_voice_manifest_application.py and classify each as valid invariant,
   incidental representation or known incorrect expectation; commit that inventory in the
   change brief. Authorized changes, each with its before/after rationale in the brief:
   (a) mutation fixture rows `{id, applied}` in test_dns_actions_use_documented_process_api_and_json_escaping
   and test_http_content_is_serialized_and_never_interpolated_as_javascript become the item 4
   row contract, and `all(item.applied)` becomes an assertion on postcondition SATISFIED and
   applied True (incidental representation; the script substring assertions stay);
   (b) test_dns_behavior_rejects_a_fresh_but_wrong_address keeps FAILED and asserts
   fresh_evidence True with observation CONTRADICTED (known incorrect expectation: a complete
   fresh window with the wrong address is fresh negative evidence);
   (c) test_http_behavior_rejects_fresh_content_without_expected_marker keeps FAILED and
   asserts fresh_evidence True with CONTRADICTED (same reason);
   (d) the stale-marker half of test_http_behavior_rejects_stale_marker_and_accepts_fresh_fetch
   becomes UNKNOWN with INCONCLUSIVE and fresh False (known incorrect expectation:
   unattributed output is not a demonstrated failure); its fresh half is unchanged;
   (e) test_https_behavior_uses_https_url_and_never_substitutes_http adds `https_mode: true` to
   the start fixture, asserts the setHttps and isHttps calls, and changes VERIFIED to PARTIAL
   with limitation no_https_marker (R-HTTPS-03); its URL assertions stay.
   Everything else in those files is a valid invariant and stays unchanged, including
   test_direct_dns_readback_requires_enabled_state_and_expected_record,
   test_dns_behavior_starts_typed_ping_and_reads_only_fresh_command_output,
   test_dns_negative_control_requires_fresh_not_found_output,
   test_http_behavior_uses_a_fresh_background_client_and_releases_it,
   test_ntp_and_tftp_behavior_remain_unobservable_without_client_evidence and every test in
   tests/test_service_application.py (its FakeServiceRuntime is a legacy producer: rows
   without facts follow the legacy mapping, and its verification rows carry observation
   UNSPECIFIED, which never means OBSERVED). New tests go in new files:
   tests/test_execution_status_facts.py, tests/test_transport_dispatch_facts.py,
   tests/test_service_runtime_observation.py, tests/test_service_application_uncertainty.py,
   tests/test_service_mutation_script_harness.py. Golden-script equality (direct read-back,
   DNS verification, http-scheme verification) preserves the vendor-call surface only; it is
   not evidence of classifier equivalence, ownership, provenance or a live capability.

8. Ruff. Every touched file passes scripts/quality_gate.py. Measured at the baseline with
   ruff 0.16.7: execution.py 14 findings (4 UP042) and would be reformatted;
   configuration_runtime.py 21 (5 UP042) and reformat; live_bridge.py 12 and reformat;
   file_bridge.py 6 (1 UP042), already formatted; service_runtime.py 5 and reformat;
   enterprise_service_runtime.py 5 and reformat; apply_services.py 7 and reformat;
   tests/test_service_runtime.py 12, formatted. Own that debt in the files you touch and
   nowhere else. Split it into two commits per file set: first `ruff format` only, proven by
   AST equality (ast.dump before and after) and the unchanged suite; then lint fixes that add
   docstrings or reorder imports, proven by the suite, with no AST-equality claim. No `# noqa`.

9. Registry and catalog untouched: no new action families (mutation_replay.py unchanged);
   dispositions change no replay classification; service_capabilities.py unchanged; no
   ServiceType additions.

RED first. Each case must fail at the baseline for the stated reason, then pass:
- B1/C1a facts: harness scenario "changed-to-wrong" -> baseline row `applied=False` and journal
  dirty_state CLEAN; target FAILED disposition with residual_change True, action status
  PARTIAL with POSTCONDITION_UNSATISFIED, dirty_state DIRTY_UNRECOVERABLE (no inverse).
  "digest-collision pair" -> baseline `applied=False` and CLEAN, and a digest comparison would
  report unchanged; target transition CHANGED from the typed comparison, FAILED with
  residual_change True, DIRTY_UNRECOVERABLE. "setter effect then exception" -> baseline
  whole-batch PT_ERROR and `{}` collapse; target post-read still reported, facts derived from
  it. "getter failure (post)" -> target row 8 with `changed` null, never a transition claim.
- C1b facts: "add returns true, membership missing" -> baseline applied=True (short-circuit);
  target postcondition UNSATISFIED, footprint PARTIAL, disposition UNKNOWN, sticky,
  dirty_state UNKNOWN with `residue_unknown`. "incorrect add changes another record" and "add
  replaces an existing record" -> baseline CLEAN; target dirty_state UNKNOWN with
  `residue_unknown`, never CLEAN. "add already present" -> target NO_OP, no add call in the
  stub log, frontier open, CLEAN.
- R-OBS-07: a fully successful apply of COVERED families (EnableDnsService, EnableHttpService,
  SetHttpContent) -> baseline dirty_state "unknown" (measured offline); target CLEAN with
  CHANGED or REASSERTED from the harness rows. The same run plus AddDnsRecord on an empty table
  -> target usability unchanged, dirty_state UNKNOWN, limitation
  `residue_unknown:<id>:footprint_partial:dns_a_record_table`; a re-run with the record present
  -> NO_OP and CLEAN.
- R-OBS-01/02: send_and_wait None during apply -> baseline FAILED ("never left the process");
  target UNKNOWN with ACCEPTANCE_UNKNOWN under the legacy wrapper, APPLIED with disposition
  UNKNOWN and OUTCOME_UNKNOWN under an ACCEPTED outcome, and transport_unknown set in both.
- B2a/C2: ACCEPTED plus ENGINE_ERROR -> baseline FAILED; target APPLIED, postcondition
  UNOBSERVED, dependents DEPENDENCY_BLOCKED, transport_unknown set, bundle never VERIFIED.
  Runtime exception after dispatch -> baseline FAILED for the batch; target UNKNOWN with
  SESSION_FAILED and transport_unknown set (row 15, never the legacy FAILED branch). Missing
  row -> baseline FAILED; target APPLIED with disposition UNKNOWN, RESPONSE_MALFORMED and
  transport_unknown set. Row 10 (pre-read failed, postcondition unsatisfied) -> target PARTIAL,
  disposition UNKNOWN, sticky, dirty_state UNKNOWN; a journal built from a FAILED disposition
  without residual for that row is the rejected revision 2.1 reading. Inconsistent tuples
  (NOT_SUBMITTED with CORRELATED and SATISFIED and applied True; ACCEPTED with ENGINE_ERROR and
  SATISFIED; ACCEPTED, CORRELATED, SATISFIED with applied False) -> target UNKNOWN, frontier
  closed, sticky, the received SATISFIED preserved on the row and never consulted.
- B2b: round-trip test of item 5; baseline models drop every new fact.
- R-OBS-03: direct read found=False -> baseline FAILED with fresh True; target UNOBSERVABLE,
  SUBJECT_NOT_FOUND. Malformed payload -> baseline FAILED; target UNOBSERVABLE MALFORMED.
  Timeout -> baseline FAILED; target UNKNOWN NOT_OBSERVED.
- B3 semantics: the four authorized assertion changes of item 7 (b) to (e) are RED at the
  baseline by construction.
- R-EVD-01: VERIFIED fresh direct read -> classification "verified"; UNKNOWN NOT_OBSERVED ->
  "probe_failed" with "transport:not_observed"; legacy rows -> identical to the baseline
  adapter output.
- Transport: the real-socket cases of items 2 and 3; the differential table is green at the
  baseline by construction and is a regression guard only.
Positive controls that must stay green unchanged: the tests named in item 7 as valid
invariants; tests/test_file_bridge.py and tests/test_file_bridge_lifecycle.py;
tests/test_bridge_results.py; tests/test_bridge_security.py;
tests/test_product_mutation_replay_registry.py; tests/test_e95_execution_semantics.py; every
other tests/test_e95_* module; golden-script equality for the direct read-back, DNS
verification and http-scheme verification payloads.

Validation (repository root, checkout-local venv):
  .\.venv\Scripts\python.exe -m pip install -e ".[test,docs,quality]"
  git rev-parse --verify "<base>/main^{commit}"
  .\.venv\Scripts\python.exe scripts\quality_gate.py --base <base>/main
  .\.venv\Scripts\python.exe -m pytest -q
  .\.venv\Scripts\python.exe -m mkdocs build --site-dir _site
  git diff --check
After committing:
  .\.venv\Scripts\python.exe scripts\quality_gate.py --base <base>/main --delivery-commit HEAD

Delivery: one commit series on the feature branch, status READY_FOR_REVIEW. The first commit
adds docs/engineering/change-briefs/server-pt-services.md containing revision 2.2 of the plan
(self-contained; no reference to a Downloads file) and a record section (baseline SHA, branch,
risk L, the test inventory of item 7 with each classification, what changed, tests added,
measured Ruff counts before and after, the two-commit format/lint split). Do not claim runtime
functionality: S0 proves offline behavior against stubs only; every LIVE fact in the plan
stays a qualification gate.
