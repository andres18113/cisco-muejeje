"""Renderer confiable de acciones E7 para el backend IOS de Packet Tracer."""

from __future__ import annotations

import ipaddress
import re
from collections import defaultdict
from dataclasses import dataclass

from ...domain.enterprise.models.voice_plan import (
    BindPhoneToExtension,
    ConfigureCallControlSource,
    ConfigureDialRule,
    ConfigureVoiceDhcpOption,
    CreateExtension,
    EnableCallControl,
    GeneratePhoneConfigurationFiles,
    VoiceAction,
    VoicePhase,
)
from ...shared.ios_config import build_configure_ios_call


_PHONE_TYPES = {"7960": "7960", "CIPC": "CIPC", "ATA": "ata"}
_HEX = re.compile(r"^[0-9A-Fa-f]{12}$")
_POOL_NAME = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")


@dataclass(frozen=True)
class RenderedVoiceBatch:
    device_name: str
    phase: VoicePhase
    action_ids: list[str]
    ios_payload: str
    js_call: str


class PacketTracerVoiceRenderer:
    """Convierte acciones cerradas y MACs observadas; no acepta IOS libre."""

    def render_device_batches(
        self,
        device_name: str,
        model: str,
        actions: list[VoiceAction],
        *,
        phone_macs: dict[str, str] | None = None,
    ) -> list[RenderedVoiceBatch]:
        del model
        phone_macs = phone_macs or {}
        grouped: dict[VoicePhase, list[VoiceAction]] = defaultdict(list)
        for action in actions:
            if action.host_device_name == device_name:
                grouped[action.phase].append(action)
        batches = []
        for phase in sorted(grouped):
            phase_actions = sorted(grouped[phase], key=lambda item: item.id)
            body = self._render_body(phase_actions, phone_macs)
            if not body:
                continue
            payload = "\n".join(["enable", "configure terminal", *body, "end", "write memory"])
            batches.append(RenderedVoiceBatch(
                device_name=device_name, phase=phase,
                action_ids=[item.id for item in phase_actions], ios_payload=payload,
                js_call=build_configure_ios_call(device_name, payload),
            ))
        return batches

    def _render_body(self, actions, phone_macs):
        lines = []
        for action in actions:
            if isinstance(action, EnableCallControl):
                if not 1 <= action.max_phones <= 42 or not 1 <= action.max_extensions <= 144:
                    raise ValueError("Packet Tracer CME limits are 42 phones and 144 extensions.")
                lines.extend([
                    "telephony-service", f" max-ephones {action.max_phones}",
                    f" max-dn {action.max_extensions}",
                ])
                if action.registration_required:
                    lines.append(" auto-reg-ephone")
                lines.append(" exit")
            elif isinstance(action, ConfigureCallControlSource):
                address = str(ipaddress.ip_address(action.source_address))
                if not 2000 <= action.signaling_port <= 9999:
                    raise ValueError("Call-control signaling port is outside PT IOS bounds.")
                lines.extend([
                    "telephony-service",
                    f" ip source-address {address} port {action.signaling_port}", " exit",
                ])
            elif isinstance(action, CreateExtension):
                if not action.extension.isascii() or not action.extension.isdigit():
                    raise ValueError("Extension must contain ASCII digits only.")
                lines.extend([
                    f"ephone-dn {action.directory_index}",
                    f" number {action.extension}", " exit",
                ])
            elif isinstance(action, BindPhoneToExtension):
                mac = self._mac(phone_macs.get(action.phone_id, ""))
                phone_type = _PHONE_TYPES.get(action.phone_model.upper())
                if phone_type is None:
                    raise ValueError(f"No trusted PT ephone type for {action.phone_model!r}.")
                lines.extend([
                    f"ephone {action.directory_index}", f" mac-address {mac}",
                    f" type {phone_type}", f" button 1:{action.directory_index}", " exit",
                ])
            elif isinstance(action, ConfigureVoiceDhcpOption):
                if not _POOL_NAME.fullmatch(action.pool_name):
                    raise ValueError("DHCP pool name is outside the trusted IOS subset.")
                address = str(ipaddress.ip_address(action.tftp_address))
                lines.extend([
                    f"ip dhcp pool {action.pool_name}",
                    f" option 150 ip {address}", " exit",
                ])
            elif isinstance(action, GeneratePhoneConfigurationFiles):
                lines.extend(["telephony-service", " create cnf-files", " exit"])
            elif isinstance(action, ConfigureDialRule) and not action.local:
                raise ValueError("Packet Tracer intersite voice rendering is not verified.")
        return lines

    @staticmethod
    def _mac(value: str) -> str:
        compact = re.sub(r"[.:-]", "", value)
        if not _HEX.fullmatch(compact):
            raise ValueError("Phone MAC is missing or malformed.")
        compact = compact.lower()
        return ".".join(compact[index:index + 4] for index in range(0, 12, 4))
