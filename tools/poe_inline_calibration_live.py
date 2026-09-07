"""POE-1: governed live calibration of `show power inline` as a PSE observable.

What this measures, and why it is a measurement and not a claim:
The only authorized PoE delivery evidence today is a human looking at a phone
(`manual_visible_power_state`). It does not scale to one more port, so the
governed state recorded the remaining switch-side candidate. This harness runs
ONE causal sequence on ONE exact binding and records what Packet Tracer
actually prints:

    A. power inline auto   -> capture
    B. power inline never  -> capture
    C. power inline auto   -> capture

Nothing here parses the table into a verdict. The point of the run is to obtain
the exact text this build emits, so that a parser can later be written against
measured bytes instead of against a remembered IOS layout. Registering a parsed
shape first would be asserting a guessed form -- and PT answers a command it
does not understand with text that parses anyway.

The caller supplies no IOS and no JavaScript. Both the three mode mutations and
the read-backs come from closed registries: `PoEInlineMode` below, and
`IosQualificationQueryId` / `OperationalQueryId` in the governed executor.

Safety envelope, all of it fail-closed:
  * import isolation proven in THIS process before Packet Tracer is touched;
  * exact build, Realtime, and an empty semantic inventory required up front;
  * the fixture is disposable, created by this run and deleted by it;
  * `power inline auto` is restored and PROVEN by read-back, not assumed;
  * inventory must return to its opening fingerprint or the run reports dirty;
  * evidence is persisted with its own SHA-256.

Run:
    .venv/Scripts/python.exe tools/poe_inline_calibration_live.py --execute
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from secrets import token_hex

from packet_tracer_mcp.infrastructure.execution.file_bridge import FileBridge
from packet_tracer_mcp.infrastructure.execution.import_isolation_preflight import (
    ImportIsolationPreflight,
)
from packet_tracer_mcp.infrastructure.execution.ios_terminal import (
    ControlledIosExecutor,
    IosQualificationQueryId,
    OperationalQueryId,
)
from packet_tracer_mcp.infrastructure.execution.poe_delivery_runtime import (
    PacketTracerPoEDeliveryFixtureRuntime,
)
from packet_tracer_mcp.infrastructure.execution.configuration_runtime import (
    PacketTracerConfigurationRuntime,
)

REQUIRED_BUILD = "9.0.1.0858"
CANDIDATE_MODEL = "3560-24PS"
ENDPOINT_MODEL = "7960"
SWITCH_PORT = "FastEthernet0/1"
ENDPOINT_PORT = "Switch"

# El motor tarda en reflejar un cambio de PoE. La cota es dura y la estabilidad
# se PRUEBA -- dos capturas idénticas separadas en el tiempo -- en vez de
# suponerse a partir de un sleep que "seguro alcanzó".
_SETTLE_SECONDS = 6.0
_STABILITY_GAP_SECONDS = 2.0
_BOOT_TIMEOUT_SECONDS = 150.0

_EVIDENCE_DIR = Path("docs/reference/cp-scale/canonical-live-evidence")


class PoEInlineMode(str, Enum):
    """Los únicos modos que este arnés sabe pedir. El caller no aporta IOS."""

    AUTO = "auto"
    NEVER = "never"


def _payload(interface: str, mode: PoEInlineMode) -> str:
    """Construye el payload IOS internamente, desde el enum cerrado.

    Sin `write memory`: el dispositivo es desechable y se borra al final, así
    que escribir NVRAM sería una mutación extra sin lector.
    """
    return "\n".join((
        "enable",
        "configure terminal",
        f"interface {interface}",
        f" power inline {mode.value}",
        " exit",
        "end",
    ))


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


@dataclass
class Capture:
    """Una lectura del candidato, con TODO lo que la hace atribuible o no."""

    label: str
    captured_at: str
    executed: bool
    output: str
    stable_repeat_output: str
    stable: bool
    fresh_output_observed: bool
    output_complete: bool
    truncated_by_pager: bool
    pager_continuation: str
    dispatch_classification: str
    echo_observed: str
    device_identity_provenance: str
    device_identity_evidence: str
    observed_device_name: str
    session_state: str
    failure_reason: str
    duration_ms: int
    interface_brief: str = ""
    port_up_switch: object = None
    port_up_endpoint: object = None

    @property
    def attributable(self) -> bool:
        """Fresca, completa, sin pager y atribuida a un único dispositivo."""
        return (
            self.executed
            and self.fresh_output_observed
            and self.output_complete
            and not self.truncated_by_pager
            and self.device_identity_provenance == "confirmed_unique"
        )


@dataclass
class Report:
    run_id: str
    started_at: str
    facts: dict = field(default_factory=dict)
    captures: list[Capture] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)

    def fail(self, reason: str) -> None:
        self.problems.append(reason)


_PORT_STATE_JS_TEMPLATE = (
    "try{{var net=ipc.network();"
    "var sd=net.getDevice({switch_name});var ed=net.getDevice({endpoint_name});"
    "var sp=sd?sd.getPort({switch_port}):null;"
    "var ep=ed?ed.getPort({endpoint_port}):null;"
    "function up(p){{try{{return (typeof p.isPortUp==='function')?p.isPortUp():null;}}"
    "catch(e){{return null;}}}}"
    "reportResult(JSON.stringify({{"
    "switch_present:(sd?true:false),endpoint_present:(ed?true:false),"
    "switch_port_up:(sp?up(sp):null),endpoint_port_up:(ep?up(ep):null),"
    "linked:(sp?(sp.getLink()!=null):false)}}));"
    "}}catch(e){{reportResult('ERROR:'+e);}}"
)

_ENV_JS = (
    "try{var a=ipc.appWindow();var f=a.getActiveFile();var s=ipc.simulation();"
    "var net=ipc.network();"
    "reportResult(JSON.stringify({"
    "found:(f?true:false),"
    "saved_filename:(f?String(f.getSavedFilename()||''):''),"
    "pt_version:(f?String(f.getVersion()||''):''),"
    "simulation_mode:(typeof s.isSimulationMode==='function'?s.isSimulationMode():null),"
    "devices:net.getDeviceCount(),links:net.getLinkCount()"
    "}));}catch(e){reportResult('ERROR:'+e);}"
)


class Calibration:
    def __init__(self, bridge: FileBridge, report: Report) -> None:
        self._bridge = bridge
        self._report = report
        self._executor = ControlledIosExecutor(bridge.send_and_wait)
        self._fixture = PacketTracerPoEDeliveryFixtureRuntime(
            bridge.send_and_wait, REQUIRED_BUILD,
        )
        self._config = PacketTracerConfigurationRuntime(bridge.send)
        self._switch_name = f"MCP-POE1-SW-{report.run_id}"
        self._endpoint_name = f"MCP-POE1-PH-{report.run_id}"

    # -- lectura de entorno -------------------------------------------

    def environment(self) -> dict:
        raw = self._bridge.send_and_wait(_ENV_JS, 15.0)
        if raw is None or raw.startswith("ERROR:"):
            raise RuntimeError(f"environment read failed: {raw}")
        return json.loads(raw)

    def port_state(self) -> dict:
        script = _PORT_STATE_JS_TEMPLATE.format(
            switch_name=json.dumps(self._switch_name),
            endpoint_name=json.dumps(self._endpoint_name),
            switch_port=json.dumps(SWITCH_PORT),
            endpoint_port=json.dumps(ENDPOINT_PORT),
        )
        raw = self._bridge.send_and_wait(script, 15.0)
        if raw is None or raw.startswith("ERROR:"):
            return {"error": raw}
        return json.loads(raw)

    # -- fixture -------------------------------------------------------

    def build_fixture(self) -> dict:
        switch = self._fixture.create_device(
            CANDIDATE_MODEL, self._switch_name, (SWITCH_PORT,), arm="candidate",
        )
        endpoint = self._fixture.create_device(
            ENDPOINT_MODEL, self._endpoint_name, (ENDPOINT_PORT,), arm="candidate",
        )
        link = self._fixture.create_link(
            switch, SWITCH_PORT, endpoint, ENDPOINT_PORT,
        )
        return {
            "switch": switch.model_dump(mode="json"),
            "endpoint": endpoint.model_dump(mode="json"),
            "link": link.model_dump(mode="json"),
        }

    def teardown(self) -> dict:
        return {
            "endpoint_deleted": self._fixture.delete_device(self._endpoint_name),
            "switch_deleted": self._fixture.delete_device(self._switch_name),
        }

    def inventory_fingerprint(self) -> str:
        return self._fixture.inventory_fingerprint()

    # -- la secuencia causal -------------------------------------------

    def apply_mode(self, mode: PoEInlineMode) -> bool:
        return self._config.configure_ios(
            self._switch_name, _payload(SWITCH_PORT, mode),
        )

    def capture(self, label: str) -> Capture:
        """Una captura del candidato, con estabilidad PROBADA por repetición."""
        first = self._executor.qualify(
            self._switch_name, IosQualificationQueryId.SHOW_POWER_INLINE,
        )
        time.sleep(_STABILITY_GAP_SECONDS)
        second = self._executor.qualify(
            self._switch_name, IosQualificationQueryId.SHOW_POWER_INLINE,
        )
        brief = self._executor.execute(
            self._switch_name, OperationalQueryId.SHOW_IP_INTERFACE_BRIEF,
        )
        ports = self.port_state()
        return Capture(
            label=label,
            captured_at=_utc_now(),
            executed=first.executed,
            output=first.output,
            stable_repeat_output=second.output,
            stable=first.executed and second.executed
            and first.output == second.output,
            fresh_output_observed=first.fresh_output_observed,
            output_complete=first.output_complete,
            truncated_by_pager=first.truncated_by_pager,
            pager_continuation=first.pager_continuation,
            dispatch_classification=first.dispatch_classification,
            echo_observed=first.echo_observed,
            device_identity_provenance=first.device_identity_provenance,
            device_identity_evidence=first.device_identity_evidence,
            observed_device_name=first.observed_device_name,
            session_state=first.session_state.value,
            failure_reason=first.failure_reason,
            duration_ms=first.duration_ms,
            interface_brief=brief.output if brief.executed else "",
            port_up_switch=ports.get("switch_port_up"),
            port_up_endpoint=ports.get("endpoint_port_up"),
        )

    def wait_until_ready(self):
        return self._executor.wait_until_ready(
            self._switch_name, timeout_seconds=_BOOT_TIMEOUT_SECONDS,
        )


def _persist(report: Report, root: Path) -> dict:
    payload = {
        "schema": "poe-inline-calibration-v1",
        "run_id": report.run_id,
        "started_at": report.started_at,
        "finished_at": _utc_now(),
        "packet_tracer_build": REQUIRED_BUILD,
        "candidate_command": ControlledIosExecutor.qualification_command(
            IosQualificationQueryId.SHOW_POWER_INLINE,
        ),
        "binding": {
            "candidate_model": CANDIDATE_MODEL,
            "switch_port": SWITCH_PORT,
            "endpoint_model": ENDPOINT_MODEL,
            "endpoint_port": ENDPOINT_PORT,
            "external_phone_power_adapter": False,
        },
        "facts": report.facts,
        "captures": [
            {
                **{
                    key: value
                    for key, value in vars(capture).items()
                },
                "attributable": capture.attributable,
            }
            for capture in report.captures
        ],
        "problems": report.problems,
        "claim_authority": {
            "authorized_observation_methods_unchanged": True,
            "poe_ports_extrapolated": False,
            "promotes_candidate_to_product_registry": False,
        },
    }
    directory = root / _EVIDENCE_DIR
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"poe-inline-calibration-{report.run_id}.json"
    body = json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True)
    path.write_text(body + "\n", encoding="utf-8")
    digest = hashlib.sha256(body.encode("utf-8") + b"\n").hexdigest()
    return {"path": str(path.relative_to(root)).replace("\\", "/"), "sha256": digest}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Perform the governed live calibration. Without it, nothing runs.",
    )
    args = parser.parse_args(argv)
    if not args.execute:
        print("Refusing to touch Packet Tracer without --execute.")
        return 1

    root = Path(__file__).resolve().parents[1]
    isolation = ImportIsolationPreflight(governed_root=root).ensure_isolated()
    print("== IMPORT ISOLATION ==")
    print(isolation.render())
    if not isolation.isolated:
        print("Import isolation failed - refusing to touch Packet Tracer.")
        return 2

    report = Report(run_id=f"poe1-{token_hex(4)}", started_at=_utc_now())
    bridge = FileBridge()
    if not bridge.pt_alive():
        print("Script Engine heartbeat is stale - refusing.")
        return 3

    calibration = Calibration(bridge, report)

    env = calibration.environment()
    print("== ENVIRONMENT ==")
    print(json.dumps(env, indent=2))
    report.facts["environment_before"] = env
    if env.get("pt_version") != REQUIRED_BUILD:
        print(f"Build is not {REQUIRED_BUILD} - refusing.")
        return 4
    if env.get("simulation_mode") is not False:
        print("Packet Tracer is not in Realtime - refusing.")
        return 5
    if env.get("devices") != 0 or env.get("links") != 0:
        print("Semantic inventory is not empty - refusing.")
        return 6

    opening_fingerprint = calibration.inventory_fingerprint()
    report.facts["inventory_fingerprint_before"] = opening_fingerprint

    try:
        print("\n== FIXTURE ==")
        report.facts["fixture"] = calibration.build_fixture()
        print(json.dumps(report.facts["fixture"], indent=2))

        print("\n== IOS BOOT ==")
        boot = calibration.wait_until_ready()
        report.facts["boot"] = boot.model_dump(mode="json")
        print(json.dumps(report.facts["boot"], indent=2))

        report.captures.append(calibration.capture("as_created"))

        for label, mode in (
            ("auto_1", PoEInlineMode.AUTO),
            ("never", PoEInlineMode.NEVER),
            ("auto_2", PoEInlineMode.AUTO),
        ):
            print(f"\n== {label.upper()}: power inline {mode.value} ==")
            queued = calibration.apply_mode(mode)
            if not queued:
                report.fail(f"{label}: mutation was not even queued")
            time.sleep(_SETTLE_SECONDS)
            capture = calibration.capture(label)
            report.captures.append(capture)
            print(f"attributable={capture.attributable} stable={capture.stable}")
            print(capture.output)
    finally:
        print("\n== TEARDOWN ==")
        try:
            report.facts["teardown"] = calibration.teardown()
        except Exception as exc:  # noqa: BLE001 - se reporta, no se traga
            report.facts["teardown"] = {"error": str(exc)}
            report.fail(f"teardown raised: {exc}")
        closing = calibration.inventory_fingerprint()
        report.facts["inventory_fingerprint_after"] = closing
        report.facts["inventory_restored"] = closing == opening_fingerprint
        if closing != opening_fingerprint:
            report.fail("inventory did not return to its opening fingerprint")
        env_after = calibration.environment()
        report.facts["environment_after"] = env_after
        report.facts["realtime_restored"] = env_after.get("simulation_mode") is False
        artifact = _persist(report, root)
        report.facts["artifact"] = artifact
        print(json.dumps(report.facts["teardown"], indent=2))
        print("inventory restored:", report.facts["inventory_restored"])
        print("realtime restored:", report.facts["realtime_restored"])
        print("artifact:", artifact)
        print("problems:", report.problems or "none")

    return 0 if not report.problems else 7


if __name__ == "__main__":
    raise SystemExit(main())
