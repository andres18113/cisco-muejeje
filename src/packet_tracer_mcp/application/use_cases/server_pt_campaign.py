"""Server-PT campaign identities and the execution purpose each one carries.

A campaign is selected by its identity and its charter digest together, never
by a flag. Its purpose decides what source authority a LIVE phase needs:

- `delivery` (C31): the clean HEAD must be published as its upstream and an
  exact-SHA CI run must be green for it. Nothing about this changed.
- `experimental` (FASTLOOP): a clean, committed local checkpoint is enough,
  and a CI claim is refused outright. An experimental phase therefore can
  never borrow an ancestor's CI, and an experimental grant never re-derives as
  a delivery one, because re-derivation always uses the caller's campaign.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, StrEnum
from typing import Protocol

from ...domain.enterprise.models.service_qualification import RepositoryIdentity


class ExecutionPurpose(StrEnum):
    """Why a campaign contacts Packet Tracer; it bounds what it may claim."""

    __str__ = Enum.__str__

    DELIVERY = "delivery"
    EXPERIMENTAL = "experimental"


class ExactCiEvidenceLike(Protocol):
    """Read-only exact-SHA CI result a delivery phase must be sealed with."""

    run_id: int
    head_sha: str
    url: str


@dataclass(frozen=True)
class ServerPtCampaign:
    """One approved campaign: identity, charter, purpose and fixed limits.

    `complete_attempt_limit` is the charter's cap on setup attempts; `None`
    means the campaign ledger bounds consumption instead. A pinned acceptance
    cost is the exact proposal the charter approved; without one, the
    campaign's ledger must admit whatever the product derives.
    """

    campaign_id: str
    charter_sha256: str
    purpose: ExecutionPurpose
    deployment_prefix: str
    authorization_prefix: str
    complete_attempt_limit: int | None
    acceptance_cost_pin: tuple[int, int] | None
    #: Whether this charter lets retirement terminate an owned process after
    #: a failed graceful close. FASTLOOP's Addendum 02 authorized one; the
    #: DHCP charter says it "does not newly authorize force termination".
    forced_retirement_authorized: bool = True

    @property
    def experimental(self) -> bool:
        """Whether this campaign's phases run under experimental authority."""
        return self.purpose is ExecutionPurpose.EXPERIMENTAL


C31_CAMPAIGN = ServerPtCampaign(
    campaign_id="SERVER-PT-C31-COMMISSION-01",
    charter_sha256="7dbc5bbcd575bb0e9bcdac49fa003be6597e5b89e0742790c54237222fe8a200",
    purpose=ExecutionPurpose.DELIVERY,
    deployment_prefix="server-pt-c31-",
    authorization_prefix="SERVER-PT-C31-",
    complete_attempt_limit=2,
    acceptance_cost_pin=(7849, 2792),
)
FASTLOOP_CAMPAIGN = ServerPtCampaign(
    campaign_id="SERVER-PT-IOS-FASTLOOP-01",
    charter_sha256="3ed40bd1e3bfc433f340c995d3e5944b010e3099e8e1e1228953d2304646a793",
    purpose=ExecutionPurpose.EXPERIMENTAL,
    deployment_prefix="server-pt-fastloop-",
    authorization_prefix="SERVER-PT-FASTLOOP-",
    complete_attempt_limit=None,
    acceptance_cost_pin=None,
)
#: The S3/Q3 DHCP qualification campaign. Its charter is the adopted work
#: order `Next_Work_S3_Q3_FASTLOOP_PROPOSAL.md`. It runs versioned Q3-FL
#: qualification stages, never the HTTP commissioning phases, so its prefixes
#: name no deployment the commissioning setup would create.
DHCP_FASTLOOP_CAMPAIGN = ServerPtCampaign(
    campaign_id="SERVER-PT-DHCP-FASTLOOP-01",
    charter_sha256="6c24e5eaf0044e11191012fdd061d02db2098af3422664984844a876330ac5fe",
    purpose=ExecutionPurpose.EXPERIMENTAL,
    deployment_prefix="server-pt-dhcp-fastloop-",
    authorization_prefix="SERVER-PT-DHCP-FASTLOOP-",
    complete_attempt_limit=None,
    acceptance_cost_pin=None,
    forced_retirement_authorized=False,
)
CAMPAIGNS = {
    item.campaign_id: item
    for item in (C31_CAMPAIGN, FASTLOOP_CAMPAIGN, DHCP_FASTLOOP_CAMPAIGN)
}


def source_authority_findings(
    campaign: ServerPtCampaign,
    source: RepositoryIdentity,
    ci: ExactCiEvidenceLike | None,
) -> tuple[str, ...]:
    """Name what keeps this source from authorizing a phase of `campaign`.

    Both purposes need a clean, committed checkout whose HEAD and tree were
    observed: frozen executable bytes. Only delivery needs publication and an
    exact-SHA CI run; experimental refuses any CI object instead of ignoring
    it, so a green label can never ride along with an experimental grant.
    """
    found: list[str] = []
    if source.error or source.clean is not True or not source.head or not source.tree:
        found.append("source_not_clean_committed")
    if campaign.purpose is ExecutionPurpose.DELIVERY:
        if not source.upstream_head or source.upstream_head != source.head:
            found.append("source_not_published")
        if ci is None or ci.head_sha != source.head:
            found.append("exact_ci_missing")
    elif ci is not None:
        found.append("experimental_ci_claim_refused")
    return tuple(found)
