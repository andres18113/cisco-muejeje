"""Input/output contracts of the seams the qualification refactor named.

SERVER-SERVICE-QUALIFICATION-ARCHITECTURE-01 gave shared path admission an
application owner, ServicePlan identity a domain function, and the relay
acquisition poll a domain predicate. Each test pins the seam against a
recorded value or the rule's own statement, never a copy of its algorithm.
"""

from __future__ import annotations

import pytest

from packet_tracer_mcp.adapters.cli.service_qualification import (
    sp2_remote_relay_contract,
)
from packet_tracer_mcp.application.server_service_qualification.workflows import (
    sp2_remote_relay,
)
from packet_tracer_mcp.application.use_cases import (
    apply_enterprise_services,
    service_path_admission,
)
from packet_tracer_mcp.domain.enterprise.services.dhcp_lease_evidence import (
    ClientReading,
)
from packet_tracer_mcp.domain.enterprise.services.service_compiler import (
    ServiceCompiler,
    service_plan_semantic_hash,
)
from packet_tracer_mcp.domain.enterprise.services.sp2_pool_diagnostic import (
    sp2_remote_acquired,
)

BUILD = "9.0.1.0858"
RUN_ID = "sp2-e3-seam-contract"


def test_plan_identity_is_the_reviewed_remote_relay_hash():
    """The named identity reproduces the hash the reviewed SP-2 plan pinned."""
    contract = sp2_remote_relay_contract(BUILD, RUN_ID)

    assert (
        service_plan_semantic_hash(contract.service_plan)
        == contract.service_plan.semantic_hash
        == sp2_remote_relay.SP2_REMOTE_SERVICES_SHA256
    )


def test_the_compiler_keeps_its_identity_method_for_existing_consumers():
    """`ServiceCompiler._semantic_hash` answers with the named identity."""
    contract = sp2_remote_relay_contract(BUILD, RUN_ID)
    changed = contract.service_plan.model_copy(update={"id": "changed"}, deep=True)

    assert ServiceCompiler._semantic_hash(changed) == service_plan_semantic_hash(
        changed
    )
    assert service_plan_semantic_hash(changed) != contract.service_plan.semantic_hash


def test_both_path_admission_callers_consume_one_owner():
    """The product entry and the relay qualification share the same rule."""
    assert apply_enterprise_services.path_admission is (
        service_path_admission.path_admission
    )
    assert sp2_remote_relay.path_admission is service_path_admission.path_admission
    assert sp2_remote_relay.dhcp_prelease_paths is (
        service_path_admission.dhcp_prelease_paths
    )
    assert not hasattr(apply_enterprise_services, "_path_admission")


def test_path_admission_admits_the_one_relayed_remote_path():
    """The reviewed remote relay plan has exactly one admitted routed path."""
    contract = sp2_remote_relay_contract(BUILD, RUN_ID)

    unsupported, paths = service_path_admission.path_admission(
        contract.configuration_plan,
        contract.service_plan,
        contract.service_plan.services,
        links=contract.topology.links,
    )
    prelease = service_path_admission.dhcp_prelease_paths(
        paths, contract.service_plan.services
    )

    assert unsupported == []
    assert len(paths) == 1
    [path] = paths.values()
    [target] = prelease.values()
    assert path.client_ipv4 == ""
    assert target.client_ipv4 != ""


@pytest.mark.parametrize(
    ("reading", "acquired"),
    [
        (ClientReading("PC", False, ipv4="10.72.1.10"), False),
        (ClientReading("PC", True, ipv4=""), False),
        (ClientReading("PC", True, ipv4="0.0.0.0"), False),
        (ClientReading("PC", True, ipv4="169.254.17.3"), False),
        (ClientReading("PC", True, ipv4="10.72.1.10"), True),
    ],
)
def test_a_relayed_acquisition_needs_an_observed_non_fallback_address(
    reading, acquired
):
    """Unread, empty, all-zero and link-local readings are no acquisition."""
    assert sp2_remote_acquired(reading) is acquired
