"""CP-SCALE Floor 1 — reading one registration table for twenty-one phones.

Floor 1 hangs twenty-one 7960s off one 2811. Two properties of that scale break
the registration read, and they are independent defects:

1. `show ephone` on twenty-one ephones **pages**, and `SHOW_EPHONE` was not a
   pagination-qualified query. Every capture therefore stopped at its first
   page, `output_complete` stayed False, and the honest reporting fixed in
   32df973 then answered every phone `show_ephone_capture_incomplete`. Refusing
   to call a truncated read an absence is right; leaving the read truncated
   forever means the call-control channel can never answer anything at Floor-1
   scale. The pager continuation machinery already exists, is hard-bounded and
   fails closed -- this query is qualified for it here, on the same measured
   grounds as `SHOW_CONTROLLERS_SERIAL` and `SHOW_IP_PROTOCOLS`.

2. `show ephone` is ONE table for the whole call control, and it was being read
   once per phone. Each of the twenty-one expectations opened its own bounded
   convergence episode, and each episode re-read the same table until its own
   row registered or 180s elapsed -- about 63 minutes of polling to learn what a
   single complete capture states about all twenty-one rows simultaneously.

The evidence semantics do not move: a phone is VERIFIED only from a row that was
actually read, an UNREGISTERED row is still a contradiction, an incomplete
capture still claims nothing, and each phone's own SVI is still read separately.
"""

from __future__ import annotations

import json

from src.packet_tracer_mcp.domain.enterprise.models.configuration_runtime import (
    ActionExecutionStatus,
    ConfigurationFailureCode,
)
from src.packet_tracer_mcp.domain.enterprise.models.voice_plan import (
    VoiceVerificationExpectation,
    VoiceVerificationKind,
)
from src.packet_tracer_mcp.infrastructure.execution.ios_terminal import (
    OperationalQueryId,
    PagerContinuation,
    parse_show_ephone,
)
from src.packet_tracer_mcp.infrastructure.execution.enterprise_voice_runtime import (
    PacketTracerEnterpriseVoiceRuntime,
)
from tests.test_e95_serial_orientation_pager_capture import (
    _PagedTerminal,
    _executor,
)
from tests.test_voice_runtime import FakeVoiceRuntime, _apply


#: Floor 1: extensions 3011..3031 on one 2811.
_FLOOR1_EXTENSIONS = [str(3011 + index) for index in range(21)]


def _ephone_block(index: int, extension: str, *, registered: bool, ip: str) -> str:
    """One `show ephone` entry with the shape measured on PT 9.0.1.0858."""
    state = "REGISTERED in SCCP ver 12" if registered else "UNREGISTERED"
    socket = "[1]" if registered else "[-1]"
    return (
        f"ephone-{index}  Mac:0001.4218.{index:04X}  TCP socket:{socket} "
        f"activeLine:0  {state}\n"
        "mediaActive:0  offhook:0  ringing:0  reset:0  reset_sent:0  paging 0  debug:0\n"
        f"IP:{ip}   0  Telecaster 7960   keepalive 0 max_line 6\n"
        f"button 1: dn {index}  number {extension} CH1   IDLE\n"
    )


def _floor1_pages(
    *, registered: set[str] = frozenset(), per_page: int = 5,
) -> list[str]:
    """The twenty-one-ephone table as Packet Tracer pages it."""
    blocks = [
        _ephone_block(
            index + 1, extension,
            registered=extension in registered,
            ip=f"172.31.20.{index + 2}" if extension in registered else "0.0.0.0",
        )
        for index, extension in enumerate(_FLOOR1_EXTENSIONS)
    ]
    return [
        "".join(blocks[start:start + per_page])
        for start in range(0, len(blocks), per_page)
    ]


def _expectation(extension: str, *, phone: str) -> VoiceVerificationExpectation:
    return VoiceVerificationExpectation(
        id=f"voice/verify/{extension}",
        kind=VoiceVerificationKind.PHONE_REGISTRATION,
        phone_id=phone,
        extension=extension,
        call_control_id="cc",
        action_id=f"voice/bind/{extension}",
        endpoint_device_name=f"F1-PHONE-{extension}",
        endpoint_interface="Vlan20",
    )


# --------------------------------------------------------------------------
# 1: the paged registration table is one complete logical read
# --------------------------------------------------------------------------


def test_show_ephone_walks_its_pager_into_one_complete_registration_table():
    """Twenty-one ephones exceed a page, and page one is not the table.

    Before this query was qualified the capture stopped at its first five rows
    and reported truncated, so the other sixteen phones had no readable row on
    any invocation -- the exact scattered-window observation Floor 1 recorded.
    """
    pages = _floor1_pages(registered={"3011"})
    terminal = _PagedTerminal(pages, command="show ephone")

    result = _executor(terminal).execute("F1-R4", OperationalQueryId.SHOW_EPHONE)

    assert result.executed and result.fresh_output_observed
    assert result.output_complete
    assert not result.truncated_by_pager
    assert result.pager_continuation == PagerContinuation.COMPLETED.value
    assert result.pager_pages_captured == len(pages)
    assert terminal.advances == len(pages) - 1
    assert terminal.cancels == 0

    rows = parse_show_ephone(result.output)
    assert [item.extension for item in rows] == _FLOOR1_EXTENSIONS
    assert [item.extension for item in rows if item.registered] == ["3011"]


def test_a_registration_table_that_cannot_close_still_claims_nothing():
    """Fail-closed survives the qualification: a capture that stalls is truncated."""

    class _Stalling(_PagedTerminal):
        def _advance(self) -> None:
            return

    terminal = _Stalling(_floor1_pages(), command="show ephone")

    result = _executor(terminal).execute("F1-R4", OperationalQueryId.SHOW_EPHONE)

    assert not result.output_complete
    assert result.truncated_by_pager
    assert result.pager_continuation == PagerContinuation.FAILED.value


# --------------------------------------------------------------------------
# 2: one bounded episode answers every phone on the host
# --------------------------------------------------------------------------


class _CountingCallControl:
    """A voice runtime whose `show ephone` is scripted and counted."""

    def __init__(self, runtime, pages, *, complete: bool = True) -> None:
        from src.packet_tracer_mcp.infrastructure.execution.ios_terminal import (
            IosCommandResult,
            IosSessionState,
        )

        self.executions = 0
        self.endpoint_reads: list[str] = []
        output = "F1-R4#show ephone\n" + "".join(pages) + "F1-R4#"

        def execute(device_name, query_id, *, interface=""):
            self.executions += 1
            return IosCommandResult(
                device_name=device_name,
                query_id=query_id,
                executed=True,
                output=output,
                session_state=IosSessionState.EXEC_PROMPT_READY,
                fresh_output_observed=True,
                window_strategy="current_command",
                truncated_by_pager=not complete,
                output_complete=complete,
                pager_pages_captured=len(pages),
            )

        runtime._ios.execute = execute  # noqa: SLF001
        self.runtime = runtime


def _floor1_runtime(pages, *, complete: bool = True, present: bool = True):
    reads: list[str] = []

    def send_and_wait(source, _timeout):
        if "getPortCount" in source and "getIpAddress" in source:
            reads.append(source)
            return json.dumps({
                "found": True,
                "port_found": present,
                "address_channel": present,
                "ipv4": "172.31.20.9" if present else "",
            })
        return "{}"

    runtime = PacketTracerEnterpriseVoiceRuntime(
        lambda: {"devices": [{"name": "F1-R4", "model": "2811"}]},
        lambda _source: True,
        send_and_wait,
        ios_readiness=lambda _name: True,
        registration_timeout_seconds=0.2,
        convergence_interval_seconds=0.05,
    )
    for extension in _FLOOR1_EXTENSIONS:
        runtime._registration_hosts[f"phone-{extension}"] = "F1-R4"  # noqa: SLF001
    control = _CountingCallControl(runtime, pages, complete=complete)
    control.endpoint_reads = reads
    return control


def test_twenty_one_phones_are_read_from_one_bounded_observation_episode():
    """One table, one episode. Twenty-one episodes was twenty-one times the wait.

    Each expectation used to open its own convergence wait over the same
    per-host table, so a Floor 1 where nothing registers spent 21 x 180s
    re-reading a table that already said so on its first complete capture.
    """
    control = _floor1_runtime(_floor1_pages(registered={"3011", "3012"}))
    expectations = [
        _expectation(extension, phone=f"phone-{extension}")
        for extension in _FLOOR1_EXTENSIONS
    ]

    observed = control.runtime.observe_registrations(expectations)

    assert [item.extension for item in observed] == _FLOOR1_EXTENSIONS
    # One shared episode: strictly fewer reads of the table than there are
    # phones, instead of at least one bounded wait per phone.
    assert control.executions < len(expectations)
    # The phone's own SVI stays a per-phone read: it is a different fact.
    assert len(control.endpoint_reads) == len(expectations)


def test_a_shared_capture_still_judges_every_phone_on_its_own_row():
    control = _floor1_runtime(_floor1_pages(registered={"3011", "3012"}))
    expectations = [
        _expectation(extension, phone=f"phone-{extension}")
        for extension in _FLOOR1_EXTENSIONS
    ]

    observed = {
        item.extension: item
        for item in control.runtime.observe_registrations(expectations)
    }

    assert observed["3011"].status is ActionExecutionStatus.VERIFIED
    assert observed["3011"].call_control_ipv4 == "172.31.20.2"
    assert observed["3011"].evidence_method == "fresh_privileged_show_ephone"
    assert observed["3013"].status is ActionExecutionStatus.FAILED
    # `IP:0.0.0.0` is the call control saying it has no address for this phone.
    assert observed["3013"].call_control_ipv4 == ""
    assert all(item.endpoint_interface_present for item in observed.values())
    assert all(item.endpoint_ipv4 == "172.31.20.9" for item in observed.values())


def test_a_shared_capture_that_is_incomplete_claims_nothing_about_any_phone():
    """Truncation is a limit of the read, and sharing it must not hide that."""
    control = _floor1_runtime(
        _floor1_pages(registered={"3011"})[:1], complete=False,
    )
    expectations = [
        _expectation(extension, phone=f"phone-{extension}")
        for extension in _FLOOR1_EXTENSIONS
    ]

    observed = {
        item.extension: item
        for item in control.runtime.observe_registrations(expectations)
    }

    assert observed["3016"].status is ActionExecutionStatus.UNOBSERVABLE
    assert observed["3016"].evidence_method == "show_ephone_capture_incomplete"
    # A row that WAS read inside the truncated window is still an observation
    # about that phone; truncation only silences the rows it never reached.
    assert observed["3011"].status is ActionExecutionStatus.VERIFIED


def test_an_absent_svi_is_reported_apart_from_an_unaddressed_one():
    control = _floor1_runtime(_floor1_pages(), present=False)
    expectations = [_expectation("3011", phone="phone-3011")]

    observed = control.runtime.observe_registrations(expectations)[0]

    assert not observed.endpoint_interface_present
    assert observed.endpoint_ipv4 == ""


def test_the_single_phone_entry_point_still_answers_on_its_own():
    """`observe_registration` keeps its contract; batching is an addition."""
    control = _floor1_runtime(_floor1_pages(registered={"3011"}))

    observed = control.runtime.observe_registration(
        _expectation("3011", phone="phone-3011"),
    )

    assert observed.status is ActionExecutionStatus.VERIFIED
    assert observed.call_control_ipv4 == "172.31.20.2"


# --------------------------------------------------------------------------
# 3: the applicator asks once, and stays fail-closed when the ask fails
# --------------------------------------------------------------------------


class _BatchingRuntime(FakeVoiceRuntime):
    """A runtime that can answer a whole batch of expectations at once."""

    def __init__(self, *, raises: Exception | None = None) -> None:
        super().__init__()
        self.batches: list[list[str]] = []
        self.singles: list[str] = []
        self._raises = raises

    def observe_registration(self, expectation):
        self.singles.append(expectation.phone_id)
        return super().observe_registration(expectation)

    def observe_registrations(self, expectations):
        self.batches.append([item.phone_id for item in expectations])
        if self._raises is not None:
            raise self._raises
        return [super(_BatchingRuntime, self).observe_registration(item)
                for item in expectations]


def test_the_applicator_asks_the_runtime_once_for_the_whole_batch():
    _, runtime, result = _apply(_BatchingRuntime())

    assert len(runtime.batches) == 1
    assert not runtime.singles
    assert runtime.batches[0] == [item.phone_id for item in result.registrations]
    assert all(
        item.status is ActionExecutionStatus.VERIFIED
        for item in result.registrations
    )


def test_a_runtime_without_a_batch_entry_point_keeps_the_per_phone_contract():
    _, runtime, result = _apply(FakeVoiceRuntime())

    assert all(
        item.status is ActionExecutionStatus.VERIFIED
        for item in result.registrations
    )


def test_a_batch_that_cannot_be_read_fails_every_phone_closed():
    """A channel that did not answer is not a phone that registered."""
    _, _, result = _apply(_BatchingRuntime(raises=RuntimeError("bridge lost")))

    assert result.registrations
    assert all(
        item.status is ActionExecutionStatus.FAILED
        and item.failure_code is ConfigurationFailureCode.SESSION_FAILED
        for item in result.registrations
    )


def test_a_batch_answering_a_different_number_of_phones_is_refused():
    class _Miscounting(_BatchingRuntime):
        def observe_registrations(self, expectations):
            return super().observe_registrations(expectations)[:-1]

    _, _, result = _apply(_Miscounting())

    assert all(
        item.status is ActionExecutionStatus.FAILED
        for item in result.registrations
    )


# --------------------------------------------------------------------------
# 4: the phone's own address channel, and the row a complete table lacks
# --------------------------------------------------------------------------


def _endpoint_runtime(pages, *, getter: bool, ipv4: str = "", present: bool = True):
    """A Floor-1 runtime whose phone SVI may or may not expose an address."""
    scripts: list[str] = []

    def send_and_wait(source, _timeout):
        if "getPortCount" in source and "getIpAddress" in source:
            scripts.append(source)
            return json.dumps({
                "found": True,
                "port_found": present,
                # `able` is the fact under test: whether this port has an
                # address channel to ask at all, separate from what it answered.
                "address_channel": bool(getter and present),
                "ipv4": ipv4 if (getter and present) else "",
            })
        return "{}"

    runtime = PacketTracerEnterpriseVoiceRuntime(
        lambda: {"devices": [{"name": "F1-R4", "model": "2811"}]},
        lambda _source: True,
        send_and_wait,
        ios_readiness=lambda _name: True,
        registration_timeout_seconds=0.2,
        convergence_interval_seconds=0.05,
    )
    for extension in _FLOOR1_EXTENSIONS:
        runtime._registration_hosts[f"phone-{extension}"] = "F1-R4"  # noqa: SLF001
    control = _CountingCallControl(runtime, pages)
    control.scripts = scripts
    return control


def test_a_phone_svi_with_no_address_getter_is_not_a_phone_with_no_lease():
    """The measured AccessPoint-PT case, on the channel that judges the phone.

    An SVI that exposes no `getIpAddress` and an SVI that exposes one and holds
    nothing both read back as the empty string. Collapsing them turns "we could
    not look" into "the phone did not acquire" -- which is precisely the finding
    Floor 1 must not manufacture.
    """
    control = _endpoint_runtime(_floor1_pages(), getter=False)

    observed = control.runtime.observe_registrations(
        [_expectation("3011", phone="phone-3011")],
    )[0]

    assert observed.endpoint_interface_present
    assert not observed.endpoint_address_channel
    assert observed.endpoint_ipv4 == ""


def test_a_phone_svi_that_can_answer_and_holds_nothing_says_so():
    control = _endpoint_runtime(_floor1_pages(), getter=True, ipv4="")

    observed = control.runtime.observe_registrations(
        [_expectation("3011", phone="phone-3011")],
    )[0]

    assert observed.endpoint_interface_present
    assert observed.endpoint_address_channel
    assert observed.endpoint_ipv4 == ""


def test_an_addressed_phone_svi_reports_its_address_and_its_channel():
    control = _endpoint_runtime(
        _floor1_pages(registered={"3011"}), getter=True, ipv4="172.16.20.7",
    )

    observed = control.runtime.observe_registrations(
        [_expectation("3011", phone="phone-3011")],
    )[0]

    assert observed.endpoint_address_channel
    assert observed.endpoint_ipv4 == "172.16.20.7"


def test_an_unreadable_phone_address_channel_never_reads_as_a_failed_lease():
    """The applicator's claim must name the ceiling, not invent an absence."""
    from src.packet_tracer_mcp.application.use_cases.apply_voice import (
        _addressing_claim,
    )
    from src.packet_tracer_mcp.domain.enterprise.models.voice_plan import (
        PhoneAssignment,
    )
    from src.packet_tracer_mcp.domain.enterprise.models.voice_runtime import (
        RuntimePhoneRegistration,
    )

    assignment = PhoneAssignment(
        phone_id="phone-3011", physical_device_name="F1-PHONE-3011",
        model="7960", site_id="large-branch", extension="3011",
        call_control_id="cc", voice_vlan_id=20,
        voice_segment_id="large-branch-voice",
        access_configuration_action_id="cfg/access/1",
        addressing_configuration_action_id="",
        binding_action_id="voice/bind/3011",
        addressing_interface="Vlan20",
        voice_network="172.16.20.0", voice_prefix=24,
    )
    unreadable = RuntimePhoneRegistration(
        expectation_id="voice/verify/3011", phone_id="phone-3011",
        extension="3011", status=ActionExecutionStatus.FAILED,
        endpoint_interface="Vlan20", endpoint_interface_present=True,
        endpoint_address_channel=False,
    )
    empty = unreadable.model_copy(update={"endpoint_address_channel": True})

    unreadable_status, unreadable_message = _addressing_claim(assignment, unreadable)
    empty_status, empty_message = _addressing_claim(assignment, empty)

    assert unreadable_status is ActionExecutionStatus.UNOBSERVABLE
    assert empty_status is ActionExecutionStatus.UNOBSERVABLE
    # Both are UNOBSERVABLE, and they are not the same observation.
    assert unreadable_message != empty_message
    assert "channel" in unreadable_message.casefold()


def test_a_complete_table_without_this_row_says_what_it_did_contain():
    """A row absent from a complete capture is its own fact, not a missing getter.

    Floor 1 read a complete pager-walked table that carried nineteen rows, and
    the two phones it did not name were reported with the message for a phone no
    `show ephone` session is bound to at all. That message describes a different
    failure and makes the real one undiagnosable -- a row missing from a table
    that WAS read whole is only interpretable against the rows that were in it.
    """
    # The first page never arrives, so 3011..3015 have no row in a capture that
    # nonetheless closed complete.
    control = _floor1_runtime(["".join(_floor1_pages()[1:])])
    observed = {
        item.extension: item
        for item in control.runtime.observe_registrations([
            _expectation(extension, phone=f"phone-{extension}")
            for extension in ("3011", "3016")
        ])
    }

    absent = observed["3011"]
    assert absent.status is ActionExecutionStatus.UNOBSERVABLE
    assert absent.evidence_method == "show_ephone_complete_without_this_row"
    assert "3016" in absent.message
    assert "16 extension(s)" in absent.message
    assert observed["3016"].status is ActionExecutionStatus.FAILED


# --------------------------------------------------------------------------
# 5: whether the phone was ever asked to acquire
# --------------------------------------------------------------------------


def _dhcp_runtime(pages, *, dhcp, getter: bool = True):
    """A Floor-1 runtime whose phone SVI reports a DHCP state, or cannot."""

    def send_and_wait(source, _timeout):
        if "getPortCount" in source and "getIpAddress" in source:
            body = {
                "found": True, "port_found": True,
                "address_channel": True, "ipv4": "",
            }
            if getter:
                body["dhcp_channel"] = True
                body["dhcp"] = dhcp
            else:
                body["dhcp_channel"] = False
                body["dhcp"] = None
            return json.dumps(body)
        return "{}"

    runtime = PacketTracerEnterpriseVoiceRuntime(
        lambda: {"devices": [{"name": "F1-R4", "model": "2811"}]},
        lambda _source: True,
        send_and_wait,
        ios_readiness=lambda _name: True,
        registration_timeout_seconds=0.2,
        convergence_interval_seconds=0.05,
    )
    for extension in _FLOOR1_EXTENSIONS:
        runtime._registration_hosts[f"phone-{extension}"] = "F1-R4"  # noqa: SLF001
    return _CountingCallControl(runtime, pages)


def test_a_phone_that_was_never_asked_to_acquire_is_reported_as_such():
    """An SVI with DHCP off has not failed to acquire; it never solicited.

    Floor 1 gives its twenty-one phones no endpoint addressing action at all --
    E5 stopped claiming a phone on a voice VLAN, correctly, because the SVI does
    not exist when E5 is preflighted. Whether anything then asks the phone to
    acquire is exactly the question that separates "DHCP is broken" from "no
    DHCP was ever attempted", and it was not being read.
    """
    control = _dhcp_runtime(_floor1_pages(), dhcp=False)

    observed = control.runtime.observe_registrations(
        [_expectation("3011", phone="phone-3011")],
    )[0]

    assert observed.endpoint_interface_present
    assert observed.endpoint_address_channel
    assert observed.endpoint_ipv4 == ""
    assert observed.endpoint_dhcp_enabled is False


def test_a_phone_that_solicited_and_holds_nothing_is_a_different_report():
    control = _dhcp_runtime(_floor1_pages(), dhcp=True)

    observed = control.runtime.observe_registrations(
        [_expectation("3011", phone="phone-3011")],
    )[0]

    assert observed.endpoint_dhcp_enabled is True


def test_an_svi_with_no_dhcp_getter_never_reads_as_dhcp_off():
    """Absent is not False. The AccessPoint-PT lesson, on the third channel."""
    control = _dhcp_runtime(_floor1_pages(), dhcp=None, getter=False)

    observed = control.runtime.observe_registrations(
        [_expectation("3011", phone="phone-3011")],
    )[0]

    assert observed.endpoint_dhcp_enabled is None


# --------------------------------------------------------------------------
# 6: the phone as a device, not only the SVI the plan names
# --------------------------------------------------------------------------


def _device_runtime(pages, *, device_ipv4=None, device_dhcp=None):
    """A Floor-1 runtime whose phone answers at device level as well."""

    def send_and_wait(source, _timeout):
        if "getPortCount" in source and "getIpAddress" in source:
            body = {
                "found": True, "port_found": True,
                "address_channel": True, "ipv4": "",
                "dhcp_channel": False, "dhcp": None,
                "device_address_channel": device_ipv4 is not None,
                "device_ipv4": device_ipv4 or "",
                "device_dhcp_channel": device_dhcp is not None,
                "device_dhcp": device_dhcp,
            }
            return json.dumps(body)
        return "{}"

    runtime = PacketTracerEnterpriseVoiceRuntime(
        lambda: {"devices": [{"name": "F1-R4", "model": "2811"}]},
        lambda _source: True,
        send_and_wait,
        ios_readiness=lambda _name: True,
        registration_timeout_seconds=0.2,
        convergence_interval_seconds=0.05,
    )
    for extension in _FLOOR1_EXTENSIONS:
        runtime._registration_hosts[f"phone-{extension}"] = "F1-R4"  # noqa: SLF001
    return _CountingCallControl(runtime, pages)


def test_the_phone_is_asked_at_device_level_when_its_svi_cannot_answer():
    """`Vlan20` exposes no DHCP flag, and that is not the end of the question.

    The AccessPoint-PT probe that settled addressability on this build asked the
    device AND every port, because Packet Tracer does not put the same getters
    in both places. The phone read asked one port and stopped, so "the SVI has
    no DHCP flag" closed a question the device itself may still answer.
    """
    control = _device_runtime(_floor1_pages(), device_dhcp=False)

    observed = control.runtime.observe_registrations(
        [_expectation("3011", phone="phone-3011")],
    )[0]

    assert observed.endpoint_dhcp_enabled is None
    assert observed.device_dhcp_enabled is False


def test_an_address_the_device_holds_is_reported_without_overwriting_the_svi():
    """The plan names Vlan20 and that claim stays Vlan20's; the device is extra.

    A phone that holds an address somewhere its voice SVI does not report is a
    finding about where to read, not a phone that acquired on the interface the
    plan asked about. Both facts travel; neither is silently substituted.
    """
    control = _device_runtime(_floor1_pages(), device_ipv4="172.16.20.5")

    observed = control.runtime.observe_registrations(
        [_expectation("3011", phone="phone-3011")],
    )[0]

    assert observed.endpoint_ipv4 == ""
    assert observed.device_ipv4 == "172.16.20.5"


def test_a_device_that_exposes_nothing_reports_nothing_rather_than_false():
    control = _device_runtime(_floor1_pages())

    observed = control.runtime.observe_registrations(
        [_expectation("3011", phone="phone-3011")],
    )[0]

    assert observed.device_dhcp_enabled is None
    assert observed.device_ipv4 == ""
