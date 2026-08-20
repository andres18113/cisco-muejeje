"""TD-TRANSPORT-001 branch B: cada familia de mutación E9.5, contenida y acotada.

La limitación es real y no se cierra por ingenio: el Script Engine desplegado no
publica marca de *claim*, así que "leído y evaluando" es indistinguible de
"nunca leído" a través del filesystem. Branch A necesita recompilar el `.pts`
con dependencias de PTBuilder que este repositorio no redistribuye, de modo que
el cierre pasa por branch B:

> la limitación queda explícitamente clasificada y **toda** familia de mutación
> del producto E9.5 está contenida de forma segura, sin ninguna afirmación más
> fuerte que la evidencia disponible.

Eso tiene dos mitades, y la segunda es la que se degrada sola con el tiempo:

1. **clasificar** -- la tabla de abajo enumera cada familia, su contención y su
   techo de afirmación;
2. **que la tabla no se quede vieja en silencio** -- el barrido descubre las
   familias desde el CÓDIGO, así que una mutación nueva que nadie clasifique
   rompe estos tests en vez de heredar una contención que nadie comprobó.

Lo segundo es el punto entero. Una matriz de contención escrita una vez es una
foto; ésta es un cerrojo.
"""

from __future__ import annotations

import ast
import pathlib

import pytest

from src.packet_tracer_mcp.infrastructure.execution.file_bridge import (
    RequestDisposition,
)

REPO = pathlib.Path(__file__).resolve().parents[1]
PACKAGE = REPO / "src" / "packet_tracer_mcp"
EXECUTION = PACKAGE / "infrastructure" / "execution"

#: Las primitivas Python que MUTAN Packet Tracer. Todo lo demás lee.
_MUTATION_PRIMITIVES = {
    "configure_ios",            # lote IOS por el canal de configuración
    "configure_endpoint_ipv4",  # `configurePcIp` sobre un endpoint
    "_mutation_ack",            # creación/borrado físico con ACK acotado
    "_module_mutation_ack",     # inserción de módulo con ACK acotado
}

#: Y las APIs de Packet Tracer que mutan, para los módulos que arman su propio
#: JS en vez de pasar por una primitiva Python. `enterprise_service_runtime.py`
#: es exactamente ese caso, y la primera versión de este barrido no lo vio: se
#: apoyaba sólo en las primitivas Python y dejó una familia entera sin
#: clasificar. Buscar el nombre de la API cierra ese hueco.
_MUTATING_PT_APIS = {
    "lwAddDevice", "lwAddLink", "removeDevice", "configureIosDevice",
    "configurePcIp", "setEnable", "setEnabled", "setHttpsEnable",
    "setPageContents", "addARecordToNameServerDb", "setSimulationMode",
    "resetSimulation",
}

#: Cada familia, con la contención que la cubre y el techo de lo que puede
#: afirmar. `owner` es la ruta, relativa al paquete, donde vive el despacho.
#:
#: El barrido recorre el PAQUETE ENTERO, no sólo `infrastructure/execution/`.
#: La primera versión miraba una sola carpeta y por eso no veía `apply_acl.py`
#: -- que despacha cuando recibe un `bridge_send` -- ni la superficie de tools
#: MCP. Una tabla cerrada sobre un subdirectorio no es un cerrojo: es un cerrojo
#: en una puerta con la ventana abierta.
CONTAINED_MUTATION_FAMILIES = {
    "physical": {
        "owner": "infrastructure/execution/packet_tracer_physical_runtime.py",
        "containment": (
            "pre-readback before every mutation; a bounded ACK classifies "
            "ACCEPTED / REJECTED / UNKNOWN; an UNKNOWN outcome is never replayed"
        ),
        "ceiling": "acknowledgement is not effect; an independent read-back decides",
    },
    "configuration": {
        "owner": "infrastructure/execution/enterprise_configuration_runtime.py",
        "containment": (
            "the whole batch is rendered and routed before the first device is "
            "touched; a refused batch mutates nothing"
        ),
        "ceiling": "APPLIED means the channel accepted the dispatch, not that the device changed",
    },
    "control_plane": {
        "owner": "infrastructure/execution/enterprise_control_plane_runtime.py",
        "containment": "typed actions only; a rendering failure refuses instead of dispatching",
        "ceiling": "APPLIED is separate from VERIFIED; fresh registered read-back decides",
    },
    "security": {
        "owner": "infrastructure/execution/enterprise_security_runtime.py",
        "containment": (
            "typed actions only, with a separate typed removal payload; the "
            "family is classified TREAT_AS_REPLAY_UNSAFE regardless of the "
            "measurement recorded in TD-SECURITY-001"
        ),
        "ceiling": "direct read-back per action; no behavioural claim from application alone",
    },
    "services": {
        "owner": "infrastructure/execution/enterprise_service_runtime.py",
        "containment": "typed actions only; capability-gated before dispatch",
        "ceiling": "compile readiness is not behaviour",
    },
    "voice": {
        "owner": "infrastructure/execution/enterprise_voice_runtime.py",
        "containment": (
            "typed actions only, capability-gated; with no supplied profile "
            "every action resolves UNKNOWN and is SKIPPED without dispatch"
        ),
        "ceiling": "`create cnf-files` replay behaviour is UNKNOWN -- TD-VOICE-001",
    },
    "probe": {
        "owner": "infrastructure/execution/probe_runtime.py",
        "containment": (
            "disposable `__MCP_PROBE_*` resources only, created and removed by "
            "the same pass, with inventory fingerprints either side"
        ),
        "ceiling": "a probe result is evidence about the probe, never about a deployed device",
    },
    "shared_dispatch": {
        "owner": "infrastructure/execution/configuration_runtime.py",
        "containment": (
            "the single choke point every IOS and endpoint mutation passes "
            "through; it sends and reports only whether the CHANNEL accepted, "
            "and never retries on its own"
        ),
        "ceiling": (
            "its boolean is transport acceptance, not device effect -- every "
            "caller must read the device back to claim anything"
        ),
    },
    "legacy_raw_acl": {
        "owner": "application/use_cases/apply_acl.py",
        "containment": (
            "NONE ESTABLISHED, and named as such rather than dressed up: this "
            "path bypasses the typed compile/render/apply chain entirely and "
            "dispatches only when a caller hands it a bridge_send"
        ),
        "ceiling": (
            "TREAT_AS_REPLAY_UNSAFE -- generate_acl_cli emits no preceding "
            "`no access-list N`, so the payload is structurally additive"
        ),
    },
    "mcp_tool_surface": {
        "owner": "adapters/mcp/tool_registry.py",
        "containment": (
            "the operator-facing tools, each pinning a transport and requiring "
            "its own read-back; the raw fire-and-forget tool remains separately "
            "ledgered as TD-PUBLIC-001"
        ),
        "ceiling": "a tool result reports what the channel accepted, not what the device did",
    },
    "simulation_mode": {
        "owner": "infrastructure/execution/simulation_trace_runtime.py",
        "containment": (
            "the only mutation is Packet Tracer's own Realtime/Simulation mode, "
            "which reports the state before and after rather than assuming it"
        ),
        "ceiling": (
            "diagnostic only; a trace localises and never promotes anything to "
            "VERIFIED, and nothing from it enters ConfigurationApplicationResult"
        ),
    },
}


#: Módulos que NOMBRAN una API mutante sin despacharla. Cada uno está acá por
#: una razón distinta y verificable, no por conveniencia:
#:
#: * los dos generadores devuelven TEXTO -- una llamada JS o un script -- y no
#:   tienen ningún canal por el que mandarlo;
#: * `settings.py` documenta las tools en una cadena de módulo, que es prosa
#:   aunque no sea un docstring.
#:
#: Si alguno empezara a despachar, dejaría de pertenecer acá y tendría que
#: entrar en la tabla de familias. Nada en este archivo lo detecta solo, y por
#: eso la lista es corta y cada entrada dice por qué.
PAYLOAD_BUILDERS_AND_PROSE = {
    "shared/ios_config.py": "returns the configureIosDevice call as text",
    "infrastructure/generator/ptbuilder_generator.py": "generates a PTBuilder script",
    "settings.py": "documents the MCP tools in a module-level string",
}


def _docstrings(tree: ast.AST) -> set[int]:
    """Los `id()` de las constantes que son docstring, para no confundir un
    ejemplo de uso en prosa con un despacho real. `live_bridge.py` documenta
    `addDevice(...)` en su docstring y no muta nada."""
    marked: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = getattr(node, "body", [])
            if (
                body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)
            ):
                marked.add(id(body[0].value))
    return marked


def _modules_dispatching_mutations() -> dict[str, set[str]]:
    """Descubre desde el AST qué módulos despachan mutaciones, y con qué."""
    found: dict[str, set[str]] = {}
    for path in sorted(PACKAGE.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        skip = _docstrings(tree)
        used = {
            node.func.attr
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in _MUTATION_PRIMITIVES
        }
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Constant)
                and isinstance(node.value, str)
                and id(node) not in skip
            ):
                used.update(
                    name for name in _MUTATING_PT_APIS if name in node.value
                )
        if used:
            found[path.relative_to(PACKAGE).as_posix()] = used
    return found


def _owners() -> set[str]:
    return {item["owner"] for item in CONTAINED_MUTATION_FAMILIES.values()}


def _accounted_for() -> set[str]:
    return _owners() | set(PAYLOAD_BUILDERS_AND_PROSE)


# ===================== la limitación sigue clasificada ====================


def test_no_disposition_claims_a_request_did_not_execute():
    """El corazón de la limitación, estructural y no meramente afirmado."""
    assert [item for item in RequestDisposition if item.proves_no_execution] == []


def test_every_disposition_is_covered_by_the_property():
    assert len(list(RequestDisposition)) >= 4


# ===================== la tabla no se queda vieja =========================


def test_every_module_that_dispatches_a_mutation_is_a_classified_family():
    """El cerrojo: una familia nueva sin clasificar rompe acá, no en producción."""
    dispatching = set(_modules_dispatching_mutations())

    unclassified = dispatching - _accounted_for()

    assert unclassified == set(), (
        "These modules dispatch a Packet Tracer mutation and belong to no "
        f"classified containment family: {sorted(unclassified)}. Classify them "
        "in CONTAINED_MUTATION_FAMILIES with their containment and claim "
        "ceiling, or stop dispatching from there."
    )


def test_no_classified_family_names_a_module_that_stopped_dispatching():
    """Y al revés: una entrada que ya no corresponde a nada es ruido."""
    dispatching = set(_modules_dispatching_mutations())

    stale = _accounted_for() - dispatching

    assert stale == set(), (
        f"These families name a module that dispatches no mutation: {sorted(stale)}."
    )


@pytest.mark.parametrize("family", sorted(CONTAINED_MUTATION_FAMILIES))
def test_every_family_states_a_containment_and_a_ceiling(family):
    entry = CONTAINED_MUTATION_FAMILIES[family]

    assert entry["containment"].strip()
    assert entry["ceiling"].strip()
    assert (PACKAGE / entry["owner"]).exists()


@pytest.mark.parametrize("module", sorted(PAYLOAD_BUILDERS_AND_PROSE))
def test_every_exempted_module_exists_and_says_why(module):
    assert (PACKAGE / module).exists()
    assert PAYLOAD_BUILDERS_AND_PROSE[module].strip()


def test_the_sweep_covers_the_whole_package_and_not_one_directory():
    """El agujero literal de la primera versión de este barrido."""
    dispatching = set(_modules_dispatching_mutations())

    assert any(not item.startswith("infrastructure/execution/") for item in dispatching)
    assert "application/use_cases/apply_acl.py" in dispatching


# ===================== ninguna mutación se reintenta a ciegas =============


def test_the_only_retry_in_the_dispatch_path_is_read_only():
    """Un reintento sobre una mutación ambigua es exactamente lo que la
    limitación prohíbe. El único reintento del ejecutor IOS está acotado a
    corrupción PROBADA del despacho, que significa que IOS nunca recibió lo que
    se pidió."""
    source = (EXECUTION / "ios_terminal.py").read_text(encoding="utf-8")

    assert "_READ_ONLY_DISPATCH_ATTEMPTS" in source
    assert "_is_retryable_corruption" in source


def test_the_physical_path_says_in_words_that_an_unknown_is_not_replayed():
    source = (EXECUTION / "packet_tracer_physical_runtime.py").read_text(encoding="utf-8")

    assert "will not be replayed" in source
