"""What Cisco's reference says about a workspace link, and what that admits.

`network.link_inventory` and `network.link_endpoints` read the workspace's links
(MJ-031). The installed IpcAPI reference for 9.0.1.0858 is why most of what they
call cannot be DOCUMENTED, and it is re-read here so that the split between the
two evidence bases is a measurement rather than a sentence.

**Every documented route to a link hands over the base interface.**
`Network.getLinkAt(int)` answers a `Link`, and so does `Port.getLink()`. `Link`
documents one member, `getConnectionType()`. A link's ends are documented only on
`Cable` and `Antenna`, and no installed member hands over a `Cable`.

**So the ends are TARGET_EVIDENCED on `Link`, and nothing decides what kind of
link one is.** `Link.getPort1` and `Link.getPort2` are admitted because they
answered on the object `Network.getLinkAt` hands over on 9.0.1.0858 — not because
`Cable` documents members of those names: no interface inherits another's here,
and no `Cable` or `Antenna` member is admitted. `getClassName()` is on no page
and the `CONNECT_TYPES` values name no interface, so the connection type is
published as the platform's number and never translated (MJ-014). A link that
does not offer its ends is `PLATFORM_MEMBER_ABSENT`, never a link without any;
`test_network_link_endpoints` drives that.

**No member that addresses an end by name is admitted.**
`Port.getRemotePortName()` is a name with no device, and `Cable.getOtherPort()`
takes a device name and a port name; relating either would be the name join
MJ-031 forbids. `Port.getLink()` is a second route to a link the enumeration
already reaches, and is not admitted either.

When a check here fails, the reference or the allowlist has moved under these
readings, and the basis of each link member has to be read again.
"""

from __future__ import annotations

import functools
import hashlib
import re
from collections.abc import Mapping

import pytest

from tests.muejeje.measure import js_code_only, packaged_text_bodies
from tests.muejeje.test_platform_reference import (
    INTERFACE_PAGES,
    REFERENCE,
    admitted_entries,
    documented_members,
    requires_installed_reference,
)

# The pages the link readings rest on beyond those an admitted member already
# cites, and the bytes each was read in. `Link` is cited by its own members.
DERIVED_LINK_PAGES = {
    "Cable": (
        "class_cable.html",
        "a55a107a765954e15f1680616f8c53c2c9e3d0f6cb8539aebfe87c81bbbae4b5",
    ),
    "Antenna": (
        "class_antenna.html",
        "c172a0192c3fc0b43270b32455c00e537638a1c191e1fd670044e7c4897a9602",
    ),
}
LINK_INTERFACES = frozenset({"Link", *DERIVED_LINK_PAGES})
# Everything the boundary admits that reads the link subject, by basis.
LINK_MEMBERS = frozenset({
    "Network.getLinkCount", "Network.getLinkAt", "Link.getConnectionType",
    "Link.getObjectUuid", "Link.getPort1", "Link.getPort2",
})
# Documented members that would reach a link or an end some other way.
UNADMITTED_ROUTES = frozenset({
    "Port.getLink", "Port.getRemotePortName", "Cable.getOtherPort",
    "Cable.getPort1", "Cable.getPort2", "Antenna.getPort",
})
# A connection-type name as the `Link` page lists it, e.g. `ETHERNET_STRAIGHT`.
CONNECTION_TYPE_NAME = re.compile(r"\b[A-Z][A-Z]+(?:_[A-Z]+)*\b")


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


def _members(interface: str) -> dict[str, set[tuple[str, int]]]:
    pages = {**INTERFACE_PAGES, **DERIVED_LINK_PAGES}
    return documented_members(_class_pages()[pages[interface][0]])


def test_the_boundary_reads_links_on_link_and_never_on_a_derived_interface():
    """Admitted on the interface that is handed over, and nowhere a guess would put it."""
    entries = admitted_entries()
    linked = {m for m in entries if m.split(".")[0] in LINK_INTERFACES}

    assert linked == {m for m in LINK_MEMBERS if m.startswith("Link.")}
    assert LINK_MEMBERS <= set(entries)
    assert not [m for m, (_, over) in entries.items() if over in DERIVED_LINK_PAGES]
    assert not UNADMITTED_ROUTES & set(entries)


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
@pytest.mark.parametrize("interface", sorted(DERIVED_LINK_PAGES))
def test_each_derived_page_is_the_page_this_repository_read(interface: str):
    page, digest = DERIVED_LINK_PAGES[interface]

    assert hashlib.sha256((REFERENCE / page).read_bytes()).hexdigest() == digest, page


@requires_installed_reference
def test_a_link_documents_its_type_and_only_its_derived_interfaces_its_ends():
    cable, antenna = _members("Cable"), _members("Antenna")
    network, port = _members("Network"), _members("Port")

    assert _members("Link") == {"getConnectionType": {("CONNECT_TYPES", 0)}}
    assert cable["getPort1"] == cable["getPort2"] == {("Port", 0)}
    assert cable["getOtherPort"] == {("Port", 2)}
    assert antenna["getPort"] == {("Port", 0)}
    assert network["getLinkCount"] == {("int", 0)}
    assert network["getLinkAt"] == {("Link", 1)}
    assert port["getLink"] == {("Link", 0)}
    assert port["getOwnerDevice"] == {("Device", 0)}
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
    assert by_interface["Antenna"] == {(DERIVED_LINK_PAGES["Antenna"][0], "getReceiverAt")}


@requires_installed_reference
def test_nothing_installed_says_which_interface_a_link_is():
    pages = _class_pages()
    documentation = pages[INTERFACE_PAGES["Link"][0]].split(
        "Member Function Documentation", 1,
    )[1]

    assert not [page for page, text in pages.items() if "getClassName" in documented_members(text)]
    assert "ETHERNET_STRAIGHT" in documentation, "the connection types are listed"
    assert "Cable" not in documentation and "Antenna" not in documentation


@requires_installed_reference
def test_no_packaged_source_names_a_connection_type():
    """The names Cisco lists for `CONNECT_TYPES` stay on Cisco's page (MJ-014).

    Read off the installed page rather than written down here, so a table of
    ours cannot hide behind a list of ours. Code only: a comment may say what
    the artifact refuses to carry.
    """
    listed = " ".join(_class_pages()[INTERFACE_PAGES["Link"][0]].split())
    types = listed.split("Connection types:", 1)[1].split("The documentation", 1)[0]
    names = set(CONNECTION_TYPE_NAME.findall(types))
    offenders = [
        f"{logical}: {name}"
        for logical, body in sorted(packaged_text_bodies().items())
        if logical.endswith(".js")
        for name in sorted(names)
        if re.search(rf"\b{name}\b", js_code_only(body))
    ]

    assert {"ETHERNET_STRAIGHT", "FIRST_TYPE", "LAST_TYPE"} <= names, sorted(names)
    assert not offenders, offenders
