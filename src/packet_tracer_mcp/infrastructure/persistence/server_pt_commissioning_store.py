"""Write-once inputs and records of one Server-PT commissioning campaign.

The store is bound to one campaign identity. Its default is C31, so every
existing caller keeps its directory and index; another campaign, such as the
experimental FASTLOOP one, gets its own directory, index and ledger.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from collections.abc import Mapping
from pathlib import Path, PurePosixPath
from uuid import uuid4

from ...application.use_cases.prepare_server_pt_commissioning import (
    ServerPtCommissioningBundle,
)
from ...application.use_cases.prequalify_server_pt import (
    ServerPtPrequalificationResult,
)
from ...application.use_cases.server_pt_phase_grant import ServerPtPhaseGrant
from ...domain.enterprise.models.configuration import ConfigurationPlan
from ...domain.enterprise.models.configuration_runtime import (
    ConfigurationApplicationResult,
)
from ...domain.enterprise.models.physical_deployment import (
    PhysicalDeploymentResult,
    PhysicalMutationResult,
    PhysicalWorkspaceObservation,
    ServerPtCleanupResult,
)
from ...domain.models.plans import TopologyPlan
from ...shared.utils import resolve_within, safe_name_component

CAMPAIGN_ID = "SERVER-PT-C31-COMMISSION-01"
_ATTEMPT = re.compile(r"[0-9a-f]{32}\Z")
_EXIT_IMPORT_SUFFIXES = frozenset({".json", ".jsonl", ".txt"})


def _safe_id(value: str) -> str:
    if not value or safe_name_component(value, "") != value:
        raise ValueError("commissioning attempt ID is not a safe name")
    return value


def _write_once(path: Path, payload: bytes) -> None:
    """Publish complete bytes by exclusive link; an existing record wins."""
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with temporary.open("xb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError as exc:
            raise ValueError(
                f"commissioning record already exists: {path.name}"
            ) from exc
    finally:
        temporary.unlink(missing_ok=True)


def _write_once_or_same(path: Path, payload: bytes) -> None:
    """Publish bytes once; an existing file must already hold exactly them."""
    try:
        _write_once(path, payload)
    except ValueError:
        if path.read_bytes() != payload:
            raise
        # A retried import finds its own identical bytes: nothing to do.


class ServerPtCommissioningStore:
    """Persist one full exported bundle under one explicitly governed root."""

    def __init__(self, governed_root: Path, campaign_id: str = CAMPAIGN_ID) -> None:
        """Bind the declared checkout root and one campaign, writing nothing."""
        self.root = Path(governed_root).resolve()
        self.campaign_id = safe_name_component(campaign_id, "")
        if not self.campaign_id or self.campaign_id != campaign_id:
            raise ValueError("commissioning campaign ID is not a safe name")

    def _attempt_dir(self, attempt_id: str) -> Path:
        return resolve_within(
            self.root, "data", "commissioning", self.campaign_id, _safe_id(attempt_id)
        )

    def _campaign_dir(self) -> Path:
        return resolve_within(self.root, "data", "commissioning", self.campaign_id)

    def ledger_path_for(self, name: str) -> Path:
        """Return one contained campaign-ledger record path."""
        return resolve_within(self._campaign_dir(), "ledger", _safe_id(name) + ".json")

    def save_ledger_record(self, name: str, document: Mapping[str, object]) -> Path:
        """Write one ledger record once; an existing record is never replaced."""
        path = self.ledger_path_for(name)
        _write_once(path, (json.dumps(dict(document), sort_keys=True) + "\n").encode())
        return path

    def ledger_records(self) -> dict[str, dict[str, object]]:
        """Read every ledger record, by name; a malformed one is an error."""
        root = resolve_within(self._campaign_dir(), "ledger")
        if not root.exists():
            return {}
        records: dict[str, dict[str, object]] = {}
        for path in sorted(root.glob("*.json")):
            try:
                value = json.loads(path.read_bytes())
            except (OSError, ValueError) as exc:
                raise ValueError("campaign ledger record is unreadable") from exc
            if not isinstance(value, dict):
                raise ValueError("campaign ledger record is malformed")
            records[path.stem] = value
        return records

    def setup_attempt_ids(self) -> tuple[str, ...]:
        """Count immutable setup grants; no new nonce resets the campaign cap."""
        root = self._campaign_dir()
        if not root.exists():
            return ()
        return tuple(
            sorted(
                item.name
                for item in root.iterdir()
                if item.is_dir()
                and _ATTEMPT.fullmatch(item.name)
                and resolve_within(item, "setup-grant.json").exists()
            )
        )

    def prequalification_attempt_ids(self) -> tuple[str, ...]:
        """Detect any spent or ambiguous preliminary authorization campaign-wide."""
        root = self._campaign_dir()
        if not root.exists():
            return ()
        names = (
            "prequalification-grant.json",
            "prequalification.json",
            "raw-prequalification.jsonl",
            "prequalification-status.json",
        )
        return tuple(
            sorted(
                item.name
                for item in root.iterdir()
                if item.is_dir()
                and _ATTEMPT.fullmatch(item.name)
                and any(resolve_within(item, name).exists() for name in names)
            )
        )

    def bundle_path_for(self, attempt_id: str) -> Path:
        """Return the contained immutable full-plan path for one attempt."""
        return resolve_within(self._attempt_dir(attempt_id), "bundle.json")

    def intent_path_for(self, attempt_id: str) -> Path:
        """Return the exact immutable four-input product intent file."""
        return resolve_within(self._attempt_dir(attempt_id), "intent.json")

    def topology_path_for(self, attempt_id: str) -> Path:
        """Return the complete exported E4 TopologyPlan file."""
        return resolve_within(self._attempt_dir(attempt_id), "topology.json")

    def require_bundle_sha256(self, attempt_id: str, expected: str) -> None:
        """Bind all later phases to the exact full input E4 consumed."""
        try:
            actual = hashlib.sha256(
                self.bundle_path_for(attempt_id).read_bytes()
            ).hexdigest()
        except OSError as exc:
            raise ValueError("setup bundle changed: unreadable") from exc
        if actual != expected:
            raise ValueError("setup bundle changed")

    def cleanup_started(self, attempt_id: str) -> bool:
        """Refuse acceptance after any owned cleanup reservation or effect."""
        directory = self._attempt_dir(attempt_id)
        return any(
            resolve_within(directory, name).exists()
            for name in ("cleanup-grant.json", "precleanup.json", "cleanup-result.json")
        ) or any(directory.glob("cleanup-device-*.json"))

    def record_path_for(self, attempt_id: str, name: str) -> Path:
        """Return one fixed record path for archive inspection."""
        if name not in {
            "prequalification",
            "baseline",
            "e4-result",
            "e5-plan",
            "e5-result",
            "precleanup",
            "cleanup-result",
            "prequalification-grant",
            "setup-grant",
            "cleanup-grant",
            "acceptance-prepare",
            "acceptance-grant",
            "acceptance-seal",
            "acceptance-status",
            "acceptance-raw-index",
            "process-launch",
            "process-exit",
            "exit-import",
            "causal-correction",
            "setup-status",
            "prequalification-status",
            "cleanup-status",
            "prequalification-archive-admission",
            "setup-archive-admission",
            "acceptance-archive-admission",
            "cleanup-archive-admission",
        }:
            raise ValueError("unknown commissioning record name")
        return resolve_within(self._attempt_dir(attempt_id), name + ".json")

    def journal_path_for(self, attempt_id: str, phase: str) -> Path:
        """Return one contained, exclusive original-answer journal path."""
        if phase not in {"prequalification", "setup", "acceptance", "cleanup"}:
            raise ValueError("unknown commissioning phase")
        return resolve_within(self._attempt_dir(attempt_id), "raw-" + phase + ".jsonl")

    def save_bundle(self, attempt_id: str, bundle: ServerPtCommissioningBundle) -> Path:
        """Seal the exact bytes E4 will consume; never replace an existing input."""
        self._validate(bundle)
        directory = self._attempt_dir(attempt_id)
        path = self.bundle_path_for(attempt_id)
        digest_path = resolve_within(directory, "bundle.sha256")
        intent_path = self.intent_path_for(attempt_id)
        topology_path = self.topology_path_for(attempt_id)
        if any(
            item.exists() for item in (path, digest_path, intent_path, topology_path)
        ):
            raise ValueError("commissioning bundle already exists")
        payload = (bundle.model_dump_json(indent=2) + "\n").encode("utf-8")
        _write_once(intent_path, bundle.intent_json.encode("utf-8"))
        _write_once(topology_path, bundle.topology_json.encode("utf-8"))
        _write_once(digest_path, (hashlib.sha256(payload).hexdigest() + "\n").encode())
        _write_once(path, payload)
        return path

    def load_bundle(self, attempt_id: str) -> ServerPtCommissioningBundle:
        """Reload an intact full plan; missing or changed bytes fail closed."""
        directory = self._attempt_dir(attempt_id)
        path = self.bundle_path_for(attempt_id)
        digest_path = resolve_within(directory, "bundle.sha256")
        try:
            payload = path.read_bytes()
            expected = digest_path.read_text(encoding="ascii").strip()
        except OSError as exc:
            raise ValueError("commissioning bundle is missing") from exc
        if hashlib.sha256(payload).hexdigest() != expected:
            raise ValueError("commissioning bundle bytes changed")
        bundle = ServerPtCommissioningBundle.model_validate_json(payload)
        self._validate(bundle)
        try:
            intent_bytes = self.intent_path_for(attempt_id).read_bytes()
            topology_bytes = self.topology_path_for(attempt_id).read_bytes()
        except OSError as exc:
            raise ValueError("commissioning full input is missing") from exc
        if intent_bytes != bundle.intent_json.encode(
            "utf-8"
        ) or topology_bytes != bundle.topology_json.encode("utf-8"):
            raise ValueError("commissioning full input bytes changed")
        return bundle

    def _save_model(self, attempt_id: str, name: str, value) -> Path:
        directory = self._attempt_dir(attempt_id)
        path = resolve_within(directory, name + ".json")
        digest_path = resolve_within(directory, name + ".sha256")
        if path.exists() or digest_path.exists():
            raise ValueError(f"commissioning {name} already exists")
        payload = (value.model_dump_json(indent=2) + "\n").encode("utf-8")
        _write_once(path, payload)
        _write_once(digest_path, (hashlib.sha256(payload).hexdigest() + "\n").encode())
        return path

    def _load_model(self, attempt_id: str, name: str, model_type):
        directory = self._attempt_dir(attempt_id)
        path = resolve_within(directory, name + ".json")
        digest_path = resolve_within(directory, name + ".sha256")
        try:
            payload = path.read_bytes()
            expected = digest_path.read_text(encoding="ascii").strip()
        except OSError as exc:
            raise ValueError(f"commissioning {name} is missing") from exc
        if hashlib.sha256(payload).hexdigest() != expected:
            raise ValueError(f"commissioning {name} bytes changed")
        return model_type.model_validate_json(payload)

    def save_e4(self, attempt_id: str, result: PhysicalDeploymentResult) -> Path:
        """Retain every E4 item, readback, journal and error once."""
        return self._save_model(attempt_id, "e4-result", result)

    def save_baseline(
        self, attempt_id: str, observation: PhysicalWorkspaceObservation
    ) -> Path:
        """Retain the pre-effect empty workspace as full typed evidence."""
        return self._save_model(attempt_id, "baseline", observation)

    def load_baseline(self, attempt_id: str) -> PhysicalWorkspaceObservation:
        """Reload the complete baseline for owned cleanup comparison."""
        return self._load_model(attempt_id, "baseline", PhysicalWorkspaceObservation)

    def save_precleanup(
        self, attempt_id: str, observation: PhysicalWorkspaceObservation
    ) -> Path:
        """Retain the full physical state before the first cleanup effect."""
        return self._save_model(attempt_id, "precleanup", observation)

    def save_cleanup_item(
        self, attempt_id: str, index: int, result: PhysicalMutationResult
    ) -> Path:
        """Retain one removal answer before another device can be touched."""
        if isinstance(index, bool) or not 0 <= index < 35:
            raise ValueError("cleanup item index exceeds the reviewed topology")
        return self._save_model(attempt_id, f"cleanup-device-{index:03d}", result)

    def save_cleanup(self, attempt_id: str, result: ServerPtCleanupResult) -> Path:
        """Retain the full cleanup outcome and both restoration readings."""
        return self._save_model(attempt_id, "cleanup-result", result)

    def load_cleanup(self, attempt_id: str) -> ServerPtCleanupResult:
        """Reload byte-bound cleanup evidence."""
        return self._load_model(attempt_id, "cleanup-result", ServerPtCleanupResult)

    def load_e4(self, attempt_id: str) -> PhysicalDeploymentResult:
        """Reload the complete E4 result after its stored-byte check."""
        return self._load_model(attempt_id, "e4-result", PhysicalDeploymentResult)

    def save_configuration_plan(self, attempt_id: str, plan: ConfigurationPlan) -> Path:
        """Retain the plan recompiled against the observed E4 manifest."""
        return self._save_model(attempt_id, "e5-plan", plan)

    def load_configuration_plan(self, attempt_id: str) -> ConfigurationPlan:
        """Reload the exact E5 plan used by setup."""
        return self._load_model(attempt_id, "e5-plan", ConfigurationPlan)

    def save_e5(self, attempt_id: str, result: ConfigurationApplicationResult) -> Path:
        """Retain all E5 action and verification rows without relabeling."""
        return self._save_model(attempt_id, "e5-result", result)

    def load_e5(self, attempt_id: str) -> ConfigurationApplicationResult:
        """Reload the complete E5 result after its stored-byte check."""
        return self._load_model(attempt_id, "e5-result", ConfigurationApplicationResult)

    def save_prequalification(
        self, attempt_id: str, result: ServerPtPrequalificationResult
    ) -> Path:
        """Retain both preliminary measurements and restoration evidence once."""
        return self._save_model(attempt_id, "prequalification", result)

    def load_prequalification(self, attempt_id: str) -> ServerPtPrequalificationResult:
        """Reload preliminary evidence only while its bytes remain intact."""
        return self._load_model(
            attempt_id, "prequalification", ServerPtPrequalificationResult
        )

    def save_phase_grant(self, attempt_id: str, grant: ServerPtPhaseGrant) -> Path:
        """Seal one deterministic child grant before its first effect."""
        if grant.attempt_id != attempt_id:
            raise ValueError("phase grant attempt mismatch")
        return self._save_model(attempt_id, grant.phase + "-grant", grant)

    def load_phase_grant(self, attempt_id: str, phase: str) -> ServerPtPhaseGrant:
        """Reload the exact byte-bound grant for this phase."""
        if phase not in {"prequalification", "setup", "cleanup"}:
            raise ValueError("unknown commissioning phase")
        return self._load_model(attempt_id, phase + "-grant", ServerPtPhaseGrant)

    def save_phase_status(
        self, attempt_id: str, phase: str, status: Mapping[str, object]
    ) -> Path:
        """Retain one named phase exit, including failures before a typed result."""
        if phase not in {"prequalification", "setup", "cleanup"}:
            raise ValueError("unknown commissioning phase")
        name = phase + "-status"
        directory = self._attempt_dir(attempt_id)
        path = resolve_within(directory, name + ".json")
        digest_path = resolve_within(directory, name + ".sha256")
        payload = (
            json.dumps(dict(status), sort_keys=True, ensure_ascii=False) + "\n"
        ).encode("utf-8")
        _write_once(path, payload)
        _write_once(digest_path, (hashlib.sha256(payload).hexdigest() + "\n").encode())
        return path

    def load_phase_status(self, attempt_id: str, phase: str) -> dict[str, object]:
        """Reload one byte-bound phase exit for cross-phase admission."""
        if phase not in {"prequalification", "setup", "cleanup"}:
            raise ValueError("unknown commissioning phase")
        return self._load_mapping(attempt_id, phase + "-status")

    @staticmethod
    def mapping_bytes(document: Mapping[str, object]) -> bytes:
        """Return the exact bytes a mapping record of this store is written as."""
        return (
            json.dumps(dict(document), sort_keys=True, ensure_ascii=False) + "\n"
        ).encode("utf-8")

    def _save_mapping(
        self, attempt_id: str, name: str, document: Mapping[str, object]
    ) -> Path:
        directory = self._attempt_dir(attempt_id)
        path = resolve_within(directory, name + ".json")
        digest_path = resolve_within(directory, name + ".sha256")
        payload = self.mapping_bytes(document)
        _write_once(path, payload)
        _write_once(digest_path, (hashlib.sha256(payload).hexdigest() + "\n").encode())
        return path

    def _load_mapping(self, attempt_id: str, name: str) -> dict[str, object]:
        directory = self._attempt_dir(attempt_id)
        path = resolve_within(directory, name + ".json")
        digest_path = resolve_within(directory, name + ".sha256")
        try:
            raw = path.read_bytes()
            expected = digest_path.read_text(encoding="ascii").strip()
        except OSError as exc:
            raise ValueError(f"commissioning {name} is missing") from exc
        if hashlib.sha256(raw).hexdigest() != expected:
            raise ValueError(f"commissioning {name} bytes changed")
        value = json.loads(raw)
        if not isinstance(value, dict):
            raise ValueError(f"commissioning {name} is not a JSON object")
        return value

    def save_acceptance_prepare(
        self, attempt_id: str, document: Mapping[str, object]
    ) -> Path:
        """Retain the exact derived schema-2 proposal before its grant."""
        return self._save_mapping(attempt_id, "acceptance-prepare", document)

    def save_acceptance_grant(
        self, attempt_id: str, document: Mapping[str, object]
    ) -> Path:
        """Retain the unchanged product grant after its proposal is sealed."""
        return self._save_mapping(attempt_id, "acceptance-grant", document)

    def load_acceptance_grant(self, attempt_id: str) -> dict[str, object]:
        """Reload the exact product grant for the existing acceptance command."""
        return self._load_mapping(attempt_id, "acceptance-grant")

    def save_acceptance_seal(
        self, attempt_id: str, document: Mapping[str, object]
    ) -> Path:
        """Bind charter, source, CI, process, setup and grant before contact."""
        return self._save_mapping(attempt_id, "acceptance-seal", document)

    def save_acceptance_status(
        self, attempt_id: str, document: Mapping[str, object]
    ) -> Path:
        """Retain the product exit and publication claim without rewriting it."""
        return self._save_mapping(attempt_id, "acceptance-status", document)

    def load_acceptance_status(self, attempt_id: str) -> dict[str, object]:
        """Reload the immutable product exit for attempt-two admission."""
        return self._load_mapping(attempt_id, "acceptance-status")

    def save_causal_correction(
        self, attempt_id: str, document: Mapping[str, object]
    ) -> Path:
        """Retain one first-result-bound correction before attempt two."""
        return self._save_mapping(attempt_id, "causal-correction", document)

    def load_causal_correction(self, attempt_id: str) -> dict[str, object]:
        """Reload attempt two's immutable causal explanation and source SHA."""
        return self._load_mapping(attempt_id, "causal-correction")

    def save_acceptance_raw_index(
        self, attempt_id: str, document: Mapping[str, object]
    ) -> Path:
        """Bind original answers to the product's purpose and episode ledger."""
        return self._save_mapping(attempt_id, "acceptance-raw-index", document)

    def save_process_launch(
        self, attempt_id: str, document: Mapping[str, object]
    ) -> Path:
        """Retain the exact owned PID/path/incarnation and launch provenance."""
        return self._save_mapping(attempt_id, "process-launch", document)

    def load_process_launch(self, attempt_id: str) -> dict[str, object]:
        """Reload byte-bound campaign process creation evidence."""
        return self._load_mapping(attempt_id, "process-launch")

    def save_process_exit(
        self, attempt_id: str, document: Mapping[str, object]
    ) -> Path:
        """Retain the graceful close request and observed process exit."""
        return self._save_mapping(attempt_id, "process-exit", document)

    def save_retirement_attempt(
        self, attempt_id: str, stamp: str, document: Mapping[str, object]
    ) -> Path:
        """Retain one retirement attempt that did not end in an admitted exit."""
        if not re.fullmatch(r"[0-9]{8}T[0-9]{6}Z", stamp):
            raise ValueError("retirement attempt stamp is not a compact UTC time")
        return self._save_mapping(attempt_id, "retirement-attempt-" + stamp, document)

    def load_process_exit(self, attempt_id: str) -> dict[str, object]:
        """Reload the indexed observed exit of the campaign-owned process."""
        return self._load_mapping(attempt_id, "process-exit")

    def save_authority_document(self, name: str, raw: bytes) -> Path:
        """Keep one operator authority document's exact bytes, once."""
        if (
            not name.endswith(".md")
            or safe_name_component(name, "") != name
            or not isinstance(raw, bytes)
        ):
            raise ValueError("authority document name or bytes are invalid")
        path = resolve_within(self._campaign_dir(), "authority", name)
        _write_once_or_same(path, raw)
        return path

    def save_exit_import_artifact(
        self, attempt_id: str, role: str, suffix: str, raw: bytes
    ) -> Path:
        """Keep one original artifact of a historical exit import, byte-exact."""
        if (
            not role
            or safe_name_component(role, "") != role
            or suffix not in _EXIT_IMPORT_SUFFIXES
            or not isinstance(raw, bytes)
        ):
            raise ValueError("exit import artifact role or bytes are invalid")
        path = resolve_within(
            self._attempt_dir(attempt_id), "exit-import-" + role + suffix
        )
        _write_once_or_same(path, raw)
        return path

    def save_exit_import(self, attempt_id: str, document: Mapping[str, object]) -> Path:
        """Retain the validated historical exit import, never a `process-exit`."""
        return self._save_mapping(attempt_id, "exit-import", document)

    def load_exit_import(self, attempt_id: str) -> dict[str, object]:
        """Reload the byte-bound historical exit import."""
        return self._load_mapping(attempt_id, "exit-import")

    def seal_exit_import(self, attempt_id: str) -> Path:
        """Write the digest of an import record whose writer stopped before it.

        The digest is derived from the record's own bytes; it adds no claim.
        An existing digest must already be that one.
        """
        directory = self._attempt_dir(attempt_id)
        record = resolve_within(directory, "exit-import.json")
        digest = resolve_within(directory, "exit-import.sha256")
        payload = (hashlib.sha256(record.read_bytes()).hexdigest() + "\n").encode()
        _write_once_or_same(digest, payload)
        return digest

    def archive_residue(self) -> tuple[str, ...] | None:
        """Name files the index does not list, if everything it lists is intact.

        `None` means the index is unreadable or an indexed file is missing or
        changed: no residue can then be told apart from damage.
        """
        try:
            entries = self._indexed_entries()
            indexed = {item["path"]: item for item in entries}
            actual = self._archive_paths()
            if len(indexed) != len(entries) or set(indexed) - set(actual):
                return None
            for name, item in indexed.items():
                data = actual[name].read_bytes()
                if item["sha256"] != hashlib.sha256(data).hexdigest() or item[
                    "bytes"
                ] != len(data):
                    return None
        except (OSError, ValueError, KeyError, TypeError):
            return None
        return tuple(sorted(set(actual) - set(indexed)))

    def relative_path(self, path: Path) -> str:
        """Return a contained archive path as the index names it."""
        return Path(path).resolve().relative_to(self.root).as_posix()

    def index_bytes(self) -> bytes:
        """Return the current campaign index exactly as stored."""
        return resolve_within(self._campaign_dir(), "index.json").read_bytes()

    def register_external_source(
        self, attempt_id: str, label: str, source_path: Path
    ) -> Path:
        """Pin one product record or envelope's actual source bytes."""
        if not label or safe_name_component(label, "") != label:
            raise ValueError("external evidence label is unsafe")
        source = Path(source_path).resolve()
        allowed = (
            self.root / "data" / "deployments",
            self.root / "data" / "services",
            self.root / "data" / "acceptance",
        )
        if not any(source.is_relative_to(root.resolve()) for root in allowed):
            raise ValueError("external evidence path is outside product stores")
        raw = source.read_bytes()
        return self._save_mapping(
            attempt_id,
            "source-ref-" + label,
            {
                "path": source.relative_to(self.root).as_posix(),
                "sha256": hashlib.sha256(raw).hexdigest(),
                "bytes": len(raw),
            },
        )

    def external_source_registered(self, attempt_id: str, label: str) -> bool:
        """Report whether this exact external source reference was already sealed."""
        if not label or safe_name_component(label, "") != label:
            raise ValueError("external evidence label is unsafe")
        return resolve_within(
            self._attempt_dir(attempt_id), "source-ref-" + label + ".json"
        ).exists()

    def update_current_status(self, document: Mapping[str, object]) -> Path:
        """Replace only the campaign's current projection, atomically."""
        root = self._campaign_dir()
        root.mkdir(parents=True, exist_ok=True)
        target = resolve_within(root, "current-status.json")
        temporary = resolve_within(root, f".current-status.{uuid4().hex}.tmp")
        payload = (json.dumps(dict(document), sort_keys=True) + "\n").encode("utf-8")
        try:
            with temporary.open("xb") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, target)
        finally:
            temporary.unlink(missing_ok=True)
        return target

    def load_current_status(self) -> dict[str, object]:
        """Read the one current campaign projection without creating it."""
        try:
            value = json.loads(
                resolve_within(self._campaign_dir(), "current-status.json").read_bytes()
            )
        except (OSError, ValueError) as exc:
            raise ValueError("current campaign status is unavailable") from exc
        if not isinstance(value, dict):
            raise ValueError("current campaign status is malformed")
        return value

    def index_exists(self) -> bool:
        """Report whether this campaign already has an immutable-byte baseline."""
        return resolve_within(self._campaign_dir(), "index.json").exists()

    def require_archived_phase(
        self, attempt_id: str, phase: str, expected_outcome: str
    ) -> None:
        """Refuse a later effect unless both immutable and indexed status agree."""
        self.require_immutable_phase(attempt_id, phase, expected_outcome)
        current = self.load_current_status()
        if (
            current.get("phase") != phase
            or current.get("outcome") != expected_outcome
            or current.get("attempt_id") != attempt_id
        ):
            raise ValueError("archived phase is not ready")

    def save_archive_admission(self, attempt_id: str, phase: str) -> Path:
        """Seal that this phase's immutable result passed a source-byte index."""
        if phase not in {"prequalification", "setup", "acceptance", "cleanup"}:
            raise ValueError("unknown archive admission phase")
        status_name = (
            "acceptance-status" if phase == "acceptance" else phase + "-status"
        )
        status_path = resolve_within(
            self._attempt_dir(attempt_id), status_name + ".json"
        )
        digest = hashlib.sha256(status_path.read_bytes()).hexdigest()
        return self._save_mapping(
            attempt_id,
            phase + "-archive-admission",
            {"phase": phase, "attempt_id": attempt_id, "status_sha256": digest},
        )

    def require_immutable_phase(
        self,
        attempt_id: str,
        phase: str,
        expected_outcome: str,
        *,
        tolerate: frozenset[str] = frozenset(),
    ) -> dict[str, object]:
        """Require historical phase evidence even after current status advanced.

        `tolerate` names unindexed files a caller has already identified as
        its own residue; everything indexed must still verify.
        """
        if self.verify_index(tolerate=tolerate):
            raise ValueError("archived phase is not ready: index invalid")
        status = (
            self.load_acceptance_status(attempt_id)
            if phase == "acceptance"
            else self.load_phase_status(attempt_id, phase)
        )
        try:
            admission = self._load_mapping(attempt_id, phase + "-archive-admission")
            status_name = (
                "acceptance-status" if phase == "acceptance" else phase + "-status"
            )
            raw = resolve_within(
                self._attempt_dir(attempt_id), status_name + ".json"
            ).read_bytes()
        except (OSError, ValueError) as exc:
            raise ValueError("archived phase is not ready: admission absent") from exc
        if (
            status.get("outcome") != expected_outcome
            or admission.get("attempt_id") != attempt_id
            or admission.get("phase") != phase
            or admission.get("status_sha256") != hashlib.sha256(raw).hexdigest()
        ):
            raise ValueError("archived phase is not ready")
        return status

    def _indexed_entries(self) -> list[dict[str, object]]:
        raw = resolve_within(self._campaign_dir(), "index.json").read_bytes()
        document = json.loads(raw)
        if (
            not isinstance(document, dict)
            or document.get("campaign_id") != self.campaign_id
            or not isinstance(document.get("files"), list)
        ):
            raise ValueError("campaign index is malformed")
        return document["files"]

    def _prior_bytes_unchanged(self) -> None:
        """Never rebaseline any previously indexed immutable source."""
        try:
            entries = self._indexed_entries()
        except FileNotFoundError:
            return
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise ValueError("prior archive index is unreadable") from exc
        for item in entries:
            try:
                name = item["path"]
                if not isinstance(name, str):
                    raise ValueError("invalid index path")
                if name.endswith("/current-status.json"):
                    continue  # The one mutable current projection.
                path = resolve_within(self.root, *PurePosixPath(name).parts)
                raw = path.read_bytes()
                if (
                    hashlib.sha256(raw).hexdigest() != item["sha256"]
                    or len(raw) != item["bytes"]
                ):
                    raise ValueError("prior archive bytes changed")
            except (OSError, KeyError, TypeError) as exc:
                raise ValueError("prior archive bytes changed") from exc

    def _archive_paths(self) -> dict[str, Path]:
        campaign = self._campaign_dir()
        paths: dict[str, Path] = {}
        for path in campaign.rglob("*"):
            if not path.is_file() or path.name == "index.json":
                continue
            resolved = path.resolve()
            if not resolved.is_relative_to(campaign):
                raise ValueError("campaign archive path escaped its root")
            paths[resolved.relative_to(self.root).as_posix()] = resolved
            if not path.name.startswith("source-ref-") or path.suffix != ".json":
                continue
            attempt_id = path.parent.name
            label = path.stem.removeprefix("source-ref-")
            reference = self._load_mapping(attempt_id, "source-ref-" + label)
            relative = reference.get("path")
            if not isinstance(relative, str):
                raise ValueError("external source reference is malformed")
            source = resolve_within(self.root, *PurePosixPath(relative).parts)
            allowed = (
                self.root / "data" / "deployments",
                self.root / "data" / "services",
                self.root / "data" / "acceptance",
            )
            if not any(source.is_relative_to(root.resolve()) for root in allowed):
                raise ValueError("external source escaped product stores")
            raw = source.read_bytes()
            if reference.get("sha256") != hashlib.sha256(
                raw
            ).hexdigest() or reference.get("bytes") != len(raw):
                raise ValueError("external source bytes changed")
            paths[relative] = source
        return paths

    def index_predecessor(self) -> dict[str, object]:
        """Name where the current index would be preserved, writing nothing."""
        raw = self.index_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        path = resolve_within(
            self._campaign_dir(), "index-history", f"index-{digest}.json"
        )
        return {
            "path": path.relative_to(self.root).as_posix(),
            "sha256": digest,
            "bytes": len(raw),
        }

    def preserve_index(self) -> dict[str, object]:
        """Keep the current index's exact bytes, once, and name them.

        The copy lives at `index-history/index-<sha256>.json`, so its name is
        its digest; an existing copy must hold the same bytes. Every later
        index then lists the copy as an immutable source.
        """
        raw = self.index_bytes()
        predecessor = self.index_predecessor()
        path = resolve_within(self.root, *PurePosixPath(predecessor["path"]).parts)
        _write_once_or_same(path, raw)
        return predecessor

    def refresh_index(self, *, predecessor: Mapping[str, object] | None = None) -> Path:
        """Add new files only after all prior indexed source bytes still match.

        `predecessor`, from `preserve_index`, is recorded in the new index so
        an append-only closure names the exact index it extended.
        """
        root = self._campaign_dir()
        root.mkdir(parents=True, exist_ok=True)
        self._prior_bytes_unchanged()
        files = []
        for name, path in sorted(self._archive_paths().items()):
            raw = path.read_bytes()
            files.append(
                {
                    "path": name,
                    "sha256": hashlib.sha256(raw).hexdigest(),
                    "bytes": len(raw),
                }
            )
        document: dict[str, object] = {
            "schema_version": 2,
            "campaign_id": self.campaign_id,
            "files": files,
        }
        if predecessor is not None:
            snapshot = next(
                (item for item in files if item["path"] == predecessor.get("path")),
                None,
            )
            if snapshot is None or snapshot["sha256"] != predecessor.get("sha256"):
                raise ValueError("index predecessor is not a preserved index")
            document["predecessor"] = dict(predecessor)
        target = resolve_within(root, "index.json")
        temporary = resolve_within(root, f".index.{uuid4().hex}.tmp")
        try:
            with temporary.open("xb") as stream:
                stream.write(
                    (json.dumps(document, sort_keys=True, indent=2) + "\n").encode()
                )
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, target)
        finally:
            temporary.unlink(missing_ok=True)
        return target

    def adopt_ledger_residue(self, record_findings) -> tuple[str, ...]:
        """Index complete ledger records written after the last index, only.

        A ledger record is written before the index is refreshed; a hard stop
        between the two leaves a valid write-once record the index does not
        name, and every later phase, cleanup included, would then refuse the
        archive. The governed order refreshes the index after every ledger
        write, so one interrupted refresh leaves at most ONE such record, and
        its parents are already indexed. Adoption therefore requires nothing
        indexed to be missing or changed, exactly one unindexed file, a
        `.json` directly under the ledger, and `record_findings(name, record,
        indexed_records)` to accept it as the complete record its name implies
        against indexed parents only. Temporary, unknown, several or mutually
        supporting files are refused as they are.
        """
        findings = self.verify_index()
        if findings != ("archive_inventory_changed",):
            return findings
        indexed = {str(item["path"]) for item in self._indexed_entries()}
        actual = self._archive_paths()
        extra = set(actual) - indexed
        if indexed - set(actual) or len(extra) != 1:
            return findings
        path = actual[next(iter(extra))]
        ledger = resolve_within(self._campaign_dir(), "ledger")
        if path.parent != ledger or path.suffix != ".json":
            return findings
        records = self.ledger_records()
        indexed_records = {
            stem: value
            for stem, value in records.items()
            if self.ledger_path_for(stem).relative_to(self.root).as_posix() in indexed
        }
        if record_findings(path.stem, records.get(path.stem, {}), indexed_records):
            return findings
        self.refresh_index()
        return self.verify_index()

    def verify_index(
        self, *, tolerate: frozenset[str] = frozenset()
    ) -> tuple[str, ...]:
        """Rehash source bytes and refuse omissions, additions or changes.

        Unindexed paths named in `tolerate` are left out of the comparison;
        by default nothing is tolerated.
        """
        try:
            entries = self._indexed_entries()
            indexed = {item["path"]: item for item in entries}
            actual = {
                name: path
                for name, path in self._archive_paths().items()
                if name in indexed or name not in tolerate
            }
            if len(indexed) != len(entries) or set(indexed) != set(actual):
                return ("archive_inventory_changed",)
            for name, path in actual.items():
                resolved = path.resolve()
                if not resolved.is_relative_to(self.root):
                    return ("archive_path_escaped",)
                raw = resolved.read_bytes()
                if indexed[name]["sha256"] != hashlib.sha256(
                    raw
                ).hexdigest() or indexed[name]["bytes"] != len(raw):
                    return ("archive_bytes_changed",)
        except ValueError as exc:
            if "bytes changed" in str(exc):
                return ("archive_bytes_changed",)
            return ("archive_index_unreadable",)
        except (OSError, KeyError, TypeError):
            return ("archive_index_unreadable",)
        return ()

    @staticmethod
    def _validate(bundle: ServerPtCommissioningBundle) -> None:
        if (
            hashlib.sha256(bundle.intent_json.encode("utf-8")).hexdigest()
            != bundle.intent_sha256
            or hashlib.sha256(bundle.topology_json.encode("utf-8")).hexdigest()
            != bundle.topology_sha256
        ):
            raise ValueError("commissioning input digest mismatch")
        plan = TopologyPlan.model_validate_json(bundle.topology_json)
        if plan.physical_identity_hash != bundle.physical_topology_hash:
            raise ValueError("commissioning physical plan identity mismatch")
