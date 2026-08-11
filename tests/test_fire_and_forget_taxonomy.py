"""Taxonomia completa de superficies fire-and-forget, y los gates de R2.

Un informe anterior mezclo dos cosas distintas: las familias de accion de
CONFIGURACION y el conjunto de todas las familias de mutacion fire-and-forget
del producto. Aca se separan por subsistema, se cuentan, y se exige que cada
familia aparezca EXACTAMENTE UNA VEZ en una sola clasificacion.

Alcance de la evidencia: la clasificacion se apoya en la forma del payload
leida de los generadores. NO hay medicion sobre Packet Tracer en este archivo.
"""

from __future__ import annotations

import pytest

REPLAY_SAFE = "REPLAY_SAFE"
TREAT_UNSAFE = "TREAT_AS_REPLAY_UNSAFE"
UNKNOWN = "UNKNOWN"
DEVELOPER = "DEVELOPER_DISPOSABLE"
OUTSIDE = "OUTSIDE_NORMAL_TYPED_PRODUCT_CONTRACT"

# subsistema -> familia -> clasificacion
TAXONOMY: dict[str, dict[str, str]] = {
    "Enterprise Configuration": {
        "CreateVlan": REPLAY_SAFE,
        "ConfigureAccessPort": REPLAY_SAFE,
        "ConfigureTrunk": REPLAY_SAFE,
        "ConfigureRoutedInterface": REPLAY_SAFE,
        "ConfigureSvi": REPLAY_SAFE,
        "ConfigureSubinterface": REPLAY_SAFE,
        "ConfigureDhcpPool": REPLAY_SAFE,
        "ConfigureSerialClock": REPLAY_SAFE,
        "ConfigureInterfaceBandwidth": REPLAY_SAFE,
        "ConfigureEthernetLinkMode": REPLAY_SAFE,
    },
    "Endpoint": {
        "SetEndpointStaticAddress": REPLAY_SAFE,
        "SetEndpointDhcp": REPLAY_SAFE,
    },
    "Control Plane": {
        "spanning-tree priority": REPLAY_SAFE,
        "port-channel / etherchannel": REPLAY_SAFE,
        "router ospf": REPLAY_SAFE,
        "router eigrp": REPLAY_SAFE,
    },
    "Security": {
        "interface hardening (nat inside / snooping trust / arp trust)": REPLAY_SAFE,
        "banner + service password-encryption": REPLAY_SAFE,
        "NAT (cuerpo ACL)": TREAT_UNSAFE,
    },
    "Voice": {
        "telephony-service knobs (max-ephones / max-dn / source-address)": REPLAY_SAFE,
        "ephone-dn / ephone / button": REPLAY_SAFE,
        "option 150 (dhcp)": REPLAY_SAFE,
        "telephony-service create cnf-files": UNKNOWN,
    },
    "Probe / developer": {
        "capability probe vlan+interface payloads": DEVELOPER,
    },
    "Public / raw / legacy": {
        "pt_send_raw(wait_result=False)": OUTSIDE,
        "pt_apply_acl (ACLPlan)": TREAT_UNSAFE,
        "pt_live_deploy batch + reconcile": REPLAY_SAFE,
        "legacy cli_config_generator (incluye RIP)": OUTSIDE,
    },
}

VALID = {REPLAY_SAFE, TREAT_UNSAFE, UNKNOWN, DEVELOPER, OUTSIDE}


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
        "Enterprise Configuration": 10,
        "Endpoint": 2,
        "Control Plane": 4,
        "Security": 3,
        "Voice": 4,
        "Probe / developer": 1,
        "Public / raw / legacy": 4,
    }
    assert len(_families()) == 28


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
