"""Un worktree limpio debe probar SU PROPIO source.

Por que existe:
El `.venv` compartido tiene un editable install que apunta al checkout
principal. Un worktree recien creado hereda ese `.pth`, asi que un import
`packet_tracer_mcp` pelado resolvia al checkout principal aunque el operador
estuviera editando el worktree. Medido durante Runtime Safety R1: 18 archivos
de test validaban codigo que no era el que se estaba modificando, y el fallo
era silencioso -- los tests pasaban, simplemente probaban otra cosa.

Estos tests hacen que esa condicion no pueda volver sin que alguien se entere.
"""

from __future__ import annotations

import ast
from pathlib import Path

import src.packet_tracer_mcp as package_under_test

REPO = Path(__file__).resolve().parents[1]
TESTS = REPO / "tests"

# El unico import legitimo del paquete pelado: vive DENTRO de un string que se
# ejecuta en un subprocess con su propio sys.path. No es un import de este
# proceso y normalizarlo romperia el aislamiento que ese test busca.
_SUBPROCESS_SOURCE_TEST = "test_bridge_security.py"


def test_the_package_under_test_belongs_to_this_worktree():
    resolved = Path(package_under_test.__file__).resolve()

    assert REPO in resolved.parents, (
        "Los tests estan importando el paquete desde fuera de este worktree: "
        f"{resolved}. Revisa el editable install del entorno y `pythonpath` "
        "en pyproject.toml antes de confiar en cualquier resultado."
    )


def test_the_package_resolves_under_the_src_layout_of_this_repo():
    assert Path(package_under_test.__file__).resolve() == (
        REPO / "src" / "packet_tracer_mcp" / "__init__.py"
    )


def _imported_roots(path: Path) -> set[str]:
    """Raices de import reales, via AST.

    Se parsea en vez de usar grep para no confundir un import escrito dentro de
    un string literal con un import de verdad.
    """
    roots: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            roots.add(node.module.split(".")[0])
    return roots


def test_no_test_imports_the_package_outside_the_repo_namespace():
    """Un solo namespace: `src.packet_tracer_mcp`.

    Dos identidades del mismo codigo hacian que un `isinstance` entre objetos
    de una y clases de la otra fuera siempre falso, y una asercion escrita asi
    pasaba sin comprobar nada.
    """
    offenders = sorted(
        path.name
        for path in TESTS.glob("test_*.py")
        if path.name != _SUBPROCESS_SOURCE_TEST
        and "packet_tracer_mcp" in _imported_roots(path)
    )

    assert offenders == [], (
        "Estos tests importan `packet_tracer_mcp` pelado, que resuelve por el "
        f"editable install y no por este worktree: {offenders}"
    )
