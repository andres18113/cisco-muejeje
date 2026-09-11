"""What Cisco's installed reference says each admitted member is.

The boundary admits interface members, not names (MJ-031), and an entry is only
as good as the citation behind it. So this module re-reads every entry against
Cisco's installed IpcAPI reference for 9.0.1.0858 — the member on *its own
interface's* page, taking that many arguments, handing over that interface when
it hands over an object — and holds the evidence table a reader relies on to one
row per entry, each citing that same page.

**A citation belongs to one interface.** `getType` is documented on `Device`,
`DeviceDescriptor` and `ModuleDescriptor`; `getRootModule` on `Device` hands
over a runtime `Module`, and on `DeviceDescriptor` a `ModuleDescriptor`. A check
that looked a name up anywhere in the reference would let one interface's page
vouch for another's member — the error the qualified boundary exists to remove,
and one the evidence table had already made once, citing `IPC.hardwareFactory()`
to the `HardwareFactory` page.

The pages are read, never copied, and each is hash-pinned here, so a differently
generated reference fails loudly rather than being re-read as the same one. The
re-derivation skips when the target build is not installed; the table gate
always runs (MJ-015, `AGENTS.md` rule 6).
"""

from __future__ import annotations

import hashlib
import html
import re

import pytest

from tests.muejeje.support import INSTALLED_HELP, REPO_ROOT, SCRIPT_ENGINE

REFERENCE = INSTALLED_HELP / "IpcAPI"
# The page each interface is documented on, and the bytes it was read in.
INTERFACE_PAGES = {
    "IPC": (
        "class_i_p_c.html",
        "332eb8d1c99a9b474e761fc0ab5f24b459908fab6271e4d522f71b96b34dc188",
    ),
    "HardwareFactory": (
        "class_hardware_factory.html",
        "83658888b521dc689a90289e7d2605452911ea03f3db85f7675345f0d673ccad",
    ),
    "DeviceFactory": (
        "class_device_factory.html",
        "09e6ea044d4807c415b9ea095e0aa6518fd5499b7217a9d1c9a32e0c56b53c96",
    ),
    "DeviceDescriptor": (
        "class_device_descriptor.html",
        "c796b0c86c5a33cf86b5bdd65f971fa7a60d6d44cc38289428886b5353b98d22",
    ),
    "ModuleDescriptor": (
        "class_module_descriptor.html",
        "a553512539e4864992d4e4752890b6877c21953f0dcf221ced85ce1ea840846d",
    ),
    "Network": (
        "class_network.html",
        "23f47a6f29be2b061e4b71e6d50f90738a806eca8c015e52dcdc3992a201194e",
    ),
    "Device": (
        "class_device.html",
        "d8396d07a02115974ff330a32e1b90dbe9847d8f62ebb7079c5039513b559621",
    ),
}
# What a member answers when it answers a value rather than a platform object,
# as the reference spells the type.
VALUE_TYPES = {"int", "bool", "string", "QString", "DeviceType", "ModuleType"}
EVIDENCE_TABLE = "docs/qa/muejeje-pts-offline.md"

ENTRY = re.compile(
    r'"([A-Za-z]+)\.([A-Za-z]+)":\s*\{arity:\s*(\d+),'
    r'\s*hands_over:\s*(?:null|"([A-Za-z]+)")\}'
)
ENTRY_KEY = re.compile(r'"[A-Za-z]+\.[A-Za-z]+":')
# One member row of a Doxygen class page: the return type, then the signature.
MEMBER_ROW = re.compile(
    r'<td class="memItemLeft"[^>]*>(.*?)</td><td class="memItemRight"[^>]*>(.*?)</td>',
    re.DOTALL,
)
TAG = re.compile(r"<[^>]+>")
# A row of the evidence table: the member as a call, then the page it cites.
EVIDENCE_ROW = re.compile(
    r"^\|\s*`([A-Za-z]+)\.([A-Za-z]+)\([^`]*\)`\s*\|\s*`(class_[a-z_]+\.html)`\s*\|",
    re.MULTILINE,
)

requires_installed_reference = pytest.mark.skipif(
    not REFERENCE.is_dir(),
    reason="the target build is not installed; its reference cannot be read",
)


def _allowlist_block() -> str:
    body = (SCRIPT_ENGINE / "platform_adapter.js").read_text(encoding="utf-8")
    return body.split("MUEJEJE_PLATFORM_READ_ONLY_CALLS = {")[1].split("};")[0]


def admitted_entries() -> dict[str, tuple[int, str | None]]:
    """`Interface.member -> (arity, hands_over)`, read from the boundary."""
    return {
        f"{interface}.{member}": (int(arity), hands_over or None)
        for interface, member, arity, hands_over in ENTRY.findall(_allowlist_block())
    }


def documented_members(page: str) -> dict[str, set[tuple[str, int]]]:
    """`member -> {(return type, arity)}` for every member row of a class page."""
    members: dict[str, set[tuple[str, int]]] = {}
    for left, right in MEMBER_ROW.findall(page):
        signature = _cell_text(right)
        if "(" not in signature:
            continue
        name, _, rest = signature.partition("(")
        parameters = rest.rsplit(")", 1)[0].strip()
        arity = parameters.count(",") + 1 if parameters else 0
        members.setdefault(name.strip(), set()).add((_cell_text(left), arity))
    return members


def evidence_rows(text: str) -> list[tuple[str, str]]:
    """`(Interface.member, cited page)` for every row of the evidence table."""
    return [
        (f"{interface}.{member}", page)
        for interface, member, page in EVIDENCE_ROW.findall(text)
    ]


def _cell_text(cell: str) -> str:
    return html.unescape(TAG.sub("", cell)).replace("\xa0", " ").strip()


def _page(interface: str) -> str:
    return (REFERENCE / INTERFACE_PAGES[interface][0]).read_text(
        encoding="utf-8", errors="replace",
    )


def test_every_allowlist_entry_is_in_the_form_this_reader_parses():
    """An entry this reader skipped would be an entry nothing here checked."""
    entries = admitted_entries()

    assert entries, "the reader found no entry"
    assert len(entries) == len(ENTRY_KEY.findall(_allowlist_block()))


def test_every_entry_names_interfaces_whose_pages_are_cited():
    for member, (arity, hands_over) in admitted_entries().items():
        assert member.split(".")[0] in INTERFACE_PAGES, member
        assert hands_over is None or hands_over in INTERFACE_PAGES, member
        assert arity in (0, 1), f"{member}: the boundary has two call shapes"


@requires_installed_reference
@pytest.mark.parametrize("interface", sorted(INTERFACE_PAGES))
def test_each_cited_page_is_the_page_this_repository_read(interface: str):
    page, digest = INTERFACE_PAGES[interface]

    assert hashlib.sha256((REFERENCE / page).read_bytes()).hexdigest() == digest, page


@requires_installed_reference
@pytest.mark.parametrize("member", sorted(admitted_entries()))
def test_every_admitted_member_is_documented_on_its_own_interface(member: str):
    """That page, that arity, that answer — never a neighbour's."""
    interface, name = member.split(".")
    arity, hands_over = admitted_entries()[member]
    documented = documented_members(_page(interface)).get(name, set())
    answers = {returned for returned, count in documented if count == arity}

    assert documented, f"{INTERFACE_PAGES[interface][0]} documents no {name}"
    assert answers, f"{member} is not documented taking {arity} argument(s)"
    if hands_over is None:
        assert answers <= VALUE_TYPES, (member, answers)
    else:
        assert answers == {hands_over}, (member, answers)


@requires_installed_reference
def test_one_interfaces_page_never_vouches_for_anothers_member():
    """Read out of Cisco's own bytes, in both directions."""
    device = documented_members(_page("Device"))
    descriptor = documented_members(_page("DeviceDescriptor"))

    assert device["getRootModule"] == {("Module", 0)}
    assert descriptor["getRootModule"] == {("ModuleDescriptor", 0)}
    assert "Device.getRootModule" not in admitted_entries()
    assert admitted_entries()["DeviceDescriptor.getRootModule"] == (0, "ModuleDescriptor")


def test_the_evidence_table_has_one_row_per_entry_citing_its_own_page():
    """A member cannot be admitted without a row saying what stands behind it."""
    rows = evidence_rows((REPO_ROOT / EVIDENCE_TABLE).read_text(encoding="utf-8"))
    members = [member for member, _ in rows]

    assert len(members) == len(set(members)), "a member has two rows"
    assert set(members) == set(admitted_entries())
    for member, page in rows:
        assert page == INTERFACE_PAGES[member.split(".")[0]][0], member


def test_the_table_reader_finds_rows_and_notices_a_borrowed_citation():
    """The borrowed citation is the one the table used to carry."""
    text = (
        "| `Device.getName()` | `class_device.html` | legacy code only |\n"
        "| `IPC.hardwareFactory()` | `class_hardware_factory.html` | yes |\n"
    )
    rows = evidence_rows(text)

    assert rows == [
        ("Device.getName", "class_device.html"),
        ("IPC.hardwareFactory", "class_hardware_factory.html"),
    ]
    assert rows[1][1] != INTERFACE_PAGES["IPC"][0]
