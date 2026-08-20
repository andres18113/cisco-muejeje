"""Fail-closed replay classification for every typed product mutation family.

The registry is deliberately independent from transport adapters.  It records
what one repeated payload can do and which containment exists today; successful
read-back alone never upgrades a family to replay-safe.

Two fields carry authority and one does not.  `classification` and `basis` are
typed and validated; `evidence` is explanatory prose that no gate reads.  A
family cannot become REPLAY_SAFE because somebody wrote a convincing sentence.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import get_args

from .models.configuration import (
    ConfigurationAction,
    ConfigureAccessPort,
    ConfigureDhcpPool,
    ConfigureEthernetLinkMode,
    ConfigureInterfaceBandwidth,
    ConfigureRoutedInterface,
    ConfigureSerialClock,
    ConfigureSubinterface,
    ConfigureSvi,
    ConfigureTrunk,
    CreateVlan,
    SetEndpointDhcp,
    SetEndpointStaticAddress,
)
from .models.control_plane import (
    ControlPlaneAction,
    ConfigureEigrpIpv4,
    ConfigureEtherChannel,
    ConfigureHsrp,
    ConfigureOspfv2,
    ConfigureRipv2,
    ConfigureSpanningTree,
    ConfigureStpEdgePort,
)
from .models.security_plan import (
    AddSecurityAclRule,
    ApplyDeviceHardening,
    AttachSecurityAcl,
    ConfigureDhcpSnooping,
    ConfigureDynamicArpInspection,
    ConfigureEndpointPortSecurity,
    ConfigureSecurityNat,
    CreateSecurityAcl,
    SecurityAction,
)
from .models.service_plan import (
    AddDnsRecord,
    ConfigureNtpService,
    EnableDnsService,
    EnableHttpService,
    EnableHttpsService,
    EnableTftpService,
    PublishTftpFile,
    ServiceAction,
    SetHttpContent,
)
from .models.voice_plan import (
    BindPhoneToExtension,
    ConfigureCallControlSource,
    ConfigureDialRule,
    ConfigureVoiceDhcpOption,
    CreateExtension,
    EnableCallControl,
    GeneratePhoneConfigurationFiles,
    VoiceAction,
)


class MutationSurface(str, Enum):
    CONFIGURATION = "Enterprise Configuration"
    CONTROL_PLANE = "Control Plane"
    SECURITY = "Security"
    VOICE = "Voice"
    SERVICE = "Services"
    PHYSICAL = "Physical Topology"
    LEGACY_RAW = "Legacy / raw CLI"


class ReplayClassification(str, Enum):
    REPLAY_SAFE = "REPLAY_SAFE"
    TREAT_AS_REPLAY_UNSAFE = "TREAT_AS_REPLAY_UNSAFE"
    UNKNOWN = "UNKNOWN"


class EvidenceBasis(str, Enum):
    """How the classification was established -- never how well it was argued.

    The three states are ordered by strength and are NOT interchangeable.
    UNKNOWN classification requires UNMEASURED here; nothing else may.
    """

    #: Repetición controlada sobre Packet Tracer real, con relectura semántica.
    MEASURED_CONTROLLED_REPEAT = "measured_controlled_repeat"
    #: La repetición controlada SÍ se ejecutó, y el backend no publica ningún
    #: observador de su efecto. Es estrictamente más fuerte que UNMEASURED --
    #: se buscó -- y estrictamente más débil que MEASURED_CONTROLLED_REPEAT, que
    #: exige relectura semántica. Nunca puede sostener REPLAY_SAFE: no observar
    #: un efecto no es haber observado que no lo hay.
    MEASURED_CONTROLLED_REPEAT_UNOBSERVABLE = "measured_controlled_repeat_unobservable"
    #: El payload emitido se ejecutó en un motor JS real contra una llamada
    #: nativa instrumentada. Prueba el flujo del guard, no el backend.
    PAYLOAD_EXECUTION_SIMULATED = "payload_execution_simulated"
    #: Sólo se leyó la FORMA del texto que emite el generador.
    PAYLOAD_SHAPE_ONLY = "payload_shape_only"
    #: No se midió nada. Es la única base admisible para UNKNOWN.
    UNMEASURED = "unmeasured"


class ReplayContainment(str, Enum):
    DECLARATIVE_REAPPLICATION = "declarative_reapplication"
    STRUCTURED_SETTER = "structured_setter"
    CAPABILITY_GATE = "capability_gate"
    PRE_READ_FAIL_CLOSED = "pre_read_fail_closed"
    IN_PAYLOAD_EFFECT_GUARD = "in_payload_effect_guard"
    NO_BLIND_RETRY = "no_blind_retry"
    INDEPENDENT_READBACK = "independent_readback"
    CONTROLLED_REPEAT_QUALIFIED = "controlled_repeat_qualified"
    REFUSED_OR_NO_MUTATION = "refused_or_no_mutation"
    #: Nombra la ausencia en vez de disimularla: este camino no tiene ninguna
    #: contención estructural. Nunca puede acompañar a REPLAY_SAFE.
    NONE_ESTABLISHED = "none_established"


#: Contenciones que por sí solas pueden sostener REPLAY_SAFE. Una `evidence`
#: no vacía JAMÁS entra en este conjunto: la prosa no es contención.
_SUFFICIENT_FOR_SAFE = frozenset({
    ReplayContainment.DECLARATIVE_REAPPLICATION,
    ReplayContainment.STRUCTURED_SETTER,
    ReplayContainment.IN_PAYLOAD_EFFECT_GUARD,
    ReplayContainment.CONTROLLED_REPEAT_QUALIFIED,
})


@dataclass(frozen=True)
class MutationReplayPolicy:
    surface: MutationSurface
    family: str
    entrypoint: str
    classification: ReplayClassification
    basis: EvidenceBasis
    containment: tuple[ReplayContainment, ...]
    evidence: str
    action_type: type | None = None


class UnclassifiedProductMutation(LookupError):
    """Raised instead of assigning a default replay classification."""


_CONFIGURATION_ENTRYPOINT = (
    "packet_tracer_mcp.infrastructure.execution.enterprise_configuration_runtime."
    "PacketTracerEnterpriseConfigurationRuntime.apply_actions"
)
_CONTROL_PLANE_ENTRYPOINT = (
    "packet_tracer_mcp.infrastructure.execution.enterprise_control_plane_runtime."
    "PacketTracerEnterpriseControlPlaneRuntime.apply_actions"
)
_SECURITY_ENTRYPOINT = (
    "packet_tracer_mcp.infrastructure.execution.enterprise_security_runtime."
    "PacketTracerEnterpriseSecurityRuntime.apply_actions"
)
_VOICE_ENTRYPOINT = (
    "packet_tracer_mcp.infrastructure.execution.enterprise_voice_runtime."
    "PacketTracerEnterpriseVoiceRuntime.apply_actions"
)
_SERVICE_ENTRYPOINT = (
    "packet_tracer_mcp.infrastructure.execution.enterprise_service_runtime."
    "PacketTracerEnterpriseServiceRuntime.apply_actions"
)
_PHYSICAL_ENTRYPOINT = (
    "packet_tracer_mcp.infrastructure.execution.packet_tracer_physical_runtime."
    "PacketTracerPhysicalTopologyRuntime."
)
_LEGACY_ACL_ENTRYPOINT = (
    "packet_tracer_mcp.adapters.mcp.tool_registry.pt_apply_acl"
)

_DECLARATIVE = (
    ReplayContainment.DECLARATIVE_REAPPLICATION,
    ReplayContainment.NO_BLIND_RETRY,
    ReplayContainment.INDEPENDENT_READBACK,
)
_GATED_DECLARATIVE = (
    ReplayContainment.DECLARATIVE_REAPPLICATION,
    ReplayContainment.CAPABILITY_GATE,
    ReplayContainment.NO_BLIND_RETRY,
    ReplayContainment.INDEPENDENT_READBACK,
)
_STRUCTURED_SETTER = (
    ReplayContainment.STRUCTURED_SETTER,
    ReplayContainment.NO_BLIND_RETRY,
    ReplayContainment.INDEPENDENT_READBACK,
)
_CONSERVATIVE_READBACK = (
    ReplayContainment.NO_BLIND_RETRY,
    ReplayContainment.INDEPENDENT_READBACK,
)

_SHAPE = EvidenceBasis.PAYLOAD_SHAPE_ONLY
_UNMEASURED = EvidenceBasis.UNMEASURED


def _action_policy(
    surface: MutationSurface,
    action_type: type,
    entrypoint: str,
    classification: ReplayClassification,
    basis: EvidenceBasis,
    containment: tuple[ReplayContainment, ...],
    evidence: str,
) -> MutationReplayPolicy:
    return MutationReplayPolicy(
        surface=surface,
        family=action_type.__name__,
        action_type=action_type,
        entrypoint=entrypoint,
        classification=classification,
        basis=basis,
        containment=containment,
        evidence=evidence,
    )


def _named_policy(
    surface: MutationSurface,
    family: str,
    entrypoint: str,
    classification: ReplayClassification,
    basis: EvidenceBasis,
    containment: tuple[ReplayContainment, ...],
    evidence: str,
) -> MutationReplayPolicy:
    return MutationReplayPolicy(
        surface=surface,
        family=family,
        entrypoint=entrypoint,
        classification=classification,
        basis=basis,
        containment=containment,
        evidence=evidence,
    )


def _physical_policy(
    family: str,
    method: str,
    classification: ReplayClassification,
    basis: EvidenceBasis,
    containment: tuple[ReplayContainment, ...],
    evidence: str,
) -> MutationReplayPolicy:
    return _named_policy(
        MutationSurface.PHYSICAL, family, _PHYSICAL_ENTRYPOINT + method,
        classification, basis, containment, evidence,
    )


PRODUCT_MUTATION_REPLAY_REGISTRY: tuple[MutationReplayPolicy, ...] = (
    _action_policy(
        MutationSurface.CONFIGURATION, CreateVlan, _CONFIGURATION_ENTRYPOINT,
        ReplayClassification.REPLAY_SAFE, _SHAPE, _DECLARATIVE,
        "VLAN creation is keyed by VLAN id and reasserts the requested state.",
    ),
    _action_policy(
        MutationSurface.CONFIGURATION, ConfigureAccessPort,
        _CONFIGURATION_ENTRYPOINT, ReplayClassification.REPLAY_SAFE, _SHAPE,
        _DECLARATIVE,
        "Access mode and VLAN membership are declarative interface assignments.",
    ),
    _action_policy(
        MutationSurface.CONFIGURATION, ConfigureTrunk, _CONFIGURATION_ENTRYPOINT,
        ReplayClassification.REPLAY_SAFE, _SHAPE, _DECLARATIVE,
        "The complete allowed-VLAN set is assigned without the additive form.",
    ),
    _action_policy(
        MutationSurface.CONFIGURATION, ConfigureRoutedInterface,
        _CONFIGURATION_ENTRYPOINT, ReplayClassification.REPLAY_SAFE, _SHAPE,
        _DECLARATIVE,
        "Routed-interface address and administrative state are assignments.",
    ),
    _action_policy(
        MutationSurface.CONFIGURATION, ConfigureSvi, _CONFIGURATION_ENTRYPOINT,
        ReplayClassification.REPLAY_SAFE, _SHAPE, _DECLARATIVE,
        "SVI identity, address, and administrative state are keyed assignments.",
    ),
    _action_policy(
        MutationSurface.CONFIGURATION, ConfigureSubinterface,
        _CONFIGURATION_ENTRYPOINT, ReplayClassification.REPLAY_SAFE, _SHAPE,
        _DECLARATIVE,
        "Subinterface encapsulation and address are keyed assignments.",
    ),
    _action_policy(
        MutationSurface.CONFIGURATION, ConfigureDhcpPool,
        _CONFIGURATION_ENTRYPOINT, ReplayClassification.REPLAY_SAFE, _SHAPE,
        _DECLARATIVE,
        "The named DHCP pool fields are reasserted as declarative values.",
    ),
    _action_policy(
        MutationSurface.CONFIGURATION, SetEndpointStaticAddress,
        _CONFIGURATION_ENTRYPOINT, ReplayClassification.REPLAY_SAFE, _SHAPE,
        _STRUCTURED_SETTER,
        "The endpoint adapter invokes the structured static-address setter.",
    ),
    _action_policy(
        MutationSurface.CONFIGURATION, SetEndpointDhcp, _CONFIGURATION_ENTRYPOINT,
        ReplayClassification.REPLAY_SAFE, _SHAPE, _STRUCTURED_SETTER,
        "The endpoint adapter invokes the structured DHCP-mode setter.",
    ),
    _action_policy(
        MutationSurface.CONFIGURATION, ConfigureSerialClock,
        _CONFIGURATION_ENTRYPOINT, ReplayClassification.REPLAY_SAFE, _SHAPE,
        _DECLARATIVE,
        "Clock rate is a single interface value assignment.",
    ),
    _action_policy(
        MutationSurface.CONFIGURATION, ConfigureInterfaceBandwidth,
        _CONFIGURATION_ENTRYPOINT, ReplayClassification.REPLAY_SAFE, _SHAPE,
        _DECLARATIVE,
        "Routing bandwidth is a single interface value assignment.",
    ),
    _action_policy(
        MutationSurface.CONFIGURATION, ConfigureEthernetLinkMode,
        _CONFIGURATION_ENTRYPOINT, ReplayClassification.REPLAY_SAFE, _SHAPE,
        _DECLARATIVE,
        "Speed and duplex are declarative interface values.",
    ),

    _action_policy(
        MutationSurface.CONTROL_PLANE, ConfigureSpanningTree,
        _CONTROL_PLANE_ENTRYPOINT, ReplayClassification.REPLAY_SAFE, _SHAPE,
        _GATED_DECLARATIVE,
        "STP mode, priorities, and VLAN-instance membership are keyed state.",
    ),
    _action_policy(
        MutationSurface.CONTROL_PLANE, ConfigureStpEdgePort,
        _CONTROL_PLANE_ENTRYPOINT, ReplayClassification.REPLAY_SAFE, _SHAPE,
        _GATED_DECLARATIVE,
        "PortFast and BPDU Guard are declarative interface switches.",
    ),
    _action_policy(
        MutationSurface.CONTROL_PLANE, ConfigureEtherChannel,
        _CONTROL_PLANE_ENTRYPOINT, ReplayClassification.REPLAY_SAFE, _SHAPE,
        _GATED_DECLARATIVE,
        "Channel group, mode, and port-channel values are keyed assignments.",
    ),
    _action_policy(
        MutationSurface.CONTROL_PLANE, ConfigureHsrp, _CONTROL_PLANE_ENTRYPOINT,
        ReplayClassification.REPLAY_SAFE, _SHAPE, _GATED_DECLARATIVE,
        "HSRP group address, priority, and preempt are keyed assignments.",
    ),
    _action_policy(
        MutationSurface.CONTROL_PLANE, ConfigureOspfv2,
        _CONTROL_PLANE_ENTRYPOINT, ReplayClassification.REPLAY_SAFE, _SHAPE,
        _GATED_DECLARATIVE,
        "OSPF process, networks, and passive interfaces are set-shaped state.",
    ),
    _action_policy(
        MutationSurface.CONTROL_PLANE, ConfigureEigrpIpv4,
        _CONTROL_PLANE_ENTRYPOINT, ReplayClassification.REPLAY_SAFE, _SHAPE,
        _GATED_DECLARATIVE,
        "EIGRP process, networks, and passive interfaces are set-shaped state.",
    ),
    _action_policy(
        MutationSurface.CONTROL_PLANE, ConfigureRipv2, _CONTROL_PLANE_ENTRYPOINT,
        ReplayClassification.REPLAY_SAFE,
        EvidenceBasis.MEASURED_CONTROLLED_REPEAT,
        _GATED_DECLARATIVE
        + (ReplayContainment.CONTROLLED_REPEAT_QUALIFIED,),
        "An exact 2911/PT 9.0.1.0858 qualification repeated the typed payload.",
    ),

    _action_policy(
        MutationSurface.SECURITY, CreateSecurityAcl, _SECURITY_ENTRYPOINT,
        ReplayClassification.UNKNOWN, _UNMEASURED,
        (ReplayContainment.REFUSED_OR_NO_MUTATION,),
        "The renderer refuses this declarative shell before dispatching IOS.",
    ),
    _action_policy(
        MutationSurface.SECURITY, AddSecurityAclRule, _SECURITY_ENTRYPOINT,
        ReplayClassification.TREAT_AS_REPLAY_UNSAFE, _SHAPE,
        _CONSERVATIVE_READBACK,
        "Numbered ACL rule rendering is structurally additive and unqualified live.",
    ),
    _action_policy(
        MutationSurface.SECURITY, AttachSecurityAcl, _SECURITY_ENTRYPOINT,
        ReplayClassification.REPLAY_SAFE, _SHAPE, _GATED_DECLARATIVE,
        "Interface ACL attachment is a keyed direction assignment.",
    ),
    _action_policy(
        MutationSurface.SECURITY, ConfigureSecurityNat, _SECURITY_ENTRYPOINT,
        ReplayClassification.TREAT_AS_REPLAY_UNSAFE, _SHAPE,
        _CONSERVATIVE_READBACK,
        "Dynamic and PAT variants include the structurally additive ACL body.",
    ),
    _action_policy(
        MutationSurface.SECURITY, ConfigureEndpointPortSecurity,
        _SECURITY_ENTRYPOINT, ReplayClassification.REPLAY_SAFE, _SHAPE,
        _GATED_DECLARATIVE,
        "Port-security limits, violation mode, and sticky mode are assignments.",
    ),
    _action_policy(
        MutationSurface.SECURITY, ConfigureDhcpSnooping, _SECURITY_ENTRYPOINT,
        ReplayClassification.REPLAY_SAFE, _SHAPE, _GATED_DECLARATIVE,
        "Snooping VLAN enablement and interface trust are declarative state.",
    ),
    _action_policy(
        MutationSurface.SECURITY, ConfigureDynamicArpInspection,
        _SECURITY_ENTRYPOINT, ReplayClassification.REPLAY_SAFE, _SHAPE,
        _GATED_DECLARATIVE,
        "DAI VLAN enablement and interface trust are declarative state.",
    ),
    _action_policy(
        MutationSurface.SECURITY, ApplyDeviceHardening, _SECURITY_ENTRYPOINT,
        ReplayClassification.REPLAY_SAFE, _SHAPE, _GATED_DECLARATIVE,
        "Banner and service password-encryption reassert configured values.",
    ),

    _action_policy(
        MutationSurface.VOICE, EnableCallControl, _VOICE_ENTRYPOINT,
        ReplayClassification.REPLAY_SAFE, _SHAPE, _GATED_DECLARATIVE,
        "Telephony-service limits and registration mode are keyed values.",
    ),
    _action_policy(
        MutationSurface.VOICE, ConfigureCallControlSource, _VOICE_ENTRYPOINT,
        ReplayClassification.REPLAY_SAFE, _SHAPE, _GATED_DECLARATIVE,
        "Call-control source address and signaling port are assignments.",
    ),
    _action_policy(
        MutationSurface.VOICE, CreateExtension, _VOICE_ENTRYPOINT,
        ReplayClassification.REPLAY_SAFE, _SHAPE, _GATED_DECLARATIVE,
        "The ephone-dn index keys a directory-number assignment.",
    ),
    _action_policy(
        MutationSurface.VOICE, BindPhoneToExtension, _VOICE_ENTRYPOINT,
        ReplayClassification.REPLAY_SAFE, _SHAPE, _GATED_DECLARATIVE,
        "The ephone index keys MAC, type, and button assignments.",
    ),
    _action_policy(
        MutationSurface.VOICE, ConfigureVoiceDhcpOption, _VOICE_ENTRYPOINT,
        ReplayClassification.REPLAY_SAFE, _SHAPE, _GATED_DECLARATIVE,
        "DHCP option 150 is assigned inside a named pool.",
    ),
    _action_policy(
        MutationSurface.VOICE, GeneratePhoneConfigurationFiles,
        _VOICE_ENTRYPOINT, ReplayClassification.TREAT_AS_REPLAY_UNSAFE,
        EvidenceBasis.MEASURED_CONTROLLED_REPEAT_UNOBSERVABLE,
        # `INDEPENDENT_READBACK` estaba declarada y es FALSA: no existe relectura
        # que pueda observar el efecto de este comando en este backend. Una
        # contención inventada es peor que ninguna, porque se cuenta como
        # control al leer la tabla.
        (
            ReplayContainment.CAPABILITY_GATE,
            ReplayContainment.NO_BLIND_RETRY,
        ),
        "Controlled repeat on Packet Tracer 9.0.1.0858 / 2811: create cnf-files "
        "was dispatched twice and no observer exists. `show telephony-service` "
        "is not implemented in that image, `show ephone` answers empty, none of "
        "the 146 enumerated Router members touches telephony, and only "
        "`VlanManager` answers getProcess out of nine candidates. Both passes "
        "were byte-identical on every observable, which establishes that nothing "
        "changed in what can be seen -- not that nothing changed.",
    ),
    _action_policy(
        MutationSurface.VOICE, ConfigureDialRule, _VOICE_ENTRYPOINT,
        ReplayClassification.UNKNOWN, _UNMEASURED,
        (
            ReplayContainment.CAPABILITY_GATE,
            ReplayContainment.REFUSED_OR_NO_MUTATION,
        ),
        "The current renderer emits no local dial mutation and refuses non-local rules.",
    ),

    _action_policy(
        MutationSurface.SERVICE, EnableDnsService, _SERVICE_ENTRYPOINT,
        ReplayClassification.REPLAY_SAFE, _SHAPE, _STRUCTURED_SETTER,
        "The DNS process enable flag is set and read back in the payload.",
    ),
    _action_policy(
        MutationSurface.SERVICE, AddDnsRecord, _SERVICE_ENTRYPOINT,
        ReplayClassification.UNKNOWN, _UNMEASURED, _CONSERVATIVE_READBACK,
        "The native add-record call runs before membership read-back; repeat behavior is unmeasured.",
    ),
    _action_policy(
        MutationSurface.SERVICE, EnableHttpService, _SERVICE_ENTRYPOINT,
        ReplayClassification.REPLAY_SAFE, _SHAPE, _STRUCTURED_SETTER,
        "The HTTP process enable flag is set and read back in the payload.",
    ),
    _action_policy(
        MutationSurface.SERVICE, SetHttpContent, _SERVICE_ENTRYPOINT,
        ReplayClassification.REPLAY_SAFE, _SHAPE, _STRUCTURED_SETTER,
        "The fixed page path is assigned exact content and read back.",
    ),
    _action_policy(
        MutationSurface.SERVICE, EnableHttpsService, _SERVICE_ENTRYPOINT,
        ReplayClassification.REPLAY_SAFE, _SHAPE, _STRUCTURED_SETTER,
        "The HTTPS process enable flag is set and read back in the payload.",
    ),
    _action_policy(
        MutationSurface.SERVICE, ConfigureNtpService, _SERVICE_ENTRYPOINT,
        ReplayClassification.REPLAY_SAFE, _SHAPE, _STRUCTURED_SETTER,
        "The NTP process enable flag is set and read back in the payload.",
    ),
    _action_policy(
        MutationSurface.SERVICE, EnableTftpService, _SERVICE_ENTRYPOINT,
        ReplayClassification.REPLAY_SAFE, _SHAPE, _STRUCTURED_SETTER,
        "The TFTP process enable flag is set and read back in the payload.",
    ),
    _action_policy(
        MutationSurface.SERVICE, PublishTftpFile, _SERVICE_ENTRYPOINT,
        ReplayClassification.UNKNOWN, _UNMEASURED,
        (ReplayContainment.REFUSED_OR_NO_MUTATION,),
        "The registered runtime returns failure without issuing a publication mutation.",
    ),

    _physical_policy(
        "PhysicalEnsureDevice", "ensure_device", ReplayClassification.UNKNOWN,
        _UNMEASURED,
        (
            ReplayContainment.PRE_READ_FAIL_CLOSED,
            ReplayContainment.NO_BLIND_RETRY,
            ReplayContainment.INDEPENDENT_READBACK,
        ),
        "The pre-read is outside the payload; same-request backend replay is unmeasured.",
    ),
    _physical_policy(
        "PhysicalEnsureModule", "ensure_module",
        ReplayClassification.REPLAY_SAFE,
        EvidenceBasis.PAYLOAD_EXECUTION_SIMULATED,
        (
            ReplayContainment.PRE_READ_FAIL_CLOSED,
            ReplayContainment.IN_PAYLOAD_EFFECT_GUARD,
            ReplayContainment.NO_BLIND_RETRY,
            ReplayContainment.INDEPENDENT_READBACK,
        ),
        "A per-request receipt and exact slot-effect guard were executed in a real "
        "JS engine against an instrumented addModule: one native call across four "
        "post-states. Not measured against Packet Tracer; identity stays unobservable.",
    ),
    _physical_policy(
        "PhysicalEnsureLink", "ensure_link", ReplayClassification.UNKNOWN,
        _UNMEASURED,
        (
            ReplayContainment.PRE_READ_FAIL_CLOSED,
            ReplayContainment.NO_BLIND_RETRY,
            ReplayContainment.INDEPENDENT_READBACK,
        ),
        "Exact endpoint pre-read is outside the payload; duplicate addLink behavior is unmeasured.",
    ),
    _physical_policy(
        "PhysicalRemoveDevice", "remove_device",
        ReplayClassification.REPLAY_SAFE, _SHAPE,
        (
            ReplayContainment.IN_PAYLOAD_EFFECT_GUARD,
            ReplayContainment.NO_BLIND_RETRY,
            ReplayContainment.INDEPENDENT_READBACK,
        ),
        "The payload rechecks exact identity and a repeated evaluation cannot remove a missing target.",
    ),

    # El camino legacy no es una mutación tipada, pero SÍ está expuesto como
    # herramienta y SÍ muta. Sacarlo de la taxonomía al tipificar el resto lo
    # habría dejado sin ninguna clasificación, que es peor que clasificarlo mal.
    _named_policy(
        MutationSurface.LEGACY_RAW, "pt_apply_acl (ACLPlan)",
        _LEGACY_ACL_ENTRYPOINT,
        ReplayClassification.TREAT_AS_REPLAY_UNSAFE, _SHAPE,
        (ReplayContainment.NONE_ESTABLISHED,),
        "generate_acl_cli emits `access-list N permit|deny ...` with no preceding "
        "`no access-list N`, so the payload is structurally additive. It bypasses "
        "the typed compile/render/apply chain, so none of that containment applies.",
    ),
)


def _union_members(annotation) -> frozenset[type]:
    return frozenset(get_args(get_args(annotation)[0]))


def _validate_registry() -> None:
    expected = {
        MutationSurface.CONFIGURATION: _union_members(ConfigurationAction),
        MutationSurface.CONTROL_PLANE: _union_members(ControlPlaneAction),
        MutationSurface.SECURITY: _union_members(SecurityAction),
        MutationSurface.VOICE: _union_members(VoiceAction),
        MutationSurface.SERVICE: _union_members(ServiceAction),
    }
    families = [item.family for item in PRODUCT_MUTATION_REPLAY_REGISTRY]
    if len(families) != len(set(families)):
        raise RuntimeError("Product mutation replay registry contains duplicate families.")
    action_types = [
        item.action_type
        for item in PRODUCT_MUTATION_REPLAY_REGISTRY
        if item.action_type is not None
    ]
    if len(action_types) != len(set(action_types)):
        raise RuntimeError("A typed product action has multiple replay policies.")
    for surface, surface_expected in expected.items():
        surface_actual = {
            item.action_type
            for item in PRODUCT_MUTATION_REPLAY_REGISTRY
            if item.surface is surface and item.action_type is not None
        }
        if surface_actual != surface_expected:
            missing = sorted(item.__name__ for item in surface_expected - surface_actual)
            unexpected = sorted(item.__name__ for item in surface_actual - surface_expected)
            raise RuntimeError(
                f"Incomplete replay registry for {surface.value}: "
                f"missing={missing}, unexpected={unexpected}."
            )
    for item in PRODUCT_MUTATION_REPLAY_REGISTRY:
        if not item.containment or not item.evidence.strip() or not item.entrypoint.strip():
            raise RuntimeError(f"Incomplete replay metadata for {item.family}.")

        # UNKNOWN significa "no se midió". No admite otra base, y ninguna otra
        # clasificación puede apoyarse en UNMEASURED.
        unknown = item.classification is ReplayClassification.UNKNOWN
        unmeasured = item.basis is EvidenceBasis.UNMEASURED
        if unknown != unmeasured:
            raise RuntimeError(
                f"{item.family}: UNKNOWN and UNMEASURED must coincide "
                f"(classification={item.classification.value}, basis={item.basis.value})."
            )

        if item.classification is ReplayClassification.REPLAY_SAFE:
            # Una `evidence` no vacía NO es contención. Sin una contención
            # estructural suficiente, REPLAY_SAFE no se sostiene.
            if not _SUFFICIENT_FOR_SAFE.intersection(item.containment):
                raise RuntimeError(
                    f"{item.family}: REPLAY_SAFE requires a structural containment "
                    f"from {sorted(value.value for value in _SUFFICIENT_FOR_SAFE)}, "
                    "not a non-empty evidence string."
                )
            if ReplayContainment.NONE_ESTABLISHED in item.containment:
                raise RuntimeError(
                    f"{item.family}: NONE_ESTABLISHED cannot accompany REPLAY_SAFE."
                )

        if (
            item.basis is EvidenceBasis.MEASURED_CONTROLLED_REPEAT
            and ReplayContainment.CONTROLLED_REPEAT_QUALIFIED not in item.containment
        ):
            raise RuntimeError(
                f"{item.family}: a measured controlled repeat must record "
                "CONTROLLED_REPEAT_QUALIFIED containment."
            )


_validate_registry()

_POLICY_BY_ACTION_TYPE = {
    item.action_type: item
    for item in PRODUCT_MUTATION_REPLAY_REGISTRY
    if item.action_type is not None
}
_POLICIES_BY_ENTRYPOINT: dict[str, tuple[MutationReplayPolicy, ...]] = {}
for _policy in PRODUCT_MUTATION_REPLAY_REGISTRY:
    _POLICIES_BY_ENTRYPOINT[_policy.entrypoint] = (
        *_POLICIES_BY_ENTRYPOINT.get(_policy.entrypoint, ()),
        _policy,
    )


def policy_for_action_type(action_type: type) -> MutationReplayPolicy:
    """Return an explicit policy; never assign an unknown family a default."""

    try:
        return _POLICY_BY_ACTION_TYPE[action_type]
    except KeyError as exc:
        raise UnclassifiedProductMutation(
            f"No replay policy is registered for {action_type.__name__}."
        ) from exc


def policies_for_entrypoint(entrypoint: str) -> tuple[MutationReplayPolicy, ...]:
    """Return all families dispatched by one product mutation entrypoint."""

    try:
        return _POLICIES_BY_ENTRYPOINT[entrypoint]
    except KeyError as exc:
        raise UnclassifiedProductMutation(
            f"No replay policy is registered for {entrypoint!r}."
        ) from exc


def taxonomy_by_surface() -> dict[str, dict[str, str]]:
    """Compatibility view for reports and the historical E9.5 taxonomy tests."""

    taxonomy: dict[str, dict[str, str]] = {}
    for surface in MutationSurface:
        records = {
            item.family: item.classification.value
            for item in PRODUCT_MUTATION_REPLAY_REGISTRY
            if item.surface is surface
        }
        if records:
            taxonomy[surface.value] = dict(sorted(records.items()))
    return taxonomy


__all__ = [
    "EvidenceBasis",
    "MutationReplayPolicy",
    "MutationSurface",
    "PRODUCT_MUTATION_REPLAY_REGISTRY",
    "ReplayClassification",
    "ReplayContainment",
    "UnclassifiedProductMutation",
    "policies_for_entrypoint",
    "policy_for_action_type",
    "taxonomy_by_surface",
]
