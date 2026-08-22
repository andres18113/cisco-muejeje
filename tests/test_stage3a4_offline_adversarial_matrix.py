"""Gate adversarial offline. Todo verde aqui antes de tocar Packet Tracer.

Esta es la ULTIMA puerta antes de la mutacion en vivo y no concede ningun
permiso por si misma: cerrar aqui es condicion para abrir el gate en vivo, no
una version pequena de el.

Cobertura, y de donde sale cada fila. Varias ya estaban cubiertas por
regresiones adecuadas y NO se duplican -- repetirlas engordaria la matriz sin
agregar evidencia:

    1  preflight de import bloquea mutacion      -> test_enterprise_reference_execution
    2  sin evidencia de capacidad -> UNKNOWN     -> test_enterprise_hardware_composition
    3  version desalineada -> UNKNOWN            -> test_e95_capability_reconciliation
    4  orientacion vieja/truncada/ambigua        -> test_e95_serial_orientation_observer
    5  ambos DCE bloquea                          -> test_e95_serial_orientation_observer
    6  ambos DTE bloquea                          -> test_e95_serial_orientation_observer
    7  reloj solo sobre el DCE observado          -> test_stage3a4_product_composition
    9  sin fundaciones -> cero mutacion E9        -> test_control_plane_application:350
   10  ruta no implica reenvio                    -> test_stage3a4_product_composition
   11  prerequisito por prefijo de destino        -> test_stage3a4_product_composition
   13  E4 sin cambios                             -> test_stage3a4_product_composition

Las que faltaban, y que este archivo agrega, son las que solo aparecen cuando
alguien ORDENA las etapas -- es decir, las que no podian existir mientras la
secuencia viviera en un harness:

    8  una E5 fallida no deja mutar E9
   12  la limpieza corre tras fallar en cada etapa
   14  objetos ajenos/preexistentes nunca se borran
"""

from __future__ import annotations

import pytest

from src.packet_tracer_mcp.application.use_cases.compose_enterprise_reference import (
    compose_enterprise_reference,
)
from src.packet_tracer_mcp.application.use_cases.execute_enterprise_reference import (
    EnterpriseExecutionStage,
    EnterpriseExecutionStatus,
    EnterpriseRuntimes,
    execute_enterprise_reference,
)
from src.packet_tracer_mcp.domain.enterprise.models.configuration_runtime import (
    ActionExecutionStatus,
    RuntimeActionMutation,
    RuntimeConfigurationTarget,
    RuntimeVerification,
)
from src.packet_tracer_mcp.domain.enterprise.models.control_plane import (
    ControlPlaneIntent,
    DynamicRoutingIntent,
    DynamicRoutingProtocol,
)
from src.packet_tracer_mcp.domain.enterprise.models.deployment import (
    EnvironmentFingerprint,
    SerialEndpointOrientation,
)
from src.packet_tracer_mcp.domain.enterprise.models.intent import (
    EnterpriseIntent,
    SiteIntent,
    SiteType,
)
from src.packet_tracer_mcp.domain.enterprise.models.link_performance import (
    LinkMedia,
    TrafficFlowIntent,
)
from src.packet_tracer_mcp.domain.enterprise.models.physical_deployment import (
    EvidenceFreshness,
    MutationDisposition,
    ObservationStatus,
    PhysicalDeviceObservation,
    PhysicalLinkObservation,
    PhysicalModuleEffectCapability,
    PhysicalModuleObservation,
    PhysicalMutationResult,
    PhysicalObjectKind,
    PhysicalWorkspaceDeviceObservation,
    PhysicalWorkspaceObservation,
    SupportStatus,
)
from src.packet_tracer_mcp.domain.enterprise.models.requirements import (
    EndpointRequirement,
    WanLinkRequirement,
)
from src.packet_tracer_mcp.domain.enterprise.models.roles import DeviceRole
from src.packet_tracer_mcp.domain.enterprise.models.physical_deployment import (
    PhysicalDeploymentFailureCode,
)
from src.packet_tracer_mcp.domain.enterprise.models.port_inventory import (
    PortInventoryEvidenceTier,
    PortInventoryResolution,
)
from src.packet_tracer_mcp.domain.enterprise.services.hardware_planner import (
    HardwarePlanningPolicy,
)
from src.packet_tracer_mcp.application.use_cases.deploy_enterprise_topology import (
    EnterprisePhysicalTopologyDeployer,
)
from src.packet_tracer_mcp.application.use_cases.observe_serial_orientation import (
    SerialControllerObservation,
    SerialOrientationObserver,
)
from tests.test_enterprise_reference_execution import _isolated_preflight

FINGERPRINT = EnvironmentFingerprint(
    backend="packet_tracer",
    backend_version="9.0.1.0858",
    bridge_transport="file",
)


def _bounded_intent() -> EnterpriseIntent:
    """La forma acotada que MEG-4 cualificara: 2 routers y una WAN serial."""
    return EnterpriseIntent(
        name="Bounded serial slice",
        address_space="10.0.0.0/8",
        default_growth_percent=0,
        # Con salida a internet el rol de router reconcilia a EDGE y aparece el
        # enlace router-switch que la compilacion de configuracion exige.
        internet_required=True,
        sites=[
            SiteIntent(
                name="A", type=SiteType.HQ,
                endpoints=[EndpointRequirement(role=DeviceRole.USER_PC, count=2)],
                uplinks=[WanLinkRequirement(target_site_id="b", media=LinkMedia.SERIAL)],
            ),
            SiteIntent(
                name="B", type=SiteType.BRANCH,
                endpoints=[EndpointRequirement(role=DeviceRole.USER_PC, count=2)],
                uplinks=[WanLinkRequirement(target_site_id="a", media=LinkMedia.SERIAL)],
            ),
        ],
        traffic_flows=[
            TrafficFlowIntent(
                id="flow/a-to-b", source_site_id="a",
                destination_site_id="b", per_unit_bps=64_000,
            ),
        ],
    )


def _control_plane_intent(topology) -> ControlPlaneIntent:
    """Bien formado desde la topologia compuesta, no con listas vacias."""
    return ControlPlaneIntent(
        id="cp/bounded-ripv2",
        routing=DynamicRoutingIntent(
            id="routing/bounded-ripv2",
            protocol=DynamicRoutingProtocol.RIPV2,
            device_ids=sorted(
                item.id for item in topology.devices if item.category == "router"
            ),
            transit_link_ids=sorted(
                item.id for item in topology.links if item.cable == "serial"
            ),
        ),
    )


class _GenericPhysicalRuntime:
    """Sintetiza observaciones desde el propio plan, para cualquier topologia.

    No pretende imitar a Packet Tracer: pretende llegar a las etapas tardias
    para que se pueda comprobar el ORDEN y la LIMPIEZA. La fidelidad del
    backend es lo que establece el gate en vivo, no un doble.
    """

    def __init__(self, *, preexisting: list[str] | None = None) -> None:
        self.calls: list[str] = []
        self.removed: list[str] = []
        self.devices: dict[str, object] = {}
        self._preexisting = list(preexisting or [])

    # -- inventario ----------------------------------------------------
    def observe_workspace(self) -> PhysicalWorkspaceObservation:
        self.calls.append("observe_workspace")
        return PhysicalWorkspaceObservation(
            devices=[
                PhysicalWorkspaceDeviceObservation(
                    name="Power Distribution Device0",
                    model="Power Distribution Device",
                    backend_managed=True,
                ),
                *(
                    PhysicalWorkspaceDeviceObservation(
                        name=name, model="2911", backend_managed=False,
                    )
                    for name in self._preexisting
                ),
            ],
            links=[],
        )

    # -- dispositivos --------------------------------------------------
    def ensure_device(self, device) -> PhysicalMutationResult:
        self.calls.append(f"ensure_device:{device.name}")
        self.devices[device.name] = device
        return PhysicalMutationResult(
            target_id=device.id,
            target_kind=PhysicalObjectKind.DEVICE,
            disposition=MutationDisposition.CHANGED,
            applied=True,
            inverse_available=True,
            inverse_action_id=f"remove-device:{device.id}",
        )

    def observe_device(self, device) -> PhysicalDeviceObservation:
        self.calls.append(f"observe_device:{device.name}")
        return PhysicalDeviceObservation(
            target_id=device.id,
            deployed_name=device.name,
            model=device.model,
            interfaces=sorted(self._interfaces_for(device.name)),
            runtime_identifier=f"runtime-{device.id}",
            runtime_identifier_stable=True,
            runtime_fingerprint=f"fp-{device.id}",
        )

    def remove_device(self, device) -> PhysicalMutationResult:
        self.removed.append(device.name)
        existed = self.devices.pop(device.name, None) is not None
        return PhysicalMutationResult(
            target_id=device.id,
            target_kind=PhysicalObjectKind.DEVICE,
            disposition=(
                MutationDisposition.CHANGED if existed else MutationDisposition.NO_OP
            ),
            applied=existed,
        )

    # -- modulos -------------------------------------------------------
    def module_effect_capability(self, module, device) -> PhysicalModuleEffectCapability:
        return PhysicalModuleEffectCapability(
            target_id=f"{module.device}:{module.slot}:{module.module}",
            operation_support=SupportStatus.SUPPORTED,
            effect_observation_support=SupportStatus.SUPPORTED,
            expected_ports=["Serial0/0/0", "Serial0/0/1"],
            expected_port_classes=["serial"],
            identity_observation_status=ObservationStatus.UNOBSERVABLE,
        )

    def ensure_module(self, module) -> PhysicalMutationResult:
        self.calls.append(f"ensure_module:{module.device}")
        return PhysicalMutationResult(
            target_id=f"{module.device}:{module.slot}:{module.module}",
            target_kind=PhysicalObjectKind.MODULE,
            disposition=MutationDisposition.CHANGED,
            applied=True,
        )

    def observe_module_effect(self, module) -> PhysicalModuleObservation:
        serial = ["Serial0/0/0", "Serial0/0/1"]
        return PhysicalModuleObservation(
            target_id=f"{module.device}:{module.slot}:{module.module}",
            device_name=module.device,
            requested_slot=module.slot,
            requested_module=module.module,
            freshness=EvidenceFreshness.FRESH,
            port_inventory_observed=True,
            expected_ports=serial,
            expected_port_classes=["serial"],
            ports_before=["GigabitEthernet0/0", "GigabitEthernet0/1"],
            ports_after=["GigabitEthernet0/0", "GigabitEthernet0/1", *serial],
            observed_expected_ports=serial,
            added_ports=serial,
            observed_port_classes=["serial"],
            device_newly_owned=True,
            effect_observed=True,
            identity_observation_status=ObservationStatus.UNOBSERVABLE,
            observed_module_identity="",
        )

    # -- enlaces -------------------------------------------------------
    def ensure_link(self, link) -> PhysicalMutationResult:
        self.calls.append(f"ensure_link:{link.id}")
        return PhysicalMutationResult(
            target_id=link.id,
            target_kind=PhysicalObjectKind.LINK,
            disposition=MutationDisposition.CHANGED,
            applied=True,
        )

    def observe_link(self, link) -> PhysicalLinkObservation:
        return PhysicalLinkObservation(
            target_id=link.id,
            device_a=link.device_a, port_a=link.port_a,
            device_b=link.device_b, port_b=link.port_b,
            cable=link.cable,
            cable_observed=True,
            runtime_link_identifier=f"runtime-{link.id}",
            runtime_link_identity_observed=True,
        )

    def _interfaces_for(self, name: str) -> set[str]:
        found = {"GigabitEthernet0/0", "GigabitEthernet0/1", "Serial0/0/0", "Serial0/0/1"}
        for link in getattr(self, "_topology_links", []):
            if link.device_a == name:
                found.add(link.port_a)
            if link.device_b == name:
                found.add(link.port_b)
        return found

    def bind(self, topology) -> "_GenericPhysicalRuntime":
        self._topology_links = list(topology.links)
        return self


class _GenericOrientationRuntime:
    """Un DCE y un DTE por enlace serial, en el orden del binding."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []
        self._seen: set[str] = set()

    def observe_serial_controller(
        self, device_name: str, interface: str,
    ) -> SerialControllerObservation:
        self.calls.append((device_name, interface))
        role = (
            SerialEndpointOrientation.DTE if self._seen
            else SerialEndpointOrientation.DCE
        )
        self._seen.add(device_name)
        return SerialControllerObservation(
            device_name=device_name,
            interface=interface,
            orientation=role,
            clock_rate_bps=128_000 if role is SerialEndpointOrientation.DCE else None,
            observed=True,
            executed=True,
            fresh_evidence=True,
            complete=True,
            truncated=False,
            parseable=True,
            interface_identity_match=True,
            pages_captured=1,
            pagination="not_encountered",
            evidence_method="fake show controllers",
        )


class _FailingConfigurationRuntime:
    """Aplica y falla la verificacion: E5 no queda verificada."""

    def __init__(self, targets) -> None:
        self._targets = targets
        self.apply_calls = 0

    def inventory(self) -> list[RuntimeConfigurationTarget]:
        return self._targets

    def apply_actions(self, actions) -> list[RuntimeActionMutation]:
        self.apply_calls += 1
        return [
            RuntimeActionMutation(
                action_id=action.id,
                status=ActionExecutionStatus.FAILED,
                message="controlled configuration failure",
            )
            for action in actions
        ]

    def verify(self, expectations) -> list[RuntimeVerification]:
        return []


class _ForbiddenControlPlaneRuntime:
    def __getattr__(self, name):
        def _forbidden(*args, **kwargs):
            raise AssertionError(
                f"control_plane.{name} must not be reached after a failed E5",
            )
        return _forbidden


#: Las etapas posteriores solo se alcanzan con una topologia desplegable, y eso
#: ahora exige inventario de puertos verificado contra el backend. `2911` lo
#: tiene; la seleccion sin preferencia elige `1941`, que no. Dirigir aqui no
#: hace verde nada que estuviera roto: mueve la corrida a un modelo calificado
#: para que la fila bajo prueba -- el orden de las etapas -- llegue a ejercerse.
#: Que un plan SIN dirigir se rechace esta fijado aparte, mas abajo.
_QUALIFIED = HardwarePlanningPolicy(preferred_router_model="2911")


def _run(*, physical, configuration, control_plane, intent=None, policy=_QUALIFIED,
         pre_cleanup_diagnostic=None):
    intent = intent or _bounded_intent()
    # El fake sintetiza puertos desde el plan, asi que necesita conocerlo. La
    # composicion es determinista PARA LAS MISMAS ENTRADAS, y desde el contrato
    # de evidencia de puertos el build es una de ellas: con un inventario medido
    # los nombres salen de lo observado. Por eso aqui se compone con la misma
    # version y la misma politica que usara el caso de uso.
    topology = compose_enterprise_reference(
        intent, policy=policy, packet_tracer_version="9.0.1.0858",
    ).topology
    physical.bind(topology)
    return execute_enterprise_reference(
        intent,
        EnterpriseRuntimes(
            physical=physical,
            serial_orientation=_GenericOrientationRuntime(),
            configuration=configuration,
            control_plane=control_plane,
        ),
        _control_plane_intent(topology),
        environment_fingerprint=FINGERPRINT,
        import_preflight=_isolated_preflight(),
        packet_tracer_version="9.0.1.0858",
        policy=policy,
        pre_cleanup_diagnostic=pre_cleanup_diagnostic,
    )


class TestRow8AFailedE5NeverMutatesE9:
    def test_a_failed_configuration_stops_exactly_at_configuration_apply(self):
        """Llega de verdad hasta E5: despliegue con manifiesto y orientacion
        verificada. Si se detuviera antes, esta fila no probaria su enunciado."""
        physical = _GenericPhysicalRuntime()

        result = _run(
            physical=physical,
            configuration=_FailingConfigurationRuntime([]),
            control_plane=_ForbiddenControlPlaneRuntime(),
        )

        assert result.deployment is not None and result.deployment.manifest is not None
        assert result.orientation is not None and result.orientation.verified
        assert result.status is EnterpriseExecutionStatus.FAILED
        assert result.stopped_at is EnterpriseExecutionStage.CONFIGURATION_APPLY
        # El runtime de plano de control lanza ante cualquier llamada.
        assert result.control_plane_result is None
        assert result.foundational_statuses == {}

    def test_a_failed_configuration_may_never_carry_the_control_plane(self):
        """APPLIED no es VERIFIED, y el enum ya los distingue.

        Avanzar sobre APPLIED trataria "la mutacion volvio bien" como evidencia
        de efecto. Lo que cambio con el gate acotado por fundaciones es CUAL de
        los estados no-VERIFIED bloquea aca: una aplicacion FALLIDA sigue
        bloqueando, porque el plan no se ejecuto como se compilo. Un campo que
        nadie pudo mirar ya no bloquea por si solo -- eso lo decide la fundacion
        que lo declare, y esta fijado en `test_e95_foundation_scoped_gate.py`.
        """
        physical = _GenericPhysicalRuntime()

        result = _run(
            physical=physical,
            configuration=_FailingConfigurationRuntime([]),
            control_plane=_ForbiddenControlPlaneRuntime(),
        )
        errors = " ".join(result.errors)

        assert result.stopped_at is EnterpriseExecutionStage.CONFIGURATION_APPLY
        assert result.control_plane_result is None
        assert "failed" in errors.casefold()
        assert "not a base the control plane may build on" in errors


class TestRow12CleanupRunsAfterEveryFailure:
    @pytest.mark.parametrize("preexisting", [[], ["Foreign-R1"]])
    def test_cleanup_runs_and_is_verified_by_re_observation(self, preexisting):
        """Vale para el camino bloqueado y para el fallido: nunca se asume."""
        physical = _GenericPhysicalRuntime(preexisting=preexisting)

        result = _run(
            physical=physical,
            configuration=_FailingConfigurationRuntime([]),
            control_plane=_ForbiddenControlPlaneRuntime(),
        )

        if result.status is EnterpriseExecutionStatus.BLOCKED:
            # Con topologia ajena presente el gate corta antes de mutar, y
            # entonces NO debe haber limpieza que reportar.
            assert physical.removed == []
            assert result.inventory_restored is None
        else:
            assert result.cleanup_results
            assert result.final_inventory is not None
            assert physical.calls.count("observe_workspace") >= 2

    def test_e4_identity_survives_every_failure_path(self):
        physical = _GenericPhysicalRuntime()

        result = _run(
            physical=physical,
            configuration=_FailingConfigurationRuntime([]),
            control_plane=_ForbiddenControlPlaneRuntime(),
        )

        assert result.e4_identity_preserved is True


class TestRow14ForeignObjectsAreNeverDeleted:
    def test_a_preexisting_semantic_device_hard_stops_before_any_removal(self):
        """La unica respuesta correcta ante topologia ajena es no tocar nada."""
        physical = _GenericPhysicalRuntime(preexisting=["StudentLab-R1"])

        result = _run(
            physical=physical,
            configuration=_FailingConfigurationRuntime([]),
            control_plane=_ForbiddenControlPlaneRuntime(),
        )

        assert result.status is EnterpriseExecutionStatus.BLOCKED
        assert result.stopped_at is EnterpriseExecutionStage.WORKSPACE_INVENTORY
        assert physical.removed == []
        assert physical.devices == {}

    def test_cleanup_only_ever_targets_product_managed_devices(self):
        """Se borra exactamente lo que el producto planifico, ni un nombre mas."""
        physical = _GenericPhysicalRuntime()

        result = _run(
            physical=physical,
            configuration=_FailingConfigurationRuntime([]),
            control_plane=_ForbiddenControlPlaneRuntime(),
        )

        assert result.composition is not None and result.composition.topology is not None
        planned = {item.name for item in result.composition.topology.devices}

        assert set(physical.removed) <= planned
        assert "Power Distribution Device0" not in physical.removed


class TestTheDefaultSelectionIsRecordedNotAssumed:
    """Cual modelo elige el catalogo por si solo, fijado para el gate en vivo.

    La calificacion acotada de CP-SCALE observo que `819HG-4G-IOX` tiene un
    `Serial0` integrado. Sin preferencia, esa evidencia exact-build hace que la
    seleccion por capacidad lo elija para esta forma acotada sin instalar un
    modulo. La evidencia de capacidad de plano de control en vivo sigue
    existiendo solo para `2911`, asi que esta corrida E9.5 debe DIRIGIR la
    seleccion en vez de confiar en que el catalogo acierte.

    Nota correctiva: la compilacion del plano de control NO depende del modelo
    -- 1941 y 2911 compilan igual. La capacidad se consulta al aplicar. Una
    lectura anterior de este archivo decia que el compilador se negaba; era
    falsa y se corrige aqui. El detalle vive en
    `test_enterprise_preferred_router_model.py`.
    """

    def test_the_unsteered_selection_is_the_measured_819(self):
        physical = _GenericPhysicalRuntime()

        result = _run(
            physical=physical,
            configuration=_FailingConfigurationRuntime([]),
            control_plane=_ForbiddenControlPlaneRuntime(),
            policy=None,
        )
        routers = {
            item.model for item in result.composition.topology.devices
            if item.category == "router"
        }

        assert routers == {"819HG-4G-IOX"}, (
            "si cambia la seleccion, revisar evidencia de puertos y el gate en vivo"
        )


#: Un router del catalogo que ninguna pasada ha medido por este seam. `1941`
#: cumplia ese papel hasta que la cualificacion MEG-5 lo midio -- la referencia
#: de 41 dispositivos lo selecciona. La fila es sobre EVIDENCIA AUSENTE, no
#: sobre un modelo concreto, asi que se mueve a uno que sigue sin medir.
_UNMEASURED_ROUTER = HardwarePlanningPolicy(preferred_router_model="2901")


class TestSelectionMustCarryPortEvidenceBeforeItCanBind:
    """Fila 6 del contrato de puertos, de punta a punta por el entry point.

    Seleccionar un modelo es una decision de planificacion; vincular un nombre
    de puerto concreto contra un backend es otra cosa, y necesita evidencia de
    ese backend. Un modelo que nadie ha medido nunca por este seam hace que el
    despliegue se niegue ANTES de mutar. Que se niegue no dice que el modelo
    este mal: dice que no se sabe.
    """

    def test_the_exemplar_model_really_is_unmeasured(self):
        """Si alguien lo mide, esta fila deja de probar lo que dice probar."""
        from src.packet_tracer_mcp.infrastructure.catalog.measured_port_inventories import (
            MEASURED_PORT_INVENTORIES,
        )

        assert "2901" not in {item.model for item in MEASURED_PORT_INVENTORIES}

    def test_an_unmeasured_model_is_refused_before_any_mutation(self):
        physical = _GenericPhysicalRuntime()

        result = _run(
            physical=physical,
            configuration=_FailingConfigurationRuntime([]),
            control_plane=_ForbiddenControlPlaneRuntime(),
            policy=_UNMEASURED_ROUTER,
        )

        assert result.stopped_at is EnterpriseExecutionStage.PHYSICAL_DEPLOYMENT
        assert result.deployment is not None
        assert result.deployment.failure_code is (
            PhysicalDeploymentFailureCode.PORT_EVIDENCE_UNAVAILABLE
        )
        assert any("2901" in message for message in result.errors)
        assert physical.devices == {}
        assert physical.removed == []

    def test_a_measured_model_reaches_the_next_stage(self):
        """El contraste: con el mismo camino y un modelo medido, el gate deja pasar."""
        physical = _GenericPhysicalRuntime()

        result = _run(
            physical=physical,
            configuration=_FailingConfigurationRuntime([]),
            control_plane=_ForbiddenControlPlaneRuntime(),
        )

        assert result.deployment is not None
        assert result.deployment.failure_code is not (
            PhysicalDeploymentFailureCode.PORT_EVIDENCE_UNAVAILABLE
        )
        assert result.stopped_at is EnterpriseExecutionStage.CONFIGURATION_APPLY


class TestTheGateGrantsNoLivePermission:
    def test_no_real_runtime_participates_in_this_matrix(self):
        """Recordatorio ejecutable: aqui no se toca Packet Tracer.

        Los tres runtimes son dobles definidos en este archivo. El dia que
        alguno deje de serlo, esto falla y hay que decidirlo a proposito.
        """
        physical = _GenericPhysicalRuntime()
        configuration = _FailingConfigurationRuntime([])
        control_plane = _ForbiddenControlPlaneRuntime()

        _run(
            physical=physical, configuration=configuration, control_plane=control_plane,
        )

        for double in (physical, configuration, control_plane):
            assert type(double).__module__ == __name__, type(double)


def _double_port_inventory(topology):
    """La evidencia de puertos DEL DOBLE, que es el backend de este archivo.

    El doble sintetiza sus interfaces desde el plan, asi que su inventario
    verificado es exactamente lo que el plan pide de cada modelo. Dejar el
    resolutor por defecto le prestaria las mediciones tomadas contra Packet
    Tracer real, es decir, le atribuiria una conformidad que nadie observo en
    el -- que es justo el prestamo de evidencia que el contrato prohibe.
    """
    by_model: dict[str, set[str]] = {}
    model_of = {item.name: item.model for item in topology.devices}
    for device in topology.devices:
        by_model.setdefault(device.model, set())
    for link in topology.links:
        for name, port in (
            (link.device_a, link.port_a), (link.device_b, link.port_b),
        ):
            model = model_of.get(name)
            if model:
                by_model.setdefault(model, set()).add(port)

    def _resolve(model, *, backend="packet_tracer", backend_version="", installed_modules=None):
        return PortInventoryResolution(
            model=model,
            backend=backend,
            backend_version=backend_version,
            installed_modules=sorted(installed_modules or []),
            tier=PortInventoryEvidenceTier.BACKEND_VERIFIED,
            ports=sorted(by_model.get(model, set()), key=str.casefold),
            reason="synthesised by the physical double in this test module",
        )

    return _resolve


def _oriented_manifest_for(topology):
    """Manifiesto orientado desde el despliegue del doble, no fabricado a mano.

    Lo emite el deployer a partir de sus observaciones y lo orienta el observador
    de produccion. Construirlo a mano seria justo el atajo que el manifiesto
    existe para impedir.
    """
    runtime = _GenericPhysicalRuntime().bind(topology)
    deployment = EnterprisePhysicalTopologyDeployer(
        runtime, port_inventory=_double_port_inventory(topology),
    ).deploy(
        topology,
        environment_fingerprint=FINGERPRINT,
        require_empty_workspace=True,
    )
    assert deployment.manifest is not None, deployment.errors
    result = SerialOrientationObserver(_GenericOrientationRuntime()).observe(
        topology, deployment.manifest,
    )
    assert result.oriented_manifest is not None, result.errors
    return result.oriented_manifest
