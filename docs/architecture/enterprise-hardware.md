# E3: Enterprise Hardware Planner

E3 convierte un `EnterprisePlan` matemáticamente válido en una arquitectura física compacta. No crea coordenadas, archivos `.pkt`, enlaces de Packet Tracer ni configuración IOS. Su salida es una especificación de hardware que E4 podrá compilar.

## Flujo

```text
EnterpriseIntent
  -> EnterpriseDesigner (E1/E2: jerarquía, capacidad e IPAM)
  -> EnterprisePlan
  -> EnterpriseCapabilityAdapter (catálogo y puertos físicos conocidos)
  -> HardwarePlanner (E3)
  -> HardwarePlan
```

`HardwarePlanner` pertenece al dominio y recibe `HardwareCandidate`; nunca importa el catálogo de Packet Tracer. `EnterpriseCapabilityAdapter` es la frontera de infraestructura que traduce los modelos conocidos y sus puertos a candidatos.

## Evidencia y estados de capacidad

Una capacidad no observada sigue siendo `UNKNOWN`. No se infiere que un modelo tiene PoE, switching L3, routing o soporte de módulos solamente por su nombre o familia.

La evidencia se conserva por capacidad y se prioriza así: probe controlado/runtime de Packet Tracer, verificación manual, override estático, catálogo e inferencia. Una decisión de hardware puede quedar en tres estados:

- `COMPATIBLE`: existe evidencia suficiente y el modelo se selecciona.
- `NEEDS_VERIFICATION`: hay puertos físicos útiles, pero falta evidencia; el modelo queda provisional.
- `INCOMPATIBLE`: la evidencia disponible contradice un requisito o no existe ningún candidato físico.

Por ello, un `HardwarePlan` puede ser `VALID`, `PARTIALLY_RESOLVED` o
`UNRESOLVED`. Un plan parcial es el resultado correcto cuando falta evidencia,
pero no es compilable: E4 sólo acepta `VALID`. No se generan afirmaciones IOS,
Packet Tracer ni una topología física parcial a partir de esa incertidumbre.

## Capacidad y jerarquía

Para cada zona, E3 consume los resultados agregados E2 (`required_access_ports`, `required_poe_ports`, pares PC/teléfono y uplinks). Cuenta switches por separado para puertos de acceso, PoE y uplinks dedicados. Los uplinks no reducen artificialmente el número de puertos de usuario.

La política selecciona una estructura determinista:

- un switch de acceso: `flat`;
- hasta dos: `collapsed_core`;
- tres o más: `three_tier`, con distribución y core.

El nivel de resiliencia controla enlaces de acceso redundantes y, para `high`, la duplicación de padres en los enlaces entre capas. Es una especificación física: no presupone STP, EtherChannel, HSRP o protocolos de routing.

Cuando existe un router de sitio, la cadena física no presupone capas ausentes:
`flat` conecta acceso directamente con edge, `collapsed_core` conecta
distribución con edge y `three_tier` conserva core con edge. Una topología
plana no produce una falsa advertencia por carecer deliberadamente de
distribución.

## Puertos, PoE y módulos

Los puertos se normalizan en clases (`access_capable`, `uplink_capable`, `wan`, `serial`, etc.) y conservan su nombre real del catálogo. Los endpoints se guardan como rangos compactos (`PortAssignmentRange`), no como cientos de objetos host. El asignador limita explícitamente los endpoints PoE a la capacidad PoE conocida de cada switch; si esa capacidad es desconocida, el plan queda provisional.

`ModulePlanner` sólo usa módulos declarados compatibles por el catálogo y puede respetar un número de slots conocido. Si no existe una combinación compatible, devuelve ausencia de plan en vez de inventar una tarjeta o una ranura. El catálogo actual no conoce todas las ranuras de todos los modelos, por lo que esa evidencia debe llegar desde E3.5 cuando corresponda.

Para una WAN serial, `supports_modules=UNKNOWN` deja el requisito sin resolver
por evidencia insuficiente: no selecciona router, no instala módulo y no lo
declara `UNSUPPORTED`. `supports_modules=UNSUPPORTED`, en cambio, queda en
`unsupported_requirements`. La demanda se agrega por router antes de invocar
`ModulePlanner`; con evidencia del catálogo actual, dos enlaces seriales piden
dos puertos y una sola `HWIC-2T` satisface ambos sin duplicar el módulo.

## Reconciliación de roles de router para Stage 3A4

`EDGE_ROUTER` (gateway/salida LAN) y `WAN_ROUTER` (enlace entre sedes) siguen
siendo roles lógicos distintos. Cuando un sitio requiere ambos, E3 puede
realizarlos en un solo `PlannedNetworkDevice`: `role` conserva el rol primario
`EDGE_ROUTER`, `additional_roles` registra `WAN_ROUTER` y
`required_capabilities` contiene la unión usada para seleccionar el hardware.
E4 conserva el rol primario para nombres y compatibilidad con configuración, y
propaga los roles adicionales como metadata física.

La reconciliación sólo ocurre para esa pareja explícita y exige categoría
`router`. La demanda Ethernet es aditiva (un puerto LAN más los enlaces WAN
Ethernet); la demanda serial sigue agregándose por sitio y se entrega una sola
vez a `ModulePlanner`, incluyendo slots. Un candidato con categoría incorrecta,
puertos insuficientes, módulos no soportados o slots insuficientes no se
fusiona. La evidencia de módulos `UNKNOWN` conserva un resultado no resuelto
por falta de evidencia y nunca se transforma en `UNSUPPORTED`.

Un requisito WAN bloqueante mantiene `HardwarePlanStatus.UNRESOLVED` aunque el
resto del sitio ya tenga switches seleccionados. E4 rechaza tanto ese estado
como `PARTIALLY_RESOLVED` con `HARDWARE_PLAN_UNRESOLVED`. Cada clasificación se
conserva en un issue estructurado: `resolution_cause=insufficient_evidence` para
`UNKNOWN` y `resolution_cause=unsupported` para `unsupported_requirements`. Si
coexisten, se emiten ambos issues en orden determinista; una causa desconocida
nunca se promueve a no soportada. Así una topología LAN parcial no puede
ocultar la ausencia del router reconciliado ni otra evidencia incompleta.

Los dispositivos de un solo rol conservan sus IDs anteriores (`r-edge-*` o
`r-wan-*`) y no serializan roles adicionales. El reconciliado adopta el ID
estable `r-edge-*`, por lo que el gateway LAN y los enlaces WAN apuntan a la
misma identidad física sin igualar los dos roles en el dominio.

## Cobertura del catálogo y E3.5

`EnterpriseCapabilityAdapter.coverage_report()` compara modelos observados con el catálogo sin añadirlos automáticamente. Modelos como `PT8200`, `IR8340` o `IE-3400` permanecen `unclassified` hasta ser descubiertos y verificados.

E3.5 será la fase que obtenga evidencia de Packet Tracer real mediante proveedores de runtime o probes controlados. E3 ya define el contrato `CapabilityProvider`; no ejecuta Packet Tracer ni adivina APIs.

## Límites deliberados

E3 no implementa layout, `.pkt`, CLI/IOS, servicios, VLANs, routing, VoIP ni simulación. Tampoco marca P0.1 como estable: la llamada `setIpSubnetMask()` todavía requiere prueba en Packet Tracer real. Esos límites son parte del contrato, no trabajo omitido.
