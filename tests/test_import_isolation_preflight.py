"""El proceso que va a mutar Packet Tracer debe probar su propio aislamiento.

Por que existe:
`tests/test_worktree_isolation.py` es un guard estatico. Prueba que *existe* una
invocacion aislada, construyendo subprocesos con su propio `cwd`. No prueba nada
sobre el proceso que efectivamente mutara Packet Tracer, porque no es ese
proceso. Un suite verde no es evidencia de aislamiento en vivo.

Lo que estos tests fijan es el gate ejecutable: tres comprobaciones, en el mismo
proceso, antes de la primera mutacion, y cerrado por defecto.

La tercera no es teorica. Medido en el interprete correcto, importar ambos
namespaces produce dos objetos de modulo distintos sobre los MISMOS archivos:

    CapabilityStatus.SUPPORTED is CapabilityStatus.SUPPORTED  ->  False

Todo `isinstance` y toda comparacion de enum entre ambos falla en silencio.
"""

from __future__ import annotations

import sys
from pathlib import Path

from packet_tracer_mcp.infrastructure.execution.import_isolation_preflight import (
    ImportIsolationPreflight,
    ImportIsolationState,
    governed_root_from_env,
)
from tests.subprocess_harness import (
    checkout_venv_python,
    checkout_venv_root,
    foreign_python,
    run_isolated_python,
    subprocess_failure,
)

REPO = Path(__file__).resolve().parents[1]

_PRODUCTION = "packet_tracer_mcp"
_TEST_NAMESPACE = "src.packet_tracer_mcp"


def _preflight(
    *,
    root: Path | None = None,
    executable: str | None = None,
    environment_prefix: str | None = None,
    package_file: str | None | Exception = "",
    modules: dict[str, object] | None = None,
) -> ImportIsolationPreflight:
    """Todo inyectado: nunca se toca el `sys.modules` real del proceso de test."""
    resolved_root = REPO if root is None else root
    if package_file == "":
        package_file = str(resolved_root / "src" / _PRODUCTION / "__init__.py")

    def _resolve() -> str | None:
        if isinstance(package_file, Exception):
            raise package_file
        return package_file

    return ImportIsolationPreflight(
        resolved_root,
        executable=lambda: executable or str(checkout_venv_python(resolved_root)),
        environment_prefix=lambda: (
            environment_prefix or str(checkout_venv_root(resolved_root))
        ),
        resolve_package_file=_resolve,
        modules=lambda: {} if modules is None else modules,
    )


class TestTheGateRefusesWhatItMustRefuse:
    def test_two_namespace_identities_are_refused(self):
        """El unico de los tres reproducible HOY en el interprete correcto."""
        result = _preflight(modules={_PRODUCTION: object(), _TEST_NAMESPACE: object()}).ensure_isolated()

        assert result.state is ImportIsolationState.DUAL_IDENTITY
        assert not result.isolated
        assert _TEST_NAMESPACE in result.render()

    def test_a_test_process_is_refused_even_when_everything_else_is_right(self):
        """A suite run is not the live process, and may not be credentialed as one.

        Before the canonical namespace migration this was decided for free: the
        suite imported the package under its own name, so a pytest process
        tripped PRODUCTION_NAMESPACE_NOT_LOADED. With one namespace that
        accident is gone, and a pytest process otherwise satisfies every check.
        The disqualification is therefore stated directly, on the property that
        actually distinguishes the process.
        """
        result = _preflight(
            modules={_PRODUCTION: object(), "pytest": object()},
        ).ensure_isolated()

        assert result.state is ImportIsolationState.TEST_PROCESS
        assert not result.isolated
        assert "pytest" in result.render()

    def test_the_same_observations_without_pytest_are_accepted(self):
        """Positive control: only the test-process fact causes that refusal."""
        result = _preflight(modules={_PRODUCTION: object()}).ensure_isolated()

        assert result.state is ImportIsolationState.ISOLATED
        assert result.isolated

    def test_a_package_outside_the_governed_tree_is_refused(self):
        foreign = REPO.parent / "foreign-checkout" / "src" / _PRODUCTION / "__init__.py"

        result = _preflight(package_file=str(foreign)).ensure_isolated()

        assert result.state is ImportIsolationState.FOREIGN_TREE
        assert not result.isolated

    def test_a_foreign_interpreter_is_refused(self):
        result = _preflight(executable=str(foreign_python(REPO))).ensure_isolated()

        assert result.state is ImportIsolationState.FOREIGN_INTERPRETER
        assert not result.isolated

    def test_a_foreign_environment_cannot_hide_behind_an_in_tree_executable(self):
        result = _preflight(
            environment_prefix=str(REPO.parent / "foreign-environment"),
        ).ensure_isolated()

        assert result.state is ImportIsolationState.FOREIGN_INTERPRETER
        assert not result.isolated

    def test_a_process_without_the_production_namespace_is_refused(self):
        """No cargarlo no es "aislado por defecto": es no ser el proceso vivo."""
        result = _preflight(package_file=None).ensure_isolated()

        assert result.state is ImportIsolationState.PRODUCTION_NAMESPACE_NOT_LOADED
        assert not result.isolated

    def test_an_undeclared_governed_root_is_refused(self):
        """Sin raiz declarada no hay pregunta que responder, y eso no es un pase.

        La raiz la declara quien invoca. Derivarla del propio modulo seria
        circular: si el paquete cargo del arbol equivocado, esa derivacion
        apuntaria al arbol equivocado y la comprobacion pasaria sola.
        """
        result = ImportIsolationPreflight(None).ensure_isolated()

        assert result.state is ImportIsolationState.GOVERNED_ROOT_NOT_DECLARED
        assert not result.isolated


class TestTheGateFailsClosed:
    def test_an_unexpected_error_is_never_a_pass(self):
        result = _preflight(package_file=RuntimeError("boom")).ensure_isolated()

        assert result.state is ImportIsolationState.INDETERMINATE
        assert not result.isolated
        assert "boom" in result.render()

    def test_a_refused_gate_never_runs_the_mutation(self):
        """El gate es el seam que BLOQUEA la mutacion, no solo la reporta."""
        calls: list[str] = []
        preflight = _preflight(modules={_PRODUCTION: object(), _TEST_NAMESPACE: object()})

        result, value = preflight.execute_if_isolated(
            lambda: (calls.append("mutated"), "done")[1],
        )

        assert result.state is ImportIsolationState.DUAL_IDENTITY
        assert value is None
        assert calls == []

    def test_an_isolated_gate_runs_the_mutation_once(self):
        calls: list[str] = []

        result, value = _preflight().execute_if_isolated(
            lambda: (calls.append("mutated"), "done")[1],
        )

        assert result.isolated
        assert value == "done"
        assert calls == ["mutated"]


class TestThisSuiteIsNotALivePreflight:
    """The governance claim, executable against the real running process.

    Running the suite does NOT establish live isolation, and the gate says so
    about *this* process, with nothing injected.

    What changed with the canonical namespace migration: the suite used to
    import the package as `src.packet_tracer_mcp`, so this process simply had
    no production namespace loaded and the gate refused it for that reason.
    The suite now imports the one canonical name, so that incidental
    disqualification is gone and the refusal rests on the property that really
    separates a test run from a live run.
    """

    def test_the_pytest_process_is_refused_because_it_is_not_the_live_process(self):
        assert _TEST_NAMESPACE not in sys.modules
        assert _PRODUCTION in sys.modules
        assert "pytest" in sys.modules

        result = ImportIsolationPreflight(REPO).ensure_isolated()

        assert result.state is ImportIsolationState.TEST_PROCESS
        assert not result.isolated

    def test_the_check_never_imports_the_production_namespace_itself(self):
        """Observing must not create the condition being observed.

        If the resolver imported `packet_tracer_mcp` to read its `__file__`, it
        would manufacture a loaded namespace inside the very process it claims
        to audit, and the answer would be about the audit rather than about the
        process.

        Observing this by looking at the real `sys.modules` is not possible in
        any process that can run the gate: the gate lives inside the package,
        so importing it imports the package first. Before the canonical
        namespace migration the suite hid that -- it loaded the package under
        the retired name, leaving the production name genuinely absent -- and
        the assertion passed for a reason that no longer exists.

        The contract is therefore measured at the seam that carries it: given a
        module mapping without the production namespace, the default resolver
        must answer "not loaded" instead of importing the package to find out.
        """
        preflight = ImportIsolationPreflight(
            REPO,
            executable=lambda: str(checkout_venv_python(REPO)),
            environment_prefix=lambda: str(checkout_venv_root(REPO)),
            modules=lambda: {},
        )

        result = preflight.ensure_isolated()

        assert result.state is ImportIsolationState.PRODUCTION_NAMESPACE_NOT_LOADED
        assert not result.isolated


class TestARealGovernedProcessPasses:
    def test_all_three_checks_pass_in_a_process_that_loads_only_production(self):
        """El unico proceso donde ISOLATED es afirmable: uno vivo, en subprocess."""
        code = (
            "import sys\n"
            "from packet_tracer_mcp.infrastructure.execution.import_isolation_preflight "
            "import ImportIsolationPreflight\n"
            f"r = ImportIsolationPreflight(r'{REPO}').ensure_isolated()\n"
            "print(r.state.value)\n"
        )
        out = run_isolated_python(code, cwd=REPO)

        assert out.returncode == 0, subprocess_failure(out)
        assert out.stdout.strip() == "ISOLATED", out.stdout + out.stderr


class TestTheGovernedRootIsDeclaredNotGuessed:
    def test_the_env_var_declares_the_root(self, monkeypatch):
        monkeypatch.setenv("PT_MCP_GOVERNED_ROOT", str(REPO))

        assert governed_root_from_env() == REPO

    def test_an_unset_env_var_declares_nothing(self, monkeypatch):
        monkeypatch.delenv("PT_MCP_GOVERNED_ROOT", raising=False)

        assert governed_root_from_env() is None
