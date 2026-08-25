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
            return (
                '{"found":true,"port_found":%s,"ipv4":"172.31.20.9"}'
                % ("true" if present else "false")
            )
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
