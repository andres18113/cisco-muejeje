"""Contrato de nombres de probes desechables (TD-RUNTIME-004).

Existen DOS namespaces, y la razon es estructural, no estetica:

- `__MCP_PROBE_*` lo genera capability discovery, que nunca pasa por el
  renderer tipado de control plane;
- `MCP-PROBE-*` es para un probe que SI tiene que ser renderizado por un
  renderer confiable, cuyo allowlist exige primer caracter alfanumerico.

Lo que estos tests fijan es que el renderer NO se relajo, que el generador de
discovery NO cambio, y que la limpieza sigue sin depender de ningun prefijo.
"""

from __future__ import annotations

import json
import pathlib

import pytest

from src.packet_tracer_mcp.domain.enterprise.models.control_plane import (
    ConfigureRipv2,
    ControlPlaneCapabilityDimension,
    ControlPlanePhase,
    LinkFailureScenario,
    RipNetwork,
)
from src.packet_tracer_mcp.infrastructure.execution.probe_runtime import (
    PacketTracerBridgeProbeRuntime,
)
from src.packet_tracer_mcp.infrastructure.generator.control_plane_renderer import (
    PacketTracerControlPlaneFaultRenderer,
    PacketTracerControlPlaneRenderer,
)

REPO = pathlib.Path(__file__).resolve().parents[1]
PACKAGE = REPO / "src" / "packet_tracer_mcp"

DISCOVERY_PREFIX = "__MCP_PROBE_"
TYPED_PREFIX = "MCP-PROBE-"


# ============ A. discovery conserva su namespace =========================


def test_capability_discovery_still_names_probes_with_the_underscore_prefix(tmp_path):
    """Ejercita el caso de uso real, no el texto del generador."""
    from test_capability_discovery import _observation, _service
    from src.packet_tracer_mcp.domain.enterprise.models.discovery import ProbeRequest
    from src.packet_tracer_mcp.infrastructure.execution.fake_probe_runtime import (
        FakePacketTracerProbeRuntime,
    )

    runtime = FakePacketTracerProbeRuntime({"2911": _observation("2911")})

    _service(tmp_path, runtime).run(ProbeRequest(models=["2911"]))

    assert runtime.created_names
    assert all(name.startswith(DISCOVERY_PREFIX) for name in runtime.created_names)


def test_the_discovery_generator_was_not_renamed():
    source = (
        PACKAGE / "application" / "use_cases" / "capability_discovery.py"
    ).read_text(encoding="utf-8")

    assert 'f"__MCP_PROBE_{session.session_id.rsplit(\'-\', 1)[-1]}_{index:02d}"' in source
    assert TYPED_PREFIX not in source


# ============ B. el namespace tipado renderiza de extremo a extremo ======


def _typed_action(device_name: str) -> ConfigureRipv2:
    return ConfigureRipv2(
        id="cp/ripv2/probe",
        phase=ControlPlanePhase.DYNAMIC_ROUTING,
        device_id="r1",
        device_name=device_name,
        model="2911",
        site_id="probe",
        required_capability=ControlPlaneCapabilityDimension.RIPV2_CONFIG,
        networks=[RipNetwork(network="150.1.0.0")],
        passive_interfaces=["GigabitEthernet0/0"],
    )


@pytest.mark.parametrize(
    "device_name",
    ["MCP-PROBE-R2B-R1", "MCP-PROBE-R2B-R2", "MCP-PROBE-CAP-R1"],
)
def test_a_typed_probe_name_renders_through_the_trusted_renderer(device_name):
    """Lo que sostiene el test es que NO lanza y que el cuerpo RIP sale.

    `rendered.device_name == device_name` seria afirmar sobre la propia
    entrada, asi que no se usa como prueba.
    """
    rendered = PacketTracerControlPlaneRenderer().render_action(
        _typed_action(device_name),
    )

    assert " network 150.1.0.0" in rendered.ios_payload.splitlines()
    assert " version 2" in rendered.ios_payload.splitlines()
    assert "no router rip" in rendered.cleanup_payload.splitlines()


def test_a_typed_probe_name_renders_a_fault_scenario_too():
    scenario = LinkFailureScenario(
        id="failure/probe-link",
        link_id="probe-link",
        device_a_id="r1", device_b_id="r2",
        target_device_id="r1", target_device_name="MCP-PROBE-R2B-R1",
        target_interface="GigabitEthernet0/0",
        peer_device_id="r2", peer_device_name="MCP-PROBE-R2B-R2",
        peer_interface="GigabitEthernet0/0",
        cable="cross",
        probe_source_device_id="r1",
        probe_source_device_name="MCP-PROBE-R2B-R1",
        probe_destination_device_id="r2",
        probe_destination_device_name="MCP-PROBE-R2B-R2",
        probe_destination_ipv4="150.1.1.86",
    )

    rendered = PacketTracerControlPlaneFaultRenderer().render_scenario(scenario)

    assert rendered.device_name == "MCP-PROBE-R2B-R1"
    # `in` seria satisfecho por `no shutdown`: hay que exigir la linea exacta.
    assert " shutdown" in rendered.ios_payload.splitlines()
    assert " no shutdown" in rendered.cleanup_payload.splitlines()


def test_the_discovery_prefix_is_still_refused_by_the_trusted_renderer():
    """El conflicto original sigue existiendo, y sigue siendo intencional.

    La resolucion fue declarar un namespace compatible, NO relajar el
    validador. Si esto pasara a aceptarse, alguien relajo `_SAFE_DEVICE`.
    """
    with pytest.raises(ValueError, match="Invalid compiled device name"):
        PacketTracerControlPlaneRenderer().render_action(
            _typed_action("__MCP_PROBE_CAP_R1"),
        )


# ============ C. los rechazos hostiles no cambiaron ======================


@pytest.mark.parametrize(
    "device_name",
    [
        "MCP-PROBE-R1\nend",
        "MCP-PROBE-R1 ",
        " MCP-PROBE-R1",
        "MCP-PROBE-R1\rend",
        "MCP-PROBE-R1;evil",
        'MCP-PROBE-R1"x',
        "-MCP-PROBE-R1",
        ".MCP-PROBE-R1",
        "",
        "M" * 65,
    ],
    ids=[
        "newline", "trailing-space", "leading-space", "carriage-return",
        "semicolon", "quote", "leading-hyphen", "leading-dot", "empty",
        "too-long",
    ],
)
def test_hostile_device_names_are_still_rejected(device_name):
    # `match=` importa: sin el, un fallo por otra validacion pasaria por
    # rechazo de nombre y el test mentiria sobre que protege.
    with pytest.raises(ValueError, match="Invalid compiled device name"):
        PacketTracerControlPlaneRenderer().render_action(
            _typed_action(device_name),
        )


def test_the_device_allowlist_was_not_widened():
    source = (
        PACKAGE / "infrastructure" / "generator" / "control_plane_renderer.py"
    ).read_text(encoding="utf-8")

    assert '_SAFE_DEVICE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")' in source


# ============ D. la limpieza no depende de ningun prefijo ================


class _CapturingBridge:
    def __init__(self, response: str = '{"deleted": true}') -> None:
        self.scripts: list[str] = []
        self._response = response

    def __call__(self, script: str, timeout: float) -> str:
        self.scripts.append(script)
        return self._response


@pytest.mark.parametrize(
    "name",
    [
        "__MCP_PROBE_x_01",
        "MCP-PROBE-R2B-R1",
        "anything-at-all",
        "R1",
        # Nombres que json.dumps SI tiene que escapar: si el nombre se
        # concatenara en crudo, el script quedaria roto o inyectable.
        'weird"name',
        "back\\slash",
    ],
)
def test_deletion_names_the_device_exactly_and_never_scans(name):
    bridge = _CapturingBridge()

    PacketTracerBridgeProbeRuntime(bridge).delete_temporary_device(name)

    script = bridge.scripts[0]
    assert f"var __name={json.dumps(name)};" in script
    assert "getDevice(__name)" in script
    for token in ("startsWith", "indexOf", "startswith", "filter("):
        assert token not in script
    # Ningun prefijo de probe aparece en el script salvo dentro del propio
    # nombre pedido, asi que no puede haber seleccion por prefijo.
    without_name = script.replace(json.dumps(name), "")
    assert DISCOVERY_PREFIX not in without_name
    assert TYPED_PREFIX not in without_name


def test_deleting_an_absent_device_reports_success_without_a_scan():
    """Idempotencia en ausencia: la rama que el stub anterior nunca ejercia."""
    bridge = _CapturingBridge('{"deleted": true}')

    deleted = PacketTracerBridgeProbeRuntime(bridge).delete_temporary_device(
        "MCP-PROBE-NEVER-EXISTED",
    )

    assert deleted is True
    assert "if(!__d){reportResult(JSON.stringify({deleted:true}));}" in bridge.scripts[0]


def test_a_refused_deletion_is_reported_as_failure():
    """El retorno depende del backend, no de que el stub diga que si."""
    bridge = _CapturingBridge('{"deleted": false}')

    deleted = PacketTracerBridgeProbeRuntime(bridge).delete_temporary_device(
        "MCP-PROBE-R2B-R1",
    )

    assert deleted is False


_SELECTION_TOKENS = (
    "startswith", "startsWith", "in name", "match(", "search(", "fullmatch",
    # `indexOf` es el modismo JS que este repo usa de verdad para prefijos:
    # omitirlo dejaba pasar justo la regresion que este test debe atrapar.
    "indexOf", "lastIndexOf", "slice(", "substring(", "filter(",
)


def test_no_production_module_selects_devices_by_probe_prefix():
    offenders: list[str] = []
    for path in PACKAGE.rglob("*.py"):
        for number, line in enumerate(
            path.read_text(encoding="utf-8").splitlines(), start=1,
        ):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            if DISCOVERY_PREFIX not in line and TYPED_PREFIX not in line:
                continue
            if any(token in line for token in _SELECTION_TOKENS):
                offenders.append(
                    f"{path.relative_to(PACKAGE).as_posix()}:{number}: {stripped}"
                )

    assert offenders == []


def test_the_prefix_selection_guard_would_catch_a_real_regression():
    """El guardia anterior sirve de poco si no reacciona a nada.

    Fija las formas concretas que tiene que atrapar, incluida la JS con
    `indexOf`, que es la que el repo escribiria de verdad.
    """
    hostile = (
        "if(String(__name).indexOf('__MCP_PROBE_')===0){",
        'if name.startswith("__MCP_PROBE_"):',
        "candidates = [item for item in names if item.startswith(TYPED)]".replace(
            "TYPED", f'"{TYPED_PREFIX}"',
        ),
        "re.match(r'^__MCP_PROBE_', name)",
    )

    for line in hostile:
        assert DISCOVERY_PREFIX in line or TYPED_PREFIX in line
        assert any(token in line for token in _SELECTION_TOKENS), line


# ============ E. QA cubre los dos namespaces =============================


def test_the_qa_residue_contract_covers_both_namespaces():
    qa = (REPO / "docs" / "qa" / "capability-probes.md").read_text(encoding="utf-8")
    checklist = qa.split("## Secuencia mínima", 1)[1].split("##", 1)[0]

    assert DISCOVERY_PREFIX in checklist
    assert TYPED_PREFIX in checklist
    assert "Namespaces desechables" in qa


def test_the_authority_document_no_longer_claims_one_universal_namespace():
    doc = (
        REPO / "docs" / "architecture" / "e95-stabilization.md"
    ).read_text(encoding="utf-8")

    assert "All temporary objects remain identified by the controlled" not in doc
    assert DISCOVERY_PREFIX in doc
    assert TYPED_PREFIX in doc


def test_historical_run_records_still_name_their_original_probes():
    """No prueba inmutabilidad: prueba que no se renombraron hacia la regla nueva.

    La inmutabilidad real la da git, no una asercion de subcadena.
    """
    qualification = (
        REPO / "docs" / "architecture" / "ripv2-runtime-qualification.md"
    ).read_text(encoding="utf-8")
    ledger = (
        REPO / "docs" / "architecture" / "technical-debt.md"
    ).read_text(encoding="utf-8")

    assert "__MCP_PROBE_R2_R1" in qualification
    assert "Residue of `__MCP_PROBE_R2_*`: none." in qualification
    # La comprobacion se acota al registro R2-0. Etapas POSTERIORES en el mismo
    # documento usan legitimamente el namespace tipado; lo que no puede pasar es
    # que el registro historico se renombre hacia la convencion nueva.
    r2_0_record = qualification.split("# R2-B phase 4", 1)[0]
    assert "__MCP_PROBE_R2_R1" in r2_0_record
    assert TYPED_PREFIX not in r2_0_record
    # El registro vivo de TD-RUNTIME-002 conserva su nombre original.
    assert "__MCP_PROBE_R2_IDLE_R1" in ledger
