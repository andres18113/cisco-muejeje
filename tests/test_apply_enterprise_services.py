"""R-ENTRY-*: the product entry point, driven through its real components.

These run the actual composition, both real applicators, the real foundation
derivation and the real record store in a temporary directory. Only the two
runtimes and the endpoint observer are injected, because those are the external
boundaries; everything between them is the production path.

The single most important assertion in the module is the negative one, repeated
for every refusal class: **no mutating runtime call happened**. A product that
refuses after touching the operator's devices has not refused.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from service_entry_fixture import (
    BACKEND_VERSION,
    DEPLOYMENT_ID,
    FINGERPRINT,
    SERVER_ADDRESS,
    EndpointObserver,
    IsolationPreflight,
    ManifestStore,
    RecordingConfigurationRuntime,
    RecordingServiceRuntime,
    deployment_manifest,
    intent_payload,
)

from packet_tracer_mcp.application.ports.service_run_record import (
    RunRecordPersistenceError,
)
from packet_tracer_mcp.application.use_cases.apply_enterprise_services import (
    ServiceStageRuntimes,
    TransportSelection,
    apply_enterprise_services,
)
from packet_tracer_mcp.domain.enterprise.models.configuration import (
    SetEndpointStaticAddress,
)
from packet_tracer_mcp.domain.enterprise.models.configuration_runtime import (
    ActionExecutionStatus,
    ConfigurationFailureCode,
)
from packet_tracer_mcp.domain.enterprise.models.execution import DirtyState
from packet_tracer_mcp.domain.enterprise.models.service_entry import (
    ServiceEntryRefusal,
    ServiceRunStatus,
    ServiceStage,
)
from packet_tracer_mcp.domain.enterprise.models.service_plan import (
    ServiceVerificationKind,
)
from packet_tracer_mcp.infrastructure.execution.import_isolation_preflight import (
    ImportIsolationState,
)
from packet_tracer_mcp.infrastructure.persistence.service_run_record_store import (
    ServiceRunRecordStore,
)


@dataclass
class _Harness:
    """Everything one invocation needs, with the recorded calls kept."""

    configuration: RecordingConfigurationRuntime
    services: RecordingServiceRuntime
    manifest_store: ManifestStore
    record_store: object
    preflight: IsolationPreflight
    observer: EndpointObserver
    transport: TransportSelection
    fingerprint: object = field(default_factory=lambda: FINGERPRINT)
    intent: str = ""
    deployment_id: str = DEPLOYMENT_ID
    version: str = BACKEND_VERSION
    calls: list[str] = field(default_factory=list)

    @property
    def mutating_calls(self) -> list[list[str]]:
        """Every batch either runtime was asked to dispatch."""
        return [*self.configuration.applied, *self.services.applied]

    def run(self, **overrides: object):
        """Invoke the product entry point through its real components."""
        return apply_enterprise_services(
            overrides.pop("intent_json", self.intent),
            deployment_id=overrides.pop("deployment_id", self.deployment_id),
            packet_tracer_version=overrides.pop("packet_tracer_version", self.version),
            runtimes=ServiceStageRuntimes(
                configuration=self.configuration, services=self.services
            ),
            manifest_store=self.manifest_store,
            record_store=self.record_store,
            import_preflight=self.preflight,
            environment_fingerprint=overrides.pop(
                "environment_fingerprint", self.fingerprint
            ),
            transport_selection=overrides.pop("transport_selection", self.transport),
            endpoint_observer=overrides.pop("endpoint_observer", self.observer),
            **overrides,
        )


def _harness(tmp_path: Path, payload: dict | None = None, **kwargs) -> _Harness:
    manifest, inventory = deployment_manifest(payload)
    return _Harness(
        configuration=RecordingConfigurationRuntime(targets=inventory),
        services=RecordingServiceRuntime(targets=inventory),
        manifest_store=ManifestStore(manifest=manifest),
        record_store=ServiceRunRecordStore(tmp_path),
        preflight=IsolationPreflight(),
        observer=EndpointObserver(address=""),
        transport=TransportSelection(channel="http"),
        intent=json.dumps(payload or intent_payload()),
        **kwargs,
    )


# -- admission: every refusal happens before any effect --------------------


def test_invalid_json_refuses_without_touching_a_runtime(tmp_path: Path):
    """R-ENTRY-01: not merely no mutation - no bridge contact at all."""
    harness = _harness(tmp_path)

    result = harness.run(intent_json="{not json")

    assert result.refusal_code is ServiceEntryRefusal.INTENT_INVALID
    assert result.status is ServiceRunStatus.REFUSED
    assert harness.mutating_calls == []
    assert harness.configuration.verified == []
    assert harness.services.verified == []
    assert harness.manifest_store.reads == []
    assert harness.preflight.calls == 0
    assert result.record_path == ""
    assert not list(tmp_path.rglob("*.json"))


def test_a_missing_manifest_refuses_with_no_record(tmp_path: Path):
    """A1 and A2 bind no identity, so there is nothing to file a record under."""
    harness = _harness(tmp_path)
    harness.manifest_store.manifest = None

    result = harness.run()

    assert result.refusal_code is ServiceEntryRefusal.DEPLOYMENT_MANIFEST_MISSING
    assert harness.mutating_calls == []
    assert not list(tmp_path.rglob("*.json"))


def test_an_unreadable_manifest_store_is_a_typed_refusal(tmp_path: Path):
    """A store that raises is a refusal a caller can branch on."""
    harness = _harness(tmp_path)
    harness.manifest_store.error = RunRecordPersistenceError("corrupt")

    result = harness.run()

    assert result.refusal_code is ServiceEntryRefusal.DEPLOYMENT_MANIFEST_UNREADABLE
    assert harness.mutating_calls == []


def test_a_version_mismatch_refuses_and_leaves_an_unbound_record(tmp_path: Path):
    """R-CAP-02: a caller string agreeing with itself is not an observation."""
    harness = _harness(tmp_path)

    result = harness.run(packet_tracer_version="9.9.9.9999")

    assert result.refusal_code is ServiceEntryRefusal.VERSION_MISMATCH
    assert harness.mutating_calls == []
    assert list((tmp_path / "_admission").glob("*.json"))


def test_a_test_process_is_refused_before_any_effect(tmp_path: Path):
    """A pytest process never establishes live isolation, by design."""
    harness = _harness(tmp_path)
    harness.preflight.state = ImportIsolationState.TEST_PROCESS

    result = harness.run()

    assert result.refusal_code is ServiceEntryRefusal.IMPORT_ISOLATION_REFUSED
    assert "TEST_PROCESS" in result.blocked_reason
    assert harness.mutating_calls == []


def test_a_foreign_tree_is_refused_before_any_effect(tmp_path: Path):
    """A package loaded from outside the governed tree is not this product."""
    harness = _harness(tmp_path)
    harness.preflight.state = ImportIsolationState.FOREIGN_TREE

    result = harness.run()

    assert result.refusal_code is ServiceEntryRefusal.IMPORT_ISOLATION_REFUSED
    assert harness.mutating_calls == []


def test_an_unavailable_transport_refuses_before_any_effect(tmp_path: Path):
    """A5 fixes one channel; no channel means no run."""
    harness = _harness(tmp_path)

    result = harness.run(
        transport_selection=TransportSelection(
            channel="", ready=False, detail="no channel"
        )
    )

    assert result.refusal_code is ServiceEntryRefusal.TRANSPORT_UNAVAILABLE
    assert harness.mutating_calls == []


def test_an_unwritable_record_store_refuses_the_run(tmp_path: Path):
    """R-ENTRY-06: without the write-ahead record, the run does not start."""

    class RefusingStore(ServiceRunRecordStore):
        def begin(self, record):
            raise RunRecordPersistenceError("read-only volume")

    harness = _harness(tmp_path)
    harness.record_store = RefusingStore(tmp_path)

    result = harness.run()

    assert result.refusal_code is ServiceEntryRefusal.RECORD_STORE_UNWRITABLE
    assert harness.mutating_calls == []


def test_a_changed_environment_fingerprint_refuses_before_any_effect(
    tmp_path: Path,
):
    """R-ENTRY-03: the CURRENT environment is validated, not a stored string."""
    from packet_tracer_mcp.domain.enterprise.models.deployment import (
        EnvironmentFingerprint,
    )

    harness = _harness(tmp_path)

    result = harness.run(
        environment_fingerprint=EnvironmentFingerprint(
            backend="packet_tracer",
            backend_version=BACKEND_VERSION,
            platform="a-different-host",
        )
    )

    assert result.refusal_code is ServiceEntryRefusal.ENVIRONMENT_FINGERPRINT_MISMATCH
    assert harness.mutating_calls == []


def test_a_dns_service_without_an_address_refuses_before_any_effect(
    tmp_path: Path,
):
    """R-NET-02: the client resolver is derived or the run refuses."""
    payload = intent_payload(dns_address="")
    harness = _harness(tmp_path, payload)

    result = harness.run()

    assert result.refusal_code is ServiceEntryRefusal.DNS_SERVER_ADDRESS_REQUIRED
    assert harness.mutating_calls == []


def test_two_dns_authorities_refuse_before_any_effect(tmp_path: Path):
    """Choosing one arbitrarily would configure every client wrongly."""
    payload = intent_payload(second_dns_address="198.18.160.9")
    harness = _harness(tmp_path, payload)

    result = harness.run()

    assert result.refusal_code is ServiceEntryRefusal.DNS_AUTHORITY_CONFLICT
    assert harness.mutating_calls == []


def test_a_conflicting_endpoint_address_refuses_with_zero_effects(tmp_path: Path):
    """R-ENTRY-09: somebody else's addressing is never overwritten silently."""
    harness = _harness(tmp_path)
    harness.observer = EndpointObserver(address="10.10.10.10")

    result = harness.run()

    assert result.refusal_code is ServiceEntryRefusal.EXISTING_CONFIGURATION_CONFLICT
    assert "10.10.10.10" in result.blocked_reason
    assert harness.mutating_calls == []


def test_an_unreadable_endpoint_is_unknown_and_not_empty(tmp_path: Path):
    """An endpoint nobody could read is exactly the one not to write over."""
    harness = _harness(tmp_path)
    harness.observer = EndpointObserver(readable=False)

    result = harness.run()

    assert result.refusal_code is ServiceEntryRefusal.DRIFT_UNREADABLE
    assert harness.mutating_calls == []


def test_admission_records_the_reads_it_performed(tmp_path: Path):
    """R-ENTRY-02: the directed reads are auditable, in order."""
    harness = _harness(tmp_path)

    result = harness.run()

    steps = [item.step for item in result.admission.reads]
    assert steps[0] == "A2"
    assert "A4" in steps
    assert "A8" in steps
    assert "A10" in steps
    assert steps == sorted(steps, key=lambda item: int(item[1:]))


# -- eligibility -----------------------------------------------------------


def test_a_required_ineligible_service_refuses_the_run_before_e5(tmp_path: Path):
    """R-ENTRY-11: required means the run does not proceed without it."""
    payload = intent_payload(include_https=True, https_required=True)
    harness = _harness(tmp_path, payload)

    result = harness.run()

    assert result.refusal_code is ServiceEntryRefusal.SERVICE_INELIGIBLE
    assert "https" in result.blocked_reason
    assert harness.mutating_calls == []


def test_an_optional_ineligible_service_is_excluded_and_reported(tmp_path: Path):
    """The same plan, optional: excluded before E5, and still reported."""
    payload = intent_payload(include_https=True, https_required=False)
    harness = _harness(tmp_path, payload)

    result = harness.run()

    assert result.refusal_code is ServiceEntryRefusal.NONE
    skipped = [
        item for item in result.services if item.service_id.endswith("lab-web-tls")
    ]
    assert len(skipped) == 1
    assert skipped[0].usability_status is ActionExecutionStatus.SKIPPED
    assert any("service_ineligible" in item for item in skipped[0].limitations)
    assert any("https_fetch" in item for item in skipped[0].limitations)
    dispatched = {item for batch in harness.services.applied for item in batch}
    assert not any("https" in item for item in dispatched)


# -- the two-client acceptance --------------------------------------------


def test_two_clients_get_separate_verified_results(tmp_path: Path):
    """R-COV-01 and R-HTTP-02: one row per client per service, not a summary."""
    harness = _harness(tmp_path)

    result = harness.run()

    assert result.stage is ServiceStage.COMPLETED
    assert result.status is ServiceRunStatus.VERIFIED
    assert len(result.clients) == 2
    for client in result.clients:
        assert set(client.results) == {
            "service/hq/lab-dns",
            "service/hq/lab-web",
        }
        for outcome in client.results.values():
            assert outcome.status is ActionExecutionStatus.VERIFIED
            assert outcome.checks
    identifiers = {item.client_device_id for item in result.clients}
    assert len(identifiers) == 2


def test_one_client_contradiction_does_not_promote_the_other(tmp_path: Path):
    """A per-client result means the clients are decided separately."""
    harness = _harness(tmp_path)
    manifest, _inventory = deployment_manifest()
    failing = sorted(
        item.semantic_device_id
        for item in manifest.bindings
        if "user_pc" in item.semantic_device_id
    )[0]
    harness.services.failing_clients = frozenset({failing})

    result = harness.run()

    by_client = {item.client_device_id: item for item in result.clients}
    assert by_client[failing].results["service/hq/lab-dns"].status is (
        ActionExecutionStatus.FAILED
    )
    other = next(key for key in by_client if key != failing)
    assert by_client[other].results["service/hq/lab-web"].status is (
        ActionExecutionStatus.VERIFIED
    )
    assert result.status is ServiceRunStatus.FAILED


def test_the_advisory_client_dns_reader_never_gates_a_service(tmp_path: Path):
    """R-CAP-06: reported in full, UNKNOWN, and counted nowhere."""
    harness = _harness(tmp_path)

    result = harness.run()

    advisory = [
        row
        for client in result.clients
        for outcome in client.results.values()
        for row in outcome.checks
        if row.kind is ServiceVerificationKind.CLIENT_DNS_SERVER
    ]
    assert advisory
    for row in advisory:
        assert row.required is False
        assert row.status is not ActionExecutionStatus.VERIFIED
    assert result.status is ServiceRunStatus.VERIFIED


# -- the bounded E5 scope, through the real applicator ---------------------


def test_exactly_the_closure_reaches_the_e5_runtime(tmp_path: Path):
    """R-ENTRY-09: nothing outside the closure is rendered or dispatched."""
    harness = _harness(tmp_path)

    result = harness.run()

    dispatched = {item for batch in harness.configuration.applied for item in batch}
    assert dispatched == set(result.e5_effect_scope.mutated)
    assert dispatched.isdisjoint(result.e5_effect_scope.excluded)
    assert result.e5_effect_scope.excluded
    rendered = {item.id for item in harness.configuration.rendered}
    assert rendered.isdisjoint(result.e5_effect_scope.excluded)
    rows = {item.action_id: item for item in result.configuration_result.action_results}
    for identifier in result.e5_effect_scope.excluded:
        assert rows[identifier].status is ActionExecutionStatus.SKIPPED
        assert rows[identifier].failure_code is ConfigurationFailureCode.OUT_OF_SCOPE


def test_the_derived_dns_address_reaches_the_runtime_call_arguments(
    tmp_path: Path,
):
    """R-NET-02, all the way through: intent to policy to action to call.

    The initially unset policy is the point. Nothing in the composition knows
    the client resolver until the requested DNS service supplies it, so an
    endpoint action that reaches the runtime with dns_server unset is a client
    that will never resolve anything the run then claims to have verified.
    """
    harness = _harness(tmp_path)

    harness.run()

    endpoints = [
        item
        for item in harness.configuration.rendered
        if isinstance(item, SetEndpointStaticAddress)
    ]
    assert endpoints
    assert all(item.dns_server == SERVER_ADDRESS for item in endpoints)


def test_a_routed_client_is_refused_rather_than_routed_for(tmp_path: Path):
    """R-NET-01: same-subnet is what this slice supports, and it says so."""
    payload = intent_payload()
    payload["sites"][0]["endpoints"][1]["segment_role"] = "servers"
    harness = _harness(tmp_path, payload)

    result = harness.run()

    assert result.refusal_code in {
        ServiceEntryRefusal.SERVICE_PATH_UNSUPPORTED,
        ServiceEntryRefusal.COMPOSITION_FAILED,
    }
    assert harness.mutating_calls == []


# -- containment -----------------------------------------------------------


def test_an_e5_runtime_that_raises_after_dispatch_stops_before_e6(
    tmp_path: Path,
):
    """R-RET-02 and D-9 containment.

    The channel dropped after the request was sent, so whether the mutation
    happened is unknown. That is not a clean run and not a failed one, and it
    is certainly not a state to dispatch E6 effects on top of.
    """
    harness = _harness(tmp_path)
    harness.configuration.raise_after_dispatch = True

    result = harness.run()

    assert result.e5_effect_uncertain is True
    assert result.status is ServiceRunStatus.UNKNOWN
    assert result.dirty_state is DirtyState.UNKNOWN
    assert harness.services.applied == []
    assert any("e5_effect_uncertain" in item for item in result.limitations)


def test_a_store_failure_after_the_first_effect_dispatches_nothing_more(
    tmp_path: Path,
):
    """R-ENTRY-06, asserted on the calls rather than on the response text.

    The response saying `persist_error` proves the run noticed. What has to be
    proven is that nothing else was dispatched afterwards, while there was
    still work available to dispatch.
    """

    class FailAfterFirstAdvance(ServiceRunRecordStore):
        def __init__(self, base):
            super().__init__(base)
            self.advances = 0

        def advance(self, record):
            self.advances += 1
            if self.advances > 1:
                raise RunRecordPersistenceError("volume went read-only")
            return super().advance(record)

    harness = _harness(tmp_path)
    harness.record_store = FailAfterFirstAdvance(tmp_path)

    result = harness.run()

    assert harness.configuration.applied, "E5 must have run before the failure"
    assert harness.services.applied == [], "no E6 effect may follow the failure"
    assert result.persist_error
    assert result.refusal_code is ServiceEntryRefusal.EFFECT_HALTED
    assert result.status is ServiceRunStatus.UNKNOWN
    assert result.persisted_stage is not ServiceStage.COMPLETED


# -- evidence --------------------------------------------------------------


def test_the_response_and_the_record_agree_and_survive_json(tmp_path: Path):
    """R-QUAL-04: the record is the durable form of the same facts."""
    harness = _harness(tmp_path)

    result = harness.run()

    stored = ServiceRunRecordStore(tmp_path).load(DEPLOYMENT_ID, result.run_id)
    assert stored.status is result.status
    assert stored.e5_effect_scope.mutated == result.e5_effect_scope.mutated
    assert [item.client_device_id for item in stored.clients] == [
        item.client_device_id for item in result.clients
    ]
    assert stored.configuration_result is not None
    assert stored.service_result is not None
    assert stored.capability_snapshot.catalog_hash
    round_trip = json.loads(result.model_dump_json())
    assert round_trip["run_id"] == result.run_id


def test_documentary_provenance_is_disclosed_in_every_response(tmp_path: Path):
    """RD-8: usable, and said out loud rather than quietly assumed."""
    harness = _harness(tmp_path)

    result = harness.run()

    assert "provenance:documentary_baseline" in result.limitations
    assert set(result.capability_snapshot.provenance_by_key.values()) == {
        "documentary_baseline"
    }


def test_an_unresolved_client_release_stays_visible(tmp_path: Path):
    """No topology cleanup never meant skipping the owned-client release."""
    harness = _harness(tmp_path)
    harness.services.release_outcome = "release_failed:client_still_registered"

    result = harness.run()

    assert result.releases
    assert any(item.outcome == "release_failed" for item in result.releases)
    stored = ServiceRunRecordStore(tmp_path).load(DEPLOYMENT_ID, result.run_id)
    assert stored.releases


def test_no_secret_or_script_reaches_the_public_response(tmp_path: Path):
    """R-ENTRY-05: bounded typed diagnostics, in every encoded form."""
    sentinel = "S3CR3T-SENTINEL-VALUE"
    harness = _harness(tmp_path)
    harness.manifest_store.error = RuntimeError(f"token={sentinel}")

    result = harness.run()

    rendered = result.model_dump_json()
    assert sentinel not in rendered
    assert json.dumps(sentinel)[1:-1] not in rendered
    assert sentinel.replace("-", "%2D") not in rendered


def test_the_record_is_written_before_the_first_effect(tmp_path: Path):
    """The write-ahead ordering, observed rather than assumed."""
    order: list[str] = []

    class OrderedStore(ServiceRunRecordStore):
        def begin(self, record):
            order.append("record.begin")
            return super().begin(record)

    class OrderedRuntime(RecordingConfigurationRuntime):
        def apply_actions(self, actions):
            order.append("e5.apply")
            return super().apply_actions(actions)

    _topology, inventory = deployment_manifest()
    harness = _harness(tmp_path)
    harness.record_store = OrderedStore(tmp_path)
    harness.configuration = OrderedRuntime(targets=inventory)

    harness.run()

    assert order[0] == "record.begin"
    assert "e5.apply" in order


@pytest.mark.parametrize(
    "refusal",
    [
        ServiceEntryRefusal.INTENT_INVALID,
        ServiceEntryRefusal.DEPLOYMENT_MANIFEST_MISSING,
        ServiceEntryRefusal.VERSION_MISMATCH,
        ServiceEntryRefusal.IMPORT_ISOLATION_REFUSED,
        ServiceEntryRefusal.TRANSPORT_UNAVAILABLE,
        ServiceEntryRefusal.EXISTING_CONFIGURATION_CONFLICT,
    ],
)
def test_every_refusal_code_is_typed_and_distinct(refusal):
    """A refusal a caller cannot branch on is a message, not a contract."""
    assert refusal is not ServiceEntryRefusal.NONE
    assert refusal.value == refusal.value.lower()


def test_the_product_path_contains_no_destructive_vendor_call():
    """R-ENTRY-07: the product removes nothing of the operator.

    A corpus check rather than a behavioural one, because the guarantee is
    about what CANNOT be reached: a destructive call that is never written
    cannot be dispatched by any branch. The owned-client release lives in the
    S0 runtime and is unaffected; what may not appear here is the removal of a
    device, a pool, a user or a message.
    """
    from packet_tracer_mcp.adapters.mcp import service_tools
    from packet_tracer_mcp.application.use_cases import (
        apply_enterprise_services as entry,
    )

    corpus = "\n".join(
        Path(module.__file__).read_text(encoding="utf-8")
        for module in (service_tools, entry)
    )
    for forbidden in (
        "removeDevice",
        "removePool",
        "deleteUser",
        "deleteMailAt",
        "removeLink",
    ):
        assert forbidden not in corpus, forbidden
