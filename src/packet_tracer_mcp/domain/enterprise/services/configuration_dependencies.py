"""Orden topológico determinista compartido por acciones E5 y E6."""

from __future__ import annotations

import heapq
from typing import Protocol, TypeVar

from ..models.configuration import ConfigurationAction


class ConfigurationDependencyError(ValueError):
    def __init__(self, message: str, action_ids: list[str]) -> None:
        super().__init__(message)
        self.action_ids = action_ids


class DependencyAction(Protocol):
    id: str
    phase: int
    depends_on: list[str]

    @property
    def action_type(self): ...


ActionT = TypeVar("ActionT", bound=DependencyAction)


def _stable_key(action: DependencyAction) -> tuple[int, str, str, str]:
    target_id = getattr(action, "device_id", getattr(action, "host_device_id", ""))
    return (int(action.phase), target_id, action.action_type.value, action.id)


def order_dependency_actions(actions: list[ActionT]) -> list[ActionT]:
    """Kahn + heap: respeta el DAG y desempata por semántica estable."""
    by_id = {action.id: action for action in actions}
    if len(by_id) != len(actions):
        duplicates = sorted(
            action_id for action_id in by_id
            if sum(action.id == action_id for action in actions) > 1
        )
        raise ConfigurationDependencyError("Duplicate action IDs.", duplicates)

    missing = sorted({
        dependency
        for action in actions
        for dependency in action.depends_on
        if dependency not in by_id
    })
    if missing:
        raise ConfigurationDependencyError("Missing action dependencies.", missing)

    indegree = {action.id: len(set(action.depends_on)) for action in actions}
    dependents: dict[str, list[str]] = {action.id: [] for action in actions}
    for action in actions:
        for dependency in set(action.depends_on):
            dependents[dependency].append(action.id)

    ready: list[tuple[tuple[int, str, str, str], str]] = []
    for action in actions:
        if indegree[action.id] == 0:
            heapq.heappush(ready, (_stable_key(action), action.id))

    ordered: list[ActionT] = []
    while ready:
        _, action_id = heapq.heappop(ready)
        action = by_id[action_id]
        ordered.append(action)
        for dependent_id in sorted(dependents[action_id]):
            indegree[dependent_id] -= 1
            if indegree[dependent_id] == 0:
                dependent = by_id[dependent_id]
                heapq.heappush(ready, (_stable_key(dependent), dependent_id))

    if len(ordered) != len(actions):
        cycle = sorted(action_id for action_id, degree in indegree.items() if degree > 0)
        raise ConfigurationDependencyError("Action dependency cycle detected.", cycle)
    return ordered


def order_configuration_actions(
    actions: list[ConfigurationAction],
) -> list[ConfigurationAction]:
    """Nombre público histórico de E5 sobre el sorter compartido."""
    return order_dependency_actions(actions)
