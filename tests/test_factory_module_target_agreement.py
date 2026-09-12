"""Agreement between the target production selected and the one reported back.

The mutation script reports the target it acted on, and production compares it
with the target it selected. That comparison had no intentional test: the only
mismatch it ever saw was an accidental one, where a fixture resolved to slot 0
and a hand-written response named slot 1. The response builder now derives the
target, so an accident like that cannot recur - which makes it worth stating
the disagreement deliberately instead.

Each case here asks `tests/support/factory_module_cases` for a target that
differs on exactly one dimension, so what is being contradicted is visible in
the test rather than buried in a transcribed JSON block.
"""

from __future__ import annotations

import pytest

from src.packet_tracer_mcp.infrastructure.execution.factory_module_preparation import (
    PacketTracerFactoryModulePreparer,
)
from tests.support.factory_module_cases import (
    BUILD,
    DEVICE_MODEL,
    DEVICE_NAME,
    foreign_target,
    installation_response,
    runtime_observation,
)


class _Replies:
    """Scripted replies, queueable so a reply can derive from an observation."""

    def __init__(self, *replies: str | None) -> None:
        self.replies = list(replies)
        self.scripts: list[str] = []

    def __call__(self, script: str, _timeout: float) -> str | None:
        self.scripts.append(script)
        if not self.replies:
            raise AssertionError("Unexpected Packet Tracer dispatch")
        return self.replies.pop(0)

    def queue(self, *replies: str | None) -> None:
        self.replies.extend(replies)


def _observed() -> tuple[PacketTracerFactoryModulePreparer, _Replies, object]:
    transport = _Replies(runtime_observation())
    preparer = PacketTracerFactoryModulePreparer(transport, BUILD)
    before = preparer.observe_required_module(DEVICE_NAME, DEVICE_MODEL)
    return preparer, transport, before


@pytest.mark.parametrize(
    "field,value",
    [
        pytest.param("slot_index", 99, id="slot-index"),
        pytest.param("container_navigation_path", (7,), id="container-path"),
        pytest.param("module_type", 18, id="module-type"),
    ],
)
def test_a_target_that_disagrees_on_any_dimension_never_replays(
    field: str,
    value: object,
) -> None:
    """A reported target unequal to the selected one is not an acknowledgement."""

    preparer, transport, before = _observed()
    contradicted = foreign_target(before, **{field: value})
    transport.queue(
        installation_response(before, target_override=contradicted),
    )

    installation = preparer.install_required_module(before)

    assert contradicted != before.target
    assert installation.attempted is True
    assert installation.native_ack is None
    assert installation.target is None
    assert "malformed" in installation.message
    assert not installation.refused_before_mutating
    # The one attempt is spent whatever the reply said.
    with pytest.raises(RuntimeError, match="already attempted"):
        preparer.install_required_module(before)
    assert sum(".addModuleAt(" in script for script in transport.scripts) == 1


def test_a_reply_that_reports_no_target_is_still_an_acknowledgement() -> None:
    """Production accepts a reply that declines to name a target."""

    preparer, transport, before = _observed()
    transport.queue(installation_response(before, target_override=None))

    installation = preparer.install_required_module(before)

    assert installation.native_ack is True
    assert installation.target is None


def test_a_corrupt_target_is_currently_read_as_no_target_at_all() -> None:
    """Characterisation, not endorsement.

    A target that disagrees fails closed, but a target that is structurally
    corrupt is swallowed by the same `except ValueError` that allows an absent
    one, so it acknowledges instead. The mutation cannot be misplaced by this -
    verification still re-reads the inventory against the target production
    selected - but the reply is weaker evidence than the disagreement path
    treats it as, and the two paths are inconsistent with each other.
    """

    preparer, transport, before = _observed()
    transport.queue(
        installation_response(before, malformed_target={"slot_index": 1}),
    )

    installation = preparer.install_required_module(before)

    assert installation.native_ack is True
    assert installation.target is None
