---
name: routing-igp
description: Diseña, compila y verifica OSPFv2 y EIGRP IPv4 según capabilities observadas, separando adyacencia, RIB, forwarding, failover y recovery.
---

# Enterprise IGP Routing

## Responsibility

Compilar routing IGP desde identidades E4/E5 sin inventar addresses ni peers.

## Core workflow

RoutingIntent -> process/AS/IDs -> networks/passive interfaces -> typed plan -> apply -> neighbor read-back -> route read-back -> forwarding -> failure -> recovery.

## Rules

- Router IDs únicos y deterministas.
- Areas, networks, peers y passive interfaces vienen del plan.
- Adjacency, RIB, forwarding y convergence son evidencias distintas.
- Baseline obligatorio antes de fallos.
- No sustituir OSPF por EIGRP ni viceversa sin intent explícito.
- Consultar RuntimeQuirkRegistry antes de generalizar.

## Evidence / readiness

OSPF requiere configuración, vecino FULL, ruta remota y forwarding. EIGRP requiere configuración, vecino, ruta y forwarding; si falta cualquiera, permanece parcial.

## Stop conditions

Detener failover si neighbors/routes baseline no están verificados o si aparece output stale.

## Completion

Estado IGP con frescura, parser, next-hop, forwarding, convergence y recovery separados.

## References

- Consultar ospf.md.
- Consultar eigrp.md.
