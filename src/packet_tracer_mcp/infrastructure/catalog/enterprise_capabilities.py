"""Adapter del catálogo Packet Tracer existente al dominio Enterprise."""

from __future__ import annotations

import re

from ...domain.enterprise.models.capabilities import (
    CapabilityEvidence,
    CapabilityStatus,
    DeviceCapabilities,
    EvidenceSource,
)
from ...domain.enterprise.models.hardware import (
    CatalogCoverageReport,
    HardwareCandidate,
    ModuleInstallation,
    NormalizedPortSpeed,
    PortClass,
    PortDescriptor,
)
from ...domain.enterprise.services.capability_resolver import (
    CapabilityResolver,
    CapabilityProvider,
    CatalogDeviceFacts,
)
from ...domain.enterprise.models.link_performance import port_kind_of
from .aliases import MODEL_ALIASES
from .devices import ALL_MODELS, DeviceModel, PortSpec
from .measured_port_inventories import (
    backend_verified_port_inventory,
    module_state_token,
)
from .modules import ALL_MODULES, get_serial_module
from .capability_providers import (
    ProbeCapabilityProvider,
    RuntimeCapabilityProvider,
    StaticVerifiedCapabilityProvider,
)
from ..persistence.capability_snapshot_store import CapabilitySnapshotStore


#: Los tipos de interfaz que el catálogo sabe describir físicamente. Una lectura
#: real trae además interfaces lógicas (`Vlan1`) o de radio (`Bluetooth`); se
#: conservan en el registro de evidencia y no se convierten en puertos de
#: planificación, porque el planificador no tiene nada que hacer con ellas.
_PHYSICAL_PORT_KINDS = frozenset({
    "Ethernet", "FastEthernet", "GigabitEthernet", "TenGigabitEthernet", "Serial",
})


def _measured_port_specs(ports: list[str]) -> list[PortSpec]:
    """Convierte nombres observados en specs, conservando el orden observado."""
    specs: list[PortSpec] = []
    for name in ports:
        kind = port_kind_of(name)
        if kind not in _PHYSICAL_PORT_KINDS:
            continue
        specs.append(PortSpec(speed=kind, slot=name[len(kind):], full_name=name))
    return specs


_SERIAL_MODULE_SLOT_BY_MODEL = {
    "1941": "0/0",
    "2811": "1",
    "2901": "0/0",
    "2911": "0/0",
    "ISR4321": "0",
    "ISR4331": "0",
}

_CP_SCALE_2811_LIVE_EVIDENCE = CapabilityEvidence(
    capability="layer3",
    status=CapabilityStatus.SUPPORTED,
    source=EvidenceSource.STATIC_OVERRIDE,
    source_detail=(
        "CP-SCALE CORE governed live qualification: 15 typed routed-interface "
        "and subinterface actions on three disposable 2811 routers were read "
        "back exactly before fresh RIPv2 forwarding verification; see "
        "docs/architecture/ripv2-runtime-qualification.md"
    ),
    packet_tracer_version="9.0.1.0858",
    confidence="live_qualified",
    verified=True,
)


def _normalization_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.casefold())


class EnterpriseCapabilityAdapter:
    """Expone el catálogo vigente sin copiarlo ni asumir capacidades IOS no verificadas."""

    def __init__(
        self,
        resolver: CapabilityResolver | None = None,
        providers: list[CapabilityProvider] | None = None,
        bound_packet_tracer_version: str | None = None,
    ) -> None:
        self._resolver = resolver or CapabilityResolver()
        self._providers = providers or []
        self._bound_packet_tracer_version = bound_packet_tracer_version
        self._normalization_index = self._build_normalization_index()

    def normalize_model_name(self, name: str) -> str | None:
        """Devuelve el `pt_type` canónico reutilizando los aliases existentes."""
        return self._normalization_index.get(_normalization_key(name))

    def can_represent(self, model_name: str) -> bool:
        return self.normalize_model_name(model_name) is not None

    def capabilities_for(
        self, model_name: str, packet_tracer_version: str | None = None,
    ) -> DeviceCapabilities | None:
        canonical = self.normalize_model_name(model_name)
        if canonical is None:
            return None
        model = ALL_MODELS[canonical]
        capabilities = self._resolver.resolve(self._facts_for(model))
        return self._resolve_runtime_evidence(capabilities, packet_tracer_version)

    def all_capabilities(
        self, category: str | None = None, packet_tracer_version: str | None = None,
    ) -> list[DeviceCapabilities]:
        """Carga capacidades compactas y ordenadas; el llamador puede filtrar por categoría."""
        models = (
            model for model in ALL_MODELS.values()
            if category is None or model.category == category
        )
        return [
            self._resolve_runtime_evidence(self._resolver.resolve(self._facts_for(model)), packet_tracer_version)
            for model in sorted(models, key=lambda item: item.pt_type.casefold())
        ]

    def port_descriptors_for(
        self,
        model_name: str,
        *,
        backend_version: str = "",
        installed_modules: list[str] | tuple[str, ...] | None = None,
    ) -> list[PortDescriptor]:
        """Adapta nombres y velocidades reales del catálogo a clases físicas E3.

        Con un build concreto y una medición para ese modelo y ese estado de
        módulos, los nombres salen de lo OBSERVADO en vez de lo declarado: el
        catálogo dice qué debería haber, y una vez que un backend dijo qué hay,
        planificar contra lo declarado es planificar contra algo que ya se sabe
        distinto. Sin medición adecuada se usa lo declarado, que sirve para
        planificar y no autoriza ningún binding -- eso lo decide el preflight
        de despliegue.
        """
        canonical = self.normalize_model_name(model_name)
        if canonical is None:
            return []
        model = ALL_MODELS[canonical]
        if backend_version:
            resolution = backend_verified_port_inventory(
                canonical,
                backend_version=backend_version,
                installed_modules=installed_modules,
            )
            if resolution.backend_verified:
                return [
                    self._port_descriptor(
                        model, port, source=f"backend_verified:{backend_version}",
                    )
                    for port in _measured_port_specs(resolution.bindable_ports)
                ]
        return [self._port_descriptor(model, port) for port in model.ports]

    def coverage_report(self, observed_models: list[str] | None = None) -> CatalogCoverageReport:
        """Compara nombres observados con el catálogo sin incorporarlos automáticamente."""
        base = sorted(ALL_MODELS)
        capabilities = self.all_capabilities()
        gaps = {
            capability.model: [
                name for name in ("supports_poe", "layer2", "layer3", "supports_routing")
                if getattr(capability, name).value == "unknown"
            ]
            for capability in capabilities
        }
        observed = observed_models or []
        return CatalogCoverageReport(
            known_in_enterprise=base,
            known_in_base_catalog=base,
            unclassified=sorted(name for name in observed if not self.can_represent(name)),
            aliases=dict(sorted(MODEL_ALIASES.items())),
            capability_gaps=gaps,
        )

    def hardware_candidates(
        self, category: str, packet_tracer_version: str | None = None,
    ) -> list[HardwareCandidate]:
        """Provee candidatos físicos al dominio sin que éste importe el catálogo PT."""
        candidates: list[HardwareCandidate] = []
        for capability in self.all_capabilities(category, packet_tracer_version):
            module_options = self._serial_module_options(
                capability.model, packet_tracer_version or "",
            )
            candidates.append(HardwareCandidate(
                model=capability.model,
                capabilities=capability,
                # Sin módulos: en este momento ninguno está instalado todavía, y
                # una medición tomada CON tarjeta no responde por este estado.
                ports=self.port_descriptors_for(
                    capability.model,
                    backend_version=packet_tracer_version or "",
                ),
                module_options=module_options,
                available_module_slots=[
                    option.slot for option in module_options if option.slot is not None
                ],
            ))
        return candidates

    def identity_for(self, runtime_model: str, packet_tracer_version: str | None = None):
        """Resuelve sólo matching exacto/alias ya declarado; no inventa aliases runtime."""
        from ...domain.enterprise.models.discovery import DeviceIdentity, ModelIdentityStatus

        canonical = self.normalize_model_name(runtime_model)
        if canonical is None:
            return DeviceIdentity(
                runtime_id=runtime_model,
                display_name=runtime_model,
                packet_tracer_version=packet_tracer_version,
                status=ModelIdentityStatus.UNRESOLVED_IDENTITY,
            )
        model = ALL_MODELS[canonical]
        aliases = [alias for alias, target in MODEL_ALIASES.items() if target == canonical]
        return DeviceIdentity(
            canonical_id=canonical,
            runtime_id=runtime_model,
            display_name=model.display_name,
            aliases=sorted(aliases, key=str.casefold),
            category=model.category,
            packet_tracer_version=packet_tracer_version,
            status=ModelIdentityStatus.CATALOG_MATCHED,
        )

    def _resolve_runtime_evidence(
        self,
        capabilities: DeviceCapabilities,
        packet_tracer_version: str | None,
    ) -> DeviceCapabilities:
        if (
            self._bound_packet_tracer_version is not None
            and packet_tracer_version is not None
            and packet_tracer_version != self._bound_packet_tracer_version
        ):
            return self._resolver.with_evidence(
                capabilities, [], packet_tracer_version,
            )
        effective_version = (
            packet_tracer_version or self._bound_packet_tracer_version
        )
        evidence = [
            item
            for provider in self._providers
            for item in provider.evidence_for(capabilities.model, effective_version)
        ]
        evidence = _with_semantic_implications(evidence)
        return self._resolver.with_evidence(
            capabilities, evidence, effective_version,
        )

    def _facts_for(self, model: DeviceModel) -> CatalogDeviceFacts:
        aliases = tuple(
            alias for alias, canonical in MODEL_ALIASES.items()
            if canonical == model.pt_type
        ) + (model.pt_type, model.display_name)
        compatible_modules = tuple(
            spec.name for spec in ALL_MODULES.values()
            if not spec.compatible_with or model.pt_type in spec.compatible_with
        )
        return CatalogDeviceFacts(
            model=model.pt_type,
            category=model.category,
            aliases=aliases,
            port_speeds=tuple(self._speed_value(port.speed) for port in model.ports),
            compatible_modules=compatible_modules,
            source="packet_tracer_catalog",
        )

    def _build_normalization_index(self) -> dict[str, str]:
        index: dict[str, str] = {}
        for model in ALL_MODELS.values():
            variants = {model.pt_type, model.display_name}
            if model.pt_type.casefold().startswith("isr"):
                variants.add(model.pt_type[3:])
            for variant in tuple(variants):
                variants.add(re.sub(r"\bisr\s*", "", variant, flags=re.IGNORECASE))
            for variant in variants:
                index[_normalization_key(variant)] = model.pt_type
        for alias, canonical in MODEL_ALIASES.items():
            index[_normalization_key(alias)] = canonical
        return index

    @staticmethod
    def _speed_value(speed: object) -> str:
        return str(getattr(speed, "value", speed))

    def _port_descriptor(
        self, model: DeviceModel, port, *, source: str = "catalog",
    ) -> PortDescriptor:
        speed = self._speed_value(port.speed)
        normalized_speed = {
            "Ethernet": NormalizedPortSpeed.SPEED_10M,
            "FastEthernet": NormalizedPortSpeed.SPEED_100M,
            "GigabitEthernet": NormalizedPortSpeed.SPEED_1G,
            "TenGigabitEthernet": NormalizedPortSpeed.SPEED_10G,
        }.get(speed, NormalizedPortSpeed.UNKNOWN)
        classes: list[PortClass] = []
        if speed == "Serial":
            classes.extend([PortClass.SERIAL, PortClass.WAN])
        elif model.category == "switch" and (
            model.access_port_names or model.uplink_port_names
        ):
            if port.full_name in model.access_port_names:
                classes.append(PortClass.ACCESS_CAPABLE)
            if port.full_name in model.uplink_port_names:
                classes.append(PortClass.UPLINK_CAPABLE)
        elif model.category == "switch" and speed in {"Ethernet", "FastEthernet"}:
            classes.append(PortClass.ACCESS_CAPABLE)
        elif model.category == "switch" and speed in {"GigabitEthernet", "TenGigabitEthernet"}:
            classes.append(PortClass.UPLINK_CAPABLE)
        elif model.category == "router" and speed in {"Ethernet", "FastEthernet", "GigabitEthernet", "TenGigabitEthernet"}:
            classes.extend([PortClass.WAN, PortClass.UPLINK_CAPABLE])
        return PortDescriptor(
            name=port.full_name,
            classes=classes,
            speed=normalized_speed,
            slot=port.slot,
            source=source,
        )

    @staticmethod
    def _serial_module_options(
        model: str, backend_version: str = "",
    ) -> list[ModuleInstallation]:
        module = get_serial_module(model)
        slot = _SERIAL_MODULE_SLOT_BY_MODEL.get(model)
        if module is None or slot is None:
            return []
        option = ModuleInstallation(
            module=module.name,
            slot=slot,
            provided_ports=list(module.ports_added),
            provided_port_classes=[PortClass.SERIAL, PortClass.WAN],
        )
        if backend_version:
            evidence = backend_verified_port_inventory(
                model,
                backend_version=backend_version,
                installed_modules=[module_state_token(module.name, slot)],
            )
            if not evidence.backend_verified or not evidence.permits(option.provided_ports):
                return []
        return [option]


def packet_tracer_enterprise_capability_adapter(
    packet_tracer_version: str,
    *,
    store: CapabilitySnapshotStore | None = None,
) -> EnterpriseCapabilityAdapter:
    """Build the productive, exact-version capability composition root."""

    version = packet_tracer_version.strip()
    if not version:
        raise ValueError("An exact Packet Tracer version is required.")
    snapshots = store or CapabilitySnapshotStore()
    return EnterpriseCapabilityAdapter(
        providers=[
            StaticVerifiedCapabilityProvider({
                "2811": [_CP_SCALE_2811_LIVE_EVIDENCE],
            }),
            ProbeCapabilityProvider(snapshots, version),
            RuntimeCapabilityProvider(snapshots, version),
        ],
        bound_packet_tracer_version=version,
    )


def _with_semantic_implications(evidence):
    """Apply model-neutral, one-way implications without defeating explicit facts."""

    items = list(evidence)
    direct = {item.capability for item in items}
    if "layer3" not in direct:
        source = next((
            item for item in items
            if item.capability == "multilayer_intervlan"
            and item.status is CapabilityStatus.SUPPORTED
            and item.verified
        ), None)
        if source is not None:
            detail = source.source_detail or "verified multilayer forwarding"
            items.append(source.model_copy(update={
                "capability": "layer3",
                "source_detail": detail + " => layer3",
                "notes": (
                    (source.notes + " ") if source.notes else ""
                ) + "Inter-VLAN forwarding is a model-neutral positive proof of layer-3 capability.",
            }))
    return items
