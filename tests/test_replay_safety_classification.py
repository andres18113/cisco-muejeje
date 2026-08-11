"""Replay-safety de cada familia de accion tipada, bajo el transporte actual.

Por que existe:
El motor puede reejecutar un `req` que contesto pero no logro borrar. Eso hace
que la pregunta relevante no sea "hay readback" sino "que pasa si el payload se
aplica dos veces". READBACK != REPLAY SAFETY: releer detecta la deriva DESPUES,
no impide el efecto duplicado.

La distincion estructural que decide cada caso:

    forma de conjunto/asignacion -> reaplicar no deberia agregar nada
    forma de lista ordenada      -> reaplicar podria agregar una entrada mas

ALCANCE DE LA EVIDENCIA. Estos tests leen el texto que los generadores emiten
de verdad, y eso es todo lo que prueban: la FORMA del payload. NINGUNO mide
Packet Tracer. Por eso la clasificacion habla de como se TRATA cada familia y
no de como PT se comporta: una familia estructuralmente aditiva se trata como
insegura hasta que exista una reproduccion controlada, tal como exige el
"Gate discipline" de e95-stabilization.
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
GENERATOR = REPO / "src" / "packet_tracer_mcp" / "infrastructure" / "generator"


# Familias cuya reaplicacion deja el mismo estado, por semantica de conjunto o
# de asignacion declarativa. Evidencia: el texto emitido por cada generador.
REPLAY_SAFE_FAMILIES = {
    "CreateVlan": "vlan N / name X -- conjunto por id",
    "ConfigureAccessPort": "switchport access vlan N -- asignacion",
    "ConfigureTrunk": "switchport trunk allowed vlan <lista completa> -- forma replace, no `add`",
    "ConfigureRoutedInterface": "ip address A M -- asignacion",
    "ConfigureSvi": "interface Vlan N / ip address A M -- asignacion",
    "ConfigureSubinterface": "encapsulation dot1q N / ip address A M -- asignacion",
    "ConfigureDhcpPool": "ip dhcp pool P / network / default-router -- asignacion",
    "ConfigureSerialClock": "clock rate N -- asignacion",
    "ConfigureInterfaceBandwidth": "bandwidth N -- asignacion",
    "ConfigureEthernetLinkMode": "duplex/speed -- asignacion",
    "SetEndpointStaticAddress": "configurePcIp(...) -- setter estructurado",
    "SetEndpointDhcp": "configurePcIp(dhcp) -- setter estructurado",
}

# Familias que se TRATAN como inseguras por precaucion de producto.
#
# Lo que esta probado es la FORMA del payload, leida del generador: es
# estructuralmente aditiva. Lo que NO esta probado es como se comporta Packet
# Tracer al recibirla dos veces -- no se corrio ninguna reproduccion. El propio
# "Gate discipline" de e95-stabilization exige una reproduccion controlada
# antes de clasificar una limitacion de PT, asi que aqui no se afirma que PT
# duplique la ACE: se la trata como insegura mientras no haya evidencia.
REPLAY_UNSAFE_FAMILIES = {
    "ACLPlan / pt_apply_acl": (
        "STRUCTURALLY_ADDITIVE: generate_acl_cli emite solo "
        "`access-list N permit|deny ...`, sin un `no access-list N` delante. "
        "REPLAY_SAFETY_NOT_PROVEN: no se midio el efecto de aplicarla dos "
        "veces en PT. TREAT_AS_REPLAY_UNSAFE por seguridad de producto."
    ),
    "NAT (cuerpo ACL)": (
        "STRUCTURALLY_ADDITIVE: generate_nat_body_cli emite "
        "`access-list N permit <net>`, la misma forma. "
        "REPLAY_SAFETY_NOT_PROVEN, hereda el trato conservador."
    ),
}

# Sin medicion propia. No se declara seguro lo que no se comprobo.
REPLAY_UNKNOWN_FAMILIES = {
    "telephony-service create cnf-files": (
        "Es un verbo imperativo, no una asignacion. Regenerar los archivos dos "
        "veces probablemente rinde lo mismo, pero no se midio en PT."
    ),
}


# -- evidencia de las familias seguras ------------------------------------

def test_the_trunk_family_uses_the_replace_form_not_the_additive_one():
    """`allowed vlan X` reemplaza; `allowed vlan add X` acumularia."""
    source = (GENERATOR / "vlan_cli_generator.py").read_text(encoding="utf-8")

    assert "switchport trunk allowed vlan {allowed}" in source
    assert "allowed vlan add" not in source


def test_the_configuration_renderer_emits_only_assignments():
    """Ningun comando del renderer de configuracion es aditivo."""
    source = (GENERATOR / "configuration_renderer.py").read_text(encoding="utf-8")

    assert "access-list" not in source
    assert " add " not in source


# -- evidencia de las familias inseguras ----------------------------------

def test_the_acl_generator_appends_entries_without_resetting_the_list():
    """La forma del payload, que es lo unico que aqui se puede probar.

    `build_remove_payload` existe, pero es una operacion SEPARADA de borrado y
    la generacion normal no la antepone. Eso hace al payload estructuralmente
    aditivo. Lo que PT haga al recibirlo dos veces no se midio, y este test no
    lo afirma: por eso la familia se TRATA como insegura en vez de declararse
    probadamente insegura.
    """
    source = (GENERATOR / "acl_cli_generator.py").read_text(encoding="utf-8")
    generate = source.split("def generate_acl_cli")[1].split("\ndef ")[0]

    assert "access-list {plan.name_or_number} remark" in generate
    assert "no access-list" not in generate, (
        "Si la generacion normal antepusiera el reset, la familia pasaria a "
        "ser replay-safe y habria que reclasificarla."
    )
    # El reset existe, pero por fuera y a pedido.
    assert "no access-list {name_or_number}" in source


def test_the_nat_body_shares_the_additive_acl_form():
    source = (GENERATOR / "nat_cli_generator.py").read_text(encoding="utf-8")

    assert "access-list {config.acl_number} permit {net}" in source


# -- la clasificacion es explicita y no tiene huecos ----------------------

@pytest.mark.parametrize("family", sorted(REPLAY_SAFE_FAMILIES))
def test_every_safe_family_has_a_recorded_reason(family):
    assert REPLAY_SAFE_FAMILIES[family].strip()


@pytest.mark.parametrize("family", sorted(REPLAY_UNSAFE_FAMILIES))
def test_every_unsafe_family_has_a_recorded_reason(family):
    assert REPLAY_UNSAFE_FAMILIES[family].strip()


def test_unknown_families_are_named_rather_than_assumed_safe():
    """Lo que no se midio no se declara seguro."""
    assert REPLAY_UNKNOWN_FAMILIES
    for reason in REPLAY_UNKNOWN_FAMILIES.values():
        assert "no se midio" in reason


def test_the_classification_does_not_claim_the_whole_surface_is_safe():
    """Una superficie con una familia insegura no es una superficie segura."""
    assert REPLAY_UNSAFE_FAMILIES, (
        "Si alguna vez no queda ninguna familia insegura, hay que revisar que "
        "sea por un cambio real y no porque se dejo de mirar."
    )


# -- precondiciones de RIPv2 frente a ESTA limitacion ---------------------

# `network X` y `passive-interface X` pertenecen a un CONJUNTO en la config de
# RIP, no a una lista ordenada: repetirlos no crea una segunda entrada. Esa es
# la diferencia estructural con `access-list`, y es lo que hace tolerable la
# reejecucion duplicada para RIP y no para las ACL.
#
# ADVERTENCIA: esto es analisis de la semantica IOS, NO una medicion sobre
# Packet Tracer. R2 deberia confirmarlo aplicando el payload dos veces sobre un
# router disposable y releyendo, antes de apoyarse en ello.
RIPV2_PLANNED_OPERATIONS = {
    "router rip": "entra/crea el proceso; repetirlo no crea un segundo proceso",
    "version 2": "asignacion",
    "no auto-summary": "asignacion booleana",
    "network <major>": "conjunto de redes; repetir no duplica",
    "passive-interface <if>": "conjunto de interfaces; repetir no duplica",
}


@pytest.mark.parametrize("operation", sorted(RIPV2_PLANNED_OPERATIONS))
def test_each_planned_rip_operation_is_declarative_and_set_shaped(operation):
    reason = RIPV2_PLANNED_OPERATIONS[operation]

    assert "asignacion" in reason or "conjunto" in reason or "proceso" in reason
    # Ningun verbo imperativo entra en el set planificado.
    for imperative in ("clear ", "debug ", "reload", "write erase"):
        assert imperative not in operation


def test_the_rip_operation_set_contains_no_ordered_list_command():
    """Lo que haria a RIP tan inseguro como una ACL seria una lista ordenada."""
    assert not any(
        operation.startswith("access-list") or "distribute-list" in operation
        for operation in RIPV2_PLANNED_OPERATIONS
    )
