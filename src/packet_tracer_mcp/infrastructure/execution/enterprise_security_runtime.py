"""Adapter E8 para aplicación y evidencia de seguridad en Packet Tracer."""

from __future__ import annotations

import ipaddress
import json
from collections.abc import Callable, Sequence
from time import monotonic, sleep

from ...domain.enterprise.models.configuration_runtime import (
    ActionExecutionStatus,
    ConfigurationFailureCode,
    FieldVerificationStatus,
    RuntimeActionMutation,
    RuntimeConfigurationTarget,
)
from ...domain.enterprise.models.security_plan import (
    AddSecurityAclRule,
    ApplyDeviceHardening,
    AttachSecurityAcl,
    ConfigureDhcpSnooping,
    ConfigureDynamicArpInspection,
    ConfigureEndpointPortSecurity,
    ConfigureSecurityNat,
    SecurityAction,
    SecurityDecision,
    SecurityProbeKind,
    SecurityVerificationExpectation,
    SecurityVerificationKind,
)
from ...domain.enterprise.models.security_runtime import (
    RuntimeSecurityVerification,
    SecurityVerificationStage,
)
from ..generator.security_renderer import PacketTracerSecurityRenderer
from .configuration_runtime import PacketTracerConfigurationRuntime
from .ios_terminal import ControlledIosExecutor, OperationalQueryId
from .security_ios import (
    parse_show_access_lists,
    parse_show_ip_arp_inspection,
    parse_show_ip_dhcp_snooping,
    parse_show_ip_interface_security,
    parse_show_ip_nat_statistics,
    parse_show_ip_nat_translations,
    parse_show_port_security_interface,
)
from .typed_ping import TypedPingExecutor


TypedBehaviorDriver = Callable[
    [SecurityVerificationExpectation, SecurityVerificationStage],
    RuntimeSecurityVerification,
]


class PacketTracerEnterpriseSecurityRuntime:
    """Ejecuta únicamente acciones E8 compiladas y probes derivados del plan."""

    def __init__(
        self,
        query_inventory: Callable[[], list[dict] | dict],
        send: Callable[[str], bool],
        send_and_wait: Callable[[str, float], str | None],
        *,
        ios_readiness: Callable[[str], bool] | None = None,
        ios_executor: ControlledIosExecutor | None = None,
        service_behavior: TypedBehaviorDriver | None = None,
        voice_behavior: TypedBehaviorDriver | None = None,
        behavior_timeout_seconds: float = 12.0,
        convergence_interval_seconds: float = 0.25,
        clock: Callable[[], float] = monotonic,
        sleeper: Callable[[float], None] = sleep,
    ) -> None:
        self._query_inventory = query_inventory
        self._send_and_wait = send_and_wait
        self._configuration = PacketTracerConfigurationRuntime(send)
        self._renderer = PacketTracerSecurityRenderer()
        self._ios = ios_executor or ControlledIosExecutor(send_and_wait)
        self._ios_readiness = ios_readiness or self._wait_for_ios
        self._service_behavior = service_behavior
        self._voice_behavior = voice_behavior
        self._behavior_timeout = behavior_timeout_seconds
        self._interval = convergence_interval_seconds
        self._clock = clock
        self._sleep = sleeper
        self._ping = TypedPingExecutor(
            send_and_wait,
            timeout_seconds=behavior_timeout_seconds,
            interval_seconds=convergence_interval_seconds,
            clock=clock,
            sleeper=sleeper,
        )
        self._targets: dict[str, RuntimeConfigurationTarget] = {}
        self._actions: dict[str, SecurityAction] = {}
        self._ready_ios_devices: set[str] = set()

    def inventory(self) -> list[RuntimeConfigurationTarget]:
        raw = self._query_inventory()
        items = raw.get("devices", []) if isinstance(raw, dict) else raw
        targets: list[RuntimeConfigurationTarget] = []
        for item in items:
            interfaces = sorted({
                str(port.get("name") if isinstance(port, dict) else port)
                for port in (item.get("ports", item.get("interfaces", [])) or [])
                if port and (not isinstance(port, dict) or port.get("name"))
            }, key=str.casefold)
            targets.append(RuntimeConfigurationTarget(
                device_name=str(item.get("name") or item.get("device_name") or ""),
                model=str(item.get("model") or ""),
                interfaces=interfaces,
            ))
        self._targets = {item.device_name: item for item in targets}
        return sorted(targets, key=lambda item: item.device_name)

    def apply_actions(
        self, actions: Sequence[SecurityAction],
    ) -> list[RuntimeActionMutation]:
        results: list[RuntimeActionMutation] = []
        for action in actions:
            self._actions[action.id] = action
            if not self._ensure_ios(action.device_name):
                results.append(RuntimeActionMutation(
                    action_id=action.id,
                    applied=False,
                    failure_code=ConfigurationFailureCode.SESSION_FAILED,
                    message="IOS did not reach OPERATIONAL_READY before E8 mutation.",
                ))
                continue
            try:
                rendered = self._renderer.render_action(action)
            except ValueError as exc:
                results.append(RuntimeActionMutation(
                    action_id=action.id,
                    applied=False,
                    failure_code=ConfigurationFailureCode.SECURITY_APPLICATION_FAILED,
                    message=str(exc),
                ))
                continue
            accepted = self._configuration.configure_ios(
                rendered.device_name, rendered.ios_payload,
            )
            results.append(RuntimeActionMutation(
                action_id=action.id,
                applied=accepted,
                failure_code=(
                    ConfigurationFailureCode.NONE if accepted
                    else ConfigurationFailureCode.SECURITY_APPLICATION_FAILED
                ),
                message=(
                    "Trusted typed security mutation accepted by Packet Tracer."
                    if accepted else "Packet Tracer rejected the typed security mutation."
                ),
                batch_id=f"{action.device_name}:{int(action.phase)}",
            ))
        return results

    def cleanup_actions(
        self, actions: Sequence[SecurityAction],
    ) -> list[RuntimeActionMutation]:
        results: list[RuntimeActionMutation] = []
        for action in actions:
            try:
                rendered = self._renderer.render_action(action)
                accepted = self._configuration.configure_ios(
                    rendered.device_name, rendered.cleanup_payload,
                )
            except ValueError as exc:
                accepted = False
                message = str(exc)
            else:
                message = (
                    "Typed E8 cleanup accepted by Packet Tracer."
                    if accepted else "Packet Tracer rejected the typed E8 cleanup."
                )
            results.append(RuntimeActionMutation(
                action_id=action.id,
                applied=accepted,
                failure_code=(
                    ConfigurationFailureCode.NONE if accepted
                    else ConfigurationFailureCode.SECURITY_CLEANUP_FAILED
                ),
                message=message,
                batch_id=f"{action.device_name}:cleanup",
            ))
        return results

    def observe(
        self, expectations: Sequence[SecurityVerificationExpectation],
    ) -> list[RuntimeSecurityVerification]:
        return [self._observe_one(item) for item in expectations]

    def verify_behavior(
        self,
        expectations: Sequence[SecurityVerificationExpectation],
        stage: SecurityVerificationStage,
    ) -> list[RuntimeSecurityVerification]:
        return [self._verify_behavior_one(item, stage) for item in expectations]

    def _observe_one(
        self, expectation: SecurityVerificationExpectation,
    ) -> RuntimeSecurityVerification:
        action = self._actions.get(expectation.action_id)
        if action is None:
            return self._unobservable(expectation, "No applied typed action is bound to this expectation.")
        if isinstance(action, AttachSecurityAcl):
            return self._observe_acl(expectation, action)
        if isinstance(action, ConfigureSecurityNat):
            return self._observe_nat(expectation, action)
        if isinstance(action, ConfigureEndpointPortSecurity):
            return self._observe_port_security(expectation, action)
        if isinstance(action, ConfigureDhcpSnooping):
            return self._observe_snooping(expectation, action)
        if isinstance(action, ConfigureDynamicArpInspection):
            return self._observe_dai(expectation, action)
        if isinstance(action, ApplyDeviceHardening):
            return self._observe_hardening(expectation, action)
        return self._unobservable(expectation, "The typed E8 action has no direct observer.")

    def _observe_acl(self, expectation, action: AttachSecurityAcl):
        acl_show = self._ios.execute(
            action.device_name, OperationalQueryId.SHOW_ACCESS_LISTS,
        )
        interface_show = self._ios.execute(
            action.device_name, OperationalQueryId.SHOW_IP_INTERFACE,
            interface=action.interface,
        )
        if not acl_show.executed or not interface_show.executed:
            return self._unobservable(
                expectation, "Fresh ACL or interface SHOW output was unavailable.",
            )
        rules = [
            item for item in parse_show_access_lists(acl_show.output)
            if item.acl_name == action.acl_name
        ]
        attachment = parse_show_ip_interface_security(interface_show.output)
        bound = bool(attachment and (
            attachment.inbound_acl if action.direction == "in"
            else attachment.outbound_acl
        ) == action.acl_name)
        matched = bool(rules and bound)
        return self._direct(
            expectation,
            matched,
            "fresh_show_access_lists_and_show_ip_interface",
            {
                "acl_rules": self._field(bool(rules)),
                "interface_attachment": self._field(bound),
            },
            "ACL rules and exact interface attachment matched."
            if matched else "ACL rules or interface attachment differed.",
            fresh=acl_show.fresh_output_observed and interface_show.fresh_output_observed,
        )

    def _observe_nat(self, expectation, action: ConfigureSecurityNat):
        show = self._ios.execute(
            action.device_name, OperationalQueryId.SHOW_IP_NAT_STATISTICS,
        )
        if not show.executed:
            return self._unobservable(expectation, "Fresh NAT statistics were unavailable.")
        state = parse_show_ip_nat_statistics(show.output)
        inside = bool(state and set(action.inside_interfaces).issubset(state.inside_interfaces))
        outside = bool(state and action.outside_interface in state.outside_interfaces)
        return self._direct(
            expectation,
            inside and outside,
            "fresh_show_ip_nat_statistics",
            {"inside_interfaces": self._field(inside), "outside_interface": self._field(outside)},
            "NAT inside/outside roles matched." if inside and outside else "NAT interface roles differed.",
            fresh=show.fresh_output_observed,
        )

    def _observe_port_security(self, expectation, action: ConfigureEndpointPortSecurity):
        show = self._ios.execute(
            action.device_name,
            OperationalQueryId.SHOW_PORT_SECURITY_INTERFACE,
            interface=action.interface,
        )
        if not show.executed:
            return self._unobservable(expectation, "Fresh port-security output was unavailable.")
        state = parse_show_port_security_interface(show.output)
        enabled = bool(state and state.enabled)
        policy = bool(state and state.maximum_macs == action.max_macs
                      and state.violation_mode == action.violation)
        sticky = bool(state and state.sticky_macs > 0)
        if enabled and policy and action.sticky and not sticky:
            return RuntimeSecurityVerification(
                expectation_id=expectation.id,
                stage=SecurityVerificationStage.DIRECT_STATE,
                status=ActionExecutionStatus.UNOBSERVABLE,
                evidence_method="fresh_show_port_security_interface",
                fresh_evidence=show.fresh_output_observed,
                fields={
                    "enabled": FieldVerificationStatus.VERIFIED,
                    "policy": FieldVerificationStatus.VERIFIED,
                    "sticky_learning": FieldVerificationStatus.UNOBSERVABLE,
                },
                message=(
                    "Port-security maximum and violation mode matched; no sticky MAC "
                    "had been learned, so sticky behavior remains unobservable."
                ),
            )
        return self._direct(
            expectation, enabled and policy, "fresh_show_port_security_interface",
            {"enabled": self._field(enabled), "policy": self._field(policy)},
            "Port-security state matched." if enabled and policy else "Port-security state differed.",
            fresh=show.fresh_output_observed,
        )

    def _observe_hardening(self, expectation, action: ApplyDeviceHardening):
        name = json.dumps(action.device_name)
        observed = self._json_result(
            "try{var d=ipc.network().getDevice(" + name + ");"
            "var be=!!(d&&typeof d.getBannerMotd==='function');"
            "var se=!!(d&&typeof d.getServicePasswordEncryption==='function');"
            "reportResult(JSON.stringify({found:!!d,banner_getter:be,"
            "banner:be?String(d.getBannerMotd()||''):'',encryption_getter:se,"
            "encryption:se?!!d.getServicePasswordEncryption():null}));}"
            "catch(e){reportResult('ERROR:'+e);}",
            5.0,
        )
        banner_observable = bool(observed.get("banner_getter"))
        encryption_observable = bool(observed.get("encryption_getter"))
        fields = {
            "banner": (
                # PT 9.0.1 returns the delimiter used by IOS as part of
                # getBannerMotd(), e.g. ``#Authorized access only#``.
                self._field(
                    str(observed.get("banner") or "")
                    == f"#{action.banner_motd}#"
                )
                if banner_observable else FieldVerificationStatus.UNOBSERVABLE
            ),
            "service_password_encryption": (
                self._field(
                    bool(observed.get("encryption"))
                    is action.service_password_encryption
                ) if encryption_observable else FieldVerificationStatus.UNOBSERVABLE
            ),
        }
        if not banner_observable or not encryption_observable:
            return RuntimeSecurityVerification(
                expectation_id=expectation.id,
                stage=SecurityVerificationStage.DIRECT_STATE,
                status=ActionExecutionStatus.UNOBSERVABLE,
                evidence_method="structured_security_getters",
                fresh_evidence=bool(observed),
                fields=fields,
                message="A required Packet Tracer hardening getter was unavailable.",
            )
        matched = all(item is FieldVerificationStatus.VERIFIED for item in fields.values())
        return self._direct(
            expectation, matched, "structured_security_getters", fields,
            "Hardening getters matched." if matched else "Hardening getters differed.",
            fresh=bool(observed),
        )

    def _observe_snooping(self, expectation, action: ConfigureDhcpSnooping):
        show = self._ios.execute(
            action.device_name, OperationalQueryId.SHOW_IP_DHCP_SNOOPING,
        )
        if not show.executed:
            return self._unobservable(expectation, "Fresh DHCP snooping output was unavailable.")
        state = parse_show_ip_dhcp_snooping(show.output)
        vlans = bool(state and set(action.vlan_ids).issubset(state.vlan_ids))
        trusted = bool(state and set(action.trusted_interfaces).issubset(
            state.trusted_interfaces,
        ))
        return self._direct(
            expectation, bool(state and state.enabled and vlans and trusted),
            "fresh_show_ip_dhcp_snooping",
            {"enabled": self._field(bool(state and state.enabled)),
             "vlans": self._field(vlans), "trusted_interfaces": self._field(trusted)},
            "DHCP snooping state matched."
            if state and state.enabled and vlans and trusted else "DHCP snooping state differed.",
            fresh=show.fresh_output_observed,
        )

    def _observe_dai(self, expectation, action: ConfigureDynamicArpInspection):
        show = self._ios.execute(
            action.device_name, OperationalQueryId.SHOW_IP_ARP_INSPECTION,
        )
        if not show.executed:
            return self._unobservable(expectation, "Fresh DAI output was unavailable.")
        state = parse_show_ip_arp_inspection(show.output)
        vlans = bool(state and set(action.vlan_ids).issubset(state.enabled_vlans))
        if vlans and action.trusted_interfaces:
            return RuntimeSecurityVerification(
                expectation_id=expectation.id,
                stage=SecurityVerificationStage.DIRECT_STATE,
                status=ActionExecutionStatus.UNOBSERVABLE,
                evidence_method="fresh_show_ip_arp_inspection_first_page",
                fresh_evidence=show.fresh_output_observed,
                fields={
                    "vlans": FieldVerificationStatus.VERIFIED,
                    "trusted_interfaces": FieldVerificationStatus.UNOBSERVABLE,
                },
                message=(
                    "DAI VLAN state matched; PT paginates before the trusted uplink "
                    "and does not accept terminal length 0."
                ),
            )
        return self._direct(
            expectation, vlans, "fresh_show_ip_arp_inspection",
            {"vlans": self._field(vlans)},
            "DAI VLAN state matched." if vlans else "DAI VLAN state differed.",
            fresh=show.fresh_output_observed,
        )

    def _verify_behavior_one(self, expectation, stage):
        if expectation.probe_kind is SecurityProbeKind.VOICE_CALL:
            if self._voice_behavior is None:
                return self._unobservable(
                    expectation,
                    "E8 has no typed E7 call operation injected; phone UI remains encapsulated.",
                    stage=stage,
                )
            return self._voice_behavior(expectation, stage)
        if expectation.probe_kind in {
            SecurityProbeKind.DNS_LOOKUP,
            SecurityProbeKind.HTTPS_FETCH,
            SecurityProbeKind.NTP_SYNC,
            SecurityProbeKind.TFTP_GET,
        }:
            if self._service_behavior is None:
                return self._unobservable(
                    expectation,
                    "E8 has no typed E6 DNS operation injected.",
                    stage=stage,
                )
            return self._service_behavior(expectation, stage)
        if expectation.probe_kind is SecurityProbeKind.HTTP_FETCH:
            reached, fresh = self._typed_http(expectation)
            return self._behavior_result(expectation, stage, reached, fresh, "typed_http_client")
        if expectation.probe_kind is SecurityProbeKind.ICMP_REACHABILITY:
            reached, fresh = self._typed_ping(expectation)
            if expectation.kind is SecurityVerificationKind.NAT_TRANSLATION and reached:
                action = self._actions.get(expectation.action_id)
                if isinstance(action, ConfigureSecurityNat):
                    translated = self._nat_translation_observed(action)
                    reached = reached and translated
                    return self._behavior_result(
                        expectation, stage, reached, fresh and translated,
                        "typed_pc_ping_plus_fresh_nat_translation",
                    )
            return self._behavior_result(expectation, stage, reached, fresh, "typed_pc_ping")
        if expectation.probe_kind is SecurityProbeKind.UNOBSERVABLE:
            return self._unobservable(
                expectation,
                "The policy protocol has no matching typed behavioral operation.",
                stage=stage,
            )
        return self._unobservable(
            expectation, "No typed behavioral adapter exists for this probe.", stage=stage,
        )

    def _typed_ping(self, expectation) -> tuple[bool, bool]:
        target = self._destination_address(expectation)
        if not target:
            return False, False
        result = self._ping.ping(expectation.source_device_name, target)
        return result.reachable, result.fresh_output_observed

    def _typed_http(self, expectation) -> tuple[bool, bool]:
        target = self._destination_address(expectation)
        if not target:
            return False, False
        client = json.dumps(expectation.source_device_name)
        key = json.dumps(expectation.id)
        started = self._json_result(
            "try{var d=ipc.network().getDevice(" + client + ");"
            "var m=d&&d.getProcess('HttpBackgroundClientManager');"
            "this.__mcpE8Http=this.__mcpE8Http||{};"
            "var p=m&&m.createClient();var before=p?String(p.getLastPageContent()):'';"
            "var started=!!(p&&p.go(" + json.dumps("http://" + target + "/") + "));"
            "if(started){this.__mcpE8Http[" + key + "]={manager:m,client:p};}"
            "else if(m&&p){m.deleteClient(p);}"
            "reportResult(JSON.stringify({started:started,before:before}));}"
            "catch(e){reportResult('ERROR:'+e);}",
            5.0,
        )
        before = str(started.get("before") or "")
        if not started.get("started"):
            return False, False

        observed = self._poll(
            lambda: self._json_result(
                "try{var b=this.__mcpE8Http||{};var s=b[" + key + "];"
                "var p=s&&s.client;reportResult(JSON.stringify({found:!!p,content:p?String(p.getLastPageContent()):''}));}"
                "catch(e){reportResult('ERROR:'+e);}",
                3.0,
            ),
            lambda item: bool(str(item.get("content") or ""))
            and str(item.get("content") or "") != before,
        )
        content = str(observed.get("content") or "")
        self._json_result(
            "try{var b=this.__mcpE8Http||{};var s=b[" + key + "];"
            "if(s&&s.manager&&s.client){s.manager.deleteClient(s.client);delete b[" + key + "]; }"
            "reportResult(JSON.stringify({released:true}));}catch(e){reportResult('ERROR:'+e);}",
            3.0,
        )
        # A completed bounded request attempt is fresh negative evidence when
        # its positive baseline succeeded immediately before policy mutation.
        return bool(content and content != before), True

    def _nat_translation_observed(self, action: ConfigureSecurityNat) -> bool:
        translations = self._ios.execute(
            action.device_name, OperationalQueryId.SHOW_IP_NAT_TRANSLATIONS,
        )
        if translations.executed and parse_show_ip_nat_translations(translations.output):
            return True
        statistics = self._ios.execute(
            action.device_name, OperationalQueryId.SHOW_IP_NAT_STATISTICS,
        )
        state = parse_show_ip_nat_statistics(statistics.output) if statistics.executed else None
        return bool(state and state.hits > 0)

    def _destination_address(self, expectation) -> str:
        try:
            return str(ipaddress.ip_address(expectation.destination_address))
        except ValueError:
            pass
        if not expectation.destination_device_name:
            return ""
        name = json.dumps(expectation.destination_device_name)
        observed = self._json_result(
            "try{var d=ipc.network().getDevice(" + name + ");var ip='';"
            "if(d){for(var i=0;i<d.getPortCount();i++){var p=d.getPortAt(i);"
            "try{var v=String(p.getIpAddress()||'');if(v&&v!=='0.0.0.0'){ip=v;break;}}"
            "catch(e){}}}reportResult(JSON.stringify({found:!!d,address:ip}));}"
            "catch(e){reportResult('ERROR:'+e);}",
            5.0,
        )
        try:
            return str(ipaddress.ip_address(str(observed.get("address") or "")))
        except ValueError:
            return ""

    def _ensure_ios(self, device_name: str) -> bool:
        if device_name in self._ready_ios_devices:
            return True
        ready = self._ios_readiness(device_name)
        if ready:
            self._ready_ios_devices.add(device_name)
        return ready

    def _wait_for_ios(self, device_name: str) -> bool:
        return self._ios.wait_until_ready(device_name).state.value == "operational_ready"

    def _poll(self, inspect: Callable[[], dict], predicate: Callable[[dict], bool]) -> dict:
        deadline = self._clock() + self._behavior_timeout
        last: dict = {}
        while True:
            last = inspect()
            if predicate(last) or self._clock() >= deadline:
                return last
            self._sleep(self._interval)

    def _json_result(self, script: str, timeout: float) -> dict:
        raw = self._send_and_wait(script, timeout)
        if raw is None or raw.startswith(("ERROR:", "PT_ERROR:")):
            return {}
        try:
            value = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return {}
        return value if isinstance(value, dict) else {}

    @staticmethod
    def _field(matches: bool) -> FieldVerificationStatus:
        return FieldVerificationStatus.VERIFIED if matches else FieldVerificationStatus.FAILED

    @staticmethod
    def _direct(expectation, matched, method, fields, message, *, fresh):
        return RuntimeSecurityVerification(
            expectation_id=expectation.id,
            stage=SecurityVerificationStage.DIRECT_STATE,
            status=ActionExecutionStatus.VERIFIED if matched else ActionExecutionStatus.FAILED,
            evidence_method=method,
            fresh_evidence=fresh,
            fields=fields,
            message=message,
        )

    @staticmethod
    def _behavior_result(expectation, stage, reached, fresh, method):
        expected_reachability = (
            True if stage in {
                SecurityVerificationStage.BASELINE,
                SecurityVerificationStage.CLEANUP_RECOVERY,
            } else expectation.expected_decision is SecurityDecision.ALLOW
        )
        matched = fresh and reached is expected_reachability
        return RuntimeSecurityVerification(
            expectation_id=expectation.id,
            stage=stage,
            status=ActionExecutionStatus.VERIFIED if matched else ActionExecutionStatus.FAILED,
            evidence_method=method,
            fresh_evidence=fresh,
            fields={"traffic_outcome": (
                FieldVerificationStatus.VERIFIED if matched
                else FieldVerificationStatus.FAILED
            )},
            message=(
                "Fresh traffic behavior matched the security decision."
                if matched else "Fresh traffic behavior did not match the security decision."
            ),
        )

    @staticmethod
    def _unobservable(expectation, message, *, stage=SecurityVerificationStage.DIRECT_STATE):
        return RuntimeSecurityVerification(
            expectation_id=expectation.id,
            stage=stage,
            status=ActionExecutionStatus.UNOBSERVABLE,
            evidence_method="packet_tracer_runtime_limitation",
            fresh_evidence=False,
            fields={"state": FieldVerificationStatus.UNOBSERVABLE},
            message=message,
        )
