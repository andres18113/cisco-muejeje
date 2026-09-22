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
from ...infrastructure.execution.secret_resolver import EnvironmentSecretResolver
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
        Apply governed Server-PT services to an existing deployment.

        The tool binds a DeploymentManifest produced by pt_live_deploy; it
        deploys no topology and deletes no operator resource. The bounded path
        is one site and segment with a static Server-PT and wired PC-PT clients
        on one access switch. DNS/HTTP use the documentary baseline. Mail and
        delegated Server-PT DHCP compile as candidates but remain unavailable
        under the default UNKNOWN capability records.

        Parameters:
        - intent_json: EnterpriseIntent JSON with the requested services; DNS
          requires an explicit address and DHCP requires canonical identities.
        - deployment_id: the already verified physical deployment identity.
        - packet_tracer_version: the exact build, equal to the manifest and the
          freshly observed environment fingerprint.
        - run_label: display metadata; it chooses no path and overwrites no run.

        Returns JSON with per-service and per-client checks, the actual E5
        effect scope, effect/residue uncertainty, owned-resource releases,
        capability provenance and the durable run-record path. Offline results
        never promote a Packet Tracer capability.
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
            # One resolver per invocation: admission and the runtime resolve
            # through the same instance, and nothing outlives the call.
            secret_resolver = EnvironmentSecretResolver()
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
                secret_resolver=secret_resolver,
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
                secret_resolver=secret_resolver,
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
