"""Adapter Packet Tracer para aplicar y observar ServicePlan E6."""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Sequence
from time import monotonic, sleep

from ...domain.enterprise.models.configuration_runtime import (
    ActionExecutionStatus,
    ConfigurationFailureCode,
    RuntimeActionMutation,
    RuntimeConfigurationTarget,
)
from ...domain.enterprise.models.service_plan import (
    AddDnsRecord,
    ConfigureNtpService,
    EnableDnsService,
    EnableHttpService,
    EnableHttpsService,
    EnableTftpService,
    PublishTftpFile,
    ServiceAction,
    ServiceEvidenceKind,
    ServiceType,
    ServiceVerificationExpectation,
    ServiceVerificationKind,
    SetHttpContent,
)
from ...domain.enterprise.models.service_runtime import RuntimeServiceVerification
from .command_dispatch import PAGER_GUARD_JS
from .runtime_inventory import normalize_runtime_inventory


_HOSTNAME = re.compile(
    r"(?=^.{1,253}$)(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)*"
    r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?$"
)


class PacketTracerEnterpriseServiceRuntime:
    """Usa procesos documentados de PT; no ofrece JS ni comandos arbitrarios."""

    def __init__(
        self,
        query_inventory: Callable[[], list[dict] | dict],
        send_and_wait: Callable[[str, float], str | None],
        *,
        dns_timeout_seconds: float = 5.0,
        http_timeout_seconds: float = 8.0,
        convergence_interval_seconds: float = 0.25,
        clock: Callable[[], float] = monotonic,
        sleeper: Callable[[float], None] = sleep,
    ) -> None:
        self._query_inventory = query_inventory
        self._send_and_wait = send_and_wait
        self._dns_timeout = dns_timeout_seconds
        self._http_timeout = http_timeout_seconds
        self._interval = convergence_interval_seconds
        self._clock = clock
        self._sleep = sleeper

    def inventory(self) -> list[RuntimeConfigurationTarget]:
        return normalize_runtime_inventory(self._query_inventory())

    def apply_actions(
        self, actions: Sequence[ServiceAction],
    ) -> list[RuntimeActionMutation]:
        if not actions:
            return []
        host_names = {item.host_device_name for item in actions}
        if len(host_names) != 1:
            return [RuntimeActionMutation(
                action_id=item.id,
                applied=False,
                failure_code=ConfigurationFailureCode.APPLICATION_FAILED,
                message="A service runtime batch must target exactly one host.",
            ) for item in actions]
        host = json.dumps(next(iter(host_names)))
        lines = [
            f"var d=ipc.network().getDevice({host});var results=[];",
            "if(!d){reportResult(JSON.stringify({results:[]}));}else{",
        ]
        for action in actions:
            lines.extend(self._mutation_lines(action))
        lines.append("reportResult(JSON.stringify({results:results}));}")
        payload = self._json_result("".join(lines), 10.0)
        observed = {
            str(item.get("id")): item for item in payload.get("results", [])
            if isinstance(item, dict)
        }
        return [
            RuntimeActionMutation(
                action_id=action.id,
                applied=bool(observed.get(action.id, {}).get("applied")),
                failure_code=(
                    ConfigurationFailureCode.NONE
                    if observed.get(action.id, {}).get("applied")
                    else ConfigurationFailureCode.APPLICATION_FAILED
                ),
                message=str(observed.get(action.id, {}).get("message") or ""),
                batch_id=f"{action.host_device_name}:{int(action.phase)}",
            )
            for action in actions
        ]

    @staticmethod
    def _mutation_lines(action: ServiceAction) -> list[str]:
        action_id = json.dumps(action.id)
        process = {
            ServiceType.DNS: "DnsServer",
            ServiceType.HTTP: "HttpServer",
            ServiceType.HTTPS: "HttpsServer",
            ServiceType.NTP: "NtpServer",
            ServiceType.TFTP: "TftpServer",
        }[action.service_type]
        lines = [f"var p=d.getProcess({json.dumps(process)});var ok=false;"]
        if isinstance(action, EnableDnsService):
            lines.append("if(p){p.setEnable(true);ok=!!p.isEnabled();}")
        elif isinstance(action, AddDnsRecord):
            lines.append(
                "if(p){ok=!!p.addARecordToNameServerDb("
                + json.dumps(action.hostname) + "," + json.dumps(action.address)
                + ")||!!p.getARecordWithAddress(" + json.dumps(action.hostname)
                + "," + json.dumps(action.address) + ");}"
            )
        elif isinstance(action, EnableHttpService):
            lines.append("if(p){p.setEnable(true);ok=!!p.isEnabled();}")
        elif isinstance(action, SetHttpContent):
            lines.append(
                "if(p){p.setPageContents(" + json.dumps(action.path) + ","
                + json.dumps(action.content) + ");ok=String(p.getPage("
                + json.dumps(action.path) + "))===" + json.dumps(action.content) + ";}"
            )
        elif isinstance(action, EnableHttpsService):
            lines.append("if(p){p.setHttpsEnable(true);ok=!!p.isHttpsEnabled();}")
        elif isinstance(action, ConfigureNtpService):
            lines.append("if(p){p.setEnabled(true);ok=!!p.isEnabled();}")
        elif isinstance(action, EnableTftpService):
            lines.append("if(p){p.setEnabled(true);ok=!!p.isEnabled();}")
        elif isinstance(action, PublishTftpFile):
            lines.append("ok=false;")
        lines.append(
            "results.push({id:" + action_id
            + ",applied:ok,message:ok?'applied':'service API mutation/readback failed'});"
        )
        return lines

    def verify(
        self, expectation: ServiceVerificationExpectation,
    ) -> RuntimeServiceVerification:
        if expectation.evidence_kind is ServiceEvidenceKind.DIRECT_STATE:
            return self._verify_direct(expectation)
        if expectation.kind in {
            ServiceVerificationKind.DNS_RESOLUTION,
            ServiceVerificationKind.DNS_NEGATIVE_CONTROL,
        }:
            return self._verify_dns(expectation)
        if expectation.kind in {
            ServiceVerificationKind.HTTP_FETCH,
            ServiceVerificationKind.HTTPS_FETCH,
            ServiceVerificationKind.HTTP_BY_HOSTNAME,
        }:
            return self._verify_http(expectation)
        return RuntimeServiceVerification(
            expectation_id=expectation.id,
            status=ActionExecutionStatus.UNOBSERVABLE,
            evidence_kind=expectation.evidence_kind,
            evidence_method="packet_tracer_client_observation_unavailable",
            fresh_evidence=False,
            message="Packet Tracer exposes no registered independent client proof for this service.",
        )

    def _verify_direct(self, expectation):
        service_type = ServiceType(str(expectation.expected.get("service_type")))
        process = {
            ServiceType.DNS: "DnsServer",
            ServiceType.HTTP: "HttpServer",
            ServiceType.HTTPS: "HttpsServer",
            ServiceType.NTP: "NtpServer",
            ServiceType.TFTP: "TftpServer",
        }[service_type]
        host = json.dumps(expectation.host_device_name)
        lines = [
            f"var d=ipc.network().getDevice({host});var p=d&&d.getProcess({json.dumps(process)});",
            "var out={found:!!p,enabled:false};if(p){",
        ]
        if service_type is ServiceType.HTTPS:
            lines.append("out.enabled=!!p.isHttpsEnabled();")
        else:
            lines.append("out.enabled=!!p.isEnabled();")
        if service_type is ServiceType.DNS:
            records = str(expectation.expected.get("records_json") or "{}")
            lines.append(
                "out.records={};var wanted=JSON.parse(" + json.dumps(records) + ");"
                "for(var k in wanted){if(p.getARecordWithAddress(k,wanted[k])){"
                "out.records[k]=wanted[k];}}"
            )
        elif service_type in {ServiceType.HTTP, ServiceType.HTTPS}:
            lines.append("out.content=String(p.getPage('index.html'));")
        lines.append("}reportResult(JSON.stringify(out));")
        observed = self._json_result("".join(lines), 5.0)
        enabled = bool(observed.get("found") and observed.get("enabled"))
        matches = enabled
        if service_type is ServiceType.DNS:
            expected_records = json.loads(str(expectation.expected.get("records_json") or "{}"))
            matches = matches and observed.get("records") == expected_records
        elif service_type in {ServiceType.HTTP, ServiceType.HTTPS}:
            marker = str(expectation.expected.get("marker") or "")
            matches = matches and (not marker or marker in str(observed.get("content") or ""))
        return RuntimeServiceVerification(
            expectation_id=expectation.id,
            status=(ActionExecutionStatus.VERIFIED if matches else ActionExecutionStatus.FAILED),
            evidence_kind=expectation.evidence_kind,
            evidence_method="structured_service_getters",
            fresh_evidence=bool(observed),
            observed={"enabled": enabled},
            message="Structured service state matched." if matches else "Structured service state differed.",
        )

    def _verify_dns(self, expectation):
        hostname = str(expectation.expected.get("hostname") or "")
        if not _HOSTNAME.fullmatch(hostname):
            return self._behavior_failure(expectation, "DNS verification hostname is invalid.")
        client = json.dumps(expectation.client_device_name)
        command = "ping " + hostname
        command_json = json.dumps(command)
        start = self._json_result(
            f"var d=ipc.network().getDevice({client});"
            "var cp=d&&typeof d.getCommandPrompt==='function'?d.getCommandPrompt():null;"
            "var before=cp&&typeof cp.getOutput==='function'?String(cp.getOutput()):'';"
            + PAGER_GUARD_JS +
            # Misma frontera que el resto: tipear sobre un pager activo se come
            # el primer caracter del comando.
            "var started=false;var blocked=false;"
            "if(__pager){blocked=true;}"
            "else if(cp&&typeof cp.enterCommand==='function'){"
            f"cp.enterCommand({command_json});started=true;}}"
            "reportResult(JSON.stringify({started:started,blocked:blocked,before:before}));",
            5.0,
        )
        if start.get("blocked"):
            return self._behavior_failure(
                expectation, "Typed DNS ping was refused: the terminal pager was active.",
            )
        if not start.get("started"):
            return self._behavior_failure(expectation, "Typed DNS ping did not start.")
        before = str(start.get("before") or "")

        def inspect():
            return self._json_result(
                f"var d=ipc.network().getDevice({client});"
                "var cp=d&&typeof d.getCommandPrompt==='function'?d.getCommandPrompt():null;"
                "reportResult(JSON.stringify({found:!!cp,output:cp?String(cp.getOutput()):''}));",
                3.0,
            )
        negative = expectation.kind is ServiceVerificationKind.DNS_NEGATIVE_CONTROL
        expected = str(expectation.expected.get("address") or "")
        observed = self._poll(
            inspect,
            lambda item: self._dns_window_complete(
                self._fresh_command_window(
                    before, str(item.get("output") or ""), command,
                ),
                expected,
                negative,
            ),
            self._dns_timeout,
        )
        window = self._fresh_command_window(
            before, str(observed.get("output") or ""), command,
        )
        not_found = bool(re.search(r"could not find host|unknown host", window, re.I))
        if negative:
            matched = bool(window and not_found)
            method = "typed_pc_ping_hostname_negative_control"
        else:
            matched = bool(
                window and not not_found and expected in window
                and "packets: sent" in window.casefold()
            )
            method = "typed_pc_ping_hostname_fresh_output"
        return RuntimeServiceVerification(
            expectation_id=expectation.id,
            status=(ActionExecutionStatus.VERIFIED if matched else ActionExecutionStatus.FAILED),
            evidence_kind=expectation.evidence_kind,
            evidence_method=method,
            fresh_evidence=matched,
            observed=(
                {"hostname": hostname, "resolved": False}
                if matched and negative
                else {"hostname": hostname, "address": expected} if matched else {}
            ),
            message=(
                "DNS negative control did not resolve."
                if matched and negative
                else "DNS resolved expected address." if matched
                else "Fresh DNS command output did not match the expectation."
            ),
        )

    @staticmethod
    def _fresh_command_window(before: str, after: str, command: str) -> str:
        if after.startswith(before) and len(after) > len(before):
            return after[len(before):]
        index = after.casefold().rfind(command.casefold())
        return after[index:] if index >= 0 and after[index:] != before[index:] else ""

    @staticmethod
    def _dns_window_complete(window: str, expected: str, negative: bool) -> bool:
        if re.search(r"could not find host|unknown host", window, re.I):
            return True
        if negative:
            return "packets: sent" in window.casefold()
        return expected in window and "packets: sent" in window.casefold()

    def _verify_http(self, expectation):
        marker = str(expectation.expected.get("marker") or "")
        target = str(
            expectation.expected.get("hostname")
            or expectation.expected.get("address") or ""
        )
        scheme = str(expectation.expected.get("scheme") or "http").casefold()
        if scheme not in {"http", "https"}:
            return self._behavior_failure(
                expectation, "Web verification scheme is not registered.",
            )
        client = json.dumps(expectation.client_device_name)
        url = json.dumps(scheme + "://" + target + "/")
        start = self._json_result(
            f"var d=ipc.network().getDevice({client});"
            + self._background_http_start(expectation.id, url)
            + "var before=content_before;"
            "reportResult(JSON.stringify({started:started,content_before:before}));",
            5.0,
        )
        before = str(start.get("content_before") or "")
        if not start.get("started"):
            return self._behavior_failure(expectation, "HTTP client request did not start.")
        if marker and marker in before:
            self._release_background_http(expectation.id, client)
            return self._behavior_failure(
                expectation, "Expected marker already existed before the current request.",
            )

        def inspect():
            return self._json_result(
                self._background_http_inspect(expectation.id),
                3.0,
            )
        observed = self._poll(
            inspect,
            lambda item: bool(
                (content := str(item.get("content") or ""))
                and content != before
                and (not marker or marker in content)
            ),
            self._http_timeout,
        )
        content = str(observed.get("content") or "")
        matched = bool(
            content and content != before and (not marker or marker in content)
        )
        self._release_background_http(expectation.id, client)
        return RuntimeServiceVerification(
            expectation_id=expectation.id,
            status=(ActionExecutionStatus.VERIFIED if matched else ActionExecutionStatus.FAILED),
            evidence_kind=expectation.evidence_kind,
            evidence_method=f"{scheme}_client_fresh_content",
            fresh_evidence=matched,
            observed={"marker": marker, "target": target, "scheme": scheme} if matched else {},
            message=(
                f"Fresh {scheme.upper()} content matched the expectation."
                if matched else f"Fresh {scheme.upper()} content was not observed."
            ),
        )

    @staticmethod
    def _background_http_start(expectation_id: str, url_json: str) -> str:
        key = json.dumps(expectation_id)
        return (
            "var m=d&&d.getProcess(\"HttpBackgroundClientManager\");"
            "this.__mcpE6HttpClients=this.__mcpE6HttpClients||{};"
            f"var old=this.__mcpE6HttpClients[{key}];"
            "if(old&&old.manager&&old.client){old.manager.deleteClient(old.client);}"
            "var p=m&&m.createClient();var content_before=p?String(p.getLastPageContent()):'';"
            f"var started=!!(p&&p.go({url_json}));"
            f"if(started){{this.__mcpE6HttpClients[{key}]={{manager:m,client:p}};}}"
            "else if(m&&p){m.deleteClient(p);}"
        )

    @staticmethod
    def _background_http_inspect(expectation_id: str) -> str:
        key = json.dumps(expectation_id)
        return (
            "var bag=this.__mcpE6HttpClients||{};"
            f"var slot=bag[{key}];var p=slot&&slot.client;"
            "reportResult(JSON.stringify({found:!!p,content:p?String(p.getLastPageContent()):''}));"
        )

    def _release_background_http(self, expectation_id: str, client_json: str) -> None:
        key = json.dumps(expectation_id)
        self._json_result(
            f"var d=ipc.network().getDevice({client_json});"
            "var bag=this.__mcpE6HttpClients||{};"
            f"var slot=bag[{key}];if(slot&&slot.manager&&slot.client){{"
            "slot.manager.deleteClient(slot.client);"
            f"delete bag[{key}];}}"
            "reportResult(JSON.stringify({released:!slot||!bag["
            + key + "]}));",
            3.0,
        )

    def _poll(self, inspect, predicate, timeout):
        deadline = self._clock() + timeout
        last = {}
        while True:
            last = inspect()
            if predicate(last) or self._clock() >= deadline:
                return last
            self._sleep(self._interval)

    @staticmethod
    def _behavior_failure(expectation, message):
        return RuntimeServiceVerification(
            expectation_id=expectation.id,
            status=ActionExecutionStatus.FAILED,
            evidence_kind=expectation.evidence_kind,
            evidence_method="typed_client_operation",
            fresh_evidence=False,
            message=message,
        )

    def _json_result(self, js: str, timeout: float) -> dict:
        raw = self._send_and_wait(js, timeout)
        if raw is None or raw.startswith(("ERROR:", "PT_ERROR:")):
            return {}
        try:
            value = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return {}
        return value if isinstance(value, dict) else {}
