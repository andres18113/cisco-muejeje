"""La pasada que reproduce una aplicación E8 repetida, y lo que se niega a decir.

`TD-SECURITY-001` clasifica a la familia ACL/NAT como replay-unsafe por postura,
y Debt Checkpoint 2 anotó que esa postura *no es una medición*. Esta pasada la
mide. Lo que estos tests fijan es lo que no puede afirmar de más:

* una ACL que NUNCA se observó no reporta "0 duplicados" -- reporta `None`.
  Devolver 0 diría "no duplicó" sobre algo que nadie vio, que es exactamente el
  silencio que la primera versión de esta pasada produjo cuando el número de
  ACL de control estaba en el rango equivocado;
* dos lecturas frescas son el mínimo para comparar;
* la retirada tipada corre pase lo que pase, y el desechable se registra para
  limpieza en cuanto existe.
"""

from __future__ import annotations

from src.packet_tracer_mcp.application.use_cases.qualify_security_replay import (
    CONTROL_ACL_NUMBER,
    CONTROL_NAT_ACL_NUMBER,
    QUALIFICATION_PREFIX,
    SecurityReplayQualifier,
)
from src.packet_tracer_mcp.domain.enterprise.models.configuration_runtime import (
    RuntimeActionMutation,
)
from src.packet_tracer_mcp.domain.enterprise.models.physical_deployment import (
    MutationDisposition,
    PhysicalDeviceObservation,
    PhysicalMutationResult,
    PhysicalObjectKind,
    PhysicalWorkspaceDeviceObservation,
    PhysicalWorkspaceObservation,
)
from src.packet_tracer_mcp.domain.enterprise.models.security_plan import (
    SecurityActionType,
)
from src.packet_tracer_mcp.infrastructure.execution.ios_terminal import (
    IosCommandResult,
    IosSessionState,
    OperationalQueryId,
)

_INTERFACES = ["GigabitEthernet0/0", "GigabitEthernet0/1", "Vlan1"]

_EXTENDED = (
    f"Extended IP access list {CONTROL_ACL_NUMBER}\n"
    "    10 permit ip 198.18.160.0 0.0.0.255 198.18.161.0 0.0.0.255\n"
)
_STANDARD = (
    f"Standard IP access list {CONTROL_NAT_ACL_NUMBER}\n"
    "    10 permit 198.18.160.0 0.0.0.255\n"
)


class _Physical:
    def __init__(self, *, create_ok=True, remove_ok=True, preexisting=None, interfaces=None):
        self._create_ok = create_ok
        self._remove_ok = remove_ok
        self._preexisting = list(preexisting or [])
        self._interfaces = list(_INTERFACES if interfaces is None else interfaces)
        self.live: list[str] = []

    def observe_workspace(self):
        return PhysicalWorkspaceObservation(
            observed=True,
            devices=[
                PhysicalWorkspaceDeviceObservation(name=name, model="1941")
                for name in [*self._preexisting, *self.live]
            ],
            links=[],
        )

    def ensure_device(self, device):
        if self._create_ok:
            self.live.append(device.name)
        return PhysicalMutationResult(
            target_id=device.id, target_kind=PhysicalObjectKind.DEVICE,
            disposition=(
                MutationDisposition.CHANGED if self._create_ok
                else MutationDisposition.FAILED
            ),
            applied=self._create_ok, message="" if self._create_ok else "refused",
        )

    def observe_device(self, device):
        return PhysicalDeviceObservation(
            target_id=device.id, observed=True, deployed_name=device.name,
            model=device.model, interfaces=list(self._interfaces),
        )

    def remove_device(self, device):
        if self._remove_ok and device.name in self.live:
            self.live.remove(device.name)
        return PhysicalMutationResult(
            target_id=device.id, target_kind=PhysicalObjectKind.DEVICE,
            disposition=(
                MutationDisposition.CHANGED if self._remove_ok
                else MutationDisposition.FAILED
            ),
            applied=self._remove_ok, message="" if self._remove_ok else "still there",
        )


class _Security:
    def __init__(self, *, applied=True, cleanup_ok=True):
        self._applied = applied
        self._cleanup_ok = cleanup_ok
        self.applications: list[list] = []
        self.cleanups: list[list] = []

    def inventory(self):
        return []

    def apply_actions(self, actions):
        self.applications.append(list(actions))
        return [
            RuntimeActionMutation(action_id=item.id, applied=self._applied, message="")
            for item in actions
        ]

    def cleanup_actions(self, actions):
        self.cleanups.append(list(actions))
        return [
            RuntimeActionMutation(
                action_id=item.id, applied=self._cleanup_ok,
                message="" if self._cleanup_ok else "cleanup refused",
            )
            for item in actions
        ]


class _Query:
    def __init__(self, outputs=None, *, fresh=True, executed=True):
        self._outputs = list(outputs) if outputs is not None else [
            _EXTENDED + _STANDARD, _EXTENDED + _STANDARD,
        ]
        self._fresh = fresh
        self._executed = executed
        self.calls: list[OperationalQueryId] = []

    def execute(self, device_name, query_id, *, interface=""):
        self.calls.append(query_id)
        if query_id is OperationalQueryId.SHOW_ACCESS_LISTS:
            output = self._outputs.pop(0) if self._outputs else ""
        else:
            output = "Inside Interfaces: GigabitEthernet0/0\n"
        return IosCommandResult(
            device_name=device_name, query_id=query_id, executed=self._executed,
            output=output, session_state=IosSessionState.EXEC_PROMPT_READY,
            fresh_output_observed=self._fresh, output_complete=True,
        )


def _qualify(physical=None, security=None, query=None):
    physical = physical or _Physical()
    security = security or _Security()
    query = query or _Query()
    result = SecurityReplayQualifier(
        physical, security, query, name_token="tok",
    ).qualify("1941")
    return result, physical, security, query


# ===================== dos pasadas, comparables ============================


def test_the_same_typed_batch_is_applied_twice():
    result, _, security, _ = _qualify()

    assert len(security.applications) == 2
    assert [item.id for item in security.applications[0]] == [
        item.id for item in security.applications[1]
    ]
    kinds = {item.action_type for item in security.applications[0]}
    assert SecurityActionType.ADD_ACL_RULE in kinds
    assert SecurityActionType.ATTACH_ACL in kinds
    assert SecurityActionType.CONFIGURE_NAT in kinds
    assert len(result.readings) == 2


def test_an_identical_readback_reports_no_duplication():
    result, _, _, _ = _qualify()

    assert result.comparable is True
    assert result.duplication_for(str(CONTROL_ACL_NUMBER)) == 0
    assert result.duplication_for(str(CONTROL_NAT_ACL_NUMBER)) == 0


def test_a_second_pass_that_appends_is_reported_as_duplication():
    doubled = _EXTENDED + (
        "    20 permit ip 198.18.160.0 0.0.0.255 198.18.161.0 0.0.0.255\n"
    ) + _STANDARD
    result, _, _, _ = _qualify(query=_Query([_EXTENDED + _STANDARD, doubled]))

    assert result.duplication_for(str(CONTROL_ACL_NUMBER)) == 1


# ===================== lo que no se puede afirmar ==========================


def test_an_acl_that_was_never_observed_reports_none_not_zero():
    """El defecto literal de la primera versión de esta pasada."""
    result, _, _, _ = _qualify(query=_Query([_EXTENDED, _EXTENDED]))

    assert result.duplication_for(str(CONTROL_ACL_NUMBER)) == 0
    assert result.duplication_for(str(CONTROL_NAT_ACL_NUMBER)) is None


def test_a_stale_reading_is_not_comparable():
    result, _, _, _ = _qualify(query=_Query(fresh=False))

    assert result.comparable is False
    assert result.duplication_for(str(CONTROL_ACL_NUMBER)) is None


def test_a_query_that_did_not_execute_is_not_comparable():
    result, _, _, _ = _qualify(query=_Query(executed=False))

    assert result.comparable is False


def test_the_control_numbers_sit_in_the_ios_range_their_form_requires():
    """Una ACE estándar con número extendido no reproduce nada: IOS la rechaza."""
    assert 100 <= CONTROL_ACL_NUMBER <= 199
    assert 1 <= CONTROL_NAT_ACL_NUMBER <= 99


# ===================== aislamiento y limpieza ==============================


def test_the_disposable_carries_the_reserved_prefix():
    result, _, _, _ = _qualify()

    assert result.device_name.startswith(QUALIFICATION_PREFIX)


def test_a_non_empty_workspace_is_never_mutated():
    result, physical, security, _ = _qualify(_Physical(preexisting=["OperatorRouter"]))

    assert result.readings == ()
    assert physical.live == ["OperatorRouter"] or physical.live == []
    assert security.applications == []
    assert any("refuses to mutate" in item for item in result.errors)


def test_the_typed_removal_path_runs_in_reverse_order():
    """`no access-list` vive en la ruta de retirada, y esta pasada la ejerce."""
    result, _, security, _ = _qualify()

    assert len(security.cleanups) == 1
    assert [item.id for item in security.cleanups[0]] == [
        item.id for item in reversed(security.applications[0])
    ]


def test_a_removal_that_did_not_apply_is_reported_not_swallowed():
    result, _, _, _ = _qualify(security=_Security(cleanup_ok=False))

    assert any("Typed E8 cleanup did not apply" in item for item in result.errors)


def test_an_exception_that_escapes_the_measurement_still_cleans_up():
    class _Exploding(SecurityReplayQualifier):
        def _apply_and_read(self, *args, **kwargs):
            raise ValueError("after the device already exists")

    physical = _Physical()
    result = _Exploding(physical, _Security(), _Query(), name_token="tok").qualify("1941")

    assert physical.live == []
    assert result.removed == (result.device_name,)
    assert any("qualification_raised" in item for item in result.errors)


def test_a_router_without_two_routed_interfaces_measures_nothing():
    physical = _Physical(interfaces=["GigabitEthernet0/0", "Vlan1"])

    result, _, security, _ = _qualify(physical)

    assert result.readings == ()
    assert security.applications == []
    assert any("NAT inside/outside pair" in item for item in result.errors)


def test_restoration_is_compared_against_the_baseline():
    result, _, _, _ = _qualify()

    assert result.restored is True
    assert result.removed == (result.device_name,)
