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
    ethernet_capacity_bps,
)

_ETHERNET_SPEED_ORDER: tuple[LinkSpeedMode, ...] = (
    LinkSpeedMode.SPEED_10M, LinkSpeedMode.SPEED_100M, LinkSpeedMode.SPEED_1G,
)


class LinkPerformancePlanner:
    """Servicio puro: mismas entradas, misma decisión, sin estado ni backend."""

    #: Cambiar cualquiera de estas reglas de forma que altere el resultado
    #: obliga a subir la version: la decision la lleva grabada y con ella
    #: viaja a la identidad semantica del plan.
    POLICY_ID = "enterprise-link-performance"
    POLICY_VERSION = "1"

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
        decision.capacity_source = CapacitySource.SERVICE_REQUIREMENT
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
        if intent.requested_speed is LinkSpeedMode.AUTO:
            # Sin intent explícito no se fuerza nada: la negociación es la
            # política, y el ancho de banda lógico de plataforma se conserva.
            decision.effective_speed = LinkSpeedMode.AUTO
            decision.effective_duplex = intent.requested_duplex
            decision.capacity_source = CapacitySource.MEDIA_DEFAULT_POLICY
            decision.selection_reason = "AUTONEGOTIATION_LEFT_TO_THE_LINK"
            self._check_duplex(intent, decision)
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
        decision.effective_speed = intent.requested_speed
        decision.effective_duplex = intent.requested_duplex
        decision.effective_capacity_bps = ethernet_capacity_bps(intent.requested_speed)
        decision.capacity_source = CapacitySource.EXPLICIT_USER
        decision.selection_reason = "EXPLICIT_USER_LINK_MODE"
        self._check_duplex(intent, decision)
        if decision.engineered_demand_bps > (decision.effective_capacity_bps or 0):
            decision.issues.append(LinkPerformanceIssue(
                code=LinkPerformanceIssueCode.LINK_CAPACITY_INSUFFICIENT,
                link_id=intent.link_id,
                message=(
                    f"{decision.engineered_demand_bps} bps exceeds "
                    f"{decision.effective_capacity_bps} bps at the requested speed."
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
