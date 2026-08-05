---
name: enterprise-orchestrator
description: Coordina solicitudes Enterprise de extremo a extremo en Packet Tracer, desde EnterpriseIntent hasta despliegue, configuración, servicios, seguridad, control-plane y verificación. Usar cuando una petición cruce varias fases; coordina Skills especializadas y no inventa IOS.
---

# Enterprise Network Orchestrator

## Responsibility

Coordina planners, compilers, runtime y acceptance sin duplicar su lógica.

## Core workflow

1. Resolver EnterpriseIntent y validar requisitos.
2. Construir o reutilizar EnterprisePlan.
3. Resolver IPAM, capacidad, hardware y capabilities.
4. Compilar Concrete TopologyPlan y validar readiness.
5. Desplegar sólo con DeploymentManifest y readiness suficiente.
6. Compilar planes tipados de configuración, servicios, voz, seguridad y control-plane según el intent.
7. Aplicar con hashes fuente coincidentes.
8. Obtener evidencia operacional fresca y ejecutar comportamiento/fallos sólo con baseline verificado.
9. Reportar cada estado por separado.

## Rules

- Nunca inferir capabilities por nombre de modelo.
- UNKNOWN no significa SUPPORTED ni UNSUPPORTED.
- No saltar planners ni tomar decisiones de compiler manualmente.
- No usar IOS, JavaScript, queries o probes arbitrarios.
- No usar buffers históricos como evidencia actual.
- Resolver toda mutación mediante la identidad vigente del DeploymentManifest.
- Layout no es identidad física.
- Un fallo requiere baseline verificado e inversa conocida.

## Evidence / readiness

Separar COMPILED, APPLIED, DIRECTLY_OBSERVED, BEHAVIORALLY_VERIFIED, FAILOVER y RECOVERY. Conservar hashes, método de evidencia, frescura, runtime fingerprint y quirks.

## Stop conditions

Detener si faltan hashes, capabilities requeridas, identidad runtime, baseline, cleanup o una dependencia obligatoria. No diagnosticar ni autofijar mientras un invariante requerido siga UNKNOWN.

## Completion

Entregar resumen compacto con planes, hashes, readiness, evidencia, limitaciones y warnings; no volcar planes o buffers completos salvo solicitud explícita.

## References

- Leer workflow.md para selección de Skills y orden end-to-end.
