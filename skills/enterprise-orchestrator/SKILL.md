---
name: enterprise-orchestrator
description: Clasifica y secuencia solicitudes Enterprise que cruzan varias fases o dominios; no usar cuando una sola Skill especializada puede resolver el paso activo.
---

# Enterprise Network Orchestrator

## Responsibility

Elegir el owner de cada paso, ordenar handoffs y componer resultados sin absorber las decisiones de las Skills especializadas.

## When this is primary

Usar esta Skill cuando la solicitud necesita coordinar varios entregables, por ejemplo diseño, dimensionamiento, despliegue, dominios de red y aceptación. Una petición limitada a IPAM, layout, routing, runtime u otro dominio debe ir directamente a su owner.

## Sequencing workflow

1. Clasificar el resultado solicitado y el estado actual del trabajo.
2. Seleccionar una Skill primaria para el paso y hasta dos supporting Skills permitidas por `skills/manifest.json`.
3. Entregar al owner sólo los artefactos, decisiones y evidencia que necesita.
4. Cuando el paso termina, transferir la propiedad del razonamiento activo al siguiente owner; no afirmar que el cliente descargó contexto físicamente.
5. Componer el resultado conservando por separado decisiones, exposición, evidencia, límites y trabajo pendiente.

## Boundaries

- No decide addressing, hardware, política de dominio, comandos, acceptance ni diagnosis por cuenta propia.
- No convierte `execute_enterprise_reference` interno en una operación pública.
- No sustituye una exposición ausente con raw IOS, JavaScript o compatibilidad de desarrollo.
- No repite facts de modelos, capabilities, dependencias o runtime que tienen owner actual.

## Hard stops

Detener la secuencia cuando el siguiente owner no tenga prerequisite, identidad, exposición o evidencia suficiente. La orquestación no puede resolver una contradicción de source ni promover UNKNOWN para continuar.

## Source-of-truth navigation

Consultar `references/workflow.md` sólo para una solicitud realmente multi-fase. Para cada handoff, usar Graphify como localizador focal y confirmar el contrato en source/tests o evidencia runtime vigente.

## Reference

- Leer [references/workflow.md](references/workflow.md) para clasificar fases y handoffs; no cargarla para trabajo de un solo dominio.
