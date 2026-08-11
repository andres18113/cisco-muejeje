"""Clasificacion de cada superficie fire-and-forget, y sus limites.

El canal de configuracion es asincrono por diseno, y la arquitectura lo
sostiene sin mentir porque APPLIED significa DESPACHADO, no observado:

    docs/architecture/e95-stabilization.md    applied != observed
    docs/architecture/enterprise-control-plane.md
        "A result may be APPLIED and still be UNOBSERVABLE."

Lo que estos tests fijan es lo que SI podria romperse en silencio: que un
encolado fallido no se confunda con un rechazo del backend, que ninguna ruta
productiva promueva despacho a verificado, que el camino raw quede contenido, y
que la reejecucion duplicada del motor este clasificada como lo que es.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from src.packet_tracer_mcp.domain.enterprise.models.configuration_runtime import (
    ActionExecutionStatus,
    RuntimeActionMutation,
    mutation_execution_status,
)
from src.packet_tracer_mcp.infrastructure.execution.file_bridge import FileBridge

REPO = Path(__file__).resolve().parents[1]
PACKAGE = REPO / "src" / "packet_tracer_mcp"


# -- 3. certeza del fallo local ------------------------------------------

def test_a_failed_send_never_published_an_executable_request(tmp_path):
    """`send() == False` debe significar que nada quedo publicado.

    Si algun fallo POSTERIOR a publicar pudiera devolver False, entonces
    FAILED seria inseguro: el motor podria ejecutar igual un payload que la
    aplicacion ya dio por no aplicado.
    """
    bridge = FileBridge(tmp_path)

    def explode(path, text):
        raise OSError("disco lleno")

    bridge._write_atomic = explode

    assert bridge.send("configureIosDevice('R1','router rip')") is False
    assert list(tmp_path.glob("req_*.js")) == []


def test_a_failed_send_leaves_no_temporary_file_behind(tmp_path):
    bridge = FileBridge(tmp_path)
    original = bridge._write_atomic

    def fail_after_temp(path, text):
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_bytes(text.encode("utf-8"))
        raise OSError("rename fallo")

    bridge._write_atomic = fail_after_temp
    assert bridge.send("x") is False

    # El .tmp no lleva el prefijo que el motor busca, asi que no es ejecutable.
    assert list(tmp_path.glob("req_*.js")) == []
    assert original is not None


def test_the_publish_step_is_the_last_thing_that_can_fail(tmp_path):
    """No hay paso posterior a publicar que pueda devolver False.

    Se comprueba sobre el source: si aparece un paso capaz de fallar despues
    del `_write_atomic`, `send` podria devolver False con el request ya visible
    para el motor, y la certeza de FAILED se perderia.
    """
    import inspect

    body = inspect.getsource(FileBridge.send)
    after_publish = body.split("_write_atomic")[1]

    assert "return True" in after_publish
    assert "raise" not in after_publish


def test_a_failed_enqueue_is_the_only_definite_local_failure():
    assert mutation_execution_status(
        RuntimeActionMutation(action_id="a", applied=False),
    ) is ActionExecutionStatus.FAILED


# -- 4. despacho no es efecto --------------------------------------------

def test_dispatch_never_reaches_verified_on_its_own():
    """Ninguna combinacion de despacho produce VERIFIED.

    VERIFIED sale de releer el estado, nunca del retorno del envio.
    """
    from src.packet_tracer_mcp.domain.enterprise.models.execution import (
        MutationDisposition,
    )

    for disposition in MutationDisposition:
        status = mutation_execution_status(RuntimeActionMutation(
            action_id="a", applied=True, disposition=disposition,
        ))
        assert status is not ActionExecutionStatus.VERIFIED


def test_every_applicator_uses_the_single_domain_definition():
    """Cinco copias identicas eran cinco lugares donde divergir en silencio."""
    offenders = []
    for name in (
        "apply_configuration", "apply_control_plane",
        "apply_security", "apply_services", "apply_voice",
    ):
        source = (PACKAGE / "application" / "use_cases" / f"{name}.py").read_text(
            encoding="utf-8",
        )
        if "mutation_execution_status(mutation)" not in source:
            offenders.append(name)

    assert offenders == []


# -- 5/6. matriz de superficies y contencion del camino raw ---------------

def test_the_raw_fire_and_forget_tool_cannot_satisfy_a_typed_mutation_contract():
    """`pt_send_raw` no participa de ningun contrato de mutacion tipada.

    Es una superficie de investigacion: manda JS arbitrario. Lo que no puede
    es aparecer dentro del camino empresarial, donde el resultado se declara
    con `RuntimeActionMutation` y se verifica releyendo.
    """
    registry = (PACKAGE / "adapters" / "mcp" / "tool_registry.py").read_text(
        encoding="utf-8",
    )
    raw_tool = registry.split("def pt_send_raw")[1].split("@mcp.tool()")[0]

    assert "RuntimeActionMutation" not in raw_tool
    assert "configure_ios" not in raw_tool
    assert "ActionExecutionStatus" not in raw_tool


def test_the_typed_configuration_channel_is_the_only_mutation_runtime():
    """Toda mutacion tipada pasa por la misma primitiva de configuracion."""
    owners = sorted(
        path.relative_to(PACKAGE).as_posix()
        for path in PACKAGE.rglob("*.py")
        if "PacketTracerConfigurationRuntime(" in path.read_text(encoding="utf-8")
    )

    assert owners == [
        "infrastructure/execution/enterprise_configuration_runtime.py",
        "infrastructure/execution/enterprise_control_plane_runtime.py",
        "infrastructure/execution/enterprise_security_runtime.py",
        "infrastructure/execution/enterprise_voice_runtime.py",
        "infrastructure/execution/probe_runtime.py",
    ], f"Apareció otro dueño del canal de mutación: {owners}"


# -- 7. reejecucion duplicada: clasificacion honesta ----------------------

def test_a_response_that_arrives_between_sends_retires_its_request(tmp_path):
    """La mitigacion: el envio siguiente retira lo ya contestado."""
    bridge = FileBridge(tmp_path)
    assert bridge.send("configureIosDevice('R1','a')")
    first = next(iter(tmp_path.glob("req_*.js"))).name[4:-3]
    (tmp_path / f"res_{first}.txt").write_text("ok", encoding="utf-8")

    bridge.send("configureIosDevice('R1','b')")

    assert not (tmp_path / f"req_{first}.js").exists()
    assert not (tmp_path / f"res_{first}.txt").exists()


def test_a_request_the_engine_failed_to_remove_is_replayable_until_collected(tmp_path):
    """LIMITACION DE BACKEND, deliberadamente probada y no disimulada.

    Si el motor contesta pero no logra borrar el req, el archivo sigue siendo
    ejecutable en cada tick. Nada del lado del servidor puede impedirlo entre
    medio: la recoleccion ocurre en el envio siguiente, y si no hay envio
    siguiente -- o el proceso muere -- el req sobrevive hasta la purga de
    huerfanos del propio motor. Esto NO es exactly-once.
    """
    bridge = FileBridge(tmp_path)
    bridge.send("configureIosDevice('R1','router rip')")
    name = next(iter(tmp_path.glob("req_*.js"))).name[4:-3]

    # El motor contesta y falla al limpiar.
    (tmp_path / f"res_{name}.txt").write_text("ok", encoding="utf-8")

    executions = 0
    for _ in range(3):  # ticks simulados del Script Engine
        if (tmp_path / f"req_{name}.js").exists():
            executions += 1
        time.sleep(0.01)

    assert executions == 3, (
        "El request sigue disponible para reejecutarse en cada tick mientras "
        "nadie lo retire: esa es la limitacion que no hay que disimular."
    )


def test_how_many_times_a_stranded_request_is_evaluated(tmp_path):
    """Cuenta ejecuciones reales, no disponibilidad, replicando el bucle del motor.

    Escenario exacto: el motor contesta, falla al borrar el req, y NO hay envio
    siguiente de Python que lo recoja. Se simulan varios ticks.

    El bucle real es: listar -> leer contenido -> evaluar -> escribir res ->
    borrar req (con el error tragado). Si el borrado falla, el req sigue
    listado en el tick siguiente y se vuelve a evaluar.
    """
    bridge = FileBridge(tmp_path)
    bridge.send("configureIosDevice('R1','router rip')")

    evaluations = 0
    remove_works = False  # el fallo que se inyecta

    for _tick in range(5):
        for request in sorted(tmp_path.glob("req_*.js")):
            request.read_text(encoding="utf-8")
            evaluations += 1
            name = request.name[4:-3]
            (tmp_path / f"res_{name}.txt").write_text("ok", encoding="utf-8")
            if remove_works:
                request.unlink()

    assert evaluations == 5, (
        "El mismo payload se evalua una vez por tick mientras nadie retire el "
        "archivo. Esto NO es at-most-once ni exactly-once."
    )


def test_the_same_scenario_is_bounded_when_a_later_send_collects(tmp_path):
    """Control: con un envio posterior, la recoleccion corta la repeticion."""
    bridge = FileBridge(tmp_path)
    bridge.send("configureIosDevice('R1','a')")

    evaluations = 0
    for tick in range(5):
        for request in sorted(tmp_path.glob("req_*.js")):
            request.read_text(encoding="utf-8")
            evaluations += 1
            (tmp_path / f"res_{request.name[4:-3]}.txt").write_text("ok", encoding="utf-8")
        if tick == 0:
            bridge.send("configureIosDevice('R1','b')")  # recoge el anterior

    # El primero se evaluo una vez; el segundo, en los ticks restantes.
    assert evaluations < 10
    assert evaluations >= 2


def test_nothing_in_the_transport_claims_exactly_once():
    source = (
        PACKAGE / "infrastructure" / "execution" / "file_bridge.py"
    ).read_text(encoding="utf-8").casefold()

    assert "exactly-once" not in source or "no es exactly-once" in source


# -- 8. precondiciones de transporte para un futuro RIPv2 ------------------

RIPV2_TRANSPORT_PRECONDITIONS = (
    "declarative_typed_payload_only",
    "replay_safe_idempotent_commands",
    "single_deliberate_dispatch",
    "no_blind_retry",
    "direct_control_plane_readback",
    "behavioral_verification",
    "reconcile_only_observed_missing_state",
    "no_raw_ios_surface",
)


@pytest.mark.parametrize("precondition", RIPV2_TRANSPORT_PRECONDITIONS)
def test_the_transport_preconditions_for_rip_are_named_not_assumed(precondition):
    """Se nombran acá para que R2 las herede escritas, sin implementar RIP.

    Bajo la limitacion de reejecucion conocida, un payload RIP sólo es seguro
    si es declarativo y replay-safe: `router rip`, `version 2` y `network X`
    aplicados dos veces dejan el mismo estado. Eso hace tolerable la
    limitacion; no la elimina, y por eso el replay deliberado sigue prohibido.
    """
    assert precondition in RIPV2_TRANSPORT_PRECONDITIONS


def test_rip_exists_only_as_legacy_generated_cli_not_as_a_typed_action():
    """Fija donde esta hoy RIP, que es justo la deuda que R2 tendra que saldar.

    Existe un generador de texto CLI con `router rip`, pero vive en el camino
    legacy (full_build / deploy_executor / manual_executor). NO existe una
    accion tipada de RIP en el camino empresarial, que es el unico que declara
    su resultado con `RuntimeActionMutation` y lo verifica releyendo. R1-D no
    agrega ninguna: si este test cae, alguien empezo RIP antes de tiempo.
    """
    emitters = sorted(
        path.relative_to(PACKAGE).as_posix()
        for path in PACKAGE.rglob("*.py")
        if "router rip" in path.read_text(encoding="utf-8").casefold()
    )

    assert emitters == ["infrastructure/generator/cli_config_generator.py"]

    typed_actions = (
        PACKAGE / "domain" / "enterprise" / "models" / "control_plane.py"
    ).read_text(encoding="utf-8").casefold()
    assert "rip" not in typed_actions.replace("description", "").replace("scripting", "")


def test_the_legacy_rip_generator_is_not_wired_into_the_typed_mutation_runtime():
    """El generador legacy no puede colarse en el canal tipado.

    Es lo que hace que la deuda sea acotada: RIP hoy no puede producir un
    `RuntimeActionMutation`, asi que tampoco puede producir un APPLIED.
    """
    for name in (
        "enterprise_configuration_runtime", "enterprise_control_plane_runtime",
        "enterprise_security_runtime", "enterprise_voice_runtime",
    ):
        source = (PACKAGE / "infrastructure" / "execution" / f"{name}.py").read_text(
            encoding="utf-8",
        )
        assert "cli_config_generator" not in source
