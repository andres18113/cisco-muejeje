"""Orquestación E1: intención validada a plan Enterprise lógico."""

from __future__ import annotations

from dataclasses import dataclass

from ...models.errors import ValidationResult
from ..models.enterprise_plan import EnterprisePlan
from ..models.intent import EnterpriseIntent
from .capacity_planner import CapacityPlanner
from .ipam_planner import IPAMPlanner
from .requirements_validator import validate_enterprise_intent
from .site_planner import plan_site


@dataclass(frozen=True)
class EnterpriseDesignResult:
    plan: EnterprisePlan | None
    validation: ValidationResult


class EnterpriseDesigner:
    """Construye un plan lógico. La compilación a TopologyPlan es responsabilidad de E2."""

    def design(self, intent: EnterpriseIntent) -> EnterpriseDesignResult:
        validation = validate_enterprise_intent(intent)
        if not validation.is_valid:
            return EnterpriseDesignResult(plan=None, validation=validation)

        site_plans = [plan_site(site, intent.default_growth_percent) for site in intent.sites]
        plan = EnterprisePlan(
            id=f"ent_{_plan_id_part(intent.name)}",
            name=intent.name,
            sites=site_plans,
            address_space=intent.address_space,
            internet_required=intent.internet_required,
            warnings=validation.warning_messages(),
            metadata=intent.metadata,
        )
        capacity_planner = CapacityPlanner()
        for site in plan.sites:
            capacity_planner.plan_site(site)

        ipam_result = IPAMPlanner().plan(plan)
        validation.errors.extend(ipam_result.validation.errors)
        validation.warnings.extend(ipam_result.validation.warnings)
        if not validation.is_valid:
            return EnterpriseDesignResult(plan=None, validation=validation)
        plan.addressing = ipam_result.plan
        return EnterpriseDesignResult(plan=plan, validation=validation)


def _plan_id_part(name: str) -> str:
    """ID compacto y determinista; el repositorio stateful llegará con futuras tools MCP."""
    return "".join(character for character in name.casefold() if character.isalnum())[:24] or "plan"
