"""Validación explícita de requisitos Enterprise fuera de los modelos Pydantic."""

from __future__ import annotations

import re

from ...models.errors import ErrorCode, PlanError, ValidationResult
from ..models.intent import EnterpriseIntent
from ..models.link_performance import LinkMedia
from .site_planner import site_id_for


def validate_enterprise_intent(intent: EnterpriseIntent) -> ValidationResult:
    """Valida restricciones de negocio sin contaminar los modelos de transporte."""
    result = ValidationResult()

    if not 0 <= intent.default_growth_percent <= 100:
        result.errors.append(PlanError(
            code=ErrorCode.ENTERPRISE_INVALID_GROWTH_PERCENT,
            message="El crecimiento predeterminado debe estar entre 0 y 100.",
            suggestion="Usá un porcentaje entre 0 y 100.",
        ))

    seen_site_ids: set[str] = set()
    for site in intent.sites:
        site_id = site.name.casefold().strip()
        if site_id in seen_site_ids:
            result.errors.append(PlanError(
                code=ErrorCode.ENTERPRISE_DUPLICATE_HIERARCHY_ID,
                message=f"La sede {site.name!r} está repetida.",
                device=site.name,
            ))
        seen_site_ids.add(site_id)
        if not site.name.strip():
            result.errors.append(PlanError(
                code=ErrorCode.ENTERPRISE_EMPTY_SITE_NAME,
                message="Cada sitio Enterprise debe tener un nombre.",
                suggestion="Asigná un nombre único al sitio.",
            ))
        if site.growth_percent is not None and not 0 <= site.growth_percent <= 100:
            result.errors.append(PlanError(
                code=ErrorCode.ENTERPRISE_INVALID_GROWTH_PERCENT,
                message=f"El crecimiento de {site.name!r} debe estar entre 0 y 100.",
                device=site.name,
                suggestion="Usá un porcentaje entre 0 y 100.",
            ))
        _validate_requirements(site.endpoints, site.name, result)
        _validate_buildings(site, result)
    _validate_wan_requirements(intent, result)
    return result


def _validate_wan_requirements(
    intent: EnterpriseIntent,
    result: ValidationResult,
) -> None:
    """Valida pares WAN como enlaces no dirigidos antes de crear un plan."""
    known_sites = {site_id_for(site.name) for site in intent.sites}
    media_by_pair: dict[tuple[str, str], set[LinkMedia]] = {}
    for site in sorted(intent.sites, key=lambda item: site_id_for(item.name)):
        source = site_id_for(site.name)
        for requirement in sorted(
            site.uplinks,
            key=lambda item: (item.target_site_id, item.media.value),
        ):
            target = requirement.target_site_id
            if target == source:
                result.errors.append(PlanError(
                    code=ErrorCode.ENTERPRISE_WAN_SELF_LINK,
                    message=f"El sitio {source!r} no puede enlazarse consigo mismo.",
                    device=source,
                    suggestion="Eliminá el uplink propio o indicá otro sitio.",
                ))
                continue
            if target not in known_sites:
                result.errors.append(PlanError(
                    code=ErrorCode.ENTERPRISE_WAN_SITE_NOT_FOUND,
                    message=f"El sitio destino WAN {target!r} no existe.",
                    device=source,
                    suggestion="Usá el site_id de un sitio declarado en la intención.",
                ))
                continue
            if requirement.media is LinkMedia.UNKNOWN:
                result.errors.append(PlanError(
                    code=ErrorCode.ENTERPRISE_WAN_MEDIA_UNKNOWN,
                    message=f"El enlace WAN {source}<->{target} requiere un medio conocido.",
                    device=f"{min(source, target)}<->{max(source, target)}",
                    suggestion="Indicá serial o ethernet.",
                ))
                continue
            pair = tuple(sorted((source, target)))
            media_by_pair.setdefault(pair, set()).add(requirement.media)

    for pair, media in sorted(media_by_pair.items()):
        if len(media) <= 1:
            continue
        media_names = ", ".join(sorted(item.value for item in media))
        result.errors.append(PlanError(
            code=ErrorCode.ENTERPRISE_WAN_MEDIA_CONFLICT,
            message=(
                f"El enlace WAN {pair[0]}<->{pair[1]} declara medios incompatibles: "
                f"{media_names}."
            ),
            device=f"{pair[0]}<->{pair[1]}",
            suggestion="Declaralo con un único medio en ambos extremos.",
        ))


def _validate_buildings(site, result: ValidationResult) -> None:
    building_names: set[str] = set()
    for building in site.buildings:
        _duplicate_name(building.name, building_names, site.name, result)
        floor_names: set[str] = set()
        for floor in building.floors:
            _duplicate_name(floor.name, floor_names, site.name, result)
            zone_names: set[str] = set()
            for zone in floor.zones:
                _duplicate_name(zone.name, zone_names, site.name, result)
                group_names: set[str] = set()
                for group in zone.endpoint_groups:
                    _duplicate_name(group.name, group_names, site.name, result)
                    _validate_requirements(group.requirements, site.name, result)


def _duplicate_name(name: str, seen: set[str], site_name: str, result: ValidationResult) -> None:
    key = re.sub(r"[^a-z0-9]+", "-", name.casefold()).strip("-")
    if key in seen:
        result.errors.append(PlanError(
            code=ErrorCode.ENTERPRISE_DUPLICATE_HIERARCHY_ID,
            message=f"El identificador jerárquico {name!r} está repetido en {site_name!r}.",
            device=site_name,
        ))
    seen.add(key)


def _validate_requirements(requirements, site_name: str, result: ValidationResult) -> None:
    for endpoint in requirements:
        if endpoint.count <= 0:
            result.errors.append(PlanError(
                code=ErrorCode.ENTERPRISE_INVALID_ENDPOINT_COUNT,
                message=(
                    f"El requisito {endpoint.role.value!r} debe tener una cantidad mayor a cero."
                ),
                device=site_name,
                suggestion="Indicá al menos un endpoint o eliminá el requisito.",
            ))
        if endpoint.wired and endpoint.wireless:
            result.warnings.append(PlanError(
                code=ErrorCode.VALIDATION_ERROR,
                message=(
                    f"El requisito {endpoint.role.value!r} declara wired y wireless; "
                    "E2 deberá separarlo en dos grupos."
                ),
                device=site_name,
            ))
