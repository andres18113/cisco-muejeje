"""R-ENTRY-06 and R-RET-01: the record is part of the product.

A run record exists so that a run which stopped in the middle leaves behind
what it had already done. That only works if the write is atomic, the path is
contained, the load is validated, and reuse refuses anything it cannot fully
account for. Each of those is a separate way to lose or fabricate evidence, so
each gets its own test.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from packet_tracer_mcp.application.ports.service_run_record import (
    RunRecordPersistenceError,
)
from packet_tracer_mcp.domain.enterprise.models.configuration_runtime import (
    ActionApplicationResult,
    ActionExecutionStatus,
    ConfigurationApplicationResult,
    ConfigurationApplicationStatus,
    ConfigurationFailureCode,
    RuntimeActionMutation,
    sanitized_mutation_snapshot,
)
from packet_tracer_mcp.domain.enterprise.models.execution import (
    DispatchFact,
    FootprintFact,
    PostconditionFact,
    ResultFact,
    TransitionFact,
)
from packet_tracer_mcp.domain.enterprise.models.service_entry import (
    ServiceRunStatus,
    ServiceStage,
    StageTransition,
)
from packet_tracer_mcp.domain.enterprise.models.service_run_record import (
    ServiceRunRecord,
)
from packet_tracer_mcp.infrastructure.persistence.service_run_record_store import (
    UNBOUND_DIRECTORY,
    ServiceRunRecordStore,
    generate_run_id,
)

_DEPLOYMENT = "deploy-hq-1"
_MANIFEST_HASH = "manifest-hash"
_CONFIG_HASH = "cfg-hash"
_ENVIRONMENT_HASH = "env-hash"


def _record(
    *,
    run_id: str = "run-1",
    run_label: str = "",
    deployment_id: str = _DEPLOYMENT,
    stage: ServiceStage = ServiceStage.COMPLETED,
    created_at: datetime | None = None,
    e5_effect_uncertain: bool = False,
    environment_fingerprint_hash: str = _ENVIRONMENT_HASH,
    status: ServiceRunStatus = ServiceRunStatus.VERIFIED,
    configuration_result: ConfigurationApplicationResult | None = None,
) -> ServiceRunRecord:
    moment = created_at or datetime(2026, 9, 17, 10, 0, tzinfo=UTC)
    return ServiceRunRecord(
        run_id=run_id,
        run_label=run_label,
        created_at=moment,
        deployment_id=deployment_id,
        manifest_hash=_MANIFEST_HASH,
        configuration_semantic_hash=_CONFIG_HASH,
        environment_fingerprint_hash=environment_fingerprint_hash,
        bound=bool(deployment_id),
        persisted_stage=stage,
        status=status,
        e5_effect_uncertain=e5_effect_uncertain,
        configuration_result=(
            configuration_result
            if configuration_result is not None
            else _configuration_result()
        ),
        stages=[
            StageTransition(stage=stage, started_at=moment, ended_at=moment),
        ],
    )


def _configuration_result() -> ConfigurationApplicationResult:
    """Build an E5 result carrying the TD-12 snapshot that must survive."""
    mutation = RuntimeActionMutation(
        action_id="cfg/endpoint/pc-1",
        applied=True,
        dispatch=DispatchFact.ACCEPTED,
        result=ResultFact.CORRELATED,
        postcondition=PostconditionFact.SATISFIED,
        transition=TransitionFact.CHANGED,
        footprint=FootprintFact.COVERED,
        attempted=True,
        cause="",
        message="applied",
    )
    return ConfigurationApplicationResult(
        config_plan_id="cfg_reference",
        config_semantic_hash=_CONFIG_HASH,
        source_topology_hash="topo-hash",
        status=ConfigurationApplicationStatus.APPLIED,
        action_results=[
            ActionApplicationResult(
                action_id="cfg/endpoint/pc-1",
                status=ActionExecutionStatus.APPLIED,
                failure_code=ConfigurationFailureCode.NONE,
                dispatch=DispatchFact.ACCEPTED,
                result=ResultFact.CORRELATED,
                postcondition=PostconditionFact.SATISFIED,
                transition=TransitionFact.CHANGED,
                footprint=FootprintFact.COVERED,
                attempted=True,
                received_mutation=sanitized_mutation_snapshot(mutation),
            )
        ],
        mutation_action_ids=["cfg/endpoint/pc-1"],
    )


# -- create, rewrite, load ------------------------------------------------


def test_a_record_is_created_under_its_deployment_and_read_back(tmp_path: Path):
    """The round trip is the contract; a record nobody can read is not one."""
    store = ServiceRunRecordStore(tmp_path)
    record = _record()

    path = Path(store.begin(record))

    assert path.parent.name == _DEPLOYMENT
    assert store.load(_DEPLOYMENT, "run-1") == record


def test_an_unbound_admission_record_is_filed_apart(tmp_path: Path):
    """A3 to A5 refuse before any deployment identity exists.

    Filing it under a guessed deployment id would invent exactly the identity
    the refusal says was never established.
    """
    store = ServiceRunRecordStore(tmp_path)

    path = Path(store.begin(_record(deployment_id="", stage=ServiceStage.ADMISSION)))

    assert path.parent.name == UNBOUND_DIRECTORY


def test_every_stage_rewrites_the_same_file(tmp_path: Path):
    """One run is one file; a stage transition rewrites it in place."""
    store = ServiceRunRecordStore(tmp_path)
    record = _record(stage=ServiceStage.CONFIGURATION_APPLY)
    first = store.begin(record)

    advanced = record.model_copy(update={"persisted_stage": ServiceStage.SERVICE_APPLY})
    second = store.advance(advanced)

    assert first == second
    assert store.load(_DEPLOYMENT, "run-1").persisted_stage is (
        ServiceStage.SERVICE_APPLY
    )
    assert len(list(Path(first).parent.glob("*.json"))) == 1


def test_the_full_typed_e5_rows_survive_the_round_trip(tmp_path: Path):
    """R-RET-01 needs the rows themselves, and TD-12 needs the snapshot.

    A compact count cannot decide whether an action may be trusted without
    re-applying it, and a record that dropped `received_mutation` would lose
    the evidence that the classification was honest.
    """
    store = ServiceRunRecordStore(tmp_path)
    store.begin(_record())

    loaded = store.load(_DEPLOYMENT, "run-1")

    row = loaded.configuration_result.action_results[0]
    assert row.received_mutation is not None
    assert row.received_mutation.dispatch is DispatchFact.ACCEPTED
    assert row.received_mutation.result is ResultFact.CORRELATED
    assert row.postcondition is PostconditionFact.SATISFIED
    assert row.footprint is FootprintFact.COVERED


def test_a_malformed_record_is_refused_rather_than_skipped(tmp_path: Path):
    """A broken record is a refusal, never an invisible absence."""
    store = ServiceRunRecordStore(tmp_path)
    path = Path(store.begin(_record()))
    path.write_text("{not json", encoding="utf-8")

    with pytest.raises(RunRecordPersistenceError, match="unreadable"):
        store.load(_DEPLOYMENT, "run-1")


def test_a_record_that_no_longer_matches_the_typed_contract_is_refused(
    tmp_path: Path,
):
    """Valid JSON is not a valid record; the load validates the contract."""
    store = ServiceRunRecordStore(tmp_path)
    path = Path(store.begin(_record()))
    path.write_text('{"run_id": "run-1"}', encoding="utf-8")

    with pytest.raises(RunRecordPersistenceError):
        store.load(_DEPLOYMENT, "run-1")


# -- containment ----------------------------------------------------------


def test_a_traversing_deployment_id_cannot_escape_the_store(tmp_path: Path):
    """The deployment id arrives from an MCP caller and is sanitized."""
    store = ServiceRunRecordStore(tmp_path)

    path = Path(store.begin(_record(deployment_id="../../etc")))

    assert path.resolve().is_relative_to(tmp_path.resolve())


def test_a_traversing_run_id_cannot_escape_the_store(tmp_path: Path):
    """The same containment applies to the second path component."""
    store = ServiceRunRecordStore(tmp_path)

    path = Path(store.begin(_record(run_id="../../../evil")))

    assert path.resolve().is_relative_to(tmp_path.resolve())


def test_an_empty_run_id_is_refused(tmp_path: Path):
    """A record with no identity has nowhere to live."""
    store = ServiceRunRecordStore(tmp_path)

    with pytest.raises(RunRecordPersistenceError, match="run id"):
        store.path_for(_DEPLOYMENT, "   ")


def test_the_run_label_never_reaches_the_path(tmp_path: Path):
    """A label identifies a run to a person; it authorizes nothing.

    Two runs with the same label are still two runs, and the second must not
    be able to overwrite the first.
    """
    store = ServiceRunRecordStore(tmp_path)
    first = Path(store.begin(_record(run_id="run-1", run_label="nightly")))
    second = Path(store.begin(_record(run_id="run-2", run_label="nightly")))

    assert first != second
    assert "nightly" not in str(first)
    assert len(list(first.parent.glob("*.json"))) == 2


def test_generated_run_ids_are_unique_and_independent_of_any_label():
    """Two runs in the same second are still two runs."""
    moment = datetime(2026, 9, 17, 10, 0, tzinfo=UTC)

    identifiers = {generate_run_id(moment) for _ in range(64)}

    assert len(identifiers) == 64
    assert all(item.startswith("2026-09-17T10-00-00Z-") for item in identifiers)


# -- retained reuse -------------------------------------------------------


def _retained(store: ServiceRunRecordStore) -> ServiceRunRecord | None:
    return store.retained_result_for(
        _DEPLOYMENT,
        manifest_hash=_MANIFEST_HASH,
        configuration_semantic_hash=_CONFIG_HASH,
        environment_fingerprint_hash=_ENVIRONMENT_HASH,
    )


def test_a_completed_run_with_the_exact_identity_is_reusable(tmp_path: Path):
    """R-RET-01: all four identity values agree and the run completed."""
    store = ServiceRunRecordStore(tmp_path)
    store.begin(_record())

    assert _retained(store) is not None


def test_the_same_hashes_in_a_changed_environment_are_not_reusable(
    tmp_path: Path,
):
    """The plan is identical; the machine it would run on is not."""
    store = ServiceRunRecordStore(tmp_path)
    store.begin(_record(environment_fingerprint_hash="another-environment"))

    assert _retained(store) is None


def test_an_interrupted_run_is_never_reused(tmp_path: Path):
    """Nothing is retained from a run that stopped mid-flight."""
    store = ServiceRunRecordStore(tmp_path)
    store.begin(_record(stage=ServiceStage.SERVICE_APPLY))

    assert _retained(store) is None


def test_a_run_with_effect_uncertainty_is_never_reused(tmp_path: Path):
    """An action whose outcome is unknown is not one whose result may stand."""
    store = ServiceRunRecordStore(tmp_path)
    store.begin(_record(e5_effect_uncertain=True))

    assert _retained(store) is None


def test_a_record_without_configuration_rows_is_not_reusable(tmp_path: Path):
    """The rows ARE the retained evidence; without them there is none."""
    store = ServiceRunRecordStore(tmp_path)
    store.begin(
        ServiceRunRecord(
            run_id="run-empty",
            created_at=datetime(2026, 9, 17, 10, 0, tzinfo=UTC),
            deployment_id=_DEPLOYMENT,
            manifest_hash=_MANIFEST_HASH,
            configuration_semantic_hash=_CONFIG_HASH,
            environment_fingerprint_hash=_ENVIRONMENT_HASH,
            persisted_stage=ServiceStage.COMPLETED,
        )
    )

    assert _retained(store) is None


def test_the_newest_matching_record_wins(tmp_path: Path):
    """The most recent completed run describes the current state."""
    store = ServiceRunRecordStore(tmp_path)
    base = datetime(2026, 9, 17, 10, 0, tzinfo=UTC)
    store.begin(_record(run_id="run-old", created_at=base))
    store.begin(_record(run_id="run-new", created_at=base + timedelta(hours=1)))

    retained = _retained(store)

    assert retained is not None
    assert retained.run_id == "run-new"


def test_a_missing_identity_value_never_matches(tmp_path: Path):
    """Two unknowns are not a match; that is how an unchecked run gets reused."""
    store = ServiceRunRecordStore(tmp_path)
    store.begin(_record(environment_fingerprint_hash=""))

    assert (
        store.retained_result_for(
            _DEPLOYMENT,
            manifest_hash=_MANIFEST_HASH,
            configuration_semantic_hash=_CONFIG_HASH,
            environment_fingerprint_hash="",
        )
        is None
    )


def test_a_corrupt_record_makes_reuse_refuse_rather_than_look_past_it(
    tmp_path: Path,
):
    """A record that cannot be read cannot be ruled out either."""
    store = ServiceRunRecordStore(tmp_path)
    path = Path(store.begin(_record()))
    path.write_text("{}", encoding="utf-8")

    with pytest.raises(RunRecordPersistenceError):
        _retained(store)


def test_reuse_for_an_unknown_deployment_is_simply_absent(tmp_path: Path):
    """No records for that id is an empty answer, not an error."""
    store = ServiceRunRecordStore(tmp_path)

    assert (
        store.retained_result_for(
            "never-deployed",
            manifest_hash=_MANIFEST_HASH,
            configuration_semantic_hash=_CONFIG_HASH,
            environment_fingerprint_hash=_ENVIRONMENT_HASH,
        )
        is None
    )


# -- atomicity ------------------------------------------------------------


def test_a_failed_replacement_leaves_the_last_valid_record_in_place(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """The write-ahead record is only useful if a failed write cannot destroy it."""
    store = ServiceRunRecordStore(tmp_path)
    store.begin(_record(stage=ServiceStage.CONFIGURATION_APPLY))

    def explode(source: object, target: object) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(
        "packet_tracer_mcp.infrastructure.persistence.service_run_record_store"
        ".os.replace",
        explode,
    )
    with pytest.raises(RunRecordPersistenceError):
        store.advance(
            _record(stage=ServiceStage.SERVICE_APPLY, status=ServiceRunStatus.UNKNOWN)
        )

    monkeypatch.undo()
    surviving = store.load(_DEPLOYMENT, "run-1")
    assert surviving.persisted_stage is ServiceStage.CONFIGURATION_APPLY
    assert not list(Path(tmp_path, _DEPLOYMENT).glob("*.tmp"))
