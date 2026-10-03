"""The maintained typed effect checks recovery state before claiming acquisition."""

import pytest

from tests.test_service_dhcp_script_harness import (
    _acquire,
    _runtime,
)
from tests.test_service_dhcp_script_harness import (
    engine as _engine_fixture,
)


@pytest.fixture
def engine(tmp_path):
    """Use the actual generated scripts and persistent independent Node engine."""
    yield from _engine_fixture.__wrapped__(tmp_path)


@pytest.mark.parametrize(
    ("address", "mask"),
    [
        ("192.0.2.10", "255.255.255.0"),
        ("0.0.0.0", "0.0.0.0"),
        ("169.254.999.1", "255.255.0.0"),
        ("169.254.4.2", "255.255.255.0"),
    ],
)
def test_changed_state_inside_the_effect_script_creates_no_claim(engine, address, mask):
    """A prior eligible census cannot authorize a changed endpoint state."""
    item = engine()
    item.state["client"]["port"].update(ip=address, mask=mask)
    item.sync()
    action = _acquire().model_copy(update={"required_address_state": "link_local"})
    [mutation] = _runtime(item).apply_actions([action])
    assert mutation.attempted is False
    assert item.state["client"]["runs"] == 0
    assert item.state["claims"] == {}


def test_an_unreadable_address_at_the_effect_boundary_creates_no_claim(engine):
    """A failed getter refuses the one-shot start before any effect."""
    item = engine(throw_before=["getIpAddress"])
    item.state["client"]["port"].update(ip="169.254.4.2", mask="255.255.0.0")
    item.sync()
    action = _acquire().model_copy(update={"required_address_state": "link_local"})
    [mutation] = _runtime(item).apply_actions([action])
    assert mutation.attempted is False
    assert item.state["client"]["runs"] == 0
    assert item.state["claims"] == {}


def test_a_link_local_subject_is_started_once_through_the_existing_claim(engine):
    """Fresh recovery state admits one call and preserves replay refusal."""
    item = engine()
    item.state["client"]["port"].update(ip="169.254.4.2", mask="255.255.0.0")
    item.sync()
    action = _acquire().model_copy(update={"required_address_state": "link_local"})
    [first] = _runtime(item).apply_actions([action])
    [second] = _runtime(item).apply_actions([action])
    assert first.attempted is True
    assert second.cause == "own_claim_replayed"
    assert item.state["client"]["runs"] == 1
