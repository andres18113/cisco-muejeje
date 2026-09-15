"""Governed CLI for the minimum disposable native-UI call qualification."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from pathlib import Path

import packet_tracer_mcp

from ...application.use_cases.apply_voice import VoiceApplicator
from ...application.use_cases.qualify_call_observability import (
    QUALIFICATION_SCOPE,
    CallObservabilityQualification,
    CallObservabilityQualificationStatus,
)
from ...application.use_cases.qualify_cp_scale_live import (
    EXPECTED_BRANCH,
    EXPECTED_UPSTREAM,
)
from ...domain.enterprise.models.voice_runtime import PhoneExecutionMethod
from ...infrastructure.execution.cp_scale_live_preflight import (
    GitCPScaleRepositoryReader,
    PacketTracerImportIsolationReader,
    PowerShellPacketTracerProcessReader,
    PythonRuntimeEvidenceReader,
)
from ...infrastructure.execution.enterprise_configuration_runtime import (
    PacketTracerEnterpriseConfigurationRuntime,
)
from ...infrastructure.execution.enterprise_voice_runtime import (
    PacketTracerEnterpriseVoiceRuntime,
)
from ...infrastructure.execution.import_isolation_preflight import (
    GOVERNED_ROOT_ENV_VAR,
    governed_root_from_env,
)
from ...infrastructure.execution.live_bridge import PacketTracerHttpTransport
from ...infrastructure.execution.live_environment_preflight import (
    packet_tracer_process_error,
)
from ...infrastructure.execution.native_ui_phone_driver import (
    NATIVE_UI_PROVIDER_ID,
    PacketTracerNativeUiCallDriver,
)
from ...infrastructure.execution.packet_tracer_physical_runtime import (
    PacketTracerPhysicalTopologyRuntime,
)
from ...infrastructure.execution.phone_control import (
    PacketTracerNativeUiPhoneControlAdapter,
)
from ...infrastructure.execution.simulation_trace_runtime import (
    SimulationTraceRuntime,
)
from ...shared.utils import resolve_within, safe_name_component


_ENVIRONMENT_JS = (
    "try{var a=ipc.appWindow();var f=a.getActiveFile();var s=ipc.simulation();"
    "var net=ipc.network();reportResult(JSON.stringify({"
    "found:(f?true:false),saved_filename:(f?String(f.getSavedFilename()||''):''),"
    "pt_version:(f?String(f.getVersion()||''):''),"
    "simulation_mode:(typeof s.isSimulationMode==='function'?s.isSimulationMode():null),"
    "devices:net.getDeviceCount(),links:net.getLinkCount()}));}"
    "catch(e){reportResult('ERROR:'+e);}"
)


def _inventory(physical) -> list[dict[str, object]]:
    observed = physical.observe_workspace()
    if not observed.observed:
        raise RuntimeError("Packet Tracer workspace inventory became unobservable.")
    return [
        {"name": item.name, "model": item.model, "ports": list(item.ports)}
        for item in observed.semantic_devices
    ]


def _environment(transport) -> dict[str, object]:
    raw = transport.send_and_wait(_ENVIRONMENT_JS, 15.0)
    if raw is None or raw.startswith(("ERROR:", "PT_ERROR:")):
        raise RuntimeError("Packet Tracer environment observation failed: " + str(raw))
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise RuntimeError("Packet Tracer environment observation was not an object.")
    return value


def _environment_error(value: dict[str, object], version: str) -> str:
    expected = {
        "found": True,
        "saved_filename": "",
        "pt_version": version,
        "simulation_mode": False,
        "links": 0,
    }
    observed = {key: value.get(key) for key in expected}
    devices = value.get("devices")
    coherent_devices = type(devices) is int and devices >= 0
    return "" if observed == expected and coherent_devices else (
        "Packet Tracer environment is not the exact empty unsaved Realtime "
        f"qualification baseline: {value!r}."
    )


def _mailbox_entries(path: Path) -> tuple[str, ...]:
    if not path.exists():
        return ()
    return tuple(sorted(
        item.name for item in path.iterdir()
        if item.is_file()
        and item.name.endswith((".request.json", ".receipt.json"))
    ))


def _process_payload(observation) -> list[dict[str, object]]:
    return [
        {
            "ProcessName": item.name,
            "Id": item.pid,
            "MainWindowHandle": item.main_window_handle,
            "ProductVersion": item.product_version,
            "FileVersion": item.file_version,
            "Path": item.executable_path,
        }
        for item in observation.processes
    ]


def _primary_pid(observation) -> int | None:
    windowed = [
        item.pid for item in observation.processes
        if item.main_window_handle > 0
    ]
    if len(windowed) == 1:
        return windowed[0]
    return observation.processes[0].pid if len(observation.processes) == 1 else None


def _write_json_atomic(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f"{path.name}.",
        suffix=".tmp",
    )
    temporary = Path(name)
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        temporary.replace(path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def _call_payload(item) -> dict[str, object]:
    return {
        "call_expectation_id": item.call_expectation_id,
        "call_attempt_id": item.call_attempt_id,
        "source_phone_id": item.source_phone_id,
        "destination_phone_id": item.destination_phone_id,
        "dialed_extension": item.dialed_extension,
        "expected_result": item.expected_result.value,
        "status": item.status.value,
        "states": [state.value for state in item.states],
        "connected": item.connected,
        "teardown_verified": item.teardown_verified,
        "observed_after_ns": item.observed_after_ns,
        "fresh_evidence": item.fresh_evidence,
        "evidence_method": item.evidence_method,
        "execution_method": item.execution_method.value,
        "evidence_artifact_path": item.evidence_artifact_path,
        "evidence_sha256": item.evidence_sha256,
        "failure_code": item.failure_code.value,
        "message": item.message,
    }


def _registration_payload(item) -> dict[str, object]:
    return {
        "expectation_id": item.expectation_id,
        "phone_id": item.phone_id,
        "extension": item.extension,
        "status": item.status.value,
        "direct_readback": item.direct_readback.value,
        "fresh_evidence": item.fresh_evidence,
        "evidence_method": item.evidence_method,
        "addressing_status": item.addressing_status.value,
        "failure_code": item.failure_code.value,
        "message": item.message,
        "addressing_message": item.addressing_message,
        "call_control_ipv4": item.call_control_ipv4,
        "endpoint_ipv4": item.endpoint_ipv4,
        "endpoint_interface": item.endpoint_interface,
    }


def run(
    packet_tracer_version: str,
    *,
    expected_head: str,
    qualification_id: str,
    ci_head: str,
    ci_run_id: str,
    ci_check_runs: tuple[str, ...],
    execute: bool,
) -> int:
    root = governed_root_from_env()
    if root is None:
        print(json.dumps({"hard_stop": f"{GOVERNED_ROOT_ENV_VAR} is required."}))
        return 2
    root = root.resolve()
    exchange_value = os.environ.get("PT_MCP_PHONE_CONTROL_EXCHANGE_DIR", "")
    exchange = Path(exchange_value).resolve() if exchange_value else None
    preflight: dict[str, object] = {
        "scope": QUALIFICATION_SCOPE,
        "qualification_id": qualification_id,
        "packet_tracer_version": packet_tracer_version,
        "expected_head": expected_head,
        "exchange_dir": str(exchange) if exchange is not None else "",
        "ci": {
            "head": ci_head,
            "run_id": ci_run_id,
            "successful_check_runs": list(ci_check_runs),
        },
    }
    errors: list[str] = []
    if not execute:
        errors.append("--execute is required; no Packet Tracer mutation occurred.")
    if not qualification_id or qualification_id != qualification_id.strip():
        errors.append("A unique exact qualification ID is required.")
    if (
        ci_head != expected_head
        or not ci_run_id
        or len(ci_check_runs) != 4
        or len(set(ci_check_runs)) != 4
        or any(not item for item in ci_check_runs)
    ):
        errors.append("Exactly four successful CI checks for the authorized SHA are required.")
    if exchange is None:
        errors.append("PT_MCP_PHONE_CONTROL_EXCHANGE_DIR is required.")
    runtime = PythonRuntimeEvidenceReader().read()
    imports = PacketTracerImportIsolationReader().read(root)
    preflight["runtime"] = {
        "python_executable": runtime.python_executable,
        "package_file": runtime.package_file,
        "loaded_namespaces": list(runtime.loaded_namespaces),
    }
    preflight["import_isolation"] = {
        "isolated": imports.isolated,
        "state": imports.isolation_state,
        "detail": imports.detail,
        "error": imports.error,
    }
    if not runtime.coherent or not imports.isolated:
        errors.append(imports.error or "Production import isolation is not coherent.")
    repository = GitCPScaleRepositoryReader().read(root)
    preflight["repository"] = repository.__dict__
    if repository.branch != EXPECTED_BRANCH:
        errors.append(
            f"Expected branch {EXPECTED_BRANCH!r}; observed {repository.branch!r}."
        )
    if repository.upstream != EXPECTED_UPSTREAM:
        errors.append(
            f"Expected upstream {EXPECTED_UPSTREAM!r}; observed {repository.upstream!r}."
        )
    if repository.head != expected_head or repository.upstream_head != expected_head:
        errors.append("Authorized, local, and upstream SHA do not match exactly.")
    if repository.dirty is not False:
        errors.append("LIVE qualification requires a clean worktree.")
    if repository.error or repository.source_tree_error or repository.upstream_head_error:
        errors.extend(filter(None, (
            repository.error,
            repository.source_tree_error,
            repository.upstream_head_error,
        )))
    process_before = PowerShellPacketTracerProcessReader().read()
    process_error = process_before.error or packet_tracer_process_error(
        _process_payload(process_before),
        packet_tracer_version,
    )
    preflight["packet_tracer_processes"] = _process_payload(process_before)
    if process_error:
        errors.append(process_error)
    mailbox_before = _mailbox_entries(exchange) if exchange is not None else ()
    preflight["mailbox_entries_before"] = list(mailbox_before)
    if mailbox_before:
        errors.append("The native-UI call mailbox is not empty before qualification.")
    if errors:
        print(json.dumps({"hard_stop": " ".join(errors), "preflight": preflight}))
        return 2

    assert exchange is not None
    driver_source = (
        Path(__file__).parents[2]
        / "infrastructure"
        / "execution"
        / "native_ui_phone_driver.py"
    )
    driver_hash = hashlib.sha256(driver_source.read_bytes()).hexdigest()
    driver = PacketTracerNativeUiCallDriver(
        exchange_dir=exchange,
        physical_phone_names={},
        timeout_seconds=300.0,
        readiness_timeout_seconds=180.0,
    )
    if not driver.probe_readiness(packet_tracer_version, driver_hash):
        print(json.dumps({
            "hard_stop": "Native-UI PhoneControl readiness handshake failed.",
            "preflight": preflight,
        }))
        return 2

    transport = PacketTracerHttpTransport()
    result = None
    bridge_after = None
    initial_environment = None
    final_environment = None
    execution_error = ""
    try:
        if not transport.start(timeout_seconds=20.0):
            print(json.dumps({
                "hard_stop": "Authenticated Packet Tracer bridge did not connect.",
                "preflight": preflight,
                "bridge": transport.status_dict(),
            }))
            return 2
        initial_environment = _environment(transport)
        initial_environment_error = _environment_error(
            initial_environment,
            packet_tracer_version,
        )
        preflight["packet_tracer_environment"] = initial_environment
        preflight["bridge"] = transport.status_dict()
        if initial_environment_error:
            print(json.dumps({
                "hard_stop": initial_environment_error,
                "preflight": preflight,
            }))
            return 2
        physical = PacketTracerPhysicalTopologyRuntime(
            transport.send_and_wait,
            mutation_timeout_seconds=30.0,
            observation_timeout_seconds=12.0,
        )
        configuration = PacketTracerEnterpriseConfigurationRuntime(
            lambda: _inventory(physical),
            transport.send,
            transport.send_and_wait,
            l3_timeout_seconds=20.0,
        )
        phone_control = PacketTracerNativeUiPhoneControlAdapter(driver)
        voice_runtime = PacketTracerEnterpriseVoiceRuntime(
            lambda: _inventory(physical),
            transport.send,
            transport.send_and_wait,
            phone_control=phone_control,
            registration_timeout_seconds=180.0,
            convergence_interval_seconds=5.0,
        )
        result = CallObservabilityQualification(
            physical=physical,
            configuration=configuration,
            voice=VoiceApplicator(voice_runtime),
            mode=SimulationTraceRuntime(transport.send_and_wait),
            token=safe_name_component(qualification_id, "callqual"),
        ).qualify()
        final_environment = _environment(transport)
        bridge_after = transport.status_dict()
    except Exception as exc:
        execution_error = f"{type(exc).__name__}: {exc}"
    finally:
        transport.stop()

    process_after = PowerShellPacketTracerProcessReader().read()
    repository_after = GitCPScaleRepositoryReader().read(root)
    mailbox_after = _mailbox_entries(exchange)
    postflight_errors: list[str] = []
    if execution_error:
        postflight_errors.append("qualification_execution: " + execution_error)
    if final_environment is None:
        postflight_errors.append("Final Packet Tracer environment was not observed.")
    else:
        final_environment_error = _environment_error(
            final_environment,
            packet_tracer_version,
        )
        if final_environment_error:
            postflight_errors.append(final_environment_error)
    if mailbox_after:
        postflight_errors.append("Native-UI request/receipt mailbox residue remains.")
    if (
        repository_after.head != repository.head
        or repository_after.source_tree != repository.source_tree
        or repository_after.dirty is not False
    ):
        postflight_errors.append("Repository identity or cleanliness changed during LIVE.")
    if _primary_pid(process_before) != _primary_pid(process_after):
        postflight_errors.append("Packet Tracer primary process identity changed during LIVE.")
    voice_result = result.voice_result if result is not None else None
    calls = [_call_payload(item) for item in (voice_result.calls if voice_result else ())]
    registrations = [
        _registration_payload(item)
        for item in (voice_result.registrations if voice_result else ())
    ]
    final_status = (
        result.status.value
        if result is not None and not postflight_errors
        else CallObservabilityQualificationStatus.BLOCKED.value
    )
    raw = {
        "schema": "call-observability-live-v1",
        "scope": QUALIFICATION_SCOPE,
        "run_identity": qualification_id,
        "executed_sha": expected_head,
        "source_tree": repository.source_tree,
        "packet_tracer_version": packet_tracer_version,
        "provider": {
            "provider_id": NATIVE_UI_PROVIDER_ID,
            "execution_method": PhoneExecutionMethod.PACKET_TRACER_NATIVE_UI.value,
            "driver_source": str(driver_source.relative_to(root)).replace("\\", "/"),
            "driver_source_sha256": driver_hash,
        },
        "ci": preflight["ci"],
        "preflight": preflight,
        "qualification": {
            "status": final_status,
            "fixture_models": ["2811", "3560-24PS", "7960", "7960"],
            "voice_plan_id": result.voice_plan.id if result is not None else "",
            "voice_plan_hash": result.voice_plan.semantic_hash if result is not None else "",
            "calls": calls,
            "registrations": registrations,
            "created_devices": list(result.created_devices) if result else [],
            "created_links": list(result.created_links) if result else [],
            "removed_devices": list(result.removed_devices) if result else [],
            "baseline": result.baseline.compact_summary() if result and result.baseline else None,
            "cleanup_first": result.cleanup_first.compact_summary() if result and result.cleanup_first else None,
            "cleanup_second": result.cleanup_second.compact_summary() if result and result.cleanup_second else None,
            "cleanup_verified": result.cleanup_verified if result else False,
            "initial_realtime": result.initial_realtime if result else None,
            "final_realtime": result.final_realtime if result else None,
            "errors": list(result.errors) if result else ["qualification did not return"],
        },
        "postflight": {
            "packet_tracer_processes": _process_payload(process_after),
            "primary_pid_before": _primary_pid(process_before),
            "primary_pid_after": _primary_pid(process_after),
            "bridge": bridge_after,
            "packet_tracer_environment": final_environment,
            "mailbox_entries_after": list(mailbox_after),
            "repository": repository_after.__dict__,
            "errors": postflight_errors,
        },
    }
    output_dir = resolve_within(
        root,
        "data",
        "cp-scale",
        "call-observability-qualification",
    )
    output = resolve_within(
        output_dir,
        safe_name_component(qualification_id, "callqual") + ".json",
    )
    _write_json_atomic(output, raw)
    print(json.dumps({
        "event": "CALL_OBSERVABILITY_QUALIFICATION_COMPLETE",
        "status": raw["qualification"]["status"],
        "run_identity": qualification_id,
        "executed_sha": expected_head,
        "evidence_path": str(output),
        "evidence_sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
        "cleanup_verified": raw["qualification"]["cleanup_verified"],
        "mailbox_entries_after": list(mailbox_after),
    }))
    return 0 if (
        result is not None
        and final_status == CallObservabilityQualificationStatus.VERIFIED.value
    ) else 3


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--packet-tracer-version", default="9.0.1.0858")
    parser.add_argument("--expected-head", required=True)
    parser.add_argument("--qualification-id", required=True)
    parser.add_argument("--ci-head", required=True)
    parser.add_argument("--ci-run-id", required=True)
    parser.add_argument("--ci-check-run", action="append", default=[])
    args = parser.parse_args(argv)
    return run(
        args.packet_tracer_version,
        expected_head=args.expected_head,
        qualification_id=args.qualification_id,
        ci_head=args.ci_head,
        ci_run_id=args.ci_run_id,
        ci_check_runs=tuple(args.ci_check_run),
        execute=args.execute,
    )


if __name__ == "__main__":
    raise SystemExit(main())
