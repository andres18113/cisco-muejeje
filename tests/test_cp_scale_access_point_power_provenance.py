"""Access points are externally powered; they must not consume PoE coverage.

Provenance, audited offline against source, git history and the admitted
references:

* The immutable reference `topologia_completa_IMP.md` as admitted in `b4f25bb`
  contains no power vocabulary at all — no `PoE`, no `alimentado`, no wattage —
  and pins ten `2960-24TT` access switches, a build that delivers no power.
  Nothing upstream ever asked for an access point to be powered by a switch.
* `requires_poe=True` for `DeviceRole.ACCESS_POINT` was born as an unexplained
  literal when `cp_scale.py` was created in `bb383d0`, while the sibling
  workload path derives its value functionally (`role is DeviceRole.IP_PHONE`).
* The `(alimentado)` annotations that now appear beside access points in the
  reference were written later, by `7e5d639`, which sized the access layer from
  the powered count that literal had already produced. The document restates
  the assumption; it is not its source.
* The design's own `provenance` field marks 10 of the 17 access-point bindings
  `implementation_allocation`.
* Packet Tracer models external AP power directly: module type 31,
  `ACCESS_POINT_POWER_ADAPTER`, "Power adapter for Access Point".
* Measured, POE-2 (`poe2-20260907T173336Z-b4d3459e`): with an `AccessPoint-PT`
  on `3560-24PS` `Fa0/13`, `show power inline` prints a table byte-identical to
  the one printed with nothing connected, while a `7960` on the same model and
  port draws 10.0W.

So the access point never was a powered device. Counting it as one inflated
`required_poe_ports` by 17 and made PoE coverage a prerequisite for bindings
that cannot consume it.

Phones are a different question and are deliberately left alone: a `7960` is
dark without inline power, and that is measured, not assumed.
"""
from __future__ import annotations

from collections import Counter, defaultdict

from src.packet_tracer_mcp.domain.enterprise.models.roles import DeviceRole
from src.packet_tracer_mcp.domain.enterprise.scenarios.cp_scale import (
    CP_SCALE_ACCESS_POINT_COUNT, cp_scale_intent,
)
from src.packet_tracer_mcp.domain.enterprise.scenarios.cp_scale_physical import (
    cp_scale_physical_design,
)

AP_MODEL = "AccessPoint-PT"
PHONE_MODEL = "7960"


def _endpoint_requirements():
    """Every endpoint requirement the canonical intent declares, flattened."""
    found = []

    def walk(node):
        for endpoint in getattr(node, "endpoints", None) or []:
            found.append(endpoint)
        for group in getattr(node, "endpoint_groups", None) or []:
            found.extend(group.requirements)
        for attribute in ("buildings", "floors", "zones"):
            for child in getattr(node, attribute, None) or []:
                walk(child)

    for site in cp_scale_intent().sites:
        walk(site)
    return found


def test_the_intent_declares_access_points_as_externally_powered():
    access_points = [item for item in _endpoint_requirements()
                     if item.role is DeviceRole.ACCESS_POINT]
    assert access_points, "the canonical intent must still declare access points"
    assert sum(item.count for item in access_points) == CP_SCALE_ACCESS_POINT_COUNT
    for item in access_points:
        assert item.requires_poe is False


def test_phones_still_require_inline_power():
    """Guard against over-correcting: the measured powered device is unchanged."""
    phones = [item for item in _endpoint_requirements()
              if item.role is DeviceRole.IP_PHONE]
    assert phones
    assert all(item.requires_poe is True for item in phones)


def _powered_endpoint_ids() -> set[str]:
    from src.packet_tracer_mcp.domain.enterprise.services.endpoint_expander import (
        EndpointGroupExpander,
    )
    from src.packet_tracer_mcp.domain.enterprise.services.naming import (
        DeterministicNamingService,
    )
    from src.packet_tracer_mcp.domain.enterprise.services.enterprise_designer import (
        EnterpriseDesigner,
    )
    designed = EnterpriseDesigner().design(cp_scale_intent())
    assert designed.plan is not None
    return {item.id for item in
            EndpointGroupExpander().expand(designed.plan, DeterministicNamingService())
            if item.requires_poe}


def test_no_access_point_binding_consumes_poe_coverage():
    powered = _powered_endpoint_ids()
    design = cp_scale_physical_design()
    offenders = [binding.endpoint_id
                 for site in design.sites for binding in site.endpoint_bindings
                 if binding.endpoint_model == AP_MODEL and binding.endpoint_id in powered]
    assert offenders == []


def test_every_powered_binding_is_a_phone():
    powered = _powered_endpoint_ids()
    design = cp_scale_physical_design()
    models = Counter(binding.endpoint_model
                     for site in design.sites for binding in site.endpoint_bindings
                     if binding.endpoint_id in powered)
    assert set(models) == {PHONE_MODEL}


def test_declared_block_poe_reconciles_with_phone_only_demand():
    """The declared per-block budget must equal what actually draws power."""
    design = cp_scale_physical_design()
    phones_by_switch: dict[str, int] = defaultdict(int)
    for site in design.sites:
        for binding in site.endpoint_bindings:
            if binding.endpoint_model == PHONE_MODEL:
                phones_by_switch[binding.device_id] += 1
    for site in design.sites:
        for block in site.access_blocks:
            expected = sum(phones_by_switch.get(switch, 0) for switch in block.switches)
            assert block.required_poe_ports == expected, block.block_id


def test_the_mls6_access_switch_needs_no_inline_power_at_all():
    """The POE-2 binding's switch carried a PoE budget of exactly one access point.

    Its only powered demand was the assumption this module retires, so once
    access points are externally powered it requires no inline power at all.
    """
    design = cp_scale_physical_design()
    block = next(block for site in design.sites for block in site.access_blocks
                 if block.block_id.endswith("/mls6"))
    assert block.switches == ["sw-acc-multilayer-branch-mls6-01"]
    assert block.required_poe_ports == 0
    # The access point itself stays in the design, on the same exact port.
    bindings = [binding for site in design.sites for binding in site.endpoint_bindings
                if binding.device_id == "sw-acc-multilayer-branch-mls6-01"
                and binding.endpoint_model == AP_MODEL]
    assert len(bindings) == 1
    assert bindings[0].device_port == "FastEthernet0/13"
    assert bindings[0].endpoint_port == "Port 0"


def test_the_access_points_themselves_are_untouched():
    """Retiring a false power requirement is not permission to redesign.

    Same model, same count, same ports. `LAP-PT` and `3702i` are not
    substituted, because no functional requirement asks for them.
    """
    design = cp_scale_physical_design()
    access_points = [binding for site in design.sites
                     for binding in site.endpoint_bindings
                     if binding.endpoint_model == AP_MODEL]
    assert len(access_points) == CP_SCALE_ACCESS_POINT_COUNT == 17
    assert {binding.endpoint_port for binding in access_points} == {"Port 0"}
