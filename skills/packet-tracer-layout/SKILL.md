---
name: packet-tracer-layout
description: Genera layouts jerárquicos, deterministas y legibles para topologías Enterprise sin alterar la semántica física o lógica de la red.
---

# Packet Tracer Layout

## Responsibility

Convertir Concrete TopologyPlan en posiciones visuales limpias y reproducibles.

## Core workflow

site -> building -> floor -> zone -> infrastructure role -> endpoint rows -> relative layout checks.

## Rules

- Layout es presentation state, no topology.
- No cambiar dispositivos, addresses, links, VLANs, routing ni redundancy.
- Centrar filas respecto al site, respetar capas y alinear peers redundantes.
- Usar IDs estables sólo como tie-breaker determinista.
- Tratar Port-channel, SVI y Vlan interfaces como lógicos, nunca cableables.
- Verificar propiedades relativas si PT no ofrece getter exacto.

## Evidence / readiness

Preservar physical_topology_hash; un cambio visual puede cambiar layout_hash y artifact_hash, pero no el hash físico.

## Stop conditions

Detener si el layout intenta elegir hardware, cablear interfaz lógica o modificar la topología.

## Completion

Layout determinista, enviado a PT cuando corresponde y reportado como aplicado o parcialmente releído.

## References

Consultar el perfil de layout y el plan físico existente antes de tocar coordenadas.
