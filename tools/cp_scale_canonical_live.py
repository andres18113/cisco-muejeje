"""Compatible CP-SCALE LIVE entry point; composition lives in the CLI adapter."""
from __future__ import annotations

from packet_tracer_mcp.adapters.cli.cp_scale_live import (
    main,
    run,
    GOVERNED_ROOT,
    EVIDENCE_PATH,
    CHECKPOINT_PATH,
    FINAL_CHECKPOINT_PATH,
    CANONICAL_EVIDENCE_DIR,
    EXPECTED_BRANCH,
    EXPECTED_UPSTREAM,
    _BUILD_STAGES,
    CanonicalLiveFailure,
    _execute_stage,
    _stage_voice,
    _write_evidence,
    _write_checkpoint_summary,
    _wait_for_site_forwarding,
    _wait_for_core_forwarding,
    _network_state_observation,
    _post_failure_simulation_diagnostic,
    _frame_observer_discovery,
    _voice_dhcp_statistics_target,
    _dhcp_server_statistics_point,
    _dhcp_server_statistics_delta,
    _dhcp_server_statistics_observation,
    _representative_phone_evidence,
    _trunk_vlan_traversal_evidence,
)


if __name__ == "__main__":
    raise SystemExit(main())
