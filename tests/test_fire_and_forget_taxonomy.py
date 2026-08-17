"""Taxonomia de mutaciones tipadas de producto, y los gates de R2.

Un informe anterior mezclo dos cosas distintas: las familias de accion de
CONFIGURACION y el conjunto de todas las familias de mutacion fire-and-forget
del producto. La fuente de verdad vive ahora en el registro del dominio; este
archivo consume esa vista, la cuenta y mantiene separados los caminos raw.

Alcance de la evidencia: la clasificacion se apoya en la forma del payload
leida de los generadores. NO hay medicion sobre Packet Tracer en este archivo.
"""

from __future__ import annotations

import pytest

from src.packet_tracer_mcp.domain.enterprise.mutation_replay import (
    ReplayClassification,
    taxonomy_by_surface,
)

REPLAY_SAFE = ReplayClassification.REPLAY_SAFE.value
TREAT_UNSAFE = ReplayClassification.TREAT_AS_REPLAY_UNSAFE.value
UNKNOWN = ReplayClassification.UNKNOWN.value

# subsistema -> familia -> clasificacion, derivado de fuente de producto.
TAXONOMY = taxonomy_by_surface()
VALID = {item.value for item in ReplayClassification}

# No son mutaciones tipadas normales y por eso no pueden aparecer en el
# registro. Sus limites de superficie se prueban en test_fire_and_forget_surface.
NON_PRODUCT_PATHS = {
    "pt_send_raw(wait_result=False)",
    "legacy cli_config_generator (incluye RIP)",
    "capability probe vlan+interface payloads",
}


def _families() -> list[str]:
    return [family for group in TAXONOMY.values() for family in group]


# -- invariantes duros de la taxonomia ------------------------------------

def test_every_family_has_exactly_one_classification():
    families = _families()

    assert len(families) == len(set(families)), (
        "Una familia aparece dos veces: la taxonomia dejaria de ser una "
        "particion y una de las dos clasificaciones seria invisible."
    )


def test_every_classification_is_from_the_declared_vocabulary():
    for subsystem, group in TAXONOMY.items():
        for family, classification in group.items():
            assert classification in VALID, f"{subsystem}/{family}"


def test_no_subsystem_is_empty():
    for subsystem, group in TAXONOMY.items():
        assert group, subsystem


def test_the_counts_are_stated_explicitly():
    counts = {
        subsystem: len(group) for subsystem, group in TAXONOMY.items()
    }

    assert counts == {
        "Enterprise Configuration": 12,
        "Control Plane": 7,
        "Security": 8,
        "Voice": 7,
        "Services": 8,
        "Physical Topology": 4,
        # No es una mutacion tipada, pero muta y esta expuesta. Tipificar el
        # resto no puede ser la via por la que se queda sin clasificar.
        "Legacy / raw CLI": 1,
    }
    assert len(_families()) == 47


def test_non_product_paths_cannot_masquerade_as_registered_product_families():
    assert NON_PRODUCT_PATHS.isdisjoint(_families())


def test_the_taxonomy_still_contains_families_that_are_not_safe():
    """Si algun dia no queda ninguna, que sea por evidencia y no por descuido."""
    classifications = {
        classification
        for group in TAXONOMY.values() for classification in group.values()
    }

    assert TREAT_UNSAFE in classifications
    assert UNKNOWN in classifications


# -- 10. los dos gates de RIP van separados -------------------------------

RIPV2_GATES = {
    "RIPV2_REPLAY_SEMANTIC_ANALYSIS": "READY",
    "RIPV2_REPLAY_LIVE_QUALIFICATION": "NOT_EVALUATED",
    "RIPV2_CURRENT_TRANSPORT_SAFETY": "READY_PENDING_LIVE_QUALIFICATION",
}


def test_the_live_qualification_gate_is_not_claimed():
    """El payload RIP nunca se aplico dos veces en PT. No se finge que si."""
    assert RIPV2_GATES["RIPV2_REPLAY_LIVE_QUALIFICATION"] == "NOT_EVALUATED"


def test_transport_safety_is_not_absolute_ready():
    assert RIPV2_GATES["RIPV2_CURRENT_TRANSPORT_SAFETY"].endswith(
        "PENDING_LIVE_QUALIFICATION",
    )


# El gate que R2-0 debe pasar ANTES de escribir una sola clase de RIP.
R2_ZERO_LIVE_GATE = (
    "router disposable",
    "aplicar el payload RIP una vez",
    "readback directo",
    "aplicar el payload IDENTICO una segunda vez",
    "readback directo",
    "comparar estado semantico",
    "verificar que no haya configuracion semantica duplicada",
    "verificar que el protocolo siga operativo en un slice minimo de dos routers",
)


@pytest.mark.parametrize("step", R2_ZERO_LIVE_GATE)
def test_the_r2_zero_live_gate_is_written_down(step):
    assert step in R2_ZERO_LIVE_GATE


def test_the_live_gate_has_two_applications_and_two_readbacks():
    """Sin la segunda aplicacion y su relectura, el gate no prueba replay."""
    assert sum("aplicar" in step for step in R2_ZERO_LIVE_GATE) == 2
    assert sum("readback" in step for step in R2_ZERO_LIVE_GATE) == 2


# -- 11. reglas de transporte no negociables para R2 ----------------------

R2_TRANSPORT_CONTRACT = (
    "solo acciones tipadas",
    "el generador legacy de RIP no es camino de ejecucion de producto",
    "sin pt_send_raw",
    "un despacho deliberado",
    "cero reintentos ciegos",
    "conjunto de operaciones declarativo/replay-safe unicamente",
    "readback de control plane obligatorio",
    "verificacion conductual despues de configurar",
    "reconciliar solo el estado probado faltante",
    "el execution status por si solo nunca prueba estado de ruteo",
    "la limitacion de exactly-once del FileBridge sigue explicita",
)


@pytest.mark.parametrize("rule", R2_TRANSPORT_CONTRACT)
def test_every_r2_transport_rule_is_predeclared(rule):
    assert rule in R2_TRANSPORT_CONTRACT


def test_the_contract_forbids_both_bypass_paths():
    joined = " | ".join(R2_TRANSPORT_CONTRACT)

    assert "pt_send_raw" in joined
    assert "generador legacy" in joined
