"""MCP registration for the enterprise-services product entry point.

Translation only. The tool turns four strings into one application call and
one application result into JSON, and it decides nothing: no orchestration, no
transport policy of its own, no domain rule. Everything a caller could get
wrong - an unparseable intent, a deployment that does not exist, a build that
disagrees with the manifest, a process that is not the live one - is refused by
the use case, through the same code path the offline tests drive.

The one thing that happens here and nowhere else is composition of the
production wiring: the channel is picked ONCE and both runtimes are bound to
it, so E5 and E6 cannot end up talking over different transports within one
invocation.
"""

from __future__ import annotations

import json
import subprocess
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ...application.use_cases.apply_enterprise_services import (
    ServiceInvocationBinding,
    ServiceStageRuntimes,
    TransportSelection,
    apply_enterprise_services,
)
from ...domain.enterprise.models.configuration_runtime import RuntimeConfigurationTarget
from ...domain.enterprise.models.deployment import EnvironmentFingerprint
from ...domain.enterprise.models.service_run_record import SourceTreeIdentity
from ...infrastructure.execution.endpoint_address_observer import (
    PacketTracerEndpointAddressObserver,
)
from ...infrastructure.execution.enterprise_configuration_runtime import (
    PacketTracerEnterpriseConfigurationRuntime,
)
from ...infrastructure.execution.enterprise_service_runtime import (
    PacketTracerEnterpriseServiceRuntime,
)
from ...infrastructure.execution.import_isolation_preflight import (
    ImportIsolationPreflight,
)
from ...infrastructure.execution.transport_outcome import BridgeDispatchOutcome
from ...infrastructure.persistence.deployment_manifest_store import (
    DeploymentManifestStore,
)
from ...infrastructure.persistence.service_run_record_store import (
    ServiceRunRecordStore,
)

#: The checkout this package was loaded from. The preflight compares the live
#: interpreter and the loaded package against it, so it is read from the
#: package location rather than from a working directory a caller controls.
GOVERNED_ROOT = Path(__file__).resolve().parents[3].parent


def register_service_tools(
    mcp: Any,
    *,
    send_and_wait: Callable[[str, float, str | None], str | None],
    dispatch_and_wait: Callable[[str, float, str | None], BridgeDispatchOutcome],
    send_payload: Callable[[str, str | None], bool],
    query_inventory: Callable[[Sequence[str], str | None], list[dict] | dict],
    pick_channel: Callable[[], str],
    observe_environment: Callable[[str], EnvironmentFingerprint],
    governed_root: Path = GOVERNED_ROOT,
) -> None:
    """Register `pt_apply_enterprise_services` on the enterprise surface.

    The registry passes its own closure-scoped transport helpers, so the tool
    shares the one bridge session the rest of the surface already uses instead
    of opening a second one.
    """

    @mcp.tool()
    def pt_apply_enterprise_services(
        intent_json: str,
        deployment_id: str,
        packet_tracer_version: str,
        run_label: str = "",
    ) -> str:
        """
        Aplica y verifica los servicios DNS y HTTP de un despliegue existente.

        Trabaja sobre un DeploymentManifest ya producido por pt_live_deploy: no
        despliega topología, no borra nada del usuario y no limpia la topología
        al terminar. Solo libera los clientes temporales que la propia
        verificación creó.

        Alcance soportado (R-NET-01): un sitio, un segmento, un Server-PT
        estático y los PC-PT estáticos de ese mismo segmento. Un cliente fuera
        del segmento del host se rechaza en vez de darse por bueno.

        Parámetros:
        - intent_json: EnterpriseIntent en JSON, con los servicios pedidos. Un
          servicio DNS debe declarar su address explícita.
        - deployment_id: identificador del despliegue físico ya verificado.
        - packet_tracer_version: build exacta; debe coincidir con la del
          manifest, y además se valida el entorno actual contra el manifest.
        - run_label: etiqueta de presentación. No elige ruta ni sobrescribe
          ninguna corrida.

        Devuelve JSON con el resultado por servicio y POR CLIENTE, el alcance
        E5 aplicado, la incertidumbre de efecto y de residuo, las liberaciones
        de recursos propios y la ruta del registro persistido. Toda capacidad
        DNS/HTTP usada se declara como documentary_baseline: todavía no existe
        una corrida LIVE registrada que la promueva.
        """

        def bind_session() -> ServiceInvocationBinding:
            """Select and bind every collaborator after A1/A4 admission."""
            channel = pick_channel()
            fixed_at = datetime.now(UTC)
            transport = TransportSelection(
                channel=channel,
                fixed_at=fixed_at,
                ready=channel in {"http", "file"},
                detail=(
                    ""
                    if channel in {"http", "file"}
                    else "Packet Tracer is not connected on any channel."
                ),
            )

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

            endpoint_reader = PacketTracerEndpointAddressObserver(
                bound_send_and_wait,
            )
            configuration_runtime = PacketTracerEnterpriseConfigurationRuntime(
                cached_inventory,
                bound_send_payload,
                bound_send_and_wait,
                endpoint_address_observer=endpoint_reader,
            )
            service_runtime = PacketTracerEnterpriseServiceRuntime(
                cached_inventory,
                bound_send_and_wait,
                dispatch_and_wait=bound_dispatch_and_wait,
            )

            def inventory_reader(
                names: Sequence[str],
            ) -> list[RuntimeConfigurationTarget]:
                """Select exact manifest names once, then normalize the snapshot."""
                nonlocal selected_names
                normalized = tuple(dict.fromkeys(str(item) for item in names))
                if selected_names is not None and normalized != selected_names:
                    raise RuntimeError(
                        "Runtime inventory scope changed within one run."
                    )
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
                record_store=ServiceRunRecordStore(),
                environment_fingerprint=environment,
                transport_selection=transport,
                source_tree=_observe_source_tree(governed_root),
                endpoint_observer=endpoint_reader,
                inventory_reader=inventory_reader,
            )

        result = apply_enterprise_services(
            intent_json,
            deployment_id=deployment_id,
            packet_tracer_version=packet_tracer_version.strip(),
            manifest_store_factory=DeploymentManifestStore,
            import_preflight=ImportIsolationPreflight(governed_root),
            record_store_factory=ServiceRunRecordStore,
            session_factory=bind_session,
            run_label=run_label,
        )
        return json.dumps(result.compact_summary(), indent=2, ensure_ascii=False)


def _observe_source_tree(governed_root: Path) -> SourceTreeIdentity:
    """Observe the executing checkout identity without trusting caller input."""
    try:
        sha = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=governed_root,
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        ).stdout.strip()
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
    return SourceTreeIdentity(sha=sha, dirty=bool(status.strip()))
