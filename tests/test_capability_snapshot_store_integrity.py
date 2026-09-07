"""Reading capability snapshots: absence and corruption are different answers.

`CapabilitySnapshotStore` feeds productive capability evidence. Its `_list`
used to swallow every content-level failure — `ValidationError` is a
`ValueError`, so a malformed, schema-invalid or version-incompatible snapshot
was silently dropped and the read simply returned fewer facts. That turns a
persistence fault into "no evidence", which is a capability answer, and a
quieter one than it deserves: a capability can fall from SUPPORTED to UNKNOWN
because a file on disk got truncated, with nothing said.

The policy these tests pin:

* **no snapshot** — missing directory, empty directory — is `[]`. Absence of
  evidence is a legitimate, deterministic answer.
* **a file listed and then gone** before it could be read is tolerated and
  skipped. Nothing was read, so nothing can be hidden by skipping it.
* **corrupt, schema-invalid or structurally incompatible** is neither of those.
  It raises `CorruptCapabilitySnapshotError`, naming the file, and the read
  yields nothing at all — no partial list, no partial authority.
"""
from __future__ import annotations

import pathlib

import pytest
from pydantic_core import SchemaError

from src.packet_tracer_mcp.domain.enterprise.models.capabilities import (
    CapabilityStatus, EvidenceSource,
)
from src.packet_tracer_mcp.domain.enterprise.models.discovery import (
    CapabilityProbeResult, CapabilitySnapshot, CapabilityVerificationMethod,
    ProbeExecutionStatus, ProbeSession, ProbeSessionResult,
)
from src.packet_tracer_mcp.infrastructure.persistence import capability_snapshot_store
from src.packet_tracer_mcp.infrastructure.persistence.capability_snapshot_store import (
    CapabilitySnapshotStore, CorruptCapabilitySnapshotError,
    UnusableCapabilitySnapshotError, VanishedCapabilitySnapshotError,
)

VERSION = "9.0.1.0858"


def _snapshot(session_id: str = "integrity-fixture", model: str = "3560-24PS") -> CapabilitySnapshot:
    return CapabilitySnapshot(
        packet_tracer_version=VERSION,
        session=ProbeSessionResult(
            session=ProbeSession(session_id=session_id, packet_tracer_version=VERSION),
            results=[CapabilityProbeResult(
                probe_id="layer3-probe", model=model, capability="layer3",
                status=CapabilityStatus.SUPPORTED,
                execution_status=ProbeExecutionStatus.VERIFIED,
                evidence_source=EvidenceSource.CONTROLLED_PROBE,
                configured=True, verified=True, packet_tracer_version=VERSION,
                verification_method=CapabilityVerificationMethod.CLI_PLUS_READBACK,
            )],
        ),
    )


def _store(tmp_path: pathlib.Path, name: str = "capabilities") -> CapabilitySnapshotStore:
    return CapabilitySnapshotStore(tmp_path / name)


def _version_dir(store: CapabilitySnapshotStore) -> pathlib.Path:
    return store.base_dir / "runtime" / VERSION


# --------------------------------------------------------------------------
# Absence is an answer, and it is not corruption.
# --------------------------------------------------------------------------

def test_a_missing_store_is_no_evidence_not_an_error(tmp_path):
    assert _store(tmp_path, "never-created").list_runtime(VERSION) == []


def test_an_empty_store_is_no_evidence_not_an_error(tmp_path):
    store = _store(tmp_path)
    _version_dir(store).mkdir(parents=True)
    assert store.list_runtime(VERSION) == []


# --------------------------------------------------------------------------
# The productive read is unaffected.
# --------------------------------------------------------------------------

def test_a_valid_snapshot_round_trips(tmp_path):
    store = _store(tmp_path)
    store.save_runtime(_snapshot())
    listed = store.list_runtime(VERSION)
    assert len(listed) == 1
    assert listed[0].session.session.session_id == "integrity-fixture"


def test_several_valid_snapshots_all_survive(tmp_path):
    # Snapshots are content-addressed: `stable_hash` blanks session_id and
    # started_at, so distinct files need distinct facts, not distinct sessions.
    store = _store(tmp_path)
    for model in ("3560-24PS", "3650-24PS", "2960-24TT"):
        store.save_runtime(_snapshot(model=model))
    assert len(store.list_runtime(VERSION)) == 3


# --------------------------------------------------------------------------
# Corruption is attributable and fail-closed.
# --------------------------------------------------------------------------

@pytest.mark.parametrize("content, label", [
    ("{\"not closed\": ", "malformed json"),
    ("", "empty file"),
    ("null", "json null"),
    ("[1, 2, 3]", "json array"),
    ("{\"hello\": \"world\"}", "valid json, wrong shape"),
])
def test_an_unusable_snapshot_is_attributable_not_silently_dropped(tmp_path, content, label):
    store = _store(tmp_path)
    directory = _version_dir(store)
    directory.mkdir(parents=True)
    broken = directory / "broken.json"
    broken.write_text(content, encoding="utf-8")

    with pytest.raises(CorruptCapabilitySnapshotError) as raised:
        store.list_runtime(VERSION)
    assert raised.value.path == broken
    assert "broken.json" in str(raised.value), label


def test_a_truncated_previously_valid_snapshot_is_attributable(tmp_path):
    store = _store(tmp_path)
    written = store.save_runtime(_snapshot())
    body = written.read_text(encoding="utf-8")
    written.write_text(body[: len(body) // 2], encoding="utf-8")

    with pytest.raises(CorruptCapabilitySnapshotError) as raised:
        store.list_runtime(VERSION)
    assert raised.value.path == written


def test_a_structural_schema_error_is_attributable_too(tmp_path, monkeypatch):
    """`SchemaError` is not a `ValueError`, so it used to escape raw.

    A raw pydantic internal error crossing the persistence boundary tells the
    caller nothing about which file caused it. Whatever its origin, it is
    reported the same way as any other unusable snapshot: by name.
    """
    store = _store(tmp_path)
    written = store.save_runtime(_snapshot())

    def _raise(*_args, **_kwargs):
        raise SchemaError("Uncaught `PydanticUseDefault` exception")

    monkeypatch.setattr(CapabilitySnapshot, "model_validate_json", _raise)
    with pytest.raises(CorruptCapabilitySnapshotError) as raised:
        store.list_runtime(VERSION)
    assert raised.value.path == written


def test_one_corrupt_file_never_yields_partial_authority(tmp_path):
    """The survivors are not returned. Half a read is not a smaller truth."""
    store = _store(tmp_path)
    store.save_runtime(_snapshot(session_id="good-1"))
    store.save_runtime(_snapshot(session_id="good-2"))
    (_version_dir(store) / "corrupt.json").write_text("{", encoding="utf-8")

    with pytest.raises(CorruptCapabilitySnapshotError):
        store.list_runtime(VERSION)


def test_corruption_does_not_become_a_negative_capability_fact(tmp_path):
    """The read fails; it does not quietly answer "no evidence for this model"."""
    from src.packet_tracer_mcp.infrastructure.catalog.capability_providers import (
        RuntimeCapabilityProvider,
    )
    store = _store(tmp_path)
    store.save_runtime(_snapshot())
    (_version_dir(store) / "corrupt.json").write_text("{", encoding="utf-8")

    provider = RuntimeCapabilityProvider(store, VERSION)
    with pytest.raises(CorruptCapabilitySnapshotError):
        provider.evidence_for("3560-24PS")


def test_find_cached_refuses_to_answer_over_a_corrupt_directory(tmp_path):
    store = _store(tmp_path)
    store.save_runtime(_snapshot())
    (_version_dir(store) / "corrupt.json").write_text("{", encoding="utf-8")

    with pytest.raises(CorruptCapabilitySnapshotError):
        store.find_cached(VERSION, ["3560-24PS"], ["layer3"], probe_schema_version=1)


# --------------------------------------------------------------------------
# A file that vanishes mid-read is tolerated, deterministically.
# --------------------------------------------------------------------------

def _vanish(monkeypatch, name: str) -> None:
    """Make one already-enumerated file disappear at read time."""
    original = pathlib.Path.read_text

    def _read(self, *args, **kwargs):
        if self.name == name:
            raise FileNotFoundError(2, "No such file or directory", str(self))
        return original(self, *args, **kwargs)

    monkeypatch.setattr(pathlib.Path, "read_text", _read)


def test_a_file_enumerated_then_gone_is_an_inconsistent_read(tmp_path, monkeypatch):
    """Enumeration already saw it, so its disappearance is not absence.

    The listing observed a set of snapshots. If one of them cannot be read,
    the set that would be returned is not the set that was enumerated, and it
    is not any state the store was ever in. That is an inconsistent read, and
    it is attributed rather than smoothed over.
    """
    store = _store(tmp_path)
    store.save_runtime(_snapshot(session_id="survivor"))
    vanishing = _version_dir(store) / "vanishing.json"
    vanishing.write_text("{}", encoding="utf-8")

    _vanish(monkeypatch, "vanishing.json")
    with pytest.raises(VanishedCapabilitySnapshotError) as raised:
        store.list_runtime(VERSION)
    assert raised.value.path == vanishing
    assert "vanishing.json" in str(raised.value)


def test_a_vanished_file_returns_no_survivors(tmp_path, monkeypatch):
    """The readable snapshot beside it is not a smaller, safer answer."""
    store = _store(tmp_path)
    store.save_runtime(_snapshot(model="3560-24PS"))
    store.save_runtime(_snapshot(model="3650-24PS"))
    vanishing = _version_dir(store) / "vanishing.json"
    vanishing.write_text("{}", encoding="utf-8")

    _vanish(monkeypatch, "vanishing.json")
    with pytest.raises(VanishedCapabilitySnapshotError):
        store.list_runtime(VERSION)


def test_a_vanished_file_gives_the_provider_no_partial_authority(tmp_path, monkeypatch):
    from src.packet_tracer_mcp.infrastructure.catalog.capability_providers import (
        RuntimeCapabilityProvider,
    )
    store = _store(tmp_path)
    store.save_runtime(_snapshot())
    vanishing = _version_dir(store) / "vanishing.json"
    vanishing.write_text("{}", encoding="utf-8")

    _vanish(monkeypatch, "vanishing.json")
    provider = RuntimeCapabilityProvider(store, VERSION)
    with pytest.raises(VanishedCapabilitySnapshotError):
        provider.evidence_for("3560-24PS")


def test_every_unusable_snapshot_shares_one_catchable_base(tmp_path, monkeypatch):
    """Callers that only care "this read did not happen" catch one type."""
    assert issubclass(CorruptCapabilitySnapshotError, UnusableCapabilitySnapshotError)
    assert issubclass(VanishedCapabilitySnapshotError, UnusableCapabilitySnapshotError)

    store = _store(tmp_path)
    store.save_runtime(_snapshot())
    (_version_dir(store) / "corrupt.json").write_text("{", encoding="utf-8")
    with pytest.raises(UnusableCapabilitySnapshotError):
        store.list_runtime(VERSION)


# --------------------------------------------------------------------------
# Isolation: no store may see another's state, or the checkout's.
# --------------------------------------------------------------------------

def test_two_stores_do_not_see_each_other(tmp_path):
    first = _store(tmp_path, "first")
    second = _store(tmp_path, "second")
    first.save_runtime(_snapshot(session_id="only-in-first"))

    assert [item.session.session.session_id for item in first.list_runtime(VERSION)] == ["only-in-first"]
    assert second.list_runtime(VERSION) == []


def test_the_default_store_is_redirected_away_from_the_checkout(tmp_path):
    """The suite must never read the gitignored `data/capabilities` residue.

    That directory is machine state: it holds 72 snapshots on one developer's
    box and none in CI, so a test that reads it composes different evidence
    from the same source SHA.
    """
    default = CapabilitySnapshotStore().base_dir.resolve()
    checkout = (pathlib.Path(__file__).resolve().parents[1] / "data" / "capabilities").resolve()
    assert default != checkout


# --------------------------------------------------------------------------
# Writing: two savers must never share a temporary file.
# --------------------------------------------------------------------------

def test_two_snapshots_can_share_a_hash_but_not_their_bytes():
    """The premise of the write race, stated on its own.

    `stable_hash` deliberately blanks `session_id` and `started_at`, so two
    snapshots of the same facts collapse onto one target file — while their
    serialized bodies still differ in length.
    """
    first = _snapshot(session_id="S")
    second = _snapshot(session_id="a-much-longer-session-identifier-than-the-other")
    assert first.stable_hash() == second.stable_hash()
    assert first.model_dump_json(indent=2) != second.model_dump_json(indent=2)


def test_two_savers_of_one_target_never_share_a_temporary_file(tmp_path, monkeypatch):
    """The write race, pinned by its structural cause rather than by timing.

    The temporary name used to be derived from the target -- and so from the
    content hash -- which meant two savers of one hash opened the same path.
    Because the hash ignores `session_id`, those two bodies are NOT identical,
    so an interleaved write leaves a truncated file that no longer parses.

    Observed once directly: two threads saving hash-colliding snapshots
    produced a `PermissionError` and a corrupt file on disk. That reproduction
    depends on Windows file-locking timing, so what is pinned here is the
    invariant the fix actually establishes -- distinct writers, distinct
    temporary files -- which is deterministic.
    """
    store = _store(tmp_path)
    first = _snapshot(session_id="S")
    second = _snapshot(session_id="a-much-longer-session-identifier-than-the-other")
    assert first.stable_hash() == second.stable_hash()

    import tempfile

    temporaries: list[pathlib.Path] = []
    original = tempfile.mkstemp

    def _record(*args, **kwargs):
        handle, name = original(*args, **kwargs)
        temporaries.append(pathlib.Path(name))
        return handle, name

    monkeypatch.setattr(tempfile, "mkstemp", _record)
    store.save_runtime(first)
    store.save_runtime(second)
    monkeypatch.undo()

    assert len(temporaries) == 2
    assert temporaries[0] != temporaries[1], (
        "both savers of one target used the same temporary file"
    )
    # The temporaries must still be invisible to the reader.
    assert all(item.suffix == ".tmp" for item in temporaries)
    assert len(store.list_runtime(VERSION)) == 1


def test_no_temporary_files_are_left_behind(tmp_path):
    store = _store(tmp_path)
    store.save_runtime(_snapshot())
    assert list(_version_dir(store).glob("*.tmp")) == []


def test_the_temporary_is_created_exclusively_by_the_os(tmp_path, monkeypatch):
    """Uniqueness must be the OS refusing to reuse a name, not luck.

    A random suffix makes a collision unlikely; `O_EXCL` makes it impossible.
    The distinction matters because the loser of a name collision does not get
    an error, it gets someone else's half-written file.
    """
    import tempfile

    store = _store(tmp_path)
    calls: list[dict] = []
    original = tempfile.mkstemp

    def _spy(*args, **kwargs):
        calls.append(kwargs)
        return original(*args, **kwargs)

    monkeypatch.setattr(tempfile, "mkstemp", _spy)
    written = store.save_runtime(_snapshot())

    assert len(calls) == 1, "the temporary must come from an exclusive OS create"
    # Same directory as the target, so the replace stays atomic.
    assert pathlib.Path(calls[0]["dir"]) == written.parent
    assert calls[0].get("suffix") == ".tmp"


def test_an_existing_candidate_name_is_never_clobbered(tmp_path, monkeypatch):
    """Force the first candidate names to one that already exists on disk.

    With exclusive creation the OS refuses that name and `mkstemp` keeps
    looking; a probabilistic scheme would open it and truncate whatever was
    there. The decoy's bytes are the assertion, and the fresh temporary having
    the third name proves the first two were actually rejected.
    """
    import tempfile

    store = _store(tmp_path)
    first = store.save_runtime(_snapshot())
    directory = _version_dir(store)

    second = _snapshot(model="3650-24PS")
    target_name = f"{second.stable_hash()}.json"
    # Exactly the path mkstemp will try first: prefix + candidate + suffix.
    decoy = directory / f"{target_name}.collision.tmp"
    decoy.write_text("decoy bytes that must survive", encoding="utf-8")

    names = iter(["collision", "collision", "fresh-name"])
    monkeypatch.setattr(tempfile, "_get_candidate_names", lambda: names)

    created: list[pathlib.Path] = []
    original = tempfile.mkstemp

    def _record(*args, **kwargs):
        handle, name = original(*args, **kwargs)
        created.append(pathlib.Path(name))
        return handle, name

    monkeypatch.setattr(tempfile, "mkstemp", _record)
    store.save_runtime(second)
    monkeypatch.undo()

    assert decoy.read_text(encoding="utf-8") == "decoy bytes that must survive"
    assert created == [directory / f"{target_name}.fresh-name.tmp"]
    assert first.exists() and (directory / target_name).exists()


def test_a_failed_write_leaves_no_temporary_behind(tmp_path, monkeypatch):
    store = _store(tmp_path)
    store.save_runtime(_snapshot())
    directory = _version_dir(store)

    def _boom(*_args, **_kwargs):
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(pathlib.Path, "replace", _boom)
    with pytest.raises(OSError):
        store.save_runtime(_snapshot(model="3650-24PS"))
    monkeypatch.undo()

    assert list(directory.glob("*.tmp")) == []
    assert len(store.list_runtime(VERSION)) == 1
