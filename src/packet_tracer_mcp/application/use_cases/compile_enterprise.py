"""Use case fino para compilar E4 sin realizar mutaciones de backend."""

from __future__ import annotations

from collections.abc import Callable

from ...domain.enterprise.models.compilation import (
    EnterpriseCompileResult,
    LayoutProfile,
    PhysicalCompilationProfile,
)
from ...domain.enterprise.models.enterprise_plan import EnterprisePlan
from ...domain.enterprise.models.hardware import HardwarePlan
from ...domain.enterprise.services.enterprise_compiler import EnterpriseCompiler


def compile_enterprise_topology(
    enterprise_plan: EnterprisePlan,
    hardware_plan: HardwarePlan,
    physical_profile: PhysicalCompilationProfile,
    cable_resolver: Callable[[str, str], str] | None = None,
    layout_profile: LayoutProfile = LayoutProfile(),
) -> EnterpriseCompileResult:
    """Compila y valida; no despliega ni genera configuración E5."""

    return EnterpriseCompiler().compile(
        enterprise_plan,
        hardware_plan,
        physical_profile,
        layout_profile,
        cable_resolver,
    )
