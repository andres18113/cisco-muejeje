"""Normalize Packet Tracer inventory into manifest-safe runtime targets."""

from __future__ import annotations

from ...domain.enterprise.models.configuration_runtime import RuntimeConfigurationTarget
from ...domain.enterprise.models.deployment import runtime_target_fingerprint


def normalize_runtime_inventory(
    raw: list[dict] | dict,
) -> list[RuntimeConfigurationTarget]:
    """Create deterministic targets with a revalidatable composite fingerprint."""

    items = raw.get("devices", []) if isinstance(raw, dict) else raw
    targets: list[RuntimeConfigurationTarget] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        interfaces = sorted({
            str(port.get("name") if isinstance(port, dict) else port)
            for port in (item.get("ports", item.get("interfaces", [])) or [])
            if port and (not isinstance(port, dict) or port.get("name"))
        }, key=str.casefold)
        device_name = str(item.get("name") or item.get("device_name") or "")
        model = str(item.get("model") or "")
        explicit_fingerprint = str(item.get("runtime_fingerprint") or "")
        targets.append(RuntimeConfigurationTarget(
            device_name=device_name,
            model=model,
            interfaces=interfaces,
            runtime_identifier=str(item.get("runtime_identifier") or ""),
            runtime_identifier_stable=(
                item.get("runtime_identifier_stable") is True
            ),
            runtime_fingerprint=(
                explicit_fingerprint
                or runtime_target_fingerprint(device_name, model, interfaces)
            ),
        ))
    return sorted(targets, key=lambda item: item.device_name)
