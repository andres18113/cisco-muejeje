"""Patrones y capas semánticas de la topología física Enterprise."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class NetworkLayer(str, Enum):
    ACCESS = "access"
    DISTRIBUTION = "distribution"
    CORE = "core"
    EDGE = "edge"
    WAN = "wan"


class TopologyPattern(str, Enum):
    STAR = "star"
    EXTENDED_STAR = "extended_star"
    TREE = "tree"
    HIERARCHICAL = "hierarchical"
    HUB_AND_SPOKE = "hub_and_spoke"
    PARTIAL_MESH = "partial_mesh"
    FULL_MESH = "full_mesh"
    POINT_TO_POINT = "point_to_point"
    HYBRID = "hybrid"


class TopologyDesign(BaseModel):
    """Patrón principal y decisiones concretas por capa para topologías híbridas."""

    pattern: TopologyPattern
    layer_patterns: dict[NetworkLayer, TopologyPattern] = Field(default_factory=dict)
    network_layers: list[NetworkLayer] = Field(default_factory=list)
