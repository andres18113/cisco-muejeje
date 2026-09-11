"""What this artifact declares about its own platform surface.

An exemption from a layer gate is only as good as the declaration behind it, so
the declarations live here with the rules that check them. A registry that
could be pointed at `core.js` would be a switch for turning the boundaries off
(MJ-019, MJ-021, MJ-031).

Three registries, three different claims: which files may name `ipc`, which are
platform adapters, and which carry platform vocabulary at all. They are
separate because they are not the same set — an adapter that reads through the
boundary needs no `ipc` exemption, and the file that says what a *reading* is
makes no call whatever. Adding to any of them is an edit here, which is the
point: a platform file arrives visibly rather than by matching a naming
convention.

Split out of `test_layer_boundaries` when that module crossed its own line
budget: declaring the surface and gating the kernel against it are two
responsibilities (MJ-018, MJ-020).
"""

from __future__ import annotations

import pytest

from tests.muejeje.measure import layer_offenders, literal_pattern, packaged_text_bodies
from tests.muejeje.support import REPO_ROOT, repo_manifest

# Declared adapters, by path. Only a declared adapter may name the layer it
# adapts; every other packaged source is kernel and may not. Declaring one is
# an edit to this gate, which is the point: an adapter arrives visibly, and
# every declaration is checked against the rules below.
TRANSPORT_ADAPTER_FILES: tuple[str, ...] = ()
IPC_ADAPTER_FILES: tuple[str, ...] = (
    # The read-only platform-call boundary (MJ-031): the one file that names
    # `ipc`, and the one function every platform call goes through. What it may
    # call is gated in `test_platform_adapter`; the declaration here is what
    # makes naming `ipc` legal in that one file and a violation in every other.
    "muejeje_pts/script-engine/platform_adapter.js",
)
# Every declared platform adapter: the boundary, and the subject adapters that
# read one thing each *through* it. They name no platform object of their own —
# which is why only the boundary needs the `ipc` exemption — but the
# declaration rules below apply to all of them.
PLATFORM_ADAPTER_FILES: tuple[str, ...] = IPC_ADAPTER_FILES + (
    "muejeje_pts/script-engine/network_adapter.js",
    "muejeje_pts/script-engine/network_identity_adapter.js",
    "muejeje_pts/script-engine/platform_device_adapter.js",
    "muejeje_pts/script-engine/platform_module_adapter.js",
    "muejeje_pts/script-engine/platform_support_adapter.js",
)
# Every packaged source that carries platform vocabulary: the adapters, and the
# file that declares what a platform reading *is*. That file names no platform
# object, so it needs no exemption; it is declared because the enum-mirror gate
# reads this set rather than only the adapters (MJ-014, MJ-029).
PLATFORM_SOURCE_FILES: tuple[str, ...] = PLATFORM_ADAPTER_FILES + (
    "muejeje_pts/script-engine/platform_reading.js",
)
# The vocabulary a platform reading is made of: what an outcome is called, why
# one was unavailable, and which calls the boundary admits. Naming any of it is
# answering for the platform, which is what a declared platform source is for.
#
# All four unavailable reasons, not three. `MEMBER_ABSENT` was missing from this
# sweep, so the one word that says "nothing was called" could have been named
# from a kernel file with no gate watching — and that is the reason a reader is
# most likely to reach for when inventing a reading.
READING_VOCABULARY = (
    "MUEJEJE_PLATFORM_ABSENT", "MUEJEJE_PLATFORM_MEMBER_ABSENT",
    "MUEJEJE_PLATFORM_CALL_FAILED",
    "MUEJEJE_PLATFORM_UNUSABLE", "MUEJEJE_PLATFORM_OBSERVED",
    "MUEJEJE_PLATFORM_UNAVAILABLE", "MUEJEJE_PLATFORM_READ_ONLY_CALLS",
)
# The bounds themselves. An operation may reference one to declare an argument
# rule; exactly one file may define them.
PLATFORM_BOUNDS = "MUEJEJE_PLATFORM_LIMITS"

# What a declared adapter must be. Without these, the layer gate could be
# silenced by declaring `core.js` an adapter, which is the one way a boundary
# like this fails without anybody noticing.
ADAPTER_SUFFIX = "_adapter.js"
# An adapter adapts. It does not answer a request, shape an envelope, or decide
# what is admitted; those belong to the kernel it is called from (MJ-019).
ADAPTER_MAY_NOT_NAME = (
    "mcpDispatchV6", "muejejeV6Ok", "muejejeV6Fail", "muejejeV6OperationTable",
    "MUEJEJE_V6_ERRORS", "MUEJEJE_CORE",
)

DECLARED_ADAPTERS = sorted(
    set(TRANSPORT_ADAPTER_FILES) | set(PLATFORM_ADAPTER_FILES)
)


def _packaged_bodies() -> dict[str, str]:
    return packaged_text_bodies()


def adapter_declaration_error(logical: str, artifact_inputs: set[str]) -> str | None:
    """Why `logical` may not be declared an adapter, or None.

    A declared adapter is an exemption from the layer gates, so the
    declaration itself is checked: it has to name a file that ships, and the
    name has to say what it is. Otherwise the exemption is a way to turn the
    gate off.
    """
    if not logical.endswith(ADAPTER_SUFFIX):
        return f"an adapter's name must end with {ADAPTER_SUFFIX}: {logical}"
    if logical not in artifact_inputs:
        return f"a declared adapter must be a declared artifact input: {logical}"
    if not (REPO_ROOT / logical).is_file():
        return f"a declared adapter must exist: {logical}"
    return None


@pytest.mark.parametrize("logical", DECLARED_ADAPTERS)
def test_every_declared_adapter_is_a_file_that_ships_and_says_so(logical: str):
    inputs = set(repo_manifest()["artifact_inputs"])
    assert adapter_declaration_error(logical, inputs) is None


@pytest.mark.parametrize("logical", DECLARED_ADAPTERS)
def test_a_declared_adapter_adapts_and_does_not_answer(logical: str):
    body = (REPO_ROOT / logical).read_text(encoding="utf-8")
    named = [symbol for symbol in ADAPTER_MAY_NOT_NAME if symbol in body]
    assert named == [], (
        f"{logical} is an adapter; dispatching, shaping an envelope and "
        f"reading core belong to the kernel that calls it: {named}"
    )


def test_the_declared_adapter_registries_are_what_this_artifact_ships():
    """A registry is evidence, and an empty one is a claim, not an omission.

    Adding an entry is an edit to this assertion, which is what makes an
    adapter arrive visibly rather than by a file quietly matching a naming
    convention. One platform adapter ships; no transport adapter does, and no
    transport exists for one to adapt (MJ-026).
    """
    assert TRANSPORT_ADAPTER_FILES == ()
    assert IPC_ADAPTER_FILES == ("muejeje_pts/script-engine/platform_adapter.js",)
    assert PLATFORM_ADAPTER_FILES == (
        "muejeje_pts/script-engine/platform_adapter.js",
        "muejeje_pts/script-engine/network_adapter.js",
        "muejeje_pts/script-engine/network_identity_adapter.js",
        "muejeje_pts/script-engine/platform_device_adapter.js",
        "muejeje_pts/script-engine/platform_module_adapter.js",
        "muejeje_pts/script-engine/platform_support_adapter.js",
    )
    assert set(PLATFORM_ADAPTER_FILES) < set(PLATFORM_SOURCE_FILES)


def test_the_vocabulary_of_a_reading_stays_inside_the_platform_sources():
    """What a platform reading *is* has one home, and one definition site.

    An operation may name a declared bound to state an argument rule, because
    the alternative is a second copy of that number. What it may not do is
    shape a reading: a kernel file that assembled one would be reporting a
    platform observation from outside every gate that holds those honest
    (MJ-029, MJ-031).
    """
    offenders = layer_offenders(
        _packaged_bodies(),
        [literal_pattern(name) for name in READING_VOCABULARY],
        adapters=PLATFORM_SOURCE_FILES,
    )
    definitions = [
        logical for logical, body in _packaged_bodies().items()
        if f"{PLATFORM_BOUNDS} = {{" in body
    ]

    assert not offenders, f"declare these in PLATFORM_SOURCE_FILES first: {offenders}"
    assert len(definitions) == 1 and definitions[0] in PLATFORM_SOURCE_FILES, (
        f"the platform bounds have one definition site: {definitions}"
    )


def test_the_reading_vocabulary_gate_tells_a_bound_from_a_reading():
    """Asserted on synthetic sources, so the exception cannot become a hole."""
    rule = {"platform_x.js": "var A = {max: MUEJEJE_PLATFORM_LIMITS.MAX_FACTORY_WINDOW};"}
    reading = {"core.js": "return {resolution: MUEJEJE_PLATFORM_OBSERVED};"}
    patterns = [literal_pattern(name) for name in READING_VOCABULARY]

    assert layer_offenders(rule, patterns, adapters=()) == []
    assert layer_offenders(reading, patterns, adapters=()) == [
        "core.js: MUEJEJE_PLATFORM_OBSERVED"
    ]


def test_the_adapter_declaration_rule_refuses_a_kernel_file():
    """Asserted in every direction, so the exemption cannot become a switch.

    Declaring `core.js` an adapter would silence the layer gates for the one
    file they exist to protect, so the declaration is checked rather than
    trusted. Each reason is exercised here because the registries themselves
    are empty, and a check nobody has run is a check nobody can rely on.
    """
    shipped = "muejeje_pts/script-engine/core.js"
    missing = "muejeje_pts/script-engine/absent_adapter.js"
    inputs = {shipped, missing}

    assert "must end with" in (adapter_declaration_error(shipped, inputs) or "")
    assert "declared artifact input" in (
        adapter_declaration_error(missing, {shipped}) or ""
    )
    assert "must exist" in (adapter_declaration_error(missing, inputs) or "")
    assert not (REPO_ROOT / missing).exists(), "the missing-file case needs a gap"
