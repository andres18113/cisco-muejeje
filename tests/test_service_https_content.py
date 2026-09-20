"""S1b: one shared page store, one content action, through real composition.

The contract these tests pin comes from a measurement, not from a preference.
The Q1 ordinal-1 file run wrote the existing `index.html` through each of a
Server-PT's two web handles and read the change back through the other one:
distinct process objects, one page table. So HTTP and HTTPS on one host do not
have a page each, and a plan that tries to give them different content is not a
plan.

Everything here is offline. The composition, compiler, capability catalog,
product entry point and generated runtime script are the real ones; only the
channel, the manifest store and the record directory are replaced. Nothing
promotes a capability: application and verification support for the shared
contract stay UNKNOWN/UNMEASURED until a run at this SHA measures them, and a
Q1 run that exercises only the probe path is still not that run.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from service_entry_fixture import BACKEND_VERSION, deployment_manifest, intent_payload
from test_apply_enterprise_services import _harness
from test_service_mutation_script_harness import (
    _common,
    _needs_node,
    _run,
    _StubPacketTracer,
)

from packet_tracer_mcp.application.use_cases.compile_services import (
    compile_enterprise_services,
)
from packet_tracer_mcp.application.use_cases.compose_enterprise_reference import (
    compose_enterprise_reference,
)
from packet_tracer_mcp.domain.enterprise.models.capabilities import CapabilityStatus
from packet_tracer_mcp.domain.enterprise.models.configuration import (
    ConfigurationIssueCode,
    ConfigurationIssueSeverity,
)
from packet_tracer_mcp.domain.enterprise.models.enterprise_plan import EnterprisePlan
from packet_tracer_mcp.domain.enterprise.models.evidence import ReadinessStatus
from packet_tracer_mcp.domain.enterprise.models.execution import PostconditionFact
from packet_tracer_mcp.domain.enterprise.models.intent import EnterpriseIntent
from packet_tracer_mcp.domain.enterprise.models.service_entry import ServiceEntryRefusal
from packet_tracer_mcp.domain.enterprise.models.service_plan import (
    ClientOperationCapability,
    EnableHttpService,
    EnableHttpsService,
    ServiceActionType,
    ServicePhase,
    ServicePlan,
    ServiceType,
    ServiceVerificationKind,
    SetHttpContent,
)
from packet_tracer_mcp.domain.enterprise.services.service_capability_resolution import (
    profile_for,
    resolve_action_capability,
)
from packet_tracer_mcp.domain.enterprise.services.service_compiler import (
    SHARED_PAGE_STORE_RECORD,
    ServiceCompiler,
)
from packet_tracer_mcp.infrastructure.catalog.service_capabilities import (
    packet_tracer_service_capabilities,
)

HTTP_SERVICE = "service/hq/lab-web"
HTTPS_SERVICE = "service/hq/lab-web-tls"


def _compose(payload):
    """Compose one intent to E6 through the real reference composition."""
    intent = EnterpriseIntent.model_validate_json(json.dumps(payload))
    manifest, _inventory = deployment_manifest(payload)
    return compose_enterprise_reference(
        intent,
        packet_tracer_version=BACKEND_VERSION,
        deployment_manifest=manifest,
        services=True,
    )


def _compile(payload):
    """Compile one intent to E6 directly, so its typed issues are readable."""
    intent = EnterpriseIntent.model_validate_json(json.dumps(payload))
    manifest, _inventory = deployment_manifest(payload)
    composition = compose_enterprise_reference(
        intent,
        packet_tracer_version=BACKEND_VERSION,
        deployment_manifest=manifest,
    )
    return compile_enterprise_services(
        composition.enterprise, composition.topology, composition.configuration
    )


def _payload(*, http_content=None, https_content=None, https=True, drop_http=False):
    """Return the shared intent with the two web services tuned for one case."""
    payload = copy.deepcopy(intent_payload(include_https=https))
    services = payload["sites"][0]["services"]
    web = next(item for item in services if item["service_type"] == "http")
    if http_content is not None:
        web["http_content"] = http_content
    if drop_http:
        services.remove(web)
    if https and https_content is not None:
        tls = next(item for item in services if item["service_type"] == "https")
        tls["http_content"] = https_content
    return payload


def _content_actions(plan: ServicePlan) -> list[SetHttpContent]:
    return [item for item in plan.actions if isinstance(item, SetHttpContent)]


def _marker(plan: ServicePlan, kind: ServiceVerificationKind) -> str:
    rows = [item for item in plan.verification_expectations if item.kind is kind]
    assert rows, kind
    markers = {item.expected.get("marker") for item in rows}
    assert len(markers) == 1, markers
    return markers.pop()


def _candidate_catalog(
    *,
    http_fetch: CapabilityStatus = CapabilityStatus.SUPPORTED,
    https_fetch: CapabilityStatus = CapabilityStatus.UNKNOWN,
    http_content: CapabilityStatus = CapabilityStatus.SUPPORTED,
    https_content: CapabilityStatus = CapabilityStatus.SUPPORTED,
):
    records = dict(packet_tracer_service_capabilities(BACKEND_VERSION))
    for key, support in (
        ("PC-PT:http_fetch", http_fetch),
        ("PC-PT:https_fetch", https_fetch),
    ):
        current = records[key]
        assert isinstance(current, ClientOperationCapability)
        records[key] = current.model_copy(update={"support": support})
    for service_type, support in (
        (ServiceType.HTTP, http_content),
        (ServiceType.HTTPS, https_content),
    ):
        key = f"Server-PT:{service_type.value}"
        profile = records[key]
        action_support = dict(profile.action_application_support)
        action_support[ServiceActionType.SET_HTTP_CONTENT.value] = support
        records[key] = profile.model_copy(
            update={"action_application_support": action_support}
        )
    return records


def _stored(harness, result):
    return harness.record_store.load(harness.deployment_id, result.run_id)


# -- one page store, one action --------------------------------------------------


def test_one_host_page_compiles_one_action_shared_by_both_protocols():
    """F7: the payload is bound once and named by every service it serves."""
    composition = _compose(_payload())
    plan = composition.services

    (content,) = _content_actions(plan)
    assert content.content == "SAMPLE_WEB_PAGE"
    assert content.path == "index.html"
    # The HTTP service owns the write, so the shared page is published
    # through the process that host already runs for it.
    assert content.service_type is ServiceType.HTTP
    assert content.service_id == HTTP_SERVICE
    assert content.shared_service_ids == sorted([HTTP_SERVICE, HTTPS_SERVICE])
    assert content.content_source_record == SHARED_PAGE_STORE_RECORD
    enables = {
        item.id
        for item in plan.actions
        if isinstance(item, EnableHttpService | EnableHttpsService)
    }
    assert set(content.depends_on) == enables
    assert content.phase is ServicePhase.CONTENT


def test_both_protocols_verify_the_same_shared_marker():
    """F8: one page means one marker, whichever scheme asks for it."""
    plan = _compose(_payload()).services

    assert _marker(plan, ServiceVerificationKind.HTTP_FETCH) == "SAMPLE_WEB_PAGE"
    assert _marker(plan, ServiceVerificationKind.HTTPS_FETCH) == "SAMPLE_WEB_PAGE"
    direct = {
        item.service_id: item.expected.get("marker")
        for item in plan.verification_expectations
        if item.kind is ServiceVerificationKind.DIRECT_SERVICE_STATE
        and item.service_id in {HTTP_SERVICE, HTTPS_SERVICE}
    }
    assert direct == {
        HTTP_SERVICE: "SAMPLE_WEB_PAGE",
        HTTPS_SERVICE: "SAMPLE_WEB_PAGE",
    }
    schemes = {
        item.kind.value: item.expected.get("scheme")
        for item in plan.verification_expectations
        if item.kind
        in {ServiceVerificationKind.HTTP_FETCH, ServiceVerificationKind.HTTPS_FETCH}
    }
    assert schemes == {"http_fetch": "http", "https_fetch": "https"}


def test_the_payload_is_never_duplicated_to_represent_the_second_protocol():
    """F7: one action, one mutation, one copy of the content in the plan."""
    plan = _compose(_payload(http_content="X" * 512)).services

    (content,) = _content_actions(plan)
    assert content.content == "X" * 512
    # One mutation carries the page. Expectations quote the marker they check
    # for, which is what a verification row is; no second write exists.
    actions = json.dumps([item.model_dump(mode="json") for item in plan.actions])
    assert actions.count("X" * 512) == 1


def test_https_only_owns_the_page_and_never_enables_the_http_listener():
    """F7: publishing over HTTPS alone does not turn the HTTP listener on."""
    plan = _compose(_payload(drop_http=True, https_content="TLS_ONLY_PAGE")).services

    (content,) = _content_actions(plan)
    assert content.service_type is ServiceType.HTTPS
    assert content.service_id == HTTPS_SERVICE
    assert content.shared_service_ids == [HTTPS_SERVICE]
    assert content.content == "TLS_ONLY_PAGE"
    assert not [item for item in plan.actions if isinstance(item, EnableHttpService)]
    assert _marker(plan, ServiceVerificationKind.HTTPS_FETCH) == "TLS_ONLY_PAGE"


# -- disagreement is refused, not resolved ---------------------------------------


def test_incompatible_content_on_one_page_refuses_before_any_plan_exists():
    """F7: there is no plan that serves two contents from one page store."""
    result = _compile(
        _payload(http_content="PAGE_FROM_HTTP", https_content="PAGE_FROM_HTTPS")
    )

    assert result.plan is None
    conflicts = [
        item
        for item in result.issues
        if item.code is ConfigurationIssueCode.WEB_CONTENT_CONFLICT
    ]
    assert len(conflicts) == 1
    assert conflicts[0].severity is ConfigurationIssueSeverity.ERROR
    assert "PAGE_FROM_HTTP" in conflicts[0].message
    assert "PAGE_FROM_HTTPS" in conflicts[0].message
    assert HTTP_SERVICE in conflicts[0].subject
    assert HTTPS_SERVICE in conflicts[0].subject


def test_a_conflicting_page_reaches_no_runtime_at_all(tmp_path: Path):
    """F7: the refusal is before E5, so nothing is dispatched and nothing stored."""
    payload = _payload(http_content="PAGE_FROM_HTTP", https_content="PAGE_FROM_HTTPS")
    harness = _harness(tmp_path, payload)

    result = harness.run()

    assert result.refusal_code is ServiceEntryRefusal.COMPOSITION_FAILED
    assert harness.mutating_calls == []
    assert harness.configuration.verified == []
    assert harness.services.verified == []


def test_an_unstated_content_is_not_a_competing_intention():
    """One requirement asked for a page; the other asked for a protocol."""
    plan = _compose(_payload()).services
    (content,) = _content_actions(plan)
    assert content.content == "SAMPLE_WEB_PAGE"

    stated_by_https = _compose(
        _payload(http_content="", https_content="TLS_STATED_PAGE")
    ).services
    (shared,) = _content_actions(stated_by_https)
    # Only HTTPS stated a page, so the HTTP service's derived default is not
    # a second intention competing with it.
    assert shared.content == "TLS_STATED_PAGE"
    assert shared.service_type is ServiceType.HTTP
    assert shared.shared_service_ids == sorted([HTTP_SERVICE, HTTPS_SERVICE])


def test_two_stated_but_equal_contents_agree_and_compile_one_action():
    """F7: agreement is agreement, whichever service stated it."""
    plan = _compose(
        _payload(http_content="ONE_PAGE", https_content="ONE_PAGE")
    ).services

    (content,) = _content_actions(plan)
    assert content.content == "ONE_PAGE"
    assert content.shared_service_ids == sorted([HTTP_SERVICE, HTTPS_SERVICE])


# -- what did not change ---------------------------------------------------------


def test_the_existing_http_only_path_keeps_its_plan_identity():
    """F7: a host with one web service is the plan it always was."""
    composition = _compose(_payload(https=False))
    plan = composition.services

    (content,) = _content_actions(plan)
    assert content.shared_service_ids == [HTTP_SERVICE]
    assert content.service_type is ServiceType.HTTP
    assert not [item for item in plan.actions if isinstance(item, EnableHttpsService)]
    assert plan.semantic_hash == (
        "844b7665041c93a0c57cd67f7d97551941e68d1ad76da6b2123e0bc55cfb66e8"
    )


def test_a_shared_binding_is_hash_bound_and_its_source_record_is_not():
    """Ownership changes what the plan means; the citation does not."""
    shared = _compose(_payload()).services
    alone = _compose(_payload(https=False)).services
    assert shared.semantic_hash != alone.semantic_hash

    recited = shared.model_copy(deep=True)
    for action in recited.actions:
        if isinstance(action, SetHttpContent):
            action.content_source_record = "q1-some-other-record"
    assert ServiceCompiler._semantic_hash(recited) == shared.semantic_hash


def test_an_optional_unrelated_service_still_coexists_with_the_shared_page():
    """A second host service neither joins the page nor is disturbed by it."""
    payload = _payload()
    payload["sites"][0]["services"].append(
        {"name": "lab-ntp", "service_type": "ntp", "required": False}
    )
    plan = _compose(payload).services

    (content,) = _content_actions(plan)
    assert content.shared_service_ids == sorted([HTTP_SERVICE, HTTPS_SERVICE])
    assert any(item.service_type is ServiceType.NTP for item in plan.services)


# -- admitted execution projection ----------------------------------------------


def test_optional_unknown_https_keeps_one_http_writer_without_dangling_dependencies(
    tmp_path: Path,
):
    """F1-close: optional exclusion cannot remove or poison the HTTP writer."""
    payload = _payload()
    source = _compose(payload).services
    content = _content_actions(source)[0]
    harness = _harness(tmp_path, payload)

    result = harness.run()

    assert result.refusal_code is ServiceEntryRefusal.NONE
    dispatched = [
        identifier for batch in harness.services.applied for identifier in batch
    ]
    assert dispatched.count(content.id) == 1
    stored = _stored(harness, result)
    assert stored.service_semantic_hash == source.semantic_hash
    assert stored.service_result is not None
    assert stored.service_result.service_plan_id == source.id
    assert stored.service_result.service_semantic_hash == source.semantic_hash
    assert HTTP_SERVICE in stored.selected_service_ids
    assert HTTPS_SERVICE not in stored.selected_service_ids
    assert content.id in stored.selected_action_ids
    (binding,) = stored.shared_content_bindings
    assert binding.source_action_id == content.id
    assert binding.selected_action_id == content.id
    assert binding.source_service_ids == sorted([HTTP_SERVICE, HTTPS_SERVICE])
    assert binding.selected_service_ids == [HTTP_SERVICE]
    assert binding.writer_service_id == HTTP_SERVICE
    assert binding.writer_service_type is ServiceType.HTTP
    assert set(binding.dependency_ids) <= set(stored.selected_action_ids)


def test_excluded_optional_http_rebinds_the_single_writer_to_eligible_https(
    tmp_path: Path,
):
    """F1-close: the shared action survives under an exact HTTPS writer."""
    payload = _payload(http_content="ONE_PAGE", https_content="ONE_PAGE")
    services = payload["sites"][0]["services"]
    next(item for item in services if item["service_type"] == "http")["required"] = (
        False
    )
    next(item for item in services if item["service_type"] == "https")["required"] = (
        True
    )
    catalog = _candidate_catalog(
        http_fetch=CapabilityStatus.UNKNOWN,
        https_fetch=CapabilityStatus.SUPPORTED,
    )
    source = _compose(payload).services
    content = _content_actions(source)[0]
    harness = _harness(tmp_path, payload)

    result = harness.run(capability_catalog=lambda _version: catalog)

    assert result.refusal_code is ServiceEntryRefusal.NONE
    dispatched = [
        identifier for batch in harness.services.applied for identifier in batch
    ]
    assert dispatched.count(content.id) == 1
    stored = _stored(harness, result)
    assert stored.service_semantic_hash == source.semantic_hash
    assert stored.service_result is not None
    assert stored.service_result.service_plan_id == source.id
    assert HTTPS_SERVICE in stored.selected_service_ids
    assert HTTP_SERVICE not in stored.selected_service_ids
    (binding,) = stored.shared_content_bindings
    assert binding.selected_service_ids == [HTTPS_SERVICE]
    assert binding.writer_service_id == HTTPS_SERVICE
    assert binding.writer_service_type is ServiceType.HTTPS
    assert set(binding.dependency_ids) <= set(stored.selected_action_ids)
    assert not any(
        isinstance(item, EnableHttpService)
        for item in source.actions
        if item.id in stored.selected_action_ids
    )


def test_both_eligible_protocols_keep_one_writer_and_both_service_markers(
    tmp_path: Path,
):
    """F1-close: agreement produces one write and two admitted outcomes."""
    payload = _payload(http_content="ONE_PAGE", https_content="ONE_PAGE")
    next(
        item
        for item in payload["sites"][0]["services"]
        if item["service_type"] == "https"
    )["required"] = True
    catalog = _candidate_catalog(https_fetch=CapabilityStatus.SUPPORTED)
    content = _content_actions(_compose(payload).services)[0]
    harness = _harness(tmp_path, payload)

    result = harness.run(capability_catalog=lambda _version: catalog)

    assert result.refusal_code is ServiceEntryRefusal.NONE
    dispatched = [
        identifier for batch in harness.services.applied for identifier in batch
    ]
    assert dispatched.count(content.id) == 1
    assert {
        item.service_id
        for item in result.services
        if item.usability_status.value != "skipped"
    } >= {HTTP_SERVICE, HTTPS_SERVICE}
    stored = _stored(harness, result)
    (binding,) = stored.shared_content_bindings
    assert binding.source_service_ids == sorted([HTTP_SERVICE, HTTPS_SERVICE])
    assert binding.selected_service_ids == sorted([HTTP_SERVICE, HTTPS_SERVICE])
    assert binding.writer_service_id == HTTP_SERVICE


def test_an_unknown_exact_writer_operation_cannot_borrow_an_excluded_service_key(
    tmp_path: Path,
):
    """F1-close: provenance broadens ownership, never operation capability."""
    payload = _payload()
    catalog = _candidate_catalog(http_content=CapabilityStatus.UNKNOWN)
    harness = _harness(tmp_path, payload)

    result = harness.run(capability_catalog=lambda _version: catalog)

    assert result.refusal_code is ServiceEntryRefusal.SERVICE_INELIGIBLE
    assert "set_http_content" in result.blocked_reason
    assert harness.mutating_calls == []


def test_https_only_product_projection_never_selects_an_http_enable(
    tmp_path: Path,
):
    """F1-close: HTTPS-only writes through HTTPS without enabling HTTP."""
    payload = _payload(drop_http=True, https_content="TLS_ONLY_PAGE")
    next(item for item in payload["sites"][0]["services"])["required"] = True
    catalog = _candidate_catalog(https_fetch=CapabilityStatus.SUPPORTED)
    source = _compose(payload).services
    content = _content_actions(source)[0]
    harness = _harness(tmp_path, payload)

    result = harness.run(capability_catalog=lambda _version: catalog)

    assert result.refusal_code is ServiceEntryRefusal.NONE
    stored = _stored(harness, result)
    assert content.id in stored.selected_action_ids
    assert not any(
        isinstance(item, EnableHttpService)
        for item in source.actions
        if item.id in stored.selected_action_ids
    )
    (binding,) = stored.shared_content_bindings
    assert binding.writer_service_type is ServiceType.HTTPS
    assert binding.selected_service_ids == [HTTPS_SERVICE]


def test_the_shared_binding_survives_a_record_round_trip():
    """F8: the plan reloads with its ownership and provenance intact."""
    plan = _compose(_payload()).services

    reloaded = ServicePlan.model_validate_json(plan.model_dump_json())

    (content,) = _content_actions(reloaded)
    assert content.shared_service_ids == sorted([HTTP_SERVICE, HTTPS_SERVICE])
    assert content.content_source_record == SHARED_PAGE_STORE_RECORD
    assert reloaded.semantic_hash == plan.semantic_hash


# -- nothing here promotes anything ----------------------------------------------


def test_the_shared_contract_changes_no_capability_record():
    """F8: provenance metadata is not measured support, and adds no record.

    The shared action resolves exactly what the unshared one always did --
    the operation on the model that hosts it -- and no HTTPS-specific content
    record was invented to make the new branch look supported.
    """
    catalog = packet_tracer_service_capabilities(BACKEND_VERSION)
    shared = _content_actions(_compose(_payload()).services)[0]
    alone = _content_actions(_compose(_payload(https=False)).services)[0]

    resolved = resolve_action_capability(catalog, shared)
    assert resolved.key == "Server-PT:set_http_content"
    assert resolved.support is resolve_action_capability(catalog, alone).support
    assert "Server-PT:set_https_content" not in catalog
    assert "Server-PT:shared_content" not in catalog

    # HTTPS behavioral verification is exactly what S1b did not measure, so
    # implementing the content branch must not have made it READY.
    https = profile_for(catalog, model="Server-PT", service_type=ServiceType.HTTPS)
    assert https.behavioral_verification_support is CapabilityStatus.UNKNOWN
    readiness = https.capability_readiness["behavioral_verification"]
    assert readiness.apply is not ReadinessStatus.READY
    assert readiness.verify is ReadinessStatus.UNKNOWN


# -- the generated writer --------------------------------------------------------


@pytest.mark.parametrize(
    ("service_type", "process"),
    [(ServiceType.HTTP, "HttpServer"), (ServiceType.HTTPS, "HttpsServer")],
)
def test_the_shared_page_is_written_once_through_the_owning_process(
    service_type, process
):
    """F8: the owning service names the process; the page is written once."""
    _needs_node()
    stub = _StubPacketTracer()
    action = SetHttpContent(
        id="shared-content",
        phase=ServicePhase.CONTENT,
        content="SHARED_PAGE",
        content_sha256="hash",
        shared_service_ids=["service/hq/a", "service/hq/b"],
        content_source_record=SHARED_PAGE_STORE_RECORD,
        **_common("service/hq/a", service_type),
    )

    (mutation,) = _run(stub, [action])

    assert mutation.applied is True
    assert stub.state["process"]["pages"]["index.html"] == "SHARED_PAGE"
    assert stub.log.count("setPageContents:index.html") == 1
    assert f"getProcess:{process}" in stub.log
    assert len([item for item in stub.log if item.startswith("getProcess:")]) == 1


def test_a_page_the_engine_did_not_store_is_never_reported_as_written():
    """The no-marker negative: the read-back is the oracle, not the setter."""
    _needs_node()
    stub = _StubPacketTracer(stores_instead="SOMETHING_ELSE")
    action = SetHttpContent(
        id="shared-content",
        phase=ServicePhase.CONTENT,
        content="SHARED_PAGE",
        content_sha256="hash",
        shared_service_ids=["service/hq/a"],
        content_source_record=SHARED_PAGE_STORE_RECORD,
        **_common("service/hq/a", ServiceType.HTTPS),
    )

    (mutation,) = _run(stub, [action])

    # The setter ran and the channel accepted it, which is all `applied`
    # claims. The read-back is what decides whether the page holds the page.
    assert mutation.postcondition is PostconditionFact.UNSATISFIED
    assert stub.state["process"]["pages"]["index.html"] == "SOMETHING_ELSE"


def test_an_unknown_backend_build_has_no_shared_content_capability():
    """F8: the contract is qualified per build, like everything else."""
    unknown = packet_tracer_service_capabilities("0.0.0.0")
    plan = _compose(_payload()).services
    (content,) = _content_actions(plan)

    assert resolve_action_capability(unknown, content).support is (
        CapabilityStatus.UNKNOWN
    )


def test_the_compiler_reports_a_missing_enterprise_plan_without_a_page():
    """A plan with no web service compiles no content action at all."""
    payload = _payload(https=False)
    payload["sites"][0]["services"] = [
        item
        for item in payload["sites"][0]["services"]
        if item["service_type"] != "http"
    ]
    composition = _compose(payload)

    assert isinstance(composition.enterprise, EnterprisePlan)
    assert _content_actions(composition.services) == []
