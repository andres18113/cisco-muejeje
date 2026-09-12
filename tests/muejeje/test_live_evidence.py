"""Where the next manual run's relayed values come from, and what a mismatch undoes.

Split out of `test_live_runbook` when that module reached its line budget, and
split again when the run acquired a transcript model and an accounting model of
its own: here, only where the values a run sends back come from, and what an
unstable attribution does and does not invalidate. What survives the run is
`test_live_transcript`; the status every operation receives is
`test_live_accounting` (MJ-018, MJ-020).

Three defects this module exists for, each found by review:

* the declaration assigned each fixture device a `workspace_index`, a position
  the platform handed a device over at in **one** reading — never identity and
  never placement order (MJ-002);
* all three relayed values were called "addresses". `factory_index` and
  `workspace_index` are addresses in two named domains (MJ-029); `module_type`
  is an opaque value the platform produced, and calling it an address invites
  reading a position into it (MJ-014);
* an unstable workspace attribution disqualified every descendant member,
  erasing answers calls had independently given. It invalidates the
  cross-reading chain, and only that.

None of these gates runs Packet Tracer: what a person is told to do is all this
repository can check (MJ-011, MJ-015)."""

from __future__ import annotations

import re

import pytest

from tests.muejeje.test_live_runbook import runbook_body, runbook_prose

# The values a qualification statement relays from an earlier reading, and what
# each one is. Two are addresses, each in its own named domain; the third is not
# an address at all, and the declaration has to say which is which.
RELAY_INPUTS = {
    "factory_index": "a **factory address**",
    "workspace_index": "a **workspace address**",
    "module_type": "an **opaque platform-produced value**",
}

# The two things an attribution finding could be about. It concerns only the
# second, and the runbook has to write them down as two.
CONTINUITY_SPLIT = (
    "member/API observation what one call answered, in the reading that made it",
    "cross-observation continuity that readings taken through one address "
    "describe one device",
)

# The inventory's own members, which answered before any later reading could
# disagree about what sat at a position.
INVENTORY_MEMBERS = ("Network.getDeviceCount", "Network.getDeviceAt", "Device.getName")

ATTRIBUTION_HEADING = "### What an unstable attribution invalidates, and what it does not"

# A position written next to `workspace_index` anywhere in the declaration.
# There is no legitimate one: the runbook may name the argument, and may say
# which reading publishes it, and may never say what its value will be.
PREDICTED_WORKSPACE_INDEX = re.compile(r"workspace_index[^A-Za-z0-9_]{0,4}\d")


def section_prose(heading: str) -> str:
    """One section of the runbook, from its heading to the next heading."""
    body = runbook_body()
    start = body.index(heading) + len(heading)
    ends = [i for i in (body.find("\n## ", start), body.find("\n### ", start)) if i != -1]
    return " ".join(body[start:min(ends) if ends else len(body)].split())


# ---------------------------------------------------------------------------
# No position is predicted, and each relayed value is named for what it is.
# ---------------------------------------------------------------------------

def test_the_runbook_predicts_no_workspace_position_anywhere():
    """A workspace index is where the platform handed a device over in one reading.

    Writing "Switch0 is at 0" into the declaration turns an observation into an
    expectation, and a run that met a different ordering would record the
    disagreement as the target's mistake rather than as ours.
    """
    found = PREDICTED_WORKSPACE_INDEX.findall(runbook_body())

    assert not found, f"the runbook predicts a workspace position: {found}"


def test_the_fixture_names_devices_without_placing_them():
    prose = runbook_prose()

    assert "2960-24TT named Switch0" in prose
    assert "PC-PT named PC0" in prose
    assert "No position is part of the fixture, and none is predicted here." in prose


@pytest.mark.parametrize("name", sorted(RELAY_INPUTS))
def test_each_relay_input_is_named_for_what_it_is(name: str):
    """Two addresses and one opaque value, each in its own row."""
    assert f"| `{name}` | {RELAY_INPUTS[name]}" in runbook_prose(), name


def test_a_module_type_is_never_called_an_address():
    """It names no position, so nothing may read a position into it (MJ-014).

    The previous revision grouped all three under "address", which is how a
    reader ends up treating a platform-produced vocabulary value as something
    with an order, a range or a meaning this repository could predict.
    """
    prose = runbook_prose()

    assert "**A `module_type` is not an address at all**" in prose
    assert "take an address: a `factory_index`" not in prose
    assert "Every address comes from a reading" not in prose


def test_the_two_addresses_keep_their_named_domains():
    assert (
        "The two addresses keep their named domains (`MJ-029`): a factory "
        "address is never sent where a workspace address is expected"
        in runbook_prose()
    )


def test_a_placeholder_is_never_entered():
    """A literal in the recipe exists so a gate can drive it, and for nothing else."""
    prose = runbook_prose()

    assert "The literal values in the recipe's blocks are **placeholders**." in prose
    assert "**A placeholder is never entered.**" in prose
    assert "one whose input was not observed is not entered at all" in prose


# ---------------------------------------------------------------------------
# The workspace chain, and what an unstable attribution undoes.
# ---------------------------------------------------------------------------

def test_the_workspace_chain_relays_the_address_the_inventory_published():
    """Inventory first, its address reused, and the identity checked back.

    Both dependent readings take the name and the model off the same hand-over
    they take everything else from, so requiring them to re-report the intended
    device is a check their own answers can support.
    """
    prose = runbook_prose()

    assert "**`network.device_inventory` runs first**" in prose
    assert "find the entry whose `name` is `Switch0`" in prose
    assert (
        "Enter `network.device_ports` with **that same observed workspace "
        "address**" in prose
    )
    assert "`name` `Switch0` and `model` `2960-24TT`" in prose


def test_an_unpublished_workspace_address_stops_the_chain_without_searching():
    prose = runbook_prose()

    assert "**If the inventory published none**" in prose
    assert (
        "`network.device_identity` and `network.device_ports` are both "
        "`NOT_EXERCISED_PREREQUISITE_UNAVAILABLE`" in prose
    )
    assert "No further window is requested to look for the device." in prose


def test_an_unstable_attribution_invalidates_continuity_only():
    """Two claims, and the finding is about one of them.

    That readings taken through one address describe one device is a claim
    about *continuity*, and a mismatch refutes it. What each call answered is a
    claim about *that call*, and a later disagreement cannot refute it.
    """
    prose = runbook_prose()

    for line in CONTINUITY_SPLIT:
        assert line in prose, line
    assert "**The finding invalidates continuity, and only continuity.**" in prose
    assert (
        "`WORKSPACE_ATTRIBUTION_UNSTABLE`: the cross-reading chain is **not** "
        "qualified, and each call's own answer still stands" in prose
    ), "the reading table must keep the two apart in its own row"


def test_an_unstable_attribution_leaves_the_inventory_answers_standing():
    """The defect this section corrects, member by member.

    An earlier revision disqualified every descendant member on a mismatch, so
    an inventory that had counted, handed over and named devices perfectly well
    would have lost all three answers because a *later* reading disagreed.
    """
    section = section_prose(ATTRIBUTION_HEADING)
    kept = section.split("**It does not erase what each call answered.**")[1]

    for member in INVENTORY_MEMBERS:
        assert f"`{member}`" in kept, member
    assert "remain observations from the inventory" in kept


# ---------------------------------------------------------------------------
# The factory chain: an observed address, chosen for the evidence it enables.
# ---------------------------------------------------------------------------

def test_the_factory_choice_prefers_a_descriptor_that_emitted_vocabulary():
    """Pick the descriptor that lets the support lookup run on target vocabulary.

    Blindly taking the first descriptor could leave `module_type_support`
    unexercised when a descriptor two rows down had already emitted a type.
    """
    prose = runbook_prose()

    assert "**Choose the factory address inside that window, preferring evidence.**" in prose
    assert (
        "Take the first descriptor in the returned window whose "
        "`supported_module_types` is non-empty" in prose
    )
    assert (
        "If no descriptor in the window emitted one, take the first descriptor "
        "in the window." in prose
    )


def test_the_factory_choice_never_searches_beyond_the_returned_window():
    """Preference is a choice among rows already read, never a reason to read more."""
    prose = runbook_prose()

    assert "**no further window is requested to search for a better descriptor.**" in prose
    assert "choosing a descriptor happens inside the window already returned" in prose


def test_the_factory_chain_relays_only_what_the_platform_emitted():
    """A `module_type` from documentation is a number this target never produced."""
    prose = runbook_prose()

    assert "relay a `module_type` **the platform itself emitted in this run**" in prose
    assert (
        "**No module type is taken from this page, from Cisco's documentation "
        "or from a previous run.**" in prose
    )
    assert "unless a target-produced `module_type` subsequently exists" in prose


def test_relaying_an_input_never_widens_a_request():
    """Bounds are Muejeje's, and a relayed value does not touch them (MJ-029)."""
    assert (
        "Relaying an observed input changes *which* subject is read, never how "
        "much is read" in runbook_prose()
    )


def test_the_readers_above_actually_find_what_they_look_for():
    """Guards the gates above from passing because a pattern matched nothing."""
    assert PREDICTED_WORKSPACE_INDEX.search("workspace_index 0: 2960-24TT")
    assert PREDICTED_WORKSPACE_INDEX.search('{"workspace_index":1}')
    assert not PREDICTED_WORKSPACE_INDEX.search("the `workspace_index` it reports")
    assert "Network.getDeviceCount" in section_prose(ATTRIBUTION_HEADING)
