"""Lectura directa de un puerto de acceso (TD-ACCESSPORT-READBACK-001).

CONTRATO. Un `ConfigureAccessPort` sólo puede reclamar VERIFIED desde UNA
observación fresca que establezca las cinco cosas a la vez: identidad del
dispositivo, identidad exacta de la interfaz, modo switchport de acceso, VLAN
de acceso exacta, y una lectura completa y atribuible al intento actual. Una
observación parcial no verifica el todo: modo sin VLAN, o VLAN sin modo, es una
afirmación más angosta y se reporta como tal.

DE DÓNDE SALEN LOS VALORES. De una cualificación en vivo sobre PT `9.0.1.0858`,
modelo `2950T-24`, con TRES controles en la misma pasada y cada uno
corroborado por una lectura IOS independiente de la misma sesión:

| puerto     | `Administrative Mode` (IOS) | `getAdminOpMode` | `isAccessPort` | `getAccessVlan` |
| ---------- | --------------------------- | ---------------- | -------------- | --------------- |
| access 742 | static access               | 3                | True           | 742             |
| trunk      | trunk                       | 2                | False          | 1               |
| sin tocar  | dynamic desirable           | 0                | True           | 1               |

`isAccessPort` vale True para un puerto `dynamic desirable`, así que NO es el
modo administrativo y no puede sostener el gate. Ese es exactamente el error que
estas regresiones existen para impedir que alguien "arregle" al revés.
"""

from __future__ import annotations

import json

import pytest

from src.packet_tracer_mcp.domain.enterprise.models.configuration import (
    VerificationExpectation,
    VerificationKind,
)
from src.packet_tracer_mcp.domain.enterprise.models.configuration_runtime import (
    ActionExecutionStatus,
    FieldVerificationStatus,
)
from src.packet_tracer_mcp.infrastructure.execution.enterprise_configuration_runtime import (
    ADMIN_OP_MODE_ACCESS,
    MEASURED_ADMIN_OP_MODES,
    PacketTracerEnterpriseConfigurationRuntime,
)

DEVICE = "SW-APQUAL"
INTERFACE = "FastEthernet0/1"
VLAN = 742


def _expectation(interface: str = INTERFACE, vlan_id: int = VLAN):
    return VerificationExpectation(
        id="verify/access-port",
        action_id="cfg/access-port",
        kind=VerificationKind.ACCESS_PORT,
        device_id="dev/1",
        device_name=DEVICE,
        expected={"interface": interface, "vlan_id": vlan_id},
    )


def _observation(**overrides):
    """La forma exacta que devuelve la lectura de objeto, con overrides."""
    payload = {
        "device_found": True,
        "port_found": True,
        "owner_device_name": DEVICE,
        "interface": INTERFACE,
        "admin_op_mode": ADMIN_OP_MODE_ACCESS,
        "access_vlan": VLAN,
        "complete": True,
    }
    payload.update(overrides)
    return payload


_TIMEOUT = object()


def _runtime(observation, *, raw=_TIMEOUT):
    calls: list[str] = []

    def send_and_wait(payload: str, _timeout: float):
        calls.append(payload)
        if raw is _TIMEOUT:
            return json.dumps(observation)
        return raw

    runtime = PacketTracerEnterpriseConfigurationRuntime(
        query_inventory=lambda: [],
        send=lambda _payload: True,
        send_and_wait=send_and_wait,
        ios_readiness=lambda _device: True,
    )
    return runtime, calls


def _verify(observation=None, *, expectation=None, raw=_TIMEOUT):
    runtime, calls = _runtime(observation or _observation(), raw=raw)
    results = runtime.verify([expectation or _expectation()])
    assert len(results) == 1
    return results[0], calls


# ===================== el camino positivo ==================================


def test_a_measured_access_port_verifies_every_field_separately():
    result, _ = _verify()

    assert result.status is ActionExecutionStatus.VERIFIED
    assert result.fresh_evidence is True
    assert result.evidence_method == "switch_port_object_state"
    assert result.fields["interface"] is FieldVerificationStatus.VERIFIED
    assert result.fields["vlan_id"] is FieldVerificationStatus.VERIFIED
    assert result.fields["switchport_mode"] is FieldVerificationStatus.VERIFIED
    assert result.fields["device_identity"] is FieldVerificationStatus.VERIFIED


def test_the_read_back_is_no_longer_the_unobservable_branch():
    result, _ = _verify()

    assert result.status is not ActionExecutionStatus.UNOBSERVABLE
    assert result.evidence_method != "runtime_observability_limit"


def test_the_interface_travels_to_packet_tracer_json_encoded():
    """AGENTS.md regla 1: ningún campo entra al JS por f-string."""
    _, calls = _verify()

    assert len(calls) == 1
    assert json.dumps(INTERFACE) in calls[0]
    assert json.dumps(DEVICE) in calls[0]


# ===================== cierra en falso, una condición por test =============


def test_a_wrong_vlan_fails_and_does_not_verify_the_action():
    result, _ = _verify(_observation(access_vlan=1))

    assert result.status is ActionExecutionStatus.FAILED
    assert result.fields["vlan_id"] is FieldVerificationStatus.FAILED
    assert result.fields["switchport_mode"] is FieldVerificationStatus.VERIFIED


def test_a_trunk_port_is_not_a_verified_access_port_even_with_the_right_vlan():
    """El control troncal medido: modo 2, con la VLAN de acceso correcta."""
    result, _ = _verify(_observation(admin_op_mode=2, access_vlan=VLAN))

    assert result.status is ActionExecutionStatus.FAILED
    assert result.fields["switchport_mode"] is FieldVerificationStatus.FAILED
    assert result.fields["vlan_id"] is FieldVerificationStatus.VERIFIED


def test_a_dynamic_port_is_not_a_verified_access_port():
    """El control por defecto medido: modo 0, `dynamic desirable`."""
    result, _ = _verify(_observation(admin_op_mode=0, access_vlan=VLAN))

    assert result.status is ActionExecutionStatus.FAILED
    assert result.fields["switchport_mode"] is FieldVerificationStatus.FAILED


def test_an_unmeasured_mode_code_is_unobservable_and_never_verified():
    """Un código que nadie midió no es un modo conocido ni una contradicción."""
    unmeasured = next(
        code for code in range(0, 12) if code not in MEASURED_ADMIN_OP_MODES
    )
    result, _ = _verify(_observation(admin_op_mode=unmeasured))

    assert result.fields["switchport_mode"] is FieldVerificationStatus.UNOBSERVABLE
    assert result.status is ActionExecutionStatus.PARTIAL


def test_a_wrong_interface_identity_fails_and_is_never_a_prefix_match():
    result, _ = _verify(_observation(interface="FastEthernet0/10"))

    assert result.status is ActionExecutionStatus.FAILED
    assert result.fields["interface"] is FieldVerificationStatus.FAILED


def test_an_interface_that_only_shares_a_prefix_is_refused():
    """`FastEthernet0/1` no es `FastEthernet0/11`."""
    result, _ = _verify(
        _observation(interface="FastEthernet0/11"),
        expectation=_expectation(interface="FastEthernet0/1"),
    )

    assert result.fields["interface"] is FieldVerificationStatus.FAILED


def test_the_project_interface_equivalence_rule_still_matches_an_abbreviation():
    result, _ = _verify(
        _observation(interface="Fa0/1"),
        expectation=_expectation(interface="FastEthernet0/1"),
    )

    assert result.fields["interface"] is FieldVerificationStatus.VERIFIED


def test_a_wrong_device_identity_fails_the_whole_observation():
    result, _ = _verify(_observation(owner_device_name="SOMEONE-ELSE"))

    assert result.status is ActionExecutionStatus.FAILED
    assert result.fields["device_identity"] is FieldVerificationStatus.FAILED


def test_a_missing_field_is_unobservable_and_never_verified():
    observation = _observation()
    observation.pop("access_vlan")
    result, _ = _verify(observation)

    assert result.fields["vlan_id"] is FieldVerificationStatus.UNOBSERVABLE
    assert result.status is not ActionExecutionStatus.VERIFIED


def test_an_incomplete_observation_cannot_verify():
    result, _ = _verify(_observation(complete=False))

    assert result.status is not ActionExecutionStatus.VERIFIED


def test_an_absent_port_is_unobservable_rather_than_a_contradiction():
    result, _ = _verify(_observation(port_found=False))

    assert result.status is ActionExecutionStatus.UNOBSERVABLE
    assert result.fresh_evidence is False


def test_an_absent_device_is_unobservable():
    result, _ = _verify(_observation(device_found=False, port_found=False))

    assert result.status is ActionExecutionStatus.UNOBSERVABLE


@pytest.mark.parametrize(
    "raw",
    ["not json at all", "ERROR: boom", "PT_ERROR: ReferenceError", "[1,2,3]"],
    ids=["malformed", "error", "pt_error", "non_object"],
)
def test_a_parser_failure_is_unobservable_and_never_verified(raw):
    result, _ = _verify(raw=raw)

    assert result.status is ActionExecutionStatus.UNOBSERVABLE
    assert result.fields["vlan_id"] is FieldVerificationStatus.UNOBSERVABLE


def test_a_timeout_is_unobservable_and_never_verified():
    """El bridge no respondió: eso no contradice nada, tampoco verifica nada."""
    result, calls = _verify(raw=None)

    assert result.status is ActionExecutionStatus.UNOBSERVABLE
    assert len(calls) == 1


# ===================== nada se promueve de rebote =========================


def test_the_dhcp_pool_ceiling_is_untouched():
    """`DHCP_POOL` compartía la rama `_unobservable`; sigue exactamente igual."""
    runtime, _ = _runtime(_observation())
    expectation = VerificationExpectation(
        id="verify/dhcp",
        action_id="cfg/dhcp",
        kind=VerificationKind.DHCP_POOL,
        device_id="dev/1",
        device_name=DEVICE,
        expected={"network": "198.18.0.0", "gateway": "198.18.0.1"},
    )

    result = runtime.verify([expectation])[0]

    assert result.status is ActionExecutionStatus.UNOBSERVABLE
    assert result.evidence_method == "runtime_observability_limit"


def test_is_access_port_is_not_wired_as_the_mode_gate():
    """Medido: `isAccessPort` vale True para un `dynamic desirable`.

    Se comprueba sobre el JS QUE SE DESPACHA, no sobre el archivo: la
    explicación de por qué ese getter no sirve tiene que poder vivir en un
    comentario sin que la regresión la confunda con un uso.
    """
    _, calls = _verify()

    assert "isAccessPort" not in calls[0]
    assert "getAdminOpMode" in calls[0]
    assert "getAccessVlan" in calls[0]


# ===================== un tipo ilegible no contradice nada ================
#
# Encontrado por revisión adversarial. `getAccessVlan()` vuelve sin envolver, a
# diferencia de los getters de nombre, así que un retorno envuelto por Java que
# `JSON.stringify` renderice como `"742"` o `{}` es exactamente la clase de
# payload que llega acá. Reportarlo como FAILED le diría al operador que el
# puerto CONTRADICE lo esperado, a partir de una observación que no estableció
# nada. Es el mismo error que `_switchport_mode_field` ya evita.


@pytest.mark.parametrize(
    "value", ["742", {}, [], 742.5, True, None],
    ids=["string", "object", "array", "fraction", "bool", "null"],
)
def test_an_unreadable_vlan_value_is_unobservable_not_contradicted(value):
    result, _ = _verify(_observation(access_vlan=value))

    assert result.fields["vlan_id"] is FieldVerificationStatus.UNOBSERVABLE
    assert result.status is not ActionExecutionStatus.VERIFIED
    assert result.status is not ActionExecutionStatus.FAILED


def test_an_integral_float_is_the_same_vlan_number():
    result, _ = _verify(_observation(access_vlan=float(VLAN)))

    assert result.fields["vlan_id"] is FieldVerificationStatus.VERIFIED


@pytest.mark.parametrize(
    "value", [12, {}, [], True], ids=["number", "object", "array", "bool"],
)
def test_an_unreadable_device_identity_is_unobservable_not_contradicted(value):
    result, _ = _verify(_observation(owner_device_name=value))

    assert result.fields["device_identity"] is FieldVerificationStatus.UNOBSERVABLE
    assert result.status is not ActionExecutionStatus.FAILED


@pytest.mark.parametrize("value", [12, {}, [], True], ids=["number", "object", "array", "bool"])
def test_an_unreadable_interface_name_is_unobservable_not_contradicted(value):
    result, _ = _verify(_observation(interface=value))

    assert result.fields["interface"] is FieldVerificationStatus.UNOBSERVABLE
    assert result.status is not ActionExecutionStatus.FAILED


# ===================== completo significa completo =========================


@pytest.mark.parametrize("value", ["false", "", 0, 1, "yes", None], ids=[
    "string_false", "empty_string", "zero", "one", "string_yes", "null",
])
def test_completeness_is_a_boolean_and_never_a_truthy_string(value):
    result, _ = _verify(_observation(complete=value))

    assert result.status is not ActionExecutionStatus.VERIFIED


def test_a_getter_that_returned_undefined_drops_its_key_and_breaks_completeness():
    """`JSON.stringify` borra la clave de un `undefined` sin tocar `complete`."""
    observation = _observation()
    observation.pop("admin_op_mode")

    result, _ = _verify(observation)

    assert result.fields["switchport_mode"] is FieldVerificationStatus.UNOBSERVABLE
    assert result.status is not ActionExecutionStatus.VERIFIED


def test_a_truthy_port_found_that_is_not_true_cannot_verify():
    result, _ = _verify(_observation(port_found="no"))

    assert result.status is ActionExecutionStatus.UNOBSERVABLE


# ======================================================================
# VOICE VLAN — el último salto L2 antes de Router4.
#
# `ConfigureAccessPort` lleva `data_vlan_id` Y `voice_vlan_id` para un puerto
# que mira a un teléfono, pero hasta acá la expectativa sólo cargaba el de
# datos y la lectura sólo leía `getAccessVlan()`. La VLAN de voz quedaba
# APLICADA y jamás observada: ni verificada ni contradicha, invisible.
#
# `getVoipVlanId` está CONFIRMADO como `function` sobre los puertos físicos de
# un switch en PT 9.0.1.0858 -- evidencia retenida en
# `data/cp-scale/ap-addressability/result.json`, donde la SVI `Vlan1` y los
# puertos de un AP lo devuelven `undefined` y `FastEthernet0/x` no. Que el
# getter exista no dice que su valor signifique lo que su nombre sugiere, así
# que el lector COMPARA contra lo esperado y nunca confía.
# ======================================================================

VOICE_VLAN = 20


def _voice_expectation(interface: str = INTERFACE, vlan_id: int = VLAN,
                       voice_vlan_id: int = VOICE_VLAN):
    return VerificationExpectation(
        id="verify/access-port-voice",
        action_id="cfg/access-port-voice",
        kind=VerificationKind.ACCESS_PORT,
        device_id="dev/1",
        device_name=DEVICE,
        expected={
            "interface": interface, "vlan_id": vlan_id,
            "voice_vlan_id": voice_vlan_id,
        },
    )


def _voice_observation(**overrides):
    payload = _observation(voice_vlan=VOICE_VLAN)
    payload.update(overrides)
    return payload


class TestTheVoiceVlanIsReadOnlyWhenItIsClaimed:
    """Un puerto sin teléfono no gana un campo nuevo ni una lectura nueva."""

    def test_a_data_only_port_never_probes_the_voice_getter(self):
        _, calls = _verify()

        assert len(calls) == 1
        assert "getVoipVlanId" not in calls[0]

    def test_a_data_only_port_keeps_exactly_its_four_fields(self):
        result, _ = _verify()

        assert set(result.fields) == {
            "device_identity", "interface", "switchport_mode", "vlan_id",
        }
        assert result.status is ActionExecutionStatus.VERIFIED

    def test_a_phone_facing_port_probes_the_measured_getter(self):
        _, calls = _verify(
            _voice_observation(), expectation=_voice_expectation(),
        )

        assert "getVoipVlanId" in calls[0]
        # Sigue siendo UNA sola lectura: el getter viaja en el mismo JS que ya
        # leía la VLAN de datos, así que 21 teléfonos no cuestan 21 viajes más.
        assert len(calls) == 1


class TestTheVoiceVlanIsDecidedOnItsOwnEvidence:
    """Ningún campo se marca desde otro campo."""

    def test_a_matching_voice_vlan_verifies_the_field_and_the_action(self):
        result, _ = _verify(
            _voice_observation(), expectation=_voice_expectation(),
        )

        assert result.fields["voice_vlan_id"] is FieldVerificationStatus.VERIFIED
        assert result.fields["vlan_id"] is FieldVerificationStatus.VERIFIED
        assert result.status is ActionExecutionStatus.VERIFIED

    def test_a_readable_different_voice_vlan_contradicts(self):
        result, _ = _verify(
            _voice_observation(voice_vlan=999), expectation=_voice_expectation(),
        )

        assert result.fields["voice_vlan_id"] is FieldVerificationStatus.FAILED
        # La VLAN de datos sigue siendo verdadera por su cuenta.
        assert result.fields["vlan_id"] is FieldVerificationStatus.VERIFIED
        assert result.status is ActionExecutionStatus.FAILED
        # El valor crudo queda en la evidencia: una contradicción falsa por
        # semántica del getter tiene que ser diagnosticable sin otro LIVE.
        assert "999" in result.message
        assert "20" in result.message

    def test_an_absent_voice_getter_is_unobservable_not_contradicted(self):
        """`JSON.stringify` borra la clave de un getter `undefined`."""
        observation = _voice_observation()
        observation.pop("voice_vlan")

        result, _ = _verify(observation, expectation=_voice_expectation())

        assert result.fields["voice_vlan_id"] is FieldVerificationStatus.UNOBSERVABLE
        # Exactamente la combinación que el contrato declara válida.
        assert result.fields["vlan_id"] is FieldVerificationStatus.VERIFIED
        assert result.status is ActionExecutionStatus.PARTIAL
        assert result.status is not ActionExecutionStatus.FAILED

    def test_a_failed_voice_getter_reports_unavailability_without_its_raw_error(self):
        observation = _voice_observation()
        observation.pop("voice_vlan")
        observation["voice_vlan_error"] = "SENSITIVE PT OBJECT " * 100

        result, _ = _verify(observation, expectation=_voice_expectation())

        assert result.fields["voice_vlan_id"] is FieldVerificationStatus.UNOBSERVABLE
        assert "getter unavailable" in result.message.casefold()
        assert "SENSITIVE PT OBJECT" not in result.message

    def test_an_unreadable_voice_object_is_bounded_typed_evidence_not_a_dump(self):
        opaque = {"payload": "SENSITIVE PT OBJECT " * 100}

        result, _ = _verify(
            _voice_observation(voice_vlan=opaque), expectation=_voice_expectation(),
        )

        assert result.fields["voice_vlan_id"] is FieldVerificationStatus.UNOBSERVABLE
        assert "dict" in result.message
        assert "SENSITIVE PT OBJECT" not in result.message
        assert len(result.message) < 256

    def test_voice_can_verify_when_the_data_vlan_is_unobservable(self):
        observation = _voice_observation()
        observation.pop("access_vlan")

        result, _ = _verify(observation, expectation=_voice_expectation())

        assert result.fields["vlan_id"] is FieldVerificationStatus.UNOBSERVABLE
        assert result.fields["voice_vlan_id"] is FieldVerificationStatus.VERIFIED
        assert result.status is ActionExecutionStatus.PARTIAL

    @pytest.mark.parametrize("value", ["20", True, {}, None])
    def test_an_unreadable_voice_value_never_contradicts(self, value):
        result, _ = _verify(
            _voice_observation(voice_vlan=value), expectation=_voice_expectation(),
        )

        assert result.fields["voice_vlan_id"] is FieldVerificationStatus.UNOBSERVABLE
        assert result.status is not ActionExecutionStatus.FAILED


class TestTheCompilerClaimsTheVoiceVlan:
    """Lo que nadie reclama, nadie puede verificar ni contradecir."""

    def test_a_phone_facing_access_port_expectation_carries_the_voice_vlan(self):
        from src.packet_tracer_mcp.domain.enterprise.models.configuration import (
            ConfigurationPhase,
            ConfigureAccessPort,
        )
        from src.packet_tracer_mcp.domain.enterprise.services.configuration_compiler import (
            ConfigurationCompiler,
        )

        action = ConfigureAccessPort(
            id="cfg/access/phone", device_id="dev/1", device_name=DEVICE,
            site_id="site", phase=ConfigurationPhase.L2_INTERFACES,
            interface=INTERFACE, data_vlan_id=VLAN,
            voice_vlan_id=VOICE_VLAN,
        )

        expectation = ConfigurationCompiler._expectations([action])[0]

        assert expectation.kind is VerificationKind.ACCESS_PORT
        assert expectation.expected["vlan_id"] == VLAN
        assert expectation.expected["voice_vlan_id"] == VOICE_VLAN

    def test_a_data_only_access_port_expectation_gains_no_voice_key(self):
        from src.packet_tracer_mcp.domain.enterprise.models.configuration import (
            ConfigurationPhase,
            ConfigureAccessPort,
        )
        from src.packet_tracer_mcp.domain.enterprise.services.configuration_compiler import (
            ConfigurationCompiler,
        )

        action = ConfigureAccessPort(
            id="cfg/access/pc", device_id="dev/1", device_name=DEVICE,
            site_id="site", phase=ConfigurationPhase.L2_INTERFACES,
            interface=INTERFACE, data_vlan_id=VLAN,
        )

        expectation = ConfigurationCompiler._expectations([action])[0]

        assert "voice_vlan_id" not in expectation.expected


class TestTheExistingProductGateKeepsItsContradictionSemantics:
    """PARTIAL no bloquea; una contradicción fresca sí, aunque el agregado sea PARTIAL."""

    @staticmethod
    def _application(verification_status: ActionExecutionStatus):
        from src.packet_tracer_mcp.domain.enterprise.models.configuration_runtime import (
            ConfigurationApplicationResult,
            ConfigurationApplicationStatus,
            VerificationResult,
        )

        return ConfigurationApplicationResult(
            config_plan_id="cfg/plan",
            config_semantic_hash="cfg-hash",
            source_topology_hash="topology-hash",
            status=ConfigurationApplicationStatus.PARTIAL,
            verification_results=[VerificationResult(
                expectation_id="verify/access-port-voice",
                action_id="cfg/access-port-voice",
                status=verification_status,
            )],
        )

    def test_a_partial_voice_observation_does_not_fabricate_a_contradiction(self):
        from src.packet_tracer_mcp.application.use_cases.execute_enterprise_reference import (
            configuration_application_contradiction,
        )

        result = self._application(ActionExecutionStatus.PARTIAL)

        assert configuration_application_contradiction(result) == ""

    def test_a_readable_voice_mismatch_still_blocks_the_product_flow(self):
        from src.packet_tracer_mcp.application.use_cases.execute_enterprise_reference import (
            configuration_application_contradiction,
        )

        result = self._application(ActionExecutionStatus.FAILED)

        contradiction = configuration_application_contradiction(result)
        assert "verify/access-port-voice" in contradiction
