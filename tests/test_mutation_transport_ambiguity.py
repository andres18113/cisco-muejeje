"""Que puede y que no puede afirmarse de una mutacion IOS despachada.

Por que existe:
`PacketTracerConfigurationRuntime` esta documentada como envio ASINCRONO:
`configure_ios` devuelve `self._send(...)`, que es fire-and-forget. Ese bool
significa ENCOLADO, no aplicado -- nadie observa que hace Packet Tracer con el
payload. Estos tests fijan que un despacho no se convierta en certeza de
efecto, que un fallo de encolado no se reintente, y que la verificacion siga
viniendo de releer el estado.

Es el bloqueador que RIPv2 necesita cerrado: una configuracion RIP cuyo envio
quedo ambiguo no puede reintentarse a ciegas ni darse por aplicada.
"""

from __future__ import annotations

from src.packet_tracer_mcp.domain.enterprise.models.configuration_runtime import (
    ActionExecutionStatus,
)
from src.packet_tracer_mcp.infrastructure.execution.configuration_runtime import (
    PacketTracerConfigurationRuntime,
)


class _CountingChannel:
    """Canal fire-and-forget que cuenta despachos y puede fallar el encolado."""

    def __init__(self, *, queues: bool = True) -> None:
        self.payloads: list[str] = []
        self._queues = queues

    def __call__(self, payload: str) -> bool:
        self.payloads.append(payload)
        return self._queues


# -- lo que el transporte puede afirmar ----------------------------------

def test_a_queued_mutation_is_dispatched_exactly_once():
    """Sin reintento ciego: un envio, un despacho."""
    channel = _CountingChannel()

    assert PacketTracerConfigurationRuntime(channel).configure_ios("R1", "router rip\nversion 2")

    assert len(channel.payloads) == 1


def test_a_failed_enqueue_is_not_retried():
    """Si no se pudo encolar, no se reintenta por dentro del transporte."""
    channel = _CountingChannel(queues=False)

    assert not PacketTracerConfigurationRuntime(channel).configure_ios("R1", "router rip")

    assert len(channel.payloads) == 1


def test_the_dispatch_boolean_only_reports_enqueueing():
    """El canal no observa nada de lo que PT haga con el payload.

    Se documenta como test para que nadie lea el `True` como "aplicado": el
    transporte es asincrono y no hay acuse de ejecucion.
    """
    observed: list[str] = []

    def channel(payload: str) -> bool:
        observed.append(payload)
        return True  # encolado; PT podria no ejecutarlo jamas

    runtime = PacketTracerConfigurationRuntime(channel)

    assert runtime.configure_ios("R1", "router rip") is True
    # Lo unico que existe es el payload emitido. Ningun readback, ningun ack.
    assert observed and "configureIosDevice" in observed[0]


def test_a_failed_enqueue_never_reaches_packet_tracer():
    """Fail-closed: el payload no sale del proceso, no puede mutar despues."""
    channel = _CountingChannel(queues=False)
    runtime = PacketTracerConfigurationRuntime(channel)

    applied = runtime.configure_ios("R1", "router rip\nnetwork 10.0.0.0")

    assert applied is False


# -- lo que la aplicacion hace con ese hecho ------------------------------

def _mutation_status(applied: bool):
    from src.packet_tracer_mcp.application.use_cases.apply_configuration import (
        ConfigurationApplicator,
    )
    from src.packet_tracer_mcp.domain.enterprise.models.configuration_runtime import (
        RuntimeActionMutation,
    )

    return ConfigurationApplicator._mutation_status(
        RuntimeActionMutation(action_id="a1", applied=applied),
    )


def test_a_mutation_that_could_not_be_enqueued_is_never_applied():
    assert _mutation_status(False) is not ActionExecutionStatus.APPLIED


def test_a_failed_enqueue_is_a_definite_failure_because_nothing_left_the_process():
    """FAILED es correcto y fail-closed sólo en este caso.

    El payload no llegó a escribirse, así que no puede ejecutarse más tarde.
    """
    assert _mutation_status(False) is ActionExecutionStatus.FAILED


def test_the_applied_status_is_a_dispatch_fact_and_needs_readback_to_mean_effect():
    """APPLIED aquí significa "despachado", no "verificado".

    La distinción es la que E9.5 ya sostiene con `verify()` y VERIFIED: el
    efecto se afirma releyendo el estado, nunca desde el retorno del envío.
    Este test fija la asimetría para que nadie la colapse.
    """
    assert _mutation_status(True) is ActionExecutionStatus.APPLIED
    assert ActionExecutionStatus.APPLIED is not ActionExecutionStatus.VERIFIED


# -- presupuesto de ping: default declarado, y piso para producto ---------

def test_the_ping_budget_is_a_default_and_every_product_caller_meets_the_floor():
    """`SAFE_PING_TIMEOUT_S` es el DEFAULT del ejecutor y el piso de producto.

    No se fuerza dentro del constructor porque los tests pasan 0 a proposito:
    no esperan a ningun backend. Lo que si tiene que sostenerse es que ningun
    sitio PRODUCTIVO construya el ejecutor por debajo del piso -- ahi un
    destino realmente inalcanzable dejaria de poder clasificarse como tal.
    """
    import inspect

    from src.packet_tracer_mcp.infrastructure.execution import (
        enterprise_control_plane_runtime,
        enterprise_security_runtime,
    )
    from src.packet_tracer_mcp.infrastructure.execution.typed_ping import (
        SAFE_PING_TIMEOUT_S,
        TypedPingExecutor,
    )

    executor_default = inspect.signature(
        TypedPingExecutor.__init__,
    ).parameters["timeout_seconds"].default
    assert executor_default == SAFE_PING_TIMEOUT_S

    for module, owner in (
        (enterprise_control_plane_runtime, "PacketTracerControlPlaneRuntime"),
        (enterprise_security_runtime, "PacketTracerEnterpriseSecurityRuntime"),
    ):
        runtime = getattr(module, owner, None)
        if runtime is None:  # pragma: no cover - nombre cambiado
            continue
        budget = inspect.signature(
            runtime.__init__,
        ).parameters["behavior_timeout_seconds"].default
        assert budget >= SAFE_PING_TIMEOUT_S, (
            f"{owner} construye el ping con {budget}s, por debajo del piso "
            f"medido de {SAFE_PING_TIMEOUT_S}s"
        )


def test_the_connectivity_tool_budget_meets_the_floor():
    import inspect

    from src.packet_tracer_mcp.infrastructure.execution.typed_ping import (
        SAFE_PING_TIMEOUT_S,
    )

    source = inspect.getsource(
        __import__(
            "src.packet_tracer_mcp.adapters.mcp.tool_registry",
            fromlist=["register_tools"],
        ).register_tools,
    )
    declared = next(
        line for line in source.splitlines() if "timeout_s: float =" in line
    )

    assert float(declared.split("=")[1].strip().rstrip(",")) >= SAFE_PING_TIMEOUT_S
