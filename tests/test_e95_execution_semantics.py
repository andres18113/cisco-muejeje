from packet_tracer_mcp.domain.enterprise.models.configuration import (
    ConfigureAccessPort,
    ConfigurationActionType,
    ConfigurationPhase,
    CreateVlan,
)
from packet_tracer_mcp.domain.enterprise.models.configuration_runtime import (
    ActionExecutionStatus,
)
from packet_tracer_mcp.domain.enterprise.models.execution import (
    ApplicationExecutionJournal,
    DirtyState,
    ExecutionJournalEntry,
    MutationDisposition,
    OperationSemantics,
    satisfies_apply_dependency,
)
from packet_tracer_mcp.domain.enterprise.models.voice_plan import (
    CallExpectation,
    CallExpectationResult,
)


def test_typed_actions_publish_operation_semantics():
    vlan = CreateVlan(
        id="vlan/10", phase=ConfigurationPhase.L2_DEFINITIONS,
        device_id="sw1", device_name="SW1", site_id="hq", vlan_id=10,
    )
    access = ConfigureAccessPort(
        id="access/1", phase=ConfigurationPhase.L2_INTERFACES,
        device_id="sw1", device_name="SW1", site_id="hq",
        interface="FastEthernet0/1", data_vlan_id=10,
    )
    call = CallExpectation(
        id="call/1", source_phone_id="p1", source_extension="1001",
        dialed_extension="1002", expected_result=CallExpectationResult.ESTABLISHED,
        site_id="hq",
    )

    assert vlan.action_type is ConfigurationActionType.CREATE_VLAN
    assert vlan.operation is OperationSemantics.ENSURE_PRESENT
    assert access.operation is OperationSemantics.SET_VALUE
    assert call.operation is OperationSemantics.EXECUTE_ONCE


def test_noop_and_reasserted_satisfy_apply_dependencies():
    assert satisfies_apply_dependency(ActionExecutionStatus.APPLIED)
    assert satisfies_apply_dependency(ActionExecutionStatus.NO_OP)
    assert satisfies_apply_dependency(ActionExecutionStatus.REASSERTED)
    assert not satisfies_apply_dependency(ActionExecutionStatus.FAILED)


def test_execution_journal_preserves_partial_sequence_and_dirty_state():
    journal = ApplicationExecutionJournal(plan_id="plan/e5", deployment_id="dep/1")
    journal.append(ExecutionJournalEntry(
        ordinal=1, action_id="A", operation=OperationSemantics.SET_VALUE,
        disposition=MutationDisposition.CHANGED, inverse_available=True,
    ))
    journal.append(ExecutionJournalEntry(
        ordinal=2, action_id="B", operation=OperationSemantics.ENSURE_PRESENT,
        disposition=MutationDisposition.REASSERTED, inverse_available=True,
    ))
    journal.append(ExecutionJournalEntry(
        ordinal=3, action_id="C", operation=OperationSemantics.SET_VALUE,
        disposition=MutationDisposition.FAILED,
    ))
    journal.append(ExecutionJournalEntry(
        ordinal=4, action_id="D", operation=OperationSemantics.SET_VALUE,
        disposition=MutationDisposition.BLOCKED,
    ))

    assert [entry.action_id for entry in journal.entries] == ["A", "B", "C", "D"]
    assert journal.dirty_state is DirtyState.DIRTY_RECOVERABLE
    assert journal.compact_summary()["counts"] == {
        "blocked": 1, "changed": 1, "failed": 1, "reasserted": 1,
    }


def test_preflight_failure_without_mutation_is_clean():
    journal = ApplicationExecutionJournal(plan_id="plan/e5", deployment_id="dep/1")
    journal.mark_preflight_failure("manifest mismatch")

    assert journal.dirty_state is DirtyState.CLEAN
    assert journal.entries == []
