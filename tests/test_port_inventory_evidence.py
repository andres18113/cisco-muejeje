"""Un inventario declarado no es un inventario verificado contra el backend.

Que corrige. La corrida MEG-4 run 2 pidio `FastEthernet0/1` sobre un IE-2000
cuyos puertos Packet Tracer numera `1/x`. El catalogo declaraba `0/x` y ese
nombre viajaba intacto hasta la mutacion, porque nada distinguia "lo que el
catalogo dice que un modelo deberia tener" de "lo que un backend concreto
reporto".

El contrato ahora tiene tres niveles, y solo el de arriba autoriza un binding:

    DECLARED          conocimiento de catalogo. Sirve para planificar.
    BACKEND_VERIFIED  un build concreto reporto este inventario para este
                      modelo en este estado de modulos. Sirve para vincular.
    UNKNOWN           no hay evidencia adecuada. No es permiso.

Alcance de la calificacion, a proposito: solo los modelos que el camino
acotado de Stage 3A4 realmente necesita. Los demas siguen DECLARED/UNKNOWN y
eso es correcto -- este ticket arregla la arquitectura de evidencia, no
certifica el catalogo entero.
"""

from __future__ import annotations

import pytest

from src.packet_tracer_mcp.application.use_cases.deploy_enterprise_topology import (
    EnterprisePhysicalTopologyDeployer,
)
from src.packet_tracer_mcp.domain.enterprise.models.deployment import (
    EnvironmentFingerprint,
)
from src.packet_tracer_mcp.domain.enterprise.models.physical_deployment import (
    PhysicalDeploymentFailureCode,
)
from src.packet_tracer_mcp.domain.enterprise.models.port_inventory import (
    BackendVerifiedPortInventory,
    PortInventoryEvidenceTier,
    resolve_port_inventory,
)
from src.packet_tracer_mcp.domain.models.plans import DevicePlan, LinkPlan, TopologyPlan
from src.packet_tracer_mcp.domain.enterprise.services.topology_identity import (
    compute_topology_hashes,
)
from src.packet_tracer_mcp.infrastructure.catalog.enterprise_capabilities import (
    EnterpriseCapabilityAdapter,
)
from src.packet_tracer_mcp.infrastructure.catalog.measured_port_inventories import (
    MEASURED_BACKEND_VERSION,
    MEASURED_PORT_INVENTORIES,
    backend_verified_port_inventory,
    module_state_token,
)

BUILD = MEASURED_BACKEND_VERSION
OTHER_BUILD = "8.2.2.0400"

#: Lo que el catalogo declara para IE-2000, sin normalizar.
DECLARED_IE2000 = [
    "FastEthernet0/1", "FastEthernet0/2", "FastEthernet0/3", "FastEthernet0/4",
    "FastEthernet0/5", "FastEthernet0/6", "FastEthernet0/7", "FastEthernet0/8",
    "GigabitEthernet0/1", "GigabitEthernet0/2",
]

#: Lo que PT 9.0.1.0858 reporto, sin normalizar.
OBSERVED_IE2000 = [
    "FastEthernet1/1", "FastEthernet1/2", "FastEthernet1/3", "FastEthernet1/4",
    "FastEthernet1/5", "FastEthernet1/6", "FastEthernet1/7", "FastEthernet1/8",
    "GigabitEthernet1/1", "GigabitEthernet1/2", "Vlan1",
]


def _fingerprint(version: str = BUILD) -> EnvironmentFingerprint:
    return EnvironmentFingerprint(
        backend="packet_tracer",
        backend_version=version,
        bridge_transport="file",
        runtime_mode="logical-workspace",
    )


class _RefusesEveryMutation:
    """Cualquier mutacion que llegue aqui es el fallo que el test busca."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def __getattr__(self, name: str):
        def _record(*args, **kwargs):
            self.calls.append(name)
            raise AssertionError(f"the deployer mutated through {name!r} after preflight")
        return _record


def _topology(model: str, ports: list[str]) -> TopologyPlan:
    """Dos dispositivos del mismo modelo unidos por los puertos indicados."""
    plan = TopologyPlan(
        id="compiled/port-evidence",
        name="port-evidence",
        devices=[
            DevicePlan(id="d1", name="D1", model=model, category="switch"),
            DevicePlan(id="d2", name="D2", model=model, category="switch"),
        ],
        links=[LinkPlan(
            id="link/1",
            device_a_id="d1", device_a="D1", port_a=ports[0],
            device_b_id="d2", device_b="D2", port_b=ports[0],
            cable="copper",
        )],
    )
    hashes = compute_topology_hashes(plan)
    plan.physical_topology_hash = hashes.physical_topology_hash
    plan.hash_schema_version = "2"
    return plan


# --------------------------------------------------------------------------
# 1 y 2 -- declarado contra observado
# --------------------------------------------------------------------------

class TestRow1DeclaredDisagreesWithObserved:
    def test_the_two_namespaces_are_reported_without_being_reconciled(self):
        """Se fijan las dos listas tal cual; normalizarlas borraria el hallazgo."""
        resolution = backend_verified_port_inventory("IE-2000", backend_version=BUILD)

        assert resolution.tier is PortInventoryEvidenceTier.BACKEND_VERIFIED
        assert resolution.ports == OBSERVED_IE2000
        assert set(DECLARED_IE2000).isdisjoint(OBSERVED_IE2000)

    def test_a_declared_port_name_is_not_authorised_by_the_measurement(self):
        resolution = backend_verified_port_inventory("IE-2000", backend_version=BUILD)

        assert resolution.permits(["FastEthernet0/1"]) is False
        assert resolution.unsupported_ports(
            ["FastEthernet0/1", "GigabitEthernet0/1"],
        ) == ["FastEthernet0/1", "GigabitEthernet0/1"]


class TestRow2AdequateEvidencePermitsTheBinding:
    def test_the_observed_names_are_authorised(self):
        resolution = backend_verified_port_inventory("IE-2000", backend_version=BUILD)

        assert resolution.permits(["FastEthernet1/1", "GigabitEthernet1/1"]) is True
        assert resolution.unsupported_ports(["FastEthernet1/1"]) == []


# --------------------------------------------------------------------------
# 3 y 4 -- la evidencia no migra
# --------------------------------------------------------------------------

class TestRow3EvidenceNeverMigratesAcrossBuilds:
    def test_the_same_model_on_another_build_is_unknown(self):
        resolution = backend_verified_port_inventory("IE-2000", backend_version=OTHER_BUILD)

        assert resolution.tier is PortInventoryEvidenceTier.UNKNOWN
        assert resolution.ports == []
        assert "never migrates across builds" in resolution.reason
        assert resolution.permits(["FastEthernet1/1"]) is False

    def test_an_empty_build_is_not_a_wildcard(self):
        resolution = backend_verified_port_inventory("IE-2000", backend_version="")

        assert resolution.tier is PortInventoryEvidenceTier.UNKNOWN
        assert resolution.permits(["FastEthernet1/1"]) is False


class TestRow4EvidenceNeverMigratesAcrossModels:
    def test_another_models_evidence_is_not_reused(self):
        resolution = backend_verified_port_inventory("2950T-24", backend_version=BUILD)

        assert resolution.tier is PortInventoryEvidenceTier.UNKNOWN
        assert "No backend-verified port inventory exists" in resolution.reason
        # El IE-2000 tiene evidencia; prestarsela a otro modelo seria inventarla.
        assert resolution.permits(["FastEthernet1/1"]) is False

    def test_module_state_is_part_of_the_scope(self):
        """Un 2911 vacio no hereda la medicion del 2911 con la tarjeta puesta."""
        empty = backend_verified_port_inventory("2911", backend_version=BUILD)
        carded = backend_verified_port_inventory(
            "2911", backend_version=BUILD,
            installed_modules=[module_state_token("HWIC-2T", "0/0")],
        )

        assert empty.tier is PortInventoryEvidenceTier.UNKNOWN
        assert "module state" in empty.reason
        assert carded.tier is PortInventoryEvidenceTier.BACKEND_VERIFIED
        assert carded.permits(["Serial0/0/0", "GigabitEthernet0/0"]) is True


# --------------------------------------------------------------------------
# 5 -- lo declarado no asciende solo
# --------------------------------------------------------------------------

class TestRow5DeclaredOnlyModelsStayDeclared:
    def test_the_reference_switch_has_no_backend_evidence(self):
        """`2960-24TT` es el modelo que fija la topologia de referencia.

        Nunca se corrio por este seam, asi que no tiene evidencia y no debe
        obtenerla por parecerse a los que si la tienen.
        """
        resolution = backend_verified_port_inventory("2960-24TT", backend_version=BUILD)

        assert resolution.tier is PortInventoryEvidenceTier.UNKNOWN
        assert resolution.permits(["FastEthernet0/1"]) is False

    def test_the_declared_catalogue_still_describes_it(self):
        declared = EnterpriseCapabilityAdapter().port_descriptors_for("2960-24TT")

        assert [item.name for item in declared][:2] == [
            "FastEthernet0/1", "FastEthernet0/2",
        ]
        assert {item.source for item in declared} == {"catalog"}


# --------------------------------------------------------------------------
# 6 -- lo seleccionado tiene que traer su evidencia
# --------------------------------------------------------------------------

class TestRow6SelectionMustCarryConcretePortEvidence:
    def test_a_selected_model_with_evidence_plans_the_observed_names(self):
        """IE-2000 se sigue seleccionando; lo que cambia es como se nombra."""
        adapter = EnterpriseCapabilityAdapter()
        verified = adapter.port_descriptors_for("IE-2000", backend_version=BUILD)

        names = [item.name for item in verified]
        assert names[:2] == ["FastEthernet1/1", "FastEthernet1/2"]
        assert "GigabitEthernet1/1" in names
        # La lectura trae `Vlan1`; no es un puerto fisico de planificacion.
        assert "Vlan1" not in names
        assert {item.source for item in verified} == {f"backend_verified:{BUILD}"}

    def test_without_a_build_context_the_declared_names_are_used(self):
        adapter = EnterpriseCapabilityAdapter()
        declared = adapter.port_descriptors_for("IE-2000")

        assert [item.name for item in declared][:2] == [
            "FastEthernet0/1", "FastEthernet0/2",
        ]
        assert {item.source for item in declared} == {"catalog"}


# --------------------------------------------------------------------------
# 7 -- determinismo
# --------------------------------------------------------------------------

class TestRow7ResolutionIsDeterministic:
    def test_repeated_resolution_is_identical(self):
        first = backend_verified_port_inventory("IE-2000", backend_version=BUILD)
        second = backend_verified_port_inventory("IE-2000", backend_version=BUILD)

        assert first.model_dump() == second.model_dump()

    def test_module_state_order_does_not_change_the_result(self):
        a = resolve_port_inventory(
            [BackendVerifiedPortInventory(
                model="X", backend_version=BUILD,
                installed_modules=["m2@0/1", "m1@0/0"], ports=["Serial0/0/0"],
            )],
            "X", backend="packet_tracer", backend_version=BUILD,
            installed_modules=["m1@0/0", "m2@0/1"],
        )
        b = resolve_port_inventory(
            [BackendVerifiedPortInventory(
                model="X", backend_version=BUILD,
                installed_modules=["m1@0/0", "m2@0/1"], ports=["Serial0/0/0"],
            )],
            "X", backend="packet_tracer", backend_version=BUILD,
            installed_modules=["m2@0/1", "m1@0/0"],
        )

        assert a.tier is PortInventoryEvidenceTier.BACKEND_VERIFIED
        assert a.model_dump() == b.model_dump()

    def test_descriptor_order_is_stable(self):
        adapter = EnterpriseCapabilityAdapter()
        runs = [
            [item.name for item in adapter.port_descriptors_for("IE-2000", backend_version=BUILD)]
            for _ in range(3)
        ]

        assert runs[0] == runs[1] == runs[2]


# --------------------------------------------------------------------------
# 8 -- sin excepciones por nombre de modelo
# --------------------------------------------------------------------------

class TestRow8NoModelNameSpecialCase:
    def test_no_planning_or_runtime_module_branches_on_a_model_name(self):
        """El dato medido vive en el catalogo; la logica no lo conoce."""
        import pathlib

        root = pathlib.Path(__file__).resolve().parents[1] / "src" / "packet_tracer_mcp"
        guarded = [
            root / "domain" / "enterprise" / "services" / "hardware_planner.py",
            root / "domain" / "enterprise" / "services" / "device_selector.py",
            root / "domain" / "enterprise" / "services" / "enterprise_designer.py",
            root / "domain" / "enterprise" / "models" / "port_inventory.py",
            root / "application" / "use_cases" / "deploy_enterprise_topology.py",
            root / "infrastructure" / "execution" / "packet_tracer_physical_runtime.py",
        ]
        offenders = [
            path.name for path in guarded
            if any(
                token in path.read_text(encoding="utf-8")
                for token in ("IE-2000", "2960-24TT", "3560-24PS", "2950T-24")
            )
        ]

        assert offenders == []


# --------------------------------------------------------------------------
# 9, 10 y 11 -- el preflight corta antes de tocar nada
# --------------------------------------------------------------------------

class TestRow9PreflightFailureMutatesNothing:
    def test_a_model_without_port_evidence_never_reaches_a_mutation(self):
        runtime = _RefusesEveryMutation()
        topology = _topology("2960-24TT", ["FastEthernet0/1"])

        result = EnterprisePhysicalTopologyDeployer(runtime).deploy(
            topology, environment_fingerprint=_fingerprint(),
        )

        assert result.failure_code is PhysicalDeploymentFailureCode.PORT_EVIDENCE_UNAVAILABLE
        assert runtime.calls == []
        assert result.manifest is None
        assert any("2960-24TT" in message for message in result.errors)

    def test_declared_port_names_on_a_measured_model_are_refused(self):
        """El caso exacto de MEG-4 run 2, ahora detectado sin mutar nada."""
        runtime = _RefusesEveryMutation()
        topology = _topology("IE-2000", ["FastEthernet0/1"])

        result = EnterprisePhysicalTopologyDeployer(runtime).deploy(
            topology, environment_fingerprint=_fingerprint(),
        )

        assert result.failure_code is PhysicalDeploymentFailureCode.PORT_EVIDENCE_UNAVAILABLE
        assert runtime.calls == []
        assert any("FastEthernet0/1" in message for message in result.errors)

    def test_observed_port_names_on_a_measured_model_pass_the_preflight(self):
        runtime = _RefusesEveryMutation()
        topology = _topology("IE-2000", ["FastEthernet1/1"])

        result = EnterprisePhysicalTopologyDeployer(runtime).deploy(
            topology, environment_fingerprint=_fingerprint(),
        )

        # El preflight ya no es el que corta: la mutacion se intento y el doble
        # la rechazo, que es exactamente lo que prueba que paso la puerta.
        assert result.failure_code is not (
            PhysicalDeploymentFailureCode.PORT_EVIDENCE_UNAVAILABLE
        )
        assert runtime.calls != []

    def test_a_mismatched_build_refuses_even_the_observed_names(self):
        runtime = _RefusesEveryMutation()
        topology = _topology("IE-2000", ["FastEthernet1/1"])

        result = EnterprisePhysicalTopologyDeployer(runtime).deploy(
            topology, environment_fingerprint=_fingerprint(OTHER_BUILD),
        )

        assert result.failure_code is PhysicalDeploymentFailureCode.PORT_EVIDENCE_UNAVAILABLE
        assert runtime.calls == []


class TestRow10And11NothingIsRemovedOnAPortEvidenceFailure:
    def test_a_preflight_refusal_leaves_the_workspace_untouched(self):
        """Sin mutacion no hay nada que limpiar, y limpiar igual seria tocar lo ajeno."""
        runtime = _RefusesEveryMutation()
        topology = _topology("2960-24TT", ["FastEthernet0/1"])

        result = EnterprisePhysicalTopologyDeployer(runtime).deploy(
            topology, environment_fingerprint=_fingerprint(),
            require_empty_workspace=True,
        )

        assert result.failure_code is PhysicalDeploymentFailureCode.PORT_EVIDENCE_UNAVAILABLE
        # Ni siquiera se leyo el workspace: el preflight es anterior.
        assert runtime.calls == []


# --------------------------------------------------------------------------
# 12 -- la observacion no reescribe el catalogo universal
# --------------------------------------------------------------------------

class TestRow12TheUniversalCatalogueIsNotRewritten:
    def test_devices_py_still_declares_what_it_always_declared(self):
        """`devices.py` es agnostico del build y sigue diciendo `0/x`.

        Corregirlo desde UNA observacion convertiria una declaracion de
        planificacion en una afirmacion sobre un build concreto, que es
        precisamente la confusion que este contrato existe para deshacer.
        """
        from src.packet_tracer_mcp.infrastructure.catalog.devices import SWITCH_IE2000

        assert [port.full_name for port in SWITCH_IE2000.ports][:2] == [
            "FastEthernet0/1", "FastEthernet0/2",
        ]

    def test_measured_evidence_lives_in_a_build_pinned_module(self):
        assert all(
            record.backend_version == BUILD for record in MEASURED_PORT_INVENTORIES
        )
        assert all(record.source for record in MEASURED_PORT_INVENTORIES)

    def test_only_the_stage_3a4_bounded_models_are_qualified(self):
        """El alcance, fijado. Ampliarlo debe ser una decision, no un descuido."""
        assert sorted({record.model for record in MEASURED_PORT_INVENTORIES}) == [
            "2911", "IE-2000", "PC-PT",
        ]


@pytest.mark.parametrize("model", ["2911", "IE-2000", "PC-PT"])
def test_every_qualified_model_carries_its_provenance(model):
    record = next(item for item in MEASURED_PORT_INVENTORIES if item.model == model)

    assert record.backend == "packet_tracer"
    assert record.backend_version == BUILD
    assert "meg4-run2" in record.source
