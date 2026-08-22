"""Declared port inventory is not backend-verified port inventory.

A catalogue says which ports a model *should* have.  That is planning
knowledge: enough to choose a model and count its capacity, and not enough to
name a port a backend will accept.  The two were the same thing until a live
run asked Packet Tracer for `FastEthernet0/1` on a device whose ports are
numbered `1/x`.

The distinction is a tier, and only the top one authorises a concrete binding:

``DECLARED``
    Static catalogue knowledge.  Plan with it; never bind with it.
``BACKEND_VERIFIED``
    One backend build actually reported this inventory for this model in this
    module state.  Adequate for a concrete executable binding.
``UNKNOWN``
    Nothing adequate is on record.  Not permission — the absence of evidence
    never becomes evidence of a name.

Evidence is scoped to the dimensions the binding actually depends on: the
physical model, the backend build, and the module state, because a port that
exists only once a card is installed does not exist before it.  Evidence from
another model or another build is not weaker evidence, it is evidence about
something else, and is never reused.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class PortInventoryEvidenceTier(str, Enum):
    DECLARED = "declared"
    BACKEND_VERIFIED = "backend_verified"
    UNKNOWN = "unknown"


def normalized_module_state(modules: list[str] | tuple[str, ...] | None) -> list[str]:
    """Order-independent module state, so two spellings of one state compare equal."""

    return sorted({item.strip() for item in (modules or ()) if item and item.strip()})


class BackendVerifiedPortInventory(BaseModel):
    """What one backend build reported for one model in one module state.

    ``ports`` is the inventory exactly as observed, un-normalised: logical
    interfaces the model also reports stay in the record, because trimming them
    here would quietly turn an observation into an interpretation.
    """

    model: str
    backend: str = "packet_tracer"
    backend_version: str
    installed_modules: list[str] = Field(default_factory=list)
    ports: list[str] = Field(default_factory=list)
    # Names enumerated by the backend that resolve to another physical port.
    # They remain in `ports` as observed evidence, but cannot authorize a
    # second concrete binding.
    port_aliases: dict[str, str] = Field(default_factory=dict)
    source: str = ""

    def matches(
        self,
        model: str,
        *,
        backend: str,
        backend_version: str,
        installed_modules: list[str] | tuple[str, ...] | None = None,
    ) -> bool:
        return (
            self.model == model
            and self.backend == backend
            and self.backend_version == backend_version
            and normalized_module_state(self.installed_modules)
            == normalized_module_state(installed_modules)
        )


class PortInventoryResolution(BaseModel):
    """The tier that applies to one concrete query, and what it permits."""

    model: str
    backend: str
    backend_version: str
    installed_modules: list[str] = Field(default_factory=list)
    tier: PortInventoryEvidenceTier = PortInventoryEvidenceTier.UNKNOWN
    ports: list[str] = Field(default_factory=list)
    port_aliases: dict[str, str] = Field(default_factory=dict)
    reason: str = ""

    @property
    def backend_verified(self) -> bool:
        return self.tier is PortInventoryEvidenceTier.BACKEND_VERIFIED

    @property
    def bindable_ports(self) -> list[str]:
        """Observed names that represent independent exact-link endpoints."""

        return [item for item in self.ports if item not in self.port_aliases]

    def unsupported_ports(self, required: list[str] | tuple[str, ...]) -> list[str]:
        """Required ports this resolution cannot authorise, in a stable order.

        Everything is unsupported when the tier is not BACKEND_VERIFIED: an
        unverified inventory does not partially authorise a name.
        """

        wanted = sorted({item for item in required if item}, key=str.casefold)
        if not self.backend_verified:
            return wanted
        available = set(self.bindable_ports)
        return [item for item in wanted if item not in available]

    def permits(self, required: list[str] | tuple[str, ...]) -> bool:
        return not self.unsupported_ports(required)


def resolve_port_inventory(
    records: list[BackendVerifiedPortInventory] | tuple[BackendVerifiedPortInventory, ...],
    model: str,
    *,
    backend: str,
    backend_version: str,
    installed_modules: list[str] | tuple[str, ...] | None = None,
) -> PortInventoryResolution:
    """Find backend-verified evidence for exactly this model, build and module state.

    Fails closed in every direction that is not an exact match, and says which
    direction it was, so a caller reading UNKNOWN can tell "never measured"
    from "measured somewhere else".
    """

    state = normalized_module_state(installed_modules)
    unknown = PortInventoryResolution(
        model=model,
        backend=backend,
        backend_version=backend_version,
        installed_modules=state,
    )
    if not model or not backend or not backend_version:
        return unknown.model_copy(update={
            "reason": "A model, a backend and an exact build are all required.",
        })

    for record in records:
        if record.matches(
            model,
            backend=backend,
            backend_version=backend_version,
            installed_modules=state,
        ):
            return PortInventoryResolution(
                model=model,
                backend=backend,
                backend_version=backend_version,
                installed_modules=state,
                tier=PortInventoryEvidenceTier.BACKEND_VERIFIED,
                ports=list(record.ports),
                port_aliases=dict(record.port_aliases),
                reason=record.source,
            )

    same_model = [item for item in records if item.model == model]
    if not same_model:
        reason = f"No backend-verified port inventory exists for model {model!r}."
    elif not any(
        item.backend == backend and item.backend_version == backend_version
        for item in same_model
    ):
        reason = (
            f"Port evidence for {model!r} exists for other builds "
            f"({', '.join(sorted({item.backend_version for item in same_model}))}), "
            f"and evidence never migrates across builds."
        )
    else:
        reason = (
            f"Port evidence for {model!r} on {backend_version} was measured in a "
            f"different module state; port shape depends on modules."
        )
    return unknown.model_copy(update={"reason": reason})
