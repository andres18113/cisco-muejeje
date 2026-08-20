"""La pasada que repite `create cnf-files`, y por qué su silencio significa algo.

`TD-VOICE-001` admite tres desenlaces: replay-safe, efectos adicionales, o
**inobservable**. El tercero sólo vale si se miró por todos los caminos, así que
lo que estos tests fijan es precisamente eso:

* dos lecturas vacías idénticas NO son evidencia de idempotencia. Si ningún
  observador respondió, el desenlace es `unobservable` y jamás
  `no_observable_difference`;
* "IOS rechazó el comando" y "el comando respondió vacío" son evidencias
  distintas y no se colapsan;
* si un observador SÍ responde, entonces comparar las dos pasadas vuelve a
  significar algo, y una diferencia se reporta.

Valores medidos en vivo sobre PT `9.0.1.0858` / `2811`: `show telephony-service`
inválido, `show ephone` vacío, 146 miembros del objeto `Router` sin nada de
telefonía, y `VlanManager` como único proceso que responde de nueve candidatos.
"""

from __future__ import annotations

from src.packet_tracer_mcp.application.use_cases.qualify_voice_replay import (
    QUALIFICATION_PREFIX,
    VoiceReplayQualifier,
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
from src.packet_tracer_mcp.domain.enterprise.models.voice_plan import (
    VoiceActionType,
)
from src.packet_tracer_mcp.infrastructure.execution.access_port_probe import (
    DeviceObserverDiscovery,
)
from src.packet_tracer_mcp.infrastructure.execution.ios_terminal import (
    IosCommandResult,
    IosSessionState,
    OperationalQueryId,
)

#: Las dos salidas reales capturadas en vivo.
_INVALID = (
    "show telephony-service\n              ^\n"
    "% Invalid input detected at '^' marker.\n\t\nRouter#"
)
_EMPTY_EPHONE = "show ephone\nRouter#"
_ANSWERING_EPHONE = "show ephone\nephone-1 Mac:0001.0002.0003 registered\nRouter#"


class _Physical:
    def __init__(self, *, create_ok=True, remove_ok=True, preexisting=None, interfaces=None):
        self._create_ok = create_ok
        self._remove_ok = remove_ok
        self._preexisting = list(preexisting or [])
        self._interfaces = list(
            ["FastEthernet0/0", "FastEthernet0/1"] if interfaces is None else interfaces
        )
        self.live: list[str] = []

    def observe_workspace(self):
        return PhysicalWorkspaceObservation(
            observed=True,
            devices=[
                PhysicalWorkspaceDeviceObservation(name=name, model="2811")
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


class _Applying:
    def __init__(self, *, applied=True):
        self._applied = applied
        self.batches: list[list] = []

    def inventory(self):
        return []

    def apply_actions(self, actions):
        self.batches.append(list(actions))
        return [
            RuntimeActionMutation(action_id=item.id, applied=self._applied, message="")
            for item in actions
        ]


class _Query:
    def __init__(self, ephone_outputs=None):
        self._ephone = list(ephone_outputs or [_EMPTY_EPHONE, _EMPTY_EPHONE])
        self.calls: list[OperationalQueryId] = []

    def execute(self, device_name, query_id, *, interface=""):
        self.calls.append(query_id)
        if query_id is OperationalQueryId.SHOW_TELEPHONY_SERVICE:
            output = _INVALID
        else:
            output = self._ephone.pop(0) if self._ephone else _EMPTY_EPHONE
        return IosCommandResult(
            device_name=device_name, query_id=query_id, executed=True,
            output=output, session_state=IosSessionState.EXEC_PROMPT_READY,
            fresh_output_observed=True, output_complete=True,
        )


def _probe(processes=("VlanManager",), members=("getPort", "getProcess")):
    def call(device_name: str) -> DeviceObserverDiscovery:
        return DeviceObserverDiscovery(
            device_found=True, device_class_name="Router",
            enumerated_members=tuple(members), processes_present=tuple(processes),
        )
    return call


def _qualify(physical=None, voice=None, query=None, probe=None, configuration=None):
    physical = physical or _Physical()
    voice = voice or _Applying()
    result = VoiceReplayQualifier(
        physical,
        configuration or _Applying(),
        voice,
        query or _Query(),
        probe if probe is not None else _probe(),
        name_token="tok",
    ).qualify("2811")
    return result, physical, voice


# ===================== el silencio no es idempotencia ======================


def test_two_identical_silences_are_unobservable_and_never_equivalence():
    """El error que este test existe para impedir."""
    result, _, _ = _qualify()

    assert result.dispatched_twice is True
    assert result.any_observer_answered is False
    assert result.repeat_effect == "unobservable"
    assert result.repeat_effect != "no_observable_difference"


def test_an_invalid_command_and_an_empty_answer_are_different_evidence():
    result, _, _ = _qualify()

    queries = {item.query: item for item in result.passes[0].queries}
    telephony = queries["show_telephony_service"]
    ephone = queries["show_ephone"]
    assert telephony.rejected_by_ios is True
    assert telephony.answered_empty is False
    assert ephone.rejected_by_ios is False
    assert ephone.answered_empty is True


def test_vlan_manager_alone_is_not_a_telephony_observer():
    result, _, _ = _qualify()

    assert result.passes[0].discovery.processes_present == ("VlanManager",)
    assert result.any_observer_answered is False


# ===================== cuando alguien SÍ responde ==========================


def test_an_answering_observer_makes_the_comparison_mean_something():
    result, _, _ = _qualify(
        query=_Query([_ANSWERING_EPHONE, _ANSWERING_EPHONE]),
    )

    assert result.any_observer_answered is True
    assert result.repeat_effect == "no_observable_difference"


def test_a_difference_between_the_passes_is_reported():
    result, _, _ = _qualify(
        query=_Query([_ANSWERING_EPHONE, _ANSWERING_EPHONE.replace("ephone-1", "ephone-2")]),
    )

    assert result.repeat_effect == "observable_difference"


def test_a_telephony_process_would_count_as_an_observer():
    result, _, _ = _qualify(probe=_probe(processes=("VlanManager", "TelephonyService")))

    assert result.any_observer_answered is True


# ===================== la reproducción, y lo que la invalida ===============


def test_the_imperative_action_is_dispatched_exactly_twice():
    result, _, voice = _qualify()

    cnf = [
        item for batch in voice.batches for item in batch
        if item.action_type is VoiceActionType.GENERATE_PHONE_CONFIGURATION_FILES
    ]
    assert len(cnf) == 2
    assert len(result.passes) == 2


def test_the_call_control_setup_runs_before_the_imperative_action():
    _, _, voice = _qualify()

    kinds = [item.action_type for item in voice.batches[0]]
    assert VoiceActionType.ENABLE_CALL_CONTROL in kinds
    assert VoiceActionType.CREATE_EXTENSION in kinds
    assert VoiceActionType.GENERATE_PHONE_CONFIGURATION_FILES not in kinds


def test_a_dispatch_that_did_not_apply_is_not_a_reproduction():
    result, _, _ = _qualify(voice=_Applying(applied=False))

    assert result.dispatched_twice is False
    assert result.repeat_effect == "not_reproduced"


def test_a_router_without_a_routed_interface_measures_nothing():
    result, _, _ = _qualify(_Physical(interfaces=["Vlan1"]))

    assert result.passes == ()
    assert any("No routed Ethernet interface" in item for item in result.errors)


def test_an_unaddressable_source_stops_before_the_voice_batch():
    result, _, voice = _qualify(configuration=_Applying(applied=False))

    assert result.passes == ()
    assert voice.batches == []
    assert any("source_address_not_applied" in item for item in result.errors)


# ===================== aislamiento y limpieza ==============================


def test_the_disposable_carries_the_reserved_prefix():
    result, _, _ = _qualify()

    assert result.device_name.startswith(QUALIFICATION_PREFIX)


def test_a_non_empty_workspace_is_never_mutated():
    result, physical, voice = _qualify(_Physical(preexisting=["OperatorRouter"]))

    assert result.passes == ()
    assert voice.batches == []
    assert any("refuses to mutate" in item for item in result.errors)


def test_the_disposable_is_removed_and_restoration_compared():
    result, physical, _ = _qualify()

    assert physical.live == []
    assert result.removed == (result.device_name,)
    assert result.restored is True


def test_an_exception_that_escapes_the_measurement_still_cleans_up():
    class _Exploding(VoiceReplayQualifier):
        def _dispatch_and_observe(self, *args, **kwargs):
            raise ValueError("after the device already exists")

    physical = _Physical()
    result = _Exploding(
        physical, _Applying(), _Applying(), _Query(), _probe(), name_token="tok",
    ).qualify("2811")

    assert physical.live == []
    assert result.removed == (result.device_name,)
    assert any("qualification_raised" in item for item in result.errors)
