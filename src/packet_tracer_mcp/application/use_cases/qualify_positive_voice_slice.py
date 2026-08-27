"""Positive disposable Voice slice: the A side of the Configuring-IP A/B.

CP-SCALE Floor 1 leaves DHCP enabled on 21/21 phones and addressed on 0/21.
Nothing in that failure says whether Voice works AT ALL on this build, so the
failure cannot yet be called scale-specific.  This qualification builds the
smallest Voice slice that could succeed -- one router, one PoE switch, two
phones -- and reads the same surfaces the canonical run reads.

What it deliberately does NOT do:

* It applies no edge STP policy.  PortFast is emitted by the control-plane
  stage, not by the configuration or voice paths, so a slice built from those
  paths carries none.  Adding one to make the slice succeed would answer a
  question nobody asked; a slice that registers WITHOUT PortFast is exactly the
  evidence that weakens PortFast as the explanation.
* It promotes nothing.  Voice VLAN read back, DHCP enabled, an address, a
  binding and a registration are five independent facts, and each is observed
  on its own surface.  COMPILED != APPLIED != ADDRESSED != REGISTERED.
* It creates no mutation primitive.  Every mutation goes through a typed
  production runtime; this module only orders them and journals when each one
  happened.

The lifecycle journal exists because lifecycle is still a live hypothesis:
historical E7 never retained its ordering, so "it worked once" cannot be
compared against anything.  Here the order is recorded as it happens, and a
milestone nobody could observe is written UNOBSERVABLE rather than assumed.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass, field
from typing import Protocol

from ...domain.enterprise.models.physical_deployment import (
    PhysicalWorkspaceObservation,
    physical_workspace_restoration_matches,
)
from ...domain.models.plans import DevicePlan, LinkPlan

#: Reserved prefix, same intent as the other disposables: every object this
#: qualification creates is recognisable as its own and nothing else is touched.
POSITIVE_VOICE_PREFIX = "__MCP_VOICEAB_"

#: The documented historical E7 shape.  930 is a non-default VLAN, so a row that
#: appears for it was created by this slice and not inherited from VLAN 1.
VOICE_VLAN_ID = 930
DATA_VLAN_ID = 931
EXTENSIONS = ("3101", "3102")

VOICE_NETWORK = "10.93.0.0"
VOICE_PREFIX = 24
VOICE_NETMASK = "255.255.255.0"
VOICE_GATEWAY = "10.93.0.1"
DATA_NETWORK = "10.94.0.0"
DATA_GATEWAY = "10.94.0.1"

#: Statuses.  Absence is never spelled as a negative result.
VERIFIED = "VERIFIED"
CONTRADICTED = "CONTRADICTED"
UNOBSERVABLE = "UNOBSERVABLE"
YES = "YES"
NO = "NO"
REGISTERED = "REGISTERED"
NOT_REGISTERED = "NOT_REGISTERED"

#: STP phone-row classification.  ABSENT is its own answer: CP-SCALE's VLAN20
#: phone rows were absent, and an absent row is not a blocked one.
FORWARDING = "FORWARDING"
BLOCKING = "BLOCKING"
ABSENT = "ABSENT"

#: Outcomes of the whole positive control.
SUCCESS = "SUCCESS"
SAME_FAILURE = "SAME_FAILURE"
DIFFERENT_FAILURE = "DIFFERENT_FAILURE"


@dataclass(frozen=True)
class LifecycleMilestone:
    """One ordered fact about WHEN something existed.

    `observed` is what separates this journal from a plan: a milestone the
    backend never published stays `observed=False` and reads UNOBSERVABLE, which
    is the honest answer for phone boot state on this build.
    """

    sequence: int
    name: str
    observed: bool = False
    detail: str = ""

    @property
    def status(self) -> str:
        return VERIFIED if self.observed else UNOBSERVABLE


@dataclass(frozen=True)
class PositiveVoicePhoneOutcome:
    """The five success dimensions for one phone, each read independently."""

    phone_name: str = ""
    extension: str = ""
    switch_interface: str = ""
    data_vlan_readback: str = UNOBSERVABLE
    voice_vlan_readback: str = UNOBSERVABLE
    dhcp_enabled: str = UNOBSERVABLE
    ipv4: str = ""
    registration: str = UNOBSERVABLE
    stp_row_before: str = UNOBSERVABLE
    stp_row_after: str = UNOBSERVABLE
    failure_reason: str = ""

    @property
    def ipv4_observed(self) -> bool:
        """An address only counts when it is a real lease, not a placeholder."""
        value = self.ipv4.strip()
        if not value or value in {"0.0.0.0", "<not set>", "unassigned"}:
            return False
        return not value.startswith("169.254.")

    @property
    def addressed(self) -> str:
        if not self.ipv4.strip():
            return UNOBSERVABLE
        return YES if self.ipv4_observed else NO

    @property
    def succeeded(self) -> bool:
        return (
            self.voice_vlan_readback == VERIFIED
            and self.dhcp_enabled == YES
            and self.ipv4_observed
            and self.registration == REGISTERED
        )

    @property
    def matches_cp_scale_signature(self) -> bool:
        """DHCP enabled, no address, not registered -- the Floor-1 shape.

        Registration is allowed to be UNOBSERVABLE here: CP-SCALE never got far
        enough to read a registration either, and demanding a definite
        NOT_REGISTERED would make the signature unmatchable for the wrong
        reason.
        """
        return (
            self.dhcp_enabled == YES
            and self.addressed == NO
            and self.registration in {NOT_REGISTERED, UNOBSERVABLE}
        )


@dataclass(frozen=True)
class PositiveVoiceSliceResult:
    """Everything the positive control observed, with nothing collapsed."""

    router_model: str = ""
    switch_model: str = ""
    phone_model: str = ""
    router_name: str = ""
    switch_name: str = ""
    voice_vlan_id: int = VOICE_VLAN_ID
    phones: tuple[PositiveVoicePhoneOutcome, ...] = ()
    lifecycle: tuple[LifecycleMilestone, ...] = ()
    #: `show ip dhcp binding` rows whose address falls in the voice pool.  None
    #: means the table was never read, which is not the same as zero rows.
    voice_binding_count: int | None = None
    #: No edge STP action is part of this plan.  The value is a recorded fact,
    #: never a knob this qualification turns to obtain a better outcome.
    portfast: str = "NOT_APPLIED"
    realtime_before: bool = False
    realtime_after: bool = False
    baseline_inventory: PhysicalWorkspaceObservation | None = None
    final_inventory: PhysicalWorkspaceObservation | None = None
    workspace_restored: bool = False
    realtime_restored: bool = False
    owned_links: tuple[str, ...] = ()
    removed: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()

    @property
    def voice_bindings_observed(self) -> str:
        if self.voice_binding_count is None:
            return UNOBSERVABLE
        return YES if self.voice_binding_count > 0 else NO

    @property
    def outcome(self) -> str:
        """The decision matrix, computed from independent facts only.

        SUCCESS demands every dimension on every phone AND a voice binding on
        the server.  A phone that reports an address while the server shows no
        binding is not a success; it is a disagreement worth seeing.
        """
        if not self.phones:
            return UNOBSERVABLE
        if not self.realtime_before or not self.realtime_after:
            # Addressing judged outside Realtime is not judged at all.
            return UNOBSERVABLE
        # The server-side binding table is a dimension like any other: unread
        # is UNOBSERVABLE, and only a table that was actually read can confirm
        # or contradict what the phones reported.
        if all(item.succeeded for item in self.phones):
            if self.voice_binding_count is None:
                return UNOBSERVABLE
            return SUCCESS if self.voice_binding_count > 0 else DIFFERENT_FAILURE
        if all(item.matches_cp_scale_signature for item in self.phones):
            if self.voice_binding_count is None:
                return UNOBSERVABLE
            return SAME_FAILURE if self.voice_binding_count == 0 else DIFFERENT_FAILURE
        # UNKNOWN fails closed in BOTH directions.  A phone whose decisive
        # dimensions were never read has not succeeded, but it has not been
        # shown to fail either, and calling it DIFFERENT_FAILURE would invent a
        # divergence out of a missing observation.
        if any(
            item.dhcp_enabled == UNOBSERVABLE
            or item.addressed == UNOBSERVABLE
            or item.registration == UNOBSERVABLE
            for item in self.phones
        ):
            return UNOBSERVABLE
        return DIFFERENT_FAILURE

    @property
    def stp_phone_row_after(self) -> str:
        """One classification for the phone-facing rows under the voice VLAN."""
        rows = {item.stp_row_after for item in self.phones}
        if not rows:
            return UNOBSERVABLE
        if len(rows) == 1:
            return rows.pop()
        # Disagreeing rows are not averaged into a verdict.
        return "MIXED"


class VoicePhysicalRuntime(Protocol):
    def observe_workspace(self) -> PhysicalWorkspaceObservation: ...
    def ensure_device(self, device: DevicePlan): ...
    def observe_device(self, device: DevicePlan): ...
    def remove_device(self, device: DevicePlan): ...
    def ensure_link(self, link: LinkPlan): ...


class VoiceConfigurationRuntime(Protocol):
    def apply_actions(self, actions) -> list: ...
    def read_access_port(self, device_name: str, interface: str): ...
    def read_spanning_tree(self, device_name: str): ...
    def read_dhcp_bindings(self, device_name: str): ...


class VoiceCallControlRuntime(Protocol):
    def apply_actions(self, actions) -> list: ...
    def observe_registrations(self, expectations) -> list: ...


class VoiceEndpointRuntime(Protocol):
    def configure_endpoint_dhcp(self, device_name: str, interface: str): ...
    def read_endpoint_address(self, device_name: str, interface: str): ...


class VoiceModeRuntime(Protocol):
    def read_simulation_state(self): ...
    def set_simulation_mode(self, on: bool): ...


@dataclass
class _Journal:
    """Monotonic lifecycle recorder.  Order is the evidence."""

    entries: list[LifecycleMilestone] = field(default_factory=list)

    def record(self, name: str, observed: bool = False, detail: str = "") -> None:
        self.entries.append(
            LifecycleMilestone(
                sequence=len(self.entries) + 1,
                name=name,
                observed=observed,
                detail=detail,
            )
        )

    def frozen(self) -> tuple[LifecycleMilestone, ...]:
        return tuple(self.entries)


def _classify_stp_row(instances, vlan_id: int, interface: str) -> str:
    """FORWARDING / BLOCKING / ABSENT / UNOBSERVABLE for one phone port.

    An instance that was never read is UNOBSERVABLE.  An instance that was read
    and simply has no row for this port is ABSENT.  Those are different facts,
    and collapsing them is exactly how CP-SCALE's missing VLAN20 rows would turn
    into an STP block that nobody measured.
    """
    if instances is None:
        return UNOBSERVABLE
    for instance in instances:
        if getattr(instance, "vlan_id", None) != vlan_id:
            continue
        for row in getattr(instance, "interfaces", ()):
            if getattr(row, "interface", "") != interface:
                continue
            state = str(getattr(row, "state", "")).upper()
            if state.startswith("FWD") or state.startswith("FORW"):
                return FORWARDING
            if state.startswith("BLK") or state.startswith("BLOCK"):
                return BLOCKING
            return state or UNOBSERVABLE
        return ABSENT
    return ABSENT


class PositiveVoiceSliceQualifier:
    """Builds the disposable slice, reads the five dimensions, and cleans up."""

    def __init__(
        self,
        physical: VoicePhysicalRuntime,
        configuration: VoiceConfigurationRuntime,
        call_control: VoiceCallControlRuntime,
        endpoints: VoiceEndpointRuntime,
        mode: VoiceModeRuntime,
        *,
        token: str = "",
        phone_count: int = 2,
    ) -> None:
        self._physical = physical
        self._configuration = configuration
        self._call_control = call_control
        self._endpoints = endpoints
        self._mode = mode
        self._token = token or secrets.token_hex(3)
        self._phone_count = phone_count

    def _name(self, suffix: str) -> str:
        return f"{POSITIVE_VOICE_PREFIX}{self._token}_{suffix}"

    def qualify(
        self,
        router_model: str,
        switch_model: str,
        phone_model: str,
        *,
        require_empty_workspace: bool = True,
    ) -> PositiveVoiceSliceResult:
        errors: list[str] = []
        try:
            baseline = self._physical.observe_workspace()
        except Exception as exc:  # noqa: BLE001
            return PositiveVoiceSliceResult(
                router_model=router_model, switch_model=switch_model,
                phone_model=phone_model,
                errors=(f"Read-only workspace inventory failed: {exc}",),
            )
        if require_empty_workspace and not baseline.safe_for_disposable_mutation:
            return PositiveVoiceSliceResult(
                router_model=router_model, switch_model=switch_model,
                phone_model=phone_model, baseline_inventory=baseline,
                errors=(
                    "The workspace inventory is not a complete empty baseline "
                    f"(observed={baseline.observed}, "
                    f"semantic_devices={len(baseline.semantic_devices)}, "
                    f"links={len(baseline.links)}); the positive Voice slice "
                    "refuses to mutate a workspace it did not find empty.",
                ),
            )

        journal = _Journal()
        created: list[DevicePlan] = []
        owned_links: list[str] = []
        phones: tuple[PositiveVoicePhoneOutcome, ...] = ()
        binding_count: int | None = None
        realtime_before = realtime_after = False
        original_simulation: bool | None = None
        try:
            (
                original_simulation, phones, binding_count,
                realtime_before, realtime_after, measured_errors,
            ) = self._measure(
                router_model, switch_model, phone_model,
                created, owned_links, journal,
            )
            errors.extend(measured_errors)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"positive_voice_raised: {type(exc).__name__}: {exc}")
        finally:
            realtime_restored, restore_errors = self._restore_mode(original_simulation)
            errors.extend(restore_errors)
            removed, cleanup_errors, final, restored = self._cleanup(created, baseline)
            errors.extend(cleanup_errors)

        return PositiveVoiceSliceResult(
            router_model=router_model, switch_model=switch_model,
            phone_model=phone_model,
            router_name=self._name("R"), switch_name=self._name("SW"),
            phones=phones, lifecycle=journal.frozen(),
            voice_binding_count=binding_count,
            realtime_before=realtime_before, realtime_after=realtime_after,
            baseline_inventory=baseline, final_inventory=final,
            workspace_restored=restored, realtime_restored=realtime_restored,
            owned_links=tuple(owned_links), removed=tuple(removed),
            errors=tuple(errors),
        )

    def _restore_mode(self, original: bool | None) -> tuple[bool, list[str]]:
        """Realtime is the authoritative window; leaving Simulation on is a leak."""
        if original is None:
            return True, []
        try:
            self._mode.set_simulation_mode(bool(original))
        except Exception as exc:  # noqa: BLE001
            return False, [f"mode_restore_failed: {exc}"]
        return True, []

    def _cleanup(self, created, baseline):
        removed: list[str] = []
        errors: list[str] = []
        for device in reversed(created):
            try:
                self._physical.remove_device(device)
                removed.append(device.name)
            except Exception as exc:  # noqa: BLE001
                errors.append(f"cleanup_failed:{device.name}: {exc}")
        final = None
        restored = False
        try:
            final = self._physical.observe_workspace()
            restored = physical_workspace_restoration_matches(baseline, final)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"final_inventory_failed: {exc}")
        return removed, errors, final, restored

    # ------------------------------------------------------------------
    # Plan construction.  Every action is a typed production action; this
    # module adds no primitive of its own.
    # ------------------------------------------------------------------

    def _switch_interface(self, position: int) -> str:
        return f"FastEthernet0/{position}"

    def _configuration_actions(self, phone_ports: tuple[str, ...]) -> list:
        from ...domain.enterprise.models.configuration import (
            AddressRange,
            ConfigureAccessPort,
            ConfigureDhcpPool,
            ConfigureSubinterface,
            ConfigureTrunk,
            ConfigurationPhase,
            CreateVlan,
        )

        switch = self._name("SW")
        router = self._name("R")
        site = "voiceab"
        actions: list = [
            CreateVlan(
                id="voiceab/vlan/data", phase=ConfigurationPhase.L2_DEFINITIONS,
                device_id="voiceab/sw", device_name=switch, site_id=site,
                vlan_id=DATA_VLAN_ID, name="VOICEAB_DATA",
            ),
            CreateVlan(
                id="voiceab/vlan/voice", phase=ConfigurationPhase.L2_DEFINITIONS,
                device_id="voiceab/sw", device_name=switch, site_id=site,
                vlan_id=VOICE_VLAN_ID, name="VOICEAB_VOICE",
            ),
            ConfigureTrunk(
                id="voiceab/trunk/uplink", phase=ConfigurationPhase.L2_INTERFACES,
                device_id="voiceab/sw", device_name=switch, site_id=site,
                interface="GigabitEthernet0/1",
                allowed_vlans=[DATA_VLAN_ID, VOICE_VLAN_ID],
                native_vlan_id=1,
            ),
        ]
        for index, interface in enumerate(phone_ports, start=1):
            actions.append(
                ConfigureAccessPort(
                    id=f"voiceab/access/{index}",
                    phase=ConfigurationPhase.L2_INTERFACES,
                    device_id="voiceab/sw", device_name=switch, site_id=site,
                    interface=interface,
                    data_vlan_id=DATA_VLAN_ID,
                    voice_vlan_id=VOICE_VLAN_ID,
                )
            )
        actions.extend([
            ConfigureSubinterface(
                id="voiceab/sub/data", phase=ConfigurationPhase.L3_INTERFACES,
                device_id="voiceab/r", device_name=router, site_id=site,
                parent_interface="FastEthernet0/0", vlan_id=DATA_VLAN_ID,
                ipv4=DATA_GATEWAY, prefix=VOICE_PREFIX, netmask=VOICE_NETMASK,
                segment_id="voiceab/seg/data",
            ),
            ConfigureSubinterface(
                id="voiceab/sub/voice", phase=ConfigurationPhase.L3_INTERFACES,
                device_id="voiceab/r", device_name=router, site_id=site,
                parent_interface="FastEthernet0/0", vlan_id=VOICE_VLAN_ID,
                ipv4=VOICE_GATEWAY, prefix=VOICE_PREFIX, netmask=VOICE_NETMASK,
                segment_id="voiceab/seg/voice",
            ),
            ConfigureDhcpPool(
                id="voiceab/pool/voice", phase=ConfigurationPhase.SERVICES,
                device_id="voiceab/r", device_name=router, site_id=site,
                pool_name="VOICEAB_VOICE", segment_id="voiceab/seg/voice",
                network=VOICE_NETWORK, prefix=VOICE_PREFIX,
                netmask=VOICE_NETMASK, gateway=VOICE_GATEWAY,
                excluded_ranges=[AddressRange(start=VOICE_GATEWAY, end="10.93.0.9")],
                lease_start="10.93.0.10", lease_end="10.93.0.254",
            ),
        ])
        return actions

    def _voice_actions(self) -> list:
        from ...domain.enterprise.models.voice_plan import (
            ConfigureCallControlSource,
            BindPhoneToExtension,
            ConfigureVoiceDhcpOption,
            CreateExtension,
            EnableCallControl,
            GeneratePhoneConfigurationFiles,
            VoiceCapabilityDimension,
            VoicePhase,
        )

        router = self._name("R")
        common = {
            "call_control_id": "voiceab/cme",
            "host_device_id": "voiceab/r",
            "host_device_name": router,
            "host_model": self._router_model,
            "site_id": "voiceab",
        }
        actions: list = [
            # Option 150 is a DHCP-pool attribute, so it is named against the
            # pool the configuration stage already created.
            ConfigureVoiceDhcpOption(
                id="voiceab/option150", phase=VoicePhase.CALL_CONTROL,
                required_capability=VoiceCapabilityDimension.VOICE_DHCP_OPTIONS,
                pool_name="VOICEAB_VOICE", tftp_address=VOICE_GATEWAY,
                source_configuration_action_id="voiceab/sub/voice", **common,
            ),
            ConfigureCallControlSource(
                id="voiceab/cme/source", phase=VoicePhase.CALL_CONTROL,
                required_capability=VoiceCapabilityDimension.CALL_CONTROL_CONFIG,
                source_address=VOICE_GATEWAY, signaling_port=2000,
                source_configuration_action_id="voiceab/sub/voice", **common,
            ),
            EnableCallControl(
                id="voiceab/cme/enable", phase=VoicePhase.CALL_CONTROL,
                required_capability=VoiceCapabilityDimension.CALL_CONTROL_CONFIG,
                max_phones=self._phone_count, max_extensions=self._phone_count,
                **common,
            ),
        ]
        for index, extension in enumerate(EXTENSIONS[: self._phone_count], start=1):
            actions.append(
                CreateExtension(
                    id=f"voiceab/cme/ext/{extension}", phase=VoicePhase.EXTENSIONS,
                    required_capability=(
                        VoiceCapabilityDimension.PHONE_EXTENSION_CONFIG
                    ),
                    extension=extension, directory_index=index, **common,
                )
            )
        for index, extension in enumerate(EXTENSIONS[: self._phone_count], start=1):
            actions.append(
                BindPhoneToExtension(
                    id=f"voiceab/cme/bind/{extension}",
                    phase=VoicePhase.PHONE_BINDINGS,
                    required_capability=(
                        VoiceCapabilityDimension.PHONE_EXTENSION_CONFIG
                    ),
                    phone_id=f"voiceab/p{index}",
                    physical_device_name=self._name(f"P{index}"),
                    phone_model=self._phone_model, extension=extension,
                    directory_index=index, **common,
                )
            )
        actions.append(
            GeneratePhoneConfigurationFiles(
                id="voiceab/cme/cnf", phase=VoicePhase.PHONE_BOOTSTRAP,
                required_capability=VoiceCapabilityDimension.TFTP_PHONE_BOOTSTRAP,
                **common,
            )
        )
        return actions

    # ------------------------------------------------------------------
    # The measured pass.  Order here IS the lifecycle record.
    # ------------------------------------------------------------------

    def _measure(
        self, router_model: str, switch_model: str, phone_model: str,
        created, owned_links, journal: _Journal,
    ):
        self._router_model = router_model
        self._phone_model = phone_model
        errors: list[str] = []

        router = DevicePlan(
            id="voiceab/r", name=self._name("R"), model=router_model,
            category="", x=9000, y=9000,
        )
        switch = DevicePlan(
            id="voiceab/sw", name=self._name("SW"), model=switch_model,
            category="", x=9000, y=9400,
        )
        phones = [
            DevicePlan(
                id=f"voiceab/p{index}", name=self._name(f"P{index}"),
                model=phone_model, category="", x=8800 + 300 * index, y=9800,
            )
            for index in range(1, self._phone_count + 1)
        ]

        original_simulation = self._read_mode(errors)
        empty: tuple[PositiveVoicePhoneOutcome, ...] = ()

        for device in (router, switch):
            if not self._create(device, created, errors):
                return original_simulation, empty, None, False, False, errors
        journal.record("DEVICE_CREATE_ORDER", True, "router, switch, then phones")
        for device in phones:
            if not self._create(device, created, errors):
                return original_simulation, empty, None, False, False, errors
        journal.record("WHEN_PHONE_EXISTS", True, ", ".join(p.name for p in phones))
        # PT publishes no phone power or boot state on this build.  Writing a
        # guess here is what the UNOBSERVABLE status exists to prevent.
        journal.record("WHEN_PHONE_IS_POWERED", False, "no measured boot surface")

        uplink = LinkPlan(
            device_a=router.name, port_a="FastEthernet0/0",
            device_b=switch.name, port_b="GigabitEthernet0/1", cable="straight",
        )
        phone_ports = tuple(
            self._switch_interface(index) for index in range(1, len(phones) + 1)
        )
        links = [uplink] + [
            LinkPlan(
                device_a=switch.name, port_a=port,
                device_b=phone.name, port_b="Switch", cable="straight",
            )
            for port, phone in zip(phone_ports, phones)
        ]
        for link in links:
            if not self._link(link, owned_links, errors):
                return original_simulation, empty, None, False, False, errors
        journal.record("LINK_CREATE_ORDER", True, "uplink first, then phone links")
        journal.record("WHEN_PHONE_IS_LINKED", True, ", ".join(phone_ports))

        applied, config_errors = self._apply(
            self._configuration.apply_actions,
            self._configuration_actions(phone_ports),
        )
        errors.extend(config_errors)
        journal.record("WHEN_ACCESS_VLAN_APPLIED", applied, f"data vlan {DATA_VLAN_ID}")
        journal.record("WHEN_VOICE_VLAN_APPLIED", applied, f"voice vlan {VOICE_VLAN_ID}")
        journal.record("WHEN_DHCP_POOL_EXISTS", applied, "VOICEAB_VOICE")
        journal.record("CONFIGURATION_APPLY_ORDER", applied, "L2, L3, then services")

        voice_applied, voice_errors = self._apply(
            self._call_control.apply_actions, self._voice_actions(),
        )
        errors.extend(voice_errors)
        journal.record("WHEN_OPTION150_APPLIED", voice_applied, VOICE_GATEWAY)
        journal.record("WHEN_CME_ENABLED", voice_applied, "telephony-service")
        journal.record("WHEN_PHONE_BINDING_EXISTS", voice_applied, ", ".join(EXTENSIONS))
        journal.record("WHEN_CNF_FILES_GENERATED", voice_applied, "create cnf-files")

        for phone in phones:
            try:
                self._endpoints.configure_endpoint_dhcp(phone.name, "Switch")
            except Exception as exc:  # noqa: BLE001
                errors.append(f"endpoint_dhcp_failed:{phone.name}: {exc}")
        journal.record("WHEN_ENDPOINT_DHCP_ARMED", True, "phones set to DHCP")

        # Realtime is the authoritative window for addressing and registration.
        realtime_before = self._realtime(errors, "before")
        stp_before = self._read_stp(switch.name, errors)
        journal.record("REALTIME_VERIFIED_BEFORE_WINDOW", realtime_before)

        registrations = self._observe_registrations(phones, errors)
        journal.record("ACQUISITION_WINDOW_RUN", True, "registration convergence")

        stp_after = self._read_stp(switch.name, errors)
        binding_count = self._read_bindings(router.name, errors)
        realtime_after = self._realtime(errors, "after")
        journal.record("REALTIME_VERIFIED_AFTER_WINDOW", realtime_after)

        outcomes = tuple(
            self._phone_outcome(
                phone, phone_ports[index],
                EXTENSIONS[index] if index < len(EXTENSIONS) else "",
                switch.name, registrations.get(phone.name),
                stp_before, stp_after, errors,
            )
            for index, phone in enumerate(phones)
        )
        return (
            original_simulation, outcomes, binding_count,
            realtime_before, realtime_after, errors,
        )

    def _read_mode(self, errors: list[str]) -> bool | None:
        try:
            state = self._mode.read_simulation_state()
        except Exception as exc:  # noqa: BLE001
            errors.append(f"simulation_state_unreadable: {exc}")
            return None
        return bool(getattr(state, "simulation_mode", False))

    def _realtime(self, errors: list[str], label: str) -> bool:
        """A pure read.  Realtime is verified, never inferred from not switching."""
        try:
            state = self._mode.read_simulation_state()
        except Exception as exc:  # noqa: BLE001
            errors.append(f"realtime_unreadable_{label}: {exc}")
            return False
        if not bool(getattr(state, "observed", True)):
            errors.append(f"realtime_unobserved_{label}")
            return False
        return not bool(getattr(state, "simulation_mode", False))

    def _create(self, device: DevicePlan, created, errors) -> bool:
        try:
            outcome = self._physical.ensure_device(device)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"device_create_raised:{device.name}: {exc}")
            return False
        # Ownership is recorded BEFORE the result is judged: a device that was
        # half-created still has to be cleaned up.
        created.append(device)
        if not bool(getattr(outcome, "success", True)):
            message = getattr(outcome, "message", "")
            errors.append(f"device_not_created:{device.name}: {message}")
            return False
        return True

    def _link(self, link: LinkPlan, owned_links, errors) -> bool:
        try:
            outcome = self._physical.ensure_link(link)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"link_raised:{link.device_a}->{link.device_b}: {exc}")
            return False
        owned_links.append(
            f"{link.device_a}:{link.port_a}->{link.device_b}:{link.port_b}"
        )
        if not bool(getattr(outcome, "success", True)):
            message = getattr(outcome, "message", "")
            errors.append(f"link_failed:{link.device_a}->{link.device_b}: {message}")
            return False
        return True

    def _apply(self, runner, actions) -> tuple[bool, list[str]]:
        try:
            results = runner(actions)
        except Exception as exc:  # noqa: BLE001
            return False, [f"apply_raised: {type(exc).__name__}: {exc}"]
        errors = []
        for item in results or ():
            if bool(getattr(item, "success", True)):
                continue
            action_id = getattr(item, "action_id", "")
            message = getattr(item, "message", "")
            errors.append(f"action_failed:{action_id}: {message}")
        return not errors, errors

    def _read_stp(self, switch_name: str, errors: list[str]):
        """None means the table was never read; it never means no rows."""
        try:
            return self._configuration.read_spanning_tree(switch_name)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"stp_unreadable: {exc}")
            return None

    def _read_bindings(self, router_name: str, errors: list[str]) -> int | None:
        try:
            rows = self._configuration.read_dhcp_bindings(router_name)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"dhcp_bindings_unreadable: {exc}")
            return None
        if rows is None:
            return None
        prefix = VOICE_NETWORK.rsplit(".", 1)[0] + "."
        return sum(
            1 for row in rows
            if str(getattr(row, "ip_address", "") or "").startswith(prefix)
        )

    def _observe_registrations(self, phones, errors: list[str]) -> dict:
        expectations = [
            _RegistrationExpectation(
                id=f"voiceab/reg/{index}",
                phone_id=f"voiceab/p{index}",
                phone_name=phone.name,
                extension=EXTENSIONS[index - 1] if index - 1 < len(EXTENSIONS) else "",
                endpoint_interface="Switch",
            )
            for index, phone in enumerate(phones, start=1)
        ]
        try:
            observed = self._call_control.observe_registrations(expectations)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"registration_unobservable: {exc}")
            return {}
        by_name: dict = {}
        for expectation, item in zip(expectations, observed or ()):
            by_name[expectation.phone_name] = item
        return by_name

    def _phone_outcome(
        self, phone: DevicePlan, interface: str, extension: str,
        switch_name: str, registration, stp_before, stp_after,
        errors: list[str],
    ) -> PositiveVoicePhoneOutcome:
        data_status = voice_status = UNOBSERVABLE
        try:
            port = self._configuration.read_access_port(switch_name, interface)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"access_port_unreadable:{interface}: {exc}")
            port = None
        if port is not None:
            data_status = _compare_vlan(getattr(port, "data_vlan_id", None), DATA_VLAN_ID)
            voice_status = _compare_vlan(
                getattr(port, "voice_vlan_id", None), VOICE_VLAN_ID,
            )

        ipv4 = ""
        dhcp_enabled = UNOBSERVABLE
        registered = UNOBSERVABLE
        if registration is not None:
            ipv4 = str(getattr(registration, "endpoint_ipv4", "") or "")
            flag = getattr(registration, "endpoint_dhcp_enabled", None)
            if flag is not None:
                dhcp_enabled = YES if bool(flag) else NO
            status = str(getattr(registration, "status", "") or "")
            direct = str(getattr(registration, "direct_readback", "") or "")
            if "VERIFIED" in status.upper() and "VERIFIED" in direct.upper():
                registered = REGISTERED
            elif status:
                registered = NOT_REGISTERED
        if not ipv4:
            # The registration surface carries the endpoint address, but a
            # separate endpoint read is what makes an absent one distinguishable
            # from an unread one.
            try:
                observation = self._endpoints.read_endpoint_address(
                    phone.name, "Switch",
                )
            except Exception as exc:  # noqa: BLE001
                errors.append(f"endpoint_address_unreadable:{phone.name}: {exc}")
                observation = None
            if observation is not None:
                ipv4 = str(getattr(observation, "ipv4", "") or "")
                if dhcp_enabled == UNOBSERVABLE:
                    flag = getattr(observation, "dhcp_enabled", None)
                    if flag is not None:
                        dhcp_enabled = YES if bool(flag) else NO

        return PositiveVoicePhoneOutcome(
            phone_name=phone.name, extension=extension,
            switch_interface=interface,
            data_vlan_readback=data_status, voice_vlan_readback=voice_status,
            dhcp_enabled=dhcp_enabled, ipv4=ipv4, registration=registered,
            stp_row_before=_classify_stp_row(stp_before, VOICE_VLAN_ID, interface),
            stp_row_after=_classify_stp_row(stp_after, VOICE_VLAN_ID, interface),
        )


@dataclass(frozen=True)
class _RegistrationExpectation:
    """The minimum a registration observer needs, named as this slice uses it."""

    id: str
    phone_id: str
    phone_name: str
    extension: str
    endpoint_interface: str


def _compare_vlan(observed, expected: int) -> str:
    """VERIFIED / CONTRADICTED / UNOBSERVABLE, with absence kept separate."""
    if observed is None:
        return UNOBSERVABLE
    try:
        return VERIFIED if int(observed) == expected else CONTRADICTED
    except (TypeError, ValueError):
        return UNOBSERVABLE
