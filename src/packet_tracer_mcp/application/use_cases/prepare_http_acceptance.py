"""Derive a scalable acceptance scope offline, through the product itself.

A schema 2 grant has to name the digest of a scope the operator cannot write
by hand: every selected client, its placement, its path and its readiness
groups, and the exact cost ceiling. This use case derives it with the very
code a governed run executes. It invokes the unchanged product use case over a
planning session that has no transport at all: its runtimes answer the
inventory from the persisted manifest, every endpoint reads as unaddressed,
records stay in memory, and the effect admission captures the compiled closure
and refuses it. The product therefore stops at A11, before E1, with nothing
dispatched and nothing persisted, and the captured closure is the one a run on
the same manifest, intent and build would admit.

It never contacts Packet Tracer, opens a channel or writes a store.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from ...domain.enterprise.models.configuration_runtime import (
    RuntimeConfigurationTarget,
)
from ...domain.enterprise.models.deployment import DeploymentManifest
from ...domain.enterprise.models.forwarding import ForwardingAddressObservation
from ...domain.enterprise.models.scalable_http_acceptance import (
    SCALABLE_GRANT_SCHEMA_VERSION,
    SCALABLE_PROFILE,
    AcceptanceScope,
    derive_scope,
)
from ...domain.enterprise.models.service_entry import ServiceEffectClosure
from ...domain.enterprise.models.service_run_record import (
    ServiceRunRecord,
    SourceTreeIdentity,
)
from ..ports.service_run_record import DeploymentManifestPort
from .apply_enterprise_services import (
    ServiceInvocationBinding,
    ServiceStageRuntimes,
    TransportSelection,
    apply_enterprise_services,
)

#: What the planning session's admission answers; the product records it as
#: an A11 refusal, which is the proof that nothing was dispatched.
PLANNING_ONLY = "planning_only:no_effect_is_dispatched"


class _PlanningIsolation:
    """A4's answer for a session that has no transport to isolate."""

    class _State:
        value = "planning_only"

    isolated = True
    state = _State()

    @staticmethod
    def render() -> str:
        return "planning session: no transport, no runtime, no effect"

    def ensure_isolated(self) -> _PlanningIsolation:
        return self


class _ManifestInventory:
    """Answer every inventory question from the persisted manifest."""

    def __init__(self, manifest: DeploymentManifest) -> None:
        self._targets = [
            RuntimeConfigurationTarget(
                device_name=item.deployed_name,
                model=item.model,
                interfaces=list(item.ports),
                runtime_identifier=item.runtime_identifier,
                runtime_fingerprint=item.runtime_fingerprint,
            )
            for item in manifest.bindings
        ]

    def inventory(self) -> list[RuntimeConfigurationTarget]:
        return [item.model_copy(deep=True) for item in self._targets]

    def read(self, names) -> list[RuntimeConfigurationTarget]:
        wanted = set(names)
        return [item for item in self.inventory() if item.device_name in wanted]

    def apply_actions(self, actions):
        raise RuntimeError("a planning session applies nothing")

    def verify(self, expectations):
        raise RuntimeError("a planning session verifies nothing")


class _UnaddressedEndpoints:
    """Read every endpoint as fresh and unaddressed: the cold precondition."""

    @staticmethod
    def observe(
        runtime_device_name: str, interface: str
    ) -> ForwardingAddressObservation:
        return ForwardingAddressObservation(
            runtime_device_name=runtime_device_name,
            interface=interface,
            device_found=True,
            port_found=True,
            address_channel=True,
            ipv4="",
            fresh_evidence=True,
            evidence_method="planning_session_cold_precondition",
        )


@dataclass
class _MemoryRecords:
    """Keep the product's write-ahead records in memory, never on disk."""

    records: list[ServiceRunRecord] = field(default_factory=list)

    def begin(self, record: ServiceRunRecord) -> str:
        self.records.append(record.model_copy(deep=True))
        return "memory://planning"

    advance = begin
    complete = begin

    def load(self, deployment_id: str, run_id: str) -> ServiceRunRecord:
        raise LookupError("a planning session loads nothing")

    def retained_result_for(self, deployment_id: str, **identity) -> None:
        return None


@dataclass(frozen=True)
class PreparedScope:
    """The scope a schema 2 grant must name, and how it was derived."""

    scope: AcceptanceScope | None
    closure: ServiceEffectClosure | None
    findings: tuple[str, ...]
    product_refusal: str = ""

    def grant_skeleton(self) -> dict[str, object]:
        """Return the derived grant fields; the operator supplies the rest."""
        if self.scope is None:
            return {}
        cost = self.scope.cost
        return {
            "schema_version": SCALABLE_GRANT_SCHEMA_VERSION,
            "profile": SCALABLE_PROFILE,
            "deployment_id": self.scope.deployment_id,
            "manifest_hash": self.scope.manifest_hash,
            "physical_topology_hash": self.scope.physical_topology_hash,
            "servers": [item.name for item in self.scope.servers],
            "clients": [item.name for item in self.scope.clients],
            "scope_sha256": self.scope.digest(),
            "max_operations": cost.max_operations,
            "max_seconds": cost.max_seconds,
            "reserve_operations": cost.reserve_operations,
            "reserve_seconds": cost.reserve_seconds,
        }


def prepare_http_acceptance(
    intent_json: str,
    *,
    deployment_id: str,
    build: str,
    marker: str,
    manifest_store: DeploymentManifestPort,
    source_tree: SourceTreeIdentity,
    now=None,
) -> PreparedScope:
    """Derive the scope of one scalable attempt without any effect."""
    captured: dict[str, ServiceEffectClosure] = {}

    def admission(closure: ServiceEffectClosure) -> str:
        captured["closure"] = closure
        return PLANNING_ONLY

    manifest = manifest_store.latest_by_deployment_id(deployment_id)
    if manifest is None:
        return PreparedScope(None, None, ("manifest_missing",))
    inventory = _ManifestInventory(manifest)

    def session() -> ServiceInvocationBinding:
        return ServiceInvocationBinding(
            runtimes=ServiceStageRuntimes(configuration=inventory, services=inventory),
            record_store=_MemoryRecords(),
            environment_fingerprint=manifest.environment_fingerprint,
            transport_selection=TransportSelection(
                channel="file", fixed_at=datetime(2000, 1, 1), ready=True
            ),
            source_tree=source_tree,
            endpoint_observer=_UnaddressedEndpoints(),
            inventory_reader=inventory.read,
            effect_admission=admission,
        )

    result = apply_enterprise_services(
        intent_json,
        deployment_id=deployment_id,
        packet_tracer_version=build,
        import_preflight=_PlanningIsolation(),
        manifest_store=manifest_store,
        session_factory=session,
        run_label="planning-only",
        now=now,
    )
    closure = captured.get("closure")
    if closure is None:
        return PreparedScope(
            None,
            None,
            (f"product_refused_before_closure:{result.refusal_code.value}",),
            product_refusal=result.blocked_reason,
        )
    scope, findings = derive_scope(closure, marker)
    return PreparedScope(scope, closure, findings)
