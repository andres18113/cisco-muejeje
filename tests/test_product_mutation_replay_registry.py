"""Completeness gate for the source-owned product mutation replay registry."""

from __future__ import annotations

import inspect
from typing import get_args

import pytest

from src.packet_tracer_mcp.domain.enterprise.models.configuration import ConfigurationAction
from src.packet_tracer_mcp.domain.enterprise.models.control_plane import ControlPlaneAction
from src.packet_tracer_mcp.domain.enterprise.models.security_plan import SecurityAction
from src.packet_tracer_mcp.domain.enterprise.models.service_plan import ServiceAction
from src.packet_tracer_mcp.domain.enterprise.models.voice_plan import VoiceAction
from src.packet_tracer_mcp.domain.enterprise.mutation_replay import (
    PRODUCT_MUTATION_REPLAY_REGISTRY,
    MutationSurface,
    ReplayClassification,
    UnclassifiedProductMutation,
    policies_for_entrypoint,
    policy_for_action_type,
    taxonomy_by_surface,
)
from src.packet_tracer_mcp.infrastructure.execution.packet_tracer_physical_runtime import (
    PacketTracerPhysicalTopologyRuntime,
)


ACTION_SURFACES = {
    MutationSurface.CONFIGURATION: ConfigurationAction,
    MutationSurface.CONTROL_PLANE: ControlPlaneAction,
    MutationSurface.SECURITY: SecurityAction,
    MutationSurface.VOICE: VoiceAction,
    MutationSurface.SERVICE: ServiceAction,
}


def _union_members(annotation) -> frozenset[type]:
    """Return the concrete members of an Annotated discriminated union."""

    union = get_args(annotation)[0]
    return frozenset(get_args(union))


@pytest.mark.parametrize("surface, annotation", ACTION_SURFACES.items())
def test_every_typed_action_family_is_registered_exactly_once(surface, annotation):
    expected = _union_members(annotation)
    registered = [
        item.action_type
        for item in PRODUCT_MUTATION_REPLAY_REGISTRY
        if item.surface is surface and item.action_type is not None
    ]

    assert len(registered) == len(set(registered))
    assert set(registered) == expected


def test_every_physical_product_mutation_entrypoint_is_registered():
    expected_methods = {
        name
        for name, member in inspect.getmembers(
            PacketTracerPhysicalTopologyRuntime,
            predicate=inspect.isfunction,
        )
        if name.startswith(("ensure_", "remove_"))
    }
    registered_methods = {
        item.entrypoint.rsplit(".", 1)[-1]
        for item in PRODUCT_MUTATION_REPLAY_REGISTRY
        if item.surface is MutationSurface.PHYSICAL
    }

    assert registered_methods == expected_methods


def test_every_registry_record_has_a_classification_and_containment_metadata():
    for item in PRODUCT_MUTATION_REPLAY_REGISTRY:
        assert isinstance(item.classification, ReplayClassification)
        assert item.containment
        assert item.evidence.strip()
        assert item.entrypoint.strip()


def test_registry_keys_are_unique_and_taxonomy_is_derived_from_the_registry():
    families = [item.family for item in PRODUCT_MUTATION_REPLAY_REGISTRY]
    assert len(families) == len(set(families))

    taxonomy = taxonomy_by_surface()
    flattened = {
        family: classification
        for surface in taxonomy.values()
        for family, classification in surface.items()
    }
    assert flattened == {
        item.family: item.classification.value
        for item in PRODUCT_MUTATION_REPLAY_REGISTRY
    }


def test_lookup_fails_closed_for_an_unregistered_action_or_entrypoint():
    class NewlyAddedMutation:
        pass

    with pytest.raises(UnclassifiedProductMutation):
        policy_for_action_type(NewlyAddedMutation)
    with pytest.raises(UnclassifiedProductMutation):
        policies_for_entrypoint("unregistered.runtime.mutate")


def test_registry_does_not_claim_the_whole_product_surface_is_replay_safe():
    classifications = {
        item.classification for item in PRODUCT_MUTATION_REPLAY_REGISTRY
    }

    assert ReplayClassification.TREAT_AS_REPLAY_UNSAFE in classifications
    assert ReplayClassification.UNKNOWN in classifications
