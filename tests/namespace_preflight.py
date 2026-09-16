"""Fail-closed identity and origin preflight for this checkout's test process.

Why the suite needs its own gate
--------------------------------
`packet_tracer_mcp` resolves through the environment's editable install, which
records one absolute tree.  A `.venv` created for another checkout -- copied,
inherited by a new worktree, or simply invoked by its full path -- therefore
resolves that other checkout's source while the operator edits this one.  The
failure is silent: the tests pass, they just test something else.

This module refuses that process before any test module is imported.  It
observes three things and treats any doubt as a refusal:

1. **Environment.** The running interpreter must belong to an environment that
   lives inside this checkout.  The interpreter decides the other two answers,
   so leaving it implicit would rest the gate on an undeclared assumption.
2. **Origin.** `packet_tracer_mcp.__file__` must resolve under this checkout's
   `src/packet_tracer_mcp`.
3. **Single identity.** `src.packet_tracer_mcp` must not be loaded.  The same
   files imported under two names are two module objects, two classes and two
   enums, so every `isinstance` and enum comparison between them is silently
   false.

Where the root comes from
-------------------------
From this file, which pytest loads by path out of the checkout being tested, so
it identifies that checkout by construction.  This is deliberately *not* how
`packet_tracer_mcp.infrastructure.execution.import_isolation_preflight` works:
that gate audits a process that may already have loaded the package, so
deriving its root from the package would let a package loaded from the wrong
tree approve itself.  Here the root is the observer, not the observed.

Contract
--------
`evaluate()` never raises; it returns the state it observed, and an error while
observing is `INDETERMINATE`, not a pass.  `enforce()` returns an accepted
result or raises `NamespacePreflightError` naming the expected and the observed
values.  Neither imports `src.packet_tracer_mcp`, which would manufacture the
very identity being ruled out.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

#: The one production identity: the console script, `python -m`, and the suite.
PRODUCTION_NAMESPACE = "packet_tracer_mcp"
#: The retired test-only identity. `src/` stays the physical location of the
#: package; it is no longer an import namespace, and loading it is a refusal.
LEGACY_NAMESPACE = "src.packet_tracer_mcp"


class NamespacePreflightState(StrEnum):
    """Every outcome the preflight can observe."""

    ISOLATED = "ISOLATED"
    FOREIGN_INTERPRETER = "FOREIGN_INTERPRETER"
    PRODUCTION_PACKAGE_UNRESOLVED = "PRODUCTION_PACKAGE_UNRESOLVED"
    FOREIGN_PACKAGE_ORIGIN = "FOREIGN_PACKAGE_ORIGIN"
    LEGACY_NAMESPACE_LOADED = "LEGACY_NAMESPACE_LOADED"
    INDETERMINATE = "INDETERMINATE"


class NamespacePreflightError(RuntimeError):
    """Raised instead of running tests whose identity could not be trusted."""


@dataclass(frozen=True)
class NamespacePreflightResult:
    """What the preflight observed, and whether it licenses a test run."""

    state: NamespacePreflightState
    detail: str = ""

    @property
    def accepted(self) -> bool:
        """Report whether this process may be trusted to test this checkout."""
        return self.state is NamespacePreflightState.ISOLATED

    def render(self, checkout_root: Path) -> str:
        """Describe the refusal with the expected root and the observed values."""
        reasons = {
            NamespacePreflightState.FOREIGN_INTERPRETER: (
                "The running interpreter does not belong to an environment "
                "inside this checkout. Create and install this checkout's own "
                "environment instead of reusing another one."
            ),
            NamespacePreflightState.PRODUCTION_PACKAGE_UNRESOLVED: (
                f"{PRODUCTION_NAMESPACE!r} did not resolve. Install this "
                "checkout in editable mode before running the suite."
            ),
            NamespacePreflightState.FOREIGN_PACKAGE_ORIGIN: (
                f"{PRODUCTION_NAMESPACE!r} resolved outside this checkout, so "
                "the suite would validate another tree's source."
            ),
            NamespacePreflightState.LEGACY_NAMESPACE_LOADED: (
                f"{LEGACY_NAMESPACE!r} is loaded. The same files under two "
                "names are two identities, and comparisons across them fail "
                "silently."
            ),
            NamespacePreflightState.INDETERMINATE: (
                "The preflight could not determine identity, so it closes."
            ),
        }
        reason = reasons.get(self.state, "Namespace identity verified.")
        expected = f"expected checkout: {checkout_root}"
        observed = f"observed: {self.detail}" if self.detail else "observed: nothing"
        return f"{self.state.value}: {reason} ({expected}; {observed})"


def _loaded_package_file() -> str | None:
    """Import the production package once and report where it resolved."""
    import packet_tracer_mcp

    return getattr(packet_tracer_mcp, "__file__", None)


def _loaded_namespace_names() -> frozenset[str]:
    """Read the namespaces already present without importing either of them."""
    return frozenset(
        name for name in (PRODUCTION_NAMESPACE, LEGACY_NAMESPACE) if name in sys.modules
    )


class NamespacePreflight:
    """Decide whether this process may be trusted to test this checkout."""

    def __init__(
        self,
        checkout_root: Path | str,
        *,
        executable: Callable[[], str] = lambda: sys.executable,
        environment_prefix: Callable[[], str] = lambda: sys.prefix,
        resolve_package_file: Callable[[], str | None] = _loaded_package_file,
        loaded_namespaces: Callable[[], Iterable[str]] = _loaded_namespace_names,
    ) -> None:
        """Bind the checkout under test and the observations to judge it by."""
        self._checkout_root = Path(checkout_root)
        self._executable = executable
        self._environment_prefix = environment_prefix
        self._resolve_package_file = resolve_package_file
        self._loaded_namespaces = loaded_namespaces

    def evaluate(self) -> NamespacePreflightResult:
        """Observe identity and origin, treating any failure as a refusal."""
        try:
            return self._evaluate()
        except Exception as error:  # fail closed: an error is never a pass
            return NamespacePreflightResult(
                NamespacePreflightState.INDETERMINATE, str(error)
            )

    def enforce(self) -> NamespacePreflightResult:
        """Return the accepted result or refuse the run with a diagnostic."""
        result = self.evaluate()
        if not result.accepted:
            raise NamespacePreflightError(result.render(self._checkout_root.resolve()))
        return result

    def _evaluate(self) -> NamespacePreflightResult:
        root = self._checkout_root.resolve()

        # Keep the invocation path lexical. A POSIX venv interpreter commonly
        # symlinks to the base interpreter outside the checkout, so resolving
        # the target would reject a genuine checkout-local environment. The
        # resolved prefix proves which environment owns the invocation, and
        # requiring the executable inside it stops an arbitrary in-tree symlink
        # from standing in for that environment.
        prefix = Path(self._environment_prefix()).resolve()
        executable = Path(os.path.abspath(self._executable()))
        if not _within(prefix, root) or not _within(executable, prefix):
            return NamespacePreflightResult(
                NamespacePreflightState.FOREIGN_INTERPRETER,
                f"executable={executable}; environment={prefix}",
            )

        package_file = self._resolve_package_file()
        if package_file is None:
            return NamespacePreflightResult(
                NamespacePreflightState.PRODUCTION_PACKAGE_UNRESOLVED
            )
        origin = Path(package_file).resolve()
        if not _within(origin, root / "src" / PRODUCTION_NAMESPACE):
            return NamespacePreflightResult(
                NamespacePreflightState.FOREIGN_PACKAGE_ORIGIN, str(origin)
            )

        loaded = frozenset(self._loaded_namespaces())
        if LEGACY_NAMESPACE in loaded:
            return NamespacePreflightResult(
                NamespacePreflightState.LEGACY_NAMESPACE_LOADED,
                f"loaded namespaces: {', '.join(sorted(loaded))}",
            )
        return NamespacePreflightResult(NamespacePreflightState.ISOLATED, str(origin))


def _within(candidate: Path, root: Path) -> bool:
    """Report whether a resolved path lies inside a root directory."""
    try:
        candidate.relative_to(root)
    except ValueError:
        return False
    return True
