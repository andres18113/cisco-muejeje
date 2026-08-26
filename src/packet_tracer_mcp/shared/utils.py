"""Utilidades compartidas."""

from __future__ import annotations
import ipaddress
import re
from collections.abc import Iterable
from pathlib import Path
from typing import Protocol
from .constants import PREFIX_TO_MASK

# Caracteres permitidos en un componente de ruta. Todo lo demás se reemplaza por "_",
# incluidos los separadores (/ \), los dos puntos de unidad (C:) y los NUL.
_UNSAFE_PATH_CHARS = re.compile(r"[^A-Za-z0-9._-]")
_UNSAFE_IOS_IDENTIFIER_CHARS = re.compile(r"[^A-Za-z0-9_.-]")
_IOS_INTERFACE = re.compile(r"^[A-Za-z][A-Za-z0-9-]*[0-9][A-Za-z0-9/.-]*$")

# Nombres reservados por Windows: crear "CON.txt" o "NUL" falla de forma opaca.
_WINDOWS_RESERVED = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}

_MAX_COMPONENT_LEN = 100


class _TypedPingEvidence(Protocol):
    reachable: bool
    fresh_output_observed: bool
    window_strategy: str
    failure_reason: str
    attempts: int
    statistics: str
    dispatched_destination: str
    observed_device_name: str
    device_identity_provenance: str
    device_identity_evidence: str


def serialize_typed_ping_evidence(
    result: _TypedPingEvidence,
) -> dict[str, object]:
    """Serialize the stable public evidence carried by a typed ping result."""
    return {
        "reachable": result.reachable,
        "fresh_output_observed": result.fresh_output_observed,
        "window_strategy": result.window_strategy,
        "failure_reason": result.failure_reason,
        "attempts": result.attempts,
        "statistics": result.statistics,
        "dispatched_destination": result.dispatched_destination,
        "observed_device_name": result.observed_device_name,
        "device_identity_provenance": result.device_identity_provenance,
        "device_identity_evidence": result.device_identity_evidence,
    }


def typed_ping_behavior_transition_verified(
    before: Iterable[_TypedPingEvidence],
    after: Iterable[_TypedPingEvidence],
) -> bool:
    """Require fresh unreachable controls before and fresh reachability after."""
    negative = tuple(before)
    positive = tuple(after)
    return (
        bool(negative)
        and bool(positive)
        and all(
            item.fresh_output_observed and not item.reachable
            for item in negative
        )
        and all(
            item.fresh_output_observed and item.reachable
            for item in positive
        )
    )


def safe_name_component(name: str, fallback: str = "topology") -> str:
    """Reduce un nombre a un componente de ruta seguro (un solo nivel, sin escapes).

    Neutraliza separadores, "..", letras de unidad y nombres reservados de Windows.
    Los espacios se mapean a "_" — se conserva el comportamiento histórico para no
    cambiar los nombres de proyectos ya existentes en disco.
    """
    cleaned = _UNSAFE_PATH_CHARS.sub("_", (name or "").strip())
    # Un componente compuesto solo de puntos ("." o "..") es un escape, no un nombre.
    if not cleaned.strip("._-") or set(cleaned) <= {"."}:
        return fallback
    if cleaned.split(".")[0].upper() in _WINDOWS_RESERVED:
        cleaned = f"_{cleaned}"
    return cleaned[:_MAX_COMPONENT_LEN]


def js_escape(s: str) -> str:
    """Escapa una string para insertarla en un literal JS.

    Un literal JS no puede cruzar un fin de línea, y JS trata U+2028/U+2029 como
    tales. Sin escaparlos, un nombre con un salto no "se cuela" como código: rompe
    el parseo y el comando entero se pierde en silencio dentro del catch del
    bridge, que es peor que fallar ruidosamente.

    Para construir una llamada entera preferí `json.dumps`; esto es para los
    casos en que hay que interpolar dentro de un literal ya existente.
    """
    return (
        s.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("'", "\\'")
        .replace("\n", "\\n")
        .replace("\r", "\\r")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )


def safe_ios_identifier(value: str, fallback: str = "ITEM", max_length: int = 32) -> str:
    """Normaliza nombres internos que ocupan un único token IOS."""
    cleaned = _UNSAFE_IOS_IDENTIFIER_CHARS.sub("_", (value or "").strip())
    return (cleaned.strip("._-") or fallback)[:max_length]


def validate_ios_interface_name(value: str) -> str:
    """Rechaza interfaces que podrían transformarse en comandos IOS adicionales."""
    candidate = (value or "").strip()
    if len(candidate) > 64 or not _IOS_INTERFACE.fullmatch(candidate):
        raise ValueError(f"Invalid IOS interface name: {value!r}")
    return candidate


#: Formas largas y su abreviatura IOS, de la más específica a la más corta: el
#: orden es parte del contrato, porque `fastethernet` empieza por `fast` y
#: `tengigabitethernet` por `tengig`.
_INTERFACE_ALIASES = (
    ("serial", "se"),
    ("tengigabitethernet", "te"),
    ("tengig", "te"),
    ("gigabitethernet", "gi"),
    ("gig", "gi"),
    ("fastethernet", "fa"),
    ("fast", "fa"),
    ("ethernet", "et"),
    ("eth", "et"),
)


def same_interface_name(observed: str, expected: str) -> bool:
    """True si ambas cadenas nombran UN mismo puerto físico.

    IOS abrevia la interfaz en casi toda salida tabular (`Fa0/1`) mientras el
    plan tipado nunca lo hace (`FastEthernet0/1`).  Comparar en crudo convierte
    una lectura correcta en una fila ausente, así que la reconciliación vive
    acá una sola vez: dos tablas de alias serían dos juegos de errores.
    """

    def normalize(value: str) -> str:
        result = (value or "").casefold().replace(" ", "")
        for long_name, short_name in _INTERFACE_ALIASES:
            if result.startswith(long_name):
                return short_name + result[len(long_name):]
        return result

    normalized = normalize(observed)
    return bool(normalized) and normalized == normalize(expected)


def interpret_ping(stat_line: str) -> bool:
    """True si una línea de estadística de ping indica al menos un paquete recibido.

    Cubre los dos formatos que produce Packet Tracer:
      - Host (PC/Server): "Packets: Sent = 4, Received = 4, Lost = 0 (0% loss)"
      - IOS (router/switch): "Success rate is 100 percent (4/5)"
    """
    if not stat_line:
        return False
    m = re.search(r"Received\s*=\s*(\d+)", stat_line)
    if m:
        return int(m.group(1)) > 0
    m = re.search(r"Success rate is (\d+) percent", stat_line)
    if m:
        return int(m.group(1)) > 0
    m = re.search(r"\((\d+)/(\d+)\)", stat_line)
    if m:
        return int(m.group(1)) > 0
    return False


def normalize_ip(value: str) -> str:
    """Valida una IP de host y devuelve su representación canónica.

    Esta validación se usa antes de construir comandos de consola para Packet
    Tracer. Un destino de ``ping`` sólo puede ser una dirección IPv4 o IPv6, no
    texto arbitrario que pueda alterar el comando o el literal JavaScript.
    """
    return str(ipaddress.ip_address(value.strip()))


def resolve_within(base: Path, *parts: str) -> Path:
    """Resuelve `parts` bajo `base` y verifica que el resultado no se escape.

    Sanitizar el nombre es la primera barrera; esta comprobación posterior a
    resolve() es la que realmente decide, porque cubre symlinks y cualquier caso
    que la sanitización no haya previsto.
    """
    base_resolved = Path(base).resolve()
    candidate = base_resolved.joinpath(*parts).resolve()
    if candidate != base_resolved and not candidate.is_relative_to(base_resolved):
        raise ValueError(
            f"Ruta fuera del directorio base: {candidate} no está dentro de {base_resolved}"
        )
    return candidate


def prefix_to_mask(prefix: int) -> str:
    """Convierte un prefijo CIDR a máscara decimal."""
    if prefix in PREFIX_TO_MASK:
        return PREFIX_TO_MASK[prefix]
    bits = (0xFFFFFFFF << (32 - prefix)) & 0xFFFFFFFF
    return f"{(bits >> 24) & 0xFF}.{(bits >> 16) & 0xFF}.{(bits >> 8) & 0xFF}.{bits & 0xFF}"


def wildcard_mask(network: ipaddress.IPv4Network) -> str:
    """Calcula la wildcard mask de una red."""
    mask_int = int(network.netmask)
    wildcard_int = mask_int ^ 0xFFFFFFFF
    return str(ipaddress.IPv4Address(wildcard_int))


def first_ip(interfaces: dict[str, str]) -> str:
    """Devuelve la primera IP de un dict de interfaces."""
    for ip_cidr in interfaces.values():
        return ip_cidr.split("/")[0]
    return "0.0.0.0"
