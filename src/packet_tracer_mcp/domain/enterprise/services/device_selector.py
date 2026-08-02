"""Selección determinista basada en capacidades conocidas, no en nombres de modelo."""

from __future__ import annotations

from collections.abc import Iterable

from ..models.capabilities import (
    CapabilityStatus,
    DeviceCandidate,
    DeviceCandidateStatus,
    DeviceCapabilities,
    DeviceRequirement,
    DeviceSelectionResult,
    DeviceSelectionStatus,
)
from ..models.roles import DeviceRole


_CATEGORY_BY_ROLE = {
    DeviceRole.ACCESS_SWITCH: "switch",
    DeviceRole.DISTRIBUTION_SWITCH: "switch",
    DeviceRole.CORE_SWITCH: "switch",
    DeviceRole.WAN_ROUTER: "router",
    DeviceRole.EDGE_ROUTER: "router",
    DeviceRole.FIREWALL: "firewall",
}


class DeviceSelector:
    """Filtra candidatos por hechos del catálogo y ordena los resultados establemente."""

    def select(
        self,
        requirement: DeviceRequirement,
        candidates: Iterable[DeviceCapabilities],
    ) -> DeviceSelectionResult:
        expected_category = requirement.category or _CATEGORY_BY_ROLE.get(requirement.role)
        rejected: dict[str, list[str]] = {}
        needs_verification: dict[str, list[str]] = {}
        compatible: list[DeviceCapabilities] = []
        for candidate in candidates:
            problems, missing = self._problems(candidate, requirement, expected_category)
            if problems:
                rejected[candidate.model] = problems
            elif missing:
                needs_verification[candidate.model] = missing
            else:
                compatible.append(candidate)

        preferred_warning = self._preferred_warning(requirement, compatible, rejected)
        candidate_rows = [
            DeviceCandidate(model=model, status=DeviceCandidateStatus.INCOMPATIBLE, rejected_reasons=reasons)
            for model, reasons in sorted(rejected.items())
        ] + [
            DeviceCandidate(model=model, status=DeviceCandidateStatus.NEEDS_VERIFICATION, missing_evidence=missing)
            for model, missing in sorted(needs_verification.items())
        ] + [
            DeviceCandidate(model=item.model, status=DeviceCandidateStatus.COMPATIBLE)
            for item in sorted(compatible, key=lambda item: item.model.casefold())
        ]
        if not compatible:
            if needs_verification:
                return DeviceSelectionResult(
                    status=DeviceSelectionStatus.PARTIALLY_SUPPORTED,
                    alternatives=sorted(needs_verification),
                    reasons=["Los candidatos físicos cumplen puertos, pero requieren evidencia de capacidad."],
                    warnings=[preferred_warning] if preferred_warning else [],
                    candidates=candidate_rows,
                )
            reasons = ["Ningún modelo del catálogo cumple todos los requisitos verificables."]
            if expected_category:
                reasons.append(f"Categoría requerida: {expected_category}.")
            reasons.extend(self._compact_rejection_reasons(rejected))
            return DeviceSelectionResult(
                status=DeviceSelectionStatus.UNSUPPORTED,
                reasons=reasons,
                warnings=[preferred_warning] if preferred_warning else [],
                candidates=candidate_rows,
            )

        ranked = sorted(
            compatible,
            key=lambda item: self._ranking_key(item, requirement),
        )
        selected = ranked[0]
        reasons = [
            f"{selected.model} cumple {selected.access_port_count} puertos de acceso "
            f"y {selected.uplink_port_count} uplinks conocidos.",
        ]
        if requirement.preferred_model and selected.model.casefold() == requirement.preferred_model.casefold():
            reasons.append("Se respetó el modelo preferido porque cumple los requisitos.")
        return DeviceSelectionResult(
            status=DeviceSelectionStatus.SUPPORTED,
            selected_model=selected.model,
            alternatives=[candidate.model for candidate in ranked[1:]],
            reasons=reasons,
            warnings=[preferred_warning] if preferred_warning else [],
            candidates=candidate_rows,
        )

    @staticmethod
    def _problems(
        candidate: DeviceCapabilities,
        requirement: DeviceRequirement,
        expected_category: str | None,
    ) -> tuple[list[str], list[str]]:
        problems: list[str] = []
        missing_evidence: list[str] = []
        if expected_category and candidate.category != expected_category:
            problems.append(f"categoría {candidate.category}, se requiere {expected_category}")
        if candidate.access_port_count < requirement.min_access_ports:
            problems.append(
                f"{candidate.access_port_count} puertos de acceso, se requieren {requirement.min_access_ports}"
            )
        if candidate.uplink_port_count < requirement.min_uplinks:
            problems.append(f"{candidate.uplink_port_count} uplinks, se requieren {requirement.min_uplinks}")
        if requirement.poe_ports:
            if candidate.supports_poe is CapabilityStatus.UNSUPPORTED:
                problems.append("PoE no soportado")
            elif candidate.supports_poe is CapabilityStatus.UNKNOWN:
                missing_evidence.append("supports_poe")
            elif candidate.poe_ports is None or candidate.poe_ports < requirement.poe_ports:
                problems.append(f"{candidate.poe_ports or 0} puertos PoE, se requieren {requirement.poe_ports}")
        if requirement.requires_layer3:
            if candidate.layer3 is CapabilityStatus.UNSUPPORTED:
                problems.append("capa 3 no soportada")
            elif candidate.layer3 is CapabilityStatus.UNKNOWN:
                missing_evidence.append("layer3")
        if requirement.requires_modules:
            if candidate.supports_modules is CapabilityStatus.UNSUPPORTED:
                problems.append("módulos no soportados")
            elif candidate.supports_modules is CapabilityStatus.UNKNOWN:
                missing_evidence.append("supports_modules")
        return problems, missing_evidence

    @staticmethod
    def _ranking_key(candidate: DeviceCapabilities, requirement: DeviceRequirement) -> tuple[int, int, int, str]:
        requested = (
            ("supports_poe", requirement.poe_ports > 0),
            ("layer3", requirement.requires_layer3),
            ("supports_modules", requirement.requires_modules),
        )
        unknown_requested = sum(
            getattr(candidate, attribute) is CapabilityStatus.UNKNOWN
            for attribute, required in requested
            if required
        )
        preferred_penalty = 0
        if requirement.preferred_model:
            preferred_penalty = int(candidate.model.casefold() != requirement.preferred_model.casefold())
        excess = (
            candidate.access_port_count - requirement.min_access_ports
            + candidate.uplink_port_count - requirement.min_uplinks
        )
        return preferred_penalty, unknown_requested, excess, candidate.model.casefold()

    @staticmethod
    def _preferred_warning(
        requirement: DeviceRequirement,
        compatible: list[DeviceCapabilities],
        rejected: dict[str, list[str]],
    ) -> str:
        if not requirement.preferred_model:
            return ""
        preferred = requirement.preferred_model.casefold()
        if any(candidate.model.casefold() == preferred for candidate in compatible):
            return ""
        for model, problems in rejected.items():
            if model.casefold() == preferred:
                return f"Modelo preferido {model} rechazado: {'; '.join(problems)}."
        return f"Modelo preferido {requirement.preferred_model} no existe en los candidatos disponibles."

    @staticmethod
    def _compact_rejection_reasons(rejected: dict[str, list[str]]) -> list[str]:
        grouped: dict[str, int] = {}
        for problems in rejected.values():
            for problem in problems:
                grouped[problem] = grouped.get(problem, 0) + 1
        return [f"{count} candidato(s): {problem}." for problem, count in sorted(grouped.items())]
