"""Productive PoE observation: switch identity and ports in, semantics out.

Why this exists on top of the typed rule:
``classify_poe_inline_delivery`` decides correctly, but it leaves the caller to
wire the conditions that make its answer valid -- freshness, completeness,
dispatch integrity and attribution to the exact switch. Getting any one of them
wrong is silent, and it always fails in the dangerous direction: passing
``capture_complete=True`` over a truncated capture turns a page break into a
NOT_DELIVERING on a port that is powered, and skipping
``device_identity_provenance`` attributes one switch's table to another.

``observe_poe_inline_status`` takes an exact switch identity and the exact ports
being asked about. It accepts no IOS and no JavaScript -- there is no parameter
through which a command could arrive -- and every gate it cannot satisfy comes
back UNOBSERVABLE with a reason instead of becoming a negative.

Calibrated in governed run `poe1-c4fae886` on PT 9.0.1.0858, binding
3560-24PS/FastEthernet0/1 -> 7960/Switch. This module observes; it authorizes
nothing. The authorized PoE claim method is still the visual one, and no port
coverage is extrapolated from a reading taken here.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from enum import Enum

from .command_dispatch import DispatchClassification, is_command_corrupted
from .ios_terminal import (
    DeviceIdentityProvenance,
    IosCommandResult,
    IosQualificationQueryId,
    PoEInlineDelivery,
    PoEInlineRow,
    classify_poe_inline_delivery,
    parse_show_power_inline,
)

# Misma forma que ya acepta el ejecutor gobernado para una interfaz registrada.
# No es una validacion cosmetica: es lo que impide que un "puerto" traiga un
# pipe, un espacio o un comando entero adentro.
_PORT_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9./:-]{0,79}$")


class PoEInlineObservationStatus(str, Enum):
    OBSERVED = "observed"
    UNOBSERVABLE = "unobservable"


@dataclass(frozen=True)
class PoEInlinePortObservation:
    """Lo que la tabla dice de UN puerto pedido, y la fila que lo sostiene."""

    port: str
    delivery: PoEInlineDelivery
    row: PoEInlineRow | None = None


@dataclass(frozen=True)
class PoEInlineObservation:
    """Una lectura completa, con todo lo que la hace creible o la anula."""

    switch_identity: str
    status: PoEInlineObservationStatus
    ports: tuple[PoEInlinePortObservation, ...] = ()
    refusal_reason: str = ""
    capture_complete: bool = False
    fresh_output_observed: bool = False
    device_identity_provenance: str = (
        DeviceIdentityProvenance.NOT_OBSERVED.value
    )
    observed_device_name: str = ""
    # Diagnostico. Medido identico en los cuatro estados de la calibracion,
    # incluido aquel en que ningun puerto entrega: describe, no decide.
    summary_used_watts: float | None = None
    raw_output: str = ""

    @property
    def delivering_ports(self) -> tuple[str, ...]:
        return tuple(
            item.port for item in self.ports
            if item.delivery is PoEInlineDelivery.DELIVERING
        )


class GovernedPoEInlineObserver:
    """Read inline-power delivery for exact ports on one exact switch."""

    def __init__(self, executor) -> None:
        self._executor = executor

    def observe_poe_inline_status(
        self,
        exact_switch_identity: str,
        exact_expected_ports: Sequence[str],
    ) -> PoEInlineObservation:
        """Observe the exact ports, or refuse. Never reports an unproven negative.

        The caller supplies identity and ports only. The IOS text comes from the
        closed qualification registry, so there is no path by which a command
        reaches Packet Tracer from here.
        """
        ports = tuple(exact_expected_ports)
        rejection = _reject_input(exact_switch_identity, ports)
        if rejection is not None:
            # Antes de despachar: rechazar despues ya habria tocado PT para nada.
            return _refused(exact_switch_identity, ports, rejection)

        result = self._executor.qualify(
            exact_switch_identity, IosQualificationQueryId.SHOW_POWER_INLINE,
        )
        return _interpret(exact_switch_identity, ports, result)


def _reject_input(identity: str, ports: tuple[str, ...]) -> str | None:
    if not isinstance(identity, str) or not identity or identity != identity.strip():
        return "The switch identity must be exact, non-empty and unpadded."
    if not ports:
        return "At least one exact expected port is required."
    if len(set(ports)) != len(ports):
        return "The expected ports must be distinct."
    if any(
        not isinstance(port, str) or not _PORT_NAME.fullmatch(port)
        for port in ports
    ):
        return "Every expected port must be a valid interface name."
    return None


def _refused(
    identity: str,
    ports: Iterable[str],
    reason: str,
    result: IosCommandResult | None = None,
) -> PoEInlineObservation:
    """Un rechazo responde por CADA puerto pedido, y siempre UNOBSERVABLE."""
    return PoEInlineObservation(
        switch_identity=identity,
        status=PoEInlineObservationStatus.UNOBSERVABLE,
        ports=tuple(
            PoEInlinePortObservation(port, PoEInlineDelivery.UNOBSERVABLE)
            for port in ports
        ),
        refusal_reason=reason,
        capture_complete=bool(result.output_complete) if result else False,
        fresh_output_observed=bool(result.fresh_output_observed) if result else False,
        device_identity_provenance=(
            result.device_identity_provenance if result
            else DeviceIdentityProvenance.NOT_OBSERVED.value
        ),
        observed_device_name=result.observed_device_name if result else "",
        raw_output=result.output if result else "",
    )


def _interpret(
    identity: str,
    ports: tuple[str, ...],
    result: IosCommandResult,
) -> PoEInlineObservation:
    reason = _gate(identity, result)
    if reason is not None:
        return _refused(identity, ports, reason, result)

    table = parse_show_power_inline(result.output)
    observations = tuple(
        PoEInlinePortObservation(
            port=port,
            delivery=classify_poe_inline_delivery(
                result.output, port, capture_complete=result.output_complete,
            ),
            row=table.row_for(port),
        )
        for port in ports
    )
    return PoEInlineObservation(
        switch_identity=identity,
        status=PoEInlineObservationStatus.OBSERVED,
        ports=observations,
        capture_complete=result.output_complete,
        fresh_output_observed=result.fresh_output_observed,
        device_identity_provenance=result.device_identity_provenance,
        observed_device_name=result.observed_device_name,
        summary_used_watts=table.summary_used_watts,
        raw_output=result.output,
    )


def _gate(identity: str, result: IosCommandResult) -> str | None:
    """Cada condicion que, si falta, vuelve la lectura inutilizable.

    Completitud NO esta aca: la calibracion midio que sólo condiciona a la
    AUSENCIA de fila, y `classify_poe_inline_delivery` ya la aplica por puerto.
    Subirla a este nivel descartaria una fila encendida que se ve perfectamente.
    """
    if not result.executed:
        return "The registered query did not execute."
    if not result.fresh_output_observed:
        return "The captured window was not proven fresh."
    if is_command_corrupted(DispatchClassification(result.dispatch_classification)):
        return "The dispatched command was proven corrupted."
    if (
        result.device_identity_provenance
        != DeviceIdentityProvenance.CONFIRMED_UNIQUE.value
    ):
        return "The capture carries no unique device attribution."
    observed = result.observed_device_name
    if observed and observed != identity:
        return "The capture was attributed to another device."
    if not parse_show_power_inline(result.output).rows:
        return "The output carries no inline-power table."
    return None
