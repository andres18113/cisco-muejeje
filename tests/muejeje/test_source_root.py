"""What the owned source tree contains, and what may never enter it.

Architecture tests over the real repository, not fixtures. They pin the
boundary that lets `muejeje.pts` evolve independently of the legacy
`EXTENSION/**` extension: which assets ship, whose vocabulary may appear in
them, that no endpoint or arbitrary JavaScript does, and that there is exactly
one lifecycle and one dispatcher (MJ-001, MJ-002, MJ-004, MJ-007, MJ-009).

Which *layers* those sources may name — PTBuilder, a transport, the Cisco
platform — is `test_layer_boundaries`, split out of here when this module
crossed its own line budget (MJ-020).

**Every gate here has to survive the runtime growing.** A rule that would have
to be deleted the first time a packaged image arrived is not a rule; it is a
delay. So the prose gates read only the assets whose bytes are text, and a
suffix in neither class is a failure rather than a default (MJ-021).
"""

from __future__ import annotations

import re

import pytest

from tests.muejeje.measure import (
    BINARY_SUFFIXES,
    PACKAGED_SUFFIXES,
    TEXT_SUFFIXES,
    engine_sources,
    layer_offenders,
    literal_pattern,
    packaged_binary_sources,
    packaged_sources,
    packaged_text_bodies,
    relative,
    symbols_present,
)
from tests.muejeje.support import SOURCE_ROOT

# A consumer's *identifiers*: the project a scenario belongs to, and the device
# names one topology happens to use. These are what MJ-004 excludes.
CONSUMER_PROJECT_IDENTIFIERS = (
    "cp-live", "cp_live", "cplive", "cp-scale", "cp_scale",
)
TOPOLOGY_IDENTIFIERS = ("router0", "switch0", "pc0", "server0", "laptop0")

# Generic networking vocabulary is *not* a consumer identifier. DHCP, VLAN,
# OSPF and PoE are Packet Tracer's domain rather than any one consumer's, and a
# runtime forbidden from naming them could never describe the platform it
# adapts to. An earlier gate listed them beside the project identifiers, which
# made "generic" and "project-specific" indistinguishable.
GENERIC_NETWORKING_VOCABULARY = (
    "dhcp", "vlan", "ospf", "eigrp", "poe", "voice", "ripv2",
)

# A dotted-quad literal is a hard-coded endpoint, which is a topology
# assumption wearing a transport's clothes (MJ-002). The baselined HTTP default
# lives in the requirements; it never lives in the kernel.
ADDRESS_LITERAL = re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}\b")


def _packaged_bodies() -> dict[str, str]:
    return packaged_text_bodies()


def test_owned_source_root_has_an_engine_and_an_interface():
    assert (SOURCE_ROOT / "script-engine").is_dir()
    assert (SOURCE_ROOT / "interface").is_dir()
    assert packaged_sources(), "the owned root must carry at least one packaged source"


# ---------------------------------------------------------------------------
# Not every packaged asset is text.
# ---------------------------------------------------------------------------

def test_every_packaged_asset_is_classified_as_text_or_as_bytes():
    """A suffix in neither set is unclassified, and that is a failure.

    The prose gates below decode what they read. An earlier revision decoded
    the whole packaged inventory, which included `.png`, `.gif` and `.jpg` —
    so the first packaged image would have crashed every one of them with a
    `UnicodeDecodeError` rather than reporting anything about the tree.
    """
    assert TEXT_SUFFIXES.isdisjoint(BINARY_SUFFIXES)
    assert PACKAGED_SUFFIXES == TEXT_SUFFIXES | BINARY_SUFFIXES

    from src.packet_tracer_mcp.infrastructure.pts import inventory

    assert PACKAGED_SUFFIXES == inventory.PACKAGED_SUFFIXES, (
        "what the auditor packages and what the gates sweep must be one set"
    )


def test_a_binary_asset_is_inventoried_and_never_decoded(tmp_path):
    """Asserted on a synthetic tree, because the real one has no image yet.

    A gate that could only be checked once someone shipped a PNG would be
    discovered by the crash it was written to prevent.
    """
    root = tmp_path / "muejeje_pts"
    (root / "interface").mkdir(parents=True)
    (root / "interface/index.html").write_text("<p>text</p>", encoding="utf-8")
    logo = root / "interface/logo.png"
    logo.write_bytes(b"\x89PNG\r\n\x1a\n\xff\xfe invalid utf-8")

    swept = sorted(logical.rsplit("/", 1)[-1] for logical in packaged_text_bodies(root))

    assert [path.name for path in packaged_binary_sources(root)] == ["logo.png"]
    assert swept == ["index.html"], "a binary asset must not be swept as prose"
    with pytest.raises(UnicodeDecodeError):
        logo.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Vocabulary: a consumer's identifiers stay out; the platform's domain does not.
# ---------------------------------------------------------------------------

def test_owned_sources_carry_no_consumer_project_or_topology_identifier():
    offenders = layer_offenders(
        _packaged_bodies(),
        [
            literal_pattern(symbol)
            for symbol in CONSUMER_PROJECT_IDENTIFIERS + TOPOLOGY_IDENTIFIERS
        ],
        adapters=(),
    )
    assert not offenders, (
        "Muejeje is project-independent; a consumer's own identifiers may not "
        f"appear in its sources: {offenders}"
    )


def test_the_vocabulary_gate_rejects_identifiers_without_rejecting_the_domain():
    """The correction, asserted in both directions on synthetic sources.

    Rejecting `dhcp` as if it were consumer-specific would forbid the runtime
    from ever naming what Packet Tracer does, so the gate has to separate "a
    consumer's project" from "the platform's domain" rather than treat every
    networking word as the former.
    """
    identifiers = CONSUMER_PROJECT_IDENTIFIERS + TOPOLOGY_IDENTIFIERS
    domain = "var note = 'DHCP, VLAN, OSPF and PoE are the platform domain';"
    scenario = "var note = 'this is the CP-LIVE Router0 topology';"

    assert symbols_present(domain, identifiers) == []
    assert symbols_present(domain, GENERIC_NETWORKING_VOCABULARY)
    assert sorted(symbols_present(scenario, identifiers)) == ["cp-live", "router0"]


def test_owned_sources_hardcode_no_endpoint_address():
    offenders = [
        f"{path}: {found.group(0)}"
        for path, body in sorted(_packaged_bodies().items())
        for found in [ADDRESS_LITERAL.search(body)]
        if found is not None
    ]
    assert not offenders, (
        f"the kernel is transport-agnostic; an endpoint is a consumer's: {offenders}"
    )


def test_owned_sources_execute_no_arbitrary_javascript():
    """No `eval`, no `new Function`, no `setTimeout`-with-a-string (MJ-009)."""
    offenders: list[str] = []
    for logical, body in sorted(_packaged_bodies().items()):
        for pattern in (r"\beval\s*\(", r"\bnew\s+Function\b", r"\bFunction\s*\("):
            if re.search(pattern, body):
                offenders.append(f"{logical}: {pattern}")
    assert not offenders, (
        f"V6 admits typed operations only; arbitrary JS is a V5 surface: {offenders}"
    )


# ---------------------------------------------------------------------------
# One lifecycle, one dispatcher. Two of either means two answers to "what ran".
# ---------------------------------------------------------------------------

def _engine_bodies() -> dict[str, str]:
    return {relative(path): path.read_text(encoding="utf-8") for path in engine_sources()}


@pytest.mark.parametrize("symbol", ["main", "cleanUp"])
def test_exactly_one_lifecycle_entry_point_exists(symbol: str):
    pattern = re.compile(rf"^function\s+{symbol}\s*\(", re.MULTILINE)
    owners = [
        name for name, body in _engine_bodies().items() if pattern.search(body)
    ]
    assert owners == ["muejeje_pts/script-engine/lifecycle.js"], (
        f"{symbol}() must be declared exactly once, by lifecycle.js: {owners}"
    )


def test_no_second_dispatcher_can_ever_appear():
    """MJ-007. Vacuously true before V6, strict once the dispatcher exists.

    `test_protocol_v6` asserts the stronger form — that it exists at all. This
    gate is the one that must hold forever: never two answers to "what ran".
    """
    pattern = re.compile(r"^function\s+mcpDispatchV6\s*\(", re.MULTILINE)
    owners = [
        name for name, body in _engine_bodies().items() if pattern.search(body)
    ]
    assert owners in ([], ["muejeje_pts/script-engine/dispatcher_v6.js"]), (
        f"exactly one mcpDispatchV6, owned by the dispatcher: {owners}"
    )


def test_lifecycle_owns_no_dispatch_and_no_operation():
    body = (SOURCE_ROOT / "script-engine/lifecycle.js").read_text(encoding="utf-8")
    for forbidden in ("mcpDispatchV6", "runtime.identify", "JSON.parse"):
        assert forbidden not in body, (
            f"lifecycle.js owns main()/cleanUp() only; {forbidden} belongs elsewhere"
        )
