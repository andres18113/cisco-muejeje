"""TD-HARDWARE-001: la evidencia reconcilia en HARDWARE ELEGIBLE, no sólo en candidatos.

`test_enterprise_hardware_composition.py` fija que la evidencia de versión exacta
llega a `DeviceCapabilities`. Eso no era el criterio. El criterio literal habla
de *hardware físico elegible*:

> La evidencia de capacidad usada por el resolver enterprise debe reconciliar
> deterministamente en hardware físico elegible sin casos especiales por nombre
> de modelo, mientras UNKNOWN siga siendo UNKNOWN.

Lo que faltaba medir era la DECISIÓN: que una evidencia medida cambie a un
modelo de "necesita verificación" a "seleccionado", y que sin esa evidencia no
se seleccione nada. Eso es lo que se fija acá.

La cadena completa, y ningún eslabón mira un nombre de modelo:

```text
multilayer_intervlan SUPPORTED + verified   (probe controlado, versión exacta)
  -> _with_semantic_implications             (implicación de una sola dirección)
  -> layer3 SUPPORTED
  -> DeviceSelector._problems                (ramifica en CapabilityStatus)
  -> el modelo deja `needs_verification` y pasa a ser elegible
```

CORROBORACIÓN EN VIVO. Las mismas transiciones se midieron contra evidencia real
producida por la vía de cualificación gobernada sobre PT `9.0.1.0858`
(`3560-24PS`, probe multicapa, forwarding entre VLANs demostrado). Su proyección
revisada ahora sobrevive al checkout en `measured_capabilities.py`; estos tests
siguen inyectando sólo la observación nombrada por cada caso para que la unidad
bajo prueba sea el selector, no el baseline distribuido.
"""

from __future__ import annotations

import pytest

from src.packet_tracer_mcp.application.use_cases.plan_enterprise_hardware import (
    capability_catalog_for,
)
from src.packet_tracer_mcp.domain.enterprise.models.capabilities import (
    CapabilityStatus,
    DeviceCandidateStatus,
    DeviceRequirement,
    DeviceSelectionStatus,
)
from src.packet_tracer_mcp.domain.enterprise.models.roles import DeviceRole
from src.packet_tracer_mcp.domain.enterprise.services.device_selector import DeviceSelector
from src.packet_tracer_mcp.infrastructure.catalog.capability_providers import (
    ProbeCapabilityProvider,
    RuntimeCapabilityProvider,
)
from src.packet_tracer_mcp.infrastructure.catalog.enterprise_capabilities import (
    EnterpriseCapabilityAdapter,
)
from tests.test_e95_capability_reconciliation import (
    MEASURED_VERSION,
    _probe_result,
    _store_with,
)

MEASURED_MODEL = "3560-24PS"
OTHER_MODEL = "3650-24PS"
LAYER3_ROLE = DeviceRequirement(
    role=DeviceRole.DISTRIBUTION_SWITCH, min_uplinks=1, requires_layer3=True,
)


@pytest.fixture
def measured_store(tmp_path_factory):
    """Sólo `3560-24PS`, y sólo la capacidad que el probe realmente demostró."""
    return _store_with(tmp_path_factory, "multilayer", [
        _probe_result(
            MEASURED_MODEL, "multilayer_intervlan",
            status=CapabilityStatus.SUPPORTED, verified=True,
        ),
    ])


def _catalog(store=None, *, version: str | None = MEASURED_VERSION):
    if version is None:
        return capability_catalog_for(None)
    return EnterpriseCapabilityAdapter(
        providers=[
            ProbeCapabilityProvider(store, version),
            RuntimeCapabilityProvider(store, version),
        ],
        bound_packet_tracer_version=version,
    )


def _select(store=None, *, version: str | None = MEASURED_VERSION, asked=MEASURED_VERSION):
    catalog = _catalog(store, version=version)
    candidates = [item.capabilities for item in catalog.hardware_candidates("switch", asked)]
    return DeviceSelector().select(LAYER3_ROLE, candidates)


def _needs_verification(selection) -> set[str]:
    return {
        item.model for item in selection.candidates
        if item.status is DeviceCandidateStatus.NEEDS_VERIFICATION
    }


# ===================== la evidencia decide la elegibilidad =================


def test_measured_evidence_makes_a_model_eligible(measured_store):
    selection = _select(measured_store)

    assert selection.status is DeviceSelectionStatus.SUPPORTED
    assert selection.selected_model == MEASURED_MODEL


def test_without_evidence_the_same_role_selects_nothing():
    selection = _select(None, version=None)

    assert selection.status is DeviceSelectionStatus.PARTIALLY_SUPPORTED
    assert selection.selected_model is None
    assert MEASURED_MODEL in _needs_verification(selection)


def test_a_version_mismatch_makes_the_same_evidence_ineligible(measured_store):
    """La evidencia sólo vale para el build exacto que la produjo."""
    selection = _select(measured_store, version="0.0.0.0000", asked="0.0.0.0000")

    assert selection.status is DeviceSelectionStatus.PARTIALLY_SUPPORTED
    assert selection.selected_model is None
    assert MEASURED_MODEL in _needs_verification(selection)


def test_unknown_stays_unknown_for_every_unmeasured_model(measured_store):
    """Un modelo sin evidencia no queda habilitado por estar al lado de uno que sí."""
    selection = _select(measured_store)

    unresolved = _needs_verification(selection)
    assert OTHER_MODEL in unresolved
    assert MEASURED_MODEL not in unresolved


def test_the_decision_is_deterministic_across_repeated_compositions(measured_store):
    first = _select(measured_store)
    second = _select(measured_store)

    assert first.selected_model == second.selected_model
    assert first.status is second.status
    assert [item.model for item in first.candidates] == [
        item.model for item in second.candidates
    ]


def test_evidence_is_never_redistributed_to_a_neighbouring_model(measured_store):
    catalog = _catalog(measured_store)
    by_model = {
        item.model: item.capabilities
        for item in catalog.hardware_candidates("switch", MEASURED_VERSION)
    }

    assert by_model[MEASURED_MODEL].layer3 is CapabilityStatus.SUPPORTED
    assert by_model[OTHER_MODEL].layer3 is CapabilityStatus.UNKNOWN


def test_a_measured_negative_is_refused_rather_than_left_to_verify(tmp_path_factory):
    """UNSUPPORTED no es lo mismo que UNKNOWN: uno se rechaza, el otro se verifica."""
    store = _store_with(tmp_path_factory, "negative", [
        _probe_result(
            MEASURED_MODEL, "layer3",
            status=CapabilityStatus.UNSUPPORTED, verified=True,
        ),
    ])

    selection = _select(store)

    rejected = {
        item.model for item in selection.candidates
        if item.status is DeviceCandidateStatus.INCOMPATIBLE
    }
    assert MEASURED_MODEL in rejected
    assert MEASURED_MODEL not in _needs_verification(selection)


def test_the_decision_follows_the_evidence_and_not_the_model_name(tmp_path_factory):
    """Mover la evidencia al otro modelo mueve la selección con ella.

    Es la prueba directa de "sin casos especiales por nombre de modelo": si
    alguna rama privilegiara a `3560-24PS`, este test seguiría eligiéndolo con
    la evidencia puesta en `3650-24PS`.
    """
    moved = _store_with(tmp_path_factory, "moved", [
        _probe_result(
            OTHER_MODEL, "multilayer_intervlan",
            status=CapabilityStatus.SUPPORTED, verified=True,
        ),
    ])

    selection = _select(moved)

    assert selection.selected_model == OTHER_MODEL
    assert MEASURED_MODEL in _needs_verification(selection)


def test_every_unverified_switch_names_the_capability_it_is_missing(measured_store):
    selection = _select(measured_store)

    for candidate in selection.candidates:
        if candidate.status is DeviceCandidateStatus.NEEDS_VERIFICATION:
            assert candidate.missing_evidence == ["layer3"]
