"""Invariantes del Concrete TopologyPlan producido por E4."""

from __future__ import annotations

from collections import Counter

from ..enterprise.models.compilation import (
    CompilationIssue,
    CompilationIssueCode,
    CompilationIssueSeverity,
)
from ..enterprise.services.physical_ports import is_logical_interface
from ..models.plans import TopologyPlan


def validate_concrete_topology(
    plan: TopologyPlan, physical_ports_by_device: dict[str, set[str]],
) -> list[CompilationIssue]:
    issues: list[CompilationIssue] = []
    ids = Counter(device.id for device in plan.devices)
    names = Counter(device.name for device in plan.devices)
    for device_id, count in sorted(ids.items()):
        if not device_id or count > 1:
            issues.append(_error(
                CompilationIssueCode.DUPLICATE_DEVICE_ID,
                f"ID de dispositivo ausente o duplicado: {device_id!r}.", device_id,
            ))
    for name, count in sorted(names.items()):
        if count > 1:
            issues.append(_error(
                CompilationIssueCode.DUPLICATE_DEVICE_NAME,
                f"Nombre de dispositivo duplicado: {name!r}.", name,
            ))

    devices = {device.id: device for device in plan.devices}
    used: dict[tuple[str, str], str] = {}
    links_seen: set[tuple[tuple[str, str], tuple[str, str]]] = set()
    for link in plan.links:
        if link.device_a_id == link.device_b_id:
            issues.append(_error(
                CompilationIssueCode.SELF_LINK, "Un enlace no puede conectar un dispositivo consigo mismo.", link.id,
            ))
        for device_id in (link.device_a_id, link.device_b_id):
            if device_id not in devices:
                issues.append(_error(
                    CompilationIssueCode.LINK_ENDPOINT_MISSING,
                    f"El enlace referencia el dispositivo inexistente {device_id!r}.", link.id,
                ))
        endpoints = ((link.device_a_id, link.port_a), (link.device_b_id, link.port_b))
        link_key = tuple(sorted(endpoints))
        if link_key in links_seen:
            issues.append(_error(
                CompilationIssueCode.DUPLICATE_LINK, "Enlace físico duplicado.", link.id,
            ))
        links_seen.add(link_key)
        for device_id, port in endpoints:
            if is_logical_interface(port):
                issues.append(_error(
                    CompilationIssueCode.LOGICAL_PORT_SELECTED,
                    f"La interfaz lógica {port!r} no puede recibir un cable.", device_id,
                ))
            known_ports = physical_ports_by_device.get(device_id, set())
            if known_ports and port not in known_ports:
                issues.append(_error(
                    CompilationIssueCode.PHYSICAL_PORT_MISSING,
                    f"El puerto {port!r} no existe en el inventario físico.", device_id,
                ))
            key = (device_id, port)
            if key in used:
                issues.append(_error(
                    CompilationIssueCode.PORT_ALREADY_ASSIGNED,
                    f"El puerto {device_id}:{port} ya pertenece a {used[key]}.", link.id,
                ))
            else:
                used[key] = link.id

    coordinates = Counter((device.x, device.y) for device in plan.devices)
    for coordinate, count in sorted(coordinates.items()):
        if count > 1:
            issues.append(_error(
                CompilationIssueCode.LAYOUT_COLLISION,
                f"{count} dispositivos comparten las coordenadas {coordinate}.",
            ))
    return issues


def _error(code: CompilationIssueCode, message: str, subject: str = "") -> CompilationIssue:
    return CompilationIssue(
        severity=CompilationIssueSeverity.ERROR,
        code=code,
        message=message,
        subject=subject,
    )
