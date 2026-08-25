"""Adapter E7 para la superficie de telefonía documentada de Packet Tracer."""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Sequence

from ...application.ports.phone_control import PhoneControlPort
from ...domain.enterprise.models.configuration_runtime import (
    ActionExecutionStatus,
    ConfigurationFailureCode,
    FieldVerificationStatus,
    RuntimeActionMutation,
    RuntimeConfigurationTarget,
)
from ...domain.enterprise.models.voice_plan import (
    BindPhoneToExtension,
    CallExpectation,
    ConfigureDialRule,
    VoiceAction,
    VoiceVerificationExpectation,
)
from ...domain.enterprise.models.voice_runtime import (
    RuntimeCallObservation,
    RuntimePhoneRegistration,
)
from ..generator.voice_renderer import PacketTracerVoiceRenderer
from .configuration_runtime import PacketTracerConfigurationRuntime
from .device_lifecycle import StateConvergenceWaiter
from .ios_terminal import ControlledIosExecutor, OperationalQueryId, parse_show_ephone
from .phone_control import (
    UnavailablePhoneControl,
)
from .runtime_inventory import normalize_runtime_inventory


_MAC = re.compile(r"^[0-9A-Fa-f]{12}$")
#: What an unaddressed interface reads as, on both channels. A call control
#: printing `IP:0.0.0.0` for an unregistered ephone is telling us it has no
#: address for that phone; carrying it forward as an address turned an absence
#: into "0.0.0.0 is outside the voice segment", a contradiction manufactured
#: out of nothing having been seen.
_UNADDRESSED = frozenset({"", "0.0.0.0"})


def _reported_address(value: object) -> str:
    """The address a channel actually reported, or "" when it reported none."""
    address = str(value or "").strip()
    return "" if address in _UNADDRESSED else address


class PacketTracerEnterpriseVoiceRuntime:
    """Aplica acciones cerradas; no publica IOS ni acciones telefónicas arbitrarias."""

    def __init__(
        self,
        query_inventory: Callable[[], list[dict] | dict],
        send: Callable[[str], bool],
        send_and_wait: Callable[[str, float], str | None],
        *,
        ios_readiness: Callable[[str], bool] | None = None,
        phone_control: PhoneControlPort | None = None,
        registration_timeout_seconds: float = 30.0,
        convergence_interval_seconds: float = 0.5,
    ) -> None:
        self._query_inventory = query_inventory
        self._send_and_wait = send_and_wait
        self._configuration = PacketTracerConfigurationRuntime(send)
        self._renderer = PacketTracerVoiceRenderer()
        self._ios = ControlledIosExecutor(send_and_wait)
        self._ios_readiness = ios_readiness or self._wait_for_ios
        self._phone_control = phone_control or UnavailablePhoneControl()
        self._registration_timeout = registration_timeout_seconds
        self._convergence_interval = convergence_interval_seconds
        self._targets: dict[str, RuntimeConfigurationTarget] = {}
        self._ready_ios_devices: set[str] = set()
        self._registration_hosts: dict[str, str] = {}

    def inventory(self) -> list[RuntimeConfigurationTarget]:
        targets = normalize_runtime_inventory(self._query_inventory())
        self._targets = {item.device_name: item for item in targets}
        return targets

    def apply_actions(
        self, actions: Sequence[VoiceAction],
    ) -> list[RuntimeActionMutation]:
        if not actions:
            return []
        host_names = {item.host_device_name for item in actions}
        if len(host_names) != 1:
            return self._failed(actions, "A voice batch must target exactly one call-control host.")
        host = next(iter(host_names))
        if not self._targets:
            self.inventory()
        if host not in self._targets:
            return self._failed(actions, f"Call-control host {host!r} was not found.")

        local_rules = [
            item for item in actions
            if isinstance(item, ConfigureDialRule) and item.local
        ]
        nonlocal_rules = [
            item for item in actions
            if isinstance(item, ConfigureDialRule) and not item.local
        ]
        renderable = [item for item in actions if item not in local_rules]
        results: dict[str, RuntimeActionMutation] = {
            item.id: RuntimeActionMutation(
                action_id=item.id,
                applied=True,
                message="Local dialing is implicit in the configured CME directory.",
                batch_id=f"{host}:implicit-local-dial",
            )
            for item in local_rules
        }
        if nonlocal_rules:
            results.update({item.id: RuntimeActionMutation(
                action_id=item.id,
                applied=False,
                failure_code=ConfigurationFailureCode.CAPABILITY_UNKNOWN,
                message="Packet Tracer intersite voice rendering is not verified.",
            ) for item in nonlocal_rules})
            renderable = [item for item in renderable if item not in nonlocal_rules]
        if not renderable:
            return [results[item.id] for item in actions]

        if host not in self._ready_ios_devices:
            if not self._ios_readiness(host):
                results.update({item.id: RuntimeActionMutation(
                    action_id=item.id,
                    applied=False,
                    failure_code=ConfigurationFailureCode.SESSION_FAILED,
                    message="IOS did not reach OPERATIONAL_READY before voice configuration.",
                ) for item in renderable})
                return [results[item.id] for item in actions]
            self._ready_ios_devices.add(host)

        phone_macs: dict[str, str] = {}
        try:
            for binding in (
                item for item in renderable if isinstance(item, BindPhoneToExtension)
            ):
                self._registration_hosts[binding.phone_id] = binding.host_device_name
                phone_macs[binding.phone_id] = self._phone_mac(
                    binding.physical_device_name,
                )
            batches = self._renderer.render_device_batches(
                host, self._targets[host].model, list(renderable),
                phone_macs=phone_macs,
            )
        except ValueError as exc:
            results.update({item.id: RuntimeActionMutation(
                action_id=item.id,
                applied=False,
                failure_code=ConfigurationFailureCode.APPLICATION_FAILED,
                message=str(exc),
            ) for item in renderable})
            return [results[item.id] for item in actions]

        applied_ids: set[str] = set()
        for batch in batches:
            accepted = self._configuration.configure_ios(host, batch.ios_payload)
            for action_id in batch.action_ids:
                applied_ids.add(action_id)
                results[action_id] = RuntimeActionMutation(
                    action_id=action_id,
                    applied=accepted,
                    failure_code=(
                        ConfigurationFailureCode.NONE
                        if accepted else ConfigurationFailureCode.CALL_CONTROL_APPLICATION_FAILED
                    ),
                    message=(
                        "Typed voice batch accepted by Packet Tracer."
                        if accepted else "Packet Tracer rejected the typed voice batch."
                    ),
                    batch_id=f"{host}:{int(batch.phase)}",
                )
        for item in renderable:
            if item.id not in applied_ids:
                results[item.id] = RuntimeActionMutation(
                    action_id=item.id,
                    applied=False,
                    failure_code=ConfigurationFailureCode.APPLICATION_FAILED,
                    message="The trusted voice renderer produced no mutation for this action.",
                )
        return [results[item.id] for item in actions]

    def inspect_call_control(
        self, device_name: str, *, max_extensions: int = 144,
    ) -> dict[str, object]:
        """Read-back fresco por el SHOW que PT 9.0.1 expone realmente."""
        if not 1 <= max_extensions <= 144:
            raise ValueError("max_extensions must stay within Packet Tracer CME limits.")
        result = self._ios.execute(device_name, OperationalQueryId.SHOW_EPHONE)
        rows = [
            item for item in parse_show_ephone(result.output)
            if item.index <= max_extensions
        ] if result.executed else []
        return {
            "executed": result.executed,
            "fresh_output_observed": result.fresh_output_observed,
            "window_strategy": result.window_strategy,
            "failure_reason": result.failure_reason,
            # COMPLETA is a dimension of its own, and dropping it made a window
            # that stopped early indistinguishable from an ephone that is not
            # there. With 21 ephones the output pages, and that is exactly the
            # difference between "this phone did not register" and "this read
            # did not reach it".
            "output_complete": result.output_complete,
            "truncated_by_pager": result.truncated_by_pager,
            "pager_pages_captured": result.pager_pages_captured,
            "ephones": [item.__dict__ for item in rows],
        }

    def observe_registration(
        self, expectation: VoiceVerificationExpectation,
    ) -> RuntimePhoneRegistration:
        return self.observe_registrations([expectation])[0]

    def observe_registrations(
        self, expectations: Sequence[VoiceVerificationExpectation],
    ) -> list[RuntimePhoneRegistration]:
        """One bounded observation episode per call control, not per phone.

        `show ephone` is ONE table for the whole call control: a single complete
        capture states, simultaneously, what every ephone row on that host is
        doing. Reading it once per phone multiplied one bounded wait by the
        number of phones -- twenty-one 7960s that never register cost 21 x the
        registration timeout to learn what the first complete capture already
        said -- without adding a single observation.

        Nothing about the evidence moves. Each phone is still judged on its own
        row, from a capture that was actually read; the episode only ends early
        when EVERY phone in the group is registered, so no phone gets a shorter
        window than the contract gives it; an incomplete capture still claims
        nothing; and the phone's own SVI is still read per phone, because it is
        a different fact observed on a different channel.
        """
        ordered = list(expectations)
        results: dict[int, RuntimePhoneRegistration] = {}
        by_host: dict[str, list[tuple[int, VoiceVerificationExpectation]]] = {}
        for index, expectation in enumerate(ordered):
            host = self._registration_hosts.get(expectation.phone_id)
            if not host:
                results[index] = self._unobservable_registration(expectation)
                continue
            by_host.setdefault(host, []).append((index, expectation))
        for host, group in by_host.items():
            results.update(self._observe_host_registrations(host, group))
        return [results[index] for index in range(len(ordered))]

    def _observe_host_registrations(
        self,
        host: str,
        group: Sequence[tuple[int, VoiceVerificationExpectation]],
    ) -> dict[int, RuntimePhoneRegistration]:
        """Walk one call control's registration table until the group settles."""
        decided: dict[int, tuple[dict[str, object], dict, int]] = {}
        last: dict[str, object] = {}
        attempts = 0

        def inspect() -> dict[str, object]:
            nonlocal last, attempts
            attempts += 1
            last = self.inspect_call_control(host)
            rows = last.get("ephones", [])
            by_extension = {
                str(item.get("extension") or ""): item
                for item in rows
                if isinstance(item, dict)
            }
            last["by_extension"] = by_extension
            for index, expectation in group:
                if index in decided:
                    continue
                match = by_extension.get(expectation.extension)
                if isinstance(match, dict) and match.get("registered"):
                    decided[index] = (last, match, attempts)
            return {
                "found": bool(last.get("executed")),
                # The episode closes early only when every phone on this host
                # has registered. Anything less keeps reading until the bound.
                "configuration_channel": len(decided) == len(group),
            }

        StateConvergenceWaiter(
            inspect,
            timeout_seconds=self._registration_timeout,
            interval_seconds=self._convergence_interval,
        ).wait()

        final_rows = last.get("by_extension")
        final_rows = final_rows if isinstance(final_rows, dict) else {}
        complete = bool(last.get("output_complete"))
        observed: dict[int, RuntimePhoneRegistration] = {}
        for index, expectation in group:
            endpoint = self._endpoint_observation(expectation)
            endpoint_ipv4 = str(endpoint["ipv4"])
            endpoint_present = bool(endpoint["present"])
            settled = decided.get(index)
            if settled is not None:
                capture, match, seen_after = settled
                observed[index] = RuntimePhoneRegistration(
                    expectation_id=expectation.id,
                    phone_id=expectation.phone_id,
                    extension=expectation.extension,
                    status=ActionExecutionStatus.VERIFIED,
                    direct_readback=FieldVerificationStatus.VERIFIED,
                    evidence_method="fresh_privileged_show_ephone",
                    fresh_evidence=bool(capture.get("fresh_output_observed")),
                    call_control_ipv4=_reported_address(match.get("ip_address")),
                    endpoint_ipv4=endpoint_ipv4,
                    endpoint_interface=expectation.endpoint_interface,
                    endpoint_interface_present=endpoint_present,
                    message=(
                        f"SCCP registered at {match.get('ip_address')} after "
                        f"{seen_after} observation(s)."
                    ),
                )
                continue
            match = final_rows.get(expectation.extension)
            if isinstance(match, dict):
                observed[index] = RuntimePhoneRegistration(
                    expectation_id=expectation.id,
                    phone_id=expectation.phone_id,
                    extension=expectation.extension,
                    status=ActionExecutionStatus.FAILED,
                    direct_readback=FieldVerificationStatus.FAILED,
                    evidence_method="fresh_privileged_show_ephone",
                    fresh_evidence=bool(last.get("fresh_output_observed")),
                    call_control_ipv4=_reported_address(match.get("ip_address")),
                    endpoint_ipv4=endpoint_ipv4,
                    endpoint_interface=expectation.endpoint_interface,
                    endpoint_interface_present=endpoint_present,
                    message="The current ephone row remained UNREGISTERED before timeout.",
                )
                continue
            if last.get("executed") and not complete:
                observed[index] = self._unobservable_registration(
                    expectation,
                    endpoint_ipv4=endpoint_ipv4,
                    endpoint_interface_present=endpoint_present,
                    evidence_method="show_ephone_capture_incomplete",
                    message=(
                        "The show ephone capture was truncated after "
                        f"{last.get('pager_pages_captured')} page(s), so the absence "
                        f"of extension {expectation.extension} is a limit of the read "
                        "and not an observation about this phone."
                    ),
                )
                continue
            observed[index] = self._unobservable_registration(
                expectation,
                endpoint_ipv4=endpoint_ipv4,
                endpoint_interface_present=endpoint_present,
            )
        return observed

    def _endpoint_observation(
        self, expectation: VoiceVerificationExpectation,
    ) -> dict[str, object]:
        """What the phone itself reports on the SVI this plan addressed.

        Independent of the call control's view on purpose: a phone that has
        acquired but not registered, and a call control that remembers a phone
        that is gone, are different failures and must not look alike.
        """
        device = expectation.endpoint_device_name
        interface = expectation.endpoint_interface
        if not device or not interface:
            return {"present": False, "ipv4": ""}
        script = "".join((
            "try{var d=ipc.network().getDevice(", json.dumps(device), ");",
            "var want=", json.dumps(interface), ";var ip='';var p=null;",
            "if(d){for(var i=0;i<d.getPortCount();i++){var c=d.getPortAt(i);",
            "if(c&&typeof c.getName==='function'&&String(c.getName())===want){",
            "p=c;ip=typeof c.getIpAddress==='function'?String(c.getIpAddress()):'';",
            "break;}}}",
            "reportResult(JSON.stringify({found:!!d,port_found:!!p,ipv4:ip}));",
            "}catch(e){reportResult('ERROR:'+e);}",
        ))
        observed = self._json_result(script, 5.0)
        # Whether the SVI exists at all is the fact that separates "the phone
        # never learned its voice VLAN" from "it did, and holds no lease". Both
        # read as no address, and they are different findings about the voice
        # path, so the presence travels with the value.
        present = bool(observed.get("port_found"))
        return {
            "present": present,
            "ipv4": _reported_address(observed.get("ipv4")) if present else "",
        }

    def _unobservable_registration(
        self,
        expectation: VoiceVerificationExpectation,
        *,
        endpoint_ipv4: str | None = None,
        endpoint_interface_present: bool | None = None,
        evidence_method: str = (
            "pt_9_0_1_extension_api_has_no_registration_getter"
        ),
        message: str = (
            "No fresh show ephone session is bound to this phone; the documented "
            "extension API has no registration getter."
        ),
    ) -> RuntimePhoneRegistration:
        # An unreadable registration table says nothing about whether the phone
        # acquired, and the two questions fail independently: a phone can hold a
        # lease the call control never saw. Reading its SVI here keeps that
        # evidence instead of discarding it with the registration.
        return RuntimePhoneRegistration(
            expectation_id=expectation.id,
            phone_id=expectation.phone_id,
            extension=expectation.extension,
            status=ActionExecutionStatus.UNOBSERVABLE,
            direct_readback=FieldVerificationStatus.UNOBSERVABLE,
            evidence_method=evidence_method,
            fresh_evidence=False,
            endpoint_ipv4=(
                str(self._endpoint_observation(expectation)["ipv4"])
                if endpoint_ipv4 is None else endpoint_ipv4
            ),
            endpoint_interface=expectation.endpoint_interface,
            endpoint_interface_present=bool(endpoint_interface_present),
            message=message,
        )

    def verify_call(
        self, expectation: CallExpectation, call_attempt_id: str, started_ns: int,
    ) -> RuntimeCallObservation:
        return self._phone_control.execute_call(
            expectation, call_attempt_id, started_ns,
        )

    def _wait_for_ios(self, device_name: str) -> bool:
        return self._ios.wait_until_ready(device_name).state.value == "operational_ready"

    def _phone_mac(self, device_name: str) -> str:
        name = json.dumps(device_name)
        script = "".join((
            "try{var d=ipc.network().getDevice(", name, ");var found='';",
            "if(d){for(var i=0;i<d.getPortCount();i++){var p=d.getPortAt(i);",
            "var m=p&&typeof p.getMacAddress==='function'?String(p.getMacAddress()):'';",
            "var c=m.replace(/[.:-]/g,'');if(/^[0-9A-Fa-f]{12}$/.test(c)&&",
            "c!=='000000000000'){found=m;break;}}}",
            "reportResult(JSON.stringify({found:!!d,mac:found}));",
            "}catch(e){reportResult('ERROR:'+e);}",
        ))
        observed = self._json_result(script, 5.0)
        mac = str(observed.get("mac") or "")
        if not _MAC.fullmatch(re.sub(r"[.:-]", "", mac)):
            raise ValueError(f"No observable MAC address for phone {device_name!r}.")
        return mac

    def _json_result(self, script: str, timeout: float) -> dict[str, object]:
        raw = self._send_and_wait(script, timeout)
        if raw is None or raw.startswith(("ERROR:", "PT_ERROR:")):
            return {}
        try:
            value = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return {}
        return value if isinstance(value, dict) else {}

    @staticmethod
    def _failed(actions: Sequence[VoiceAction], message: str) -> list[RuntimeActionMutation]:
        return [RuntimeActionMutation(
            action_id=item.id,
            applied=False,
            failure_code=ConfigurationFailureCode.APPLICATION_FAILED,
            message=message,
        ) for item in actions]
