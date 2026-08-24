"""Canonical declarative Enterprise scenarios."""

from .cp_scale import (
    CP_SCALE_ACCESS_POINT_COUNT,
    CP_SCALE_SITE_WORKLOAD_COUNTS,
    CP_SCALE_WORKLOAD_COUNTS,
    CPScalePoint,
    cp_scale_intent,
    cp_scale_intent_for,
    cp_scale_scale_fixture_intent,
)
from .cp_scale_physical import (
    cp_scale_canonical_control_plane_intent,
    cp_scale_physical_design,
)

__all__ = [
    "CP_SCALE_ACCESS_POINT_COUNT",
    "CP_SCALE_SITE_WORKLOAD_COUNTS",
    "CP_SCALE_WORKLOAD_COUNTS",
    "CPScalePoint",
    "cp_scale_intent",
    "cp_scale_intent_for",
    "cp_scale_scale_fixture_intent",
    "cp_scale_canonical_control_plane_intent",
    "cp_scale_physical_design",
]
