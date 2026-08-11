"""Selección determinista y explicable de capacidad y modo de enlace.

Python calcula y selecciona; el intent sólo aporta lo que se pidió. Ninguna
decisión vive en un renderer, y ningún porcentaje queda escondido en un
compiler: la reserva de ingeniería es una política inyectada y viaja en el
resultado junto a la demanda que la motivó.
"""

from __future__ import annotations

from ..models.link_performance import (
    ENTERPRISE_SERIAL_FALLBACK_BPS,
    SUPPORTED_SERIAL_RATES_BPS,
    CapacityRequestMode,
    CapacitySource,
    DuplexMode,
    HeadroomPolicy,
    LinkMedia,
    LinkPerformanceDecision,
    LinkPerformanceIntent,
    LinkPerformanceIssue,
    LinkPerformanceIssueCode,
    LinkSpeedMode,
    CapabilityReadiness,
    ObservedLinkPerformance,
    ReadinessStatus,
    ethernet_capacity_bps,
    nominal_link_ceiling_bps,
    auto_negotiable_ceiling_bps,
    forceable_speed_ceiling_bps,
)

_ETHERNET_SPEED_ORDER: tuple[LinkSpeedMode, ...] = (
    LinkSpeedMode.SPEED_10M, LinkSpeedMode.SPEED_100M, LinkSpeedMode.SPEED_1G,
)
_ETHERNET_SPEED_CAPACITY: dict[LinkSpeedMode, int] = {
    speed: ethernet_capacity_bps(speed) for speed in _ETHERNET_SPEED_ORDER
}


class LinkPerformancePlanner:
    """Servicio puro: mismas entradas, misma decisión, sin estado ni backend."""

    #: Cambiar cualquiera de estas reglas de forma que altere el resultado
    #: obliga a subir la version: la decision la lleva grabada y con ella
    #: viaja a la identidad semantica del plan.
    #: v2 (Stage 3A3): la capacidad Ethernet pasa a estar acotada por el menor
    #: de los dos extremos y por lo que cada puerto rechazó de verdad.
    #: v3 (Stage 3A3-B): el rechazo pasa a depender del contexto medido, el
    #: techo nominal se separa del mutuo verificado, y un modo sin medir deja
    #: de autorizar una mutación productiva.
    #: v4 (Stage 3A3-C): capacidad negociable y velocidad forzable dejan de
    #: ser el mismo techo -- forzar `speed` no resultó observable en ninguna
    #: plataforma medida -- y la demanda bajo AUTO se contrasta contra lo
    #: negociable con evidencia.
    POLICY_ID = "enterprise-link-performance"
    POLICY_VERSION = "4"

    def __init__(
        self,
        headroom: HeadroomPolicy | None = None,
        supported_serial_rates_bps: tuple[int, ...] = SUPPORTED_SERIAL_RATES_BPS,
        enterprise_serial_fallback_bps: int = ENTERPRISE_SERIAL_FALLBACK_BPS,
        policy_id: str | None = None,
        policy_version: str | None = None,
    ) -> None:
        self._policy_id = policy_id or self.POLICY_ID
        self._policy_version = policy_version or self.POLICY_VERSION
        self._headroom = headroom or HeadroomPolicy()
        self._serial_rates = tuple(sorted(set(supported_serial_rates_bps)))
        self._serial_fallback = enterprise_serial_fallback_bps

    def plan(self, intent: LinkPerformanceIntent) -> LinkPerformanceDecision:
        decision = LinkPerformanceDecision(
            link_id=intent.link_id,
            media=intent.media,
            role=intent.role,
            policy_id=self._policy_id,
            policy_version=self._policy_version,
            requested_capacity_bps=intent.requested_capacity_bps,
            requested_capacity_mode=intent.requested_capacity_mode,
            headroom_percent=self._headroom.engineering_headroom_percent,
            dce_endpoint_device_id=intent.dce_endpoint_device_id,
            dte_endpoint_device_id=intent.dte_endpoint_device_id,
        )
        decision.calculated_demand_bps = self._demand_bps(intent)
        decision.engineered_demand_bps = self._headroom.engineered_bps(
            decision.calculated_demand_bps,
        )
        if intent.media is LinkMedia.SERIAL:
            self._plan_serial(intent, decision)
        elif intent.media is LinkMedia.ETHERNET:
            self._plan_ethernet(intent, decision)
        else:
            decision.issues.append(LinkPerformanceIssue(
                code=LinkPerformanceIssueCode.MEDIA_UNKNOWN,
                link_id=intent.link_id,
                message="Link media must be resolved before performance policy applies.",
            ))
        if intent.sync_routing_bandwidth_to_effective_capacity and decision.effective_capacity_bps:
            decision.routing_bandwidth_kbps = decision.effective_capacity_bps // 1000
        return decision

    # -- demanda ---------------------------------------------------------

    @staticmethod
    def _demand_bps(intent: LinkPerformanceIntent) -> int:
        """Sólo el tráfico que atraviesa este enlace, más la supervivencia.

        La demanda de supervivencia no se suma a la normal: se toma la mayor de
        las dos, porque no ocurren a la vez.
        """
        normal = sum(item.demand_bps for item in intent.traffic)
        survival = intent.failure_survival_bps or 0
        required = max(normal, survival, intent.minimum_capacity_bps or 0)
        return max(0, required)

    # -- serial ----------------------------------------------------------

    def _plan_serial(
        self, intent: LinkPerformanceIntent, decision: LinkPerformanceDecision,
    ) -> None:
        decision.supported_capacities_bps = list(self._serial_rates)
        if not intent.dce_endpoint_device_id:
            decision.issues.append(LinkPerformanceIssue(
                code=LinkPerformanceIssueCode.DCE_ENDPOINT_UNRESOLVED,
                link_id=intent.link_id,
                message="A serial link needs an observed DCE endpoint before a clock is applied.",
            ))

        if intent.requested_capacity_bps:
            self._select_explicit_serial(intent, decision)
        elif decision.engineered_demand_bps > 0:
            self._select_engineered_serial(decision)
        else:
            decision.effective_capacity_bps = self._serial_fallback
            decision.capacity_source = CapacitySource.MEDIA_DEFAULT_POLICY
            decision.selection_reason = "ENTERPRISE_SERIAL_FALLBACK_WITHOUT_TRAFFIC_INFORMATION"

        if decision.effective_capacity_bps and not decision.issues:
            # El reloj es del extremo DCE y de nadie más.
            decision.serial_clock_rate_bps = decision.effective_capacity_bps

    def _select_explicit_serial(
        self, intent: LinkPerformanceIntent, decision: LinkPerformanceDecision,
    ) -> None:
        requested = int(intent.requested_capacity_bps or 0)
        decision.capacity_source = CapacitySource.EXPLICIT_USER
        if requested in self._serial_rates:
            decision.effective_capacity_bps = requested
            decision.selection_reason = "EXPLICIT_USER_RATE"
        elif intent.requested_capacity_mode is CapacityRequestMode.EXACT:
            # "Exactamente 3 Mbps" no puede convertirse en 4 en silencio.
            decision.effective_capacity_bps = None
            decision.selection_reason = "EXACT_RATE_NOT_SUPPORTED_BY_MEDIUM"
            decision.issues.append(LinkPerformanceIssue(
                code=LinkPerformanceIssueCode.EXACT_CAPACITY_UNSUPPORTED,
                link_id=decision.link_id,
                message=(
                    f"{requested} bps was requested exactly and is not a supported "
                    f"rate; supported rates are {list(self._serial_rates)}."
                ),
            ))
            return
        else:
            usable = [rate for rate in self._serial_rates if rate >= requested]
            if not usable:
                self._insufficient(decision, requested)
                return
            decision.effective_capacity_bps = usable[0]
            decision.selection_reason = "SMALLEST_SUPPORTED_RATE_MEETING_MINIMUM_REQUEST"
        if decision.engineered_demand_bps > (decision.effective_capacity_bps or 0):
            decision.warnings.append(
                "Explicit capacity is below the engineered demand for this link.",
            )

    def _select_engineered_serial(self, decision: LinkPerformanceDecision) -> None:
        usable = [
            rate for rate in self._serial_rates
            if rate >= decision.engineered_demand_bps
        ]
        if not usable:
            self._insufficient(decision, decision.engineered_demand_bps)
            return
        decision.effective_capacity_bps = usable[0]
        # Demanda agregada calculada, no un requisito de servicio declarado.
        decision.capacity_source = CapacitySource.TRAFFIC_CALCULATION
        decision.selection_reason = "SMALLEST_SUPPORTED_RATE_MEETING_ENGINEERED_DEMAND"

    def _insufficient(self, decision: LinkPerformanceDecision, required: int) -> None:
        """Nunca se elige la mayor tasa disponible y se declara éxito."""
        decision.effective_capacity_bps = None
        decision.serial_clock_rate_bps = None
        decision.selection_reason = "NO_SUPPORTED_RATE_MEETS_REQUIREMENT"
        decision.issues.append(LinkPerformanceIssue(
            code=LinkPerformanceIssueCode.LINK_CAPACITY_INSUFFICIENT,
            link_id=decision.link_id,
            message=(
                f"{required} bps exceeds the highest supported rate "
                f"{self._serial_rates[-1]} bps for this medium."
            ),
        ))

    # -- ethernet --------------------------------------------------------

    def _plan_ethernet(
        self, intent: LinkPerformanceIntent, decision: LinkPerformanceDecision,
    ) -> None:
        decision.supported_capacities_bps = [
            ethernet_capacity_bps(speed) for speed in _ETHERNET_SPEED_ORDER
        ]
        decision.nominal_link_ceiling_bps = self._nominal_ceiling(intent, decision)
        decision.auto_negotiable_ceiling_bps = auto_negotiable_ceiling_bps(
            intent.local_port_capability, intent.peer_port_capability,
            context=intent.link_context,
        )
        decision.forceable_speed_ceiling_bps = forceable_speed_ceiling_bps(
            intent.local_port_capability, intent.peer_port_capability,
            speed_capacity=_ETHERNET_SPEED_CAPACITY,
            context=intent.link_context,
        )
        if intent.requested_speed is LinkSpeedMode.AUTO:
            # Sin intent explícito no se fuerza nada: la negociación es la
            # política, y el ancho de banda lógico de plataforma se conserva.
            decision.effective_speed = LinkSpeedMode.AUTO
            decision.effective_duplex = intent.requested_duplex
            decision.capacity_source = CapacitySource.MEDIA_DEFAULT_POLICY
            decision.selection_reason = "AUTONEGOTIATION_LEFT_TO_THE_LINK"
            self._check_duplex(intent, decision)
            # Bajo AUTO la referencia correcta es lo que la negociación alcanza
            # con evidencia; el nominal sólo cubre el caso sin medir. El techo
            # forzable no pinta nada aquí: nadie está forzando.
            self._check_demand(
                intent, decision,
                decision.auto_negotiable_ceiling_bps or decision.nominal_link_ceiling_bps,
            )
            return

        if self._mode_refused_by_a_port(intent, decision):
            return
        if intent.peer_supported_speeds and intent.requested_speed not in intent.peer_supported_speeds:
            decision.issues.append(LinkPerformanceIssue(
                code=LinkPerformanceIssueCode.SPEED_NOT_SUPPORTED,
                link_id=intent.link_id,
                message=(
                    f"{intent.requested_speed.value} is not supported by both endpoints."
                ),
            ))
            return
        requested_capacity = ethernet_capacity_bps(intent.requested_speed)
        ceiling = decision.nominal_link_ceiling_bps
        if ceiling is not None and requested_capacity > ceiling:
            decision.issues.append(LinkPerformanceIssue(
                code=LinkPerformanceIssueCode.SPEED_NOT_SUPPORTED,
                link_id=intent.link_id,
                message=(
                    f"{intent.requested_speed.value} exceeds the {ceiling} bps "
                    "nominal ceiling set by the slower endpoint of this link."
                ),
            ))
            return
        if self._mode_unverified_for_production(intent, decision):
            return
        if not self._speed_request_is_satisfiable(intent, decision, requested_capacity):
            return
        decision.effective_speed = intent.requested_speed
        decision.effective_duplex = intent.requested_duplex
        decision.effective_capacity_bps = requested_capacity
        decision.capacity_source = CapacitySource.EXPLICIT_USER
        self._check_duplex(intent, decision)
        self._check_demand(intent, decision, decision.effective_capacity_bps)

    @staticmethod
    def _speed_request_is_satisfiable(
        intent: LinkPerformanceIntent,
        decision: LinkPerformanceDecision,
        requested_capacity: int,
    ) -> bool:
        """Fijar una velocidad y que el enlace la alcance no son lo mismo.

        Medido en tres plataformas: el CLI acepta `speed` sobre un puerto
        enlazado y la capacidad no se mueve. Así que una petición explícita
        sólo se satisface de dos maneras -- forzándola donde el forzado se
        demostró, o comprobando que la negociación ya llega a ese valor. Si no
        se da ninguna, decir que sí sería prometer un enlace de 100 Mbps sobre
        uno que corre a 1 Gbps.
        """
        capabilities = (intent.local_port_capability, intent.peer_port_capability)
        if all(capability is None for capability in capabilities):
            # Sin ningún perfil no hay nada medido que contradecir. La regla
            # vive donde vive la evidencia; extenderla a backends sin perfil
            # bloquearía peticiones sobre las que este proyecto no ha medido
            # nada, que es justamente lo contrario de lo que se pretende.
            decision.speed_forced = True
            decision.selection_reason = "EXPLICIT_USER_LINK_MODE"
            return True
        if intent.allow_unverified_mode_exploration:
            decision.speed_forced = True
            decision.selection_reason = "EXPLICIT_USER_LINK_MODE_UNDER_EXPLORATION"
            return True
        if all(
            capability is not None
            and capability.speed_is_forceable(intent.requested_speed, intent.link_context)
            for capability in capabilities
        ):
            decision.speed_forced = True
            decision.selection_reason = "EXPLICIT_USER_LINK_MODE_FORCED"
            return True
        negotiable = decision.auto_negotiable_ceiling_bps
        if negotiable is not None and negotiable == requested_capacity:
            decision.speed_forced = False
            decision.selection_reason = "REQUESTED_SPEED_MET_BY_NEGOTIATION_NOT_FORCED"
            decision.warnings.append(
                f"The link negotiates {negotiable} bps on its own, which matches "
                "the request; no speed command is emitted because forcing the "
                "rate was never observed to take effect on this backend."
            )
            return True
        if negotiable is None:
            decision.selection_reason = "SPEED_FORCING_UNVERIFIED_AND_NEGOTIATION_UNKNOWN"
            decision.issues.append(LinkPerformanceIssue(
                code=LinkPerformanceIssueCode.LINK_MODE_NOT_VERIFIED,
                link_id=intent.link_id,
                message=(
                    f"speed {intent.requested_speed.value} cannot be forced on this "
                    "backend and what the link negotiates was never observed."
                ),
            ))
            return False
        decision.selection_reason = "SPEED_FORCING_UNVERIFIED_AND_NEGOTIATION_DIFFERS"
        decision.issues.append(LinkPerformanceIssue(
            code=LinkPerformanceIssueCode.LINK_MODE_NOT_VERIFIED,
            link_id=intent.link_id,
            message=(
                f"speed {intent.requested_speed.value} cannot be forced on this "
                f"backend, and the link negotiates {negotiable} bps instead of "
                f"{requested_capacity} bps."
            ),
        ))
        return False

    @staticmethod
    def _nominal_ceiling(
        intent: LinkPerformanceIntent, decision: LinkPerformanceDecision,
    ) -> int | None:
        ceiling = nominal_link_ceiling_bps(
            intent.local_port_capability, intent.peer_port_capability,
        )
        nominals = [
            capability.nominal_capacity_bps
            for capability in (intent.local_port_capability, intent.peer_port_capability)
            if capability is not None and capability.nominal_capacity_bps > 0
        ]
        if ceiling is not None and max(nominals) != ceiling:
            decision.warnings.append(
                f"Link runs at {ceiling} bps: the endpoints are asymmetric "
                f"({max(nominals)} bps on the faster side)."
            )
        return ceiling

    @staticmethod
    def _readiness_for_request(
        capability, intent: LinkPerformanceIntent,
    ) -> CapabilityReadiness:
        return capability.readiness_for(
            intent.requested_speed, intent.requested_duplex, intent.link_context,
        )

    def _mode_refused_by_a_port(
        self, intent: LinkPerformanceIntent, decision: LinkPerformanceDecision,
    ) -> bool:
        """Solo bloquea lo que el backend rechazó, en el contexto en que lo hizo.

        Sin medir no es rechazo: eso lo resuelve `_mode_unverified_for_production`,
        que es una pregunta distinta.
        """
        for capability in (intent.local_port_capability, intent.peer_port_capability):
            if capability is None:
                continue
            readiness = self._readiness_for_request(capability, intent)
            if readiness.apply is not ReadinessStatus.UNSUPPORTED:
                continue
            observation = capability.observation_for(
                intent.requested_speed, intent.requested_duplex, intent.link_context,
            )
            # Cuál de los dos ejes falla no se deduce de que el intent fije el
            # duplex: pedir 1G full en un puerto FastEthernet se rechaza por la
            # velocidad. Si esa velocidad ya se rechaza con el duplex en AUTO,
            # el eje culpable es la velocidad.
            speed_alone_rejected = (
                capability.readiness_for(
                    intent.requested_speed, DuplexMode.AUTO, intent.link_context,
                ).apply is ReadinessStatus.UNSUPPORTED
            )
            code = (
                LinkPerformanceIssueCode.SPEED_NOT_SUPPORTED
                if speed_alone_rejected or intent.requested_duplex is DuplexMode.AUTO
                else LinkPerformanceIssueCode.DUPLEX_NOT_SUPPORTED
            )
            decision.mode_readiness = readiness
            decision.issues.append(LinkPerformanceIssue(
                code=code,
                link_id=intent.link_id,
                message=(
                    f"{capability.device_model} {capability.port_kind} rejected "
                    f"speed {intent.requested_speed.value} duplex "
                    f"{intent.requested_duplex.value} in context "
                    f"{intent.link_context.value} on backend "
                    f"{capability.backend_version}"
                    + (f": {observation.prerequisite}" if observation and observation.prerequisite else ".")
                ),
            ))
            return True
        return False

    def _mode_unverified_for_production(
        self, intent: LinkPerformanceIntent, decision: LinkPerformanceDecision,
    ) -> bool:
        """Lo no verificado compila pero no muta en producción.

        `UNKNOWN` no es `UNSUPPORTED` -- no se declara nada falso -- pero
        tampoco es permiso. Una exploración controlada puede pedirlo
        explícitamente; la ruta productiva no.
        """
        weakest: CapabilityReadiness | None = None
        for capability in (intent.local_port_capability, intent.peer_port_capability):
            if capability is None:
                continue
            readiness = self._readiness_for_request(capability, intent)
            if readiness.apply is ReadinessStatus.READY:
                if weakest is None:
                    weakest = readiness
                continue
            weakest = readiness
            break
        decision.mode_readiness = weakest
        if weakest is None or weakest.apply is ReadinessStatus.READY:
            return False
        if intent.allow_unverified_mode_exploration:
            decision.warnings.append(
                "Controlled exploration: this mode was not verified on either "
                "endpoint and is being requested deliberately."
            )
            return False
        decision.issues.append(LinkPerformanceIssue(
            code=LinkPerformanceIssueCode.LINK_MODE_NOT_VERIFIED,
            link_id=intent.link_id,
            message=(
                f"speed {intent.requested_speed.value} duplex "
                f"{intent.requested_duplex.value} has apply readiness "
                f"{weakest.apply.value} on this link: not refused by the "
                "backend, but never shown to take effect either."
            ),
        ))
        return True

    @staticmethod
    def verify_observed_capacity(
        decision: LinkPerformanceDecision,
        observed: ObservedLinkPerformance,
        *,
        minimum_capacity_bps: int | None,
    ) -> list[LinkPerformanceIssue]:
        """Contrasta lo negociado contra el mínimo exigido, ya desplegado.

        Es un fallo distinto del de planificación: el plan cabía en el techo y
        la configuración se aplicó, pero el enlace negoció por debajo. Llamarlo
        `CONFIG_APPLY_FAILED` culparía a un paso que sí funcionó.

        Sin evidencia suficiente no se emite nada: desconocido no es
        incumplimiento.
        """
        meets = observed.meets(minimum_capacity_bps)
        if meets is not False:
            return []
        return [LinkPerformanceIssue(
            code=LinkPerformanceIssueCode.LINK_CAPACITY_BELOW_REQUIREMENT,
            link_id=decision.link_id,
            message=(
                f"The link negotiated {observed.effective_capacity_bps} bps, "
                f"below the required {minimum_capacity_bps} bps. The plan and "
                "the configuration were both applied as decided."
            ),
        )]

    @staticmethod
    def _check_demand(
        intent: LinkPerformanceIntent,
        decision: LinkPerformanceDecision,
        capacity_bps: int | None,
    ) -> None:
        if not capacity_bps or decision.engineered_demand_bps <= capacity_bps:
            return
        decision.issues.append(LinkPerformanceIssue(
            code=LinkPerformanceIssueCode.LINK_CAPACITY_INSUFFICIENT,
            link_id=intent.link_id,
            message=(
                f"{decision.engineered_demand_bps} bps exceeds "
                f"{capacity_bps} bps available on this link."
            ),
        ))

    @staticmethod
    def _check_duplex(
        intent: LinkPerformanceIntent, decision: LinkPerformanceDecision,
    ) -> None:
        """Un extremo fijado en full contra otro en half es el mismatch clásico."""
        peer = intent.peer_duplex
        if peer is None or peer is DuplexMode.AUTO:
            return
        if intent.requested_duplex is DuplexMode.AUTO:
            return
        if peer is not intent.requested_duplex:
            decision.issues.append(LinkPerformanceIssue(
                code=LinkPerformanceIssueCode.DUPLEX_MISMATCH,
                link_id=intent.link_id,
                message=(
                    f"Requested {intent.requested_duplex.value} duplex against a "
                    f"peer fixed at {peer.value}."
                ),
            ))
