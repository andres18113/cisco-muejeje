"""Why the workspace's links stay unread: what Cisco's reference hands over.

`network.device_ports` is where the read-only topology stops (MJ-031, MJ-033).
The next subject is the link between two ports, and the stop is not a choice
this repository made. It is what the installed IpcAPI reference for 9.0.1.0858
documents, re-read here so that the blocker is a measurement rather than a
sentence.

**Every documented route to a link hands over the base interface.**
`Network.getLinkAt(int)` answers a `Link`, and so does `getLink()` on `Port` and
on every other interface that documents it. `Link` documents one member,
`getConnectionType()`. A link's endpoints are documented only on the two
interfaces derived from it — `Cable.getPort1()` and `getPort2()`, and
`Antenna.getPort()` — and no installed member hands over a `Cable`, while the
only one handing over an `Antenna` is asked of an `Antenna` already held.

**Nothing installed says which one a handed-over `Link` is.** `getClassName()`
is on no page, and the `CONNECT_TYPES` values the `Link` page lists name no
interface, so a table from connection type to interface would be a Cisco enum
mirror (MJ-014) and an inference nobody documented. The boundary marks every
handle with the interface its member documents, so even an admitted `Cable`
member would be refused on a `Link`. Reading an endpoint needs target evidence
of what a Script Module is actually handed (MJ-015, `AGENTS.md` rule 6).

When a check here fails, the reference or the allowlist has changed under the
blocker, and the blocker has to be read again before anything is admitted.
"""

from __future__ import annotations

import functools
import hashlib
from collections.abc import Mapping

import pytest

from tests.muejeje.test_platform_reference import (
    INTERFACE_PAGES,
    REFERENCE,
    admitted_entries,
    documented_members,
    requires_installed_reference,
)

# The pages the blocker rests on beyond those an admitted member already cites,
# and the bytes each was read in.
LINK_PAGES = {
    "Link": (
        "class_link.html",
        "0dab984158772796a41b5f4a4e8b03ea6e222159b231e731108d7e6c474374b9",
    ),
    "Cable": (
        "class_cable.html",
        "a55a107a765954e15f1680616f8c53c2c9e3d0f6cb8539aebfe87c81bbbae4b5",
    ),
    "Antenna": (
        "class_antenna.html",
        "c172a0192c3fc0b43270b32455c00e537638a1c191e1fd670044e7c4897a9602",
    ),
}
LINK_INTERFACES = frozenset(LINK_PAGES)
# Documented members of interfaces the boundary already admits that read the
# link subject: its size, a link itself, or the name at a link's other end.
LINK_SUBJECT_MEMBERS = frozenset({
    "Network.getLinkCount",
    "Network.getLinkAt",
    "Port.getLink",
    "Port.getRemotePortName",
})


def link_hand_overs(pages: Mapping[str, str]) -> set[tuple[str, str, str]]:
    """`(page, member, interface)` for every member that hands over a link."""
    return {
        (page, member, returned)
        for page, text in pages.items()
        for member, signatures in documented_members(text).items()
        for returned, _ in signatures
        if returned in LINK_INTERFACES
    }


@functools.cache
def _class_pages() -> dict[str, str]:
    """Every installed class page, without Doxygen's member-index companions."""
    return {
        path.name: path.read_text(encoding="utf-8", errors="replace")
        for path in sorted(REFERENCE.glob("class_*.html"))
        if not path.name.endswith("-members.html")
    }


def _members(page: str) -> dict[str, set[tuple[str, int]]]:
    return documented_members(_class_pages()[page])


def test_the_boundary_admits_nothing_that_reads_a_link():
    """The stop is enforced by the allowlist, not only described beside it."""
    entries = admitted_entries()

    assert not [m for m in entries if m.split(".")[0] in LINK_INTERFACES]
    assert not [m for m, (_, over) in entries.items() if over in LINK_INTERFACES]
    assert not LINK_SUBJECT_MEMBERS & set(entries)
    assert {m.split(".")[0] for m in LINK_SUBJECT_MEMBERS} <= set(INTERFACE_PAGES)


def test_the_hand_over_reader_notices_a_member_that_would_reach_an_endpoint():
    """Asserted in both directions: a converter would be found, a port is not."""
    page = (
        '<td class="memItemLeft" align="right">Cable&#160;</td>'
        '<td class="memItemRight" valign="bottom">asCable (Link)</td>'
        '<td class="memItemLeft" align="right">Port&#160;</td>'
        '<td class="memItemRight" valign="bottom">getPort1 ()</td>'
    )

    assert link_hand_overs({"class_x.html": page}) == {
        ("class_x.html", "asCable", "Cable"),
    }


@requires_installed_reference
@pytest.mark.parametrize("interface", sorted(LINK_PAGES))
def test_each_page_the_blocker_rests_on_is_the_page_this_repository_read(
    interface: str,
):
    page, digest = LINK_PAGES[interface]

    assert hashlib.sha256((REFERENCE / page).read_bytes()).hexdigest() == digest, page


@requires_installed_reference
def test_a_link_documents_its_type_and_only_its_derived_interfaces_its_ends():
    cable = _members(LINK_PAGES["Cable"][0])
    antenna = _members(LINK_PAGES["Antenna"][0])
    network = _members(INTERFACE_PAGES["Network"][0])
    port = _members(INTERFACE_PAGES["Port"][0])

    assert _members(LINK_PAGES["Link"][0]) == {
        "getConnectionType": {("CONNECT_TYPES", 0)},
    }
    assert cable["getPort1"] == cable["getPort2"] == {("Port", 0)}
    assert antenna["getPort"] == {("Port", 0)}
    assert network["getLinkCount"] == {("int", 0)}
    assert network["getLinkAt"] == {("Link", 1)}
    assert port["getLink"] == {("Link", 0)}
    assert port["getRemotePortName"] == {("QString", 0)}


@requires_installed_reference
def test_no_installed_member_hands_over_a_cable_or_an_antenna_from_a_link():
    hand_overs = link_hand_overs(_class_pages())
    by_interface = {
        interface: {(page, member) for page, member, over in hand_overs if over == interface}
        for interface in LINK_INTERFACES
    }

    assert ("class_network.html", "getLinkAt") in by_interface["Link"]
    assert ("class_port.html", "getLink") in by_interface["Link"]
    assert {member for _, member in by_interface["Link"]} == {"getLinkAt", "getLink"}
    assert by_interface["Cable"] == set()
    assert by_interface["Antenna"] == {(LINK_PAGES["Antenna"][0], "getReceiverAt")}


@requires_installed_reference
def test_nothing_installed_says_which_interface_a_link_is():
    pages = _class_pages()
    documentation = pages[LINK_PAGES["Link"][0]].split(
        "Member Function Documentation", 1,
    )[1]

    assert not [page for page, text in pages.items() if "getClassName" in documented_members(text)]
    assert "ETHERNET_STRAIGHT" in documentation, "the connection types are listed"
    assert "Cable" not in documentation and "Antenna" not in documentation
