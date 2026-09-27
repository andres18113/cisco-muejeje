"""SP-1 SP1-05: a routed run's durable record agrees with its response.

A refusal after the write-ahead record (A6) returns the stage it persisted;
the terminal record written for it must say the same, or a governed caller
that reloads the record and compares cannot tell a consistent refusal from a
tampered one.
"""

from __future__ import annotations

import json
from pathlib import Path

from service_entry_fixture import (
    BACKEND_VERSION,
    DEPLOYMENT_ID,
    FINGERPRINT,
    EndpointObserver,
    IsolationPreflight,
    ManifestStore,
    RecordingConfigurationRuntime,
    RecordingServiceRuntime,
)
from sp1_routed_fixture import routed_workload

from packet_tracer_mcp.application.use_cases.apply_enterprise_services import (
    ServiceStageRuntimes,
    TransportSelection,
    apply_enterprise_services,
)
from packet_tracer_mcp.domain.enterprise.models.service_entry import (
    ServiceEntryRefusal,
    ServiceStage,
)
from packet_tracer_mcp.domain.enterprise.models.service_run_record import (
    SourceTreeIdentity,
)
from packet_tracer_mcp.infrastructure.catalog.enterprise_capabilities import (
    candidate_capability_adapter,
)
from packet_tracer_mcp.infrastructure.persistence.service_run_record_store import (
    ServiceRunRecordStore,
)

CANDIDATES = {"1941": ["supports_static_routes"], "2911": ["supports_static_routes"]}


def test_a_refusal_after_the_write_ahead_record_persists_its_stage(tmp_path: Path):
    """Unreadable endpoints refuse after A6; record and response agree."""
    payload, plans = routed_workload()
    configuration = RecordingConfigurationRuntime(targets=plans.inventory)
    services = RecordingServiceRuntime(targets=plans.inventory)
    store = ServiceRunRecordStore(tmp_path)

    result = apply_enterprise_services(
        json.dumps(payload),
        deployment_id=DEPLOYMENT_ID,
        packet_tracer_version=BACKEND_VERSION,
        runtimes=ServiceStageRuntimes(configuration=configuration, services=services),
        manifest_store=ManifestStore(manifest=plans.manifest),
        record_store=store,
        import_preflight=IsolationPreflight(),
        environment_fingerprint=FINGERPRINT,
        transport_selection=TransportSelection(channel="file"),
        endpoint_observer=EndpointObserver(readable=False),
        source_tree=SourceTreeIdentity(sha="test-source", dirty=True),
        device_capability_catalog=candidate_capability_adapter(
            BACKEND_VERSION, CANDIDATES, label="sp1-failure"
        ),
    )

    assert result.refusal_code is ServiceEntryRefusal.DRIFT_UNREADABLE
    assert result.persisted_stage is ServiceStage.ADMISSION
    stored = store.load(DEPLOYMENT_ID, result.run_id)
    assert stored.persisted_stage is result.persisted_stage
