"""Backend catalogs and capability policies: device models and ports, cables, modules,
aliases, templates, and the measured capability profiles the planners consume."""

from .devices import (
    ALL_MODELS, DeviceModel, PortSpec,
    resolve_model, get_ports_by_speed, get_valid_ports,
)
from .cables import CABLE_TYPES, CABLE_RULES, ALL_LINK_TYPES, infer_cable
from .aliases import MODEL_ALIASES
from .templates import TEMPLATES, get_template, list_templates, TemplateSpec
from .modules import ALL_MODULES, ModuleSpec, resolve_module, get_serial_module, SERIAL_MODULES
from .service_capabilities import packet_tracer_service_capabilities
from .security_capabilities import packet_tracer_security_capabilities
from .control_plane_capabilities import packet_tracer_control_plane_capabilities
