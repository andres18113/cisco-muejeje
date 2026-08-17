"""El slot pedido y el numero de modulo observado son namespaces distintos.

Hallazgo del gate en vivo MEG-4, 2026-08-17, sobre 2911 en PT 9.0.1.0858.

El modulo HWIC-2T se instalo y sus puertos se verificaron de forma independiente
-- `Serial0/0/0` y `Serial0/0/1` aparecieron en una relectura fresca. Aun asi el
despliegue se nego, porque `slot_effect_observed` compara

    item.observed_module_number  ("0",   namespace del arbol de modulos)
    module.slot                  ("0/0", namespace de nombres de puerto)

Nunca pueden ser iguales para este modelo. Y el HWIC insertado ni siquiera
aparece en el arbol: la unica entrada reportada es el modulo onboard, con tres
puertos Gigabit. Emparejar contra `"0"` afirmaria que el HWIC entro en el slot
onboard, que es falso.

Por que no se detecto antes: `test_e95_serial_physical_product_slice.py` pone
`slot_effect_observed=True` a mano en su doble, asi que ninguna regresion habia
ejercido la derivacion real.

Estos tests fijan la condicion medida. NO relajan la puerta -- relajarla para que
la corrida pase seria fabricar el resultado. La capacidad que falta esta abierta
como `TD-MODULE-SLOT-001`.
"""

from __future__ import annotations

from src.packet_tracer_mcp.domain.enterprise.models.physical_deployment import (
    EvidenceFreshness,
    ObservationStatus,
    PhysicalModuleObservation,
    PhysicalModuleSlotObservation,
)

#: Exactamente lo que PT 9.0.1.0858 reporto para un 2911 tras insertar HWIC-2T.
_LIVE_SLOT_OBSERVATION = PhysicalModuleSlotObservation(
    observed_module_number="0",
    slot_type_code="18",
    port_count=3,
    observed_module_identity="",
    identity_observable=False,
)

_SERIAL_PORTS = ["Serial0/0/0", "Serial0/0/1"]


def _live_module_observation(**overrides) -> PhysicalModuleObservation:
    """La observacion medida en vivo, con el slot pedido en `0/0`."""
    base = dict(
        target_id="A-EDGE-RTR-01:0/0:HWIC-2T",
        device_name="A-EDGE-RTR-01",
        requested_slot="0/0",
        requested_module="HWIC-2T",
        freshness=EvidenceFreshness.FRESH,
        port_inventory_observed=True,
        expected_ports=_SERIAL_PORTS,
        expected_port_classes=["serial"],
        ports_before=["GigabitEthernet0/0", "GigabitEthernet0/1", "GigabitEthernet0/2", "Vlan1"],
        ports_after=[
            "GigabitEthernet0/0", "GigabitEthernet0/1", "GigabitEthernet0/2",
            *_SERIAL_PORTS, "Vlan1",
        ],
        observed_expected_ports=_SERIAL_PORTS,
        added_ports=_SERIAL_PORTS,
        observed_port_classes=["serial"],
        slot_observations=[_LIVE_SLOT_OBSERVATION],
        # Medido: el efecto de puerto SI se observa; el del slot NO.
        effect_observed=True,
        slot_effect_observed=False,
        identity_observation_status=ObservationStatus.UNOBSERVABLE,
        observed_module_identity="",
        message="fresh_packet_tracer_module_port_effect_readback",
    )
    base.update(overrides)
    return PhysicalModuleObservation(**base)


class TestTheTwoNamespacesCannotBeCompared:
    def test_the_observed_module_number_is_not_the_requested_slot(self):
        """La medicion, fijada: `0` no es `0/0`, y compararlos no tiene sentido."""
        observation = _live_module_observation()

        assert observation.requested_slot == "0/0"
        assert [item.observed_module_number for item in observation.slot_observations] == ["0"]
        assert observation.requested_slot not in {
            item.observed_module_number for item in observation.slot_observations
        }

    def test_the_inserted_module_never_appears_in_the_tree(self):
        """Solo se reporta el modulo onboard: 3 puertos Gigabit, sin identidad.

        Por eso emparejar contra `0` seria peor que no emparejar: afirmaria una
        ubicacion que la evidencia no respalda.
        """
        observation = _live_module_observation()

        assert len(observation.slot_observations) == 1
        only = observation.slot_observations[0]
        assert only.port_count == 3
        assert only.identity_observable is False
        assert only.observed_module_identity == ""


class TestThePortEffectIsRealEvenWhenTheSlotIsNot:
    def test_the_serial_ports_were_independently_observed(self):
        observation = _live_module_observation()

        assert observation.effect_observed is True
        assert set(_SERIAL_PORTS).issubset(observation.ports_after)
        assert observation.added_ports == _SERIAL_PORTS
        assert set(observation.ports_before).isdisjoint(_SERIAL_PORTS)

    def test_port_evidence_never_promotes_module_identity(self):
        """El puerto prueba efecto, nunca la identidad del modulo pedido."""
        observation = _live_module_observation()

        assert observation.identity_observation_status is ObservationStatus.UNOBSERVABLE
        assert observation.observed_module_identity == ""


class TestTheDeploymentGateStillRefuses:
    """Documenta la puerta tal como esta, sin relajarla.

    Si algun dia se decide que una ubicacion de slot UNOBSERVABLE no debe
    bloquear, este test falla y esa decision se toma a proposito, con su techo
    de afirmacion escrito. Hasta entonces la negativa es el comportamiento
    correcto y esta fijada.
    """

    def test_a_port_verified_but_slot_unobserved_module_is_refused(self):
        """Ejercita la regla real, no la existencia del modulo.

        Se pasa la observacion medida en vivo por `_observe_module_effect` y se
        comprueba el mensaje exacto que produjo la corrida: `did not converge`.
        """
        from src.packet_tracer_mcp.application.use_cases.deploy_enterprise_topology import (
            EnterprisePhysicalTopologyDeployer,
        )
        from src.packet_tracer_mcp.domain.enterprise.models.physical_deployment import (
            PhysicalModuleEffectCapability,
            SupportStatus,
        )
        from src.packet_tracer_mcp.domain.models.plans import ModulePlan

        module = ModulePlan(device="A-EDGE-RTR-01", slot="0/0", module="HWIC-2T")
        capability = PhysicalModuleEffectCapability(
            target_id="A-EDGE-RTR-01:0/0:HWIC-2T",
            operation_support=SupportStatus.SUPPORTED,
            effect_observation_support=SupportStatus.SUPPORTED,
            expected_ports=_SERIAL_PORTS,
            expected_port_classes=["serial"],
            identity_observation_status=ObservationStatus.UNOBSERVABLE,
        )

        class _OnlyObservesTheModule:
            def observe_module_effect(self, _module):
                return _live_module_observation()

        deployer = EnterprisePhysicalTopologyDeployer(_OnlyObservesTheModule())
        observation, error = deployer._observe_module_effect(module, capability)

        assert observation is not None
        assert observation.effect_observed is True
        assert error == "Module effect for 'A-EDGE-RTR-01:0/0:HWIC-2T' did not converge."

    def test_the_slice_2a_double_fakes_what_the_live_run_could_not_produce(self):
        """La razon por la que esto no se detecto, hecha visible.

        El doble de Slice 2A afirma `slot_effect_observed=True`. Contra Packet
        Tracer real ese valor es False. Mientras el doble siga afirmandolo, la
        suite no puede volver a descubrir este hallazgo sola.
        """
        import pathlib

        slice_2a = (
            pathlib.Path(__file__).resolve().parents[0]
            / "test_e95_serial_physical_product_slice.py"
        ).read_text(encoding="utf-8")

        assert "slot_effect_observed=True" in slice_2a, (
            "si el doble dejo de fabricar este valor, revisar TD-MODULE-SLOT-001"
        )
