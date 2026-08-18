"""Contrato de aceptacion del EFECTO DE PUERTO de un modulo -- TD-MODULE-SLOT-001, rama B.

Que corrige. La corrida en vivo MEG-4 del 2026-08-17 (2911, PT `9.0.1.0858`)
demostro que el modulo entra y que sus puertos se observan, pero que Packet
Tracer no dice en que slot entro: el arbol de modulos reporta una sola entrada,
el modulo onboard con numero `"0"` y tres puertos Gigabit, y el HWIC-2T
insertado no aparece nunca. La puerta anterior comparaba

    item.observed_module_number  ("0",   namespace del arbol de modulos)
    module.slot                  ("0/0", namespace de nombres de puerto)

Son namespaces distintos y este repositorio no tiene ningun mapeo gobernado
entre ellos, asi que la igualdad no podia cumplirse nunca.

Que se afirma ahora, y que no:

    MUTATION_SUBMISSION       APPLIED, nada mas
    REQUESTED_INSERTION_SLOT  intencion de mutacion, nada mas
    MODULE_PORT_EFFECT        VERIFIED solo desde evidencia antes/despues fresca,
                              completa, causada por esta transaccion
    EXACT_MODULE_IDENTITY     UNOBSERVABLE
    EXACT_MODULE_PLACEMENT    UNOBSERVABLE

No se emite ni se insinua SLOT_VERIFIED en ningun lado.

Como estan hechos estos tests. Ninguno asigna el veredicto a mano: se conduce el
runtime de produccion real contra un transporte que reproduce la carga exacta
que devolvio PT, y el veredicto lo deriva `PhysicalModuleObservation` con la
misma logica que corre en vivo. Perturbar un test significa perturbar una
ENTRADA de evidencia (inventario de puertos, frescura, propiedad de la
transaccion), nunca la conclusion.

Las filas 12 y 13 del contrato -- la limpieza corre tras un fallo de efecto de
modulo, y nunca borra objetos ajenos -- viven en
`test_e95_serial_physical_product_slice.py`, donde ya existen el doble y el caso
de uso de limpieza; duplicarlos aqui no agregaria evidencia.
"""

from __future__ import annotations

import json

import pytest

from src.packet_tracer_mcp.application.use_cases.deploy_enterprise_topology import (
    EnterprisePhysicalTopologyDeployer,
)
from src.packet_tracer_mcp.domain.enterprise.models.evidence import (
    EvidenceFreshness,
    ObservationStatus,
    SupportStatus,
    VerificationStatus,
)
from src.packet_tracer_mcp.domain.enterprise.models.execution import MutationDisposition
from src.packet_tracer_mcp.domain.models.plans import DevicePlan, ModulePlan
from src.packet_tracer_mcp.infrastructure.execution.packet_tracer_physical_runtime import (
    PacketTracerPhysicalTopologyRuntime,
)

DEVICE = "MCP-PROBE-TDMS-R1"
GIGABIT = ["GigabitEthernet0/0", "GigabitEthernet0/1", "GigabitEthernet0/2"]
SERIAL = ["Serial0/0/0", "Serial0/0/1"]

#: La unica entrada que PT 9.0.1.0858 reporto para un 2911 tras insertar HWIC-2T:
#: el modulo onboard, con sus tres puertos Gigabit y sin identidad legible.
ONBOARD_MODULE_ENTRY = {
    "observed_module_number": "0",
    "slot_type_code": "18",
    "port_count": 3,
    "observed_module_identity": "",
    "identity_observable": False,
}


class _PacketTracerModuleTransport:
    """Reproduce la respuesta medida de PT para `getRootModule` y `addModule`.

    Las perillas son entradas de evidencia, no conclusiones: que puertos existen
    antes, que puertos agrega realmente la insercion, si el arbol de modulos se
    puede leer, y que dice ese arbol.
    """

    def __init__(
        self,
        *,
        ports: list[str] | None = None,
        ports_added_by_insertion: list[str] | None = None,
        modules_observed: bool = True,
        module_entries: list[dict] | None = None,
        readback_malformed: bool = False,
    ) -> None:
        self.ports = list(ports if ports is not None else GIGABIT)
        self.ports_added_by_insertion = list(
            ports_added_by_insertion if ports_added_by_insertion is not None else SERIAL
        )
        self.modules_observed = modules_observed
        self.module_entries = (
            list(module_entries) if module_entries is not None else [ONBOARD_MODULE_ENTRY]
        )
        self.readback_malformed = readback_malformed
        self.module_mutations = 0
        self.mutation_reply: str | None = (
            '{"ack":true,"changed":true,"outcome":"mutation_accepted",'
            '"identity_status":"unobservable"}'
        )

    def __call__(self, script: str, _timeout: float) -> str | None:
        if "addModule(" in script:
            self.module_mutations += 1
            self.ports = sorted({*self.ports, *self.ports_added_by_insertion})
            return self.mutation_reply
        if "getRootModule" in script:
            if self.readback_malformed:
                return "not json at all"
            return json.dumps({
                "found": True,
                "name": DEVICE,
                "model": "2911",
                "ports": self.ports,
                "modules_observed": self.modules_observed,
                "modules": self.module_entries,
            })
        raise AssertionError(f"unexpected script: {script}")


def _module() -> ModulePlan:
    return ModulePlan(device=DEVICE, slot="0/0", module="HWIC-2T")


def _device() -> DevicePlan:
    return DevicePlan(id="r1", name=DEVICE, model="2911", category="router")


def _owned_runtime(transport) -> PacketTracerPhysicalTopologyRuntime:
    """Un runtime que ya es dueno del dispositivo, como tras crearlo el mismo."""
    runtime = PacketTracerPhysicalTopologyRuntime(transport)
    runtime._owned_new_devices.add(DEVICE)
    return runtime


def _insert(transport) -> tuple[PacketTracerPhysicalTopologyRuntime, object]:
    """Inserta el modulo por el camino real y devuelve la observacion real."""
    runtime = _owned_runtime(transport)
    runtime.ensure_module(_module())
    return runtime, runtime.observe_module_effect(_module())


def _deployer_verdict(runtime, observation=None) -> tuple[object, str]:
    """Pasa la observacion por la puerta de despliegue de produccion."""
    capability = runtime.module_effect_capability(_module(), _device())

    class _Fixed:
        def observe_module_effect(self, _module):
            return observation if observation is not None else runtime.observe_module_effect(_module)

    return EnterprisePhysicalTopologyDeployer(_Fixed())._observe_module_effect(
        _module(), capability,
    )


# --------------------------------------------------------------------------
# Filas 1 y 2 -- el numero del arbol de modulos no es una ubicacion
# --------------------------------------------------------------------------

class TestRow1TheObservedModuleNumberNeverEstablishesPlacement:
    def test_the_requested_slot_and_the_observed_number_stay_separate(self):
        _, observation = _insert(_PacketTracerModuleTransport())

        assert observation.requested_slot == "0/0"
        assert [i.observed_module_number for i in observation.slot_observations] == ["0"]
        assert observation.placement_observation_status is ObservationStatus.UNOBSERVABLE

    def test_no_field_ever_reports_a_verified_slot(self):
        """Ni el volcado del manifiesto puede insinuar SLOT_VERIFIED."""
        _, observation = _insert(_PacketTracerModuleTransport())
        dumped = json.dumps(observation.model_dump(mode="json")).casefold()

        assert "slot_verified" not in dumped
        assert observation.model_dump(mode="json")["placement_observation_status"] == (
            "unobservable"
        )


class TestRow2TheOnboardModuleDoesNotSatisfyTheInsertedOne:
    def test_the_onboard_entry_with_its_gigabit_ports_proves_no_placement(self):
        """El HWIC nunca aparece en el arbol; emparejar contra `0` seria mentir."""
        _, observation = _insert(_PacketTracerModuleTransport())

        assert len(observation.slot_observations) == 1
        only = observation.slot_observations[0]
        assert only.port_count == 3
        assert only.identity_observable is False
        assert observation.placement_observation_status is ObservationStatus.UNOBSERVABLE
        assert observation.identity_observation_status is ObservationStatus.UNOBSERVABLE


# --------------------------------------------------------------------------
# Fila 3 -- el efecto de puerto SI puede verificarse
# --------------------------------------------------------------------------

class TestRow3AFreshCompleteNewlyCausedPortEffectIsVerifiable:
    def test_the_measured_live_shape_verifies_the_port_effect(self):
        transport = _PacketTracerModuleTransport()
        _, observation = _insert(transport)

        assert set(observation.ports_before).isdisjoint(SERIAL)
        assert set(SERIAL).issubset(observation.ports_after)
        assert observation.added_ports == SERIAL
        assert observation.effect_newly_caused is True
        assert observation.effect_verification_status is VerificationStatus.VERIFIED

    def test_the_deployment_gate_accepts_the_measured_live_shape(self):
        """La corrida MEG-4 murio aqui con `did not converge`. Ya no debe."""
        runtime, observation = _insert(_PacketTracerModuleTransport())

        returned, error = _deployer_verdict(runtime, observation)

        assert error == ""
        assert returned is observation

    def test_the_expected_effect_comes_from_the_catalogue_not_from_the_test(self):
        runtime = _owned_runtime(_PacketTracerModuleTransport())
        capability = runtime.module_effect_capability(_module(), _device())

        assert capability.effect_observation_support is SupportStatus.SUPPORTED
        assert capability.expected_ports == SERIAL
        assert capability.identity_observation_status is ObservationStatus.UNOBSERVABLE


# --------------------------------------------------------------------------
# Fila 4 -- lo que ya estaba no lo causo esta transaccion
# --------------------------------------------------------------------------

class TestRow4PreexistingExpectedPortsAreNotANewlyCausedEffect:
    def test_ports_present_before_the_mutation_never_verify_the_effect(self):
        transport = _PacketTracerModuleTransport(ports=[*GIGABIT, *SERIAL])
        runtime = _owned_runtime(transport)

        mutation = runtime.ensure_module(_module())
        observation = runtime.observe_module_effect(_module())

        assert mutation.disposition is MutationDisposition.NO_OP
        assert transport.module_mutations == 0
        assert observation.effect_observed is True
        assert observation.effect_newly_caused is False
        assert observation.effect_verification_status is VerificationStatus.FAILED

    def test_the_deployment_gate_refuses_a_preexisting_effect(self):
        transport = _PacketTracerModuleTransport(ports=[*GIGABIT, *SERIAL])
        runtime = _owned_runtime(transport)
        runtime.ensure_module(_module())
        observation = runtime.observe_module_effect(_module())

        _, error = _deployer_verdict(runtime, observation)

        assert "port effect" in error.casefold()
        assert "verified" in error.casefold()

    def test_a_device_this_transaction_does_not_own_never_verifies(self):
        """Sin propiedad no hay causa: el efecto podria ser de cualquiera."""
        transport = _PacketTracerModuleTransport()
        owned = _owned_runtime(transport)
        owned.ensure_module(_module())

        foreign = PacketTracerPhysicalTopologyRuntime(transport)
        foreign._module_baselines.update(owned._module_baselines)
        observation = foreign.observe_module_effect(_module())

        assert observation.device_newly_owned is False
        assert observation.effect_verification_status is VerificationStatus.FAILED


# --------------------------------------------------------------------------
# Filas 5, 6 y 7 -- todo lo incompleto cierra
# --------------------------------------------------------------------------

class TestRow5PartialAppearanceFailsClosed:
    def test_only_one_of_the_two_expected_serial_ports_fails_closed(self):
        transport = _PacketTracerModuleTransport(ports_added_by_insertion=[SERIAL[0]])
        runtime, observation = _insert(transport)

        assert observation.added_ports == [SERIAL[0]]
        assert observation.effect_newly_caused is False
        assert observation.effect_verification_status is VerificationStatus.FAILED

        _, error = _deployer_verdict(runtime, observation)
        assert error != ""


class TestRow6StaleEvidenceFailsClosed:
    def test_a_stale_observation_is_never_verified(self):
        """La frescura es una ENTRADA; el veredicto se recalcula solo."""
        runtime, fresh = _insert(_PacketTracerModuleTransport())
        stale = fresh.model_copy(update={"freshness": EvidenceFreshness.STALE})

        assert fresh.effect_verification_status is VerificationStatus.VERIFIED
        assert stale.effect_verification_status is VerificationStatus.UNVERIFIED

        _, error = _deployer_verdict(runtime, stale)
        assert "stale" in error.casefold()


class TestRow7IncompleteOrAmbiguousEvidenceFailsClosed:
    def test_an_unreadable_port_inventory_is_never_verified(self):
        transport = _PacketTracerModuleTransport()
        runtime = _owned_runtime(transport)
        runtime.ensure_module(_module())
        transport.readback_malformed = True

        observation = runtime.observe_module_effect(_module())

        assert observation.observed is False
        assert observation.port_inventory_observed is False
        assert observation.effect_verification_status is VerificationStatus.UNVERIFIED

        _, error = _deployer_verdict(runtime, observation)
        assert error != ""

    def test_an_ambiguous_superset_in_the_requested_slot_fails_closed(self):
        """Un puerto extra en `0/0` es ambiguedad, no exito con propina."""
        transport = _PacketTracerModuleTransport(
            ports_added_by_insertion=[*SERIAL, "Serial0/0/2"],
        )
        runtime, observation = _insert(transport)

        assert observation.effect_observed is False
        assert observation.effect_verification_status is VerificationStatus.FAILED

        _, error = _deployer_verdict(runtime, observation)
        assert error != ""

    def test_a_missing_module_tree_does_not_by_itself_refuse_the_port_effect(self):
        """Cambio deliberado de la rama B, escrito para que se vea.

        Antes la puerta exigia leer el arbol de modulos -- para correr sobre el
        una comparacion invalida. El veredicto ya no lee nada del arbol, asi que
        exigirlo seria pedir evidencia que no se usa. El arbol se sigue
        registrando como evidencia cruda, y la UBICACION sigue UNOBSERVABLE.
        """
        transport = _PacketTracerModuleTransport(modules_observed=False, module_entries=[])
        runtime, observation = _insert(transport)

        assert observation.module_tree_observed is False
        assert observation.slot_observations == []
        assert observation.effect_verification_status is VerificationStatus.VERIFIED
        assert observation.placement_observation_status is ObservationStatus.UNOBSERVABLE

        _, error = _deployer_verdict(runtime, observation)
        assert error == ""


# --------------------------------------------------------------------------
# Filas 8 y 9 -- el efecto verificado no asciende nada mas
# --------------------------------------------------------------------------

class TestRow8AVerifiedEffectNeverPromotesIdentity:
    def test_the_measured_shape_keeps_identity_unobservable(self):
        _, observation = _insert(_PacketTracerModuleTransport())

        assert observation.effect_verification_status is VerificationStatus.VERIFIED
        assert observation.identity_observation_status is ObservationStatus.UNOBSERVABLE
        assert observation.observed_module_identity == ""

    def test_a_tree_entry_numbered_like_the_slot_still_proves_no_identity(self):
        """Aunque el arbol dijera `0/0` y nombrara el modulo, no seria atribucion.

        Que los dos namespaces coincidan por accidente no crea el mapeo
        gobernado que falta. Antes esto SI ascendia la identidad.
        """
        transport = _PacketTracerModuleTransport(module_entries=[{
            "observed_module_number": "0/0",
            "slot_type_code": "18",
            "port_count": 2,
            "observed_module_identity": "HWIC-2T",
            "identity_observable": True,
        }])
        _, observation = _insert(transport)

        assert observation.slot_observations[0].observed_module_identity == "HWIC-2T"
        assert observation.identity_observation_status is ObservationStatus.UNOBSERVABLE
        assert observation.observed_module_identity == ""


class TestRow9AVerifiedEffectNeverPromotesPlacement:
    @pytest.mark.parametrize("number", ["0", "0/0", "1"])
    def test_no_module_tree_number_ever_makes_placement_observed(self, number):
        transport = _PacketTracerModuleTransport(module_entries=[{
            **ONBOARD_MODULE_ENTRY,
            "observed_module_number": number,
        }])
        _, observation = _insert(transport)

        assert observation.effect_verification_status is VerificationStatus.VERIFIED
        assert observation.placement_observation_status is ObservationStatus.UNOBSERVABLE


# --------------------------------------------------------------------------
# Filas 10 y 11 -- la contencion de replay no se toca
# --------------------------------------------------------------------------

class TestRow10ReplayContainmentIsUnchanged:
    def test_a_second_ensure_is_a_no_op_without_a_second_native_mutation(self):
        transport = _PacketTracerModuleTransport()
        runtime = _owned_runtime(transport)

        first = runtime.ensure_module(_module())
        second = runtime.ensure_module(_module())

        assert first.disposition is MutationDisposition.CHANGED
        assert second.disposition is MutationDisposition.NO_OP
        assert transport.module_mutations == 1

    def test_an_ambiguous_receipt_is_never_replayed(self):
        transport = _PacketTracerModuleTransport()
        transport.mutation_reply = None
        runtime = _owned_runtime(transport)

        mutation = runtime.ensure_module(_module())

        assert mutation.disposition is MutationDisposition.UNKNOWN
        assert "will not be replayed" in mutation.message
        assert transport.module_mutations == 1

    def test_a_partial_preexisting_effect_refuses_to_overwrite(self):
        transport = _PacketTracerModuleTransport(ports=[*GIGABIT, SERIAL[0]])
        runtime = _owned_runtime(transport)

        mutation = runtime.ensure_module(_module())

        assert mutation.disposition is MutationDisposition.FAILED
        assert "partial" in mutation.message.casefold()
        assert transport.module_mutations == 0

    def test_insertion_still_requires_an_owned_new_device(self):
        transport = _PacketTracerModuleTransport()
        runtime = PacketTracerPhysicalTopologyRuntime(transport)

        mutation = runtime.ensure_module(_module())

        assert mutation.disposition is MutationDisposition.FAILED
        assert "not independently proven" in mutation.message
        assert transport.module_mutations == 0


class TestRow11DuplicateEvaluationCausesNoFurtherMutation:
    def test_observing_the_effect_many_times_never_mutates(self):
        transport = _PacketTracerModuleTransport()
        runtime = _owned_runtime(transport)
        runtime.ensure_module(_module())

        verdicts = [
            runtime.observe_module_effect(_module()).effect_verification_status
            for _ in range(3)
        ]

        assert transport.module_mutations == 1
        assert verdicts == [VerificationStatus.VERIFIED] * 3


# --------------------------------------------------------------------------
# El efecto aceptado tiene que ser el declarado COMPLETO, ni mas ni menos
# --------------------------------------------------------------------------

class TestTheCausedEffectMustBeExactlyTheDeclaredOne:
    """Auditoria posterior: `expected <= added` no alcanza como causacion.

    Que aparezcan los puertos esperados no dice que la mutacion haya hecho SOLO
    eso. Si la insercion produjo ademas un efecto de modulo relevante que nadie
    pidio, lo que ocurrio no es el efecto declarado, y atribuirle el resultado a
    la mutacion pedida seria una lectura optimista de evidencia ambigua.

    "Relevante" son los puertos de las mismas clases que el modulo declara
    agregar. Un puerto de otra clase que aparezca por su cuenta no es efecto
    plausible de un HWIC serial, y exigir que tampoco aparezca seria inventar
    una dimension que no se midio.
    """

    def test_an_unexpected_extra_serial_port_is_not_the_declared_effect(self):
        """El hueco medido: antes esto verificaba."""
        transport = _PacketTracerModuleTransport(
            ports_added_by_insertion=[*SERIAL, "Serial0/1/0"],
        )
        runtime, observation = _insert(transport)

        assert observation.added_ports == [*SERIAL, "Serial0/1/0"]
        # El efecto en el slot pedido es exacto...
        assert observation.effect_observed is True
        # ...pero la mutacion causo mas de lo declarado.
        assert observation.effect_newly_caused is False
        assert observation.effect_verification_status is VerificationStatus.FAILED

        _, error = _deployer_verdict(runtime, observation)
        assert error != ""

    def test_an_incidental_port_of_another_class_does_not_fail_the_effect(self):
        """El limite del criterio, fijado para que no se ensanche solo."""
        transport = _PacketTracerModuleTransport(
            ports_added_by_insertion=[*SERIAL, "GigabitEthernet0/3"],
        )
        runtime, observation = _insert(transport)

        assert "GigabitEthernet0/3" in observation.added_ports
        assert observation.newly_added_relevant_ports == SERIAL
        assert observation.effect_newly_caused is True
        assert observation.effect_verification_status is VerificationStatus.VERIFIED

        _, error = _deployer_verdict(runtime, observation)
        assert error == ""

    def test_a_missing_expected_port_is_still_not_the_declared_effect(self):
        transport = _PacketTracerModuleTransport(ports_added_by_insertion=[SERIAL[0]])
        _, observation = _insert(transport)

        assert observation.newly_added_relevant_ports == [SERIAL[0]]
        assert observation.effect_newly_caused is False

    def test_relevance_is_read_from_the_expected_ports_themselves(self):
        """Vaciar `expected_port_classes` no debe poder ablandar el criterio.

        Si la relevancia se leyera de ese campo, un doble podria borrarlo y
        conseguir que ningun puerto extra contara como relevante.
        """
        transport = _PacketTracerModuleTransport(
            ports_added_by_insertion=[*SERIAL, "Serial0/1/0"],
        )
        _, observation = _insert(transport)
        blanked = observation.model_copy(update={"expected_port_classes": []})

        assert blanked.newly_added_relevant_ports == [*SERIAL, "Serial0/1/0"]
        assert blanked.effect_newly_caused is False


# --------------------------------------------------------------------------
# El veredicto no se puede declarar, y esa es la parte estructural
# --------------------------------------------------------------------------

class TestTheVerdictCannotBeAsserted:
    """Lo que hizo invisible el defecto anterior fue un doble que lo afirmaba.

    `slot_effect_observed=True` escrito a mano en un doble bastaba para que
    ninguna regresion ejerciera la derivacion real. El veredicto ahora es un
    campo calculado: no hay forma de escribirlo, ni desde produccion ni desde
    un test, sin aportar la evidencia que lo gana.
    """

    def test_assigning_the_verification_status_is_impossible(self):
        _, observation = _insert(_PacketTracerModuleTransport())

        with pytest.raises(AttributeError, match="no setter"):
            observation.effect_verification_status = VerificationStatus.VERIFIED

        with pytest.raises(AttributeError, match="no setter"):
            observation.effect_newly_caused = True

    def test_the_ambiguous_flag_is_gone_from_the_tree(self):
        """`slot_effect_observed` no debe volver ni con otro nombre igual de vago."""
        import pathlib

        root = pathlib.Path(__file__).resolve().parents[1]
        offenders = [
            path.relative_to(root).as_posix()
            for folder in ("src", "tests")
            for path in (root / folder).rglob("*.py")
            if path != pathlib.Path(__file__).resolve()
            and "slot_effect_observed" in path.read_text(encoding="utf-8")
        ]

        assert offenders == []
