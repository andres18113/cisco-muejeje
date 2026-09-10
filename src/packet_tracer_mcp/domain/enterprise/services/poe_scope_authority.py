"""Fail-closed admission against simultaneous PoE authority cohorts."""

from __future__ import annotations

from collections.abc import Iterable

from ..models.capabilities import PoEAuthorizedBinding, PoEAuthorizedScope


def select_authorizing_poe_scope(
    scopes: Iterable[PoEAuthorizedScope],
    required_bindings: Iterable[PoEAuthorizedBinding],
) -> PoEAuthorizedScope | None:
    """Return one scope covering the complete demand without combining cohorts."""

    required = tuple(required_bindings)
    required_set = set(required)
    if not required or len(required_set) != len(required):
        return None

    covering: list[PoEAuthorizedScope] = []
    for scope in scopes:
        active = tuple(scope.active_bindings)
        if (
            type(scope.simultaneous_active_ports) is not int
            or scope.simultaneous_active_ports <= 0
            or scope.simultaneous_active_ports != len(active)
            or len(set(active)) != len(active)
            or len({binding.switch_port for binding in active}) != len(active)
        ):
            continue
        if (
            scope.simultaneous_active_ports >= len(required)
            and required_set <= set(active)
        ):
            covering.append(scope)
    if not covering:
        return None
    return max(
        covering,
        key=lambda scope: (
            scope.simultaneous_active_ports,
            scope.active_bindings,
        ),
    )
