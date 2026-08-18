"""Packet Tracer adapter for fresh serial-controller orientation read-back."""

from __future__ import annotations

from collections.abc import Callable

from ...application.use_cases.observe_serial_orientation import (
    SerialControllerObservation,
)
from ...domain.enterprise.models.deployment import SerialEndpointOrientation
from .ios_terminal import (
    ControlledIosExecutor,
    OperationalQueryId,
    parse_serial_controller,
)


class PacketTracerSerialOrientationRuntime:
    """Observe DCE/DTE through one registered, read-only IOS query.

    The query is qualified for bounded multi-page capture
    (``TD-ORIENTATION-PAGER-001``): on PT ``9.0.1.0858`` the controller output
    of a 2911 with an HWIC-2T never fits one page.  The pager mechanics live
    entirely inside the executor -- this adapter only ever asks whether the
    logical read is COMPLETE, and refuses everything else.
    """

    def __init__(
        self,
        send_and_wait: Callable[[str, float], str | None],
        *,
        ios_executor: ControlledIosExecutor | None = None,
    ) -> None:
        self._ios = ios_executor or ControlledIosExecutor(send_and_wait)

    @property
    def ios_executor(self) -> ControlledIosExecutor:
        return self._ios

    def observe_serial_controller(
        self,
        device_name: str,
        interface: str,
    ) -> SerialControllerObservation:
        result = self._ios.execute(
            device_name,
            OperationalQueryId.SHOW_CONTROLLERS_SERIAL,
            interface=interface,
        )
        # Cada dimensión se conserva por separado: que la consulta se ejecutara,
        # que la ventana fuera fresca, que la lectura lógica cerrara completa,
        # que hubiera truncamiento, que el texto se pudiera tipar y que nombrara
        # exactamente la interfaz pedida. Colapsarlas en un solo booleano es lo
        # que hace imposible después distinguir "paginado pero completo" de
        # "truncado".
        base = {
            "device_name": device_name,
            "interface": interface,
            "executed": result.executed,
            "fresh_evidence": result.fresh_output_observed,
            "complete": result.output_complete,
            "truncated": result.truncated_by_pager,
            "pages_captured": result.pager_pages_captured,
            "pagination": result.pager_continuation,
            "evidence_method": "fresh_show_controllers_serial",
        }
        if (
            result.device_name != device_name
            or result.query_id is not OperationalQueryId.SHOW_CONTROLLERS_SERIAL
        ):
            return SerialControllerObservation(
                **base,
                message="IOS result identity does not match the registered query target.",
            )
        if not result.executed:
            return SerialControllerObservation(
                **base,
                message=result.failure_reason or "Registered controller query was not executed.",
            )
        if not result.fresh_output_observed:
            return SerialControllerObservation(
                **base,
                message="Registered controller query produced no fresh command window.",
            )
        if not result.output_complete:
            # Una primera página que ya muestre DCE/DTE no alcanza: lo que no se
            # capturó no se sabe, y leerlo igual sería exactamente el atajo que
            # el flag de truncamiento existe para impedir.
            return SerialControllerObservation(
                **base,
                message=(
                    result.failure_reason
                    or "Registered controller query was truncated by the pager."
                ),
            )
        parsed = parse_serial_controller(result.output)
        if parsed is None:
            return SerialControllerObservation(
                **base,
                message="Fresh controller output contained no typed DCE/DTE state.",
            )
        base["parseable"] = True
        if not parsed.interface or parsed.interface.casefold() != interface.casefold():
            return SerialControllerObservation(
                **base,
                message=(
                    f"Fresh controller output named interface {parsed.interface!r}, "
                    f"not exact bound interface {interface!r}."
                ),
            )
        base["interface_identity_match"] = True
        orientation = {
            "dce": SerialEndpointOrientation.DCE,
            "dte": SerialEndpointOrientation.DTE,
        }.get(parsed.endpoint_role, SerialEndpointOrientation.UNRESOLVED)
        if orientation is SerialEndpointOrientation.UNRESOLVED:
            return SerialControllerObservation(
                **base,
                message="Fresh controller output carried an unknown endpoint role.",
            )
        if (
            orientation is SerialEndpointOrientation.DTE
            and parsed.clock_rate_bps is not None
        ):
            return SerialControllerObservation(
                **base,
                message="DTE controller output unexpectedly reported a local clock rate.",
            )
        return SerialControllerObservation(
            **{**base, "interface": parsed.interface},
            orientation=orientation,
            clock_rate_bps=parsed.clock_rate_bps,
            observed=True,
            message="Fresh exact serial-controller orientation observed.",
        )
