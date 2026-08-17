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

from src.packet_tracer_mcp.domain.enterprise.mutation_replay import (
    PRODUCT_MUTATION_REPLAY_REGISTRY,
    EvidenceBasis,
    MutationSurface,
    ReplayClassification,
    ReplayContainment,
    UnclassifiedProductMutation,
    policy_for_action_type,
)

REPO = Path(__file__).resolve().parents[1]
GENERATOR = REPO / "src" / "packet_tracer_mcp" / "infrastructure" / "generator"


def _families(classification: ReplayClassification) -> dict[str, str]:
    return {
        item.family: item.evidence
        for item in PRODUCT_MUTATION_REPLAY_REGISTRY
        if item.classification is classification
    }


# La clasificacion vive en fuente de producto. Este archivo conserva pruebas
# puntuales de la forma emitida por los generadores mas sensibles.
REPLAY_SAFE_FAMILIES = _families(ReplayClassification.REPLAY_SAFE)
REPLAY_UNSAFE_FAMILIES = _families(
    ReplayClassification.TREAT_AS_REPLAY_UNSAFE,
)
REPLAY_UNKNOWN_FAMILIES = _families(ReplayClassification.UNKNOWN)


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
    """Lo que no se midio no se declara seguro.

    Antes esto se comprobaba buscando el literal "no se midio" dentro de una
    prosa en castellano. Al mover la fuente de verdad al registro tipado ese
    literal deja de existir, pero la INVARIANTE no puede relajarse a "el texto
    no esta vacio": cualquier frase pasaria. Se afirma sobre `basis`, que es un
    campo estructurado y validado.
    """
    unknown = [
        item for item in PRODUCT_MUTATION_REPLAY_REGISTRY
        if item.classification is ReplayClassification.UNKNOWN
    ]

    assert unknown
    for item in unknown:
        assert item.basis is EvidenceBasis.UNMEASURED, item.family


def test_a_non_empty_reason_can_never_by_itself_make_a_family_replay_safe():
    """La prosa no es contencion.

    Este es exactamente el agujero que abriria `assert reason.strip()`: una
    familia con evidencia redactada pero sin contencion estructural no puede
    llegar a REPLAY_SAFE. El validador del registro lo rechaza al importar.
    """
    for item in PRODUCT_MUTATION_REPLAY_REGISTRY:
        if item.classification is not ReplayClassification.REPLAY_SAFE:
            continue
        structural = {
            ReplayContainment.DECLARATIVE_REAPPLICATION,
            ReplayContainment.STRUCTURED_SETTER,
            ReplayContainment.IN_PAYLOAD_EFFECT_GUARD,
            ReplayContainment.CONTROLLED_REPEAT_QUALIFIED,
        }
        assert structural.intersection(item.containment), item.family
        assert item.basis is not EvidenceBasis.UNMEASURED, item.family


def test_the_three_classifications_are_distinct_and_never_default():
    """UNKNOWN no es UNSAFE, y ninguno de los dos es SAFE.

    Ademas no hay clasificacion por defecto: preguntar por una familia que no
    esta registrada falla cerrado en vez de devolver algo.
    """
    by_class: dict[ReplayClassification, set[str]] = {
        item: set() for item in ReplayClassification
    }
    for item in PRODUCT_MUTATION_REPLAY_REGISTRY:
        by_class[item.classification].add(item.family)

    assert all(by_class.values()), "las tres clases deben estar pobladas"
    assert not by_class[ReplayClassification.REPLAY_SAFE] & by_class[
        ReplayClassification.TREAT_AS_REPLAY_UNSAFE
    ]
    assert not by_class[ReplayClassification.REPLAY_SAFE] & by_class[
        ReplayClassification.UNKNOWN
    ]
    assert not by_class[ReplayClassification.TREAT_AS_REPLAY_UNSAFE] & by_class[
        ReplayClassification.UNKNOWN
    ]

    class _NeverRegistered:
        pass

    with pytest.raises(UnclassifiedProductMutation):
        policy_for_action_type(_NeverRegistered)


def test_the_legacy_raw_acl_path_keeps_an_explicit_classification():
    """Tipificar el resto no puede dejar al camino legacy sin clasificar.

    `pt_apply_acl` sigue expuesto y sigue mutando. Cuando la taxonomia se movio
    al registro tipado esta familia se quedo fuera de toda clasificacion, que es
    peor que clasificarla mal.
    """
    legacy = [
        item for item in PRODUCT_MUTATION_REPLAY_REGISTRY
        if item.surface is MutationSurface.LEGACY_RAW
    ]

    assert [item.family for item in legacy] == ["pt_apply_acl (ACLPlan)"]
    assert legacy[0].classification is ReplayClassification.TREAT_AS_REPLAY_UNSAFE
    # Nombra la ausencia de contencion en vez de inventar una.
    assert legacy[0].containment == (ReplayContainment.NONE_ESTABLISHED,)


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
# Este set nacio como analisis de la semantica IOS. R2-0 lo confirmo en vivo
# (PT 9.0.1.0858, 2911 disposable): dos aplicaciones identicas dejaron el mismo
# estado semantico. La calificacion, con sus limites, esta en
# docs/architecture/ripv2-runtime-qualification.md. Sigue siendo una
# calificacion de una repeticion sobre un modelo, no una afirmacion estadistica.
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


def test_the_typed_rip_renderer_emits_only_the_classified_operation_set():
    """La clasificacion vale para lo que el producto emite, no para un plan.

    Si el renderer tipado empezara a emitir una forma aditiva, la familia
    quedaria mal clasificada sin que ningun otro test lo notara.
    """
    source = (GENERATOR / "control_plane_renderer.py").read_text(encoding="utf-8")
    body = source.split("def _rip(")[1].split("\n\nclass ")[0]

    for additive in ("access-list", "distribute-list", "offset-list", "neighbor "):
        assert additive not in body
    for declared in ("router rip", "version", "no auto-summary", "network",
                     "passive-interface"):
        assert declared in body
