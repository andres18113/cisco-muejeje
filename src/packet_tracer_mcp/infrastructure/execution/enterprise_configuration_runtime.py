"""Adapter Packet Tracer para aplicar y observar ConfigurationPlan E5."""

from __future__ import annotations

import ipaddress
import json
import re
from collections import defaultdict
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from math import isfinite
from time import monotonic, sleep
from typing import Any

from ...domain.enterprise.models.configuration import (
    ConfigurationAction,
    ConfigureAccessPort,
    ConfigureDhcpPool,
    ConfigureEthernetLinkMode,
    ConfigureHostname,
    ConfigureInterfaceBandwidth,
    ConfigureRoutedInterface,
    ConfigureSerialClock,
    ConfigureSubinterface,
    ConfigureSvi,
    ConfigureTrunk,
    CreateVlan,
    SetEndpointDhcp,
    SetEndpointStaticAddress,
    VerificationExpectation,
    VerificationKind,
)
from ...domain.enterprise.models.configuration_runtime import (
    ActionExecutionStatus,
    ConfigurationFailureCode,
    ConvergenceReport,
    FieldVerificationStatus,
    RuntimeActionMutation,
    RuntimeConfigurationTarget,
    RuntimeVerification,
)
from ...domain.enterprise.models.discovery import DeviceInitializationState
from ...domain.enterprise.models.forwarding import (
    AccessForwardingObservation,
    AccessForwardingRow,
    AccessForwardingSampleEvidence,
)
from ...domain.enterprise.services.access_forwarding import (
    CAUSE_AUXILIARY_READ_AFTER_DEADLINE,
    CAUSE_EPISODE_WINDOW_ENDED,
    CAUSE_SAMPLE_AFTER_DEADLINE,
    CAUSE_SAMPLE_BUDGET_EXHAUSTED,
    FORWARDING_STATES,
)
from ...domain.enterprise.services.trunk_continuity import (
    TrunkContinuityObservation,
    TrunkContinuityRound,
    TrunkPortReading,
    TrunkSwitchReading,
)
from ...shared.utils import same_interface_name
from ..generator.configuration_renderer import PacketTracerIosRenderer
from .configuration_runtime import PacketTracerConfigurationRuntime
from .device_lifecycle import StateConvergenceWaiter
from .endpoint_address_observer import PacketTracerEndpointAddressObserver
from .endpoint_dhcp_mode_observer import PacketTracerEndpointDhcpModeObserver
from .ios_terminal import (
    ControlledIosExecutor,
    DeviceIdentityProvenance,
    IosCommandResult,
    OperationalQueryId,
    parse_serial_controller,
    parse_show_interfaces_trunk,
    parse_show_ip_dhcp_pool,
    parse_show_ip_interface_brief,
    parse_show_spanning_tree,
)
from .runtime_inventory import normalize_runtime_inventory
from .simulation_time_convergence import (
    BoundedPvstLearningExtension,
    SimulationTimeConvergenceResult,
    pvst_learning_progress_target_ms,
)
from .simulation_trace_runtime import (
    SimulationStateObservation,
    SimulationTraceRuntime,
)

# Acciones que se aplican por el canal IOS. Faltaban aqui las tres de
# rendimiento de enlace, de modo que el runtime las descartaba antes
# incluso de llegar al renderer: el mismo fallo mudo, una capa mas abajo.
_IOS_ACTIONS = (
    ConfigureHostname,
    CreateVlan,
    ConfigureAccessPort,
    ConfigureTrunk,
    ConfigureRoutedInterface,
    ConfigureSvi,
    ConfigureSubinterface,
    ConfigureDhcpPool,
    ConfigureSerialClock,
    ConfigureInterfaceBandwidth,
    ConfigureEthernetLinkMode,
)
_ENDPOINT_ACTIONS = (SetEndpointStaticAddress, SetEndpointDhcp)
#: Endpoint addressing calls per fire-and-forget send. One call renders to
#: about two hundred bytes, so one script stays near thirteen kilobytes however
#: many endpoints a plan addresses; a plan within it sends exactly as before.
MAX_ENDPOINT_CALLS_PER_SEND = 64


# A trunk verification now claims operational STP forwarding, not merely that
# IOS accepted `switchport mode trunk`.  A fresh PT 9.0.1.0858 run still had all
# expected VLANs allowed and active, but none forwarding, when the former 8 s
# budget expired after 25 complete reads.  Keep the wait bounded while giving
# the independent forwarding read-back its own lifecycle-sized budget.
TRUNK_FORWARDING_CONVERGENCE_TIMEOUT_SECONDS = 45.0

#: Hard ceiling on the neutral access-forwarding observer. It is a sampling
#: bound, not a retry budget: the first admissible sample ends the loop, and a
#: sequence that never becomes forwarding is an observation, not a failure to
#: keep trying. No mode toggle, PortFast write, link bounce or reconfiguration
#: is ever dispatched to make it converge.
ACCESS_FORWARDING_MAX_SAMPLES = 3
ACCESS_FORWARDING_DEADLINE_SECONDS = 30.0
ACCESS_FORWARDING_INTERVAL_SECONDS = 1.0
#: Every channel call one registered sample may make. `execute` is not
#: one call: it prepares the session, dispatches, waits for the output to
#: converge, attributes the session, and may walk or cancel a pager, and
#: it retries a dispatch it proved corrupt. A deadline the caller reads
#: only after `execute` returns bounds none of that, so the bound lives on
#: the channel itself. Six covers the intended path -- session read,
#: dispatch, two convergence reads, attribution -- plus one pager
#: continuation or cancellation. A sample that needs more is returned as
#: incomplete rather than being allowed to spend an unbounded ledger.
ACCESS_FORWARDING_SAMPLE_CALLS = 6


def spanning_tree_sample_is_authoritative(
    show: IosCommandResult, device_name: str
) -> bool:
    """Whether one registered STP sample may be read as evidence at all.

    Execution, freshness, completeness and source identity are the four
    dimensions the registered reader already separates. All four must hold
    before any row of the output means anything, and this is the one place
    that decides it for every STP consumer of this runtime.
    """
    return bool(
        show.executed
        and show.fresh_output_observed
        and show.output_complete
        and show.observed_device_name == device_name
        and show.device_identity_provenance
        == DeviceIdentityProvenance.CONFIRMED_UNIQUE.value
    )


def spanning_tree_vlan_instance(output: str, vlan_id: int):
    """Return the parsed instance of one VLAN, or None when it is absent."""
    return next(
        (item for item in parse_show_spanning_tree(output) if item.vlan_id == vlan_id),
        None,
    )


def spanning_tree_interface_rows(instance, interface: str) -> tuple:
    """Return every row of one instance that names the requested interface.

    More than one row is an ambiguity the caller has to see: collapsing it to
    the first match would turn two contradictory rows into one state.
    """
    return tuple(
        item
        for item in instance.interfaces
        if same_interface_name(item.interface, interface)
    )


def _access_forwarding_row(instance, interface: str) -> AccessForwardingRow:
    """Project one requested interface into its neutral observation row."""
    rows = spanning_tree_interface_rows(instance, interface)
    first = rows[0] if len(rows) == 1 else None
    return AccessForwardingRow(
        interface=interface,
        matches=len(rows),
        state=str(first.state).upper() if first is not None else "",
        role=str(first.role) if first is not None else "",
    )


def voice_access_learning_extension_is_authorized(
    observation: dict[str, object],
    *,
    device_name: str,
    expected_count: int,
    terminal_sample_round: int,
) -> bool:
    """Decide whether ONE protocol-sized PVST extension may be granted.

    The bounded window already closed without forwarding, so extending it is
    an authority decision and not a retry.  It is granted only when the run's
    own TERMINAL round -- never an earlier snapshot that merely survived a
    failed one -- is fresh, complete, uniquely attributed to this switch,
    carries the voice VLAN instance, resolves every expected port and leaves
    every still-pending port in exactly LRN.  A failed terminal round, LIS,
    BLK, a missing row or an identity this observer cannot attribute all fail
    closed, because none of them is the already-proven learning transition.
    """
    if expected_count <= 0 or not device_name:
        return False
    if observation.get("sample_round") != terminal_sample_round:
        return False
    if observation.get("authoritative") is not True:
        return False
    if observation.get("vlan_present") is not True:
        return False
    if observation.get("observed_device_name") != device_name:
        return False
    states = observation.get("states")
    if not isinstance(states, dict) or len(states) != expected_count:
        return False
    pending = False
    for state in states.values():
        text = str(state).upper()
        if text == "LRN":
            pending = True
            continue
        if not text.startswith(("FWD", "FORW")):
            return False
    return pending


@dataclass(frozen=True)
class TrunkReadbackObservation:
    """One exact, registered and read-only trunk observation.

    The four VLAN dimensions intentionally remain independent. ``None`` means
    that dimension was not exposed by a fresh complete query; an empty tuple is
    an observed empty IOS section.
    """

    device_name: str
    requested_interface: str
    interface: str = ""
    status: str = ""
    native_vlan: int | None = None
    allowed_vlans: tuple[int, ...] | None = None
    active_vlans: tuple[int, ...] | None = None
    forwarding_vlans: tuple[int, ...] | None = None
    executed: bool = False
    fresh_output_observed: bool = False
    fresh_evidence: bool = False
    output_complete: bool = False
    device_identity_provenance: str = DeviceIdentityProvenance.NOT_OBSERVED.value
    failure_reason: str = ""


@dataclass(frozen=True)
class DhcpPoolReadbackObservation:
    """Independent fields from one fresh complete global pool table."""

    device_name: str
    requested_pool_name: str
    requested_range_start: str
    requested_range_end: str
    pool_present: bool | None = None
    requested_range_covered: bool | None = None
    range_start: str = ""
    range_end: str = ""
    subnet_ranges: tuple[tuple[str, str], ...] = ()
    total_addresses: int | None = None
    leased_addresses: int | None = None
    excluded_addresses: int | None = None
    available_addresses: int | None = None
    fresh_evidence: bool = False
    output_complete: bool = False
    identity_confirmed: bool = False
    failure_reason: str = ""


#: `SwitchPort.getAdminOpMode()` para `switchport mode access`. MEDIDO, no
#: supuesto: cualificación en vivo sobre PT `9.0.1.0858` / `2950T-24`, tres
#: puertos en la misma pasada, cada código corroborado por la lectura IOS
#: independiente `show interfaces <if> switchport` de esa misma sesión.
#:
#: Se mide el CÓDIGO, no un nombre. Un código fuera de esta tabla no es un modo
#: desconocido que se pueda tratar como no-acceso: es un modo que nadie midió,
#: y el campo sale UNOBSERVABLE.
#:
#: `isAccessPort()` existe en el mismo objeto y NO sirve para esto: devuelve
#: True tanto para `static access` como para `dynamic desirable`. Usarlo como
#: gate del modo convertiría un puerto sin configurar en un puerto de acceso
#: verificado.
ADMIN_OP_MODE_ACCESS = 3
MEASURED_ADMIN_OP_MODES = {
    0: "dynamic desirable",
    2: "trunk",
    ADMIN_OP_MODE_ACCESS: "static access",
}


class _BoundedTerminalChannel:
    """Carry a per-sample call budget and the remaining deadline into the I/O.

    A registered IOS query expands into several channel calls that its caller
    cannot see, so a deadline checked between calls caps nothing. This channel
    sits underneath the executor: it caps each call's timeout by the time the
    sample has left, and refuses past the sample's call budget. A refusal is
    returned as "no answer", which the executor already models, so the sample
    ends as an unobserved one instead of an unbounded one.

    `remaining_seconds` is the port the executor bounds its nested waits with,
    and it reports the EFFECTIVE allowance rather than the clock alone. Time
    left on a channel that can no longer dispatch is not allowance: a waiter
    that kept polling it would spin, because nothing it asks can change the
    answer. So it is zero once the call budget is spent, once the deadline has
    passed, and once the channel underneath has stopped granting calls at all.
    """

    def __init__(
        self,
        send_and_wait: Callable[[str, float], str | None],
        clock: Callable[[], float],
        sleeper: Callable[[float], None],
    ) -> None:
        """Wrap one channel; nothing is bounded until a sample opens."""
        self._send_and_wait = send_and_wait
        self._clock = clock
        self._sleeper = sleeper
        self._remaining = 0
        self._deadline: float | None = None
        self.calls = 0
        self.exhausted = False
        #: Whether the channel underneath refused terminally. It is a fact
        #: about the invocation's own allowance, not about one sample, so it
        #: survives the next `open()` instead of being asked again per sample.
        self.stopped = False
        self.stop_reason = ""

    def open(self, *, calls: int, deadline: float | None) -> None:
        """Start one sample with its own call budget and absolute deadline."""
        self._remaining = int(calls)
        self._deadline = deadline
        self.exhausted = False

    def seconds_left(self) -> float:
        """Return the wall-clock time between now and the sample's deadline."""
        return (
            max(0.0, self._deadline - self._clock())
            if self._deadline is not None
            else float("inf")
        )

    def can_dispatch(self) -> bool:
        """Return whether one more call could actually reach the channel."""
        return not self.stopped and self._remaining > 0 and self.seconds_left() > 0

    def remaining_seconds(self) -> float:
        """Return the allowance a nested waiter may still spend polling."""
        return self.seconds_left() if self.can_dispatch() else 0.0

    def sleep(self, seconds: float) -> None:
        """Bound an executor wait by the same absolute sample deadline."""
        remaining = self.remaining_seconds()
        if remaining > 0:
            self._sleeper(min(seconds, remaining))

    def __call__(self, script: str, timeout: float) -> str | None:
        """Dispatch one call, or refuse it because the sample is spent."""
        if self.stopped or self._remaining <= 0:
            self.exhausted = True
            return None
        allowed = float(timeout)
        if self._deadline is not None:
            allowed = min(allowed, max(0.0, self._deadline - self._clock()))
        if allowed <= 0:
            self.exhausted = True
            return None
        self._remaining -= 1
        self.calls += 1
        try:
            return self._send_and_wait(script, allowed)
        except Exception as exc:
            # The channel underneath refused or failed this dispatch. Whatever
            # its type -- and this layer deliberately does not know the
            # application's -- the caller that owns the budget has stopped
            # granting calls, so the answer is the "no answer" the executor
            # already models and the channel stops offering more. The type is
            # kept so the episode can report which boundary ended it.
            self.stopped = True
            self.stop_reason = f"channel_refused:{type(exc).__name__}"
            self.exhausted = True
            return None


class PacketTracerEnterpriseConfigurationRuntime:
    """Usa los canales oficiales existentes; no expone IOS/JS arbitrario."""

    def __init__(
        self,
        query_inventory: Callable[[], list[dict] | dict],
        send: Callable[[str], bool],
        send_and_wait: Callable[[str, float], str | None],
        *,
        hostname_timeout_seconds: float = 8.0,
        vlan_timeout_seconds: float = 5.0,
        endpoint_timeout_seconds: float = 30.0,
        trunk_timeout_seconds: float = TRUNK_FORWARDING_CONVERGENCE_TIMEOUT_SECONDS,
        ios_boot_timeout_seconds: float = 90.0,
        ios_query_max_calls: int | None = None,
        ios_query_max_seconds: float | None = None,
        l3_timeout_seconds: float = 8.0,
        convergence_interval_seconds: float = 0.25,
        ios_readiness: Callable[[str], bool] | None = None,
        trunk_transition_observer: (Callable[[str], dict[str, object]] | None) = None,
        simulation_time_observer: (
            Callable[[], SimulationStateObservation] | None
        ) = None,
        endpoint_address_observer=None,
        endpoint_dhcp_mode_observer=None,
        clock: Callable[[], float] = monotonic,
        sleeper: Callable[[float], None] = sleep,
        wait_allowance: Callable[[], float] | None = None,
    ) -> None:
        """Bind inventory, mutation and observation channels for one run.

        `wait_allowance` is the optional control of a caller that owns a
        shorter budget than this runtime's own waits. When it is supplied,
        every E5 waiter and the IOS boot wait use this runtime's clock and
        sleeper and stop as soon as the control reports nothing left, so a
        refused read cannot be polled until the waiter's own timeout. Without
        it, those waits keep the lifecycle defaults they always had.
        """
        self._query_inventory = query_inventory
        self._send = send
        self._send_and_wait = send_and_wait
        # Only the neutral access-forwarding observer reads these; every other
        # waiter keeps the lifecycle helper it already used, so injecting them
        # changes no existing path.
        self._clock = clock
        self._sleeper = sleeper
        simulation_state_reader = (
            simulation_time_observer
            or SimulationTraceRuntime(send_and_wait).read_simulation_state
        )
        self._simulation_time_observer = simulation_state_reader
        self._endpoint_addresses = (
            endpoint_address_observer
            or PacketTracerEndpointAddressObserver(send_and_wait)
        )
        self._endpoint_dhcp_modes = (
            endpoint_dhcp_mode_observer
            or PacketTracerEndpointDhcpModeObserver(send_and_wait)
        )
        self._configuration = PacketTracerConfigurationRuntime(send)
        self._wait_allowance = wait_allowance
        self._ios = (
            ControlledIosExecutor(
                send_and_wait,
                clock=clock,
                sleeper=sleeper,
                remaining_budget=wait_allowance,
                max_query_calls=ios_query_max_calls,
                max_query_seconds=ios_query_max_seconds,
            )
            if wait_allowance is not None
            else ControlledIosExecutor(
                send_and_wait,
                max_query_calls=ios_query_max_calls,
                max_query_seconds=ios_query_max_seconds,
            )
        )
        # The neutral forwarding observation accounts for nested calls and
        # auxiliary state reads through its own bounded channel. Other queries keep the
        # unbounded channel and the executor it always used, and this one
        # keeps its own pager quarantine across a run's observations.
        self._forwarding_channel = _BoundedTerminalChannel(
            send_and_wait, clock, sleeper
        )
        self._forwarding_ios = ControlledIosExecutor(
            self._forwarding_channel,
            clock=clock,
            sleeper=self._forwarding_channel.sleep,
            remaining_budget=self._forwarding_channel.remaining_seconds,
        )
        self._forwarding_simulation_time_observer = (
            simulation_time_observer
            or SimulationTraceRuntime(self._forwarding_channel).read_simulation_state
        )
        self._forwarding_aux_is_injected = simulation_time_observer is not None
        self._renderer = PacketTracerIosRenderer()
        self._targets: dict[str, RuntimeConfigurationTarget] = {}
        self._hostname_timeout = hostname_timeout_seconds
        self._vlan_timeout = vlan_timeout_seconds
        self._endpoint_timeout = endpoint_timeout_seconds
        self._trunk_timeout = trunk_timeout_seconds
        if not isfinite(ios_boot_timeout_seconds) or ios_boot_timeout_seconds < 0:
            raise ValueError("IOS boot bound must be finite and nonnegative")
        self._ios_boot_timeout = ios_boot_timeout_seconds
        self._l3_timeout = l3_timeout_seconds
        self._convergence_interval = convergence_interval_seconds
        self._ios_readiness = ios_readiness or self._wait_for_ios
        self._trunk_transition_observer = trunk_transition_observer
        self._pvst_learning_extension = BoundedPvstLearningExtension(
            simulation_state_reader,
            interval_seconds=convergence_interval_seconds,
        )
        self._ready_ios_devices: set[str] = set()

    def inventory(self) -> list[RuntimeConfigurationTarget]:
        """Return and index the normalized runtime inventory."""
        targets = normalize_runtime_inventory(self._query_inventory())
        self._targets = {item.device_name: item for item in targets}
        return targets

    def read_trunk(
        self,
        device_name: str,
        interface: str,
    ) -> TrunkReadbackObservation:
        """Read one trunk through the existing registered paged SHOW only."""
        show = self._ios.execute(
            device_name,
            OperationalQueryId.SHOW_INTERFACES_TRUNK,
        )
        row = (
            next(
                (
                    item
                    for item in parse_show_interfaces_trunk(show.output)
                    if same_interface_name(item.interface, interface)
                ),
                None,
            )
            if show.executed
            else None
        )
        fresh = bool(show.executed and show.fresh_output_observed)
        complete = bool(show.output_complete)
        reason = show.failure_reason
        if not reason and not fresh:
            reason = "No fresh current show interfaces trunk output was observed."
        if not reason and not complete:
            reason = "The show interfaces trunk output was incomplete."
        if (
            not reason
            and show.device_identity_provenance
            != DeviceIdentityProvenance.CONFIRMED_UNIQUE.value
        ):
            reason = "The trunk table was not attributed to one device."
        if not reason and row is None:
            reason = f"The fresh trunk table did not contain {interface!r}."
        return TrunkReadbackObservation(
            device_name=device_name,
            requested_interface=interface,
            interface=row.interface if row is not None else "",
            status=row.status if row is not None else "",
            native_vlan=row.native_vlan if row is not None else None,
            allowed_vlans=row.allowed_vlans if row is not None else None,
            active_vlans=row.active_vlans if row is not None else None,
            forwarding_vlans=(row.forwarding_vlans if row is not None else None),
            executed=bool(show.executed),
            fresh_output_observed=bool(show.fresh_output_observed),
            fresh_evidence=fresh,
            output_complete=complete,
            device_identity_provenance=show.device_identity_provenance,
            failure_reason=reason,
        )

    def wait_for_voice_access_forwarding(
        self,
        expectations: Sequence[VerificationExpectation],
    ) -> list[RuntimeVerification]:
        """Wait once per switch/VLAN until every signalled phone port is FWD."""
        ordered = list(expectations)
        grouped: dict[tuple[str, int], list[VerificationExpectation]] = defaultdict(
            list
        )
        invalid: dict[str, RuntimeVerification] = {}
        for expectation in ordered:
            voice_vlan = expectation.expected.get("voice_vlan_id")
            if not isinstance(voice_vlan, int) or isinstance(
                voice_vlan,
                bool,
            ):
                invalid[expectation.id] = RuntimeVerification(
                    expectation_id=expectation.id,
                    status=ActionExecutionStatus.UNOBSERVABLE,
                    fields={
                        "voice_forwarding": (FieldVerificationStatus.UNOBSERVABLE),
                    },
                    message=("Voice access forwarding requires a typed voice VLAN."),
                )
                continue
            grouped[(expectation.device_name, voice_vlan)].append(expectation)

        observed = dict(invalid)
        for (device_name, voice_vlan), group in grouped.items():
            observed.update(
                self._wait_voice_access_group(
                    device_name,
                    voice_vlan,
                    group,
                )
            )
        return [
            observed.get(expectation.id)
            or RuntimeVerification(
                expectation_id=expectation.id,
                status=ActionExecutionStatus.UNOBSERVABLE,
                fields={
                    "voice_forwarding": (FieldVerificationStatus.UNOBSERVABLE),
                },
                message="Voice access forwarding was not observed.",
            )
            for expectation in ordered
        ]

    def _wait_voice_access_group(
        self,
        device_name: str,
        voice_vlan: int,
        expectations: Sequence[VerificationExpectation],
    ) -> dict[str, RuntimeVerification]:
        expected_interfaces = {
            expectation.id: str(expectation.expected.get("interface") or "")
            for expectation in expectations
        }
        latest: dict[str, object] = {
            "show": None,
            "states": {},
            "authoritative": False,
            "vlan_present": False,
            "observed_device_name": "",
            "sample_round": 0,
            "forward_delay_seconds": None,
        }
        sample_round = 0

        def inspect() -> dict[str, object]:
            nonlocal sample_round
            sample_round += 1
            show = self._ios.execute(
                device_name,
                OperationalQueryId.SHOW_SPANNING_TREE,
            )
            authoritative = spanning_tree_sample_is_authoritative(show, device_name)
            states: dict[str, str] = {}
            vlan_present = False
            forward_delay_seconds = None
            if authoritative:
                instance = spanning_tree_vlan_instance(show.output, voice_vlan)
                vlan_present = instance is not None
                if instance is not None:
                    forward_delay_seconds = instance.forward_delay_seconds
                    for expectation in expectations:
                        interface = expected_interfaces[expectation.id]
                        rows = spanning_tree_interface_rows(instance, interface)
                        if rows:
                            states[expectation.id] = str(rows[0].state).upper()
            latest.update(
                {
                    "show": show,
                    "states": states,
                    "authoritative": authoritative,
                    "vlan_present": vlan_present,
                    "observed_device_name": show.observed_device_name,
                    "sample_round": sample_round,
                    "forward_delay_seconds": forward_delay_seconds,
                }
            )
            all_forwarding = bool(
                authoritative
                and len(states) == len(expectations)
                and all(state.startswith(("FWD", "FORW")) for state in states.values())
            )
            return {
                "found": show.executed,
                "configuration_channel": all_forwarding,
                "failure_reason": show.failure_reason,
                "continuation_authorized": bool(
                    all_forwarding
                    or (
                        voice_access_learning_extension_is_authorized(
                            latest,
                            device_name=device_name,
                            expected_count=len(expectations),
                            terminal_sample_round=sample_round,
                        )
                        and pvst_learning_progress_target_ms(
                            latest.get("forward_delay_seconds"),
                        )
                        is not None
                    )
                ),
            }

        initial_convergence = StateConvergenceWaiter(
            inspect,
            timeout_seconds=self._trunk_timeout,
            interval_seconds=self._convergence_interval,
            **self._wait_controls(),
        ).wait()

        learning_extension_candidate = (
            not initial_convergence.configuration_channel
            and voice_access_learning_extension_is_authorized(
                latest,
                device_name=device_name,
                expected_count=len(expectations),
                terminal_sample_round=initial_convergence.attempts,
            )
        )
        learning_extension_target = (
            pvst_learning_progress_target_ms(
                latest.get("forward_delay_seconds"),
            )
            if learning_extension_candidate
            else None
        )
        extension_convergence: SimulationTimeConvergenceResult | None = None
        if learning_extension_target is not None:
            extension_convergence = self._pvst_learning_extension.grant(
                inspect,
                required_simulation_progress_ms=learning_extension_target,
            )
        convergence = (
            initial_convergence
            if extension_convergence is None
            else extension_convergence
        )
        total_attempts = initial_convergence.attempts + (
            extension_convergence.attempts if extension_convergence is not None else 0
        )
        total_elapsed_ms = initial_convergence.elapsed_ms + (
            extension_convergence.elapsed_ms if extension_convergence is not None else 0
        )
        states = latest["states"]
        states = states if isinstance(states, dict) else {}
        authoritative = bool(latest["authoritative"])
        vlan_present = bool(latest["vlan_present"])
        show = latest["show"]
        verified_interfaces = sorted(
            expected_interfaces[identifier]
            for identifier, state in states.items()
            if state.startswith(("FWD", "FORW"))
        )
        missing_interfaces = sorted(
            interface
            for identifier, interface in expected_interfaces.items()
            if identifier not in states
        )
        non_forwarding_interfaces = {
            expected_interfaces[identifier]: state
            for identifier, state in sorted(states.items())
            if not state.startswith(("FWD", "FORW"))
        }
        if not isinstance(show, IosCommandResult) or not show.executed:
            failure_dimension = "EXECUTION"
        elif not show.fresh_output_observed:
            failure_dimension = "FRESHNESS"
        elif not show.output_complete:
            failure_dimension = "COMPLETENESS"
        elif (
            show.observed_device_name != device_name
            or show.device_identity_provenance
            != DeviceIdentityProvenance.CONFIRMED_UNIQUE.value
        ):
            failure_dimension = "IDENTITY"
        elif not vlan_present:
            failure_dimension = "VLAN_INSTANCE"
        elif missing_interfaces:
            failure_dimension = "MISSING_INTERFACE"
        elif non_forwarding_interfaces:
            failure_dimension = "NON_FORWARDING"
        elif len(verified_interfaces) == len(expectations):
            failure_dimension = "NONE"
        else:
            failure_dimension = "TIMEOUT"
        details = {
            "kind": "voice_access_forwarding_group",
            "switch": device_name,
            "voice_vlan_id": voice_vlan,
            "expected_interfaces": sorted(expected_interfaces.values()),
            "verified_fwd_interfaces": verified_interfaces,
            "missing_interfaces": missing_interfaces,
            "non_fwd_interfaces": non_forwarding_interfaces,
            "initial_sample_count": initial_convergence.attempts,
            "terminal_sample_round": latest.get("sample_round"),
            "observed_forward_delay_seconds": latest.get(
                "forward_delay_seconds",
            ),
            "learning_extension_candidate": learning_extension_candidate,
            **self._pvst_learning_extension.evidence(
                extension_convergence,
                requested_progress_ms=learning_extension_target,
            ),
            "sample_count": total_attempts,
            "elapsed_ms": total_elapsed_ms,
            "terminal_authority": (
                "AUTHORITATIVE" if authoritative else "UNOBSERVABLE"
            ),
            "terminal_failure_dimension": failure_dimension,
        }
        report = ConvergenceReport(
            attempts=total_attempts,
            elapsed_ms=total_elapsed_ms,
            final_status=(
                ActionExecutionStatus.VERIFIED
                if convergence.configuration_channel
                else ActionExecutionStatus.UNOBSERVABLE
            ),
            last_observable_state=", ".join(
                f"{key}:{value}" for key, value in sorted(states.items())
            )
            or "unobservable",
            details=details,
        )
        results: dict[str, RuntimeVerification] = {}
        for expectation in expectations:
            state = str(states.get(expectation.id) or "")
            forwarding = bool(authoritative and state.startswith(("FWD", "FORW")))
            results[expectation.id] = RuntimeVerification(
                expectation_id=expectation.id,
                status=(
                    ActionExecutionStatus.VERIFIED
                    if forwarding
                    else ActionExecutionStatus.UNOBSERVABLE
                ),
                evidence_method="fresh_show_spanning_tree_voice_access",
                fresh_evidence=authoritative,
                fields={
                    "voice_forwarding": (
                        FieldVerificationStatus.VERIFIED
                        if forwarding
                        else FieldVerificationStatus.UNOBSERVABLE
                    ),
                },
                message=(
                    ""
                    if forwarding
                    else (
                        "Voice access forwarding did not converge within the "
                        f"bounded window; last state={state or 'unobservable'}; "
                        f"terminal failure dimension={failure_dimension}."
                    )
                ),
                convergence=report,
            )
        return results

    def observe_access_forwarding(
        self,
        device_name: str,
        vlan_id: int,
        interfaces: Sequence[str],
        *,
        max_samples: int = ACCESS_FORWARDING_MAX_SAMPLES,
        deadline_seconds: float = ACCESS_FORWARDING_DEADLINE_SECONDS,
        interval_seconds: float = ACCESS_FORWARDING_INTERVAL_SECONDS,
        sample_calls: int = ACCESS_FORWARDING_SAMPLE_CALLS,
        remaining_seconds: float | None = None,
        episode_calls: int | None = None,
    ) -> AccessForwardingObservation:
        """Observe one switch/VLAN group's exact interfaces, neutrally.

        Same registered dispatch, same parser, same authority core as the
        Voice observer, and nothing of its semantics: no `voice_vlan_id`, no
        `voice_forwarding` field, no PVST learning extension and no inherited
        simulation-time window. The three bounds are separate and all of them
        are hard: a sample count, a wall-clock deadline read from the injected
        clock, and whatever the caller's operation ledger still allows, which
        stops the loop by refusing the next dispatch.

        Sampling stops at the first sample whose every requested interface is
        forwarding. A sequence that never gets there is returned as it was
        observed; nothing is reconfigured to make it converge.

        What is returned separates the observation from the decision. The
        top-level rows, identity and budget fields describe the LAST sample,
        because its rows are the ones a caller may act on; every sample keeps
        its own record in the history. `episode_budget_exhausted` and
        `episode_end_reason` describe the episode and never the last sample,
        so a read that failed recoverably early cannot refuse a complete read
        that followed it. `deadline_reached` with `deadline_cause` is the only
        decision here: the window is closed, and by which boundary.

        `episode_calls`, when given, is what all samples and the auxiliary
        read may spend together. Each sample may still spend up to
        `sample_calls`, but never more than the episode has left, and no
        sample starts once nothing is left. Without it the episode is bounded
        by its samples alone, as before.
        """
        requested = tuple(dict.fromkeys(str(item) for item in interfaces if item))
        if (
            isinstance(max_samples, bool)
            or not isinstance(max_samples, int)
            or max_samples < 0
        ):
            raise ValueError("access forwarding max_samples must be a non-negative int")
        numeric_bounds = (deadline_seconds, interval_seconds)
        if remaining_seconds is not None:
            numeric_bounds += (remaining_seconds,)
        if any(
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not isfinite(float(value))
            or float(value) < 0
            for value in numeric_bounds
        ):
            raise ValueError(
                "access forwarding time bounds must be finite and non-negative"
            )
        if isinstance(sample_calls, bool) or not isinstance(sample_calls, int):
            raise ValueError("access forwarding sample_calls must be an int")
        if sample_calls < 1:
            raise ValueError("access forwarding sample_calls must be positive")
        if episode_calls is not None and (
            isinstance(episode_calls, bool)
            or not isinstance(episode_calls, int)
            or episode_calls < 1
        ):
            raise ValueError("access forwarding episode_calls must be a positive int")
        ceiling = max_samples
        group_window = float(deadline_seconds)
        parent_window = (
            float(remaining_seconds) if remaining_seconds is not None else float("inf")
        )
        deadline_window = min(group_window, parent_window)
        deadline_scope = (
            "group"
            if group_window < parent_window
            else "invocation_remaining"
            if parent_window < group_window
            else "group_equals_remaining"
        )
        interval = float(interval_seconds)
        started = self._clock()
        deadline = started + deadline_window
        samples = 0
        self._forwarding_channel.calls = 0
        # Two budget facts, deliberately not one. The first describes the
        # sample a decision will read; the second only says that something,
        # somewhere in this episode, ended on its budget.
        sample_budget_exhausted = False
        episode_budget_exhausted = False
        sample_after_deadline = False
        episode_end_reason = ""
        show: IosCommandResult | None = None
        rows: tuple[AccessForwardingRow, ...] = ()
        history: list[AccessForwardingSampleEvidence] = []
        vlan_present = False
        authoritative = False
        while samples < ceiling:
            if self._forwarding_channel.stopped:
                # Nothing below will answer again, so polling for it is not
                # patience, it is a spin. The reason the channel gave is kept.
                episode_end_reason = self._forwarding_channel.stop_reason
                break
            if self._clock() >= deadline:
                episode_end_reason = "deadline"
                break
            granted = sample_calls
            if episode_calls is not None:
                left = episode_calls - self._forwarding_channel.calls
                if left <= 0:
                    # The episode's allowance is spent. Starting a sample that
                    # can dispatch nothing would only record an exhaustion.
                    episode_budget_exhausted = True
                    episode_end_reason = "episode_call_budget_exhausted"
                    break
                granted = min(sample_calls, left)
            # The bound travels with the call, not around it: each nested
            # dispatch is capped by the time this observation has left and
            # refused past the sample's own call budget.
            self._forwarding_channel.open(calls=granted, deadline=deadline)
            calls_before = self._forwarding_channel.calls
            show = self._forwarding_ios.execute(
                device_name,
                OperationalQueryId.SHOW_SPANNING_TREE,
            )
            samples += 1
            # This sample's own exhaustion replaces the previous sample's: it
            # is the one whose rows the admission is about. The episode keeps
            # the fact that an exhaustion happened, under its own name.
            sample_budget_exhausted = self._forwarding_channel.exhausted
            episode_budget_exhausted = (
                episode_budget_exhausted or sample_budget_exhausted
            )
            # An answer that arrived after the bounded window is late evidence
            # about this sample, not authority. It is kept and it grants nothing.
            sample_after_deadline = self._clock() >= deadline
            authoritative = spanning_tree_sample_is_authoritative(show, device_name)
            vlan_present = False
            rows = ()
            if authoritative:
                instance = spanning_tree_vlan_instance(show.output, vlan_id)
                vlan_present = instance is not None
                if instance is not None:
                    rows = tuple(
                        _access_forwarding_row(instance, interface)
                        for interface in requested
                    )
            history.append(
                AccessForwardingSampleEvidence(
                    elapsed_ms=int(max(0.0, self._clock() - started) * 1000),
                    rows=rows,
                    executed=show.executed,
                    fresh_output_observed=show.fresh_output_observed,
                    output_complete=show.output_complete,
                    observed_device_name=show.observed_device_name,
                    device_identity_provenance=show.device_identity_provenance,
                    vlan_present=vlan_present,
                    channel_calls=self._forwarding_channel.calls - calls_before,
                    sample_budget_exhausted=sample_budget_exhausted,
                    deadline_reached=sample_after_deadline,
                )
            )
            if rows and all(
                item.matches == 1 and str(item.state).upper() in FORWARDING_STATES
                for item in rows
            ):
                episode_end_reason = "all_requested_interfaces_observed_forwarding"
                break
            if samples >= ceiling:
                episode_end_reason = "max_samples_reached"
                break
            remaining = deadline - self._clock()
            if remaining <= 0:
                episode_end_reason = "deadline"
                break
            self._sleeper(min(interval, remaining))
        if not episode_end_reason:
            episode_end_reason = (
                "max_samples_reached" if ceiling else "no_sample_requested"
            )
        auxiliary_calls = 0
        auxiliary_budget_exhausted = False
        auxiliary_read_after_deadline = False
        simulation_time = "not_sampled"
        if (
            samples
            and episode_calls is not None
            and self._forwarding_channel.calls >= episode_calls
        ):
            simulation_time = "not_sampled_call_budget"
        elif samples and self._clock() < deadline:
            # The default reader performs one bridge call over the same bounded
            # channel. An injected reader is an opaque auxiliary call; it is
            # charged here and its elapsed time is checked before permission.
            # Both facts belong to the auxiliary read, never to the sample.
            self._forwarding_channel.open(calls=1, deadline=deadline)
            simulation_time = self._simulation_time_text()
            auxiliary_calls = int(self._forwarding_aux_is_injected)
            auxiliary_budget_exhausted = self._forwarding_channel.exhausted
            auxiliary_read_after_deadline = self._clock() >= deadline
        elif samples:
            simulation_time = "not_sampled_deadline"
        # The window is closed when a boundary closed it, and the boundary that
        # did is the one reported. The order is most specific first: this
        # sample's own lateness, then the auxiliary read's overrun, then the
        # window simply ending. An episode that stopped for any other reason
        # while the window was still open closes nothing.
        deadline_cause = ""
        if sample_after_deadline:
            deadline_cause = CAUSE_SAMPLE_AFTER_DEADLINE
        elif auxiliary_read_after_deadline:
            deadline_cause = CAUSE_AUXILIARY_READ_AFTER_DEADLINE
        elif self._clock() >= deadline:
            deadline_cause = CAUSE_EPISODE_WINDOW_ENDED
        return AccessForwardingObservation(
            switch_name=device_name,
            vlan_id=vlan_id,
            requested_interfaces=requested,
            rows=rows,
            executed=bool(show is not None and show.executed),
            fresh_output_observed=bool(show is not None and show.fresh_output_observed),
            output_complete=bool(show is not None and show.output_complete),
            observed_device_name=(show.observed_device_name if show else ""),
            device_identity_provenance=(
                show.device_identity_provenance if show else ""
            ),
            vlan_present=vlan_present,
            samples=samples,
            sample_history=tuple(history),
            max_samples=ceiling,
            deadline_seconds=deadline_window,
            elapsed_ms=int(max(0.0, self._clock() - started) * 1000),
            deadline_reached=bool(deadline_cause),
            deadline_cause=deadline_cause,
            deadline_scope=deadline_scope,
            sample_call_budget=sample_calls,
            channel_calls=self._forwarding_channel.calls + auxiliary_calls,
            sample_budget_exhausted=sample_budget_exhausted,
            sample_after_deadline=sample_after_deadline,
            episode_budget_exhausted=episode_budget_exhausted,
            episode_end_reason=episode_end_reason,
            auxiliary_budget_exhausted=auxiliary_budget_exhausted,
            auxiliary_read_after_deadline=auxiliary_read_after_deadline,
            simulation_time=simulation_time,
            failure_reason=(
                CAUSE_SAMPLE_BUDGET_EXHAUSTED
                if sample_budget_exhausted and not authoritative
                else (
                    (show.failure_reason if show is not None else "no_sample_taken")
                    or ("" if authoritative else "stp_sample_not_authoritative")
                )
            ),
        )

    def observe_trunk_continuity(
        self,
        switches: Sequence[tuple[str, Sequence[str]]],
        vlan_id: int,
        *,
        settled: Callable[[TrunkContinuityRound], bool],
        remaining_seconds: float,
        max_rounds: int,
        deadline_seconds: float,
        interval_seconds: float,
        sample_calls: int,
        episode_calls: int | None = None,
    ) -> TrunkContinuityObservation:
        """Read the registered trunk table of every listed switch, per round.

        One round reads each switch once with the registered `show interfaces
        trunk` query, through the same bounded channel as the forwarding
        observer: each reading has its own call budget and every call is capped
        by the window. Rounds stop when `settled` accepts a complete round, when
        the window closes, when the round ceiling is reached, or when the
        channel stops granting calls; nothing is reconfigured to make a path
        appear. Each reading keeps only the requested trunk interfaces, and a
        reading that is late, incomplete, not fresh or not attributed to
        exactly its switch is kept as such and authorizes nothing.

        `episode_calls`, when given, bounds every reading of the episode
        together: a reading may spend up to `sample_calls` but never more than
        is left, and no reading starts once nothing is left.
        """
        if isinstance(max_rounds, bool) or not isinstance(max_rounds, int):
            raise ValueError("trunk continuity max_rounds must be an int")
        if sample_calls < 1:
            raise ValueError("trunk continuity sample_calls must be positive")
        if episode_calls is not None and (
            isinstance(episode_calls, bool)
            or not isinstance(episode_calls, int)
            or episode_calls < 1
        ):
            raise ValueError("trunk continuity episode_calls must be a positive int")
        requested = tuple((str(name), tuple(ports)) for name, ports in switches)
        window = min(float(deadline_seconds), float(remaining_seconds))
        started = self._clock()
        deadline = started + window
        rounds: list[TrunkContinuityRound] = []
        calls = 0
        end_reason = ""
        while len(rounds) < max_rounds:
            if self._forwarding_channel.stopped:
                end_reason = self._forwarding_channel.stop_reason
                break
            if self._clock() >= deadline:
                end_reason = "deadline"
                break
            readings: list[TrunkSwitchReading] = []
            allowance_spent = False
            for name, ports in requested:
                if self._forwarding_channel.stopped or self._clock() >= deadline:
                    break
                granted = sample_calls
                if episode_calls is not None:
                    left = episode_calls - calls
                    if left <= 0:
                        allowance_spent = True
                        break
                    granted = min(sample_calls, left)
                self._forwarding_channel.open(calls=granted, deadline=deadline)
                before = self._forwarding_channel.calls
                show = self._forwarding_ios.execute(
                    name, OperationalQueryId.SHOW_INTERFACES_TRUNK
                )
                spent = self._forwarding_channel.calls - before
                calls += spent
                rows = (
                    parse_show_interfaces_trunk(show.output)
                    if show.executed and show.output_complete
                    else []
                )
                readings.append(
                    TrunkSwitchReading(
                        switch_name=name,
                        executed=show.executed,
                        fresh_output_observed=show.fresh_output_observed,
                        output_complete=show.output_complete,
                        observed_device_name=show.observed_device_name,
                        device_identity_provenance=show.device_identity_provenance,
                        ports=tuple(
                            _trunk_port_reading(rows, port, self._same_interface)
                            for port in ports
                        ),
                        channel_calls=spent,
                        call_budget_exhausted=self._forwarding_channel.exhausted,
                        after_deadline=self._clock() >= deadline,
                        failure_reason=show.failure_reason,
                    )
                )
            round_ = TrunkContinuityRound(
                index=len(rounds),
                elapsed_ms=int(max(0.0, self._clock() - started) * 1000),
                readings=tuple(readings),
                complete=len(readings) == len(requested),
            )
            rounds.append(round_)
            if round_.complete and settled(round_):
                end_reason = "required_pairs_joined"
                break
            if allowance_spent or (
                episode_calls is not None and calls >= episode_calls
            ):
                end_reason = "episode_call_budget_exhausted"
                break
            remaining = deadline - self._clock()
            if remaining <= 0:
                end_reason = "deadline"
                break
            if len(rounds) < max_rounds:
                self._sleeper(min(float(interval_seconds), remaining))
        if not end_reason:
            end_reason = "max_rounds_reached"
        closed = self._clock() >= deadline
        return TrunkContinuityObservation(
            vlan_id=vlan_id,
            switch_names=tuple(name for name, _ in requested),
            rounds=tuple(rounds),
            deadline_seconds=window,
            elapsed_ms=int(max(0.0, self._clock() - started) * 1000),
            deadline_reached=closed,
            deadline_cause="continuity_window_ended" if closed else "",
            episode_end_reason=end_reason,
            channel_calls=calls,
        )

    def _simulation_time_text(self) -> str:
        """Report the simulation-time reader, when the composition has one.

        Wall-clock time, simulation time and the operation budget are three
        separate bounds. This runtime only ever bounds the first and the
        third; the second is read when a reader exists and is named `absent`
        when none was composed, which is a fact about this run rather than a
        claim that simulation time stood still.
        """
        reader = self._forwarding_simulation_time_observer
        if reader is None:
            return "absent"
        try:
            observed = reader()
        except Exception as exc:
            return f"unreadable:{type(exc).__name__}"
        if not getattr(observed, "observed", False):
            return "unobserved"
        return f"sim_time:{observed.sim_time};frames:{observed.frames}"

    def read_dhcp_pool(
        self,
        device_name: str,
        pool_name: str,
        lease_start: str,
        lease_end: str,
    ) -> DhcpPoolReadbackObservation:
        """Read pool existence, range coverage and available space only."""
        show = self._ios.execute(
            device_name,
            OperationalQueryId.SHOW_IP_DHCP_POOL,
        )
        fresh = bool(show.executed and show.fresh_output_observed)
        complete = bool(show.output_complete)
        identity = (
            show.device_identity_provenance
            == DeviceIdentityProvenance.CONFIRMED_UNIQUE.value
        )
        reason = show.failure_reason
        if not reason and not fresh:
            reason = "No fresh current show ip dhcp pool output was observed."
        if not reason and not complete:
            reason = "The show ip dhcp pool output was incomplete."
        if not reason and not identity:
            reason = "The DHCP pool table was not attributed to one device."
        pools = (
            parse_show_ip_dhcp_pool(show.output)
            if fresh and complete and identity
            else None
        )
        if pools is None:
            return DhcpPoolReadbackObservation(
                device_name=device_name,
                requested_pool_name=pool_name,
                requested_range_start=lease_start,
                requested_range_end=lease_end,
                fresh_evidence=fresh,
                output_complete=complete,
                identity_confirmed=identity,
                failure_reason=(reason or "The DHCP pool table did not parse."),
            )

        # `parse_show_ip_dhcp_pool` refuses a table holding two casefold-equal
        # pool identities, so matching the requested name the same way stays
        # unambiguous -- and letter case alone can never publish an absence,
        # which the ladder would read as a finding about the router.
        wanted = pool_name.casefold()
        selected = next(
            (item for item in pools if item.name.casefold() == wanted),
            None,
        )
        if selected is None:
            return DhcpPoolReadbackObservation(
                device_name=device_name,
                requested_pool_name=pool_name,
                requested_range_start=lease_start,
                requested_range_end=lease_end,
                pool_present=False,
                fresh_evidence=True,
                output_complete=True,
                identity_confirmed=True,
                failure_reason=f"Pool {pool_name!r} was absent from the table.",
            )
        try:
            requested_start = ipaddress.IPv4Address(lease_start)
            requested_end = ipaddress.IPv4Address(lease_end)
        except ipaddress.AddressValueError:
            return DhcpPoolReadbackObservation(
                device_name=device_name,
                requested_pool_name=pool_name,
                requested_range_start=lease_start,
                requested_range_end=lease_end,
                pool_present=True,
                fresh_evidence=True,
                output_complete=True,
                identity_confirmed=True,
                failure_reason="The requested lease range was not valid IPv4.",
            )
        ranges = tuple((item.range_start, item.range_end) for item in selected.subnets)
        covering = next(
            (
                item
                for item in selected.subnets
                if (
                    ipaddress.IPv4Address(item.range_start)
                    <= requested_start
                    <= requested_end
                    <= ipaddress.IPv4Address(item.range_end)
                )
            ),
            None,
        )
        only = selected.subnets[0] if len(selected.subnets) == 1 else None
        displayed = covering or only
        return DhcpPoolReadbackObservation(
            device_name=device_name,
            requested_pool_name=pool_name,
            requested_range_start=lease_start,
            requested_range_end=lease_end,
            pool_present=True,
            requested_range_covered=covering is not None,
            range_start=displayed.range_start if displayed is not None else "",
            range_end=displayed.range_end if displayed is not None else "",
            subnet_ranges=ranges,
            total_addresses=selected.total_addresses,
            leased_addresses=selected.leased_addresses,
            excluded_addresses=selected.excluded_addresses,
            available_addresses=selected.available_addresses,
            fresh_evidence=True,
            output_complete=True,
            identity_confirmed=True,
        )

    @staticmethod
    def _refuse_batch(
        actions: Sequence[ConfigurationAction],
        message: str,
    ) -> list[RuntimeActionMutation]:
        """Rechaza el lote entero sin haber tocado ningun dispositivo."""
        return [
            RuntimeActionMutation(
                action_id=action.id,
                applied=False,
                failure_code=ConfigurationFailureCode.APPLICATION_FAILED,
                message=message,
            )
            for action in actions
        ]

    def apply_actions(
        self,
        actions: Sequence[ConfigurationAction],
    ) -> list[RuntimeActionMutation]:
        """Apply one preflighted configuration batch through its owning channel."""
        results: dict[str, RuntimeActionMutation] = {}
        ios_by_device: dict[str, list[ConfigurationAction]] = defaultdict(list)
        endpoints: list[SetEndpointStaticAddress | SetEndpointDhcp] = []
        unroutable: list[ConfigurationAction] = []
        for action in actions:
            if isinstance(action, _IOS_ACTIONS):
                ios_by_device[action.device_name].append(action)
            elif isinstance(action, _ENDPOINT_ACTIONS):
                endpoints.append(action)
            else:
                unroutable.append(action)

        # Enrutabilidad y renderizabilidad se comprueban sobre TODO el lote
        # antes de la primera mutacion. Fallar a mitad dejaria la red en un
        # estado que nadie pidio, y ese estado es peor que no haber empezado.
        if unroutable:
            return self._refuse_batch(
                actions,
                "No runtime channel handles "
                + ", ".join(sorted({type(item).__name__ for item in unroutable}))
                + "; the batch was refused before any device was touched.",
            )

        if ios_by_device and not self._targets:
            self.inventory()

        prerendered: dict[str, list] = {}
        for device_name, device_actions in sorted(ios_by_device.items()):
            target = self._targets.get(device_name)
            try:
                prerendered[device_name] = self._renderer.render_device_batches(
                    device_name,
                    target.model if target else "",
                    device_actions,
                )
            except ValueError as exc:
                return self._refuse_batch(
                    actions,
                    f"{device_name}: {exc}; the batch was refused before any "
                    "device was touched.",
                )

        for device_name, device_actions in sorted(ios_by_device.items()):
            if device_name not in self._ready_ios_devices:
                if not self._ios_readiness(device_name):
                    for action in device_actions:
                        results[action.id] = RuntimeActionMutation(
                            action_id=action.id,
                            applied=False,
                            failure_code=ConfigurationFailureCode.SESSION_FAILED,
                            message="IOS did not reach OPERATIONAL_READY before configuration.",
                        )
                    continue
                self._ready_ios_devices.add(device_name)
            # Ya renderizado en el preflight: aqui solo queda aplicar.
            for batch in prerendered[device_name]:
                applied = self._configuration.configure_ios(
                    device_name, batch.ios_payload
                )
                batch_id = f"{device_name}:{int(batch.phase)}"
                for action_id in batch.action_ids:
                    results[action_id] = RuntimeActionMutation(
                        action_id=action_id,
                        applied=applied,
                        failure_code=(
                            ConfigurationFailureCode.NONE
                            if applied
                            else ConfigurationFailureCode.APPLICATION_FAILED
                        ),
                        message=(
                            "Configuration batch accepted by Packet Tracer."
                            if applied
                            else "Packet Tracer rejected the configuration batch."
                        ),
                        batch_id=batch_id,
                    )

        ordered = sorted(endpoints, key=lambda item: item.id)
        chunks = [
            ordered[start : start + MAX_ENDPOINT_CALLS_PER_SEND]
            for start in range(0, len(ordered), MAX_ENDPOINT_CALLS_PER_SEND)
        ]
        for index, chunk in enumerate(chunks):
            # Script size is bounded by the call count of one send. A chunk
            # the engine refuses marks only its own actions; the others keep
            # their own outcome, and a lone chunk keeps the historical id.
            payload = "".join(self._endpoint_call(action) for action in chunk)
            applied = bool(payload) and self._send(payload)
            batch_id = "endpoints:" + str(int(chunk[0].phase))
            if len(chunks) > 1:
                batch_id += f":{index}"
            for action in chunk:
                results[action.id] = RuntimeActionMutation(
                    action_id=action.id,
                    applied=applied,
                    failure_code=(
                        ConfigurationFailureCode.NONE
                        if applied
                        else ConfigurationFailureCode.APPLICATION_FAILED
                    ),
                    message=(
                        "Endpoint batch accepted by Packet Tracer."
                        if applied
                        else "Packet Tracer rejected the endpoint batch."
                    ),
                    batch_id=batch_id,
                )
        return [
            results.get(
                action.id,
                RuntimeActionMutation(
                    action_id=action.id,
                    applied=False,
                    failure_code=ConfigurationFailureCode.APPLICATION_FAILED,
                    message="No Packet Tracer adapter exists for this typed action.",
                ),
            )
            for action in actions
        ]

    def _wait_for_ios(self, device_name: str) -> bool:
        readiness = self._ios.wait_until_ready(
            device_name,
            timeout_seconds=self._ios_boot_timeout,
            **self._wait_controls(),
        )
        return readiness.state is DeviceInitializationState.OPERATIONAL_READY

    def _wait_controls(self) -> dict[str, Any]:
        """Return the waiter controls a composed allowance requires, or none.

        An empty mapping keeps a waiter's own clock and sleeper, which is the
        ordinary composition. With a control, the waiter shares this runtime's
        clock and sleeper and ends when the caller's allowance ends.
        """
        if self._wait_allowance is None:
            return {}
        return {
            "clock": self._clock,
            "sleeper": self._sleeper,
            "remaining_seconds": self._wait_allowance,
        }

    @staticmethod
    def _endpoint_call(action: SetEndpointStaticAddress | SetEndpointDhcp) -> str:
        name = json.dumps(action.device_name)
        interface = json.dumps(action.interface)
        if isinstance(action, SetEndpointDhcp):
            call = (
                "configurePcIp("
                + ",".join((name, "true", "null", "null", "null", "null", interface))
                + ");"
            )
        else:
            arguments = ",".join(
                (
                    name,
                    "false",
                    json.dumps(action.ipv4),
                    json.dumps(action.netmask),
                    json.dumps(action.gateway),
                    json.dumps(action.dns_server or ""),
                    interface,
                )
            )
            call = "configurePcIp(" + arguments + ");"
        return "try{" + call + "}catch(__e){}"

    def verify(
        self,
        expectations: Sequence[VerificationExpectation],
    ) -> list[RuntimeVerification]:
        """Verify each E5 expectation through its typed reader."""
        ios_cache: dict[tuple[str, OperationalQueryId], object] = {}
        trunk_results = {
            item.expectation_id: item
            for item in self._verify_trunks(
                [
                    expectation
                    for expectation in expectations
                    if expectation.kind is VerificationKind.TRUNK
                ]
            )
        }
        results: list[RuntimeVerification] = []
        for expectation in expectations:
            if expectation.kind is VerificationKind.HOSTNAME:
                results.append(self._verify_hostname(expectation))
            elif expectation.kind is VerificationKind.VLAN:
                results.append(self._verify_vlan(expectation))
            elif expectation.kind is VerificationKind.TRUNK:
                results.append(trunk_results[expectation.id])
            elif expectation.kind is VerificationKind.L3_INTERFACE:
                results.append(self._verify_l3(expectation, ios_cache))
            elif expectation.kind is VerificationKind.SERIAL_CONTROLLER:
                results.append(self._verify_serial_controller(expectation))
            elif expectation.kind is VerificationKind.ENDPOINT_ADDRESSING:
                results.append(self._verify_endpoint(expectation))
            elif expectation.kind is VerificationKind.ENDPOINT_DHCP_MODE:
                results.append(self._verify_endpoint_dhcp_mode(expectation))
            elif expectation.kind is VerificationKind.ACCESS_PORT:
                results.append(self._verify_access_port(expectation))
            elif expectation.kind is VerificationKind.DHCP_POOL:
                results.append(self._unobservable(expectation))
        return results

    def _observe_pvst_boundary(self, device_name: str) -> dict[str, object]:
        """Read one PVST boundary, normalized so absence cannot authorize.

        Every caller of the registered observer needs the same three outcomes
        collapsed into one object -- no observer, a raised read, or a result
        that is not an object at all -- because an extension decision reads
        these dicts and a missing ``authoritative`` must fail closed rather
        than raise inside a convergence round.
        """
        if self._trunk_transition_observer is None:
            return {}
        try:
            observed = self._trunk_transition_observer(device_name)
        except Exception as exc:
            return {
                "authoritative": False,
                "failure_reason": f"{type(exc).__name__}: {exc}",
            }
        if not isinstance(observed, dict):
            return {
                "authoritative": False,
                "failure_reason": (
                    "The PVST boundary observer returned a non-object result."
                ),
            }
        return observed

    def _verify_trunks(
        self,
        expectations: Sequence[VerificationExpectation],
    ) -> list[RuntimeVerification]:
        """Observe all trunks round-robin and retain every state transition."""
        ordered = list(expectations)
        if not ordered:
            return []
        started = monotonic()
        grouped: dict[str, list[VerificationExpectation]] = defaultdict(list)
        for expectation in ordered:
            grouped[expectation.device_name].append(expectation)

        latest: dict[str, dict[str, object]] = {}
        transitions: dict[str, list[dict[str, object]]] = defaultdict(list)
        signatures: dict[str, tuple[object, ...]] = {}
        round_failures: list[dict[str, object]] = []
        sample_round = 0
        learning_boundary_stp: dict[str, dict[str, object]] = {}
        learning_extension_observation_active = False
        learning_extension_expectation_ids: frozenset[str] = frozenset()

        def inspect(
            expectation_ids: frozenset[str] | None = None,
        ) -> dict[str, object]:
            nonlocal sample_round
            sample_round += 1
            round_latest: dict[str, dict[str, object]] = {}
            round_signatures: dict[str, tuple[object, ...]] = {}
            round_correlated: dict[str, dict[str, object]] = {}
            try:
                for device_name in sorted(grouped):
                    device_expectations = [
                        expectation
                        for expectation in grouped[device_name]
                        if (
                            expectation_ids is None or expectation.id in expectation_ids
                        )
                    ]
                    if not device_expectations:
                        continue
                    show = self._ios.execute(
                        device_name,
                        OperationalQueryId.SHOW_INTERFACES_TRUNK,
                    )
                    authoritative = bool(
                        show.executed
                        and show.fresh_output_observed
                        and show.output_complete
                        and show.observed_device_name == device_name
                        and show.device_identity_provenance
                        == DeviceIdentityProvenance.CONFIRMED_UNIQUE.value
                    )
                    rows = (
                        parse_show_interfaces_trunk(show.output)
                        if authoritative
                        else []
                    )
                    changed: list[str] = []
                    for expectation in device_expectations:
                        expected_interface = str(
                            expectation.expected.get("interface") or ""
                        )
                        row = next(
                            (
                                item
                                for item in rows
                                if self._same_interface(
                                    item.interface,
                                    expected_interface,
                                )
                            ),
                            None,
                        )
                        observed = self._trunk_observation(
                            expectation,
                            show,
                            row,
                            authoritative=authoritative,
                        )
                        round_latest[expectation.id] = observed
                        signature = self._trunk_observation_signature(
                            observed,
                        )
                        round_signatures[expectation.id] = signature
                        if signatures.get(expectation.id) != signature:
                            changed.append(expectation.id)
                    # An extension is only ever justified by a boundary read
                    # from THIS round: an unchanged trunk row must not keep
                    # an earlier LRN alive.  Only a device that still has a
                    # pending expectation feeds that authority, so no other
                    # device pays for a read the decision never consults.
                    device_pending = any(
                        not self._trunk_observation_verified(
                            round_latest[item.id],
                        )
                        for item in device_expectations
                    )
                    refresh_boundary = bool(
                        learning_extension_observation_active and device_pending
                    )
                    if not changed and not refresh_boundary:
                        continue
                    correlated = self._observe_pvst_boundary(device_name)
                    if refresh_boundary:
                        learning_boundary_stp[device_name] = correlated
                    for identifier in changed:
                        round_correlated[identifier] = correlated
            except Exception as exc:
                failure_reason = f"{type(exc).__name__}: {exc}"
                round_failures.append(
                    {
                        "sample_round": sample_round,
                        "failure_reason": failure_reason,
                    }
                )
                return {
                    "found": bool(latest),
                    "configuration_channel": False,
                    "failure_reason": failure_reason,
                }

            latest.update(round_latest)
            for identifier, signature in round_signatures.items():
                if signatures.get(identifier) == signature:
                    continue
                signatures[identifier] = signature
                transition = {
                    "sample_round": sample_round,
                    **self._trunk_transition_payload(
                        round_latest[identifier],
                    ),
                }
                if self._trunk_transition_observer is not None:
                    transition["correlated_stp"] = round_correlated.get(
                        identifier,
                        {},
                    )
                transitions[identifier].append(transition)

            complete = bool(latest) and all(
                self._trunk_observation_verified(latest[item.id]) for item in ordered
            )
            return {
                "found": bool(latest),
                "configuration_channel": complete,
                "failure_reason": "",
                "continuation_authorized": bool(
                    complete
                    or (
                        learning_extension_observation_active
                        and learning_extension_cohort_continuation_authorized()
                    )
                    or (
                        not learning_extension_observation_active
                        and pending_learning_progress_target_ms() is not None
                    )
                ),
            }

        def capture_learning_boundary(
            expectation_ids: frozenset[str],
        ) -> None:
            if self._trunk_transition_observer is None:
                return
            pending_devices = sorted(
                {
                    expectation.device_name
                    for expectation in ordered
                    if expectation.id in expectation_ids
                }
            )
            for device_name in pending_devices:
                learning_boundary_stp[device_name] = self._observe_pvst_boundary(
                    device_name
                )

        def expectation_learning_progress_target_ms(
            expectation: VerificationExpectation,
            *,
            allow_forwarding: bool = False,
        ) -> float | None:
            observed = latest.get(expectation.id, {})
            fields = observed.get("fields")
            if not isinstance(fields, dict):
                return None
            if any(
                fields.get(name) is not FieldVerificationStatus.VERIFIED
                for name in (
                    "interface",
                    "status",
                    "allowed_vlans",
                    "active_vlans",
                )
            ):
                return None
            if fields.get("forwarding_vlans") is not FieldVerificationStatus.FAILED:
                return None
            correlated = learning_boundary_stp.get(expectation.device_name)
            if (
                not isinstance(correlated, dict)
                or correlated.get("authoritative") is not True
                or correlated.get("device_name") != expectation.device_name
            ):
                return None
            instances = {
                item.get("vlan_id"): item
                for item in correlated.get("instances", [])
                if isinstance(item, dict)
            }
            progress_targets: set[float] = set()
            expected_interface = str(expectation.expected.get("interface") or "")
            for vlan_id in {
                int(item) for item in expectation.expected.get("allowed_vlans", [])
            }:
                instance = instances.get(vlan_id)
                if (
                    not isinstance(instance, dict)
                    or instance.get("authoritative") is not True
                ):
                    return None
                progress_target = pvst_learning_progress_target_ms(
                    instance.get("forward_delay_seconds"),
                )
                if progress_target is None:
                    return None
                progress_targets.add(progress_target)
                port = next(
                    (
                        item
                        for item in instance.get("ports", [])
                        if isinstance(item, dict)
                        and self._same_interface(
                            str(item.get("interface") or ""),
                            expected_interface,
                        )
                    ),
                    None,
                )
                state = str(port.get("state") if isinstance(port, dict) else "").upper()
                allowed_states = {"LRN", "FWD"} if allow_forwarding else {"LRN"}
                if (
                    port is None
                    or port.get("row_present") is not True
                    or state not in allowed_states
                ):
                    return None
            if len(progress_targets) != 1:
                return None
            return next(iter(progress_targets))

        def learning_progress_target_ms(
            expectation_ids: frozenset[str],
        ) -> float | None:
            pending = False
            progress_targets: set[float] = set()
            for expectation in ordered:
                if expectation.id not in expectation_ids:
                    continue
                observed = latest.get(expectation.id, {})
                if self._trunk_observation_verified(observed):
                    continue
                pending = True
                progress_target = expectation_learning_progress_target_ms(
                    expectation,
                )
                if progress_target is None:
                    return None
                progress_targets.add(progress_target)
            if not pending or len(progress_targets) != 1:
                return None
            return next(iter(progress_targets))

        def pending_learning_progress_target_ms() -> float | None:
            return learning_progress_target_ms(
                frozenset(
                    expectation.id
                    for expectation in ordered
                    if not self._trunk_observation_verified(
                        latest.get(expectation.id, {}),
                    )
                )
            )

        def learning_extension_cohort_continuation_authorized() -> bool:
            if not learning_extension_expectation_ids:
                return False
            for expectation in ordered:
                if expectation.id not in learning_extension_expectation_ids:
                    continue
                observed = latest.get(expectation.id, {})
                if self._trunk_observation_verified(observed):
                    continue
                if (
                    expectation_learning_progress_target_ms(
                        expectation,
                        allow_forwarding=True,
                    )
                    is None
                ):
                    return False
            return True

        initial_convergence = StateConvergenceWaiter(
            inspect,
            timeout_seconds=self._trunk_timeout,
            interval_seconds=self._convergence_interval,
            **self._wait_controls(),
        ).wait()
        learning_boundary_refresh_performed = False
        learning_boundary_refresh_complete = False
        learning_boundary_refresh_error = ""
        learning_boundary_expectation_ids = frozenset(
            expectation.id
            for expectation in ordered
            if not self._trunk_observation_verified(
                latest.get(expectation.id, {}),
            )
        )
        if not initial_convergence.configuration_channel:
            capture_learning_boundary(learning_boundary_expectation_ids)
            if learning_boundary_stp:
                learning_boundary_refresh_performed = True
                try:
                    refresh = inspect(learning_boundary_expectation_ids)
                    learning_boundary_refresh_error = str(
                        refresh.get("failure_reason") or "",
                    )
                    learning_boundary_refresh_complete = bool(
                        refresh["configuration_channel"]
                        and not learning_boundary_refresh_error,
                    )
                except Exception as exc:
                    learning_boundary_refresh_error = f"{type(exc).__name__}: {exc}"
        candidate_expectation_ids = frozenset(
            identifier
            for identifier in learning_boundary_expectation_ids
            if not self._trunk_observation_verified(latest.get(identifier, {}))
        )
        learning_extension_target = (
            learning_progress_target_ms(candidate_expectation_ids)
            if (
                not initial_convergence.configuration_channel
                and not learning_boundary_refresh_complete
                and not learning_boundary_refresh_error
            )
            else None
        )
        learning_extension_candidate = learning_extension_target is not None
        if learning_extension_candidate:
            learning_extension_expectation_ids = candidate_expectation_ids
        extension_convergence: SimulationTimeConvergenceResult | None = None
        if learning_extension_target is not None:
            learning_extension_observation_active = True
            try:
                extension_convergence = self._pvst_learning_extension.grant(
                    lambda: inspect(learning_extension_expectation_ids),
                    required_simulation_progress_ms=(learning_extension_target),
                )
            finally:
                learning_extension_observation_active = False
        elapsed_ms = int((monotonic() - started) * 1000)
        results: list[RuntimeVerification] = []
        for expectation in ordered:
            observed = latest.get(expectation.id, {})
            fields = dict(observed.get("fields") or {})
            status = self._trunk_observation_status(fields)
            authoritative = bool(observed.get("authoritative"))
            details = {
                "kind": "trunk_round_robin",
                "device_name": expectation.device_name,
                "interface": str(expectation.expected.get("interface") or ""),
                "expected_vlans": sorted(
                    {
                        int(item)
                        for item in expectation.expected.get("allowed_vlans", [])
                    }
                ),
                "sample_rounds": sample_round,
                "initial_sample_rounds": initial_convergence.attempts,
                "learning_extension_candidate": (learning_extension_candidate),
                "learning_extension_expectation_ids": sorted(
                    learning_extension_expectation_ids
                ),
                "learning_boundary_expectation_ids": sorted(
                    learning_boundary_expectation_ids
                ),
                **self._pvst_learning_extension.evidence(
                    extension_convergence,
                    requested_progress_ms=learning_extension_target,
                ),
                "learning_boundary_refresh_performed": (
                    learning_boundary_refresh_performed
                ),
                "learning_boundary_refresh_complete": (
                    learning_boundary_refresh_complete
                ),
                "learning_boundary_refresh_error": (learning_boundary_refresh_error),
                "learning_boundary_stp": learning_boundary_stp.get(
                    expectation.device_name,
                ),
                "transitions": transitions.get(expectation.id, []),
                "round_failures": round_failures,
                "terminal_authority": (
                    "AUTHORITATIVE" if authoritative else "UNOBSERVABLE"
                ),
                "terminal_identity_confirmed": bool(
                    observed.get("observed_device_name") == expectation.device_name
                    and observed.get("device_identity_provenance")
                    == DeviceIdentityProvenance.CONFIRMED_UNIQUE.value
                ),
                "terminal_failure_dimension": (
                    self._trunk_failure_dimension(observed, fields)
                ),
            }
            results.append(
                RuntimeVerification(
                    expectation_id=expectation.id,
                    status=status,
                    evidence_method="fresh_show_interfaces_trunk",
                    fresh_evidence=authoritative,
                    fields=fields,
                    message=self._trunk_observation_message(
                        expectation,
                        observed,
                        fields,
                        status,
                    ),
                    convergence=ConvergenceReport(
                        attempts=sample_round,
                        elapsed_ms=elapsed_ms,
                        final_status=status,
                        last_observable_state=json.dumps(
                            self._trunk_transition_payload(observed),
                            sort_keys=True,
                            separators=(",", ":"),
                        ),
                        details=details,
                    ),
                )
            )
        return results

    @staticmethod
    def _trunk_observation(
        expectation: VerificationExpectation,
        show: IosCommandResult,
        row,
        *,
        authoritative: bool,
    ) -> dict[str, object]:
        expected_vlans = {
            int(item) for item in expectation.expected.get("allowed_vlans", [])
        }

        def vlan_field(attribute: str) -> FieldVerificationStatus:
            if not authoritative:
                return FieldVerificationStatus.UNOBSERVABLE
            if row is None:
                return FieldVerificationStatus.FAILED
            value = getattr(row, attribute)
            if value is None:
                return FieldVerificationStatus.UNOBSERVABLE
            return (
                FieldVerificationStatus.VERIFIED
                if expected_vlans.issubset(value)
                else FieldVerificationStatus.FAILED
            )

        if not authoritative:
            interface_status = FieldVerificationStatus.UNOBSERVABLE
            operational_status = FieldVerificationStatus.UNOBSERVABLE
        else:
            interface_status = (
                FieldVerificationStatus.VERIFIED
                if row is not None
                else FieldVerificationStatus.FAILED
            )
            operational_status = (
                FieldVerificationStatus.VERIFIED
                if row is not None and row.status.casefold() == "trunking"
                else FieldVerificationStatus.FAILED
            )
        return {
            "authoritative": authoritative,
            "executed": bool(show.executed),
            "fresh_output_observed": bool(show.fresh_output_observed),
            "output_complete": bool(show.output_complete),
            "observed_device_name": show.observed_device_name,
            "device_identity_provenance": (show.device_identity_provenance),
            "failure_reason": show.failure_reason,
            # Retain exactly the current-command window that fed the parser.
            # Without it, a later missing row cannot be separated from a
            # delimiter/completion defect using the immutable LIVE artifact.
            "raw_output": show.output,
            "row_present": row is not None,
            "row_interface": row.interface if row is not None else "",
            "status": row.status if row is not None else "",
            "native_vlan": row.native_vlan if row is not None else None,
            "allowed_vlans": (
                list(row.allowed_vlans)
                if row is not None and row.allowed_vlans is not None
                else None
            ),
            "active_vlans": (
                list(row.active_vlans)
                if row is not None and row.active_vlans is not None
                else None
            ),
            "forwarding_vlans": (
                list(row.forwarding_vlans)
                if row is not None and row.forwarding_vlans is not None
                else None
            ),
            "fields": {
                "interface": interface_status,
                "status": operational_status,
                "allowed_vlans": vlan_field("allowed_vlans"),
                "active_vlans": vlan_field("active_vlans"),
                "forwarding_vlans": vlan_field("forwarding_vlans"),
            },
        }

    @staticmethod
    def _trunk_observation_signature(
        observed: dict[str, object],
    ) -> tuple[object, ...]:
        def vlan_set(name: str) -> tuple[object, ...] | None:
            value = observed.get(name)
            return None if value is None else tuple(value)

        return (
            observed.get("authoritative"),
            observed.get("row_present"),
            observed.get("row_interface"),
            observed.get("status"),
            observed.get("native_vlan"),
            vlan_set("allowed_vlans"),
            vlan_set("active_vlans"),
            vlan_set("forwarding_vlans"),
            observed.get("failure_reason"),
        )

    @staticmethod
    def _trunk_transition_payload(
        observed: dict[str, object],
    ) -> dict[str, object]:
        return {
            key: observed.get(key)
            for key in (
                "authoritative",
                "executed",
                "fresh_output_observed",
                "output_complete",
                "observed_device_name",
                "device_identity_provenance",
                "failure_reason",
                "raw_output",
                "row_present",
                "row_interface",
                "status",
                "native_vlan",
                "allowed_vlans",
                "active_vlans",
                "forwarding_vlans",
            )
        }

    @staticmethod
    def _trunk_observation_status(
        fields: dict[str, FieldVerificationStatus],
    ) -> ActionExecutionStatus:
        if FieldVerificationStatus.FAILED in fields.values():
            return ActionExecutionStatus.FAILED
        if fields and all(
            item is FieldVerificationStatus.VERIFIED for item in fields.values()
        ):
            return ActionExecutionStatus.VERIFIED
        return ActionExecutionStatus.UNOBSERVABLE

    @classmethod
    def _trunk_observation_verified(
        cls,
        observed: dict[str, object],
    ) -> bool:
        return (
            cls._trunk_observation_status(dict(observed.get("fields") or {}))
            is ActionExecutionStatus.VERIFIED
        )

    @staticmethod
    def _trunk_failure_dimension(
        observed: dict[str, object],
        fields: dict[str, FieldVerificationStatus],
    ) -> str:
        if not observed.get("executed"):
            return "EXECUTION"
        if not observed.get("fresh_output_observed"):
            return "FRESHNESS"
        if not observed.get("output_complete"):
            return "COMPLETENESS"
        if observed.get(
            "device_identity_provenance"
        ) != DeviceIdentityProvenance.CONFIRMED_UNIQUE.value or not observed.get(
            "observed_device_name"
        ):
            return "IDENTITY"
        if not observed.get("row_present"):
            return "NO_MATCHING_ROW"
        if fields.get("status") is FieldVerificationStatus.FAILED:
            return "NOT_TRUNKING"
        if fields.get("allowed_vlans") is FieldVerificationStatus.FAILED:
            return "ALLOWED_VLAN_OMISSION"
        if fields.get("active_vlans") is FieldVerificationStatus.FAILED:
            return "ACTIVE_VLAN_OMISSION"
        if fields.get("forwarding_vlans") is FieldVerificationStatus.FAILED:
            return "NON_FORWARDING"
        if FieldVerificationStatus.UNOBSERVABLE in fields.values():
            return "PARSING"
        return "NONE"

    @staticmethod
    def _trunk_observation_message(
        expectation: VerificationExpectation,
        observed: dict[str, object],
        fields: dict[str, FieldVerificationStatus],
        status: ActionExecutionStatus,
    ) -> str:
        if status is ActionExecutionStatus.VERIFIED:
            return ""
        if not observed.get("authoritative"):
            return str(
                observed.get("failure_reason")
                or "Trunk evidence was not fresh, complete, and uniquely attributed."
            )
        if not observed.get("row_present"):
            return "Trunk convergence timed out."
        expected_vlans = {
            int(item) for item in expectation.expected.get("allowed_vlans", [])
        }
        omissions = []
        for field_name, label in (
            ("allowed_vlans", "allowed"),
            ("active_vlans", "active"),
            ("forwarding_vlans", "forwarding"),
        ):
            if fields.get(field_name) is not FieldVerificationStatus.FAILED:
                continue
            value = observed.get(field_name)
            if isinstance(value, list):
                missing = sorted(expected_vlans - set(value))
                if missing:
                    omissions.append(
                        f"{label} omitted " + ",".join(str(item) for item in missing)
                    )
        return "; ".join(omissions) or "Trunk convergence timed out."

    def _verify_hostname(
        self,
        expectation: VerificationExpectation,
    ) -> RuntimeVerification:
        expected = str(expectation.expected["hostname"])
        name = json.dumps(expectation.device_name)
        last_observed: dict = {}

        def inspect() -> dict:
            js = "".join(
                (
                    "try{var d=ipc.network().getDevice(",
                    name,
                    ");",
                    "var t=d&&typeof d.getCommandLine==='function'?d.getCommandLine():null;",
                    "var hs=!!d&&typeof d.getHostName==='function';",
                    "var h=hs?String(d.getHostName()):'';",
                    "var p=t&&typeof t.getPrompt==='function'?String(t.getPrompt()):'';",
                    "var o=t&&typeof t.getOutput==='function'?String(t.getOutput()):'';",
                    "reportResult(JSON.stringify({found:!!d,terminal:!!t,",
                    "hostname_supported:hs,hostname:h,prompt:p,output:o}));",
                    "}catch(e){reportResult('ERROR:'+e);}",
                )
            )
            current = self._json_result(js, 3.0)
            actual = str(current.get("hostname") or "").strip()
            method = "packet_tracer_device_hostname_getter"
            if not actual:
                prompt = str(current.get("prompt") or "").strip()
                actual = self._hostname_from_prompt(prompt)
                method = "ios_terminal_prompt_identity"
                if not actual:
                    actual = self._hostname_from_output(
                        str(current.get("output") or "")
                    )
                    method = "ios_terminal_output_prompt_identity"
            current["actual_hostname"] = actual
            current["evidence_method"] = method
            current["configuration_channel"] = actual == expected
            last_observed.clear()
            last_observed.update(current)
            return current

        convergence = StateConvergenceWaiter(
            inspect,
            timeout_seconds=self._hostname_timeout,
            interval_seconds=self._convergence_interval,
            **self._wait_controls(),
        ).wait()
        actual = str(last_observed.get("actual_hostname") or "")
        evidence_method = str(
            last_observed.get("evidence_method") or "ios_terminal_prompt_identity"
        )
        if not last_observed.get("found") or not actual:
            return self._unobservable(expectation)
        verified = (
            convergence.state is DeviceInitializationState.CONFIGURATION_READY
            and actual == expected
        )
        return RuntimeVerification(
            expectation_id=expectation.id,
            status=(
                ActionExecutionStatus.VERIFIED
                if verified
                else ActionExecutionStatus.FAILED
            ),
            evidence_method=evidence_method,
            fresh_evidence=True,
            fields={
                "hostname": (
                    FieldVerificationStatus.VERIFIED
                    if verified
                    else FieldVerificationStatus.FAILED
                ),
            },
            message="" if verified else f"IOS prompt identity is {actual!r}.",
            convergence=ConvergenceReport(
                attempts=convergence.attempts,
                elapsed_ms=convergence.elapsed_ms,
                final_status=(
                    ActionExecutionStatus.VERIFIED
                    if verified
                    else ActionExecutionStatus.FAILED
                ),
                last_observable_state=actual or "unobservable",
            ),
        )

    @staticmethod
    def _hostname_from_prompt(prompt: str) -> str:
        match = re.fullmatch(r"([^\s()]+)[>#]", prompt.strip())
        return match.group(1) if match else ""

    @classmethod
    def _hostname_from_output(cls, output: str) -> str:
        # PT 9.0.1 may expose an empty getPrompt() on a 3560 while getOutput()
        # still retains the current IOS prompt. Ignore asynchronous syslog at
        # the tail and select the latest complete EXEC prompt, never a device
        # display name or an inferred model default.
        for line in reversed(output.splitlines()):
            candidate = line.strip()
            if not candidate or candidate.startswith("%"):
                continue
            hostname = cls._hostname_from_prompt(candidate)
            if hostname:
                return hostname
        return ""

    def _verify_serial_controller(
        self,
        expectation: VerificationExpectation,
    ) -> RuntimeVerification:
        """Verify the physical DCE role and exact configured clock independently."""
        expected_interface = str(expectation.expected["interface"])
        expected_role = str(expectation.expected["serial_endpoint_role"]).casefold()
        expected_rate = int(expectation.expected["clock_rate_bps"])
        show = self._ios.execute(
            expectation.device_name,
            OperationalQueryId.SHOW_CONTROLLERS_SERIAL,
            interface=expected_interface,
        )
        # `output_complete` es estrictamente mas fuerte que "no truncada": para
        # esta consulta, cualificada para continuacion acotada, exige ademas que
        # la lectura logica haya cerrado en un prompt.
        complete = bool(
            show.executed and show.fresh_output_observed and show.output_complete
        )
        row = parse_serial_controller(show.output) if complete else None
        if row is None:
            return RuntimeVerification(
                expectation_id=expectation.id,
                status=ActionExecutionStatus.UNOBSERVABLE,
                evidence_method=(
                    "registered_ios_output_truncated"
                    if show.truncated_by_pager
                    else "fresh_show_controllers_serial"
                ),
                fresh_evidence=complete,
                fields={
                    field: FieldVerificationStatus.UNOBSERVABLE
                    for field in expectation.expected
                },
                message=(
                    show.failure_reason
                    or "Fresh, complete serial-controller output was unavailable."
                ),
            )
        interface_ok = self._same_interface(row.interface, expected_interface)
        role_ok = row.endpoint_role == expected_role
        rate_ok = row.clock_rate_bps == expected_rate
        verified = interface_ok and role_ok and rate_ok
        return RuntimeVerification(
            expectation_id=expectation.id,
            status=(
                ActionExecutionStatus.VERIFIED
                if verified
                else ActionExecutionStatus.FAILED
            ),
            evidence_method="fresh_show_controllers_serial",
            fresh_evidence=True,
            fields={
                "interface": (
                    FieldVerificationStatus.VERIFIED
                    if interface_ok
                    else FieldVerificationStatus.FAILED
                ),
                "serial_endpoint_role": (
                    FieldVerificationStatus.VERIFIED
                    if role_ok
                    else FieldVerificationStatus.FAILED
                ),
                "clock_rate_bps": (
                    FieldVerificationStatus.VERIFIED
                    if rate_ok
                    else FieldVerificationStatus.FAILED
                ),
            },
            message=(
                ""
                if verified
                else "Serial controller does not match the planned DCE role and clock."
            ),
        )

    def _verify_vlan(self, expectation: VerificationExpectation) -> RuntimeVerification:
        vlan_id = int(expectation.expected["vlan_id"])
        name = json.dumps(expectation.device_name)

        def inspect() -> dict:
            js = "".join(
                (
                    "try{var d=ipc.network().getDevice(",
                    name,
                    ");",
                    "var vm=d&&typeof d.getProcess==='function'?d.getProcess('VlanManager'):null;",
                    "var present=false;if(vm){for(var i=0;i<vm.getVlanCount();i++){var v=vm.getVlanAt(i);",
                    "if(v&&v.getVlanNumber()===",
                    str(vlan_id),
                    "){present=true;break;}}}",
                    "reportResult(JSON.stringify({found:!!d,configuration_channel:present,present:present}));",
                    "}catch(e){reportResult('ERROR:'+e);}",
                )
            )
            return self._json_result(js, 3.0)

        convergence = StateConvergenceWaiter(
            inspect,
            timeout_seconds=self._vlan_timeout,
            interval_seconds=self._convergence_interval,
            **self._wait_controls(),
        ).wait()
        verified = convergence.configuration_channel
        return RuntimeVerification(
            expectation_id=expectation.id,
            status=ActionExecutionStatus.VERIFIED
            if verified
            else ActionExecutionStatus.FAILED,
            evidence_method="vlan_manager_object_state",
            fresh_evidence=True,
            fields={
                "vlan_id": (
                    FieldVerificationStatus.VERIFIED
                    if verified
                    else FieldVerificationStatus.FAILED
                )
            },
            convergence=ConvergenceReport(
                attempts=convergence.attempts,
                elapsed_ms=convergence.elapsed_ms,
                final_status=(
                    ActionExecutionStatus.VERIFIED
                    if verified
                    else ActionExecutionStatus.FAILED
                ),
                last_observable_state="present" if verified else "absent",
            ),
        )

    def _verify_trunk(
        self,
        expectation: VerificationExpectation,
        cache: dict,
    ) -> RuntimeVerification:
        expected_interface = str(expectation.expected["interface"])
        expected_vlans = frozenset(
            int(item) for item in expectation.expected.get("allowed_vlans", [])
        )

        def find_row(show: IosCommandResult):
            return (
                next(
                    (
                        item
                        for item in parse_show_interfaces_trunk(show.output)
                        if self._same_interface(item.interface, expected_interface)
                    ),
                    None,
                )
                if show.executed
                else None
            )

        def vlan_status(
            show: IosCommandResult,
            row,
            attribute: str,
        ) -> FieldVerificationStatus:
            if (
                row is None
                or not show.fresh_output_observed
                or not show.output_complete
            ):
                return FieldVerificationStatus.UNOBSERVABLE
            observed = getattr(row, attribute)
            if observed is None:
                return FieldVerificationStatus.UNOBSERVABLE
            return (
                FieldVerificationStatus.VERIFIED
                if expected_vlans.issubset(observed)
                else FieldVerificationStatus.FAILED
            )

        def traverses_expected_vlans(show: IosCommandResult) -> bool:
            row = find_row(show)
            return bool(
                row
                and row.status.casefold() == "trunking"
                and all(
                    vlan_status(show, row, attribute)
                    is FieldVerificationStatus.VERIFIED
                    for attribute in (
                        "allowed_vlans",
                        "active_vlans",
                        "forwarding_vlans",
                    )
                )
            )

        show, convergence, converged = self._converged_ios_query(
            expectation,
            OperationalQueryId.SHOW_INTERFACES_TRUNK,
            cache,
            traverses_expected_vlans,
            timeout_seconds=self._trunk_timeout,
        )
        row = (
            next(
                (
                    item
                    for item in parse_show_interfaces_trunk(show.output)
                    if self._same_interface(item.interface, expected_interface)
                ),
                None,
            )
            if show.executed
            else None
        )
        interface_status = (
            FieldVerificationStatus.VERIFIED if row else FieldVerificationStatus.FAILED
        )
        operational_status = (
            FieldVerificationStatus.VERIFIED
            if row and row.status.casefold() == "trunking"
            else FieldVerificationStatus.FAILED
        )
        fields = {
            "interface": interface_status,
            "status": operational_status,
            "allowed_vlans": vlan_status(show, row, "allowed_vlans"),
            "active_vlans": vlan_status(show, row, "active_vlans"),
            "forwarding_vlans": vlan_status(show, row, "forwarding_vlans"),
        }
        if FieldVerificationStatus.FAILED in fields.values():
            status = ActionExecutionStatus.FAILED
        elif converged and all(
            item is FieldVerificationStatus.VERIFIED for item in fields.values()
        ):
            status = ActionExecutionStatus.VERIFIED
        else:
            status = ActionExecutionStatus.UNOBSERVABLE

        message = show.failure_reason
        if not message and status is ActionExecutionStatus.FAILED and row is not None:
            omissions = []
            for field_name, attribute in (
                ("allowed", "allowed_vlans"),
                ("active", "active_vlans"),
                ("forwarding", "forwarding_vlans"),
            ):
                observed = getattr(row, attribute)
                if observed is None:
                    continue
                missing = sorted(expected_vlans - set(observed))
                if missing:
                    omissions.append(
                        f"{field_name} omitted " + ",".join(map(str, missing))
                    )
            message = "; ".join(omissions)
        if not message and status is ActionExecutionStatus.UNOBSERVABLE:
            message = (
                "The complete registered show interfaces trunk output did not "
                "expose every VLAN traversal section."
            )
        return RuntimeVerification(
            expectation_id=expectation.id,
            status=status,
            evidence_method="fresh_show_interfaces_trunk",
            fresh_evidence=show.fresh_output_observed,
            fields=fields,
            message=message or ("" if converged else "Trunk convergence timed out."),
            convergence=convergence,
        )

    def _verify_l3(
        self,
        expectation: VerificationExpectation,
        cache: dict,
    ) -> RuntimeVerification:
        expected_interface = str(expectation.expected["interface"])
        expected_ip = str(expectation.expected["ipv4"])
        expected_up = bool(expectation.expected.get("administrative_up", True))

        def find_row(show: IosCommandResult):
            return (
                next(
                    (
                        item
                        for item in parse_show_ip_interface_brief(show.output)
                        if self._same_interface(item.interface, expected_interface)
                    ),
                    None,
                )
                if show.executed
                else None
            )

        def administrative_state_matches(row) -> bool:
            if row is None:
                return False
            status = row.status.casefold()
            if expected_up:
                return status != "administratively down"
            return status == "administratively down"

        show, convergence, converged = self._converged_ios_query(
            expectation,
            OperationalQueryId.SHOW_IP_INTERFACE_BRIEF,
            cache,
            lambda value: bool(
                (row := find_row(value))
                and row.ip_address == expected_ip
                and administrative_state_matches(row)
            ),
            timeout_seconds=self._l3_timeout,
        )
        row = (
            next(
                (
                    item
                    for item in parse_show_ip_interface_brief(show.output)
                    if self._same_interface(item.interface, expected_interface)
                ),
                None,
            )
            if show.executed
            else None
        )
        address_verified = bool(
            converged
            and row
            and row.ip_address == expected_ip
            and show.fresh_output_observed
        )
        administrative_state_verified = administrative_state_matches(row)
        operational_up = bool(
            row and row.status.casefold() == "up" and row.protocol.casefold() == "up"
        )
        verified = address_verified and administrative_state_verified
        return RuntimeVerification(
            expectation_id=expectation.id,
            status=ActionExecutionStatus.VERIFIED
            if verified
            else ActionExecutionStatus.FAILED,
            evidence_method="fresh_show_ip_interface_brief",
            fresh_evidence=show.fresh_output_observed,
            fields={
                "interface": FieldVerificationStatus.VERIFIED
                if row
                else FieldVerificationStatus.FAILED,
                "ipv4": FieldVerificationStatus.VERIFIED
                if address_verified
                else FieldVerificationStatus.FAILED,
                "administrative_state": (
                    FieldVerificationStatus.VERIFIED
                    if administrative_state_verified
                    else FieldVerificationStatus.FAILED
                ),
                # Carrier/protocol are deliberately absent: this expectation
                # claims interface/IP/admin configuration, not reachability.
                # Serial up/up and end-to-end behavior have their own typed
                # operational gates; emitting supplemental UNKNOWN fields here
                # made an absent future LAN link look like unknown E5 state.
            },
            message=(
                show.failure_reason
                or (
                    ""
                    if operational_up
                    else "Configuration verified; operational link is not up/up."
                )
                if converged
                else "L3 configuration convergence timed out."
            ),
            convergence=convergence,
        )

    def _verify_access_port(
        self,
        expectation: VerificationExpectation,
    ) -> RuntimeVerification:
        """Lee el puerto como OBJETO, que es donde este backend lo expone.

        `show interfaces <if> switchport` trae los mismos campos y fue capturado
        en la misma cualificación, pero pagina incluso acotado a UNA interfaz:
        la captura cerró en `--More--` con `output_complete=False`. Esa consulta
        NO está en `_PAGINATION_QUALIFIED_QUERIES` y no se la agrega por
        conveniencia, así que no puede sostener una afirmación completa. La
        lectura de objeto no tiene pager y devuelve el registro entero o nada.

        Cada campo se decide por separado. Una observación parcial no verifica
        el todo: modo sin VLAN es una afirmación más angosta y se reporta así.

        La VLAN de voz sólo se lee cuando la expectativa la reclama, y con el
        getter MEDIDO sobre este build: `getVoipVlanId` responde `function` en
        los puertos físicos de un switch en PT 9.0.1.0858 y `undefined` en una
        SVI o en un puerto de AP. Que el getter exista no dice que su valor
        signifique lo que su nombre sugiere, así que el lector COMPARA contra lo
        esperado; un valor ilegible o ausente queda UNOBSERVABLE y nunca
        contradice.
        """
        expected_interface = str(expectation.expected["interface"])
        expected_vlan = int(expectation.expected["vlan_id"])
        expected_voice = expectation.expected.get("voice_vlan_id")
        device = json.dumps(expectation.device_name)
        port = json.dumps(expected_interface)
        js = "".join(
            (
                "try{var __d=ipc.network().getDevice(",
                device,
                ");",
                "if(!__d){reportResult(JSON.stringify({device_found:false,port_found:false}));}",
                "else{var __p=(typeof __d.getPort===",
                json.dumps("function"),
                ")?__d.getPort(",
                port,
                "):null;",
                "if(!__p){reportResult(JSON.stringify({device_found:true,port_found:false}));}",
                "else{var __r={device_found:true,port_found:true,complete:true};",
                "try{__r.owner_device_name=String(__p.getOwnerDevice().getName());}catch(__oe){__r.complete=false;}",
                "try{__r.interface=String(__p.getName());}catch(__ne){__r.complete=false;}",
                "try{__r.admin_op_mode=__p.getAdminOpMode();}catch(__me){__r.complete=false;}",
                "try{__r.access_vlan=__p.getAccessVlan();}catch(__ve){__r.complete=false;}",
                # El error del getter de voz se retiene aparte y NO baja `complete`:
                # un puerto sin ese getter no invalida lo que los otros cuatro sí
                # establecieron.
                (
                    "try{__r.voice_vlan=__p.getVoipVlanId();}"
                    "catch(__vve){__r.voice_vlan_error=String(__vve);}"
                    if expected_voice is not None
                    else ""
                ),
                "reportResult(JSON.stringify(__r));}}}",
                "catch(__e){reportResult(",
                json.dumps("ERROR:"),
                "+__e);}",
            )
        )
        observation = self._access_port_observation(js)
        if observation is None or observation.get("port_found") is not True:
            return self._unobservable(
                expectation,
                message=(
                    "The switch port object could not be observed."
                    if observation is not None
                    else "The access-port read-back returned no usable observation."
                ),
                extra_fields=("switchport_mode", "device_identity"),
            )

        # Completa significa dos cosas, y las dos hacen falta: que ningún getter
        # haya fallado, y que estén TODAS las claves del contrato. Un getter que
        # devuelve `undefined` no dispara el `catch`, así que no baja el flag --
        # pero `JSON.stringify` le borra la clave, y esa ausencia es la única
        # señal que queda.
        required_keys = [
            "owner_device_name",
            "interface",
            "admin_op_mode",
            "access_vlan",
        ]
        if expected_voice is not None:
            required_keys.append("voice_vlan")
        complete = observation.get("complete") is True and all(
            key in observation for key in required_keys
        )
        fields = {
            "device_identity": _field_status(
                observation.get("owner_device_name"),
                _as_text,
                lambda value: value == expectation.device_name,
            ),
            "interface": _field_status(
                observation.get("interface"),
                _as_text,
                lambda value: self._same_interface(value, expected_interface),
            ),
            "switchport_mode": self._switchport_mode_field(
                observation.get("admin_op_mode"),
            ),
            "vlan_id": _field_status(
                observation.get("access_vlan"),
                _as_vlan_id,
                lambda value: value == expected_vlan,
            ),
        }
        if expected_voice is not None:
            # Decidido sobre SU propia evidencia. Ningún campo se marca desde
            # otro: `vlan_id` VERIFIED con `voice_vlan_id` UNOBSERVABLE es un
            # resultado válido y más angosto, no una verificación a medias que
            # se pueda redondear hacia arriba.
            fields["voice_vlan_id"] = _field_status(
                observation.get("voice_vlan"),
                _as_vlan_id,
                lambda value: value == int(expected_voice),
            )
        statuses = set(fields.values())
        if FieldVerificationStatus.FAILED in statuses:
            status = ActionExecutionStatus.FAILED
        elif statuses == {FieldVerificationStatus.VERIFIED} and complete:
            status = ActionExecutionStatus.VERIFIED
        else:
            status = ActionExecutionStatus.PARTIAL
        return RuntimeVerification(
            expectation_id=expectation.id,
            status=status,
            evidence_method="switch_port_object_state",
            fresh_evidence=True,
            fields=fields,
            message=(
                ""
                if status is ActionExecutionStatus.VERIFIED
                else "The access-port observation did not establish every field."
                + (
                    # Una contradicción conserva el número observado, pero un
                    # payload ilegible sólo expone su tipo. El bridge no puede
                    # convertir un objeto arbitrario en un volcado sin límite.
                    _voice_vlan_evidence_message(observation, int(expected_voice))
                    if expected_voice is not None
                    else ""
                )
            ),
        )

    @staticmethod
    def _switchport_mode_field(value: object) -> FieldVerificationStatus:
        """Un código medido decide; uno que nadie midió no afirma nada."""
        if not isinstance(value, int) or isinstance(value, bool):
            return FieldVerificationStatus.UNOBSERVABLE
        if value == ADMIN_OP_MODE_ACCESS:
            return FieldVerificationStatus.VERIFIED
        if value in MEASURED_ADMIN_OP_MODES:
            return FieldVerificationStatus.FAILED
        return FieldVerificationStatus.UNOBSERVABLE

    def _access_port_observation(self, js: str) -> dict | None:
        raw = self._send_and_wait(js, 6.0)
        if raw is None or raw.startswith(("ERROR:", "PT_ERROR:")):
            return None
        try:
            value = json.loads(raw)
        except json.JSONDecodeError:
            return None
        return value if isinstance(value, dict) else None

    def _converged_ios_query(
        self,
        expectation: VerificationExpectation,
        query_id: OperationalQueryId,
        cache: dict[tuple[str, OperationalQueryId], IosCommandResult],
        predicate: Callable[[IosCommandResult], bool],
        *,
        timeout_seconds: float,
    ) -> tuple[IosCommandResult, ConvergenceReport, bool]:
        key = (expectation.device_name, query_id)
        cached = cache.get(key)
        if cached is not None and cached.fresh_output_observed and predicate(cached):
            return (
                cached,
                ConvergenceReport(
                    attempts=0,
                    elapsed_ms=0,
                    final_status=ActionExecutionStatus.VERIFIED,
                    last_observable_state="cached_current_query",
                ),
                True,
            )

        latest: dict[str, IosCommandResult] = {}

        def inspect() -> dict:
            show = self._ios.execute(expectation.device_name, query_id)
            latest["show"] = show
            matched = bool(show.fresh_output_observed and predicate(show))
            return {
                "found": show.executed,
                "configuration_channel": matched,
                "failure_reason": show.failure_reason,
            }

        observed = StateConvergenceWaiter(
            inspect,
            timeout_seconds=timeout_seconds,
            interval_seconds=self._convergence_interval,
            **self._wait_controls(),
        ).wait()
        show = latest["show"]
        converged = observed.state is DeviceInitializationState.CONFIGURATION_READY
        if show.fresh_output_observed:
            cache[key] = show
        convergence = ConvergenceReport(
            attempts=observed.attempts,
            elapsed_ms=observed.elapsed_ms,
            final_status=(
                ActionExecutionStatus.VERIFIED
                if converged
                else ActionExecutionStatus.FAILED
            ),
            last_observable_state=(
                "matched" if converged else show.failure_reason or "not_matched"
            ),
        )
        return show, convergence, converged

    def _verify_endpoint_dhcp_mode(
        self,
        expectation: VerificationExpectation,
    ) -> RuntimeVerification:
        """Read DHCP mode without waiting for an address acquisition."""
        interface = str(expectation.expected.get("interface") or "")
        if not interface:
            return self._unobservable(
                expectation,
                message="The DHCP-mode expectation names no interface.",
                evidence_method="structured_endpoint_dhcp_mode",
            )
        observed = self._endpoint_dhcp_modes.observe(
            expectation.device_name,
            interface,
        )
        exact_subject = (
            observed.runtime_device_name == expectation.device_name
            and observed.interface == interface
        )
        if not (
            exact_subject
            and observed.device_found
            and observed.port_found
            and observed.mode_channel
            and observed.fresh_evidence
            and isinstance(observed.dhcp_mode, bool)
        ):
            return self._unobservable(
                expectation,
                message=(
                    observed.failure_reason
                    or "The exact endpoint DHCP-mode getter was unavailable."
                ),
                evidence_method="structured_endpoint_dhcp_mode",
            )
        status = (
            ActionExecutionStatus.VERIFIED
            if observed.dhcp_mode
            else ActionExecutionStatus.FAILED
        )
        return RuntimeVerification(
            expectation_id=expectation.id,
            status=status,
            evidence_method="structured_endpoint_dhcp_mode",
            fresh_evidence=True,
            fields={
                "dhcp_mode": (
                    FieldVerificationStatus.VERIFIED
                    if observed.dhcp_mode
                    else FieldVerificationStatus.FAILED
                )
            },
            convergence=ConvergenceReport(
                attempts=1,
                elapsed_ms=0,
                final_status=status,
                last_observable_state=(
                    "dhcp_mode_enabled" if observed.dhcp_mode else "dhcp_mode_disabled"
                ),
                details={
                    "kind": "endpoint_dhcp_mode",
                    "device_name": expectation.device_name,
                    "interface": interface,
                    "last_observation": {
                        "device_found": observed.device_found,
                        "port_found": observed.port_found,
                        "mode_channel": observed.mode_channel,
                        "interface": observed.interface,
                        "dhcp_mode": observed.dhcp_mode,
                        "fresh_evidence": observed.fresh_evidence,
                        "failure_reason": observed.failure_reason,
                    },
                },
            ),
        )

    def _verify_endpoint(
        self, expectation: VerificationExpectation
    ) -> RuntimeVerification:
        """Read back the exact interface the action addressed.

        Walking the port list and taking the first one exposing `getIpAddress`
        only ever agreed with the plan by accident: on a single-port endpoint the
        addressed port IS the first port. On a 7960 (`Switch`, `PC`, logical
        `Vlan1`) or an AccessPoint-PT it is not, and the mismatch was reported as
        a contradiction -- an observation about a port nobody configured, which
        is a strictly stronger claim than the evidence supported.

        A named interface that cannot be found or cannot expose an address is
        UNOBSERVABLE, never FAILED: not having looked at the right thing is not
        the same as having looked and seen the opposite.
        """
        expected = expectation.expected
        interface = str(expected.get("interface") or "")
        if not interface:
            return self._unobservable(
                expectation,
                message="The expectation names no addressed interface to read.",
            )
        latest: dict[str, object] = {}
        transitions: list[dict[str, object]] = []
        signature: tuple[object, ...] | None = None
        sample_round = 0

        def inspect() -> dict:
            nonlocal sample_round, signature
            sample_round += 1
            read = self._endpoint_addresses.observe(
                expectation.device_name,
                interface,
            )
            observed = {
                "found": read.device_found,
                "port_found": read.port_found,
                "interface": read.interface,
                "address_channel": read.address_channel,
                "ipv4": read.ipv4,
                "netmask": read.netmask,
                # PT 9.0.1 evidence confirms only IP/mask getters. Gateway and
                # DNS remain deliberately unobservable.
                "gateway": None,
                "dns": None,
                "fresh_evidence": read.fresh_evidence,
                "failure_reason": read.failure_reason,
            }
            observed["configuration_channel"] = self._endpoint_matches(
                expected, observed
            )
            transition = {
                "device_found": observed["found"],
                "port_found": observed["port_found"],
                "address_channel": observed["address_channel"],
                "interface": observed["interface"],
                "ipv4": observed["ipv4"],
                "netmask": observed["netmask"],
                "fresh_evidence": observed["fresh_evidence"],
                "failure_reason": observed["failure_reason"],
            }
            current_signature = tuple(transition.values())
            if current_signature != signature:
                transitions.append(
                    {
                        "sample_round": sample_round,
                        **transition,
                    }
                )
                signature = current_signature
            latest.clear()
            latest.update(observed)
            return observed

        convergence = StateConvergenceWaiter(
            inspect,
            timeout_seconds=self._endpoint_timeout,
            interval_seconds=self._convergence_interval,
            **self._wait_controls(),
        ).wait()
        observed = dict(latest)
        if not observed.get("port_found"):
            return self._unobservable(
                expectation,
                message=(
                    f"{interface} was not exposed by {expectation.device_name}, so "
                    "its addressing was never read."
                ),
            )
        if not observed.get("address_channel"):
            # The port exists and carries traffic; it just has no address to
            # read. An AccessPoint-PT is the measured case on build 9.0.1.0858:
            # both its ports come up powered and neither exposes `getIpAddress`,
            # because it bridges rather than hosts. Treating the empty string
            # that comes back as a wrong address states more than was seen.
            return self._unobservable(
                expectation,
                # Distinct from a generic observability limit and from an
                # interface that was not found: this port is present, and the
                # device model has no address getter to ask. A governed ceiling
                # can admit that exact case without also admitting a missing
                # interface, which would hide a real topology error.
                evidence_method="structured_endpoint_getters_absent",
                message=(
                    f"{interface} on {expectation.device_name} exposes no address "
                    "channel, so nothing about its addressing was read."
                ),
            )
        ipv4_ok = self._ipv4_matches(expected, str(observed.get("ipv4") or ""))
        mask_ok = str(observed.get("netmask") or "") == str(
            expected.get("netmask") or ""
        )
        fields = {
            "ipv4": FieldVerificationStatus.VERIFIED
            if ipv4_ok
            else FieldVerificationStatus.FAILED,
            "netmask": FieldVerificationStatus.VERIFIED
            if mask_ok
            else FieldVerificationStatus.FAILED,
        }
        for field in ("gateway", "dns"):
            value = observed.get(field)
            wanted = expected.get(field)
            if value is None:
                fields[field] = FieldVerificationStatus.UNOBSERVABLE
            elif not wanted:
                fields[field] = FieldVerificationStatus.UNKNOWN
            else:
                fields[field] = (
                    FieldVerificationStatus.VERIFIED
                    if str(value) == str(wanted)
                    else FieldVerificationStatus.FAILED
                )
        converged = convergence.state is DeviceInitializationState.CONFIGURATION_READY
        core_verified = converged and ipv4_ok and mask_ok
        partial = any(
            value is FieldVerificationStatus.UNOBSERVABLE for value in fields.values()
        )
        status = (
            ActionExecutionStatus.PARTIAL
            if core_verified and partial
            else ActionExecutionStatus.VERIFIED
            if core_verified
            else ActionExecutionStatus.FAILED
        )
        return RuntimeVerification(
            expectation_id=expectation.id,
            status=status,
            evidence_method="structured_endpoint_getters",
            fresh_evidence=True,
            fields=fields,
            convergence=ConvergenceReport(
                attempts=convergence.attempts,
                elapsed_ms=convergence.elapsed_ms,
                final_status=status,
                last_observable_state=json.dumps(
                    {
                        key: observed.get(key)
                        for key in (
                            "found",
                            "port_found",
                            "address_channel",
                            "interface",
                            "ipv4",
                            "netmask",
                            "fresh_evidence",
                            "failure_reason",
                        )
                    },
                    sort_keys=True,
                    separators=(",", ":"),
                ),
                details={
                    "kind": "endpoint_addressing",
                    "device_name": expectation.device_name,
                    "interface": interface,
                    "sample_rounds": sample_round,
                    "transitions": transitions,
                    "last_observation": {
                        "device_found": observed.get("found"),
                        "port_found": observed.get("port_found"),
                        "address_channel": observed.get("address_channel"),
                        "interface": observed.get("interface"),
                        "ipv4": observed.get("ipv4"),
                        "netmask": observed.get("netmask"),
                        "fresh_evidence": observed.get("fresh_evidence"),
                        "failure_reason": observed.get("failure_reason"),
                    },
                },
            ),
        )

    @staticmethod
    def _endpoint_matches(expected: dict, observed: dict) -> bool:
        return PacketTracerEnterpriseConfigurationRuntime._ipv4_matches(
            expected,
            str(observed.get("ipv4") or ""),
        ) and str(observed.get("netmask") or "") == str(expected.get("netmask") or "")

    @staticmethod
    def _ipv4_matches(expected: dict, value: str) -> bool:
        try:
            address = ipaddress.ip_address(value)
        except ValueError:
            return False
        if expected.get("mode") == "static":
            return value == expected.get("ipv4")
        try:
            network = ipaddress.ip_network(
                f"{expected.get('network')}/{expected.get('prefix')}",
                strict=True,
            )
        except ValueError:
            return False
        return address in network and address not in {
            network.network_address,
            network.broadcast_address,
        }

    @staticmethod
    def _unobservable(
        expectation: VerificationExpectation,
        *,
        message: str = "",
        extra_fields: tuple[str, ...] = (),
        evidence_method: str = "runtime_observability_limit",
    ) -> RuntimeVerification:
        fields = {
            field: FieldVerificationStatus.UNOBSERVABLE
            for field in (*expectation.expected, *extra_fields)
        }
        return RuntimeVerification(
            expectation_id=expectation.id,
            status=ActionExecutionStatus.UNOBSERVABLE,
            evidence_method=evidence_method,
            fresh_evidence=False,
            fields=fields,
            message=message
            or (f"No independent getter is registered for {expectation.kind.value}."),
        )

    def _json_result(self, js: str, timeout: float) -> dict:
        raw = self._send_and_wait(js, timeout)
        if raw is None:
            return {
                "found": False,
                "configuration_channel": False,
                "failure_reason": "timeout",
            }
        if raw.startswith(("ERROR:", "PT_ERROR:")):
            return {
                "found": False,
                "configuration_channel": False,
                "failure_reason": raw,
            }
        try:
            value = json.loads(raw)
        except json.JSONDecodeError:
            return {
                "found": False,
                "configuration_channel": False,
                "failure_reason": "malformed_json",
            }
        return (
            value
            if isinstance(value, dict)
            else {
                "found": False,
                "configuration_channel": False,
                "failure_reason": "non_object_json",
            }
        )

    @staticmethod
    def _same_interface(observed: str, expected: str) -> bool:
        return same_interface_name(observed, expected)


def _trunk_port_reading(
    rows: Sequence[Any],
    interface: str,
    same: Callable[[str, str], bool],
) -> TrunkPortReading:
    """Keep what one trunk table says about one requested interface."""
    matching = [row for row in rows if same(row.interface, interface)]
    row = matching[0] if len(matching) == 1 else None
    return TrunkPortReading(
        interface=interface,
        matches=len(matching),
        status=str(row.status) if row is not None else "",
        allowed_vlans=(
            tuple(row.allowed_vlans)
            if row is not None and row.allowed_vlans is not None
            else None
        ),
        active_vlans=(
            tuple(row.active_vlans)
            if row is not None and row.active_vlans is not None
            else None
        ),
        forwarding_vlans=(
            tuple(row.forwarding_vlans)
            if row is not None and row.forwarding_vlans is not None
            else None
        ),
    )


def _field_status(value: object, read, matches) -> FieldVerificationStatus:
    """Ausente no es contradicho. ILEGIBLE tampoco. Legible y distinto sí.

    Los tres estados son distintos y colapsarlos en dos fue un defecto real:
    `getAccessVlan()` vuelve sin envolver, así que un retorno que
    `JSON.stringify` renderice como `"742"` o `{}` llegaba acá y salía FAILED
    -- diciéndole al operador que el puerto CONTRADICE lo esperado a partir de
    una observación que no estableció nada. `read` devuelve el valor
    normalizado o `None` si el tipo no es el que el getter promete.
    """
    if value is None:
        return FieldVerificationStatus.UNOBSERVABLE
    readable = read(value)
    if readable is None:
        return FieldVerificationStatus.UNOBSERVABLE
    return (
        FieldVerificationStatus.VERIFIED
        if matches(readable)
        else FieldVerificationStatus.FAILED
    )


def _voice_vlan_evidence_message(observation: dict, expected: int) -> str:
    """Describe evidencia de voz con forma tipada y acotada.

    Un número legible se conserva para diagnosticar una contradicción. Un error
    del getter o un valor estructurado sólo aporta su clase de evidencia; nunca
    se interpola el error ni el objeto entregado por Packet Tracer.
    """
    if "voice_vlan" not in observation:
        observed = (
            "getter unavailable" if "voice_vlan_error" in observation else "unavailable"
        )
    else:
        raw = observation["voice_vlan"]
        readable = _as_vlan_id(raw)
        observed = (
            f"observed {readable}"
            if readable is not None
            else f"unreadable {type(raw).__name__[:32]}"
        )
    return f" Voice VLAN evidence: {observed} (expected {expected})."


def _as_text(value: object) -> str | None:
    """Coerce only a non-empty string to observable text.

    Un número o un objeto no se puede leer como nombre.
    """
    return value if isinstance(value, str) and value else None


def _as_vlan_id(value: object) -> int | None:
    """Coerce only an integer-valued number to a VLAN id.

    Una cadena, un booleano o un objeto no son un id comparable.
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return None
