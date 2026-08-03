"""Contratos puros de E4 para compilación física y layout."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field

from ...models.plans import TopologyPlan
from .roles import DeviceRole


class CompilationIssueSeverity(str, Enum):
    ERROR = "error"
    WARNING = "warning"


class CompilationIssueCode(str, Enum):
    MODEL_SELECTION_UNRESOLVED = "MODEL_SELECTION_UNRESOLVED"
    MODEL_SELECTION_PROVISIONAL = "MODEL_SELECTION_PROVISIONAL"
    ENDPOINT_MODEL_UNRESOLVED = "ENDPOINT_MODEL_UNRESOLVED"
    ENDPOINT_MODEL_GENERIC = "ENDPOINT_MODEL_GENERIC"
    HARDWARE_SITE_MISSING = "HARDWARE_SITE_MISSING"
    HIERARCHY_REFERENCE_MISSING = "HIERARCHY_REFERENCE_MISSING"
    DUPLICATE_DEVICE_ID = "DUPLICATE_DEVICE_ID"
    DUPLICATE_DEVICE_NAME = "DUPLICATE_DEVICE_NAME"
    DUPLICATE_LINK = "DUPLICATE_LINK"
    LINK_ENDPOINT_MISSING = "LINK_ENDPOINT_MISSING"
    SELF_LINK = "SELF_LINK"
    LOGICAL_PORT_SELECTED = "LOGICAL_PORT_SELECTED"
    PHYSICAL_PORT_MISSING = "PHYSICAL_PORT_MISSING"
    PORT_ALREADY_ASSIGNED = "PORT_ALREADY_ASSIGNED"
    PORT_CLASS_FALLBACK = "PORT_CLASS_FALLBACK"
    INSUFFICIENT_PHYSICAL_PORT_CAPACITY = "INSUFFICIENT_PHYSICAL_PORT_CAPACITY"
    ENDPOINT_ASSIGNMENT_MISSING = "ENDPOINT_ASSIGNMENT_MISSING"
    MODULE_SLOT_UNRESOLVED = "MODULE_SLOT_UNRESOLVED"
    POE_CAPABILITY_UNKNOWN = "POE_CAPABILITY_UNKNOWN"
    MODULE_CAPABILITY_UNKNOWN = "MODULE_CAPABILITY_UNKNOWN"
    LAYOUT_COLLISION = "LAYOUT_COLLISION"
    LAYOUT_COORDINATE_READBACK_PARTIAL = "LAYOUT_COORDINATE_READBACK_PARTIAL"


class CompilationIssue(BaseModel):
    severity: CompilationIssueSeverity
    code: CompilationIssueCode
    message: str
    subject: str = ""
    details: dict[str, str | int | bool] = Field(default_factory=dict)


class PhysicalModelProfile(BaseModel):
    """Vista backend-neutral de un modelo ya resuelto por un adapter."""

    model: str
    category: str
    physical_ports: list[str] = Field(default_factory=list)
    network_port: str = ""
    passthrough_port: str = ""
    generic: bool = False


class PhysicalCompilationProfile(BaseModel):
    """Catálogo físico inyectado; EnterprisePlan sigue libre de modelos runtime."""

    models: list[PhysicalModelProfile] = Field(default_factory=list)
    endpoint_role_models: dict[DeviceRole, str] = Field(default_factory=dict)
    device_name_prefix: str = ""
    max_device_name_length: int = 64
    default_cable: str = "straight"

    def model_by_name(self, model: str) -> PhysicalModelProfile | None:
        return next((item for item in self.models if item.model == model), None)


class ConcreteLinkRole(str, Enum):
    ENDPOINT_ACCESS = "endpoint_access"
    PHONE_PASSTHROUGH = "phone_passthrough"
    SERVER_ACCESS = "server_access"
    ACCESS_UPLINK = "access_uplink"
    DISTRIBUTION_UPLINK = "distribution_uplink"
    CORE_LINK = "core_link"
    EDGE_LINK = "edge_link"
    WAN_LINK = "wan_link"
    REDUNDANT_LINK = "redundant_link"


class LayoutProfile(BaseModel):
    horizontal_spacing: int = 140
    site_horizontal_padding: int | None = None
    vertical_spacing: int = 130
    group_spacing: int = 360
    site_spacing: int = 800
    floor_spacing: int = 260
    endpoint_row_size: int = 10
    paired_endpoint_offset: int = 55
    origin_x: int = 100
    origin_y: int = 100


class LayoutRegion(BaseModel):
    id: str
    kind: str
    parent_id: str = ""
    x: int
    y: int
    width: int
    height: int


class EnterpriseCompileSummary(BaseModel):
    plan_id: str
    semantic_hash: str = ""
    sites: int = 0
    network_devices: int = 0
    endpoints: int = 0
    endpoints_by_role: dict[str, int] = Field(default_factory=dict)
    devices: int = 0
    links: int = 0
    endpoint_access_links: int = 0
    phone_passthrough_links: int = 0
    infrastructure_links: int = 0
    warnings: int = 0
    errors: int = 0
    layout_width: int = 0
    layout_height: int = 0


class EnterpriseCompileResult(BaseModel):
    plan: TopologyPlan | None = None
    semantic_hash: str = ""
    summary: EnterpriseCompileSummary
    issues: list[CompilationIssue] = Field(default_factory=list)
    layout_regions: list[LayoutRegion] = Field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        return not any(issue.severity is CompilationIssueSeverity.ERROR for issue in self.issues)

    def compact_summary(self) -> dict[str, object]:
        return {
            **self.summary.model_dump(mode="json"),
            "valid": self.is_valid,
            "issues": [issue.model_dump(mode="json") for issue in self.issues],
        }
