"""Stage 3A4 MEG-5 — la pasada que mide inventarios de puertos, y sus negativas.

`_port_evidence_errors` rechaza puertos que ninguna medicion autoriza. Correcto,
y no se relaja. Pero un modelo que la corrida todavia no puede desplegar no
tenia forma de adquirir esa evidencia: el gate lo rechazaba antes. Ese circulo
es lo que bloquea a MEG-5, porque la referencia selecciona `1941` y `2950T-24` y
ninguno esta medido.

`PortInventoryQualifier` lo cierra creando un desechable por par (modelo, estado
de modulo) y releyendolo por el MISMO seam de produccion que usa el despliegue.
Lo que estos tests fijan es lo que se niega a hacer:

* no emite evidencia si la relectura no observo interfaces;
* no emite evidencia de "modelo CON modulo" si la insercion no se aplico;
* no escribe nada: devuelve observaciones, y pinchar es un acto versionado;
* no muta un workspace que no encontro vacio;
* limpia en orden inverso pase lo que pase, y compara restauracion.
"""

from __future__ import annotations

import pytest

from src.packet_tracer_mcp.application.use_cases.qualify_port_inventories import (
    QUALIFICATION_PREFIX,
    PortInventoryQualifier,
    PortInventoryTarget,
)
from src.packet_tracer_mcp.domain.enterprise.models.physical_deployment import (
    MutationDisposition,
    PhysicalDeviceObservation,
    PhysicalMutationResult,
    PhysicalObjectKind,
    PhysicalWorkspaceDeviceObservation,
    PhysicalWorkspaceObservation,
)

_BACKEND = {"backend": "packet_tracer", "backend_version": "9.0.1.0858",
            "source": "test"}


class _Physical:
    """Backend falso con puertos por modelo y por estado de modulo."""

    def __init__(
        self,
        ports_by_state: dict[tuple[str, str], list[str]],
        *,
        create_ok: bool = True,
        module_ok: bool = True,
        interfaces_observed: bool = True,
        preexisting: list[str] | None = None,
        remove_ok: bool = True,
    ) -> None:
        self._ports = dict(ports_by_state)
        self._create_ok = create_ok
        self._module_ok = module_ok
        self._interfaces_observed = interfaces_observed
        self._remove_ok = remove_ok
        self._preexisting = list(preexisting or [])
        self.calls: list[str] = []
        self.live: dict[str, tuple[str, str]] = {}

    def observe_workspace(self) -> PhysicalWorkspaceObservation:
        self.calls.append("observe_workspace")
        return PhysicalWorkspaceObservation(
            observed=True,
            devices=[
                PhysicalWorkspaceDeviceObservation(name=name, model="X")
                for name in [*self._preexisting, *self.live]
            ],
            links=[],
            message="fake",
        )

    def ensure_device(self, device) -> PhysicalMutationResult:
        self.calls.append(f"ensure_device:{device.name}")
        if self._create_ok:
            self.live[device.name] = (device.model, "")
        return PhysicalMutationResult(
            target_id=device.id, target_kind=PhysicalObjectKind.DEVICE,
            disposition=(
                MutationDisposition.CHANGED if self._create_ok
                else MutationDisposition.FAILED
            ),
            applied=self._create_ok,
            message="" if self._create_ok else "backend refused",
        )

    def ensure_module(self, module) -> PhysicalMutationResult:
        self.calls.append(f"ensure_module:{module.device}:{module.module}@{module.slot}")
        if self._module_ok and module.device in self.live:
            model, _ = self.live[module.device]
            self.live[module.device] = (model, f"{module.module}@{module.slot}")
        return PhysicalMutationResult(
            target_id=module.device, target_kind=PhysicalObjectKind.MODULE,
            disposition=(
                MutationDisposition.CHANGED if self._module_ok
                else MutationDisposition.FAILED
            ),
            applied=self._module_ok,
            message="" if self._module_ok else "slot does not exist on this model",
        )

    def observe_device(self, device) -> PhysicalDeviceObservation:
        self.calls.append(f"observe_device:{device.name}")
        model, state = self.live.get(device.name, (device.model, ""))
        ports = self._ports.get((model, state), [])
        return PhysicalDeviceObservation(
            target_id=device.id, observed=True, deployed_name=device.name,
            model=model, interfaces=list(ports),
            interfaces_observed=self._interfaces_observed,
            message="fresh",
        )

    def remove_device(self, device) -> PhysicalMutationResult:
        self.calls.append(f"remove_device:{device.name}")
        if self._remove_ok:
            self.live.pop(device.name, None)
        return PhysicalMutationResult(
            target_id=device.id, target_kind=PhysicalObjectKind.DEVICE,
            disposition=(
                MutationDisposition.CHANGED if self._remove_ok
                else MutationDisposition.FAILED
            ),
            applied=self._remove_ok,
            message="" if self._remove_ok else "still there",
        )


_ROUTER_PORTS = {
    ("1941", ""): ["GigabitEthernet0/0", "GigabitEthernet0/1", "Vlan1"],
    ("1941", "HWIC-2T@0/0"): [
        "GigabitEthernet0/0", "GigabitEthernet0/1",
        "Serial0/0/0", "Serial0/0/1", "Vlan1",
    ],
}


class TestItMeasuresWhatTheBackendReports:
    def test_a_module_state_changes_the_measured_inventory(self):
        physical = _Physical(_ROUTER_PORTS)

        result = PortInventoryQualifier(physical, name_token="t").qualify([
            PortInventoryTarget(model="1941"),
            PortInventoryTarget(model="1941", module="HWIC-2T", slot="0/0"),
        ])

        bare, carded = result.measurements
        assert "Serial0/0/0" not in bare.ports
        assert "Serial0/0/0" in carded.ports
        # El estado de modulo viaja en la evidencia, no se pierde.
        assert carded.as_evidence(**_BACKEND).installed_modules == ["HWIC-2T@0/0"]
        assert bare.as_evidence(**_BACKEND).installed_modules == []

    def test_the_module_is_installed_before_the_read_back_not_after(self):
        physical = _Physical(_ROUTER_PORTS)

        PortInventoryQualifier(physical, name_token="t").qualify([
            PortInventoryTarget(model="1941", module="HWIC-2T", slot="0/0"),
        ])

        order = [item.split(":")[0] for item in physical.calls]
        assert order.index("ensure_module") < order.index("observe_device")

    def test_devices_carry_the_reserved_disposable_prefix(self):
        physical = _Physical(_ROUTER_PORTS)

        PortInventoryQualifier(physical, name_token="t").qualify([
            PortInventoryTarget(model="1941"),
        ])

        created = [c for c in physical.calls if c.startswith("ensure_device:")]
        assert created and all(
            item.split(":", 1)[1].startswith(QUALIFICATION_PREFIX) for item in created
        )


class TestItRefusesToInventEvidence:
    def test_a_module_that_did_not_apply_yields_no_inventory(self):
        """Medir un 1941 sin su HWIC y llamarlo "con HWIC" seria fabricarlo."""
        physical = _Physical(_ROUTER_PORTS, module_ok=False)

        result = PortInventoryQualifier(physical, name_token="t").qualify([
            PortInventoryTarget(model="1941", module="HWIC-2T", slot="0/0"),
        ])

        measurement = result.measurements[0]
        assert measurement.module_applied is False
        assert measurement.usable is False
        assert measurement.as_evidence(**_BACKEND) is None
        # Y ni siquiera se relee: no hay nada que la lectura pudiera decir.
        assert not any(c.startswith("observe_device") for c in physical.calls)

    def test_an_unobserved_interface_list_yields_no_inventory(self):
        physical = _Physical(_ROUTER_PORTS, interfaces_observed=False)

        result = PortInventoryQualifier(physical, name_token="t").qualify([
            PortInventoryTarget(model="1941"),
        ])

        assert result.measurements[0].usable is False
        assert result.measurements[0].as_evidence(**_BACKEND) is None

    def test_an_empty_port_list_is_not_evidence_of_a_portless_model(self):
        physical = _Physical({("1941", ""): []})

        result = PortInventoryQualifier(physical, name_token="t").qualify([
            PortInventoryTarget(model="1941"),
        ])

        assert result.measurements[0].usable is False

    def test_a_device_the_backend_refused_to_create_measures_nothing(self):
        physical = _Physical(_ROUTER_PORTS, create_ok=False)

        result = PortInventoryQualifier(physical, name_token="t").qualify([
            PortInventoryTarget(model="1941"),
        ])

        assert result.measurements[0].usable is False
        assert "device_not_created" in result.measurements[0].message
        assert not any(c.startswith("remove_device") for c in physical.calls)

    def test_it_never_writes_the_measured_store(self):
        """Pinchar evidencia es un acto versionado, no un efecto secundario."""
        from pathlib import Path

        source = Path(
            "src/packet_tracer_mcp/application/use_cases/qualify_port_inventories.py",
        ).read_text(encoding="utf-8")

        assert "MEASURED_PORT_INVENTORIES" not in source
        assert "open(" not in source and "write_text" not in source


class TestItCleansUpAfterItself:
    def test_every_created_device_is_removed_in_reverse_order(self):
        physical = _Physical(_ROUTER_PORTS)

        result = PortInventoryQualifier(physical, name_token="t").qualify([
            PortInventoryTarget(model="1941"),
            PortInventoryTarget(model="1941", module="HWIC-2T", slot="0/0"),
        ])

        removals = [c for c in physical.calls if c.startswith("remove_device:")]
        assert len(removals) == 2
        assert removals[0].endswith("_01") and removals[1].endswith("_00")
        assert result.restored is True
        assert physical.live == {}

    def test_a_failed_read_back_still_gets_cleaned_up(self):
        physical = _Physical({}, interfaces_observed=False)

        result = PortInventoryQualifier(physical, name_token="t").qualify([
            PortInventoryTarget(model="1941"),
        ])

        assert result.removed
        assert result.restored is True

    def test_a_cleanup_that_did_not_apply_is_reported_not_swallowed(self):
        physical = _Physical(_ROUTER_PORTS, remove_ok=False)

        result = PortInventoryQualifier(physical, name_token="t").qualify([
            PortInventoryTarget(model="1941"),
        ])

        assert result.removed == ()
        assert any("Cleanup did not apply" in item for item in result.errors)
        assert result.restored is False

    def test_a_non_empty_workspace_is_never_mutated(self):
        physical = _Physical(_ROUTER_PORTS, preexisting=["Someone Elses Router"])

        result = PortInventoryQualifier(physical, name_token="t").qualify([
            PortInventoryTarget(model="1941"),
        ])

        assert result.measurements == ()
        assert physical.calls == ["observe_workspace"]
        assert any("refuses to mutate" in item for item in result.errors)


class TestTheEvidenceItProduces:
    def test_evidence_carries_the_build_it_was_measured_on(self):
        physical = _Physical(_ROUTER_PORTS)

        result = PortInventoryQualifier(physical, name_token="t").qualify([
            PortInventoryTarget(model="1941", module="HWIC-2T", slot="0/0"),
        ])
        evidence = result.usable_measurements[0].as_evidence(
            backend="packet_tracer", backend_version="9.0.1.0858", source="meg5",
        )

        assert evidence.model == "1941"
        assert evidence.backend_version == "9.0.1.0858"
        assert evidence.source == "meg5"
        assert "Serial0/0/1" in evidence.ports

    @pytest.mark.parametrize("kwargs", [
        {"module_ok": False}, {"interfaces_observed": False}, {"create_ok": False},
    ])
    def test_usable_measurements_excludes_everything_unusable(self, kwargs):
        physical = _Physical(_ROUTER_PORTS, **kwargs)

        result = PortInventoryQualifier(physical, name_token="t").qualify([
            PortInventoryTarget(model="1941", module="HWIC-2T", slot="0/0"),
        ])

        assert result.usable_measurements == ()
