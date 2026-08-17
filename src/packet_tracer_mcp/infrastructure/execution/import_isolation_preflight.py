"""Preflight de aislamiento de import para el proceso que va a mutar Packet Tracer.

Hermano de `bridge_preflight.py` y con la misma forma: un enum de estados, un
resultado inmutable, y `execute_if_*` como unico seam por el que una operacion
mutante puede pasar.

Que prueba, y por que las tres:

1. INTERPRETE. En esta maquina hay al menos tres interpretes alcanzables y solo
   uno es correcto: el `.venv` local del arbol gobernado resuelve el paquete
   dentro de ese arbol; el `.venv` del checkout principal resuelve al arbol
   equivocado en silencio; el `python` del PATH no lo resuelve en absoluto. La
   eleccion de interprete es la que decide las otras dos comprobaciones, asi que
   dejarla implicita apoyaba el gate sobre un supuesto no declarado.

2. ARBOL. `packet_tracer_mcp.__file__` debe caer dentro del arbol gobernado. Un
   proceso que mutara un workspace real con codigo de otro arbol es exactamente
   el accidente que este gate existe para impedir.

3. IDENTIDAD UNICA. Medido en el interprete CORRECTO, tener ambos namespaces
   cargados produce dos objetos de modulo distintos sobre los MISMOS archivos:

       CapabilityStatus.SUPPORTED is CapabilityStatus.SUPPORTED  ->  False

   Todo `isinstance` y toda comparacion de enum entre ambos falla en silencio.
   Esta comprobacion sobrevive a elegir bien el interprete, y es la unica de las
   tres reproducible hoy.

La raiz gobernada la DECLARA quien invoca; no se deriva de este modulo. Derivarla
de `__file__` seria circular: si el paquete cargo del arbol equivocado, la
derivacion apuntaria a ese mismo arbol equivocado y la comprobacion 2 se
aprobaria sola.

Observar no puede crear lo observado: el resolver por defecto LEE `sys.modules` y
nunca importa `packet_tracer_mcp`, porque importarlo fabricaria la segunda
identidad justo en el proceso que dice auditar.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import TypeVar

#: Namespace de produccion: lo usan el console script `pt-mcp` y `python -m`.
PRODUCTION_NAMESPACE = "packet_tracer_mcp"
#: Namespace de tests, fijado por `tests/test_worktree_isolation.py`.
TEST_NAMESPACE = "src.packet_tracer_mcp"

#: Variable por la que el operador declara cual es el arbol gobernado.
GOVERNED_ROOT_ENV_VAR = "PT_MCP_GOVERNED_ROOT"


class ImportIsolationState(str, Enum):
    ISOLATED = "ISOLATED"
    GOVERNED_ROOT_NOT_DECLARED = "GOVERNED_ROOT_NOT_DECLARED"
    FOREIGN_INTERPRETER = "FOREIGN_INTERPRETER"
    PRODUCTION_NAMESPACE_NOT_LOADED = "PRODUCTION_NAMESPACE_NOT_LOADED"
    FOREIGN_TREE = "FOREIGN_TREE"
    DUAL_IDENTITY = "DUAL_IDENTITY"
    INDETERMINATE = "INDETERMINATE"


@dataclass(frozen=True)
class ImportIsolationResult:
    state: ImportIsolationState
    detail: str = ""

    @property
    def isolated(self) -> bool:
        return self.state is ImportIsolationState.ISOLATED

    def render(self) -> str:
        messages = {
            ImportIsolationState.GOVERNED_ROOT_NOT_DECLARED:
                "No se declaro el arbol gobernado; sin raiz declarada no hay nada que verificar.",
            ImportIsolationState.FOREIGN_INTERPRETER:
                "El interprete en ejecucion no pertenece al arbol gobernado.",
            ImportIsolationState.PRODUCTION_NAMESPACE_NOT_LOADED:
                f"Este proceso no tiene cargado {PRODUCTION_NAMESPACE!r}; no es el proceso vivo.",
            ImportIsolationState.FOREIGN_TREE:
                "El paquete de produccion cargo desde fuera del arbol gobernado.",
            ImportIsolationState.DUAL_IDENTITY:
                f"Conviven {PRODUCTION_NAMESPACE!r} y {TEST_NAMESPACE!r} como identidades distintas.",
            ImportIsolationState.INDETERMINATE:
                "El preflight no pudo determinar el aislamiento; se cierra por defecto.",
        }
        message = messages.get(self.state, "Aislamiento de import verificado.")
        return f"{self.state.value}: {message}{f' ({self.detail})' if self.detail else ''}"


T = TypeVar("T")


def governed_root_from_env(
    environ: Mapping[str, str] | None = None,
) -> Path | None:
    """Lee la raiz gobernada declarada por el operador; ausente no es un default."""
    value = (environ if environ is not None else os.environ).get(GOVERNED_ROOT_ENV_VAR, "")
    return Path(value).resolve() if value.strip() else None


def _loaded_production_file(modules: Mapping[str, object]) -> str | None:
    """Lee el `__file__` ya cargado. Nunca importa: eso crearia la 2a identidad."""
    module = modules.get(PRODUCTION_NAMESPACE)
    return None if module is None else getattr(module, "__file__", None)


class ImportIsolationPreflight:
    """Cierra por defecto: cualquier duda es rechazo, nunca un pase."""

    def __init__(
        self,
        governed_root: Path | str | None,
        *,
        executable: Callable[[], str] = lambda: sys.executable,
        resolve_package_file: Callable[[], str | None] | None = None,
        modules: Callable[[], Mapping[str, object]] = lambda: sys.modules,
    ) -> None:
        self._governed_root = Path(governed_root) if governed_root is not None else None
        self._executable = executable
        self._modules = modules
        self._resolve_package_file = (
            resolve_package_file
            if resolve_package_file is not None
            else lambda: _loaded_production_file(self._modules())
        )

    def ensure_isolated(self) -> ImportIsolationResult:
        try:
            return self._evaluate()
        except Exception as exc:  # cerrado por defecto: un error no es un pase
            return ImportIsolationResult(ImportIsolationState.INDETERMINATE, str(exc))

    def execute_if_isolated(
        self, action: Callable[[], T],
    ) -> tuple[ImportIsolationResult, T | None]:
        """Impide que una operacion mutante alcance Packet Tracer sin aislamiento."""
        result = self.ensure_isolated()
        return (result, action()) if result.isolated else (result, None)

    def _evaluate(self) -> ImportIsolationResult:
        if self._governed_root is None:
            return ImportIsolationResult(ImportIsolationState.GOVERNED_ROOT_NOT_DECLARED)
        root = self._governed_root.resolve()

        executable = Path(self._executable()).resolve()
        if not self._within(executable, root):
            return ImportIsolationResult(
                ImportIsolationState.FOREIGN_INTERPRETER, str(executable),
            )

        package_file = self._resolve_package_file()
        if package_file is None:
            return ImportIsolationResult(ImportIsolationState.PRODUCTION_NAMESPACE_NOT_LOADED)
        resolved = Path(package_file).resolve()
        if not self._within(resolved, root / "src" / PRODUCTION_NAMESPACE):
            return ImportIsolationResult(ImportIsolationState.FOREIGN_TREE, str(resolved))

        loaded = self._modules()
        if PRODUCTION_NAMESPACE in loaded and TEST_NAMESPACE in loaded:
            return ImportIsolationResult(
                ImportIsolationState.DUAL_IDENTITY,
                f"{PRODUCTION_NAMESPACE} + {TEST_NAMESPACE}",
            )
        return ImportIsolationResult(ImportIsolationState.ISOLATED, str(resolved))

    @staticmethod
    def _within(candidate: Path, root: Path) -> bool:
        try:
            candidate.relative_to(root)
        except ValueError:
            return False
        return True
