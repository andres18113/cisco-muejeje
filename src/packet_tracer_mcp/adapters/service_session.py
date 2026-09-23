"""The production session composition of the enterprise-services product.

This is the wiring that used to be nested inside the MCP tool: one admitted
channel, the E5 and E6 runtimes bound to it, one endpoint reader, one
target-directed inventory snapshot, one secret resolver and one run-record
store. Two routes now use it. The MCP tool composes it with its channel picker,
consulted lazily after A1/A4 exactly as before. The cold-HTTP acceptance
envelope composes it with a selection it bound before any runtime existed.

Sharing the composition does not widen either route. The optional controls are
not reachable from the public tool, which passes none of them, and each of them
can only bound or refuse what the product does: a clock and sleeper for the
runtimes, an allowance that ends nested waits, a scope around the one owned
release dispatch, and an admission check over the compiled effect closure.
"""

from __future__ import annotations

import subprocess
from collections.abc import Callable, Sequence
from contextlib import AbstractContextManager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..application.ports.service_run_record import ServiceRunRecordPort
from ..application.use_cases.apply_enterprise_services import (
    ServiceInvocationBinding,
    ServiceStageRuntimes,
    TransportSelection,
)
from ..domain.enterprise.models.configuration_runtime import RuntimeConfigurationTarget
from ..domain.enterprise.models.deployment import EnvironmentFingerprint
from ..domain.enterprise.models.service_entry import ServiceEffectClosure
from ..domain.enterprise.models.service_run_record import SourceTreeIdentity
from ..infrastructure.execution.endpoint_address_observer import (
    PacketTracerEndpointAddressObserver,
)
from ..infrastructure.execution.enterprise_configuration_runtime import (
    PacketTracerEnterpriseConfigurationRuntime,
)
from ..infrastructure.execution.enterprise_service_runtime import (
    PacketTracerEnterpriseServiceRuntime,
)
from ..infrastructure.execution.secret_resolver import EnvironmentSecretResolver
from ..infrastructure.execution.transport_outcome import BridgeDispatchOutcome


@dataclass(frozen=True)
class SessionControls:
    """Optional bounds a governing caller adds; every default is inert."""

    clock: Callable[[], float] | None = None
    sleeper: Callable[[float], None] | None = None
    wait_allowance: Callable[[], float] | None = None
    owned_release: Callable[[str], AbstractContextManager[None]] | None = None
    effect_admission: Callable[[ServiceEffectClosure], str] | None = None


def compose_service_session(
    *,
    send_and_wait: Callable[[str, float, str | None], str | None],
    dispatch_and_wait: Callable[[str, float, str | None], BridgeDispatchOutcome],
    send_payload: Callable[[str, str | None], bool],
    query_inventory: Callable[[Sequence[str], str | None], list[dict] | dict],
    observe_environment: Callable[[str], EnvironmentFingerprint],
    select_transport: Callable[[], TransportSelection],
    record_store_factory: Callable[[], ServiceRunRecordPort],
    observe_source_tree: Callable[[], SourceTreeIdentity],
    controls: SessionControls | None = None,
) -> Callable[[], ServiceInvocationBinding]:
    """Return the lazy session factory the product use case calls at A5.

    Nothing here runs until the use case asks for the session: selection,
    environment observation, runtime construction and store initialization
    all stay behind A1 parsing and A4 process isolation.
    """
    bounds = controls or SessionControls()

    def bind_session() -> ServiceInvocationBinding:
        """Select and bind every collaborator after A1/A4 admission."""
        transport = select_transport()
        channel = transport.channel

        def bound_send_and_wait(script: str, timeout: float) -> str | None:
            """Read on the one admitted channel, without fallback."""
            return send_and_wait(script, timeout, channel)

        def bound_dispatch_and_wait(
            script: str, timeout: float
        ) -> BridgeDispatchOutcome:
            """Preserve typed dispatch facts on the admitted channel."""
            return dispatch_and_wait(script, timeout, channel)

        def bound_send_payload(script: str) -> bool:
            """Legacy E5 dispatch on the admitted channel, without fallback."""
            return send_payload(script, channel)

        selected_names: tuple[str, ...] | None = None
        raw_inventory: list[dict] | dict | None = None

        def cached_inventory() -> list[dict] | dict:
            """Return the one target-directed inventory snapshot for this run."""
            nonlocal raw_inventory
            if selected_names is None:
                raise RuntimeError("Runtime inventory targets were not selected.")
            if raw_inventory is None:
                raw_inventory = query_inventory(selected_names, channel)
            return raw_inventory

        timing: dict[str, Any] = {}
        if bounds.clock is not None:
            timing["clock"] = bounds.clock
        if bounds.sleeper is not None:
            timing["sleeper"] = bounds.sleeper
        configuration_bounds = dict(timing)
        if bounds.wait_allowance is not None:
            configuration_bounds["wait_allowance"] = bounds.wait_allowance
        service_bounds = dict(timing)
        if bounds.owned_release is not None:
            service_bounds["owned_release"] = bounds.owned_release

        endpoint_reader = PacketTracerEndpointAddressObserver(bound_send_and_wait)
        # One resolver per invocation: admission and the runtime resolve
        # through the same instance, and nothing outlives the call.
        secret_resolver = EnvironmentSecretResolver()
        configuration_runtime = PacketTracerEnterpriseConfigurationRuntime(
            cached_inventory,
            bound_send_payload,
            bound_send_and_wait,
            endpoint_address_observer=endpoint_reader,
            **configuration_bounds,
        )
        service_runtime = PacketTracerEnterpriseServiceRuntime(
            cached_inventory,
            bound_send_and_wait,
            dispatch_and_wait=bound_dispatch_and_wait,
            secret_resolver=secret_resolver,
            **service_bounds,
        )

        def inventory_reader(
            names: Sequence[str],
        ) -> list[RuntimeConfigurationTarget]:
            """Select exact manifest names once, then normalize the snapshot."""
            nonlocal selected_names
            normalized = tuple(dict.fromkeys(str(item) for item in names))
            if selected_names is not None and normalized != selected_names:
                raise RuntimeError("Runtime inventory scope changed within one run.")
            selected_names = normalized
            return configuration_runtime.inventory()

        environment = (
            observe_environment(channel)
            if transport.ready
            else EnvironmentFingerprint()
        )
        return ServiceInvocationBinding(
            runtimes=ServiceStageRuntimes(
                configuration=configuration_runtime,
                services=service_runtime,
            ),
            record_store=record_store_factory(),
            environment_fingerprint=environment,
            transport_selection=transport,
            source_tree=observe_source_tree(),
            endpoint_observer=endpoint_reader,
            inventory_reader=inventory_reader,
            secret_resolver=secret_resolver,
            effect_admission=bounds.effect_admission,
        )

    return bind_session


def observe_source_tree(governed_root: Path) -> SourceTreeIdentity:
    """Observe the executing checkout identity without trusting caller input."""
    try:
        identities = subprocess.run(
            ["git", "rev-parse", "HEAD", "HEAD^{tree}"],
            cwd=governed_root,
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        ).stdout.splitlines()
        if len(identities) != 2 or not all(item.strip() for item in identities):
            return SourceTreeIdentity()
        sha, tree = (item.strip() for item in identities)
        status = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=normal"],
            cwd=governed_root,
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return SourceTreeIdentity()
    return SourceTreeIdentity(sha=sha, tree=tree, dirty=bool(status.strip()))
