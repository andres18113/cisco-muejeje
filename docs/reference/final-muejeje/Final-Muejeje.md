---
document_id: FM-REF
version: 1.0.0
issued_on: 2026-09-26
timezone: America/Guayaquil
status: REFERENCE_CONSOLIDATED_WITH_SOURCE_GAPS
canonical_filename: Final-Muejeje.md
source_completeness: partial
exact_replication_ready: false
git_publication: not_performed
source_id: S1
source_sha256: 91802fa79a8538e4b3bb38170cdaeaec5f77e3ec8b32ff4c9e2b958fc973aa41
---

# Final-Muejeje

## 1. Control de versión y autoridad documental

**Versión 1.0.0 — referencia consolidada del material recuperable.** Documento elaborado por ChatGPT en función de dirección técnica, a partir del export aportado por el usuario. No es un prompt para otro agente ni un informe de implementación.

Este archivo es la referencia documental de los nombres, modelos, interfaces, direcciones y enlaces recuperados que enumera. Los fragmentos no recuperados y las contradicciones están segregados: **no son datos autorizados para fabricar una réplica**. La versión documental está emitida; la completitud de la topología original permanece parcial. No se declara una recuperación íntegra de 333 enlaces ni una aceptación funcional de Packet Tracer.

| Campo | Valor |
| --- | --- |
| Documento | `FM-REF` / `Final-Muejeje.md` |
| Versión | `1.0.0` |
| Fecha de emisión | 2026-09-26, America/Guayaquil |
| Objeto | Referencia de topología y delimitación no-IoT para trabajo posterior |
| Destino recomendado | `docs/reference/final-muejeje/Final-Muejeje.md` |
| Autoridad de los datos | Texto S1 íntegro incorporado en el apéndice; correspondencias y cálculos declarados en este documento |
| Estado Git | No se creó commit, tag ni push. La versión es documental; el SHA del futuro commit debe obtenerse de Git, nunca inventarse. |
| Archivo local mencionado por el usuario | `C:\Users\Andres\Desktop\Final-Muejeje.md`: ruta de origen nominal; sus bytes no se leyeron directamente desde este entorno. |
| Alcance de recuperación | Se trabajó sobre `Texto pegado(4).txt`, no sobre el PKT ni sobre un export nativo accesible en Windows. |

La referencia conserva la topología original con IoT como evidencia. La exclusión no-IoT se expresa como una proyección de alcance, sin borrar el material original. El desarrollo de Final-Muejeje comienza después de cerrar Server-PT, integrar el candidato aceptado en `main` y crear la rama de implementación desde ese `main` verificado. Esta referencia no adelanta esas acciones.

### 1.1 Convenciones de lectura

| Término | Significado |
| --- | --- |
| REFERIDO | Dato completo presente en S1. No significa que se haya vuelto a observar en Packet Tracer. |
| RECUPERADO | Dato repuesto mediante una aparición completa del mismo sujeto o una correspondencia explícita documentada; no por secuencia de nombres ni cercanía gráfica. |
| CALCULADO | Resultado aritmético obtenido de valores completos de S1, como la dirección de red. |
| NO_MOSTRADO | La vista enumera la interfaz sin mostrar una dirección. No demuestra modo estático, DHCP desactivado ni dirección cero. |
| NO_RECUPERADO | El dato falta o está truncado y otra aparición no lo completa de forma suficiente. |
| CONFLICTO | Dos afirmaciones incompatibles de la fuente se conservan sin seleccionar una silenciosamente. |
| ALCANCE | Decisión documental derivada del pedido del usuario; no un estado nativo del equipo. |
| S1:Lx–Ly | Líneas físicas del texto original incorporado en el apéndice, empezando en 1; no son números de línea de este Markdown. |

Los IDs `D001…D323`, `L001…L240` y `RF001…RF016` identifican registros documentales. No son IDs nativos de Packet Tracer ni nombres para reemplazar los originales. Las mayúsculas, espacios, paréntesis y guiones de los nombres se conservan.

## 2. Fuentes y método de consolidación

| Fuente | Identidad y alcance |
| --- | --- |
| S1 — fuente primaria disponible | `Texto pegado(4).txt`; 84055 bytes; UTF-8 sin BOM; LF; 1575 líneas según `splitlines()`; SHA-256 `91802fa79a8538e4b3bb38170cdaeaec5f77e3ec8b32ff4c9e2b958fc973aa41`. |
| S1-M | `pt_project_metadata`, líneas 3–14. |
| S1-Q | `pt_query_topology`, líneas 16–326; inventario condensado. |
| S1-E | `pt_export_topology`, encabezado en L330, fichas en L332–L1316. |
| S1-L | Listado de conexiones: L1318–L1575. Incluye cables, emisiones inalámbricas y fragmentos. |
| Copia previamente retenida | `Supplied-Topology-Export.txt` dentro de `Final_Muejeje_Audit_and_Mission.zip` es byte a byte idéntica a S1; no es una segunda observación independiente. |
| Fuentes mencionadas pero no disponibles | `C:/Users/Andres/Downloads/PKT ARTEFACTAaaa.pkt` y `scratchpad\export_raw.txt`. No se asignan hashes ni hechos a archivos que no se inspeccionaron. |
| Instrucción del usuario | Preservar la topología como referencia, excluir IoT de la implementación inicial y terminar Server-PT antes de integrar y abrir la rama de Final-Muejeje. No proporciona valores de puertos o IP faltantes. |

**No se usaron Internet, la topología CP-SCALE ni parámetros por defecto de Cisco para completar datos faltantes.** La evidencia de CP-SCALE es de otro escenario y no puede aportar enlaces, direcciones o extensiones telefónicas a éste. El roadmap Server-PT describe desarrollo, no configuración de esta topología.

La consolidación agrupa sujetos por su nombre exacto, combina hechos completos de Q y E, registra las fuentes de cada dirección y conserva los extremos completos del listado de cables. Sólo se unen saltos de línea o prefijos cuando la correspondencia queda documentada. Los enlaces con un extremo incompleto o un puerto reutilizado se separan del conjunto no conflictivo. No se suponen enlaces recíprocos a partir de `[linked]`.

### 2.1 Metadatos declarados por S1

| Campo de la fuente | Valor literal | Procedencia |
| --- | --- | --- |
| saved_filename | `C:/Users/Andres/Downloads/PKT ARTEFACTAaaa.pkt` | S1:L7 |
| pt_version | `9.0.0.0810` | S1:L8 |
| devices | 323 | S1:L10, L18, L330 |
| links | 333 | S1:L11, L18, L330 |
| updated_description | false | S1:L12 |
| Descripción | Cadena vacía | S1:L9 |
| Formato real reportado | Texto plano, aunque la herramienta se describía como JSON | S1:L1 |
| Longitud y completitud afirmadas por el emisor | 58.885 caracteres y bloque «complete, 1,404 lines» | S1:L1, L328 |

El campo `pt_version` se conserva como metadato reportado: no se interpreta aquí como una lectura independiente del ejecutable. Los 323/333 son conteos declarados, no valores obtenidos nuevamente del motor. La afirmación de 1.404 líneas del emisor no sustituye los conteos del material realmente disponible.

## 3. Resumen reconciliado y alcance

| Magnitud | Resultado de esta consolidación | Interpretación |
| --- | --- | --- |
| Nombres de dispositivos | 323 | 320 tienen modelo completo; 3 sólo aparecen con nombre completo en conexiones. Coincidir con el total declarado no vuelve completas todas sus fichas. |
| Coordenadas completas | 301 de 323 | Se conservan las explícitas o recuperadas por correspondencia; no se generan las 22 restantes. |
| Pares interfaz / IP / máscara completos | 297 | Pueden existir varias interfaces con IP por dispositivo; no es un conteo de clientes direccionados. |
| Redes calculadas de esos pares | 26 | Incluye redes IoT y WAN; no acredita VLANs ni routing. |
| Registros con separador <--> | 240 | 225 completos no conflictivos, 13 incompletos y 2 en conflicto. |
| Fragmentos de conexión sin separador | 1 | Un extremo completo sin su par: FR001. |
| Emisiones inalámbricas | 16 | No identifican receptores ni asociaciones. No son 16 enlaces cliente–AP. |
| Enlaces completos entre sujetos INCLUIDO | 138 | Subconjunto documental; no es el cableado completo requerido por el alcance futuro. |

### 3.1 Inventario por modelo

| Modelo literal | Cantidad recuperada |
| --- | --- |
| `PC-PT` | 87 |
| `7960` | 72 |
| `Smoke Detector` | 45 |
| `Webcam` | 43 |
| `AccessPoint-PT` | 16 |
| `2960-24TT` | 15 |
| `RFID Reader` | 8 |
| `Server-PT` | 7 |
| `Power Distribution Device` | 6 |
| `Printer-PT` | 5 |
| `2811` | 4 |
| `Motion Detector` | 3 |
| `Temperature Sensor` | 3 |
| `Temperature Monitor` | 2 |
| `3650-24PS` | 1 |
| `Humidity Monitor` | 1 |
| `Humiture Monitor` | 1 |
| `LCD` | 1 |
| MODELO_NO_RECUPERADO | 3 |
| **Total de identidades** | **323** |

### 3.2 Proyección no-IoT

| Clasificación | Cantidad | Regla de esta versión |
| --- | --- | --- |
| INCLUIDO | 190 | 87 PC-PT, 72 teléfonos 7960, 5 Printer-PT, 16 switches, 4 routers 2811 y 6 Server-PT no identificados como IoT. Son sujetos nominales recuperados, no un denominador final de aceptación. |
| EXCLUIDO_IOT | 110 | Dispositivos con tipos de sensores/cámaras/lectores IoT de S1, `IoT-server` y las tres identidades IoT sin modelo recuperado. Permanecen en la referencia original. |
| ALCANCE_PENDIENTE | 17 | 16 AccessPoint-PT y el LCD `Proyector`. No se eliminan por compartir una subred o por cercanía a IoT; su necesidad funcional no se determina con este export. |
| BACKEND | 6 | Power Distribution Device0…5. No se convierten en endpoints funcionales ni en objetos que el producto deba crear explícitamente. |

Se retienen todos los switches y routers: un dispositivo de infraestructura no se excluye sólo porque algunos de sus puertos sirvan a IoT. No se extrapola asociación inalámbrica, función del LCD o consumo PoE desde los nombres y coordenadas.

## 4. Estructura visible de red y servicios

### 4.1 Backbone y uplinks completos

| ID | Extremo A | Extremo B | Fuente |
| --- | --- | --- | --- |
| L043 | `SW1-P2` : `GigabitEthernet0/1` | `SW-CORE` : `GigabitEthernet1/0/2` | S1:L1377 |
| L044 | `SW-CORE-S` : `GigabitEthernet0/1` | `R-Fabrica` : `FastEthernet0/0` | S1:L1378 |
| L045 | `R-Matriz` : `FastEthernet0/0` | `SW-CORE` : `GigabitEthernet1/0/24` | S1:L1379 |
| L046 | `SW1-P1` : `GigabitEthernet0/1` | `SW-CORE` : `GigabitEthernet1/0/1` | S1:L1380 |
| L047 | `SW1-P3` : `GigabitEthernet0/1` | `SW-CORE` : `GigabitEthernet1/0/3` | S1:L1381 |
| L048 | `SW-CORE-S` : `FastEthernet0/3` | `Switch17 SEGURIDAD` : `GigabitEthernet0/1` | S1:L1382 |
| L049 | `SW-CORE-S` : `FastEthernet0/1` | `Switch15 ADMIN` : `GigabitEthernet0/1` | S1:L1383 |
| L230 | `Server VOZ` : `FastEthernet0/0` | `SW-CORE` : `GigabitEthernet1/0/23` | S1:L1565 |
| L232 | `R-Matriz` : `Serial0/3/0` | `R-Fabrica` : `Serial0/3/0` | S1:L1567 |
| L233 | `R-Matriz` : `Serial0/3/1` | `R-Sucursal` : `Serial0/3/0` | S1:L1568 |
| L234 | `R-Sucursal` : `Serial0/3/1` | `R-Fabrica` : `Serial0/3/1` | S1:L1569 |
| L236 | `SW3-P3` : `GigabitEthernet0/1` | `SW-CORE` : `GigabitEthernet1/0/5` | S1:L1571 |
| L237 | `SW2-P1` : `GigabitEthernet0/2` | `SW-CORE` : `GigabitEthernet1/0/6` | S1:L1572 |
| L240 | `SW2-P2` : `GigabitEthernet0/2` | `SW-CORE` : `GigabitEthernet1/0/9` | S1:L1575 |

El triángulo serial entre `R-Matriz`, `R-Fabrica` y `R-Sucursal` está explícitamente referido. Sus pares de direcciones permiten calcular las redes `/30` de la sección 7. El tipo DCE/DTE, reloj serial, encapsulación, protocolo de routing y estado operacional no se publican en S1. Las conexiones Ethernet de esta tabla no demuestran que un puerto esté configurado como trunk.

### 4.2 Servidores y función nominal

| ID | Dispositivo | Dirección reportada | Alcance de la interpretación | Fuente |
| --- | --- | --- | --- | --- |
| D316 | `WEB-SERVER` | `172.16.100.3/28` | Servidor web por su nombre; HTTP/HTTPS habilitados, página y dominio no informados. | S1:L1265 |
| D319 | `DNS-SERVER` | `172.16.100.2/28` | Servidor DNS por su nombre; zona y registros no informados. | S1:L1270 |
| D318 | `DHCP-Server` | `172.16.100.6/28` | Servidor DHCP por su nombre; pools, exclusiones, autoridad por segmento y relay no informados. | S1:L1268 |
| D320 | `Email-Server` | `172.16.100.4/28` | Servidor de correo por su nombre; dominio, cuentas y configuración SMTP/POP3 no informados. | S1:L305,L1271–L1272 |
| D277 | `Servidor DB` | `172.16.100.8/28` | Rol nominal de base de datos; no acredita ningún motor o servicio de BD. | S1:L306,L1274 |
| D279 | `Servidor-Apps` | `172.16.100.7/28` | Rol nominal de aplicaciones; no acredita una aplicación concreta. | S1:L308,L1278 |
| D278 | `IoT-server` | `172.16.100.5/28` | Servidor nominal IoT; fuera de la implementación inicial. | S1:L307,L1276 |

**Ninguno de esos siete Server-PT tiene su par físico completo en el listado recuperado de cables.** Sus fichas muestran `FastEthernet0 [linked]`, pero eso no permite asignarles un puerto del core. Es una brecha material, no permiso para repartir `.2…8` en los puertos libres. `Server VOZ` es un **2811**, con `FastEthernet0/0 = 172.16.2.33/27`; el cable a `SW-CORE:GigabitEthernet1/0/23` sí está referido.

### 4.3 Qué no se conoce de la configuración

S1 no incluye running-config, tablas VLAN, puertos access/voice, VLAN nativa o permitida en trunks, rutas, ACL, NAT, CME, extensiones, Option 150, leases, registros DNS, páginas web, cuentas de correo ni modos estático/DHCP de los clientes. Una interfaz llamada `FastEthernet0/0.55` conserva ese nombre, pero no demuestra por sí sola `encapsulation dot1Q 55`. Una IP de interfaz L3 no demuestra que los clientes la tengan configurada como gateway. Los teléfonos con IP no acreditan registro SCCP ni llamadas.

## 5. Inventario canónico de identidades

`Q` identifica la consulta resumida; `E`, la ficha exportada; `L`, el nombre completo presente en un extremo. La procedencia de las coordenadas recuperadas puede incluir una línea Q adicional. `—` significa que no se recuperó ese atributo, nunca un valor cero.

| ID | Nombre exacto | Modelo | Alcance | Posición | Procedencia |
| --- | --- | --- | --- | --- | --- |
| D001 | `SW1-P1` | `2960-24TT` | INCLUIDO | (1042, 1153) | Q S1:L20; E S1:L332 |
| D002 | `Power Distribution Device0` | `Power Distribution Device` | BACKEND | (3892, 3885) | Q S1:L21; E S1:L358 |
| D003 | `P1AT11` | `PC-PT` | INCLUIDO | (1008, 997) | Q S1:L22; E S1:L359 |
| D004 | `P1AT9` | `PC-PT` | INCLUIDO | (1301, 1229) | Q S1:L23; E S1:L361 |
| D005 | `P1AT7` | `PC-PT` | INCLUIDO | (1242, 1297) | Q S1:L24; E S1:L363 |
| D006 | `P1AT5` | `PC-PT` | INCLUIDO | (1066, 1292) | Q S1:L25; E S1:L365 |
| D007 | `P1AT4` | `PC-PT` | INCLUIDO | (1007, 1293) | Q S1:L26; E S1:L367 |
| D008 | `P1TICs3` | `PC-PT` | INCLUIDO | (764, 1293) | Q S1:L27; E S1:L369 |
| D009 | `P1AT13` | `PC-PT` | INCLUIDO | (1069, 1002) | Q S1:L28; E S1:L371 |
| D010 | `P1CREDITO1` | `PC-PT` | INCLUIDO | (769, 995) | Q S1:L29; E S1:L373 |
| D011 | `P1AT10` | `PC-PT` | INCLUIDO | (1298, 1301) | Q S1:L30; E S1:L375 |
| D012 | `P1AT8` | `PC-PT` | INCLUIDO | (1184, 1297) | Q S1:L31; E S1:L377 |
| D013 | `P1AT6` | `PC-PT` | INCLUIDO | (1123, 1292) | Q S1:L32; E S1:L379 |
| D014 | `P1AT1` | `PC-PT` | INCLUIDO | (829, 1291) | Q S1:L33; E S1:L381 |
| D015 | `P1TICs1` | `PC-PT` | INCLUIDO | (761, 1218) | Q S1:L34; E S1:L383 |
| D016 | `P1CREDITO2` | `PC-PT` | INCLUIDO | (932, 994) | Q S1:L35; E S1:L385 |
| D017 | `P1AT12` | `PC-PT` | INCLUIDO | (1298, 1151) | Q S1:L36; E S1:L387 |
| D018 | `P1TICs4` | `PC-PT` | INCLUIDO | (765, 1070) | Q S1:L37; E S1:L389 |
| D019 | `P1AT3` | `PC-PT` | INCLUIDO | (886, 1292) | Q S1:L38; E S1:L391 |
| D020 | `PT1AT2` | `PC-PT` | INCLUIDO | (946, 1292) | Q S1:L39; E S1:L393 |
| D021 | `P1AT14` | `PC-PT` | INCLUIDO | (1299, 1082) | Q S1:L40; E S1:L395 |
| D022 | `P1GERENCIA` | `PC-PT` | INCLUIDO | (851, 992) | Q S1:L41; E S1:L397 |
| D023 | `P1TICs2` | `PC-PT` | INCLUIDO | (767, 1147) | Q S1:L42; E S1:L399 |
| D024 | `I1AT1` | `Printer-PT` | INCLUIDO | (1215, 1012) | Q S1:L43; E S1:L401 |
| D025 | `SW2-P1` | `2960-24TT` | INCLUIDO | (1379, 657) | Q S1:L44; E S1:L403 |
| D026 | `IP Phone0` | `7960` | INCLUIDO | (1613, 659) | Q S1:L45; E S1:L426 |
| D027 | `IP Phone1` | `7960` | INCLUIDO | (1620, 586) | Q S1:L46; E S1:L429 |
| D028 | `IP Phone2` | `7960` | INCLUIDO | (1621, 509) | Q S1:L47; E S1:L432 |
| D029 | `IP Phone3` | `7960` | INCLUIDO | — | Q S1:L48 |
| D030 | `IP Phone4` | `7960` | INCLUIDO | (1553, 428) | Q S1:L49; E S1:L435 |
| D031 | `IP Phone5` | `7960` | INCLUIDO | (1486, 429) | Q S1:L50; E S1:L438 |
| D032 | `IP Phone6` | `7960` | INCLUIDO | (1426, 427) | Q S1:L51; E S1:L441 |
| D033 | `IP Phone7` | `7960` | INCLUIDO | (1361, 426) | Q S1:L52; E S1:L444 |
| D034 | `IP Phone8` | `7960` | INCLUIDO | (1453, 872) | Q S1:L53; E S1:L447 |
| D035 | `IP Phone9` | `7960` | INCLUIDO | (1141, 572) | Q S1:L54; E S1:L450 |
| D036 | `IP Phone10` | `7960` | INCLUIDO | (1294, 426) | Q S1:L55; E S1:L453 |
| D037 | `IP Phone11` | `7960` | INCLUIDO | (1146, 499) | Q S1:L56; E S1:L456 |
| D038 | `IP Phone12` | `7960` | INCLUIDO | (1599, 874) | Q S1:L57; E S1:L459 |
| D039 | `IP Phone13` | `7960` | INCLUIDO | (1224, 425) | Q S1:L58; E S1:L462 |
| D040 | `IP Phone14` | `7960` | INCLUIDO | (1608, 740) | Q S1:L59; E S1:L465 |
| D041 | `IP Phone15` | `7960` | INCLUIDO | (1525, 873) | Q S1:L60; E S1:L468 |
| D042 | `IP Phone16` | `7960` | INCLUIDO | (1155, 424) | Q S1:L61; E S1:L471 |
| D043 | `I1AT2` | `Printer-PT` | INCLUIDO | (1607, 819) | Q S1:L62; E S1:L474 |
| D044 | `P1APAT1` | `AccessPoint-PT` | ALCANCE_PENDIENTE | (1108, 1011) | Q S1:L63; E S1:L476 |
| D045 | `AP1Cl` | `AccessPoint-PT` | ALCANCE_PENDIENTE | (1271, 1018) | Q S1:L64; E S1:L479 |
| D046 | `IoT5` | `Smoke Detector` | EXCLUIDO_IOT | (1341, 851) | Q S1:L65; E S1:L482 |
| D047 | `IoT6` | `Smoke Detector` | EXCLUIDO_IOT | (1119, 853) | Q S1:L66; E S1:L484 |
| D048 | `IoT7` | `Smoke Detector` | EXCLUIDO_IOT | (1231, 851) | Q S1:L67; E S1:L486 |
| D049 | `IoT8` | `Smoke Detector` | EXCLUIDO_IOT | (697, 415) | Q S1:L68; E S1:L488 |
| D050 | `IoT9` | `Smoke Detector` | EXCLUIDO_IOT | (1121, 645) | Q S1:L69; E S1:L490 |
| D051 | `IoT16` | `Webcam` | EXCLUIDO_IOT | (604, 813) | Q S1:L70; E S1:L517 |
| D052 | `IoT17` | `Webcam` | EXCLUIDO_IOT | (1019, 818) | Q S1:L71; E S1:L519 |
| D053 | `IoT18` | `Webcam` | EXCLUIDO_IOT | (951, 817) | Q S1:L72; E S1:L521 |
| D054 | `IoT19` | `Webcam` | EXCLUIDO_IOT | (676, 817) | Q S1:L73; E S1:L523 |
| D055 | `IoT20` | `Webcam` | EXCLUIDO_IOT | (746, 817) | Q S1:L74; E S1:L525 |
| D056 | `IoT21` | `Webcam` | EXCLUIDO_IOT | (816, 817) | Q S1:L75; E S1:L527 |
| D057 | `IoT22` | `Webcam` | EXCLUIDO_IOT | (886, 816) | Q S1:L76; E S1:L529 |
| D058 | `SW1-P3` | `2960-24TT` | INCLUIDO | (1462, 2290) | Q S1:L77; E S1:L531 |
| D059 | `P3CON1` | `PC-PT` | INCLUIDO | (1751, 1980) | Q S1:L78; E S1:L555 |
| D060 | `P3CON2` | `PC-PT` | INCLUIDO | (1748, 2089) | Q S1:L79; E S1:L557 |
| D061 | `P3CON3` | `PC-PT` | INCLUIDO | (1666, 1974) | Q S1:L80; E S1:L559 |
| D062 | `P3CON4` | `PC-PT` | INCLUIDO | (1578, 1968) | Q S1:L81; E S1:L561 |
| D063 | `P3CON5` | `PC-PT` | INCLUIDO | (1489, 1972) | Q S1:L82; E S1:L563 |
| D064 | `P3RRHH3` | `PC-PT` | INCLUIDO | (1189, 2190) | Q S1:L83; E S1:L565 |
| D065 | `P3RRHH1` | `PC-PT` | INCLUIDO | (1191, 1972) | Q S1:L84; E S1:L567 |
| D066 | `P3CON6` | `PC-PT` | INCLUIDO | (1404, 1970) | Q S1:L85; E S1:L569 |
| D067 | `P3GER3` | `PC-PT` | INCLUIDO | (1371, 2639) | Q S1:L86; E S1:L571 |
| D068 | `P3TICs2` | `PC-PT` | INCLUIDO | (1746, 2197) | Q S1:L87; E S1:L573 |
| D069 | `P3TICs6` | `PC-PT` | INCLUIDO | (1630, 2639) | Q S1:L88; E S1:L575 |
| D070 | `P3TICs1` | `PC-PT` | INCLUIDO | (1746, 2302) | Q S1:L89; E S1:L577 |
| D071 | `P3RRHH4` | `PC-PT` | INCLUIDO | (1182, 2522) | Q S1:L90; E S1:L579 |
| D072 | `P3RRHH6` | `PC-PT` | INCLUIDO | (1192, 2078) | Q S1:L91; E S1:L581 |
| D073 | `P3RRHH2` | `PC-PT` | INCLUIDO | (1186, 2414) | Q S1:L92; E S1:L583 |
| D074 | `P3TICs4` | `PC-PT` | INCLUIDO | (1736, 2411) | Q S1:L93; E S1:L585 |
| D075 | `P3TICs5` | `PC-PT` | INCLUIDO | (1721, 2638) | Q S1:L94; E S1:L587 |
| D076 | `P3GER1` | `PC-PT` | INCLUIDO | (1546, 2638) | Q S1:L95; E S1:L589 |
| D077 | `P3GER4` | `PC-PT` | INCLUIDO | (1279, 2640) | Q S1:L96; E S1:L591 |
| D078 | `P3TICs3` | `PC-PT` | INCLUIDO | (1732, 2520) | Q S1:L97; E S1:L593 |
| D079 | `P3RRHH5` | `PC-PT` | INCLUIDO | (1188, 2303) | Q S1:L98; E S1:L595 |
| D080 | `P3GER2` | `PC-PT` | INCLUIDO | (1459, 2639) | Q S1:L99; E S1:L597 |
| D081 | `P3GER5` | `PC-PT` | INCLUIDO | (1188, 2639) | Q S1:L100; E S1:L599 |
| D082 | `SW2-P3` | `2960-24TT` | INCLUIDO | (622, 2429) | Q S1:L101; E S1:L601 |
| D083 | `Proyector` | `LCD` | ALCANCE_PENDIENTE | (178, 1594) | Q S1:L103; E S1:L626 |
| D084 | `IP Phone17` | `7960` | INCLUIDO | (849, 2185) | Q S1:L104; E S1:L628 |
| D085 | `IP Phone18` | `7960` | INCLUIDO | (949, 2183) | Q S1:L105; E S1:L631 |
| D086 | `IP Phone19` | `7960` | INCLUIDO | (1046, 2182) | Q S1:L106; E S1:L634 |
| D087 | `IP Phone20` | `7960` | INCLUIDO | (912, 2649) | Q S1:L107; E S1:L637 |
| D088 | `IP Phone21` | `7960` | INCLUIDO | (807, 2650) | Q S1:L108; E S1:L640 |
| D089 | `IP Phone22` | `7960` | INCLUIDO | — | Q S1:L109 |
| D090 | `IP Phone23` | `7960` | INCLUIDO | — | Q S1:L110 |
| D091 | `IP Phone24` | `7960` | INCLUIDO | (706, 2652) | Q S1:L111; E S1:L642; posición: S1:L111,L642 |
| D092 | `IP Phone25` | `7960` | INCLUIDO | (500, 2656) | Q S1:L112; E S1:L644 |
| D093 | `IP Phone26` | `7960` | INCLUIDO | (600, 2655) | Q S1:L113; E S1:L647 |
| D094 | `IP Phone27` | `7960` | INCLUIDO | (1014, 2645) | Q S1:L114; E S1:L650 |
| D095 | `IP Phone28` | `7960` | INCLUIDO | (749, 2185) | Q S1:L115; E S1:L653 |
| D096 | `IP Phone29` | `7960` | INCLUIDO | (410, 2655) | Q S1:L116; E S1:L656 |
| D097 | `IP Phone30` | `7960` | INCLUIDO | (233, 2533) | Q S1:L117; E S1:L659 |
| D098 | `IP Phone31` | `7960` | INCLUIDO | (316, 2656) | Q S1:L118; E S1:L662 |
| D099 | `IP Phone32` | `7960` | INCLUIDO | (235, 2299) | Q S1:L119; E S1:L665 |
| D100 | `IP Phone33` | `7960` | INCLUIDO | (459, 2184) | Q S1:L120; E S1:L668 |
| D101 | `IP Phone34` | `7960` | INCLUIDO | (225, 2654) | Q S1:L121; E S1:L671 |
| D102 | `IP Phone35` | `7960` | INCLUIDO | (558, 2184) | Q S1:L122; E S1:L674 |
| D103 | `IP Phone36` | `7960` | INCLUIDO | (654, 2186) | Q S1:L123; E S1:L677 |
| D104 | `IP Phone37` | `7960` | INCLUIDO | (229, 2416) | Q S1:L124; E S1:L680 |
| D105 | `IP Phone38` | `7960` | INCLUIDO | (246, 2182) | Q S1:L125; E S1:L683 |
| D106 | `IP Phone39` | `7960` | INCLUIDO | (359, 2183) | Q S1:L126; E S1:L686 |
| D107 | `SW3-P3` | `2960-24TT` | INCLUIDO | (577, 1834) | Q S1:L127; E S1:L689 |
| D108 | `I3CON1` | `Printer-PT` | INCLUIDO | (982, 2063) | Q S1:L130; E S1:L714 |
| D109 | `AP3G1` | `AccessPoint-PT` | ALCANCE_PENDIENTE | (958, 1911) | Q S1:L131; E S1:L716 |
| D110 | `AP3Cl1` | `AccessPoint-PT` | ALCANCE_PENDIENTE | (1004, 2434) | Q S1:L132; E S1:L719 |
| D111 | `AP3Con1` | `AccessPoint-PT` | ALCANCE_PENDIENTE | (1266, 1983) | Q S1:L133; E S1:L722 |
| D112 | `I3RRHH1` | `Printer-PT` | INCLUIDO | (987, 1987) | Q S1:L134; E S1:L725 |
| D113 | `IoT1` | `Smoke Detector` | EXCLUIDO_IOT | (974, 1798) | Q S1:L135; E S1:L727 |
| D114 | `IoT2` | `Smoke Detector` | EXCLUIDO_IOT | (977, 1696) | Q S1:L136; E S1:L729 |
| D115 | `IoT3` | `Smoke Detector` | EXCLUIDO_IOT | (975, 1590) | Q S1:L137; E S1:L731 |
| D116 | `IoT4` | `Smoke Detector` | EXCLUIDO_IOT | (868, 1588) | Q S1:L138; E S1:L733 |
| D117 | `IoT23` | `Smoke Detector` | EXCLUIDO_IOT | (759, 1587) | Q S1:L139; E S1:L735 |
| D118 | `IoT24` | `Smoke Detector` | EXCLUIDO_IOT | (641, 1587) | Q S1:L140; E S1:L737 |
| D119 | `IoT25` | `Smoke Detector` | EXCLUIDO_IOT | (533, 1590) | Q S1:L141; E S1:L739 |
| D120 | `IoT26` | `Webcam` | EXCLUIDO_IOT | (199, 2041) | Q S1:L142; E S1:L741 |
| D121 | `IoT27` | `Webcam` | EXCLUIDO_IOT | (203, 1707) | Q S1:L143; E S1:L742; posición: S1:L143,L742–L743 |
| D122 | `IoT28` | `Webcam` | EXCLUIDO_IOT | (196, 1814) | Q S1:L144; E S1:L744 |
| D123 | `IoT29` | `Webcam` | EXCLUIDO_IOT | (197, 1922) | Q S1:L145; E S1:L746 |
| D124 | `IoT30` | `Webcam` | EXCLUIDO_IOT | (292, 2041) | Q S1:L146; E S1:L748 |
| D125 | `IoT31` | `Webcam` | EXCLUIDO_IOT | (389, 2039) | Q S1:L147; E S1:L750 |
| D126 | `IoT32` | `Webcam` | EXCLUIDO_IOT | (476, 2038) | Q S1:L148; E S1:L752 |
| D127 | `IoT35` | `Smoke Detector` | EXCLUIDO_IOT | (425, 1591) | Q S1:L149; E S1:L754 |
| D128 | `IoT36` | `Smoke Detector` | EXCLUIDO_IOT | (321, 1591) | Q S1:L150; E S1:L756 |
| D129 | `R-Sucursal` | `2811` | INCLUIDO | (2313, 2228) | Q S1:L151; E S1:L758 |
| D130 | `SW-SUC-1` | `2960-24TT` | INCLUIDO | (3030, 2221) | Q S1:L153; E S1:L768 |
| D131 | `Power Distribution Device1` | `Power Distribution Device` | BACKEND | (3895, 3885) | Q S1:L154; E S1:L788 |
| D132 | `SPCRE2` | `PC-PT` | INCLUIDO | (2782, 2000) | Q S1:L155; E S1:L789 |
| D133 | `SPCAJ1` | `PC-PT` | INCLUIDO | (2872, 1886) | Q S1:L156; E S1:L791 |
| D134 | `SPCAJ2` | `PC-PT` | INCLUIDO | (2959, 1884) | Q S1:L157; E S1:L793 |
| D135 | `SPTICs1` | `PC-PT` | INCLUIDO | (3049, 1884) | Q S1:L158; E S1:L795 |
| D136 | `SPTICs2` | `PC-PT` | INCLUIDO | (3140, 1886) | Q S1:L159; E S1:L797 |
| D137 | `SBOD` | `PC-PT` | INCLUIDO | (3232, 1886) | Q S1:L160; E S1:L799 |
| D138 | `SPCRE1` | `PC-PT` | INCLUIDO | (2785, 1884) | Q S1:L161; E S1:L801 |
| D139 | `IP Phone40` | `7960` | INCLUIDO | (3328, 1887) | Q S1:L162; E S1:L803 |
| D140 | `IP Phone41` | `7960` | INCLUIDO | (3321, 2121) | Q S1:L163; E S1:L806 |
| D141 | `IP Phone42` | `7960` | INCLUIDO | (3320, 2006) | Q S1:L164; E S1:L809 |
| D142 | `IP Phone43` | `7960` | INCLUIDO | (3302, 2585) | Q S1:L165; E S1:L812 |
| D143 | `IP Phone44` | `7960` | INCLUIDO | (3317, 2241) | Q S1:L166; E S1:L815 |
| D144 | `IP Phone45` | `7960` | INCLUIDO | (3317, 2354) | Q S1:L167; E S1:L818 |
| D145 | `IP Phone46` | `7960` | INCLUIDO | (3310, 2469) | Q S1:L168; E S1:L821 |
| D146 | `IoT0` | `Smoke Detector` | EXCLUIDO_IOT | (2752, 2351) | Q S1:L169; E S1:L824 |
| D147 | `IoT33` | `Smoke Detector` | EXCLUIDO_IOT | (2746, 2463) | Q S1:L170; E S1:L826 |
| D148 | `IoT34` | `Smoke Detector` | EXCLUIDO_IOT | (2741, 2574) | Q S1:L171; E S1:L828 |
| D149 | `IoT37` | `Smoke Detector` | EXCLUIDO_IOT | (2845, 2577) | Q S1:L172; E S1:L830 |
| D150 | `IoT38` | `Smoke Detector` | EXCLUIDO_IOT | (2948, 2575) | Q S1:L173; E S1:L832 |
| D151 | `IoT39` | `Motion Detector` | EXCLUIDO_IOT | (2751, 2093) | Q S1:L174; E S1:L834 |
| D152 | `IoT41` | `Temperature Sensor` | EXCLUIDO_IOT | (2734, 2196) | Q S1:L175; E S1:L836 |
| D153 | `SAPCaj` | `AccessPoint-PT` | ALCANCE_PENDIENTE | (3052, 2610) | Q S1:L176; E S1:L838 |
| D154 | `SAPVIS` | `AccessPoint-PT` | ALCANCE_PENDIENTE | (3164, 2611) | Q S1:L177; E S1:L841 |
| D155 | `SW-SUC-2` | `2960-24TT` | INCLUIDO | (3658, 2214) | Q S1:L178; E S1:L844 |
| D156 | `SAPTICs` | `AccessPoint-PT` | ALCANCE_PENDIENTE | (3496, 2188) | Q S1:L179; E S1:L858 |
| D157 | `IoT46` | `Webcam` | EXCLUIDO_IOT | (3622, 2379) | Q S1:L181; E S1:L869 |
| D158 | `IoT47` | `Webcam` | EXCLUIDO_IOT | (3714, 2380) | Q S1:L182; E S1:L871 |
| D159 | `IoT48` | `Webcam` | EXCLUIDO_IOT | (3701, 2039) | Q S1:L183; E S1:L873 |
| D160 | `IoT49` | `Webcam` | EXCLUIDO_IOT | (3793, 2039) | Q S1:L184; E S1:L875 |
| D161 | `IoT51` | `Webcam` | EXCLUIDO_IOT | (3797, 2159) | Q S1:L185; E S1:L877 |
| D162 | `IoT52` | `Webcam` | EXCLUIDO_IOT | (3805, 2377) | Q S1:L186; E S1:L879 |
| D163 | `IoT50` | `Webcam` | EXCLUIDO_IOT | (3800, 2273) | Q S1:L187; E S1:L881 |
| D164 | `IoT1(2)` | `Smoke Detector` | EXCLUIDO_IOT | (2244, 406) | Q S1:L188; E S1:L883 |
| D165 | `IoT0(1)` | `Webcam` | EXCLUIDO_IOT | (2097, 406) | Q S1:L189; E S1:L885 |
| D166 | `IoT1(1)` | `Smoke Detector` | EXCLUIDO_IOT | (2352, 410) | Q S1:L190; E S1:L887 |
| D167 | `P2TICs5` | `PC-PT` | INCLUIDO | (2184, 675) | Q S1:L191; E S1:L889 |
| D168 | `P3INN8` | `PC-PT` | INCLUIDO | (2910, 853) | Q S1:L192; E S1:L891 |
| D169 | `P3INN15` | `PC-PT` | INCLUIDO | (2534, 1231) | Q S1:L193; E S1:L893 |
| D170 | `P3INN14` | `PC-PT` | INCLUIDO | (2533, 1346) | Q S1:L194; E S1:L895 |
| D171 | `P3INN5` | `PC-PT` | INCLUIDO | (2808, 855) | Q S1:L195; E S1:L897 |
| D172 | `P3INN16` | `PC-PT` | INCLUIDO | (2529, 1461) | Q S1:L196; E S1:L899 |
| D173 | `P3INN18` | `PC-PT` | INCLUIDO | (2614, 1466) | Q S1:L197; E S1:L901 |
| D174 | `P3INN13` | `PC-PT` | INCLUIDO | (2628, 1013) | Q S1:L198; E S1:L903 |
| D175 | `P3INN17` | `PC-PT` | INCLUIDO | (2704, 1468) | Q S1:L199; E S1:L905 |
| D176 | `P2TICs3` | `PC-PT` | INCLUIDO | (2056, 672) | Q S1:L200; E S1:L907 |
| D177 | `IoT2(1)` | `Smoke Detector` | EXCLUIDO_IOT | (2849, 1005) | Q S1:L201; E S1:L909 |
| D178 | `Power Distribution Device2` | `Power Distribution Device` | BACKEND | (3896, 3885) | Q S1:L202; E S1:L911 |
| D179 | `P2TICs4` | `PC-PT` | INCLUIDO | (2120, 673) | Q S1:L203; E S1:L912 |
| D180 | `P3INN4` | `PC-PT` | INCLUIDO | (2378, 606) | Q S1:L204; E S1:L914 |
| D181 | `P2MON2` | `PC-PT` | INCLUIDO | (1917, 596) | Q S1:L205; E S1:L916 |
| D182 | `P2MON1` | `PC-PT` | INCLUIDO | (1918, 519) | Q S1:L206; E S1:L918 |
| D183 | `P3INN1` | `PC-PT` | INCLUIDO | (2250, 676) | Q S1:L207; E S1:L920 |
| D184 | `P3INN3` | `PC-PT` | INCLUIDO | (2370, 680) | Q S1:L208; E S1:L922 |
| D185 | `P2TICs1` | `PC-PT` | INCLUIDO | (1915, 671) | Q S1:L209; E S1:L924 |
| D186 | `P3INN7` | `PC-PT` | INCLUIDO | (3122, 845) | Q S1:L210; E S1:L926 |
| D187 | `P2TICs2` | `PC-PT` | INCLUIDO | (1989, 672) | Q S1:L211; E S1:L928 |
| D188 | `P3INN20` | `PC-PT` | INCLUIDO | (2899, 1470) | Q S1:L212; E S1:L930 |
| D189 | `P3INN2` | `PC-PT` | INCLUIDO | (2310, 681) | Q S1:L213; E S1:L932 |
| D190 | `IP Phone24(1)` | `7960` | INCLUIDO | (3169, 1016) | Q S1:L214; E S1:L934 |
| D191 | `IP Phone19(1)` | `7960` | INCLUIDO | (3074, 1012) | Q S1:L215; E S1:L937 |
| D192 | `IP Phone22(1)` | `7960` | INCLUIDO | (3050, 284) | Q S1:L216; E S1:L940 |
| D193 | `IP Phone23(1)` | `7960` | INCLUIDO | (3223, 625) | Q S1:L217; E S1:L943 |
| D194 | `IP Phone30(1)` | `7960` | INCLUIDO | (3227, 514) | Q S1:L218; E S1:L946 |
| D195 | `IP Phone20(1)` | `7960` | INCLUIDO | (3239, 289) | Q S1:L219; E S1:L949 |
| D196 | `IP Phone33(1)` | `7960` | INCLUIDO | — | Q S1:L220 |
| D197 | `IP Phone21(1)` | `7960` | INCLUIDO | — | Q S1:L221 |
| D198 | `IP Phone27(1)` | `7960` | INCLUIDO | — | Q S1:L222 |
| D199 | `IP Phone25(1)` | `7960` | INCLUIDO | (2956, 282) | Q S1:L223; E S1:L951; posición: S1:L223,L951,L953 |
| D200 | `IP Phone31(1)` | `7960` | INCLUIDO | (3223, 400) | Q S1:L224; E S1:L954 |
| D201 | `IP Phone32(1)` | `7960` | INCLUIDO | (3147, 285) | Q S1:L225; E S1:L957 |
| D202 | `IP Phone29(1)` | `7960` | INCLUIDO | (3239, 1356) | Q S1:L226; E S1:L960 |
| D203 | `IP Phone26(1)` | `7960` | INCLUIDO | (3243, 1246) | Q S1:L227; E S1:L963 |
| D204 | `IP Phone34(1)` | `7960` | INCLUIDO | (2375, 527) | Q S1:L228; E S1:L966 |
| D205 | `P3INN19` | `PC-PT` | INCLUIDO | (2799, 1470) | Q S1:L229; E S1:L969 |
| D206 | `P3INN12` | `PC-PT` | INCLUIDO | (2537, 1010) | Q S1:L230; E S1:L971 |
| D207 | `P3INN6` | `PC-PT` | INCLUIDO | — | Q S1:L231 |
| D208 | `P3INN10` | `PC-PT` | INCLUIDO | — | Q S1:L232 |
| D209 | `P3INN9` | `PC-PT` | INCLUIDO | (3230, 845) | Q S1:L233; E S1:L974 |
| D210 | `P3INN11` | `PC-PT` | INCLUIDO | (2538, 1120) | Q S1:L234; E S1:L976 |
| D211 | `IoT29(1)` | `Smoke Detector` | EXCLUIDO_IOT | (2955, 1004) | Q S1:L235; E S1:L978 |
| D212 | `IoT30(1)` | `Smoke Detector` | EXCLUIDO_IOT | (2584, 390) | Q S1:L236; E S1:L980 |
| D213 | `IoT4(1)` | `Webcam` | EXCLUIDO_IOT | (2176, 406) | Q S1:L237; E S1:L982 |
| D214 | `IoT3(1)` | `Webcam` | EXCLUIDO_IOT | (2015, 403) | Q S1:L238; E S1:L984 |
| D215 | `IoT27(1)` | `Webcam` | EXCLUIDO_IOT | (2695, 835) | Q S1:L239; E S1:L986 |
| D216 | `IoT24(1)` | `Webcam` | EXCLUIDO_IOT | (2604, 835) | Q S1:L240; E S1:L988 |
| D217 | `IoT23(1)` | `Webcam` | EXCLUIDO_IOT | (2704, 999) | Q S1:L241; E S1:L990 |
| D218 | `IoT25(1)` | `Webcam` | EXCLUIDO_IOT | (2785, 1003) | Q S1:L242; E S1:L992 |
| D219 | `IoT28(1)` | `Smoke Detector` | EXCLUIDO_IOT | (2580, 510) | Q S1:L243; E S1:L994 |
| D220 | `SW3-P2` | `2960-24TT` | INCLUIDO | (2141, 568) | Q S1:L244; E S1:L996 |
| D221 | `SW2-P2` | `2960-24TT` | INCLUIDO | (2911, 584) | Q S1:L246; E S1:L1016 |
| D222 | `SW1-P2` | `2960-24TT` | INCLUIDO | (2881, 1250) | Q S1:L247; E S1:L1040 |
| D223 | `SW-CORE` | `3650-24PS` | INCLUIDO | (2133, 1679) | Q S1:L248; E S1:L1060 |
| D224 | `R-Matriz` | `2811` | INCLUIDO | (2141, 1858) | Q S1:L249; E S1:L1079 |
| D225 | `SW-CORE-S` | `2960-24TT` | INCLUIDO | (1880, 3396) | Q S1:L251; E S1:L1092 |
| D226 | `Switch15 ADMIN` | `2960-24TT` | INCLUIDO | — | Q S1:L253 |
| D227 | `Switch16 NAVE` | `2960-24TT` | INCLUIDO | (1335, 3123) | Q S1:L254; E S1:L1117 |
| D228 | `Switch17 SEGURIDAD` | `2960-24TT` | INCLUIDO | (2326, 3367) | Q S1:L255; E S1:L1134 |
| D229 | `FOFI1` | `PC-PT` | INCLUIDO | — | Q S1:L256 |
| D230 | `FOFI2` | `PC-PT` | INCLUIDO | — | Q S1:L257 |
| D231 | `FOFI3` | `PC-PT` | INCLUIDO | — | Q S1:L258 |
| D232 | `FOFI4` | `PC-PT` | INCLUIDO | — | Q S1:L259 |
| D233 | `FOFI5` | `PC-PT` | INCLUIDO | (1245, 3428) | Q S1:L260; E S1:L1151; posición: S1:L260,L1151–L1152 |
| D234 | `FOFI6` | `PC-PT` | INCLUIDO | (1171, 3426) | Q S1:L261; E S1:L1153 |
| D235 | `FENF1` | `PC-PT` | INCLUIDO | (1167, 3582) | Q S1:L262; E S1:L1155 |
| D236 | `FBOD1` | `PC-PT` | INCLUIDO | (1169, 3511) | Q S1:L263; E S1:L1157 |
| D237 | `FSEC1` | `PC-PT` | INCLUIDO | (1166, 3658) | Q S1:L264; E S1:L1159 |
| D238 | `IP Phone47` | `7960` | INCLUIDO | (1156, 3730) | Q S1:L265; E S1:L1161 |
| D239 | `IP Phone48` | `7960` | INCLUIDO | (1160, 3814) | Q S1:L266; E S1:L1164 |
| D240 | `IP Phone49` | `7960` | INCLUIDO | (1241, 3816) | Q S1:L267; E S1:L1167 |
| D241 | `IP Phone50` | `7960` | INCLUIDO | — | Q S1:L268 |
| D242 | `IP Phone51` | `7960` | INCLUIDO | — | Q S1:L269 |
| D243 | `IP Phone52` | `7960` | INCLUIDO | — | Q S1:L270; E S1:L1170 |
| D244 | `IP Phone53` | `7960` | INCLUIDO | (1509, 3818) | Q S1:L271; E S1:L1172 |
| D245 | `IP Phone54` | `7960` | INCLUIDO | (1519, 3578) | Q S1:L272; E S1:L1175 |
| D246 | `I1OFI` | `Printer-PT` | INCLUIDO | (1525, 3508) | Q S1:L273; E S1:L1178 |
| D247 | `FAP1EMPL` | `AccessPoint-PT` | ALCANCE_PENDIENTE | (1493, 3667) | Q S1:L274; E S1:L1180 |
| D248 | `FAP2EMPLE` | `AccessPoint-PT` | ALCANCE_PENDIENTE | (1360, 2913) | Q S1:L275; E S1:L1183 |
| D249 | `FAPINV1` | `AccessPoint-PT` | ALCANCE_PENDIENTE | (1471, 2916) | Q S1:L276; E S1:L1186 |
| D250 | `IoT110` | `RFID Reader` | EXCLUIDO_IOT | (1089, 3122) | Q S1:L278; E S1:L1195; posición: S1:L278,L1195–L1196 |
| D251 | `IoT111` | `RFID Reader` | EXCLUIDO_IOT | (1094, 3240) | Q S1:L279; E S1:L1197 |
| D252 | `IoT112` | `Webcam` | EXCLUIDO_IOT | (2081, 3075) | Q S1:L280; E S1:L1199 |
| D253 | `IoT113` | `Webcam` | EXCLUIDO_IOT | (2334, 3075) | Q S1:L281; E S1:L1201 |
| D254 | `APSEC1` | `AccessPoint-PT` | ALCANCE_PENDIENTE | (2052, 3206) | Q S1:L282; E S1:L1203 |
| D255 | `IoT0(2)(5)(1)` | `Smoke Detector` | EXCLUIDO_IOT | (2579, 3194) | Q S1:L283; E S1:L1206 |
| D256 | `IoT0(2)(5)(2)` | `Smoke Detector` | EXCLUIDO_IOT | (2578, 3297) | Q S1:L284; E S1:L1208 |
| D257 | `IoT0(2)(5)(2)(1)` | `Smoke Detector` | EXCLUIDO_IOT | (2576, 3401) | Q S1:L285; E S1:L1210 |
| D258 | `IoT0(2)(5)(2)(2)` | `Smoke Detector` | EXCLUIDO_IOT | (2574, 3614) | Q S1:L286; E S1:L1212 |
| D259 | `IoT0(2)(5)(2)(3)` | `Smoke Detector` | EXCLUIDO_IOT | — | Q S1:L287 |
| D260 | `IoT0(2)(5)(2)(4)` | `Smoke Detector` | EXCLUIDO_IOT | (2353, 3615) | Q S1:L288; E S1:L1214; posición: S1:L288,L1214–L1215 |
| D261 | `IoT0(2)(5)(2)(5)` | `Smoke Detector` | EXCLUIDO_IOT | (2256, 3616) | Q S1:L289; E S1:L1216 |
| D262 | `IoT0(2)(5)(2)(6)` | `Smoke Detector` | EXCLUIDO_IOT | (2157, 3615) | Q S1:L290; E S1:L1218 |
| D263 | `IoT0(2)(5)(2)(7)` | `Smoke Detector` | EXCLUIDO_IOT | (2056, 3615) | Q S1:L291; E S1:L1220 |
| D264 | `IoT0(2)(5)(2)(8)` | `Smoke Detector` | EXCLUIDO_IOT | (2055, 3488) | Q S1:L292; E S1:L1222 |
| D265 | `IoT33(1)(1)` | `Humidity Monitor` | EXCLUIDO_IOT | (1227, 3248) | Q S1:L293; E S1:L1224 |
| D266 | `R-Fabrica` | `2811` | INCLUIDO | (2078, 2610) | Q S1:L294; E S1:L1226 |
| D267 | `IoT24(2)` | `Motion Detector` | EXCLUIDO_IOT | (2841, 275) | Q S1:L295; E S1:L1237 |
| D268 | `IoT56` | `RFID Reader` | EXCLUIDO_IOT | (2732, 278) | Q S1:L296; E S1:L1239 |
| D269 | `IoT58` | `Temperature Monitor` | EXCLUIDO_IOT | (2587, 280) | Q S1:L297; E S1:L1241 |
| D270 | `IoT61` | `RFID Reader` | EXCLUIDO_IOT | (586, 516) | Q S1:L298; E S1:L1243 |
| D271 | `IoT63` | `RFID Reader` | EXCLUIDO_IOT | (584, 614) | Q S1:L299; E S1:L1245 |
| D272 | `IoT64` | `RFID Reader` | EXCLUIDO_IOT | (583, 713) | Q S1:L300; E S1:L1247 |
| D273 | `IoT65` | `Humiture Monitor` | EXCLUIDO_IOT | (577, 412) | Q S1:L301; E S1:L1249 |
| D274 | `IoT66` | `Motion Detector` | EXCLUIDO_IOT | (555, 2041) | Q S1:L302; E S1:L1251 |
| D275 | `IoT68` | `Temperature Monitor` | EXCLUIDO_IOT | (666, 2039) | Q S1:L303; E S1:L1253 |
| D276 | `IoT69` | `RFID Reader` | EXCLUIDO_IOT | (820, 2040) | Q S1:L304; E S1:L1255 |
| D277 | `Servidor DB` | `Server-PT` | INCLUIDO | (2324, 1576) | Q S1:L306; E S1:L1273 |
| D278 | `IoT-server` | `Server-PT` | EXCLUIDO_IOT | (2325, 1671) | Q S1:L307; E S1:L1275 |
| D279 | `Servidor-Apps` | `Server-PT` | INCLUIDO | (2328, 1465) | Q S1:L308; E S1:L1277 |
| D280 | `Power Distribution Device5` | `Power Distribution Device` | BACKEND | — | Q S1:L309; E S1:L1279 |
| D281 | `IoT41(1)` | `Temperature Sensor` | EXCLUIDO_IOT | (2051, 3399) | Q S1:L310; E S1:L1280 |
| D282 | `IoT0(2)(5)(2)(9)` | `Smoke Detector` | EXCLUIDO_IOT | (2465, 3613) | Q S1:L311; E S1:L1282 |
| D283 | `AP1EMPL1` | `AccessPoint-PT` | ALCANCE_PENDIENTE | (995, 742) | Q S1:L312; E S1:L1284 |
| D284 | `APCON1` | `AccessPoint-PT` | ALCANCE_PENDIENTE | (1887, 444) | Q S1:L313; E S1:L1287 |
| D285 | `AP2EMPLE2` | `AccessPoint-PT` | ALCANCE_PENDIENTE | — | Q S1:L314 |
| D286 | `AP2EMPLE1` | `AccessPoint-PT` | ALCANCE_PENDIENTE | (2576, 738) | Q S1:L315; E S1:L1292 |
| D287 | `IoT113(1)` | `Webcam` | EXCLUIDO_IOT | (2168, 3075) | Q S1:L316; E S1:L1295 |
| D288 | `IoT113(2)` | `Webcam` | EXCLUIDO_IOT | (2253, 3076) | Q S1:L317; E S1:L1297 |
| D289 | `IoT113(3)` | `Webcam` | EXCLUIDO_IOT | (2506, 3079) | Q S1:L318; E S1:L1299 |
| D290 | `IoT113(4)` | `Webcam` | EXCLUIDO_IOT | (2590, 3081) | Q S1:L319; E S1:L1301 |
| D291 | `IoT113(5)` | `Webcam` | EXCLUIDO_IOT | (2418, 3078) | Q S1:L320; E S1:L1303 |
| D292 | `IoT113(6)` | `Webcam` | EXCLUIDO_IOT | (1119, 2890) | Q S1:L321; E S1:L1305 |
| D293 | `IoT113(7)` | `Webcam` | EXCLUIDO_IOT | (1115, 3006) | Q S1:L322; E S1:L1307 |
| D294 | `IoT113(8)` | `Webcam` | EXCLUIDO_IOT | (1213, 2891) | Q S1:L323; E S1:L1309 |
| D295 | `IoT113(9)` | `Webcam` | EXCLUIDO_IOT | (1292, 2892) | Q S1:L324; E S1:L1311 |
| D296 | `Server VOZ` | `2811` | INCLUIDO | (1970, 1640) | Q S1:L325; E S1:L1313 |
| D297 | `IoT41(2)` | `Temperature Sensor` | EXCLUIDO_IOT | (2740, 2274) | Q S1:L326; E S1:L1315 |
| D298 | `IoT10` | `Smoke Detector` | EXCLUIDO_IOT | (1121, 749) | E S1:L492 |
| D299 | `IoT11` | `Smoke Detector` | EXCLUIDO_IOT | (1008, 417) | E S1:L494 |
| D300 | `IoT12` | `Smoke Detector` | EXCLUIDO_IOT | (903, 417) | E S1:L496 |
| D301 | `IoT13` | `Smoke Detector` | EXCLUIDO_IOT | (1005, 628) | E S1:L498 |
| D302 | `IoT14` | `Smoke Detector` | EXCLUIDO_IOT | (800, 417) | E S1:L500 |
| D303 | `IoT15` | `Smoke Detector` | EXCLUIDO_IOT | (1006, 524) | E S1:L502 |
| D304 | `SW3-P1` | `2960-24TT` | INCLUIDO | (814, 634) | E S1:L504 |
| D305 | `IoT42` | `Webcam` | EXCLUIDO_IOT | (3518, 2038) | E S1:L861 |
| D306 | `IoT43` | `Webcam` | EXCLUIDO_IOT | (3611, 2037) | E S1:L863 |
| D307 | `IoT44` | `Webcam` | EXCLUIDO_IOT | (3521, 2269) | E S1:L865 |
| D308 | `IoT45` | `Webcam` | EXCLUIDO_IOT | (3527, 2377) | Q S1:L180; E S1:L867 |
| D309 | `Power Distribution Device3` | `Power Distribution Device` | BACKEND | (3897, 3885) | E S1:L1189 |
| D310 | `IoT0(2)` | `Smoke Detector` | EXCLUIDO_IOT | (1586, 2886) | E S1:L1190 |
| D311 | `IoT0(2)(1)` | `Smoke Detector` | EXCLUIDO_IOT | (1585, 3013) | E S1:L1192 |
| D312 | `IoT0(2)(2)` | `Smoke Detector` | EXCLUIDO_IOT | (1582, 3131) | E S1:L1194 |
| D313 | `IP Phone55` | `7960` | INCLUIDO | (3010, 1472) | E S1:L1257 |
| D314 | `IP Phone56` | `7960` | INCLUIDO | (3126, 1473) | E S1:L1260 |
| D315 | `IoT57` | `RFID Reader` | EXCLUIDO_IOT | (2057, 3290) | E S1:L1262 |
| D316 | `WEB-SERVER` | `Server-PT` | INCLUIDO | (2056, 1464) | E S1:L1264 |
| D317 | `Power Distribution Device4` | `Power Distribution Device` | BACKEND | (3881, 3885) | E S1:L1266 |
| D318 | `DHCP-Server` | `Server-PT` | INCLUIDO | (2150, 1465) | E S1:L1267 |
| D319 | `DNS-SERVER` | `Server-PT` | INCLUIDO | (1954, 1465) | E S1:L1269 |
| D320 | `Email-Server` | `Server-PT` | INCLUIDO | (2242, 1467) | Q S1:L305; E S1:L1271 |
| D321 | `IoT0(2)(3)` | `MODELO_NO_RECUPERADO` | EXCLUIDO_IOT | — | L S1:L1558 |
| D322 | `IoT0(2)(4)` | `MODELO_NO_RECUPERADO` | EXCLUIDO_IOT | — | L S1:L1559 |
| D323 | `IoT0(2)(5)` | `MODELO_NO_RECUPERADO` | EXCLUIDO_IOT | — | L S1:L1560 |

## 6. Interfaces recuperadas

Esta tabla enumera nombres observados, no la capacidad teórica del modelo. En las listas, `FastEthernet0/{1–3,5}` expande exactamente a `FastEthernet0/1`, `/2`, `/3` y `/5`: **no incluye `/4`**. No es una instrucción IOS. Las subinterfaces se escriben sin abreviación.

«Reportadas enlazadas» reúne una marca `[linked]` atribuible o un extremo completo de S1-L; no acredita el otro extremo, tipo de cable, estado UP/FWD ni validez de un enlace que la sección 8 mantiene en conflicto. La ausencia de la marca significa que no se informó, no que esté desconectada. El literal `R-Matriz:FastEthernet0/24` se separa por posible corrupción.

| Dispositivo | Interfaces nombradas | Reportadas enlazadas | Fuente de enumeración/marcas |
| --- | --- | --- | --- |
| D001 | `Vlan1`; `FastEthernet0/{1–24}`; `GigabitEthernet0/{1–2}` | `FastEthernet0/{1–24}`; `GigabitEthernet0/1` | S1:L20,L333–L357,L1380,L1385–L1402 |
| D002 | No recuperadas | NO_INFORMADO | — |
| D003 | `Bluetooth`; `FastEthernet0` | `FastEthernet0` | S1:L22,L360,L1396 |
| D004 | `FastEthernet0` | `FastEthernet0` | S1:L23,L362,L1395 |
| D005 | `Bluetooth`; `FastEthernet0` | `FastEthernet0` | S1:L24,L364,L1393 |
| D006 | `Bluetooth`; `FastEthernet0` | `FastEthernet0` | S1:L25,L366,L1390 |
| D007 | `FastEthernet0` | `FastEthernet0` | S1:L26,L368,L1389 |
| D008 | `Bluetooth`; `FastEthernet0` | `FastEthernet0` | S1:L27,L370 |
| D009 | `Bluetooth`; `FastEthernet0` | `FastEthernet0` | S1:L28,L372,L1398 |
| D010 | `FastEthernet0` | `FastEthernet0` | S1:L29,L374 |
| D011 | `Bluetooth`; `FastEthernet0` | `FastEthernet0` | S1:L30,L376,L1394 |
| D012 | `Bluetooth`; `FastEthernet0` | `FastEthernet0` | S1:L31,L378,L1392 |
| D013 | `FastEthernet0` | `FastEthernet0` | S1:L32,L380,L1391 |
| D014 | `Bluetooth`; `FastEthernet0` | `FastEthernet0` | S1:L33,L382,L1387 |
| D015 | `Bluetooth`; `FastEthernet0` | `FastEthernet0` | S1:L34,L384 |
| D016 | `FastEthernet0` | `FastEthernet0` | S1:L35,L386 |
| D017 | `Bluetooth`; `FastEthernet0` | `FastEthernet0` | S1:L36,L388,L1397 |
| D018 | `Bluetooth`; `FastEthernet0` | `FastEthernet0` | S1:L37,L390 |
| D019 | `FastEthernet0` | `FastEthernet0` | S1:L38,L392,L1388 |
| D020 | `Bluetooth`; `FastEthernet0` | `FastEthernet0` | S1:L39,L394,L1386 |
| D021 | `Bluetooth`; `FastEthernet0` | `FastEthernet0` | S1:L40,L396,L1399 |
| D022 | `FastEthernet0` | `FastEthernet0` | S1:L41,L398 |
| D023 | `Bluetooth`; `FastEthernet0` | `FastEthernet0` | S1:L42,L400 |
| D024 | `FastEthernet0` | `FastEthernet0` | S1:L43,L402,L1400 |
| D025 | `Vlan1`; `FastEthernet0/{1–24}`; `GigabitEthernet0/{1–2}` | `FastEthernet0/{1,4–18,20–24}`; `GigabitEthernet0/2` | S1:L44,L404–L425,L1403–L1418,L1572 |
| D026 | `PC`; `Switch`; `Vlan1`; `Vlan50` | `Switch` | S1:L45,L427–L428 |
| D027 | `PC`; `Switch`; `Vlan1`; `Vlan50` | `Switch` | S1:L46,L430–L431 |
| D028 | `PC`; `Switch`; `Vlan1`; `Vlan50` | `Switch` | S1:L47,L433 |
| D029 | `PC`; `Switch`; `Vlan1`; `Vlan50` | `Switch` | S1:L48,L434,L1404 |
| D030 | `PC`; `Switch`; `Vlan1`; `Vlan50` | `Switch` | S1:L49,L436–L437,L1405 |
| D031 | `PC`; `Switch`; `Vlan1`; `Vlan50` | `Switch` | S1:L50,L439–L440,L1406 |
| D032 | `PC`; `Switch`; `Vlan1`; `Vlan50` | `Switch` | S1:L51,L442–L443,L1407 |
| D033 | `PC`; `Switch`; `Vlan1`; `Vlan50` | `Switch` | S1:L52,L445–L446,L1408 |
| D034 | `PC`; `Switch`; `Vlan1`; `Vlan50` | `Switch` | S1:L53,L448–L449 |
| D035 | `PC`; `Switch`; `Vlan1`; `Vlan50` | `Switch` | S1:L54,L451–L452 |
| D036 | `PC`; `Switch`; `Vlan1`; `Vlan50` | `Switch` | S1:L55,L454–L455,L1409 |
| D037 | `PC`; `Switch`; `Vlan1`; `Vlan50` | `Switch` | S1:L56,L457–L458,L1412 |
| D038 | `PC`; `Switch`; `Vlan1`; `Vlan50` | `Switch` | S1:L57,L460–L461 |
| D039 | `PC`; `Switch`; `Vlan1`; `Vlan50` | `Switch` | S1:L58,L463–L464,L1410 |
| D040 | `PC`; `Switch`; `Vlan1`; `Vlan55` | `Switch` | S1:L59,L466–L467,L1413 |
| D041 | `PC`; `Switch`; `Vlan1`; `Vlan50` | `Switch` | S1:L60,L469–L470 |
| D042 | `PC`; `Switch`; `Vlan1`; `Vlan50` | `Switch` | S1:L61,L472–L473,L1411 |
| D043 | `FastEthernet0` | `FastEthernet0` | S1:L62,L475 |
| D044 | `Port 0`; `Port 1` | `Port 0`; `Port 1` | S1:L63,L477–L478,L1401 |
| D045 | `Port 0`; `Port 1` | `Port 0`; `Port 1` | S1:L64,L480–L481,L1402 |
| D046 | `FastEthernet0` | `FastEthernet0` | S1:L65,L483,L1418 |
| D047 | `Bluetooth`; `FastEthernet0` | `FastEthernet0` | S1:L66,L485,L1417 |
| D048 | `Bluetooth`; `FastEthernet0` | `FastEthernet0` | S1:L67,L487,L1416 |
| D049 | `Bluetooth`; `FastEthernet0` | `FastEthernet0` | S1:L68,L489 |
| D050 | `FastEthernet0` | `FastEthernet0` | S1:L69,L491,L1414 |
| D051 | `Bluetooth`; `FastEthernet0` | `FastEthernet0` | S1:L70,L518 |
| D052 | `Bluetooth`; `FastEthernet0` | `FastEthernet0` | S1:L71,L520 |
| D053 | `Bluetooth`; `FastEthernet0` | `FastEthernet0` | S1:L72,L522 |
| D054 | `Bluetooth`; `FastEthernet0` | `FastEthernet0` | S1:L73,L524 |
| D055 | `Bluetooth`; `FastEthernet0` | `FastEthernet0` | S1:L74,L526 |
| D056 | `Bluetooth`; `FastEthernet0` | `FastEthernet0` | S1:L75,L528 |
| D057 | `Bluetooth`; `FastEthernet0` | `FastEthernet0` | S1:L76,L530 |
| D058 | `Vlan1`; `FastEthernet0/{1–24}`; `GigabitEthernet0/{1–2}` | `FastEthernet0/{1–2,4–24}`; `GigabitEthernet0/1` | S1:L77,L532–L554,L1381,L1419–L1440 |
| D059 | `Bluetooth`; `FastEthernet0` | `FastEthernet0` | S1:L78,L556 |
| D060 | `Bluetooth`; `FastEthernet0` | `FastEthernet0` | S1:L79,L558,L1422 |
| D061 | `Bluetooth`; `FastEthernet0` | `FastEthernet0` | S1:L80,L560 |
| D062 | `Bluetooth`; `FastEthernet0` | `FastEthernet0` | S1:L81,L562,L1420 |
| D063 | `Bluetooth`; `FastEthernet0` | `FastEthernet0` | S1:L82,L564,L1419 |
| D064 | `FastEthernet0` | `FastEthernet0` | S1:L83,L566,L1431 |
| D065 | `FastEthernet0` | `FastEthernet0` | S1:L84,L568,L1430 |
| D066 | `Bluetooth`; `FastEthernet0` | `FastEthernet0` | S1:L85,L570 |
| D067 | `Bluetooth`; `FastEthernet0` | `FastEthernet0` | S1:L86,L572,L1437 |
| D068 | `Bluetooth`; `FastEthernet0` | `FastEthernet0` | S1:L87,L574,L1423 |
| D069 | `FastEthernet0` | `FastEthernet0` | S1:L88,L576,L1424 |
| D070 | `Bluetooth`; `FastEthernet0` | `FastEthernet0` | S1:L89,L578,L1428 |
| D071 | `Bluetooth`; `FastEthernet0` | `FastEthernet0` | S1:L90,L580,L1432 |
| D072 | `Bluetooth`; `FastEthernet0` | `FastEthernet0` | S1:L91,L582,L1434 |
| D073 | `Bluetooth`; `FastEthernet0` | `FastEthernet0` | S1:L92,L584,L1429 |
| D074 | `Bluetooth`; `FastEthernet0` | `FastEthernet0` | S1:L93,L586,L1425 |
| D075 | `Bluetooth`; `FastEthernet0` | `FastEthernet0` | S1:L94,L588,L1426 |
| D076 | `Bluetooth`; `FastEthernet0` | `FastEthernet0` | S1:L95,L590,L1439 |
| D077 | `Bluetooth`; `FastEthernet0` | `FastEthernet0` | S1:L96,L592,L1436 |
| D078 | `Bluetooth`; `FastEthernet0` | `FastEthernet0` | S1:L97,L594,L1427 |
| D079 | `Bluetooth`; `FastEthernet0` | `FastEthernet0` | S1:L98,L596,L1433 |
| D080 | `Bluetooth`; `FastEthernet0` | `FastEthernet0` | S1:L99,L598,L1438 |
| D081 | `Bluetooth`; `FastEthernet0` | `FastEthernet0` | S1:L100,L600,L1435 |
| D082 | `Vlan1`; `FastEthernet0/{1–24}`; `GigabitEthernet0/{1–2}` | `FastEthernet0/{1–7,9–24}`; `GigabitEthernet0/2` | S1:L101–L102,L602–L625,L1497,L1499–L1511,L1570 |
| D083 | `FastEthernet0` | `FastEthernet0` | S1:L103,L627,L1350 |
| D084 | `PC`; `Switch`; `Vlan1`; `Vlan55` | `Switch` | S1:L104,L629–L630,L1511 |
| D085 | `PC`; `Switch`; `Vlan1`; `Vlan55` | `Switch` | S1:L105,L632–L633,L1510 |
| D086 | `PC`; `Switch`; `Vlan1`; `Vlan55` | `Switch` | S1:L106,L635–L636,L1509 |
| D087 | `PC`; `Switch`; `Vlan1`; `Vlan55` | `Switch` | S1:L107,L638–L639,L1505 |
| D088 | `PC`; `Switch`; `Vlan1`; `Vlan55` | `Switch` | S1:L108,L641,L1504 |
| D089 | `PC`; `Switch`; `Vlan1`; `Vlan55` | `Switch` | S1:L109,L1507 |
| D090 | `PC`; `Switch`; `Vlan1`; `Vlan55` | `Switch` | S1:L110,L1508 |
| D091 | `PC`; `Switch`; `Vlan1`; `Vlan55` | `Switch` | S1:L111,L643,L1503 |
| D092 | `PC`; `Switch`; `Vlan1`; `Vlan55` | `Switch` | S1:L112,L645–L646,L1501 |
| D093 | `PC`; `Switch`; `Vlan1`; `Vlan55` | `Switch` | S1:L113,L648–L649,L1502 |
| D094 | `PC`; `Switch`; `Vlan1`; `Vlan55` | `Switch` | S1:L114,L651–L652,L1506 |
| D095 | `PC`; `Switch`; `Vlan1`; `Vlan55` | `Switch` | S1:L115,L654–L655,L1497 |
| D096 | `PC`; `Switch`; `Vlan1`; `Vlan55` | `Switch` | S1:L116,L657–L658,L1500 |
| D097 | `PC`; `Switch`; `Vlan1`; `Vlan55` | `Switch` | S1:L117,L660–L661 |
| D098 | `PC`; `Switch`; `Vlan1`; `Vlan55` | `Switch` | S1:L118,L663–L664,L1499 |
| D099 | `PC`; `Switch`; `Vlan1`; `Vlan55` | `Switch` | S1:L119,L666–L667 |
| D100 | `PC`; `Switch`; `Vlan1`; `Vlan55` | `Switch` | S1:L120,L669–L670 |
| D101 | `PC`; `Switch`; `Vlan1`; `Vlan55` | `Switch` | S1:L121,L672–L673,L1498 |
| D102 | `PC`; `Switch`; `Vlan1`; `Vlan55` | `Switch` | S1:L122,L675–L676 |
| D103 | `PC`; `Switch`; `Vlan1`; `Vlan55` | `Switch` | S1:L123,L678–L679 |
| D104 | `PC`; `Switch`; `Vlan1`; `Vlan55` | `Switch` | S1:L124,L681–L682 |
| D105 | `PC`; `Switch`; `Vlan1`; `Vlan55` | `Switch` | S1:L125,L684–L685 |
| D106 | `PC`; `Switch`; `Vlan1`; `Vlan55` | `Switch` | S1:L126,L687–L688 |
| D107 | `Vlan1`; `FastEthernet0/{1–23}`; `GigabitEthernet0/{1–2}` | `FastEthernet0/{1–23}`; `GigabitEthernet0/1` | S1:L127–L129,L690–L713,L1341–L1357,L1374–L1376,L1571 |
| D108 | `FastEthernet0` | `FastEthernet0` | S1:L130,L715 |
| D109 | `Port 0`; `Port 1` | `Port 0`; `Port 1` | S1:L131,L717–L718 |
| D110 | `Port 0`; `Port 1` | `Port 0`; `Port 1` | S1:L132,L720–L721 |
| D111 | `Port 0`; `Port 1` | `Port 0`; `Port 1` | S1:L133,L723–L724,L1440 |
| D112 | `FastEthernet0` | `FastEthernet0` | S1:L134,L726,L1340 |
| D113 | `Bluetooth`; `FastEthernet0` | `FastEthernet0` | S1:L135,L728,L1341 |
| D114 | `Bluetooth`; `FastEthernet0` | `FastEthernet0` | S1:L136,L730,L1342 |
| D115 | `Bluetooth`; `FastEthernet0` | `FastEthernet0` | S1:L137,L732,L1343 |
| D116 | `Bluetooth`; `FastEthernet0` | `FastEthernet0` | S1:L138,L734,L1344 |
| D117 | `Bluetooth`; `FastEthernet0` | `FastEthernet0` | S1:L139,L736,L1345 |
| D118 | `Bluetooth`; `FastEthernet0` | `FastEthernet0` | S1:L140,L738,L1346 |
| D119 | `Bluetooth`; `FastEthernet0` | `FastEthernet0` | S1:L141,L740,L1347 |
| D120 | `Bluetooth`; `FastEthernet0` | `FastEthernet0` | S1:L142,L1354 |
| D121 | `Bluetooth`; `FastEthernet0` | `FastEthernet0` | S1:L143,L743,L1357 |
| D122 | `Bluetooth`; `FastEthernet0` | `FastEthernet0` | S1:L144,L745,L1356 |
| D123 | `Bluetooth`; `FastEthernet0` | `FastEthernet0` | S1:L145,L747,L1355 |
| D124 | `Bluetooth`; `FastEthernet0` | `FastEthernet0` | S1:L146,L749,L1353 |
| D125 | `Bluetooth`; `FastEthernet0` | `FastEthernet0` | S1:L147,L751,L1352 |
| D126 | `Bluetooth`; `FastEthernet0` | `FastEthernet0` | S1:L148,L753,L1351 |
| D127 | `Bluetooth`; `FastEthernet0` | `FastEthernet0` | S1:L149,L755,L1348 |
| D128 | `Bluetooth`; `FastEthernet0` | `FastEthernet0` | S1:L150,L757,L1349 |
| D129 | `FastEthernet0/0.12`; `FastEthernet0/0.22`; `FastEthernet0/0.52`; `FastEthernet0/0.62`; `FastEthernet0/0.72`; `FastEthernet0/0.199`; `Serial0/3/0`; `Serial0/3/1`; `Vlan1`; `FastEthernet0/{0–1}`; `FastEthernet1/0` | `Serial0/3/0`; `Serial0/3/1`; `FastEthernet0/0` | S1:L151–L152,L759–L767,L1568–L1569 |
| D130 | `Vlan1`; `FastEthernet0/{1–24}`; `GigabitEthernet0/{1–2}` | `FastEthernet0/{1–10,12,14–24}`; `GigabitEthernet0/{1–2}` | S1:L153,L769–L787,L1358–L1366,L1512–L1516,L1564,L1566 |
| D131 | No recuperadas | NO_INFORMADO | — |
| D132 | `FastEthernet0` | `FastEthernet0` | S1:L155,L790,L1358 |
| D133 | `Bluetooth`; `FastEthernet0` | `FastEthernet0` | S1:L156,L792,L1359 |
| D134 | `Bluetooth`; `FastEthernet0` | `FastEthernet0` | S1:L157,L794,L1360 |
| D135 | `Bluetooth`; `FastEthernet0` | `FastEthernet0` | S1:L158,L796,L1361 |
| D136 | `Bluetooth`; `FastEthernet0` | `FastEthernet0` | S1:L159,L798,L1362 |
| D137 | `Bluetooth`; `FastEthernet0` | `FastEthernet0` | S1:L160,L800,L1363 |
| D138 | `Bluetooth`; `FastEthernet0` | `FastEthernet0` | S1:L161,L802,L1512 |
| D139 | `PC`; `Switch`; `Vlan1`; `Vlan52` | `Switch` | S1:L162,L804–L805,L1364 |
| D140 | `PC`; `Switch`; `Vlan1`; `Vlan52` | `Switch` | S1:L163,L807–L808,L1365 |
| D141 | `PC`; `Switch`; `Vlan1`; `Vlan52` | `Switch` | S1:L164,L810–L811,L1366 |
| D142 | `PC`; `Switch`; `Vlan1`; `Vlan52` | `Switch` | S1:L165,L813–L814 |
| D143 | `PC`; `Switch`; `Vlan1`; `Vlan52` | `Switch` | S1:L166,L816–L817 |
| D144 | `PC`; `Switch`; `Vlan1`; `Vlan52` | `Switch` | S1:L167,L819–L820 |
| D145 | `PC`; `Switch`; `Vlan1`; `Vlan52` | `Switch` | S1:L168,L822–L823,L1513 |
| D146 | `Bluetooth`; `FastEthernet0` | `FastEthernet0` | S1:L169,L825 |
| D147 | `Bluetooth`; `FastEthernet0` | `FastEthernet0` | S1:L170,L827 |
| D148 | `Bluetooth`; `FastEthernet0` | `FastEthernet0` | S1:L171,L829 |
| D149 | `Bluetooth`; `FastEthernet0` | `FastEthernet0` | S1:L172,L831 |
| D150 | `FastEthernet0` | `FastEthernet0` | S1:L173,L833 |
| D151 | `Bluetooth`; `FastEthernet0` | `FastEthernet0` | S1:L174,L835,L1564 |
| D152 | `FastEthernet0` | `FastEthernet0` | S1:L175,L837 |
| D153 | `Port 0`; `Port 1` | `Port 0`; `Port 1` | S1:L176,L839–L840,L1516 |
| D154 | `Port 0`; `Port 1` | `Port 0`; `Port 1` | S1:L177,L842–L843,L1514 |
| D155 | `Vlan1`; `FastEthernet0/{1–24}`; `GigabitEthernet0/{1–2}` | `FastEthernet0/{2–12,24}`; `GigabitEthernet0/2` | S1:L178,L845–L857,L1368–L1369,L1517 |
| D156 | `Port 0`; `Port 1` | `Port 0`; `Port 1` | S1:L179,L859–L860,L1517 |
| D157 | `Bluetooth`; `FastEthernet0` | `FastEthernet0` | S1:L181,L870,L1367 |
| D158 | `Bluetooth`; `FastEthernet0` | `FastEthernet0` | S1:L182,L872 |
| D159 | `Bluetooth`; `FastEthernet0` | `FastEthernet0` | S1:L183,L874 |
| D160 | `Bluetooth`; `FastEthernet0` | `FastEthernet0` | S1:L184,L876 |
| D161 | `Bluetooth`; `FastEthernet0` | `FastEthernet0` | S1:L185,L878 |
| D162 | `Bluetooth`; `FastEthernet0` | `FastEthernet0` | S1:L186,L880 |
| D163 | `Bluetooth`; `FastEthernet0` | `FastEthernet0` | S1:L187,L882 |
| D164 | `Bluetooth`; `FastEthernet0` | `FastEthernet0` | S1:L188,L884,L1456 |
| D165 | `Bluetooth`; `FastEthernet0` | `FastEthernet0` | S1:L189,L886,L1458 |
| D166 | `Bluetooth`; `FastEthernet0` | `FastEthernet0` | S1:L190,L888,L1455 |
| D167 | `Bluetooth`; `FastEthernet0` | `FastEthernet0` | S1:L191,L890,L1448 |
| D168 | `Bluetooth`; `FastEthernet0` | `FastEthernet0` | S1:L192,L892,L1461 |
| D169 | `Bluetooth`; `FastEthernet0` | `FastEthernet0` | S1:L193,L894,L1472 |
| D170 | `Bluetooth`; `FastEthernet0` | `FastEthernet0` | S1:L194,L896 |
| D171 | `Bluetooth`; `FastEthernet0` | `FastEthernet0` | S1:L195,L898,L1460 |
| D172 | `Bluetooth`; `FastEthernet0` | `FastEthernet0` | S1:L196,L900 |
| D173 | `Bluetooth`; `FastEthernet0` | `FastEthernet0` | S1:L197,L902,L1474 |
| D174 | `Bluetooth`; `FastEthernet0` | `FastEthernet0` | S1:L198,L904 |
| D175 | `Bluetooth`; `FastEthernet0` | `FastEthernet0` | S1:L199,L906,L1473 |
| D176 | `Bluetooth`; `FastEthernet0` | `FastEthernet0` | S1:L200,L908,L1446 |
| D177 | `Bluetooth`; `FastEthernet0` | `FastEthernet0` | S1:L201,L910,L1487 |
| D178 | No recuperadas | NO_INFORMADO | — |
| D179 | `FastEthernet0` | `FastEthernet0` | S1:L203,L913,L1447 |
| D180 | `Bluetooth`; `FastEthernet0` | `FastEthernet0` | S1:L204,L915,L1452 |
| D181 | `Bluetooth`; `FastEthernet0` | `FastEthernet0` | S1:L205,L917,L1443 |
| D182 | `FastEthernet0` | `FastEthernet0` | S1:L206,L919,L1442 |
| D183 | `Bluetooth`; `FastEthernet0` | `FastEthernet0` | S1:L207,L921,L1449 |
| D184 | `Bluetooth`; `FastEthernet0` | `FastEthernet0` | S1:L208,L923,L1451 |
| D185 | `Bluetooth`; `FastEthernet0` | `FastEthernet0` | S1:L209,L925,L1444 |
| D186 | `Bluetooth`; `FastEthernet0` | `FastEthernet0` | S1:L210,L927,L1463 |
| D187 | `Bluetooth`; `FastEthernet0` | `FastEthernet0` | S1:L211,L929,L1445 |
| D188 | `FastEthernet0` | `FastEthernet0` | S1:L212,L931,L1476 |
| D189 | `Bluetooth`; `FastEthernet0` | `FastEthernet0` | S1:L213,L933,L1450 |
| D190 | `PC`; `Switch`; `Vlan1`; `Vlan50` | `Switch` | S1:L214,L935–L936,L1482 |
| D191 | `PC`; `Switch`; `Vlan1`; `Vlan50` | `Switch` | S1:L215,L938–L939,L1481 |
| D192 | `PC`; `Switch`; `Vlan1`; `Vlan55` | `Switch` | S1:L216,L941–L942,L1495 |
| D193 | `PC`; `Switch`; `Vlan1`; `Vlan55` | `Switch` | S1:L217,L944–L945,L1492 |
| D194 | `PC`; `Switch`; `Vlan1`; `Vlan50` | `Switch` | S1:L218,L947–L948,L1490 |
| D195 | `PC`; `Switch`; `Vlan1`; `Vlan55` | `Switch` | S1:L219,L950,L1493 |
| D196 | `PC`; `Switch`; `Vlan1`; `Vlan50` | `Switch` | S1:L220,L1485 |
| D197 | `PC`; `Switch`; `Vlan1`; `Vlan50` | `Switch` | S1:L221,L1478 |
| D198 | `PC`; `Switch`; `Vlan1`; `Vlan50` | `Switch` | S1:L222,L1483 |
| D199 | `PC`; `Switch`; `Vlan1`; `Vlan55` | `Switch` | S1:L223,L952–L953,L1496 |
| D200 | `PC`; `Switch`; `Vlan1`; `Vlan55` | `Switch` | S1:L224,L955–L956,L1494 |
| D201 | `PC`; `Switch`; `Vlan1`; `Vlan50` | `Switch` | S1:L225,L958–L959,L1491 |
| D202 | `PC`; `Switch`; `Vlan1`; `Vlan50` | `Switch` | S1:L226,L961–L962,L1484 |
| D203 | `PC`; `Switch`; `Vlan1`; `Vlan50` | `Switch` | S1:L227,L964–L965,L1479 |
| D204 | `PC`; `Switch`; `Vlan1`; `Vlan50` | `Switch` | S1:L228,L967–L968,L1453 |
| D205 | `Bluetooth`; `FastEthernet0` | `FastEthernet0` | S1:L229,L970,L1475 |
| D206 | `Bluetooth`; `FastEthernet0` | NO_INFORMADO | S1:L230 |
| D207 | `Bluetooth`; `FastEthernet0` | `FastEthernet0` | S1:L231,L1462 |
| D208 | `Bluetooth`; `FastEthernet0` | `FastEthernet0` | S1:L232,L1465 |
| D209 | `Bluetooth`; `FastEthernet0` | `FastEthernet0` | S1:L233,L975,L1464 |
| D210 | `Bluetooth`; `FastEthernet0` | `FastEthernet0` | S1:L234,L977 |
| D211 | `Bluetooth`; `FastEthernet0` | `FastEthernet0` | S1:L235,L979,L1486 |
| D212 | `Bluetooth`; `FastEthernet0` | `FastEthernet0` | S1:L236,L981,L1466 |
| D213 | `Bluetooth`; `FastEthernet0` | `FastEthernet0` | S1:L237,L983,L1457 |
| D214 | `Bluetooth`; `FastEthernet0` | `FastEthernet0` | S1:L238,L985,L1459 |
| D215 | `Bluetooth`; `FastEthernet0` | `FastEthernet0` | S1:L239,L987 |
| D216 | `Bluetooth`; `FastEthernet0` | `FastEthernet0` | S1:L240,L989 |
| D217 | `Bluetooth`; `FastEthernet0` | `FastEthernet0` | S1:L241,L991,L1489 |
| D218 | `Bluetooth`; `FastEthernet0` | `FastEthernet0` | S1:L242,L993,L1488 |
| D219 | `FastEthernet0` | `FastEthernet0` | S1:L243,L995,L1470 |
| D220 | `Vlan1`; `FastEthernet0/{1–21,24}`; `GigabitEthernet0/{1–2}` | `FastEthernet0/{1–17,24}`; `GigabitEthernet0/1` | S1:L244–L245,L997–L1015,L1442–L1459,L1573–L1574 |
| D221 | `Vlan1`; `FastEthernet0/{1–24}`; `GigabitEthernet0/{1–2}` | `FastEthernet0/{1–20,23–24}`; `GigabitEthernet0/2` | S1:L246,L1017–L1039,L1460–L1470,L1490–L1496,L1575 |
| D222 | `Vlan1`; `FastEthernet0/{1–24}`; `GigabitEthernet0/{1–2}` | `FastEthernet0/{1–23}`; `GigabitEthernet0/1` | S1:L247,L1041–L1059,L1377,L1471–L1489 |
| D223 | `Vlan1`; `Vlan55`; `Vlan99`; `GigabitEthernet1/0/{1–24}`; `GigabitEthernet1/1/{1–4}` | `GigabitEthernet1/0/{1–11,14–16,23–24}` | S1:L248,L1061–L1078,L1377,L1379–L1381,L1565,L1571–L1575 |
| D224 | `FastEthernet0/0.10`; `FastEthernet0/0.20`; `FastEthernet0/0.30`; `FastEthernet0/0.40`; `FastEthernet0/0.50`; `FastEthernet0/0.60`; `FastEthernet0/0.70`; `FastEthernet0/0.99`; `FastEthernet0/0.100`; `Serial0/3/0`; `Serial0/3/1`; `Vlan1`; `FastEthernet0/{0–1}`; `FastEthernet1/0` | `Serial0/3/0`; `Serial0/3/1`; `FastEthernet0/0` | S1:L249–L250,L1080–L1091,L1379,L1567–L1568 |
| D225 | `Vlan1`; `FastEthernet0/{1–12,16–24}`; `GigabitEthernet0/{1–2}` | `FastEthernet0/{1–3}`; `GigabitEthernet0/1` | S1:L251–L252,L1093–L1096,L1378,L1382–L1384 |
| D226 | `Vlan1`; `FastEthernet0/{1–24}`; `GigabitEthernet0/{1–2}` | `FastEthernet0/{1,3–9,12–18,24}`; `GigabitEthernet0/1` | S1:L253,L1383,L1532–L1539,L1541–L1548 |
| D227 | `Vlan1`; `FastEthernet0/{1–24}`; `GigabitEthernet0/{1–2}` | `FastEthernet0/{1–13,23–24}`; `GigabitEthernet0/1` | S1:L254,L1118–L1133,L1549–L1556,L1558–L1563 |
| D228 | `Vlan1`; `FastEthernet0/{1–24}`; `GigabitEthernet0/{1–2}` | `FastEthernet0/{1–20}`; `GigabitEthernet0/1` | S1:L255,L1135–L1150,L1382,L1518–L1520,L1522–L1531 |
| D229 | `Bluetooth`; `FastEthernet0` | `FastEthernet0` | S1:L256,L1532 |
| D230 | `FastEthernet0` | NO_INFORMADO | S1:L257 |
| D231 | `Bluetooth`; `FastEthernet0` | `FastEthernet0` | S1:L258,L1533 |
| D232 | `Bluetooth`; `FastEthernet0` | `FastEthernet0` | S1:L259,L1534 |
| D233 | `Bluetooth`; `FastEthernet0` | `FastEthernet0` | S1:L260,L1152,L1535 |
| D234 | `Bluetooth`; `FastEthernet0` | `FastEthernet0` | S1:L261,L1154,L1536 |
| D235 | `Bluetooth`; `FastEthernet0` | `FastEthernet0` | S1:L262,L1156,L1538 |
| D236 | `FastEthernet0` | `FastEthernet0` | S1:L263,L1158,L1537 |
| D237 | `Bluetooth`; `FastEthernet0` | `FastEthernet0` | S1:L264,L1160,L1539 |
| D238 | `PC`; `Switch`; `Vlan1`; `Vlan51` | `Switch` | S1:L265,L1162–L1163 |
| D239 | `PC`; `Switch`; `Vlan1`; `Vlan51` | `Switch` | S1:L266,L1165–L1166 |
| D240 | `PC`; `Switch`; `Vlan1`; `Vlan51` | `Switch` | S1:L267,L1168–L1169,L1541 |
| D241 | `PC`; `Switch`; `Vlan1`; `Vlan51` | `Switch` | S1:L268,L1542 |
| D242 | `PC`; `Switch`; `Vlan1`; `Vlan51` | `Switch` | S1:L269,L1543 |
| D243 | `PC`; `Switch`; `Vlan1`; `Vlan51` | `Switch` | S1:L270,L1171,L1544 |
| D244 | `PC`; `Switch`; `Vlan1`; `Vlan51` | `Switch` | S1:L271,L1173–L1174,L1545 |
| D245 | `PC`; `Switch`; `Vlan1`; `Vlan51` | `Switch` | S1:L272,L1176–L1177,L1546 |
| D246 | `FastEthernet0` | `FastEthernet0` | S1:L273,L1179,L1547 |
| D247 | `Port 0`; `Port 1` | `Port 0`; `Port 1` | S1:L274,L1181–L1182,L1548 |
| D248 | `Port 0`; `Port 1` | `Port 0`; `Port 1` | S1:L275,L1184–L1185,L1549 |
| D249 | `Port 0`; `Port 1` | `Port 0`; `Port 1` | S1:L276,L1187–L1188,L1550 |
| D250 | `FastEthernet0` | `FastEthernet0` | S1:L278,L1196,L1563 |
| D251 | `FastEthernet0` | `FastEthernet0` | S1:L279,L1198,L1562 |
| D252 | `Bluetooth`; `FastEthernet0` | `FastEthernet0` | S1:L280,L1200,L1518 |
| D253 | `Bluetooth`; `FastEthernet0` | `FastEthernet0` | S1:L281,L1202,L1520 |
| D254 | `Port 0`; `Port 1` | `Port 0`; `Port 1` | S1:L282,L1204–L1205 |
| D255 | `Bluetooth`; `FastEthernet0` | `FastEthernet0` | S1:L283,L1207 |
| D256 | `Bluetooth`; `FastEthernet0` | `FastEthernet0` | S1:L284,L1209 |
| D257 | `Bluetooth`; `FastEthernet0` | `FastEthernet0` | S1:L285,L1211 |
| D258 | `Bluetooth`; `FastEthernet0` | `FastEthernet0` | S1:L286,L1213,L1523 |
| D259 | `Bluetooth`; `FastEthernet0` | `FastEthernet0` | S1:L287,L1524 |
| D260 | `Bluetooth`; `FastEthernet0` | `FastEthernet0` | S1:L288,L1215,L1525 |
| D261 | `Bluetooth`; `FastEthernet0` | `FastEthernet0` | S1:L289,L1217,L1526 |
| D262 | `Bluetooth`; `FastEthernet0` | `FastEthernet0` | S1:L290,L1219,L1527 |
| D263 | `Bluetooth`; `FastEthernet0` | `FastEthernet0` | S1:L291,L1221,L1528 |
| D264 | `Bluetooth`; `FastEthernet0` | `FastEthernet0` | S1:L292,L1223,L1529 |
| D265 | `Bluetooth`; `FastEthernet0` | `FastEthernet0` | S1:L293,L1225,L1561 |
| D266 | `FastEthernet0/0.11`; `FastEthernet0/0.12`; `FastEthernet0/0.21`; `FastEthernet0/0.22`; `FastEthernet0/0.51`; `FastEthernet0/0.52`; `FastEthernet0/0.61`; `FastEthernet0/0.71`; `FastEthernet0/0.72`; `FastEthernet0/0.81`; `FastEthernet0/0.299`; `Serial0/3/0`; `Serial0/3/1`; `Vlan1`; `FastEthernet0/{0–1}`; `FastEthernet1/0` | `Serial0/3/0`; `Serial0/3/1`; `FastEthernet0/0` | S1:L294,L1227–L1236,L1378,L1567,L1569 |
| D267 | `Bluetooth`; `FastEthernet0` | `FastEthernet0` | S1:L295,L1238,L1469 |
| D268 | `FastEthernet0` | `FastEthernet0` | S1:L296,L1240,L1468 |
| D269 | `Bluetooth`; `FastEthernet0` | `FastEthernet0` | S1:L297,L1242,L1467 |
| D270 | `FastEthernet0` | `FastEthernet0` | S1:L298,L1244,L1371 |
| D271 | `FastEthernet0` | `FastEthernet0` | S1:L299,L1246,L1372 |
| D272 | `FastEthernet0` | `FastEthernet0` | S1:L300,L1248,L1373 |
| D273 | `Bluetooth`; `FastEthernet0` | `FastEthernet0` | S1:L301,L1250,L1370 |
| D274 | `Bluetooth`; `FastEthernet0` | `FastEthernet0` | S1:L302,L1252,L1374 |
| D275 | `Bluetooth`; `FastEthernet0` | `FastEthernet0` | S1:L303,L1254,L1375 |
| D276 | `FastEthernet0` | `FastEthernet0` | S1:L304,L1256,L1376 |
| D277 | `FastEthernet0` | `FastEthernet0` | S1:L306,L1274 |
| D278 | `FastEthernet0` | `FastEthernet0` | S1:L307,L1276 |
| D279 | `FastEthernet0` | `FastEthernet0` | S1:L308,L1278 |
| D280 | No recuperadas | NO_INFORMADO | — |
| D281 | `FastEthernet0` | `FastEthernet0` | S1:L310,L1281,L1530 |
| D282 | `Bluetooth`; `FastEthernet0` | `FastEthernet0` | S1:L311,L1283 |
| D283 | `Port 0`; `Port 1` | `Port 0`; `Port 1` | S1:L312,L1285–L1286,L1441 |
| D284 | `Port 0`; `Port 1` | `Port 0`; `Port 1` | S1:L313,L1288,L1454 |
| D285 | `Port 0`; `Port 1` | NO_INFORMADO | S1:L314 |
| D286 | `Port 0`; `Port 1` | `Port 0`; `Port 1` | S1:L315,L1293–L1294 |
| D287 | `Bluetooth`; `FastEthernet0` | `FastEthernet0` | S1:L316,L1296,L1519 |
| D288 | `Bluetooth`; `FastEthernet0` | `FastEthernet0` | S1:L317,L1298 |
| D289 | `Bluetooth`; `FastEthernet0` | `FastEthernet0` | S1:L318,L1300 |
| D290 | `Bluetooth`; `FastEthernet0` | `FastEthernet0` | S1:L319,L1302,L1521 |
| D291 | `Bluetooth`; `FastEthernet0` | `FastEthernet0` | S1:L320,L1304 |
| D292 | `Bluetooth`; `FastEthernet0` | `FastEthernet0` | S1:L321,L1306,L1553 |
| D293 | `Bluetooth`; `FastEthernet0` | `FastEthernet0` | S1:L322,L1308,L1552 |
| D294 | `Bluetooth`; `FastEthernet0` | `FastEthernet0` | S1:L323,L1310,L1551 |
| D295 | `Bluetooth`; `FastEthernet0` | `FastEthernet0` | S1:L324,L1312,L1554 |
| D296 | `FastEthernet0/0.55`; `Vlan1`; `FastEthernet0/{0–1}` | `FastEthernet0/0` | S1:L325,L1314,L1565 |
| D297 | `FastEthernet0` | `FastEthernet0` | S1:L326,L1316,L1566 |
| D298 | `FastEthernet0` | `FastEthernet0` | S1:L493,L1415 |
| D299 | `FastEthernet0` | `FastEthernet0` | S1:L495,L1336 |
| D300 | `FastEthernet0` | `FastEthernet0` | S1:L497,L1338 |
| D301 | `FastEthernet0` | `FastEthernet0` | S1:L499,L1337 |
| D302 | `FastEthernet0` | `FastEthernet0` | S1:L501,L1339 |
| D303 | `FastEthernet0` | `FastEthernet0` | S1:L503,L1335 |
| D304 | `FastEthernet0/{1–5,7–10,14–17,24}`; `GigabitEthernet0/1` | `FastEthernet0/{1–5,7–10,14–17,24}`; `GigabitEthernet0/1` | S1:L505–L509,L511–L516,L1335–L1339,L1370–L1373,L1441 |
| D305 | `FastEthernet0` | `FastEthernet0` | S1:L862 |
| D306 | `FastEthernet0` | `FastEthernet0` | S1:L864 |
| D307 | `FastEthernet0` | `FastEthernet0` | S1:L866,L1369 |
| D308 | `Bluetooth`; `FastEthernet0` | `FastEthernet0` | S1:L180,L867–L868,L1368 |
| D309 | No recuperadas | NO_INFORMADO | — |
| D310 | `FastEthernet0` | `FastEthernet0` | S1:L1191,L1555 |
| D311 | `FastEthernet0` | `FastEthernet0` | S1:L1193,L1556 |
| D312 | `FastEthernet0` | `FastEthernet0` | S1:L1557 |
| D313 | `Switch`; `Vlan50` | `Switch` | S1:L1258–L1259,L1477 |
| D314 | `Switch` | `Switch` | S1:L1480 |
| D315 | `FastEthernet0` | `FastEthernet0` | S1:L1263,L1531 |
| D316 | `FastEthernet0` | `FastEthernet0` | S1:L1265 |
| D317 | No recuperadas | NO_INFORMADO | — |
| D318 | `FastEthernet0` | `FastEthernet0` | S1:L1268 |
| D319 | `FastEthernet0` | `FastEthernet0` | S1:L1270 |
| D320 | `FastEthernet0` | `FastEthernet0` | S1:L305,L1271–L1272 |
| D321 | `FastEthernet0` | `FastEthernet0` | S1:L1558 |
| D322 | `FastEthernet0` | `FastEthernet0` | S1:L1559 |
| D323 | `FastEthernet0` | `FastEthernet0` | S1:L1560 |

## 7. Direccionamiento recuperado

### 7.1 Pares completos

La tabla conserva IP y máscara literales completas; CIDR/red es un cálculo determinista, no una nueva configuración. No se completan direcciones para interfaces sin lectura. Cuando Q está truncada y E publica el par completo, se usa el par de E con su línea, sin extrapolar a vecinos.

| Dispositivo | Interfaz | IPv4 | Máscara | Red calculada | Fuente |
| --- | --- | --- | --- | --- | --- |
| D003 | `FastEthernet0` | `172.16.1.73` | `255.255.255.224` | `172.16.1.64/27` | S1:L22,L360 |
| D004 | `FastEthernet0` | `172.16.1.81` | `255.255.255.224` | `172.16.1.64/27` | S1:L362 |
| D005 | `FastEthernet0` | `172.16.1.85` | `255.255.255.224` | `172.16.1.64/27` | S1:L24,L364 |
| D006 | `FastEthernet0` | `172.16.1.88` | `255.255.255.224` | `172.16.1.64/27` | S1:L25,L366 |
| D007 | `FastEthernet0` | `172.16.1.77` | `255.255.255.224` | `172.16.1.64/27` | S1:L368 |
| D008 | `FastEthernet0` | `172.16.1.147` | `255.255.255.192` | `172.16.1.128/26` | S1:L27,L370 |
| D009 | `FastEthernet0` | `172.16.1.83` | `255.255.255.224` | `172.16.1.64/27` | S1:L28,L372 |
| D010 | `FastEthernet0` | `172.16.1.175` | `255.255.255.192` | `172.16.1.128/26` | S1:L374 |
| D012 | `FastEthernet0` | `172.16.1.89` | `255.255.255.224` | `172.16.1.64/27` | S1:L31,L378 |
| D013 | `FastEthernet0` | `172.16.1.74` | `255.255.255.224` | `172.16.1.64/27` | S1:L380 |
| D014 | `FastEthernet0` | `172.16.1.90` | `255.255.255.224` | `172.16.1.64/27` | S1:L33,L382 |
| D015 | `FastEthernet0` | `172.16.1.171` | `255.255.255.192` | `172.16.1.128/26` | S1:L34,L384 |
| D016 | `FastEthernet0` | `172.16.1.152` | `255.255.255.192` | `172.16.1.128/26` | S1:L386 |
| D017 | `FastEthernet0` | `172.16.1.86` | `255.255.255.224` | `172.16.1.64/27` | S1:L36,L388 |
| D018 | `FastEthernet0` | `172.16.1.159` | `255.255.255.192` | `172.16.1.128/26` | S1:L37,L390 |
| D019 | `FastEthernet0` | `172.16.1.87` | `255.255.255.224` | `172.16.1.64/27` | S1:L392 |
| D020 | `FastEthernet0` | `172.16.1.80` | `255.255.255.224` | `172.16.1.64/27` | S1:L39,L394 |
| D021 | `FastEthernet0` | `172.16.1.84` | `255.255.255.224` | `172.16.1.64/27` | S1:L40,L396 |
| D022 | `FastEthernet0` | `172.16.1.8` | `255.255.255.240` | `172.16.1.0/28` | S1:L398 |
| D023 | `FastEthernet0` | `172.16.1.179` | `255.255.255.192` | `172.16.1.128/26` | S1:L42,L400 |
| D024 | `FastEthernet0` | `172.16.1.93` | `255.255.255.224` | `172.16.1.64/27` | S1:L402 |
| D026 | `Vlan50` | `172.16.2.9` | `255.255.255.224` | `172.16.2.0/27` | S1:L428 |
| D027 | `Vlan50` | `172.16.2.12` | `255.255.255.224` | `172.16.2.0/27` | S1:L46,L431 |
| D028 | `Vlan50` | `172.16.2.28` | `255.255.255.224` | `172.16.2.0/27` | S1:L47 |
| D029 | `Vlan50` | `172.16.2.8` | `255.255.255.224` | `172.16.2.0/27` | S1:L48,L434 |
| D030 | `Vlan50` | `172.16.2.19` | `255.255.255.224` | `172.16.2.0/27` | S1:L49,L437 |
| D031 | `Vlan50` | `172.16.2.17` | `255.255.255.224` | `172.16.2.0/27` | S1:L50,L440 |
| D032 | `Vlan50` | `172.16.2.7` | `255.255.255.224` | `172.16.2.0/27` | S1:L51,L443 |
| D033 | `Vlan50` | `172.16.2.3` | `255.255.255.224` | `172.16.2.0/27` | S1:L52,L446 |
| D034 | `Vlan50` | `172.16.2.13` | `255.255.255.224` | `172.16.2.0/27` | S1:L53,L449 |
| D035 | `Vlan50` | `172.16.2.11` | `255.255.255.224` | `172.16.2.0/27` | S1:L54,L452 |
| D036 | `Vlan50` | `172.16.2.5` | `255.255.255.224` | `172.16.2.0/27` | S1:L55,L455 |
| D037 | `Vlan50` | `172.16.2.15` | `255.255.255.224` | `172.16.2.0/27` | S1:L56,L458 |
| D038 | `Vlan50` | `172.16.2.14` | `255.255.255.224` | `172.16.2.0/27` | S1:L57,L461 |
| D039 | `Vlan50` | `172.16.2.30` | `255.255.255.224` | `172.16.2.0/27` | S1:L58,L464 |
| D040 | `Vlan55` | `172.16.2.38` | `255.255.255.224` | `172.16.2.32/27` | S1:L59,L467 |
| D041 | `Vlan50` | `172.16.2.25` | `255.255.255.224` | `172.16.2.0/27` | S1:L60,L470 |
| D042 | `Vlan50` | `172.16.2.16` | `255.255.255.224` | `172.16.2.0/27` | S1:L61,L473 |
| D043 | `FastEthernet0` | `172.16.1.94` | `255.255.255.224` | `172.16.1.64/27` | S1:L62,L475 |
| D046 | `FastEthernet0` | `172.16.3.16` | `255.255.255.128` | `172.16.3.0/25` | S1:L483 |
| D047 | `FastEthernet0` | `172.16.3.15` | `255.255.255.128` | `172.16.3.0/25` | S1:L66,L485 |
| D048 | `FastEthernet0` | `172.16.3.14` | `255.255.255.128` | `172.16.3.0/25` | S1:L67,L487 |
| D049 | `FastEthernet0` | `172.16.3.7` | `255.255.255.128` | `172.16.3.0/25` | S1:L68,L489 |
| D050 | `FastEthernet0` | `172.16.3.12` | `255.255.255.128` | `172.16.3.0/25` | S1:L491 |
| D051 | `FastEthernet0` | `172.16.3.46` | `255.255.255.128` | `172.16.3.0/25` | S1:L70,L518 |
| D052 | `FastEthernet0` | `172.16.3.45` | `255.255.255.128` | `172.16.3.0/25` | S1:L71,L520 |
| D053 | `FastEthernet0` | `172.16.3.44` | `255.255.255.128` | `172.16.3.0/25` | S1:L72,L522 |
| D054 | `FastEthernet0` | `172.16.3.43` | `255.255.255.128` | `172.16.3.0/25` | S1:L73,L524 |
| D055 | `FastEthernet0` | `172.16.3.42` | `255.255.255.128` | `172.16.3.0/25` | S1:L74,L526 |
| D056 | `FastEthernet0` | `172.16.3.41` | `255.255.255.128` | `172.16.3.0/25` | S1:L75,L528 |
| D057 | `FastEthernet0` | `172.16.3.40` | `255.255.255.128` | `172.16.3.0/25` | S1:L76,L530 |
| D059 | `FastEthernet0` | `172.16.1.51` | `255.255.255.224` | `172.16.1.32/27` | S1:L78,L556 |
| D060 | `FastEthernet0` | `172.16.1.47` | `255.255.255.224` | `172.16.1.32/27` | S1:L79,L558 |
| D061 | `FastEthernet0` | `172.16.1.43` | `255.255.255.224` | `172.16.1.32/27` | S1:L80,L560 |
| D062 | `FastEthernet0` | `172.16.1.52` | `255.255.255.224` | `172.16.1.32/27` | S1:L81,L562 |
| D063 | `FastEthernet0` | `172.16.1.49` | `255.255.255.224` | `172.16.1.32/27` | S1:L82,L564 |
| D064 | `FastEthernet0` | `172.16.1.44` | `255.255.255.224` | `172.16.1.32/27` | S1:L566 |
| D065 | `FastEthernet0` | `172.16.1.42` | `255.255.255.224` | `172.16.1.32/27` | S1:L568 |
| D066 | `FastEthernet0` | `172.16.1.48` | `255.255.255.224` | `172.16.1.32/27` | S1:L85,L570 |
| D067 | `FastEthernet0` | `172.16.1.7` | `255.255.255.240` | `172.16.1.0/28` | S1:L86,L572 |
| D068 | `FastEthernet0` | `172.16.1.165` | `255.255.255.192` | `172.16.1.128/26` | S1:L87,L574 |
| D069 | `FastEthernet0` | `172.16.1.141` | `255.255.255.192` | `172.16.1.128/26` | S1:L576 |
| D070 | `FastEthernet0` | `172.16.1.174` | `255.255.255.192` | `172.16.1.128/26` | S1:L89,L578 |
| D072 | `FastEthernet0` | `172.16.1.46` | `255.255.255.224` | `172.16.1.32/27` | S1:L91,L582 |
| D073 | `FastEthernet0` | `172.16.1.50` | `255.255.255.224` | `172.16.1.32/27` | S1:L92,L584 |
| D074 | `FastEthernet0` | `172.16.1.150` | `255.255.255.192` | `172.16.1.128/26` | S1:L93,L586 |
| D075 | `FastEthernet0` | `172.16.1.164` | `255.255.255.192` | `172.16.1.128/26` | S1:L94,L588 |
| D076 | `FastEthernet0` | `172.16.1.5` | `255.255.255.240` | `172.16.1.0/28` | S1:L95,L590 |
| D077 | `FastEthernet0` | `172.16.1.3` | `255.255.255.240` | `172.16.1.0/28` | S1:L96,L592 |
| D078 | `FastEthernet0` | `172.16.1.173` | `255.255.255.192` | `172.16.1.128/26` | S1:L97,L594 |
| D080 | `FastEthernet0` | `172.16.1.6` | `255.255.255.240` | `172.16.1.0/28` | S1:L99,L598 |
| D081 | `FastEthernet0` | `172.16.1.9` | `255.255.255.240` | `172.16.1.0/28` | S1:L100,L600 |
| D083 | `FastEthernet0` | `172.16.3.35` | `255.255.255.128` | `172.16.3.0/25` | S1:L103,L627 |
| D084 | `Vlan55` | `172.16.2.36` | `255.255.255.224` | `172.16.2.32/27` | S1:L104,L630 |
| D085 | `Vlan55` | `172.16.2.57` | `255.255.255.224` | `172.16.2.32/27` | S1:L633 |
| D086 | `Vlan55` | `172.16.2.54` | `255.255.255.224` | `172.16.2.32/27` | S1:L106,L636 |
| D087 | `Vlan55` | `172.16.2.45` | `255.255.255.224` | `172.16.2.32/27` | S1:L107,L639 |
| D088 | `Vlan55` | `172.16.2.58` | `255.255.255.224` | `172.16.2.32/27` | S1:L108 |
| D089 | `Vlan55` | `172.16.2.59` | `255.255.255.224` | `172.16.2.32/27` | S1:L109 |
| D090 | `Vlan55` | `172.16.2.61` | `255.255.255.224` | `172.16.2.32/27` | S1:L110 |
| D092 | `Vlan55` | `172.16.2.49` | `255.255.255.224` | `172.16.2.32/27` | S1:L112,L646 |
| D093 | `Vlan55` | `172.16.2.41` | `255.255.255.224` | `172.16.2.32/27` | S1:L113,L649 |
| D094 | `Vlan55` | `172.16.2.47` | `255.255.255.224` | `172.16.2.32/27` | S1:L114,L652 |
| D095 | `Vlan55` | `172.16.2.50` | `255.255.255.224` | `172.16.2.32/27` | S1:L115,L655 |
| D096 | `Vlan55` | `172.16.2.53` | `255.255.255.224` | `172.16.2.32/27` | S1:L658 |
| D097 | `Vlan55` | `172.16.2.44` | `255.255.255.224` | `172.16.2.32/27` | S1:L117,L661 |
| D098 | `Vlan55` | `172.16.2.62` | `255.255.255.224` | `172.16.2.32/27` | S1:L118,L664 |
| D099 | `Vlan55` | `172.16.2.60` | `255.255.255.224` | `172.16.2.32/27` | S1:L667 |
| D100 | `Vlan55` | `172.16.2.35` | `255.255.255.224` | `172.16.2.32/27` | S1:L120,L670 |
| D101 | `Vlan55` | `172.16.2.48` | `255.255.255.224` | `172.16.2.32/27` | S1:L121,L673 |
| D102 | `Vlan55` | `172.16.2.51` | `255.255.255.224` | `172.16.2.32/27` | S1:L122,L676 |
| D103 | `Vlan55` | `172.16.2.42` | `255.255.255.224` | `172.16.2.32/27` | S1:L123,L679 |
| D104 | `Vlan55` | `172.16.2.56` | `255.255.255.224` | `172.16.2.32/27` | S1:L124,L682 |
| D105 | `Vlan55` | `172.16.2.39` | `255.255.255.224` | `172.16.2.32/27` | S1:L685 |
| D106 | `Vlan55` | `172.16.2.46` | `255.255.255.224` | `172.16.2.32/27` | S1:L126,L688 |
| D108 | `FastEthernet0` | `172.16.1.61` | `255.255.255.224` | `172.16.1.32/27` | S1:L130,L715 |
| D112 | `FastEthernet0` | `172.16.1.62` | `255.255.255.224` | `172.16.1.32/27` | S1:L726 |
| D113 | `FastEthernet0` | `172.16.3.26` | `255.255.255.128` | `172.16.3.0/25` | S1:L135,L728 |
| D114 | `FastEthernet0` | `172.16.3.27` | `255.255.255.128` | `172.16.3.0/25` | S1:L136,L730 |
| D115 | `FastEthernet0` | `172.16.3.28` | `255.255.255.128` | `172.16.3.0/25` | S1:L137,L732 |
| D116 | `FastEthernet0` | `172.16.3.29` | `255.255.255.128` | `172.16.3.0/25` | S1:L138,L734 |
| D117 | `FastEthernet0` | `172.16.3.30` | `255.255.255.128` | `172.16.3.0/25` | S1:L139,L736 |
| D118 | `FastEthernet0` | `172.16.3.31` | `255.255.255.128` | `172.16.3.0/25` | S1:L140,L738 |
| D119 | `FastEthernet0` | `172.16.3.32` | `255.255.255.128` | `172.16.3.0/25` | S1:L141,L740 |
| D120 | `FastEthernet0` | `172.16.3.57` | `255.255.255.128` | `172.16.3.0/25` | S1:L142 |
| D121 | `FastEthernet0` | `172.16.3.54` | `255.255.255.128` | `172.16.3.0/25` | S1:L143,L743 |
| D122 | `FastEthernet0` | `172.16.3.55` | `255.255.255.128` | `172.16.3.0/25` | S1:L144,L745 |
| D123 | `FastEthernet0` | `172.16.3.56` | `255.255.255.128` | `172.16.3.0/25` | S1:L145,L747 |
| D124 | `FastEthernet0` | `172.16.3.58` | `255.255.255.128` | `172.16.3.0/25` | S1:L146,L749 |
| D125 | `FastEthernet0` | `172.16.3.59` | `255.255.255.128` | `172.16.3.0/25` | S1:L147,L751 |
| D126 | `FastEthernet0` | `172.16.3.60` | `255.255.255.128` | `172.16.3.0/25` | S1:L148,L753 |
| D127 | `FastEthernet0` | `172.16.3.33` | `255.255.255.128` | `172.16.3.0/25` | S1:L149,L755 |
| D128 | `FastEthernet0` | `172.16.3.34` | `255.255.255.128` | `172.16.3.0/25` | S1:L150,L757 |
| D129 | `Serial0/3/0` | `172.16.250.6` | `255.255.255.252` | `172.16.250.4/30` | S1:L151–L152,L760 |
| D129 | `Serial0/3/1` | `172.16.250.10` | `255.255.255.252` | `172.16.250.8/30` | S1:L151–L152,L761 |
| D129 | `FastEthernet0/0.12` | `172.16.20.1` | `255.255.255.240` | `172.16.20.0/28` | S1:L151–L152,L762 |
| D129 | `FastEthernet0/0.52` | `172.16.20.33` | `255.255.255.240` | `172.16.20.32/28` | S1:L151–L152,L764 |
| D129 | `FastEthernet0/0.62` | `172.16.20.65` | `255.255.255.224` | `172.16.20.64/27` | S1:L151–L152,L765 |
| D129 | `FastEthernet0/0.72` | `172.16.20.97` | `255.255.255.240` | `172.16.20.96/28` | S1:L151–L152,L766 |
| D129 | `FastEthernet0/0.199` | `172.16.20.113` | `255.255.255.240` | `172.16.20.112/28` | S1:L151–L152,L767 |
| D129 | `FastEthernet0/0.22` | `172.16.20.17` | `255.255.255.240` | `172.16.20.16/28` | S1:L763 |
| D132 | `FastEthernet0` | `172.16.20.2` | `255.255.255.240` | `172.16.20.0/28` | S1:L790 |
| D133 | `FastEthernet0` | `172.16.20.6` | `255.255.255.240` | `172.16.20.0/28` | S1:L156,L792 |
| D134 | `FastEthernet0` | `172.16.20.8` | `255.255.255.240` | `172.16.20.0/28` | S1:L157,L794 |
| D135 | `FastEthernet0` | `172.16.20.18` | `255.255.255.240` | `172.16.20.16/28` | S1:L158,L796 |
| D136 | `FastEthernet0` | `172.16.20.20` | `255.255.255.240` | `172.16.20.16/28` | S1:L159,L798 |
| D137 | `FastEthernet0` | `172.16.20.19` | `255.255.255.240` | `172.16.20.16/28` | S1:L160,L800 |
| D138 | `FastEthernet0` | `172.16.20.7` | `255.255.255.240` | `172.16.20.0/28` | S1:L161,L802 |
| D139 | `Vlan52` | `172.16.20.35` | `255.255.255.240` | `172.16.20.32/28` | S1:L162,L805 |
| D140 | `Vlan52` | `172.16.20.38` | `255.255.255.240` | `172.16.20.32/28` | S1:L163,L808 |
| D141 | `Vlan52` | `172.16.20.39` | `255.255.255.240` | `172.16.20.32/28` | S1:L164,L811 |
| D142 | `Vlan52` | `172.16.20.34` | `255.255.255.240` | `172.16.20.32/28` | S1:L165,L814 |
| D143 | `Vlan52` | `172.16.20.37` | `255.255.255.240` | `172.16.20.32/28` | S1:L166,L817 |
| D144 | `Vlan52` | `172.16.20.36` | `255.255.255.240` | `172.16.20.32/28` | S1:L167,L820 |
| D145 | `Vlan52` | `172.16.20.40` | `255.255.255.240` | `172.16.20.32/28` | S1:L168,L823 |
| D146 | `FastEthernet0` | `172.16.20.68` | `255.255.255.224` | `172.16.20.64/27` | S1:L169,L825 |
| D147 | `FastEthernet0` | `172.16.20.69` | `255.255.255.224` | `172.16.20.64/27` | S1:L170,L827 |
| D148 | `FastEthernet0` | `172.16.20.70` | `255.255.255.224` | `172.16.20.64/27` | S1:L171,L829 |
| D149 | `FastEthernet0` | `172.16.20.71` | `255.255.255.224` | `172.16.20.64/27` | S1:L172,L831 |
| D150 | `FastEthernet0` | `172.16.20.72` | `255.255.255.224` | `172.16.20.64/27` | S1:L833 |
| D151 | `FastEthernet0` | `172.16.20.66` | `255.255.255.224` | `172.16.20.64/27` | S1:L174,L835 |
| D152 | `FastEthernet0` | `172.16.20.67` | `255.255.255.224` | `172.16.20.64/27` | S1:L175,L837 |
| D157 | `FastEthernet0` | `172.16.20.81` | `255.255.255.224` | `172.16.20.64/27` | S1:L181,L870 |
| D158 | `FastEthernet0` | `172.16.20.80` | `255.255.255.224` | `172.16.20.64/27` | S1:L182,L872 |
| D159 | `FastEthernet0` | `172.16.20.75` | `255.255.255.224` | `172.16.20.64/27` | S1:L183,L874 |
| D160 | `FastEthernet0` | `172.16.20.76` | `255.255.255.224` | `172.16.20.64/27` | S1:L184,L876 |
| D161 | `FastEthernet0` | `172.16.20.77` | `255.255.255.224` | `172.16.20.64/27` | S1:L185,L878 |
| D162 | `FastEthernet0` | `172.16.20.79` | `255.255.255.224` | `172.16.20.64/27` | S1:L186,L880 |
| D163 | `FastEthernet0` | `172.16.20.78` | `255.255.255.224` | `172.16.20.64/27` | S1:L187,L882 |
| D164 | `FastEthernet0` | `172.16.3.17` | `255.255.255.128` | `172.16.3.0/25` | S1:L188,L884 |
| D165 | `FastEthernet0` | `172.16.3.48` | `255.255.255.128` | `172.16.3.0/25` | S1:L189,L886 |
| D166 | `FastEthernet0` | `172.16.3.18` | `255.255.255.128` | `172.16.3.0/25` | S1:L190,L888 |
| D167 | `FastEthernet0` | `172.16.1.176` | `255.255.255.192` | `172.16.1.128/26` | S1:L191,L890 |
| D168 | `FastEthernet0` | `172.16.1.180` | `255.255.255.192` | `172.16.1.128/26` | S1:L192,L892 |
| D169 | `FastEthernet0` | `172.16.1.145` | `255.255.255.192` | `172.16.1.128/26` | S1:L193,L894 |
| D170 | `FastEthernet0` | `172.16.1.153` | `255.255.255.192` | `172.16.1.128/26` | S1:L194,L896 |
| D171 | `FastEthernet0` | `172.16.1.148` | `255.255.255.192` | `172.16.1.128/26` | S1:L195,L898 |
| D172 | `FastEthernet0` | `172.16.1.144` | `255.255.255.192` | `172.16.1.128/26` | S1:L196,L900 |
| D173 | `FastEthernet0` | `172.16.1.170` | `255.255.255.192` | `172.16.1.128/26` | S1:L197,L902 |
| D174 | `FastEthernet0` | `172.16.1.166` | `255.255.255.192` | `172.16.1.128/26` | S1:L198,L904 |
| D175 | `FastEthernet0` | `172.16.1.169` | `255.255.255.192` | `172.16.1.128/26` | S1:L199,L906 |
| D176 | `FastEthernet0` | `172.16.1.146` | `255.255.255.192` | `172.16.1.128/26` | S1:L200,L908 |
| D177 | `FastEthernet0` | `172.16.3.25` | `255.255.255.128` | `172.16.3.0/25` | S1:L201,L910 |
| D179 | `FastEthernet0` | `172.16.1.178` | `255.255.255.192` | `172.16.1.128/26` | S1:L913 |
| D180 | `FastEthernet0` | `172.16.1.135` | `255.255.255.192` | `172.16.1.128/26` | S1:L204,L915 |
| D181 | `FastEthernet0` | `172.16.1.168` | `255.255.255.192` | `172.16.1.128/26` | S1:L205,L917 |
| D182 | `FastEthernet0` | `172.16.1.160` | `255.255.255.192` | `172.16.1.128/26` | S1:L919 |
| D183 | `FastEthernet0` | `172.16.1.140` | `255.255.255.192` | `172.16.1.128/26` | S1:L207,L921 |
| D184 | `FastEthernet0` | `172.16.1.133` | `255.255.255.192` | `172.16.1.128/26` | S1:L208,L923 |
| D186 | `FastEthernet0` | `172.16.1.143` | `255.255.255.192` | `172.16.1.128/26` | S1:L210,L927 |
| D187 | `FastEthernet0` | `172.16.1.138` | `255.255.255.192` | `172.16.1.128/26` | S1:L211,L929 |
| D188 | `FastEthernet0` | `172.16.1.177` | `255.255.255.192` | `172.16.1.128/26` | S1:L931 |
| D189 | `FastEthernet0` | `172.16.1.172` | `255.255.255.192` | `172.16.1.128/26` | S1:L213,L933 |
| D190 | `Vlan50` | `172.16.2.23` | `255.255.255.224` | `172.16.2.0/27` | S1:L214,L936 |
| D191 | `Vlan50` | `172.16.2.22` | `255.255.255.224` | `172.16.2.0/27` | S1:L939 |
| D192 | `Vlan55` | `172.16.2.43` | `255.255.255.224` | `172.16.2.32/27` | S1:L216,L942 |
| D193 | `Vlan55` | `172.16.2.55` | `255.255.255.224` | `172.16.2.32/27` | S1:L945 |
| D194 | `Vlan50` | `172.16.2.4` | `255.255.255.224` | `172.16.2.0/27` | S1:L218,L948 |
| D195 | `Vlan55` | `172.16.2.40` | `255.255.255.224` | `172.16.2.32/27` | S1:L219 |
| D196 | `Vlan50` | `172.16.2.24` | `255.255.255.224` | `172.16.2.0/27` | S1:L220 |
| D197 | `Vlan50` | `172.16.2.27` | `255.255.255.224` | `172.16.2.0/27` | S1:L221 |
| D199 | `Vlan55` | `172.16.2.37` | `255.255.255.224` | `172.16.2.32/27` | S1:L223,L953 |
| D200 | `Vlan55` | `172.16.2.52` | `255.255.255.224` | `172.16.2.32/27` | S1:L224,L956 |
| D201 | `Vlan50` | `172.16.2.10` | `255.255.255.224` | `172.16.2.0/27` | S1:L225,L959 |
| D202 | `Vlan50` | `172.16.2.26` | `255.255.255.224` | `172.16.2.0/27` | S1:L226,L962 |
| D203 | `Vlan50` | `172.16.2.21` | `255.255.255.224` | `172.16.2.0/27` | S1:L227,L965 |
| D204 | `Vlan50` | `172.16.2.6` | `255.255.255.224` | `172.16.2.0/27` | S1:L228,L968 |
| D205 | `FastEthernet0` | `172.16.1.182` | `255.255.255.192` | `172.16.1.128/26` | S1:L229,L970 |
| D206 | `FastEthernet0` | `172.16.1.142` | `255.255.255.192` | `172.16.1.128/26` | S1:L230 |
| D207 | `FastEthernet0` | `172.16.1.181` | `255.255.255.192` | `172.16.1.128/26` | S1:L231 |
| D210 | `FastEthernet0` | `172.16.1.167` | `255.255.255.192` | `172.16.1.128/26` | S1:L234,L977 |
| D211 | `FastEthernet0` | `172.16.3.24` | `255.255.255.128` | `172.16.3.0/25` | S1:L235,L979 |
| D212 | `FastEthernet0` | `172.16.3.23` | `255.255.255.128` | `172.16.3.0/25` | S1:L236,L981 |
| D213 | `FastEthernet0` | `172.16.3.49` | `255.255.255.128` | `172.16.3.0/25` | S1:L237,L983 |
| D214 | `FastEthernet0` | `172.16.3.47` | `255.255.255.128` | `172.16.3.0/25` | S1:L238,L985 |
| D215 | `FastEthernet0` | `172.16.3.53` | `255.255.255.128` | `172.16.3.0/25` | S1:L239,L987 |
| D216 | `FastEthernet0` | `172.16.3.52` | `255.255.255.128` | `172.16.3.0/25` | S1:L240,L989 |
| D217 | `FastEthernet0` | `172.16.3.50` | `255.255.255.128` | `172.16.3.0/25` | S1:L241,L991 |
| D218 | `FastEthernet0` | `172.16.3.51` | `255.255.255.128` | `172.16.3.0/25` | S1:L242,L993 |
| D219 | `FastEthernet0` | `172.16.3.19` | `255.255.255.128` | `172.16.3.0/25` | S1:L995 |
| D223 | `Vlan55` | `172.16.2.34` | `255.255.255.224` | `172.16.2.32/27` | S1:L248,L1077 |
| D223 | `Vlan99` | `172.16.0.2` | `255.255.255.240` | `172.16.0.0/28` | S1:L248,L1078 |
| D224 | `Serial0/3/0` | `172.16.250.1` | `255.255.255.252` | `172.16.250.0/30` | S1:L249–L250,L1081 |
| D224 | `Serial0/3/1` | `172.16.250.5` | `255.255.255.252` | `172.16.250.4/30` | S1:L249–L250,L1082 |
| D224 | `FastEthernet0/0.10` | `172.16.1.1` | `255.255.255.240` | `172.16.1.0/28` | S1:L249–L250,L1083 |
| D224 | `FastEthernet0/0.20` | `172.16.1.33` | `255.255.255.224` | `172.16.1.32/27` | S1:L249–L250,L1084 |
| D224 | `FastEthernet0/0.30` | `172.16.1.65` | `255.255.255.224` | `172.16.1.64/27` | S1:L249–L250,L1085 |
| D224 | `FastEthernet0/0.40` | `172.16.1.129` | `255.255.255.192` | `172.16.1.128/26` | S1:L249–L250,L1086 |
| D224 | `FastEthernet0/0.60` | `172.16.3.1` | `255.255.255.128` | `172.16.3.0/25` | S1:L249–L250,L1088 |
| D224 | `FastEthernet0/0.70` | `172.16.4.1` | `255.255.255.240` | `172.16.4.0/28` | S1:L249–L250,L1089 |
| D224 | `FastEthernet0/0.99` | `172.16.0.1` | `255.255.255.240` | `172.16.0.0/28` | S1:L249–L250,L1090 |
| D224 | `FastEthernet0/0.100` | `172.16.100.1` | `255.255.255.240` | `172.16.100.0/28` | S1:L249–L250,L1091 |
| D224 | `FastEthernet0/0.50` | `172.16.2.1` | `255.255.255.224` | `172.16.2.0/27` | S1:L1087 |
| D229 | `FastEthernet0` | `172.16.10.6` | `255.255.255.240` | `172.16.10.0/28` | S1:L256 |
| D231 | `FastEthernet0` | `172.16.10.4` | `255.255.255.240` | `172.16.10.0/28` | S1:L258 |
| D232 | `FastEthernet0` | `172.16.10.2` | `255.255.255.240` | `172.16.10.0/28` | S1:L259 |
| D233 | `FastEthernet0` | `172.16.10.5` | `255.255.255.240` | `172.16.10.0/28` | S1:L260,L1152 |
| D234 | `FastEthernet0` | `172.16.10.3` | `255.255.255.240` | `172.16.10.0/28` | S1:L261,L1154 |
| D235 | `FastEthernet0` | `172.16.10.19` | `255.255.255.240` | `172.16.10.16/28` | S1:L262,L1156 |
| D236 | `FastEthernet0` | `172.16.10.21` | `255.255.255.240` | `172.16.10.16/28` | S1:L1158 |
| D237 | `FastEthernet0` | `172.16.10.18` | `255.255.255.240` | `172.16.10.16/28` | S1:L264,L1160 |
| D238 | `Vlan51` | `172.16.10.38` | `255.255.255.224` | `172.16.10.32/27` | S1:L265,L1163 |
| D239 | `Vlan51` | `172.16.10.39` | `255.255.255.224` | `172.16.10.32/27` | S1:L1166 |
| D240 | `Vlan51` | `172.16.10.34` | `255.255.255.224` | `172.16.10.32/27` | S1:L267,L1169 |
| D241 | `Vlan51` | `172.16.10.40` | `255.255.255.224` | `172.16.10.32/27` | S1:L268 |
| D243 | `Vlan51` | `172.16.10.41` | `255.255.255.224` | `172.16.10.32/27` | S1:L270,L1171 |
| D244 | `Vlan51` | `172.16.10.37` | `255.255.255.224` | `172.16.10.32/27` | S1:L271,L1174 |
| D245 | `Vlan51` | `172.16.10.35` | `255.255.255.224` | `172.16.10.32/27` | S1:L272,L1177 |
| D246 | `FastEthernet0` | `172.16.10.14` | `255.255.255.240` | `172.16.10.0/28` | S1:L273,L1179 |
| D250 | `FastEthernet0` | `172.16.10.74` | `255.255.255.192` | `172.16.10.64/26` | S1:L278,L1196 |
| D251 | `FastEthernet0` | `172.16.10.73` | `255.255.255.192` | `172.16.10.64/26` | S1:L279,L1198 |
| D252 | `FastEthernet0` | `172.16.10.94` | `255.255.255.192` | `172.16.10.64/26` | S1:L280,L1200 |
| D253 | `FastEthernet0` | `172.16.10.90` | `255.255.255.192` | `172.16.10.64/26` | S1:L281,L1202 |
| D255 | `FastEthernet0` | `172.16.10.87` | `255.255.255.192` | `172.16.10.64/26` | S1:L283,L1207 |
| D256 | `FastEthernet0` | `172.16.10.85` | `255.255.255.192` | `172.16.10.64/26` | S1:L284,L1209 |
| D257 | `FastEthernet0` | `172.16.10.84` | `255.255.255.192` | `172.16.10.64/26` | S1:L285,L1211 |
| D258 | `FastEthernet0` | `172.16.10.83` | `255.255.255.192` | `172.16.10.64/26` | S1:L286,L1213 |
| D259 | `FastEthernet0` | `172.16.10.82` | `255.255.255.192` | `172.16.10.64/26` | S1:L287 |
| D260 | `FastEthernet0` | `172.16.10.81` | `255.255.255.192` | `172.16.10.64/26` | S1:L288,L1215 |
| D261 | `FastEthernet0` | `172.16.10.80` | `255.255.255.192` | `172.16.10.64/26` | S1:L289,L1217 |
| D262 | `FastEthernet0` | `172.16.10.79` | `255.255.255.192` | `172.16.10.64/26` | S1:L290,L1219 |
| D263 | `FastEthernet0` | `172.16.10.78` | `255.255.255.192` | `172.16.10.64/26` | S1:L291,L1221 |
| D264 | `FastEthernet0` | `172.16.10.77` | `255.255.255.192` | `172.16.10.64/26` | S1:L292,L1223 |
| D265 | `FastEthernet0` | `172.16.10.72` | `255.255.255.192` | `172.16.10.64/26` | S1:L293,L1225 |
| D266 | `Serial0/3/0` | `172.16.250.2` | `255.255.255.252` | `172.16.250.0/30` | S1:L294,L1228 |
| D266 | `Serial0/3/1` | `172.16.250.9` | `255.255.255.252` | `172.16.250.8/30` | S1:L294,L1229 |
| D266 | `FastEthernet0/0.11` | `172.16.10.1` | `255.255.255.240` | `172.16.10.0/28` | S1:L294,L1230 |
| D266 | `FastEthernet0/0.21` | `172.16.10.17` | `255.255.255.240` | `172.16.10.16/28` | S1:L294,L1231 |
| D266 | `FastEthernet0/0.51` | `172.16.10.33` | `255.255.255.224` | `172.16.10.32/27` | S1:L294,L1232 |
| D266 | `FastEthernet0/0.61` | `172.16.10.65` | `255.255.255.192` | `172.16.10.64/26` | S1:L294,L1233 |
| D266 | `FastEthernet0/0.71` | `172.16.10.129` | `255.255.255.240` | `172.16.10.128/28` | S1:L294,L1234 |
| D266 | `FastEthernet0/0.81` | `172.16.10.145` | `255.255.255.240` | `172.16.10.144/28` | S1:L294,L1235 |
| D266 | `FastEthernet0/0.299` | `172.16.10.161` | `255.255.255.240` | `172.16.10.160/28` | S1:L294,L1236 |
| D267 | `FastEthernet0` | `172.16.3.20` | `255.255.255.128` | `172.16.3.0/25` | S1:L295,L1238 |
| D268 | `FastEthernet0` | `172.16.3.22` | `255.255.255.128` | `172.16.3.0/25` | S1:L1240 |
| D269 | `FastEthernet0` | `172.16.3.21` | `255.255.255.128` | `172.16.3.0/25` | S1:L297,L1242 |
| D270 | `FastEthernet0` | `172.16.3.9` | `255.255.255.128` | `172.16.3.0/25` | S1:L298,L1244 |
| D271 | `FastEthernet0` | `172.16.3.10` | `255.255.255.128` | `172.16.3.0/25` | S1:L299,L1246 |
| D272 | `FastEthernet0` | `172.16.3.11` | `255.255.255.128` | `172.16.3.0/25` | S1:L300,L1248 |
| D273 | `FastEthernet0` | `172.16.3.8` | `255.255.255.128` | `172.16.3.0/25` | S1:L301,L1250 |
| D274 | `FastEthernet0` | `172.16.3.36` | `255.255.255.128` | `172.16.3.0/25` | S1:L302,L1252 |
| D275 | `FastEthernet0` | `172.16.3.37` | `255.255.255.128` | `172.16.3.0/25` | S1:L303,L1254 |
| D276 | `FastEthernet0` | `172.16.3.38` | `255.255.255.128` | `172.16.3.0/25` | S1:L1256 |
| D277 | `FastEthernet0` | `172.16.100.8` | `255.255.255.240` | `172.16.100.0/28` | S1:L306,L1274 |
| D278 | `FastEthernet0` | `172.16.100.5` | `255.255.255.240` | `172.16.100.0/28` | S1:L307,L1276 |
| D279 | `FastEthernet0` | `172.16.100.7` | `255.255.255.240` | `172.16.100.0/28` | S1:L308,L1278 |
| D281 | `FastEthernet0` | `172.16.10.76` | `255.255.255.192` | `172.16.10.64/26` | S1:L310,L1281 |
| D282 | `FastEthernet0` | `172.16.10.86` | `255.255.255.192` | `172.16.10.64/26` | S1:L311,L1283 |
| D287 | `FastEthernet0` | `172.16.10.93` | `255.255.255.192` | `172.16.10.64/26` | S1:L316,L1296 |
| D288 | `FastEthernet0` | `172.16.10.92` | `255.255.255.192` | `172.16.10.64/26` | S1:L317,L1298 |
| D289 | `FastEthernet0` | `172.16.10.88` | `255.255.255.192` | `172.16.10.64/26` | S1:L318,L1300 |
| D290 | `FastEthernet0` | `172.16.10.89` | `255.255.255.192` | `172.16.10.64/26` | S1:L319,L1302 |
| D291 | `FastEthernet0` | `172.16.10.91` | `255.255.255.192` | `172.16.10.64/26` | S1:L320,L1304 |
| D292 | `FastEthernet0` | `172.16.10.98` | `255.255.255.192` | `172.16.10.64/26` | S1:L321,L1306 |
| D293 | `FastEthernet0` | `172.16.10.97` | `255.255.255.192` | `172.16.10.64/26` | S1:L322,L1308 |
| D294 | `FastEthernet0` | `172.16.10.96` | `255.255.255.192` | `172.16.10.64/26` | S1:L323,L1310 |
| D295 | `FastEthernet0` | `172.16.10.95` | `255.255.255.192` | `172.16.10.64/26` | S1:L324,L1312 |
| D296 | `FastEthernet0/0` | `172.16.2.33` | `255.255.255.224` | `172.16.2.32/27` | S1:L325,L1314 |
| D297 | `FastEthernet0` | `172.16.20.86` | `255.255.255.224` | `172.16.20.64/27` | S1:L326,L1316 |
| D298 | `FastEthernet0` | `172.16.3.13` | `255.255.255.128` | `172.16.3.0/25` | S1:L493 |
| D299 | `FastEthernet0` | `172.16.3.3` | `255.255.255.128` | `172.16.3.0/25` | S1:L495 |
| D300 | `FastEthernet0` | `172.16.3.5` | `255.255.255.128` | `172.16.3.0/25` | S1:L497 |
| D301 | `FastEthernet0` | `172.16.3.4` | `255.255.255.128` | `172.16.3.0/25` | S1:L499 |
| D302 | `FastEthernet0` | `172.16.3.6` | `255.255.255.128` | `172.16.3.0/25` | S1:L501 |
| D303 | `FastEthernet0` | `172.16.3.2` | `255.255.255.128` | `172.16.3.0/25` | S1:L503 |
| D305 | `FastEthernet0` | `172.16.20.73` | `255.255.255.224` | `172.16.20.64/27` | S1:L862 |
| D306 | `FastEthernet0` | `172.16.20.74` | `255.255.255.224` | `172.16.20.64/27` | S1:L864 |
| D307 | `FastEthernet0` | `172.16.20.85` | `255.255.255.224` | `172.16.20.64/27` | S1:L866 |
| D308 | `FastEthernet0` | `172.16.20.83` | `255.255.255.224` | `172.16.20.64/27` | S1:L180,L867–L868 |
| D310 | `FastEthernet0` | `172.16.10.71` | `255.255.255.192` | `172.16.10.64/26` | S1:L1191 |
| D311 | `FastEthernet0` | `172.16.10.70` | `255.255.255.192` | `172.16.10.64/26` | S1:L1193 |
| D313 | `Vlan50` | `172.16.2.20` | `255.255.255.224` | `172.16.2.0/27` | S1:L1259 |
| D315 | `FastEthernet0` | `172.16.10.75` | `255.255.255.192` | `172.16.10.64/26` | S1:L1263 |
| D316 | `FastEthernet0` | `172.16.100.3` | `255.255.255.240` | `172.16.100.0/28` | S1:L1265 |
| D318 | `FastEthernet0` | `172.16.100.6` | `255.255.255.240` | `172.16.100.0/28` | S1:L1268 |
| D319 | `FastEthernet0` | `172.16.100.2` | `255.255.255.240` | `172.16.100.0/28` | S1:L1270 |
| D320 | `FastEthernet0` | `172.16.100.4` | `255.255.255.240` | `172.16.100.0/28` | S1:L305,L1271–L1272 |

### 7.2 Subredes calculadas y población observada

| Subred | Pares IP/interfaz | Dispositivos distintos | Interfaces L3 referidas; no gateways de clientes confirmados |
| --- | --- | --- | --- |
| `172.16.0.0/28` | 2 | 2 | `SW-CORE:Vlan99`; `R-Matriz:FastEthernet0/0.99` |
| `172.16.1.0/28` | 7 | 7 | `R-Matriz:FastEthernet0/0.10` |
| `172.16.1.32/27` | 13 | 13 | `R-Matriz:FastEthernet0/0.20` |
| `172.16.1.64/27` | 16 | 16 | `R-Matriz:FastEthernet0/0.30` |
| `172.16.1.128/26` | 37 | 37 | `R-Matriz:FastEthernet0/0.40` |
| `172.16.2.0/27` | 27 | 27 | `R-Matriz:FastEthernet0/0.50` |
| `172.16.2.32/27` | 30 | 30 | `SW-CORE:Vlan55`; `Server VOZ:FastEthernet0/0` |
| `172.16.3.0/25` | 59 | 59 | `R-Matriz:FastEthernet0/0.60` |
| `172.16.4.0/28` | 1 | 1 | `R-Matriz:FastEthernet0/0.70` |
| `172.16.10.0/28` | 7 | 7 | `R-Fabrica:FastEthernet0/0.11` |
| `172.16.10.16/28` | 4 | 4 | `R-Fabrica:FastEthernet0/0.21` |
| `172.16.10.32/27` | 8 | 8 | `R-Fabrica:FastEthernet0/0.51` |
| `172.16.10.64/26` | 30 | 30 | `R-Fabrica:FastEthernet0/0.61` |
| `172.16.10.128/28` | 1 | 1 | `R-Fabrica:FastEthernet0/0.71` |
| `172.16.10.144/28` | 1 | 1 | `R-Fabrica:FastEthernet0/0.81` |
| `172.16.10.160/28` | 1 | 1 | `R-Fabrica:FastEthernet0/0.299` |
| `172.16.20.0/28` | 5 | 5 | `R-Sucursal:FastEthernet0/0.12` |
| `172.16.20.16/28` | 4 | 4 | `R-Sucursal:FastEthernet0/0.22` |
| `172.16.20.32/28` | 8 | 8 | `R-Sucursal:FastEthernet0/0.52` |
| `172.16.20.64/27` | 20 | 20 | `R-Sucursal:FastEthernet0/0.62` |
| `172.16.20.96/28` | 1 | 1 | `R-Sucursal:FastEthernet0/0.72` |
| `172.16.20.112/28` | 1 | 1 | `R-Sucursal:FastEthernet0/0.199` |
| `172.16.100.0/28` | 8 | 8 | `R-Matriz:FastEthernet0/0.100` |
| `172.16.250.0/30` | 2 | 2 | `R-Matriz:Serial0/3/0`; `R-Fabrica:Serial0/3/0` |
| `172.16.250.4/30` | 2 | 2 | `R-Sucursal:Serial0/3/0`; `R-Matriz:Serial0/3/1` |
| `172.16.250.8/30` | 2 | 2 | `R-Sucursal:Serial0/3/1`; `R-Fabrica:Serial0/3/1` |

No se detectaron direcciones IPv4 idénticas en sujetos distintos entre los 297 pares completos consolidados. Esa comprobación no establece ausencia de duplicados en los campos no recuperados, ni estado simultáneo de toda la red.

### 7.3 Direcciones truncadas que permanecen abiertas

| Sujeto | Información conservada | Lo que no se recuperó | Fuente |
| --- | --- | --- | --- |
| `IP Phone27(1):Vlan50` | Prefijo textual `172.16.` | Dirección completa y máscara | S1:L222 |
| `FOFI2:FastEthernet0` | IPv4 completa `172.16.10.7` | Máscara; `255` es sólo un fragmento, no un prefijo válido | S1:L257 |
| `IP Phone51:Vlan51` | Prefijo textual `172.16.` | Dirección completa y máscara | S1:L269 |
| `IP Phone56` | Fragmento `.16.2.18/255.255.255.224` | IPv4 completa y nombre de la interfaz a la que pertenece | S1:L1260–L1261 |

Las interfaces sin par completo y sin fragmento explícito quedan `NO_MOSTRADO` en la fuente, no «sin configurar». Por ejemplo, la falta de IP en una interfaz de AP no autoriza asignarle una. La dirección `172.16.10.66/26` aparece en un registro cuyo nombre está cortado; permanece en la sección de fragmentos y no se atribuye a un sensor por semejanza del nombre.

## 8. Conexiones

### 8.1 Cables completos sin conflicto textual

Son 225 registros con extremos completos y sin reutilización incompatible de un mismo extremo dentro de este subconjunto. Se conserva la orientación de escritura del export aunque el enlace se interprete bidireccional. «Completo» califica el registro textual, no una comprobación del cable en Packet Tracer.

| ID | Extremo A | Extremo B | Proyección | Fuente |
| --- | --- | --- | --- | --- |
| L001 | `SW3-P1` : `FastEthernet0/1` | `IoT15` : `FastEthernet0` | EXCLUIDO_IOT | S1:L1335 |
| L002 | `SW3-P1` : `FastEthernet0/2` | `IoT11` : `FastEthernet0` | EXCLUIDO_IOT | S1:L1336 |
| L003 | `SW3-P1` : `FastEthernet0/3` | `IoT13` : `FastEthernet0` | EXCLUIDO_IOT | S1:L1337 |
| L004 | `SW3-P1` : `FastEthernet0/4` | `IoT12` : `FastEthernet0` | EXCLUIDO_IOT | S1:L1338 |
| L005 | `SW3-P1` : `FastEthernet0/5` | `IoT14` : `FastEthernet0` | EXCLUIDO_IOT | S1:L1339 |
| L007 | `SW3-P3` : `FastEthernet0/4` | `IoT1` : `FastEthernet0` | EXCLUIDO_IOT | S1:L1341 |
| L008 | `SW3-P3` : `FastEthernet0/5` | `IoT2` : `FastEthernet0` | EXCLUIDO_IOT | S1:L1342 |
| L009 | `SW3-P3` : `FastEthernet0/6` | `IoT3` : `FastEthernet0` | EXCLUIDO_IOT | S1:L1343 |
| L010 | `SW3-P3` : `FastEthernet0/7` | `IoT4` : `FastEthernet0` | EXCLUIDO_IOT | S1:L1344 |
| L011 | `SW3-P3` : `FastEthernet0/8` | `IoT23` : `FastEthernet0` | EXCLUIDO_IOT | S1:L1345 |
| L012 | `SW3-P3` : `FastEthernet0/9` | `IoT24` : `FastEthernet0` | EXCLUIDO_IOT | S1:L1346 |
| L013 | `SW3-P3` : `FastEthernet0/10` | `IoT25` : `FastEthernet0` | EXCLUIDO_IOT | S1:L1347 |
| L014 | `SW3-P3` : `FastEthernet0/11` | `IoT35` : `FastEthernet0` | EXCLUIDO_IOT | S1:L1348 |
| L015 | `SW3-P3` : `FastEthernet0/12` | `IoT36` : `FastEthernet0` | EXCLUIDO_IOT | S1:L1349 |
| L016 | `SW3-P3` : `FastEthernet0/13` | `Proyector` : `FastEthernet0` | ALCANCE_PENDIENTE | S1:L1350 |
| L017 | `SW3-P3` : `FastEthernet0/14` | `IoT32` : `FastEthernet0` | EXCLUIDO_IOT | S1:L1351 |
| L018 | `SW3-P3` : `FastEthernet0/15` | `IoT31` : `FastEthernet0` | EXCLUIDO_IOT | S1:L1352 |
| L019 | `SW3-P3` : `FastEthernet0/16` | `IoT30` : `FastEthernet0` | EXCLUIDO_IOT | S1:L1353 |
| L020 | `SW3-P3` : `FastEthernet0/17` | `IoT26` : `FastEthernet0` | EXCLUIDO_IOT | S1:L1354 |
| L021 | `SW3-P3` : `FastEthernet0/18` | `IoT29` : `FastEthernet0` | EXCLUIDO_IOT | S1:L1355 |
| L022 | `SW3-P3` : `FastEthernet0/19` | `IoT28` : `FastEthernet0` | EXCLUIDO_IOT | S1:L1356 |
| L023 | `SW3-P3` : `FastEthernet0/20` | `IoT27` : `FastEthernet0` | EXCLUIDO_IOT | S1:L1357 |
| L024 | `SW-SUC-1` : `FastEthernet0/2` | `SPCRE2` : `FastEthernet0` | INCLUIDO | S1:L1358 |
| L025 | `SW-SUC-1` : `FastEthernet0/3` | `SPCAJ1` : `FastEthernet0` | INCLUIDO | S1:L1359 |
| L026 | `SW-SUC-1` : `FastEthernet0/4` | `SPCAJ2` : `FastEthernet0` | INCLUIDO | S1:L1360 |
| L027 | `SW-SUC-1` : `FastEthernet0/5` | `SPTICs1` : `FastEthernet0` | INCLUIDO | S1:L1361 |
| L028 | `SW-SUC-1` : `FastEthernet0/6` | `SPTICs2` : `FastEthernet0` | INCLUIDO | S1:L1362 |
| L029 | `SW-SUC-1` : `FastEthernet0/7` | `SBOD` : `FastEthernet0` | INCLUIDO | S1:L1363 |
| L030 | `SW-SUC-1` : `FastEthernet0/9` | `IP Phone40` : `Switch` | INCLUIDO | S1:L1364 |
| L031 | `SW-SUC-1` : `FastEthernet0/10` | `IP Phone41` : `Switch` | INCLUIDO | S1:L1365 |
| L032 | `SW-SUC-1` : `FastEthernet0/12` | `IP Phone42` : `Switch` | INCLUIDO | S1:L1366 |
| L034 | `SW-SUC-2` : `FastEthernet0/11` | `IoT45` : `FastEthernet0` | EXCLUIDO_IOT | S1:L1368 |
| L035 | `SW-SUC-2` : `FastEthernet0/12` | `IoT44` : `FastEthernet0` | EXCLUIDO_IOT | S1:L1369 |
| L036 | `SW3-P1` : `FastEthernet0/7` | `IoT65` : `FastEthernet0` | EXCLUIDO_IOT | S1:L1370 |
| L037 | `SW3-P1` : `FastEthernet0/8` | `IoT61` : `FastEthernet0` | EXCLUIDO_IOT | S1:L1371 |
| L038 | `SW3-P1` : `FastEthernet0/9` | `IoT63` : `FastEthernet0` | EXCLUIDO_IOT | S1:L1372 |
| L039 | `SW3-P1` : `FastEthernet0/10` | `IoT64` : `FastEthernet0` | EXCLUIDO_IOT | S1:L1373 |
| L040 | `SW3-P3` : `FastEthernet0/21` | `IoT66` : `FastEthernet0` | EXCLUIDO_IOT | S1:L1374 |
| L041 | `SW3-P3` : `FastEthernet0/22` | `IoT68` : `FastEthernet0` | EXCLUIDO_IOT | S1:L1375 |
| L042 | `SW3-P3` : `FastEthernet0/23` | `IoT69` : `FastEthernet0` | EXCLUIDO_IOT | S1:L1376 |
| L043 | `SW1-P2` : `GigabitEthernet0/1` | `SW-CORE` : `GigabitEthernet1/0/2` | INCLUIDO | S1:L1377 |
| L044 | `SW-CORE-S` : `GigabitEthernet0/1` | `R-Fabrica` : `FastEthernet0/0` | INCLUIDO | S1:L1378 |
| L045 | `R-Matriz` : `FastEthernet0/0` | `SW-CORE` : `GigabitEthernet1/0/24` | INCLUIDO | S1:L1379 |
| L046 | `SW1-P1` : `GigabitEthernet0/1` | `SW-CORE` : `GigabitEthernet1/0/1` | INCLUIDO | S1:L1380 |
| L047 | `SW1-P3` : `GigabitEthernet0/1` | `SW-CORE` : `GigabitEthernet1/0/3` | INCLUIDO | S1:L1381 |
| L048 | `SW-CORE-S` : `FastEthernet0/3` | `Switch17 SEGURIDAD` : `GigabitEthernet0/1` | INCLUIDO | S1:L1382 |
| L049 | `SW-CORE-S` : `FastEthernet0/1` | `Switch15 ADMIN` : `GigabitEthernet0/1` | INCLUIDO | S1:L1383 |
| L052 | `PT1AT2` : `FastEthernet0` | `SW1-P1` : `FastEthernet0/8` | INCLUIDO | S1:L1386 |
| L053 | `P1AT1` : `FastEthernet0` | `SW1-P1` : `FastEthernet0/9` | INCLUIDO | S1:L1387 |
| L054 | `P1AT3` : `FastEthernet0` | `SW1-P1` : `FastEthernet0/10` | INCLUIDO | S1:L1388 |
| L055 | `P1AT4` : `FastEthernet0` | `SW1-P1` : `FastEthernet0/11` | INCLUIDO | S1:L1389 |
| L056 | `P1AT5` : `FastEthernet0` | `SW1-P1` : `FastEthernet0/12` | INCLUIDO | S1:L1390 |
| L057 | `P1AT6` : `FastEthernet0` | `SW1-P1` : `FastEthernet0/13` | INCLUIDO | S1:L1391 |
| L058 | `P1AT8` : `FastEthernet0` | `SW1-P1` : `FastEthernet0/14` | INCLUIDO | S1:L1392 |
| L059 | `P1AT7` : `FastEthernet0` | `SW1-P1` : `FastEthernet0/15` | INCLUIDO | S1:L1393 |
| L060 | `P1AT10` : `FastEthernet0` | `SW1-P1` : `FastEthernet0/16` | INCLUIDO | S1:L1394 |
| L061 | `P1AT9` : `FastEthernet0` | `SW1-P1` : `FastEthernet0/17` | INCLUIDO | S1:L1395 |
| L062 | `P1AT11` : `FastEthernet0` | `SW1-P1` : `FastEthernet0/18` | INCLUIDO | S1:L1396 |
| L063 | `P1AT12` : `FastEthernet0` | `SW1-P1` : `FastEthernet0/19` | INCLUIDO | S1:L1397 |
| L064 | `P1AT13` : `FastEthernet0` | `SW1-P1` : `FastEthernet0/20` | INCLUIDO | S1:L1398 |
| L065 | `P1AT14` : `FastEthernet0` | `SW1-P1` : `FastEthernet0/21` | INCLUIDO | S1:L1399 |
| L066 | `I1AT1` : `FastEthernet0` | `SW1-P1` : `FastEthernet0/22` | INCLUIDO | S1:L1400 |
| L067 | `P1APAT1` : `Port 0` | `SW1-P1` : `FastEthernet0/23` | ALCANCE_PENDIENTE | S1:L1401 |
| L068 | `AP1Cl` : `Port 0` | `SW1-P1` : `FastEthernet0/24` | ALCANCE_PENDIENTE | S1:L1402 |
| L070 | `IP Phone3` : `Switch` | `SW2-P1` : `FastEthernet0/9` | INCLUIDO | S1:L1404 |
| L071 | `IP Phone4` : `Switch` | `SW2-P1` : `FastEthernet0/10` | INCLUIDO | S1:L1405 |
| L072 | `IP Phone5` : `Switch` | `SW2-P1` : `FastEthernet0/11` | INCLUIDO | S1:L1406 |
| L073 | `IP Phone6` : `Switch` | `SW2-P1` : `FastEthernet0/12` | INCLUIDO | S1:L1407 |
| L074 | `IP Phone7` : `Switch` | `SW2-P1` : `FastEthernet0/13` | INCLUIDO | S1:L1408 |
| L075 | `IP Phone10` : `Switch` | `SW2-P1` : `FastEthernet0/14` | INCLUIDO | S1:L1409 |
| L076 | `IP Phone13` : `Switch` | `SW2-P1` : `FastEthernet0/15` | INCLUIDO | S1:L1410 |
| L077 | `IP Phone16` : `Switch` | `SW2-P1` : `FastEthernet0/16` | INCLUIDO | S1:L1411 |
| L078 | `IP Phone11` : `Switch` | `SW2-P1` : `FastEthernet0/17` | INCLUIDO | S1:L1412 |
| L079 | `IP Phone14` : `Switch` | `SW2-P1` : `FastEthernet0/18` | INCLUIDO | S1:L1413 |
| L080 | `IoT9` : `FastEthernet0` | `SW2-P1` : `FastEthernet0/20` | EXCLUIDO_IOT | S1:L1414 |
| L081 | `IoT10` : `FastEthernet0` | `SW2-P1` : `FastEthernet0/21` | EXCLUIDO_IOT | S1:L1415 |
| L082 | `IoT7` : `FastEthernet0` | `SW2-P1` : `FastEthernet0/22` | EXCLUIDO_IOT | S1:L1416 |
| L083 | `IoT6` : `FastEthernet0` | `SW2-P1` : `FastEthernet0/23` | EXCLUIDO_IOT | S1:L1417 |
| L084 | `IoT5` : `FastEthernet0` | `SW2-P1` : `FastEthernet0/24` | EXCLUIDO_IOT | S1:L1418 |
| L085 | `P3CON5` : `FastEthernet0` | `SW1-P3` : `FastEthernet0/1` | INCLUIDO | S1:L1419 |
| L086 | `P3CON4` : `FastEthernet0` | `SW1-P3` : `FastEthernet0/2` | INCLUIDO | S1:L1420 |
| L088 | `P3CON2` : `FastEthernet0` | `SW1-P3` : `FastEthernet0/6` | INCLUIDO | S1:L1422 |
| L089 | `P3TICs2` : `FastEthernet0` | `SW1-P3` : `FastEthernet0/7` | INCLUIDO | S1:L1423 |
| L090 | `P3TICs6` : `FastEthernet0` | `SW1-P3` : `FastEthernet0/8` | INCLUIDO | S1:L1424 |
| L091 | `P3TICs4` : `FastEthernet0` | `SW1-P3` : `FastEthernet0/9` | INCLUIDO | S1:L1425 |
| L092 | `P3TICs5` : `FastEthernet0` | `SW1-P3` : `FastEthernet0/10` | INCLUIDO | S1:L1426 |
| L093 | `P3TICs3` : `FastEthernet0` | `SW1-P3` : `FastEthernet0/11` | INCLUIDO | S1:L1427 |
| L094 | `P3TICs1` : `FastEthernet0` | `SW1-P3` : `FastEthernet0/12` | INCLUIDO | S1:L1428 |
| L095 | `P3RRHH2` : `FastEthernet0` | `SW1-P3` : `FastEthernet0/13` | INCLUIDO | S1:L1429 |
| L096 | `P3RRHH1` : `FastEthernet0` | `SW1-P3` : `FastEthernet0/14` | INCLUIDO | S1:L1430 |
| L097 | `P3RRHH3` : `FastEthernet0` | `SW1-P3` : `FastEthernet0/15` | INCLUIDO | S1:L1431 |
| L098 | `P3RRHH4` : `FastEthernet0` | `SW1-P3` : `FastEthernet0/16` | INCLUIDO | S1:L1432 |
| L099 | `P3RRHH5` : `FastEthernet0` | `SW1-P3` : `FastEthernet0/17` | INCLUIDO | S1:L1433 |
| L100 | `P3RRHH6` : `FastEthernet0` | `SW1-P3` : `FastEthernet0/18` | INCLUIDO | S1:L1434 |
| L101 | `P3GER5` : `FastEthernet0` | `SW1-P3` : `FastEthernet0/19` | INCLUIDO | S1:L1435 |
| L102 | `P3GER4` : `FastEthernet0` | `SW1-P3` : `FastEthernet0/20` | INCLUIDO | S1:L1436 |
| L103 | `P3GER3` : `FastEthernet0` | `SW1-P3` : `FastEthernet0/21` | INCLUIDO | S1:L1437 |
| L104 | `P3GER2` : `FastEthernet0` | `SW1-P3` : `FastEthernet0/22` | INCLUIDO | S1:L1438 |
| L105 | `P3GER1` : `FastEthernet0` | `SW1-P3` : `FastEthernet0/23` | INCLUIDO | S1:L1439 |
| L106 | `AP3Con1` : `Port 0` | `SW1-P3` : `FastEthernet0/24` | ALCANCE_PENDIENTE | S1:L1440 |
| L107 | `SW3-P1` : `FastEthernet0/24` | `AP1EMPL1` : `Port 0` | ALCANCE_PENDIENTE | S1:L1441 |
| L108 | `P2MON1` : `FastEthernet0` | `SW3-P2` : `FastEthernet0/1` | INCLUIDO | S1:L1442 |
| L109 | `P2MON2` : `FastEthernet0` | `SW3-P2` : `FastEthernet0/2` | INCLUIDO | S1:L1443 |
| L110 | `P2TICs1` : `FastEthernet0` | `SW3-P2` : `FastEthernet0/3` | INCLUIDO | S1:L1444 |
| L111 | `P2TICs2` : `FastEthernet0` | `SW3-P2` : `FastEthernet0/4` | INCLUIDO | S1:L1445 |
| L112 | `P2TICs3` : `FastEthernet0` | `SW3-P2` : `FastEthernet0/5` | INCLUIDO | S1:L1446 |
| L113 | `P2TICs4` : `FastEthernet0` | `SW3-P2` : `FastEthernet0/6` | INCLUIDO | S1:L1447 |
| L114 | `P2TICs5` : `FastEthernet0` | `SW3-P2` : `FastEthernet0/7` | INCLUIDO | S1:L1448 |
| L115 | `P3INN1` : `FastEthernet0` | `SW3-P2` : `FastEthernet0/8` | INCLUIDO | S1:L1449 |
| L116 | `P3INN2` : `FastEthernet0` | `SW3-P2` : `FastEthernet0/9` | INCLUIDO | S1:L1450 |
| L117 | `P3INN3` : `FastEthernet0` | `SW3-P2` : `FastEthernet0/10` | INCLUIDO | S1:L1451 |
| L118 | `P3INN4` : `FastEthernet0` | `SW3-P2` : `FastEthernet0/11` | INCLUIDO | S1:L1452 |
| L119 | `IP Phone34(1)` : `Switch` | `SW3-P2` : `FastEthernet0/12` | INCLUIDO | S1:L1453 |
| L120 | `APCON1` : `Port 0` | `SW3-P2` : `FastEthernet0/24` | ALCANCE_PENDIENTE | S1:L1454 |
| L121 | `IoT1(1)` : `FastEthernet0` | `SW3-P2` : `FastEthernet0/13` | EXCLUIDO_IOT | S1:L1455 |
| L122 | `IoT1(2)` : `FastEthernet0` | `SW3-P2` : `FastEthernet0/14` | EXCLUIDO_IOT | S1:L1456 |
| L123 | `IoT4(1)` : `FastEthernet0` | `SW3-P2` : `FastEthernet0/15` | EXCLUIDO_IOT | S1:L1457 |
| L124 | `SW3-P2` : `FastEthernet0/16` | `IoT0(1)` : `FastEthernet0` | EXCLUIDO_IOT | S1:L1458 |
| L125 | `IoT3(1)` : `FastEthernet0` | `SW3-P2` : `FastEthernet0/17` | EXCLUIDO_IOT | S1:L1459 |
| L126 | `P3INN5` : `FastEthernet0` | `SW2-P2` : `FastEthernet0/1` | INCLUIDO | S1:L1460 |
| L127 | `P3INN8` : `FastEthernet0` | `SW2-P2` : `FastEthernet0/2` | INCLUIDO | S1:L1461 |
| L128 | `SW2-P2` : `FastEthernet0/3` | `P3INN6` : `FastEthernet0` | INCLUIDO | S1:L1462 |
| L129 | `P3INN7` : `FastEthernet0` | `SW2-P2` : `FastEthernet0/4` | INCLUIDO | S1:L1463 |
| L130 | `P3INN9` : `FastEthernet0` | `SW2-P2` : `FastEthernet0/5` | INCLUIDO | S1:L1464 |
| L131 | `P3INN10` : `FastEthernet0` | `SW2-P2` : `FastEthernet0/6` | INCLUIDO | S1:L1465 |
| L132 | `IoT30(1)` : `FastEthernet0` | `SW2-P2` : `FastEthernet0/14` | EXCLUIDO_IOT | S1:L1466 |
| L133 | `IoT58` : `FastEthernet0` | `SW2-P2` : `FastEthernet0/15` | EXCLUIDO_IOT | S1:L1467 |
| L134 | `IoT56` : `FastEthernet0` | `SW2-P2` : `FastEthernet0/16` | EXCLUIDO_IOT | S1:L1468 |
| L135 | `IoT24(2)` : `FastEthernet0` | `SW2-P2` : `FastEthernet0/17` | EXCLUIDO_IOT | S1:L1469 |
| L136 | `IoT28(1)` : `FastEthernet0` | `SW2-P2` : `FastEthernet0/18` | EXCLUIDO_IOT | S1:L1470 |
| L138 | `P3INN15` : `FastEthernet0` | `SW1-P2` : `FastEthernet0/6` | INCLUIDO | S1:L1472 |
| L139 | `P3INN17` : `FastEthernet0` | `SW1-P2` : `FastEthernet0/7` | INCLUIDO | S1:L1473 |
| L140 | `P3INN18` : `FastEthernet0` | `SW1-P2` : `FastEthernet0/8` | INCLUIDO | S1:L1474 |
| L141 | `P3INN19` : `FastEthernet0` | `SW1-P2` : `FastEthernet0/9` | INCLUIDO | S1:L1475 |
| L142 | `P3INN20` : `FastEthernet0` | `SW1-P2` : `FastEthernet0/10` | INCLUIDO | S1:L1476 |
| L143 | `IP Phone55` : `Switch` | `SW1-P2` : `FastEthernet0/11` | INCLUIDO | S1:L1477 |
| L144 | `SW1-P2` : `FastEthernet0/14` | `IP Phone21(1)` : `Switch` | INCLUIDO | S1:L1478 |
| L145 | `SW1-P2` : `FastEthernet0/13` | `IP Phone26(1)` : `Switch` | INCLUIDO | S1:L1479 |
| L146 | `SW1-P2` : `FastEthernet0/12` | `IP Phone56` : `Switch` | INCLUIDO | S1:L1480 |
| L147 | `SW1-P2` : `FastEthernet0/15` | `IP Phone19(1)` : `Switch` | INCLUIDO | S1:L1481 |
| L148 | `SW1-P2` : `FastEthernet0/16` | `IP Phone24(1)` : `Switch` | INCLUIDO | S1:L1482 |
| L149 | `SW1-P2` : `FastEthernet0/17` | `IP Phone27(1)` : `Switch` | INCLUIDO | S1:L1483 |
| L150 | `SW1-P2` : `FastEthernet0/18` | `IP Phone29(1)` : `Switch` | INCLUIDO | S1:L1484 |
| L151 | `SW1-P2` : `FastEthernet0/19` | `IP Phone33(1)` : `Switch` | INCLUIDO | S1:L1485 |
| L152 | `IoT29(1)` : `FastEthernet0` | `SW1-P2` : `FastEthernet0/20` | EXCLUIDO_IOT | S1:L1486 |
| L153 | `IoT2(1)` : `FastEthernet0` | `SW1-P2` : `FastEthernet0/21` | EXCLUIDO_IOT | S1:L1487 |
| L154 | `IoT25(1)` : `FastEthernet0` | `SW1-P2` : `FastEthernet0/22` | EXCLUIDO_IOT | S1:L1488 |
| L155 | `IoT23(1)` : `FastEthernet0` | `SW1-P2` : `FastEthernet0/23` | EXCLUIDO_IOT | S1:L1489 |
| L156 | `SW2-P2` : `FastEthernet0/7` | `IP Phone30(1)` : `Switch` | INCLUIDO | S1:L1490 |
| L157 | `SW2-P2` : `FastEthernet0/8` | `IP Phone32(1)` : `Switch` | INCLUIDO | S1:L1491 |
| L158 | `SW2-P2` : `FastEthernet0/13` | `IP Phone23(1)` : `Switch` | INCLUIDO | S1:L1492 |
| L159 | `SW2-P2` : `FastEthernet0/12` | `IP Phone20(1)` : `Switch` | INCLUIDO | S1:L1493 |
| L160 | `SW2-P2` : `FastEthernet0/11` | `IP Phone31(1)` : `Switch` | INCLUIDO | S1:L1494 |
| L161 | `SW2-P2` : `FastEthernet0/10` | `IP Phone22(1)` : `Switch` | INCLUIDO | S1:L1495 |
| L162 | `SW2-P2` : `FastEthernet0/9` | `IP Phone25(1)` : `Switch` | INCLUIDO | S1:L1496 |
| L163 | `SW2-P3` : `FastEthernet0/12` | `IP Phone28` : `Switch` | INCLUIDO | S1:L1497 |
| L165 | `SW2-P3` : `FastEthernet0/9` | `IP Phone31` : `Switch` | INCLUIDO | S1:L1499 |
| L166 | `SW2-P3` : `FastEthernet0/10` | `IP Phone29` : `Switch` | INCLUIDO | S1:L1500 |
| L167 | `SW2-P3` : `FastEthernet0/14` | `IP Phone25` : `Switch` | INCLUIDO | S1:L1501 |
| L168 | `SW2-P3` : `FastEthernet0/13` | `IP Phone26` : `Switch` | INCLUIDO | S1:L1502 |
| L169 | `SW2-P3` : `FastEthernet0/23` | `IP Phone24` : `Switch` | INCLUIDO | S1:L1503 |
| L170 | `SW2-P3` : `FastEthernet0/22` | `IP Phone21` : `Switch` | INCLUIDO | S1:L1504 |
| L171 | `SW2-P3` : `FastEthernet0/21` | `IP Phone20` : `Switch` | INCLUIDO | S1:L1505 |
| L172 | `SW2-P3` : `FastEthernet0/19` | `IP Phone27` : `Switch` | INCLUIDO | S1:L1506 |
| L173 | `SW2-P3` : `FastEthernet0/20` | `IP Phone22` : `Switch` | INCLUIDO | S1:L1507 |
| L174 | `SW2-P3` : `FastEthernet0/18` | `IP Phone23` : `Switch` | INCLUIDO | S1:L1508 |
| L175 | `SW2-P3` : `FastEthernet0/17` | `IP Phone19` : `Switch` | INCLUIDO | S1:L1509 |
| L176 | `SW2-P3` : `FastEthernet0/16` | `IP Phone18` : `Switch` | INCLUIDO | S1:L1510 |
| L177 | `SW2-P3` : `FastEthernet0/15` | `IP Phone17` : `Switch` | INCLUIDO | S1:L1511 |
| L178 | `SPCRE1` : `FastEthernet0` | `SW-SUC-1` : `FastEthernet0/1` | INCLUIDO | S1:L1512 |
| L179 | `IP Phone46` : `Switch` | `SW-SUC-1` : `FastEthernet0/8` | INCLUIDO | S1:L1513 |
| L180 | `SAPVIS` : `Port 0` | `SW-SUC-1` : `FastEthernet0/24` | ALCANCE_PENDIENTE | S1:L1514 |
| L182 | `SAPCaj` : `Port 0` | `SW-SUC-1` : `FastEthernet0/23` | ALCANCE_PENDIENTE | S1:L1516 |
| L183 | `SAPTICs` : `Port 0` | `SW-SUC-2` : `FastEthernet0/24` | ALCANCE_PENDIENTE | S1:L1517 |
| L184 | `IoT112` : `FastEthernet0` | `Switch17 SEGURIDAD` : `FastEthernet0/1` | EXCLUIDO_IOT | S1:L1518 |
| L185 | `IoT113(1)` : `FastEthernet0` | `Switch17 SEGURIDAD` : `FastEthernet0/2` | EXCLUIDO_IOT | S1:L1519 |
| L186 | `IoT113` : `FastEthernet0` | `Switch17 SEGURIDAD` : `FastEthernet0/3` | EXCLUIDO_IOT | S1:L1520 |
| L189 | `IoT0(2)(5)(2)(2)` : `FastEthernet0` | `Switch17 SEGURIDAD` : `FastEthernet0/12` | EXCLUIDO_IOT | S1:L1523 |
| L190 | `IoT0(2)(5)(2)(3)` : `FastEthernet0` | `Switch17 SEGURIDAD` : `FastEthernet0/13` | EXCLUIDO_IOT | S1:L1524 |
| L191 | `IoT0(2)(5)(2)(4)` : `FastEthernet0` | `Switch17 SEGURIDAD` : `FastEthernet0/14` | EXCLUIDO_IOT | S1:L1525 |
| L192 | `IoT0(2)(5)(2)(5)` : `FastEthernet0` | `Switch17 SEGURIDAD` : `FastEthernet0/15` | EXCLUIDO_IOT | S1:L1526 |
| L193 | `IoT0(2)(5)(2)(6)` : `FastEthernet0` | `Switch17 SEGURIDAD` : `FastEthernet0/16` | EXCLUIDO_IOT | S1:L1527 |
| L194 | `IoT0(2)(5)(2)(7)` : `FastEthernet0` | `Switch17 SEGURIDAD` : `FastEthernet0/17` | EXCLUIDO_IOT | S1:L1528 |
| L195 | `IoT0(2)(5)(2)(8)` : `FastEthernet0` | `Switch17 SEGURIDAD` : `FastEthernet0/18` | EXCLUIDO_IOT | S1:L1529 |
| L196 | `IoT41(1)` : `FastEthernet0` | `Switch17 SEGURIDAD` : `FastEthernet0/19` | EXCLUIDO_IOT | S1:L1530 |
| L197 | `IoT57` : `FastEthernet0` | `Switch17 SEGURIDAD` : `FastEthernet0/20` | EXCLUIDO_IOT | S1:L1531 |
| L198 | `FOFI1` : `FastEthernet0` | `Switch15 ADMIN` : `FastEthernet0/1` | INCLUIDO | S1:L1532 |
| L199 | `FOFI3` : `FastEthernet0` | `Switch15 ADMIN` : `FastEthernet0/3` | INCLUIDO | S1:L1533 |
| L200 | `FOFI4` : `FastEthernet0` | `Switch15 ADMIN` : `FastEthernet0/4` | INCLUIDO | S1:L1534 |
| L201 | `FOFI5` : `FastEthernet0` | `Switch15 ADMIN` : `FastEthernet0/5` | INCLUIDO | S1:L1535 |
| L202 | `FOFI6` : `FastEthernet0` | `Switch15 ADMIN` : `FastEthernet0/6` | INCLUIDO | S1:L1536 |
| L203 | `FBOD1` : `FastEthernet0` | `Switch15 ADMIN` : `FastEthernet0/7` | INCLUIDO | S1:L1537 |
| L204 | `FENF1` : `FastEthernet0` | `Switch15 ADMIN` : `FastEthernet0/8` | INCLUIDO | S1:L1538 |
| L205 | `FSEC1` : `FastEthernet0` | `Switch15 ADMIN` : `FastEthernet0/9` | INCLUIDO | S1:L1539 |
| L206 | `IP Phone49` : `Switch` | `Switch15 ADMIN` : `FastEthernet0/12` | INCLUIDO | S1:L1541 |
| L207 | `IP Phone50` : `Switch` | `Switch15 ADMIN` : `FastEthernet0/13` | INCLUIDO | S1:L1542 |
| L208 | `IP Phone51` : `Switch` | `Switch15 ADMIN` : `FastEthernet0/14` | INCLUIDO | S1:L1543 |
| L209 | `IP Phone52` : `Switch` | `Switch15 ADMIN` : `FastEthernet0/15` | INCLUIDO | S1:L1544 |
| L210 | `IP Phone53` : `Switch` | `Switch15 ADMIN` : `FastEthernet0/16` | INCLUIDO | S1:L1545 |
| L211 | `IP Phone54` : `Switch` | `Switch15 ADMIN` : `FastEthernet0/17` | INCLUIDO | S1:L1546 |
| L212 | `I1OFI` : `FastEthernet0` | `Switch15 ADMIN` : `FastEthernet0/18` | INCLUIDO | S1:L1547 |
| L213 | `FAP1EMPL` : `Port 0` | `Switch15 ADMIN` : `FastEthernet0/24` | ALCANCE_PENDIENTE | S1:L1548 |
| L214 | `FAP2EMPLE` : `Port 0` | `Switch16 NAVE` : `FastEthernet0/24` | ALCANCE_PENDIENTE | S1:L1549 |
| L215 | `FAPINV1` : `Port 0` | `Switch16 NAVE` : `FastEthernet0/23` | ALCANCE_PENDIENTE | S1:L1550 |
| L216 | `IoT113(8)` : `FastEthernet0` | `Switch16 NAVE` : `FastEthernet0/1` | EXCLUIDO_IOT | S1:L1551 |
| L217 | `IoT113(7)` : `FastEthernet0` | `Switch16 NAVE` : `FastEthernet0/2` | EXCLUIDO_IOT | S1:L1552 |
| L218 | `IoT113(6)` : `FastEthernet0` | `Switch16 NAVE` : `FastEthernet0/3` | EXCLUIDO_IOT | S1:L1553 |
| L219 | `IoT113(9)` : `FastEthernet0` | `Switch16 NAVE` : `FastEthernet0/4` | EXCLUIDO_IOT | S1:L1554 |
| L220 | `IoT0(2)` : `FastEthernet0` | `Switch16 NAVE` : `FastEthernet0/5` | EXCLUIDO_IOT | S1:L1555 |
| L221 | `IoT0(2)(1)` : `FastEthernet0` | `Switch16 NAVE` : `FastEthernet0/6` | EXCLUIDO_IOT | S1:L1556 |
| L223 | `IoT0(2)(3)` : `FastEthernet0` | `Switch16 NAVE` : `FastEthernet0/8` | EXCLUIDO_IOT | S1:L1558 |
| L224 | `IoT0(2)(4)` : `FastEthernet0` | `Switch16 NAVE` : `FastEthernet0/9` | EXCLUIDO_IOT | S1:L1559 |
| L225 | `IoT0(2)(5)` : `FastEthernet0` | `Switch16 NAVE` : `FastEthernet0/10` | EXCLUIDO_IOT | S1:L1560 |
| L226 | `IoT33(1)(1)` : `FastEthernet0` | `Switch16 NAVE` : `FastEthernet0/11` | EXCLUIDO_IOT | S1:L1561 |
| L227 | `IoT111` : `FastEthernet0` | `Switch16 NAVE` : `FastEthernet0/12` | EXCLUIDO_IOT | S1:L1562 |
| L228 | `IoT110` : `FastEthernet0` | `Switch16 NAVE` : `FastEthernet0/13` | EXCLUIDO_IOT | S1:L1563 |
| L229 | `IoT39` : `FastEthernet0` | `SW-SUC-1` : `FastEthernet0/15` | EXCLUIDO_IOT | S1:L1564 |
| L230 | `Server VOZ` : `FastEthernet0/0` | `SW-CORE` : `GigabitEthernet1/0/23` | INCLUIDO | S1:L1565 |
| L231 | `IoT41(2)` : `FastEthernet0` | `SW-SUC-1` : `FastEthernet0/21` | EXCLUIDO_IOT | S1:L1566 |
| L232 | `R-Matriz` : `Serial0/3/0` | `R-Fabrica` : `Serial0/3/0` | INCLUIDO | S1:L1567 |
| L233 | `R-Matriz` : `Serial0/3/1` | `R-Sucursal` : `Serial0/3/0` | INCLUIDO | S1:L1568 |
| L234 | `R-Sucursal` : `Serial0/3/1` | `R-Fabrica` : `Serial0/3/1` | INCLUIDO | S1:L1569 |
| L236 | `SW3-P3` : `GigabitEthernet0/1` | `SW-CORE` : `GigabitEthernet1/0/5` | INCLUIDO | S1:L1571 |
| L237 | `SW2-P1` : `GigabitEthernet0/2` | `SW-CORE` : `GigabitEthernet1/0/6` | INCLUIDO | S1:L1572 |
| L240 | `SW2-P2` : `GigabitEthernet0/2` | `SW-CORE` : `GigabitEthernet1/0/9` | INCLUIDO | S1:L1575 |

### 8.2 Conexiones incompletas o en conflicto — no ejecutables

| ID | Extremo A conservado | Extremo B conservado | Estado | Fuente | Motivo |
| --- | --- | --- | --- | --- | --- |
| L006 | DISPOSITIVO_NO_RECUPERADO : INTERFAZ_NO_RECUPERADA | `I3RRHH1` : `FastEthernet0` | INCOMPLETO | S1:L1340 | Falta parte de un extremo; no se completa por numeración de puertos. |
| L033 | DISPOSITIVO_NO_RECUPERADO : INTERFAZ_NO_RECUPERADA | `IoT46` : `FastEthernet0` | INCOMPLETO | S1:L1367 | Falta parte de un extremo; no se completa por numeración de puertos. |
| L050 | `SW-CORE-S` : `FastEthernet0/2` | `Switch16 NAVE` : INTERFAZ_NO_RECUPERADA | INCOMPLETO | S1:L1384 | Falta parte de un extremo; no se completa por numeración de puertos. |
| L051 | DISPOSITIVO_NO_RECUPERADO : INTERFAZ_NO_RECUPERADA | `SW1-P1` : `FastEthernet0/7` | INCOMPLETO | S1:L1385 | Falta parte de un extremo; no se completa por numeración de puertos. |
| L069 | DISPOSITIVO_NO_RECUPERADO : INTERFAZ_NO_RECUPERADA | `SW2-P1` : `FastEthernet0/8` | INCOMPLETO | S1:L1403 | Falta parte de un extremo; no se completa por numeración de puertos. |
| L087 | DISPOSITIVO_NO_RECUPERADO : INTERFAZ_NO_RECUPERADA | `SW1-P3` : `FastEthernet0/5` | INCOMPLETO | S1:L1421 | Falta parte de un extremo; no se completa por numeración de puertos. |
| L137 | DISPOSITIVO_NO_RECUPERADO : INTERFAZ_NO_RECUPERADA | `SW1-P2` : `FastEthernet0/5` | INCOMPLETO | S1:L1471 | Falta parte de un extremo; no se completa por numeración de puertos. |
| L164 | DISPOSITIVO_NO_RECUPERADO : INTERFAZ_NO_RECUPERADA | `IP Phone34` : `Switch` | INCOMPLETO | S1:L1498 | Falta parte de un extremo; no se completa por numeración de puertos. |
| L181 | `SW-SUC-1` : `GigabitEthernet0/2` | `SW-SUC-2` : INTERFAZ_NO_RECUPERADA | INCOMPLETO | S1:L1515 | Falta parte de un extremo; no se completa por numeración de puertos. |
| L187 | `IoT113(4)` : `FastEthernet0` | `Switch17 SEGURIDAD` : INTERFAZ_NO_RECUPERADA | INCOMPLETO | S1:L1521 | Falta parte de un extremo; no se completa por numeración de puertos. |
| L188 | DISPOSITIVO_NO_RECUPERADO : INTERFAZ_NO_RECUPERADA | `Switch17 SEGURIDAD` : `FastEthernet0/11` | INCOMPLETO | S1:L1522 | Falta parte de un extremo; no se completa por numeración de puertos. |
| L222 | `IoT0(2)(2)` : `FastEthernet0` | `Switch16 NAVE` : INTERFAZ_NO_RECUPERADA | INCOMPLETO | S1:L1557 | Falta parte de un extremo; no se completa por numeración de puertos. |
| L235 | `SW2-P3` : `GigabitEthernet0/2` | `SW-CORE` : INTERFAZ_NO_RECUPERADA | INCOMPLETO | S1:L1570 | Falta parte de un extremo; no se completa por numeración de puertos. |
| L238 | `SW3-P2` : `GigabitEthernet0/1` | `SW-CORE` : `GigabitEthernet1/0/7` | CONFLICTO | S1:L1573 | Compite con la otra fila sobre SW3-P2:GigabitEthernet0/1; no se elige una de las dos. |
| L239 | `SW3-P2` : `GigabitEthernet0/1` | `SW-CORE` : `GigabitEthernet1/0/8` | CONFLICTO | S1:L1574 | Compite con la otra fila sobre SW3-P2:GigabitEthernet0/1; no se elige una de las dos. |

**FR001 — S1:L1540:** sólo sobrevive `Switch15 ADMIN`:`FastEthernet0/11`. No se reconstruye el otro extremo ni se asigna a un teléfono por el orden de las líneas.

Los dos conflictos `L238` y `L239` no se materializan simultáneamente ni se cambian a otro switch/puerto para resolverlos. El dato correcto requiere una fuente adicional. Los 13 registros incompletos y el fragmento FR001 también se preservan literalmente en el apéndice.

### 8.3 Emisiones inalámbricas — sin asociación demostrada

| ID | Emisor reportado | Receptor | Fuente |
| --- | --- | --- | --- |
| RF001 | `P1APAT1` : `Port 1` | NO_INFORMADO | S1:L1319 |
| RF002 | `AP1Cl` : `Port 1` | NO_INFORMADO | S1:L1320 |
| RF003 | `AP3G1` : `Port 1` | NO_INFORMADO | S1:L1321 |
| RF004 | `AP3Cl1` : `Port 1` | NO_INFORMADO | S1:L1322 |
| RF005 | `AP3Con1` : `Port 1` | NO_INFORMADO | S1:L1323 |
| RF006 | `SAPCaj` : `Port 1` | NO_INFORMADO | S1:L1324 |
| RF007 | `SAPVIS` : `Port 1` | NO_INFORMADO | S1:L1325 |
| RF008 | `SAPTICs` : `Port 1` | NO_INFORMADO | S1:L1326 |
| RF009 | `FAP1EMPL` : `Port 1` | NO_INFORMADO | S1:L1327 |
| RF010 | `FAP2EMPLE` : `Port 1` | NO_INFORMADO | S1:L1328 |
| RF011 | `FAPINV1` : `Port 1` | NO_INFORMADO | S1:L1329 |
| RF012 | `APSEC1` : `Port 1` | NO_INFORMADO | S1:L1330 |
| RF013 | `AP1EMPL1` : `Port 1` | NO_INFORMADO | S1:L1331 |
| RF014 | `APCON1` : `Port 1` | NO_INFORMADO | S1:L1332 |
| RF015 | `AP2EMPLE2` : `Port 1` | NO_INFORMADO | S1:L1333 |
| RF016 | `AP2EMPLE1` : `Port 1` | NO_INFORMADO | S1:L1334 |

El símbolo `)))` sólo publica una emisión. No acredita que un PC, sensor u otro endpoint esté asociado al AP. Esta revisión no convierte esas 16 emisiones en pares de enlace ni las resta de 333 para inventar el número de cables perdidos.

## 9. Brechas y límites de la referencia

| ID | Tema | Disposición | Fuente |
| --- | --- | --- | --- |
| G-01 | Inventario de enlaces incompleto | 333 enlaces declarados no se reconcilian con las 240 filas <--> disponibles, las 16 emisiones y FR001. La fuente no permite determinar cuántos de los enlaces declarados eran de cada clase. | S1:L11,L330,L1318–L1575 |
| G-02 | Dos uplinks usan el mismo extremo | L238 y L239 publican el mismo puerto del switch con distintos puertos del core. Ambos se retienen en cuarentena. | S1:L1573–L1574 |
| G-03 | 13 cables con extremos truncados | Cada uno queda identificado en §8.2, con los fragmentos originales preservados. | §8.2 |
| G-04 | Cables de servidores no recuperados | Los siete Server-PT muestran [linked] en sus fichas, pero el peer/puerto no aparece como cable completo ni parcial con su nombre. | S1:L1264–L1278; §8 |
| G-05 | Tres modelos ausentes | IoT0(2)(3), IoT0(2)(4), IoT0(2)(5): nombres explícitos en enlaces, modelos no recuperados. No se transforman automáticamente en Smoke Detector. | S1:L1558–L1560 |
| G-06 | Datos de direccionamiento perdidos | Cuatro casos concretos en §7.3; otras interfaces sólo carecen de una IP mostrada. | §7.3 |
| G-07 | Identidad o límites de ficha dañados | Los bloques huérfanos no se asignan al dispositivo precedente ni por proximidad en el dibujo. | §9.2 |
| G-08 | Enumeración de interfaz sospechosa | R-Matriz:FastEthernet0/24 sólo aparece en una línea fusionada. Se conserva como literal cuestionado, fuera de la enumeración operativa de §6. | S1:L249–L250 |
| G-09 | Semántica de configuración ausente | El export no contiene VLANs efectivas de puertos, dot1Q, trunks, routing, DHCP/relay, DNS, páginas, cuentas, CME ni pruebas funcionales. | §4.3 |
| G-10 | Posiciones incompletas | 22 sujetos sin coordenadas completas. No determina su sede ni sus enlaces. | §5 |
| G-11 | Alcance no-IoT no totalmente decidido | APs y Proyector tienen clasificación pendiente. La infraestructura compartida se preserva; no se genera todavía un denominador final de aceptación. | §3.2 |

### 9.1 Sujetos incluidos sin cable completo no conflictivo en esta copia

Son **46** sujetos. La condición significa «no se recuperó un cable completo y no conflictivo», no «están desconectados»: algunos sí tienen una marca `[linked]` o un extremo parcial.

| ID | Nombre | Modelo |
| --- | --- | --- |
| D008 | `P1TICs3` | PC-PT |
| D010 | `P1CREDITO1` | PC-PT |
| D015 | `P1TICs1` | PC-PT |
| D016 | `P1CREDITO2` | PC-PT |
| D018 | `P1TICs4` | PC-PT |
| D022 | `P1GERENCIA` | PC-PT |
| D023 | `P1TICs2` | PC-PT |
| D026 | `IP Phone0` | 7960 |
| D027 | `IP Phone1` | 7960 |
| D028 | `IP Phone2` | 7960 |
| D034 | `IP Phone8` | 7960 |
| D035 | `IP Phone9` | 7960 |
| D038 | `IP Phone12` | 7960 |
| D041 | `IP Phone15` | 7960 |
| D043 | `I1AT2` | Printer-PT |
| D059 | `P3CON1` | PC-PT |
| D061 | `P3CON3` | PC-PT |
| D066 | `P3CON6` | PC-PT |
| D097 | `IP Phone30` | 7960 |
| D099 | `IP Phone32` | 7960 |
| D100 | `IP Phone33` | 7960 |
| D101 | `IP Phone34` | 7960 |
| D102 | `IP Phone35` | 7960 |
| D103 | `IP Phone36` | 7960 |
| D104 | `IP Phone37` | 7960 |
| D105 | `IP Phone38` | 7960 |
| D106 | `IP Phone39` | 7960 |
| D108 | `I3CON1` | Printer-PT |
| D112 | `I3RRHH1` | Printer-PT |
| D142 | `IP Phone43` | 7960 |
| D143 | `IP Phone44` | 7960 |
| D144 | `IP Phone45` | 7960 |
| D170 | `P3INN14` | PC-PT |
| D172 | `P3INN16` | PC-PT |
| D174 | `P3INN13` | PC-PT |
| D206 | `P3INN12` | PC-PT |
| D210 | `P3INN11` | PC-PT |
| D230 | `FOFI2` | PC-PT |
| D238 | `IP Phone47` | 7960 |
| D239 | `IP Phone48` | 7960 |
| D277 | `Servidor DB` | Server-PT |
| D279 | `Servidor-Apps` | Server-PT |
| D316 | `WEB-SERVER` | Server-PT |
| D318 | `DHCP-Server` | Server-PT |
| D319 | `DNS-SERVER` | Server-PT |
| D320 | `Email-Server` | Server-PT |

### 9.2 Fragmentos huérfanos o no utilizables

Se conservan como texto fuente, no como campos completos. Las líneas del bloque L1097–L1116 no se atribuyen a `SW-CORE-S`: hay un límite de ficha perdido y hacerlo inflaría sus puertos enlazados.

| Procedencia | Texto sobreviviente | Disposición |
| --- | --- | --- |
| S1:L69 | `Ethernet0/19,FastEthernet0/20,FastEthernet0/21,FastEthernet0/22,FastEthernet0/23,FastEthernet0/24,GigabitEthernet0/1,GigabitEthernet0/2)` | Cola posterior al cierre de un registro Q; posible cabecera omitida. No se atribuye al dispositivo anterior. |
| S1:L972 | `PT] @ (3232, 734)` | Encabezado/límite de registro perdido; no se atribuye por proximidad. |
| S1:L973 | `FastEthernet0 [linked]` | Interfaz completa pero propietario no recuperable en este bloque. |
| S1:L1097 | `/1 [linked]` | Encabezado/límite de registro perdido; no se atribuye por proximidad. |
| S1:L1098 | `FastEthernet0/2 [linked]` | Interfaz completa pero propietario no recuperable en este bloque. |
| S1:L1099 | `FastEthernet0/3 [linked]` | Interfaz completa pero propietario no recuperable en este bloque. |
| S1:L1100 | `FastEthernet0/4 [linked]` | Interfaz completa pero propietario no recuperable en este bloque. |
| S1:L1101 | `FastEthernet0/5 [linked]` | Interfaz completa pero propietario no recuperable en este bloque. |
| S1:L1102 | `FastEthernet0/6 [linked]` | Interfaz completa pero propietario no recuperable en este bloque. |
| S1:L1103 | `FastEthernet0/7 [linked]` | Interfaz completa pero propietario no recuperable en este bloque. |
| S1:L1104 | `FastEthernet0/8 [linked]` | Interfaz completa pero propietario no recuperable en este bloque. |
| S1:L1105 | `FastEthernet0/9 [linked]` | Interfaz completa pero propietario no recuperable en este bloque. |
| S1:L1106 | `FastEthernet0/10 [linked]` | Interfaz completa pero propietario no recuperable en este bloque. |
| S1:L1107 | `FastEthernet0/11 [linked]` | Interfaz completa pero propietario no recuperable en este bloque. |
| S1:L1108 | `FastEthernet0/12 [linked]` | Interfaz completa pero propietario no recuperable en este bloque. |
| S1:L1109 | `FastEthernet0/13 [linked]` | Interfaz completa pero propietario no recuperable en este bloque. |
| S1:L1110 | `FastEthernet0/14 [linked]` | Interfaz completa pero propietario no recuperable en este bloque. |
| S1:L1111 | `FastEthernet0/15 [linked]` | Interfaz completa pero propietario no recuperable en este bloque. |
| S1:L1112 | `FastEthernet0/16 [linked]` | Interfaz completa pero propietario no recuperable en este bloque. |
| S1:L1113 | `FastEthernet0/17 [linked]` | Interfaz completa pero propietario no recuperable en este bloque. |
| S1:L1114 | `FastEthernet0/18 [linked]` | Interfaz completa pero propietario no recuperable en este bloque. |
| S1:L1115 | `FastEthernet0/24 [linked]` | Interfaz completa pero propietario no recuperable en este bloque. |
| S1:L1116 | `GigabitEthernet0/1 [linked]` | Interfaz completa pero propietario no recuperable en este bloque. |
| S1:L1261 | `.16.2.18/255.255.255.224` | Fragmento no recuperado sin suponer identidad o valor. |
| S1:L1289 | `ssPoint-PT] @ (2574, 633)` | Encabezado/límite de registro perdido; no se atribuye por proximidad. |
| S1:L1290 | `Port 1 [linked]` | Interfaz completa pero propietario no recuperable en este bloque. |
| S1:L1291 | `Port 0 [linked]` | Interfaz completa pero propietario no recuperable en este bloque. |
| S1:L277 | `(2)(5)           [Smoke Detector]  (FastEthernet0=172.16.10.66/255.255.255.192,Bluetooth)` | Nombre parcial compatible con varias identidades; no se completa por semejanza o secuencia. |
| S1:L101–L102 | `FastEthernet0/net0/15` | Token Q no aceptado como interfaz/dirección. Su sujeto de contexto es SW2-P3. |
| S1:L127–L129 | `FastEthEthernet0/6` | Token Q no aceptado como interfaz/dirección. Su sujeto de contexto es SW3-P3. |
| S1:L127–L129 | `FastEthernet0/2et0/24` | Token Q no aceptado como interfaz/dirección. Su sujeto de contexto es SW3-P3. |
| S1:L151–L152 | `17/255.255.255.240` | Token Q no aceptado como interfaz/dirección. Su sujeto de contexto es R-Sucursal. |
| S1:L244–L245 | `FastEthernet0/2et0/24` | Token Q no aceptado como interfaz/dirección. Su sujeto de contexto es SW3-P2. |
| S1:L251–L252 | `FastEthernet0/net0/15` | Token Q no aceptado como interfaz/dirección. Su sujeto de contexto es SW-CORE-S. |
| S1:L510 | `Ethernet0/13 [linked]` | Contexto: SW3-P1. No se completa. |
| S1:L1279 | `@ (38` | Contexto: Power Distribution Device5. No se completa. |
| S1:L249–L250 | `FastEthernet0/24; aparece dentro de una enumeración dañada y no se corrobora en E ni en enlaces.` | Contexto: R-Matriz:FastEthernet0/24. No se completa. |

## 10. Registro de recuperación

Las siguientes operaciones son editoriales y de correlación documental; no son comandos enviados a Packet Tracer. Cada fila cita el original. La repetición de una misma fuente dentro de Q/E no constituye una verificación LIVE independiente.

| ID | Sujeto | Tipo | Tratamiento aplicado | Fuente |
| --- | --- | --- | --- | --- |
| C001 | `SW2-P3` | union_lineas | Se unieron sólo líneas de continuación del mismo registro; tokens incompletos no se completaron. | S1:L101–L102 |
| C002 | `SW3-P3` | union_lineas | Se unieron sólo líneas de continuación del mismo registro; tokens incompletos no se completaron. | S1:L127–L129 |
| C003 | `R-Sucursal` | union_lineas | Se unieron sólo líneas de continuación del mismo registro; tokens incompletos no se completaron. | S1:L151–L152 |
| C004 | `SW3-P2` | union_lineas | Se unieron sólo líneas de continuación del mismo registro; tokens incompletos no se completaron. | S1:L244–L245 |
| C005 | `R-Matriz` | union_lineas | Se unieron sólo líneas de continuación del mismo registro; tokens incompletos no se completaron. | S1:L249–L250 |
| C006 | `SW-CORE-S` | union_lineas | Se unieron sólo líneas de continuación del mismo registro; tokens incompletos no se completaron. | S1:L251–L252 |
| C007 | `SW2-P1:FastEthernet0/4` | prefijo_interfaz | Se repone exclusivamente el prefijo truncado a partir de la interfaz completa de ese mismo dispositivo en Q. | S1:L44,L405 |
| C008 | `IP Phone3` | interfaz_correspondiente | Se recupera Vlan50 del registro completo de consulta; no se asocia la dirección a IP Phone2. | S1:L48,L434 |
| C009 | `SW1-P3:FastEthernet0/4` | prefijo_interfaz | Se repone exclusivamente el prefijo truncado a partir de la interfaz completa de ese mismo dispositivo en Q. | S1:L77,L533 |
| C010 | `SW2-P3:FastEthernet0/9` | prefijo_interfaz | Se repone exclusivamente el prefijo truncado a partir de la interfaz completa de ese mismo dispositivo en Q. | S1:L101–L102,L609 |
| C011 | `IP Phone24` | encabezado_correspondiente | Sufijo literal e24 y modelo 7960 coinciden con el único nombre completo compatible del inventario. | S1:L111,L642 |
| C012 | `IoT27` | encabezado_correspondiente | Modelo Webcam y pareja IP/máscara posterior coinciden con la entrada completa de consulta. | S1:L143,L742–L743 |
| C013 | `SW-SUC-1:FastEthernet0/14` | prefijo_interfaz | Se repone exclusivamente el prefijo truncado a partir de la interfaz completa de ese mismo dispositivo en Q. | S1:L153,L775 |
| C014 | `IP Phone25(1)` | encabezado_correspondiente | Sufijo (1), modelo 7960 y Vlan55/IP/máscara coinciden de forma única en la consulta. | S1:L223,L951,L953 |
| C015 | `SW1-P2:FastEthernet0/11` | prefijo_interfaz | Se repone exclusivamente el prefijo truncado a partir de la interfaz completa de ese mismo dispositivo en Q. | S1:L247,L1046 |
| C016 | `SW-CORE:GigabitEthernet1/0/14` | prefijo_interfaz | Se repone exclusivamente el prefijo truncado a partir de la interfaz completa de ese mismo dispositivo en Q. | S1:L248,L1072 |
| C017 | `FOFI5` | encabezado_correspondiente | Pareja de interfaz/IP/máscara posterior coincide de forma única con la entrada de consulta; coordenadas asociadas por esa correspondencia. | S1:L260,L1151–L1152 |
| C018 | `IP Phone52` | encabezado_correspondiente | Vlan51/IP/máscara posterior coincide de forma única en la consulta. | S1:L270,L1170–L1171 |
| C019 | `IoT110` | encabezado_correspondiente | Sufijo del modelo y pareja interfaz/IP/máscara coinciden con RFID Reader en la consulta. | S1:L278,L1195–L1196 |
| C020 | `IoT0(2)(5)(2)(4)` | encabezado_correspondiente | Modelo Smoke Detector y pareja IP/máscara posterior coinciden de forma única en la consulta. | S1:L288,L1214–L1215 |
| C021 | `IoT45` | encabezado_correspondiente | Se vincula el nombre truncado de Q con el encabezado completo de E por sufijo, modelo y pareja IP/máscara coincidente. | S1:L180,L867–L868 |
| C022 | `Email-Server` | encabezado_correspondiente | Se vincula el nombre truncado de Q con el encabezado completo de E por sufijo, modelo y pareja IP/máscara coincidente. | S1:L305,L1271–L1272 |
| C023 | `P1AT9:FastEthernet0` | direccion_recuperada | El valor completo se conserva desde la otra aparición explícita; la representación truncada queda en el original. | S1:L23,L362 |
| C024 | `P1AT4:FastEthernet0` | direccion_recuperada | El valor completo se conserva desde la otra aparición explícita; la representación truncada queda en el original. | S1:L26,L368 |
| C025 | `P1CREDITO1:FastEthernet0` | direccion_recuperada | El valor completo se conserva desde la otra aparición explícita; la representación truncada queda en el original. | S1:L29,L374 |
| C026 | `P1AT6:FastEthernet0` | direccion_recuperada | El valor completo se conserva desde la otra aparición explícita; la representación truncada queda en el original. | S1:L32,L380 |
| C027 | `P1CREDITO2:FastEthernet0` | direccion_recuperada | El valor completo se conserva desde la otra aparición explícita; la representación truncada queda en el original. | S1:L35,L386 |
| C028 | `P1AT3:FastEthernet0` | direccion_recuperada | El valor completo se conserva desde la otra aparición explícita; la representación truncada queda en el original. | S1:L38,L392 |
| C029 | `P1GERENCIA:FastEthernet0` | direccion_recuperada | El valor completo se conserva desde la otra aparición explícita; la representación truncada queda en el original. | S1:L41,L398 |
| C030 | `I1AT1:FastEthernet0` | direccion_recuperada | El valor completo se conserva desde la otra aparición explícita; la representación truncada queda en el original. | S1:L43,L402 |
| C031 | `IP Phone0:Vlan50` | direccion_recuperada | El valor completo se conserva desde la otra aparición explícita; la representación truncada queda en el original. | S1:L45,L428 |
| C032 | `IoT5:FastEthernet0` | direccion_recuperada | El valor completo se conserva desde la otra aparición explícita; la representación truncada queda en el original. | S1:L65,L483 |
| C033 | `IoT9:FastEthernet0` | direccion_recuperada | El valor completo se conserva desde la otra aparición explícita; la representación truncada queda en el original. | S1:L69,L491 |
| C034 | `P3RRHH3:FastEthernet0` | direccion_recuperada | El valor completo se conserva desde la otra aparición explícita; la representación truncada queda en el original. | S1:L83,L566 |
| C035 | `P3RRHH1:FastEthernet0` | direccion_recuperada | El valor completo se conserva desde la otra aparición explícita; la representación truncada queda en el original. | S1:L84,L568 |
| C036 | `P3TICs6:FastEthernet0` | direccion_recuperada | El valor completo se conserva desde la otra aparición explícita; la representación truncada queda en el original. | S1:L88,L576 |
| C037 | `IP Phone18:Vlan55` | direccion_recuperada | El valor completo se conserva desde la otra aparición explícita; la representación truncada queda en el original. | S1:L105,L633 |
| C038 | `IP Phone29:Vlan55` | direccion_recuperada | El valor completo se conserva desde la otra aparición explícita; la representación truncada queda en el original. | S1:L116,L658 |
| C039 | `IP Phone32:Vlan55` | direccion_recuperada | El valor completo se conserva desde la otra aparición explícita; la representación truncada queda en el original. | S1:L119,L667 |
| C040 | `IP Phone38:Vlan55` | direccion_recuperada | El valor completo se conserva desde la otra aparición explícita; la representación truncada queda en el original. | S1:L125,L685 |
| C041 | `I3RRHH1:FastEthernet0` | direccion_recuperada | El valor completo se conserva desde la otra aparición explícita; la representación truncada queda en el original. | S1:L134,L726 |
| C042 | `SPCRE2:FastEthernet0` | direccion_recuperada | El valor completo se conserva desde la otra aparición explícita; la representación truncada queda en el original. | S1:L155,L790 |
| C043 | `IoT38:FastEthernet0` | direccion_recuperada | El valor completo se conserva desde la otra aparición explícita; la representación truncada queda en el original. | S1:L173,L833 |
| C044 | `P2TICs4:FastEthernet0` | direccion_recuperada | El valor completo se conserva desde la otra aparición explícita; la representación truncada queda en el original. | S1:L203,L913 |
| C045 | `P2MON1:FastEthernet0` | direccion_recuperada | El valor completo se conserva desde la otra aparición explícita; la representación truncada queda en el original. | S1:L206,L919 |
| C046 | `P3INN20:FastEthernet0` | direccion_recuperada | El valor completo se conserva desde la otra aparición explícita; la representación truncada queda en el original. | S1:L212,L931 |
| C047 | `IP Phone19(1):Vlan50` | direccion_recuperada | El valor completo se conserva desde la otra aparición explícita; la representación truncada queda en el original. | S1:L215,L939 |
| C048 | `IP Phone23(1):Vlan55` | direccion_recuperada | El valor completo se conserva desde la otra aparición explícita; la representación truncada queda en el original. | S1:L217,L945 |
| C049 | `IoT28(1):FastEthernet0` | direccion_recuperada | El valor completo se conserva desde la otra aparición explícita; la representación truncada queda en el original. | S1:L243,L995 |
| C050 | `FBOD1:FastEthernet0` | direccion_recuperada | El valor completo se conserva desde la otra aparición explícita; la representación truncada queda en el original. | S1:L263,L1158 |
| C051 | `IP Phone48:Vlan51` | direccion_recuperada | El valor completo se conserva desde la otra aparición explícita; la representación truncada queda en el original. | S1:L266,L1166 |
| C052 | `IoT56:FastEthernet0` | direccion_recuperada | El valor completo se conserva desde la otra aparición explícita; la representación truncada queda en el original. | S1:L296,L1240 |
| C053 | `IoT69:FastEthernet0` | direccion_recuperada | El valor completo se conserva desde la otra aparición explícita; la representación truncada queda en el original. | S1:L304,L1256 |

Para los 24 dispositivos cuyo encabezado E completo no sobrevive y cuyo nombre/modelo sí están en Q, se conserva ese encabezado Q como autoridad de identidad; no se reconstruye una ficha E ficticia. Inversamente, los nombres completos exclusivos de E se conservan desde E. Los tres sujetos sólo referidos por cable mantienen el modelo desconocido.

## 11. Comprobaciones de esta edición

| Comprobación | Resultado / alcance |
| --- | --- |
| Integridad de S1 | SHA-256 calculado sobre los bytes recibidos; la copia del ZIP coincide byte a byte. El bloque literal del apéndice se verifica contra ese mismo hash. |
| IDs y nombres | 323 IDs de dispositivo únicos y 323 nombres exactos únicos. |
| Modelos | 320 identidades con un modelo completo; 3 sin modelo. No hay un nombre con dos modelos completos en conflicto. |
| Direcciones | 297 pares completos analizables; 26 redes calculadas; ninguna IP repetida entre sujetos distintos en ese subconjunto. |
| Enlaces | 240 registros arrow clasificados exhaustivamente: 225 recuperados, 13 incompletos, 2 en conflicto. Más 16 emisiones y FR001, separados. |
| Integridad referencial | Los dos extremos de cada cable recuperado nombran sujetos del inventario; todo puerto en ese conjunto tiene un token completo procedente de S1. |
| Exclusividad de extremos | Las 225 filas de §8.1 no reutilizan un mismo par dispositivo/puerto. La colisión restante está excluida y documentada. |
| Proyección de alcance | 190 + 110 + 17 + 6 = 323; las clasificaciones no borran registros de la fuente. |
| Trazabilidad | Todas las referencias S1 de tablas corresponden a líneas dentro de 1…1575; se retienen las líneas y valores usados. |
| Representación Markdown | Tablas con aridad consistente, IDs únicos, anclas internas y bloque fuente delimitado; caracteres UTF-8 y finales LF. |
| No establecido | No se ejecutó Packet Tracer, no se releyó el Desktop, no se observó el PKT, no se verificaron funcionalidades ni se publicó el archivo en GitHub. |

Estas comprobaciones validan la consolidación de lo recibido. No convierten los conteos declarados por el emisor en inventario nativo íntegro ni permiten aceptar una réplica exacta mientras G-01…G-11 contengan datos materiales pendientes.

## 12. Historial y mantenimiento de versiones

| Versión | Fecha | Cambio | Base |
| --- | --- | --- | --- |
| 1.0.0 | 2026-09-26 | Primera edición documental consolidada: inventario, interfaces, IP, cables, alcance no-IoT, recuperaciones y brechas con fuente original incorporada. | S1, SHA-256 91802fa79a8538e4b3bb38170cdaeaec5f77e3ec8b32ff4c9e2b958fc973aa41 |

Una nueva fuente recuperada se incorpora como S2, S3, etc., con bytes y hash propios. Una corrección de presentación no cambia un dato silenciosamente; la recuperación de un valor antes ausente incrementa la revisión y cita la nueva evidencia. Los IDs existentes no se renumeran ni se reciclan para otro sujeto.

La aceptación completa futura exige resolver los extremos perdidos y conflictos, fijar los datos funcionales que el export nunca incluyó y reconciliar los conteos por clase. Mientras tanto, esta versión es utilizable para conocer la escala nominal, preparar los requisitos del producto y distinguir hechos de faltantes; no es un manifiesto listo para ejecutarse.

La versión documental no equivale a un commit Git. El archivo puede incorporarse íntegro a la rama de referencia; el commit de incorporación y cualquier aprobación posterior se obtienen del repositorio y se registran sin cambiar retroactivamente la identidad de S1.

<a id="s1-original"></a>

## Apéndice A. Fuente S1 íntegra

Este apéndice conserva los daños originales para auditoría. No compite con las tablas normalizadas ni autoriza interpretar sus fragmentos como datos completos. El contenido situado entre la apertura del bloque de texto y su cierre corresponde exactamente a los 84.055 bytes de S1, incluido su LF final.

<details>
<summary>Mostrar S1 original — 1.575 líneas, sólo evidencia</summary>

<!-- S1_LITERAL_BEGIN -->
````text
One thing about the third call: pt_export_topology is described as returning JSON, but it actually returned plain text. The response (58,885 characters) was too large to display inline, so it was saved to a file. I've pasted it below exactly as it was saved. The unchanged copy is at scratchpad\export_raw.txt.

1. pt_project_metadata (no description passed, so read-only)

{
  "found": true,
  "saved_filename": "C:/Users/Andres/Downloads/PKT ARTEFACTAaaa.pkt",
  "pt_version": "9.0.0.0810",
  "description": "",
  "devices": 323,
  "links": 333,
  "updated_description": false,
  "summary": "323 dispositivo(s), 333 enlace(s). Archivo: C:/Users/Andres/Downloads/PKT ARTEFACTAaaa.pkt."
}

2. pt_query_topology

DEVICES:323|LINKS:333

  SW1-P1               [2960-24TT]  (Vlan1,FastEthernet0/1,FastEthernet0/2,FastEthernet0/3,FastEthernet0/4,FastEthernet0/5,FastEthernet0/6,FastEthernet0/7,FastEthernet0/8,FastEthernet0/9,FastEthernet0/10,FastEthernet0/11,FastEthernet0/12,FastEthernet0/13,FastEthernet0/14,FastEthernet0/15,FastEthernet0/16,FastEthernet0/17,FastEthernet0/18,FastEthernet0/19,FastEthernet0/20,FastEthernet0/21,FastEthernet0/22,FastEthernet0/23,FastEthernet0/24,GigabitEthernet0/1,GigabitEthernet0/2)
  Power Distribution Device0 [Power Distribution Device]
  P1AT11               [PC-PT]  (FastEthernet0=172.16.1.73/255.255.255.224,Bluetooth)
  P1AT9                [PC-PT]  (FastEthernet0=172.16.1.81/255
  P1AT7                [PC-PT]  (FastEthernet0=172.16.1.85/255.255.255.224,Bluetooth)
  P1AT5                [PC-PT]  (FastEthernet0=172.16.1.88/255.255.255.224,Bluetooth)
  P1AT4                [PC-PT]  (FastEthernet0=172.16.1.77/255
  P1TICs3              [PC-PT]  (FastEthernet0=172.16.1.147/255.255.255.192,Bluetooth)
  P1AT13               [PC-PT]  (FastEthernet0=172.16.1.83/255.255.255.224,Bluetooth)
  P1CREDITO1           [PC-PT]  (FastEthernet0=172.16.1.175/25
  P1AT10               [PC-PT]  (FastEthernet0,Bluetooth)
  P1AT8                [PC-PT]  (FastEthernet0=172.16.1.89/255.255.255.224,Bluetooth)
  P1AT6                [PC-PT]  (FastEthernet0=172.16.1.74/255
  P1AT1                [PC-PT]  (FastEthernet0=172.16.1.90/255.255.255.224,Bluetooth)
  P1TICs1              [PC-PT]  (FastEthernet0=172.16.1.171/255.255.255.192,Bluetooth)
  P1CREDITO2           [PC-PT]  (FastEthernet0=172.16.1.152/25
  P1AT12               [PC-PT]  (FastEthernet0=172.16.1.86/255.255.255.224,Bluetooth)
  P1TICs4              [PC-PT]  (FastEthernet0=172.16.1.159/255.255.255.192,Bluetooth)
  P1AT3                [PC-PT]  (FastEthernet0=172.16.1.87/255
  PT1AT2               [PC-PT]  (FastEthernet0=172.16.1.80/255.255.255.224,Bluetooth)
  P1AT14               [PC-PT]  (FastEthernet0=172.16.1.84/255.255.255.224,Bluetooth)
  P1GERENCIA           [PC-PT]  (FastEthernet0=172.16.1.8/255.
  P1TICs2              [PC-PT]  (FastEthernet0=172.16.1.179/255.255.255.192,Bluetooth)
  I1AT1                [Printer-PT]  (FastEthernet0=172.16.1.9
  SW2-P1               [2960-24TT]  (Vlan1,FastEthernet0/1,FastEthernet0/2,FastEthernet0/3,FastEthernet0/4,FastEthernet0/5,FastEthernet0/6,FastEthernet0/7,FastEthernet0/8,FastEthernet0/9,FastEthernet0/10,FastEthernet0/11,FastEthernet0/12,FastEthernet0/13,FastEthernet0/14,FastEthernet0/15,FastEthernet0/16,FastEthernet0/17,FastEthernet0/18,FastEthernet0/19,FastEthernet0/20,FastEthernet0/21,FastEthernet0/22,FastEthernet0/23,FastEthernet0/24,GigabitEthernet0/1,GigabitEthernet0/2)
  IP Phone0            [7960]  (Vlan1,Switch,PC,Vlan50=172.16.
  IP Phone1            [7960]  (Vlan1,Switch,PC,Vlan50=172.16.2.12/255.255.255.224)
  IP Phone2            [7960]  (Vlan1,Switch,PC,Vlan50=172.16.2.28/255.255.255.224)
  IP Phone3            [7960]  (Vlan1,Switch,PC,Vlan50=172.16.2.8/255.255.255.224)
  IP Phone4            [7960]  (Vlan1,Switch,PC,Vlan50=172.16.2.19/255.255.255.224)
  IP Phone5            [7960]  (Vlan1,Switch,PC,Vlan50=172.16.2.17/255.255.255.224)
  IP Phone6            [7960]  (Vlan1,Switch,PC,Vlan50=172.16.2.7/255.255.255.224)
  IP Phone7            [7960]  (Vlan1,Switch,PC,Vlan50=172.16.2.3/255.255.255.224)
  IP Phone8            [7960]  (Vlan1,Switch,PC,Vlan50=172.16.2.13/255.255.255.224)
  IP Phone9            [7960]  (Vlan1,Switch,PC,Vlan50=172.16.2.11/255.255.255.224)
  IP Phone10           [7960]  (Vlan1,Switch,PC,Vlan50=172.16.2.5/255.255.255.224)
  IP Phone11           [7960]  (Vlan1,Switch,PC,Vlan50=172.16.2.15/255.255.255.224)
  IP Phone12           [7960]  (Vlan1,Switch,PC,Vlan50=172.16.2.14/255.255.255.224)
  IP Phone13           [7960]  (Vlan1,Switch,PC,Vlan50=172.16.2.30/255.255.255.224)
  IP Phone14           [7960]  (Vlan1,Switch,PC,Vlan55=172.16.2.38/255.255.255.224)
  IP Phone15           [7960]  (Vlan1,Switch,PC,Vlan50=172.16.2.25/255.255.255.224)
  IP Phone16           [7960]  (Vlan1,Switch,PC,Vlan50=172.16.2.16/255.255.255.224)
  I1AT2                [Printer-PT]  (FastEthernet0=172.16.1.94/255.255.255.224)
  P1APAT1              [AccessPoint-PT]  (Port 1,Port 0)
  AP1Cl                [AccessPoint-PT]  (Port 1,Port 0)
  IoT5                 [Smoke Detector]  (FastEthernet0=172.16th)
  IoT6                 [Smoke Detector]  (FastEthernet0=172.16.3.15/255.255.255.128,Bluetooth)
  IoT7                 [Smoke Detector]  (FastEthernet0=172.16.3.14/255.255.255.128,Bluetooth)
  IoT8                 [Smoke Detector]  (FastEthernet0=172.16.3.7/255.255.255.128,Bluetooth)
  IoT9                 [Smoke Detector]  (FastEthernet0=172.16th)Ethernet0/19,FastEthernet0/20,FastEthernet0/21,FastEthernet0/22,FastEthernet0/23,FastEthernet0/24,GigabitEthernet0/1,GigabitEthernet0/2)
  IoT16                [Webcam]  (FastEthernet0=172.16.3.46/255.255.255.128,Bluetooth)
  IoT17                [Webcam]  (FastEthernet0=172.16.3.45/255.255.255.128,Bluetooth)
  IoT18                [Webcam]  (FastEthernet0=172.16.3.44/255.255.255.128,Bluetooth)
  IoT19                [Webcam]  (FastEthernet0=172.16.3.43/255.255.255.128,Bluetooth)
  IoT20                [Webcam]  (FastEthernet0=172.16.3.42/255.255.255.128,Bluetooth)
  IoT21                [Webcam]  (FastEthernet0=172.16.3.41/255.255.255.128,Bluetooth)
  IoT22                [Webcam]  (FastEthernet0=172.16.3.40/255.255.255.128,Bluetooth)
  SW1-P3               [2960-24TT]  (Vlan1,FastEthernet0/1,FastEthernet0/2,FastEthernet0/3,FastEthernet0/4,FastEthernet0/5,FastEthernet0/6,FastEthernet0/7,FastEthernet0/8,FastEthernet0/9,FastEthernet0/10,FastEthernet0/11,FastEthernet0/12,FastEthernet0/13,FastEthernet0/14,FastEthernet0/15,FastEthernet0/16,FastEthernet0/17,FastEthernet0/18,FastEthernet0/19,FastEthernet0/20,FastEthernet0/21,FastEthernet0/22,FastEthernet0/23,FastEthernet0/24,GigabitEthernet0/1,GigabitEthernet0/2)
  P3CON1               [PC-PT]  (FastEthernet0=172.16.1.51/255.255.255.224,Bluetooth)
  P3CON2               [PC-PT]  (FastEthernet0=172.16.1.47/255.255.255.224,Bluetooth)
  P3CON3               [PC-PT]  (FastEthernet0=172.16.1.43/255.255.255.224,Bluetooth)
  P3CON4               [PC-PT]  (FastEthernet0=172.16.1.52/255.255.255.224,Bluetooth)
  P3CON5               [PC-PT]  (FastEthernet0=172.16.1.49/255.255.255.224,Bluetooth)
  P3RRHH3              [PC-PT]  (FastEthernet0=172.16.1.44/255
  P3RRHH1              [PC-PT]  (FastEthernet0=172.16.1.42/255
  P3CON6               [PC-PT]  (FastEthernet0=172.16.1.48/255.255.255.224,Bluetooth)
  P3GER3               [PC-PT]  (FastEthernet0=172.16.1.7/255.255.255.240,Bluetooth)
  P3TICs2              [PC-PT]  (FastEthernet0=172.16.1.165/255.255.255.192,Bluetooth)
  P3TICs6              [PC-PT]  (FastEthernet0=172.16.1.141/25
  P3TICs1              [PC-PT]  (FastEthernet0=172.16.1.174/255.255.255.192,Bluetooth)
  P3RRHH4              [PC-PT]  (FastEthernet0,Bluetooth)
  P3RRHH6              [PC-PT]  (FastEthernet0=172.16.1.46/255.255.255.224,Bluetooth)
  P3RRHH2              [PC-PT]  (FastEthernet0=172.16.1.50/255.255.255.224,Bluetooth)
  P3TICs4              [PC-PT]  (FastEthernet0=172.16.1.150/255.255.255.192,Bluetooth)
  P3TICs5              [PC-PT]  (FastEthernet0=172.16.1.164/255.255.255.192,Bluetooth)
  P3GER1               [PC-PT]  (FastEthernet0=172.16.1.5/255.255.255.240,Bluetooth)
  P3GER4               [PC-PT]  (FastEthernet0=172.16.1.3/255.255.255.240,Bluetooth)
  P3TICs3              [PC-PT]  (FastEthernet0=172.16.1.173/255.255.255.192,Bluetooth)
  P3RRHH5              [PC-PT]  (FastEthernet0,Bluetooth)
  P3GER2               [PC-PT]  (FastEthernet0=172.16.1.6/255.255.255.240,Bluetooth)
  P3GER5               [PC-PT]  (FastEthernet0=172.16.1.9/255.255.255.240,Bluetooth)
  SW2-P3               [2960-24TT]  (Vlan1,FastEthernet0/1,FastEthernet0/2,FastEthernet0/3,FastEthernet0/4,FastEthernet0/5,FastEthernet0/6,FastEthernet0/7,FastEthernet0/8,FastEthernet0/9,Fas
tEthernet0/10,FastEthernet0/11,FastEthernet0/12,FastEthernet0/net0/15,FastEthernet0/16,FastEthernet0/17,FastEthernet0/18,FastEthernet0/19,FastEthernet0/20,FastEthernet0/21,FastEthernet0/22,FastEthernet0/23,FastEthernet0/24,GigabitEthernet0/1,GigabitEthernet0/2)
  Proyector            [LCD]  (FastEthernet0=172.16.3.35/255.255.255.128)
  IP Phone17           [7960]  (Vlan1,Switch,PC,Vlan55=172.16.2.36/255.255.255.224)
  IP Phone18           [7960]  (Vlan1,Switch,PC,Vlan55=172.16.
  IP Phone19           [7960]  (Vlan1,Switch,PC,Vlan55=172.16.2.54/255.255.255.224)
  IP Phone20           [7960]  (Vlan1,Switch,PC,Vlan55=172.16.2.45/255.255.255.224)
  IP Phone21           [7960]  (Vlan1,Switch,PC,Vlan55=172.16.2.58/255.255.255.224)
  IP Phone22           [7960]  (Vlan1,Switch,PC,Vlan55=172.16.2.59/255.255.255.224)
  IP Phone23           [7960]  (Vlan1,Switch,PC,Vlan55=172.16.2.61/255.255.255.224)
  IP Phone24           [7960]  (Vlan1,Switch,PC,Vlan55)
  IP Phone25           [7960]  (Vlan1,Switch,PC,Vlan55=172.16.2.49/255.255.255.224)
  IP Phone26           [7960]  (Vlan1,Switch,PC,Vlan55=172.16.2.41/255.255.255.224)
  IP Phone27           [7960]  (Vlan1,Switch,PC,Vlan55=172.16.2.47/255.255.255.224)
  IP Phone28           [7960]  (Vlan1,Switch,PC,Vlan55=172.16.2.50/255.255.255.224)
  IP Phone29           [7960]  (Vlan1,Switch,PC,Vlan55=172.16.
  IP Phone30           [7960]  (Vlan1,Switch,PC,Vlan55=172.16.2.44/255.255.255.224)
  IP Phone31           [7960]  (Vlan1,Switch,PC,Vlan55=172.16.2.62/255.255.255.224)
  IP Phone32           [7960]  (Vlan1,Switch,PC,Vlan55=172.16.
  IP Phone33           [7960]  (Vlan1,Switch,PC,Vlan55=172.16.2.35/255.255.255.224)
  IP Phone34           [7960]  (Vlan1,Switch,PC,Vlan55=172.16.2.48/255.255.255.224)
  IP Phone35           [7960]  (Vlan1,Switch,PC,Vlan55=172.16.2.51/255.255.255.224)
  IP Phone36           [7960]  (Vlan1,Switch,PC,Vlan55=172.16.2.42/255.255.255.224)
  IP Phone37           [7960]  (Vlan1,Switch,PC,Vlan55=172.16.2.56/255.255.255.224)
  IP Phone38           [7960]  (Vlan1,Switch,PC,Vlan55=172.16.
  IP Phone39           [7960]  (Vlan1,Switch,PC,Vlan55=172.16.2.46/255.255.255.224)
  SW3-P3               [2960-24TT]
(Vlan1,FastEthernet0/1,FastEthernet0/2,FastEthernet0/3,FastEthEthernet0/6,FastEthernet0/7,FastEthernet0/8,FastEthernet0/9,FastEthernet0/10,FastEthernet0/11,FastEthernet0/12,FastEthernet0/13,FastEthernet0/14,FastEthernet0/15,FastEthernet0/16,FastEthernet0/17,FastEthernet0/18,Fast
Ethernet0/19,FastEthernet0/20,FastEthernet0/21,FastEthernet0/2et0/24,GigabitEthernet0/1,GigabitEthernet0/2)
  I3CON1               [Printer-PT]  (FastEthernet0=172.16.1.61/255.255.255.224)
  AP3G1                [AccessPoint-PT]  (Port 1,Port 0)
  AP3Cl1               [AccessPoint-PT]  (Port 1,Port 0)
  AP3Con1              [AccessPoint-PT]  (Port 1,Port 0)
  I3RRHH1              [Printer-PT]  (FastEthernet0=172.16.1.6
  IoT1                 [Smoke Detector]  (FastEthernet0=172.16.3.26/255.255.255.128,Bluetooth)
  IoT2                 [Smoke Detector]  (FastEthernet0=172.16.3.27/255.255.255.128,Bluetooth)
  IoT3                 [Smoke Detector]  (FastEthernet0=172.16.3.28/255.255.255.128,Bluetooth)
  IoT4                 [Smoke Detector]  (FastEthernet0=172.16.3.29/255.255.255.128,Bluetooth)
  IoT23                [Smoke Detector]  (FastEthernet0=172.16.3.30/255.255.255.128,Bluetooth)
  IoT24                [Smoke Detector]  (FastEthernet0=172.16.3.31/255.255.255.128,Bluetooth)
  IoT25                [Smoke Detector]  (FastEthernet0=172.16.3.32/255.255.255.128,Bluetooth)
  IoT26                [Webcam]  (FastEthernet0=172.16.3.57/255.255.255.128,Bluetooth)
  IoT27                [Webcam]  (FastEthernet0=172.16.3.54/255.255.255.128,Bluetooth)
  IoT28                [Webcam]  (FastEthernet0=172.16.3.55/255.255.255.128,Bluetooth)
  IoT29                [Webcam]  (FastEthernet0=172.16.3.56/255.255.255.128,Bluetooth)
  IoT30                [Webcam]  (FastEthernet0=172.16.3.58/255.255.255.128,Bluetooth)
  IoT31                [Webcam]  (FastEthernet0=172.16.3.59/255.255.255.128,Bluetooth)
  IoT32                [Webcam]  (FastEthernet0=172.16.3.60/255.255.255.128,Bluetooth)
  IoT35                [Smoke Detector]  (FastEthernet0=172.16.3.33/255.255.255.128,Bluetooth)
  IoT36                [Smoke Detector]  (FastEthernet0=172.16.3.34/255.255.255.128,Bluetooth)
  R-Sucursal           [2811]  (Vlan1,FastEthernet0/0,FastEthernet0/1,Serial0/3/0=172.16.250.6/255.255.255.252,Serial0/3/1=172.16.250.10/255.255.255.252,F
astEthernet1/0,FastEthernet0/0.12=172.16.20.1/255.255.255.240,17/255.255.255.240,FastEthernet0/0.52=172.16.20.33/255.255.255.240,FastEthernet0/0.62=172.16.20.65/255.255.255.224,FastEthernet0/0.72=172.16.20.97/255.255.255.240,FastEthernet0/0.199=172.16.20.113/255.255.255.240)
  SW-SUC-1             [2960-24TT](Vlan1,FastEthernet0/1,FastEthernet0/2,FastEthernet0/3,FastEthernet0/4,FastEthernet0/5,FastEthernet0/6,FastEthernet0/7,FastEthernet0/8,FastEthernet0/9,FastEthernet0/10,FastEthernet0/11,FastEthernet0/12,FastEthernet0/13,FastEthernet0/14,FastEthernet0/15,FastEthernet0/16,FastEthernet0/17,FastEthernet0/18,FastEthernet0/19,FastEthernet0/20,FastEthernet0/21,FastEthernet0/22,FastEthernet0/23,FastEthernet0/24,GigabitEthernet0/1,GigabitEthernet0/2)
  Power Distribution Device1 [Power Distribution Device]
  SPCRE2               [PC-PT]  (FastEthernet0=172.16.20.2/255
  SPCAJ1               [PC-PT]  (FastEthernet0=172.16.20.6/255.255.255.240,Bluetooth)
  SPCAJ2               [PC-PT]  (FastEthernet0=172.16.20.8/255.255.255.240,Bluetooth)
  SPTICs1              [PC-PT]  (FastEthernet0=172.16.20.18/255.255.255.240,Bluetooth)
  SPTICs2              [PC-PT]  (FastEthernet0=172.16.20.20/255.255.255.240,Bluetooth)
  SBOD                 [PC-PT]  (FastEthernet0=172.16.20.19/255.255.255.240,Bluetooth)
  SPCRE1               [PC-PT]  (FastEthernet0=172.16.20.7/255.255.255.240,Bluetooth)
  IP Phone40           [7960]  (Vlan1,Switch,PC,Vlan52=172.16.20.35/255.255.255.240)
  IP Phone41           [7960]  (Vlan1,Switch,PC,Vlan52=172.16.20.38/255.255.255.240)
  IP Phone42           [7960]  (Vlan1,Switch,PC,Vlan52=172.16.20.39/255.255.255.240)
  IP Phone43           [7960]  (Vlan1,Switch,PC,Vlan52=172.16.20.34/255.255.255.240)
  IP Phone44           [7960]  (Vlan1,Switch,PC,Vlan52=172.16.20.37/255.255.255.240)
  IP Phone45           [7960]  (Vlan1,Switch,PC,Vlan52=172.16.20.36/255.255.255.240)
  IP Phone46           [7960]  (Vlan1,Switch,PC,Vlan52=172.16.20.40/255.255.255.240)
  IoT0                 [Smoke Detector]  (FastEthernet0=172.16.20.68/255.255.255.224,Bluetooth)
  IoT33                [Smoke Detector]  (FastEthernet0=172.16.20.69/255.255.255.224,Bluetooth)
  IoT34                [Smoke Detector]  (FastEthernet0=172.16.20.70/255.255.255.224,Bluetooth)
  IoT37                [Smoke Detector]  (FastEthernet0=172.16.20.71/255.255.255.224,Bluetooth)
  IoT38                [Smoke Detector]  (FastEthernet0=172.16oth)
  IoT39                [Motion Detector]  (FastEthernet0=172.16.20.66/255.255.255.224,Bluetooth)
  IoT41                [Temperature Sensor]  (FastEthernet0=172.16.20.67/255.255.255.224)
  SAPCaj               [AccessPoint-PT]  (Port 1,Port 0)
  SAPVIS               [AccessPoint-PT]  (Port 1,Port 0)
  SW-SUC-2             [2960-24TT]  (Vlan1,FastEthernet0/1,FastEthernet0/2,FastEthernet0/3,FastEthernet0/4,FastEthernet0/5,FastEthernet0/6,FastEthernet0/7,FastEthernet0/8,FastEthernet0/9,FastEthernet0/10,FastEthernet0/11,FastEthernet0/12,FastEthernet0/13,FastEthernet0/14,FastEthernet0/15,FastEthernet0/16,FastEthernet0/17,FastEthernet0/18,FastEthernet0/19,FastEthernet0/20,FastEthernet0/21,FastEthernet0/22,FastEthernet0/23,FastEthernet0/24,GigabitEthernet0/1,GigabitEthernet0/2)
  SAPTICs              [AccessPoint-PT]  (Port 1,Port 0)
5                [Webcam]  (FastEthernet0=172.16.20.83/255.255.255.224,Bluetooth)
  IoT46                [Webcam]  (FastEthernet0=172.16.20.81/255.255.255.224,Bluetooth)
  IoT47                [Webcam]  (FastEthernet0=172.16.20.80/255.255.255.224,Bluetooth)
  IoT48                [Webcam]  (FastEthernet0=172.16.20.75/255.255.255.224,Bluetooth)
  IoT49                [Webcam]  (FastEthernet0=172.16.20.76/255.255.255.224,Bluetooth)
  IoT51                [Webcam]  (FastEthernet0=172.16.20.77/255.255.255.224,Bluetooth)
  IoT52                [Webcam]  (FastEthernet0=172.16.20.79/255.255.255.224,Bluetooth)
  IoT50                [Webcam]  (FastEthernet0=172.16.20.78/255.255.255.224,Bluetooth)
  IoT1(2)              [Smoke Detector]  (FastEthernet0=172.16.3.17/255.255.255.128,Bluetooth)
  IoT0(1)              [Webcam]  (FastEthernet0=172.16.3.48/255.255.255.128,Bluetooth)
  IoT1(1)              [Smoke Detector]  (FastEthernet0=172.16.3.18/255.255.255.128,Bluetooth)
  P2TICs5              [PC-PT]  (FastEthernet0=172.16.1.176/255.255.255.192,Bluetooth)
  P3INN8               [PC-PT]  (FastEthernet0=172.16.1.180/255.255.255.192,Bluetooth)
  P3INN15              [PC-PT]  (FastEthernet0=172.16.1.145/255.255.255.192,Bluetooth)
  P3INN14              [PC-PT]  (FastEthernet0=172.16.1.153/255.255.255.192,Bluetooth)
  P3INN5               [PC-PT]  (FastEthernet0=172.16.1.148/255.255.255.192,Bluetooth)
  P3INN16              [PC-PT]  (FastEthernet0=172.16.1.144/255.255.255.192,Bluetooth)
  P3INN18              [PC-PT]  (FastEthernet0=172.16.1.170/255.255.255.192,Bluetooth)
  P3INN13              [PC-PT]  (FastEthernet0=172.16.1.166/255.255.255.192,Bluetooth)
  P3INN17              [PC-PT]  (FastEthernet0=172.16.1.169/255.255.255.192,Bluetooth)
  P2TICs3              [PC-PT]  (FastEthernet0=172.16.1.146/255.255.255.192,Bluetooth)
  IoT2(1)              [Smoke Detector]  (FastEthernet0=172.16.3.25/255.255.255.128,Bluetooth)
  Power Distribution Device2 [Power Distribution Device]
  P2TICs4              [PC-PT]  (FastEthernet0=172.16.1.178/25
  P3INN4               [PC-PT]  (FastEthernet0=172.16.1.135/255.255.255.192,Bluetooth)
  P2MON2               [PC-PT]  (FastEthernet0=172.16.1.168/255.255.255.192,Bluetooth)
  P2MON1               [PC-PT]  (FastEthernet0=172.16.1.160/25
  P3INN1               [PC-PT]  (FastEthernet0=172.16.1.140/255.255.255.192,Bluetooth)
  P3INN3               [PC-PT]  (FastEthernet0=172.16.1.133/255.255.255.192,Bluetooth)
  P2TICs1              [PC-PT]  (FastEthernet0,Bluetooth)
  P3INN7               [PC-PT]  (FastEthernet0=172.16.1.143/255.255.255.192,Bluetooth)
  P2TICs2              [PC-PT]  (FastEthernet0=172.16.1.138/255.255.255.192,Bluetooth)
  P3INN20              [PC-PT]  (FastEthernet0=172.16.1.177/25
  P3INN2               [PC-PT]  (FastEthernet0=172.16.1.172/255.255.255.192,Bluetooth)
  IP Phone24(1)        [7960]  (Vlan1,Switch,PC,Vlan50=172.16.2.23/255.255.255.224)
  IP Phone19(1)        [7960]  (Vlan1,Switch,PC,Vlan50=172.16.
  IP Phone22(1)        [7960]  (Vlan1,Switch,PC,Vlan55=172.16.2.43/255.255.255.224)
  IP Phone23(1)        [7960]  (Vlan1,Switch,PC,Vlan55=172.16.
  IP Phone30(1)        [7960]  (Vlan1,Switch,PC,Vlan50=172.16.2.4/255.255.255.224)
  IP Phone20(1)        [7960]  (Vlan1,Switch,PC,Vlan55=172.16.2.40/255.255.255.224)
  IP Phone33(1)        [7960]  (Vlan1,Switch,PC,Vlan50=172.16.2.24/255.255.255.224)
  IP Phone21(1)        [7960]  (Vlan1,Switch,PC,Vlan50=172.16.2.27/255.255.255.224)
  IP Phone27(1)        [7960]  (Vlan1,Switch,PC,Vlan50=172.16.
  IP Phone25(1)        [7960]  (Vlan1,Switch,PC,Vlan55=172.16.2.37/255.255.255.224)
  IP Phone31(1)        [7960]  (Vlan1,Switch,PC,Vlan55=172.16.2.52/255.255.255.224)
  IP Phone32(1)        [7960]  (Vlan1,Switch,PC,Vlan50=172.16.2.10/255.255.255.224)
  IP Phone29(1)        [7960]  (Vlan1,Switch,PC,Vlan50=172.16.2.26/255.255.255.224)
  IP Phone26(1)        [7960]  (Vlan1,Switch,PC,Vlan50=172.16.2.21/255.255.255.224)
  IP Phone34(1)        [7960]  (Vlan1,Switch,PC,Vlan50=172.16.2.6/255.255.255.224)
  P3INN19              [PC-PT]  (FastEthernet0=172.16.1.182/255.255.255.192,Bluetooth)
  P3INN12              [PC-PT]  (FastEthernet0=172.16.1.142/255.255.255.192,Bluetooth)
  P3INN6               [PC-PT]  (FastEthernet0=172.16.1.181/255.255.255.192,Bluetooth)
  P3INN10              [PC-PT]  (FastEthernet0,Bluetooth)
  P3INN9               [PC-PT]  (FastEthernet0,Bluetooth)
  P3INN11              [PC-PT]  (FastEthernet0=172.16.1.167/255.255.255.192,Bluetooth)
  IoT29(1)             [Smoke Detector]  (FastEthernet0=172.16.3.24/255.255.255.128,Bluetooth)
  IoT30(1)             [Smoke Detector]  (FastEthernet0=172.16.3.23/255.255.255.128,Bluetooth)
  IoT4(1)              [Webcam]  (FastEthernet0=172.16.3.49/255.255.255.128,Bluetooth)
  IoT3(1)              [Webcam]  (FastEthernet0=172.16.3.47/255.255.255.128,Bluetooth)
  IoT27(1)             [Webcam]  (FastEthernet0=172.16.3.53/255.255.255.128,Bluetooth)
  IoT24(1)             [Webcam]  (FastEthernet0=172.16.3.52/255.255.255.128,Bluetooth)
  IoT23(1)             [Webcam]  (FastEthernet0=172.16.3.50/255.255.255.128,Bluetooth)
  IoT25(1)             [Webcam]  (FastEthernet0=172.16.3.51/255.255.255.128,Bluetooth)
  IoT28(1)             [Smoke Detector]  (FastEthernet0=172.16th)
  SW3-P2               [2960-24TT]  (Vlan1,FastEthernet0/1,FastEthernet0/2,FastEthernet0/3,FastEthernet0/4,FastEthernet0/5,FastEthernet0/6,FastEthernet0/7,FastEthernet0/8,FastEthernet0/9,FastEthernet0/10,FastEthernet0/11,FastEthernet0/12,FastEthernet0/13,FastEthernet0/14,FastEthernet0/15,FastEthernet0/16,FastEthernet0/17,FastEthernet0/18,Fast
Ethernet0/19,FastEthernet0/20,FastEthernet0/21,FastEthernet0/2et0/24,GigabitEthernet0/1,GigabitEthernet0/2)
  SW2-P2               [2960-24TT]  (Vlan1,FastEthernet0/1,FastEthernet0/2,FastEthernet0/3,FastEthernet0/4,FastEthernet0/5,FastEthernet0/6,FastEthernet0/7,FastEthernet0/8,FastEthernet0/9,FastEthernet0/10,FastEthernet0/11,FastEthernet0/12,FastEthernet0/13,FastEthernet0/14,FastEthernet0/15,FastEthernet0/16,FastEthernet0/17,FastEthernet0/18,FastEthernet0/19,FastEthernet0/20,FastEthernet0/21,FastEthernet0/22,FastEthernet0/23,FastEthernet0/24,GigabitEthernet0/1,GigabitEthernet0/2)
  SW1-P2               [2960-24TT]  (Vlan1,FastEthernet0/1,FastEthernet0/2,FastEthernet0/3,FastEthernet0/4,FastEthernet0/5,FastEthernet0/6,FastEthernet0/7,FastEthernet0/8,FastEthernet0/9,FastEthernet0/10,FastEthernet0/11,FastEthernet0/12,FastEthernet0/13,FastEthernet0/14,FastEthernet0/15,FastEthernet0/16,FastEthernet0/17,FastEthernet0/18,FastEthernet0/19,FastEthernet0/20,FastEthernet0/21,FastEthernet0/22,FastEthernet0/23,FastEthernet0/24,GigabitEthernet0/1,GigabitEthernet0/2)
  SW-CORE              [3650-24PS]  (Vlan1,GigabitEthernet1/0/1,GigabitEthernet1/0/2,GigabitEthernet1/0/3,GigabitEthernet1/0/4,GigabitEthernet1/0/5,GigabitEthernet1/0/6,GigabitEthernet1/0/7,GigabitEthernet1/0/8,GigabitEthernet1/0/9,GigabitEthernet1/0/10,GigabitEthernet1/0/11,GigabitEthernet1/0/12,GigabitEthernet1/0/13,GigabitEthernet1/0/14,GigabitEthernet1/0/15,GigabitEthernet1/0/16,GigabitEthernet1/0/17,GigabitEthernet1/0/18,GigabitEthernet1/0/19,GigabitEthernet1/0/20,GigabitEthernet1/0/21,GigabitEthernet1/0/22,GigabitEthernet1/0/23,GigabitEthernet1/0/24,GigabitEthernet1/1/1,GigabitEthernet1/1/2,GigabitEthernet1/1/3,GigabitEthernet1/1/4,Vlan55=172.16.2.34/255.255.255.224,Vlan99=172.16.0.2/255.255.255.240)
  R-Matriz             [2811]  (Vlan1,FastEthernet0/0,FastEthernet0/1,Serial0/3/0=172.16.250.1/255.255.255.252,Serial0/3/1=172.16.250.5/255.255.255.252,FastEthernet1/0,FastEthernet0/0.10=172.16.1.1/255.255.255.240,FastEthernet0/0.20=172.16.1.33/255.255.255.224,FastEthernet0/0.30=172.16.1.65/255.255.255.224,
FastEthernet0/0.40=172.16.1.129/255.255.255.192,FastEthernet0/24,FastEthernet0/0.60=172.16.3.1/255.255.255.128,FastEthernet0/0.70=172.16.4.1/255.255.255.240,FastEthernet0/0.99=172.16.0.1/255.255.255.240,FastEthernet0/0.100=172.16.100.1/255.255.255.240)
  SW-CORE-S            [2960-24TT]  (Vlan1,FastEthernet0/1,FastEthernet0/2,FastEthernet0/3,FastEthernet0/4,FastEthernet0/5,FastEthernet0/6,FastEthernet0/7,FastEthernet0/8,FastEthernet0/9,Fas
tEthernet0/10,FastEthernet0/11,FastEthernet0/12,FastEthernet0/net0/15,FastEthernet0/16,FastEthernet0/17,FastEthernet0/18,FastEthernet0/19,FastEthernet0/20,FastEthernet0/21,FastEthernet0/22,FastEthernet0/23,FastEthernet0/24,GigabitEthernet0/1,GigabitEthernet0/2)
  Switch15 ADMIN       [2960-24TT]  (Vlan1,FastEthernet0/1,FastEthernet0/2,FastEthernet0/3,FastEthernet0/4,FastEthernet0/5,FastEthernet0/6,FastEthernet0/7,FastEthernet0/8,FastEthernet0/9,FastEthernet0/10,FastEthernet0/11,FastEthernet0/12,FastEthernet0/13,FastEthernet0/14,FastEthernet0/15,FastEthernet0/16,FastEthernet0/17,FastEthernet0/18,FastEthernet0/19,FastEthernet0/20,FastEthernet0/21,FastEthernet0/22,FastEthernet0/23,FastEthernet0/24,GigabitEthernet0/1,GigabitEthernet0/2)
  Switch16 NAVE        [2960-24TT]  (Vlan1,FastEthernet0/1,FastEthernet0/2,FastEthernet0/3,FastEthernet0/4,FastEthernet0/5,FastEthernet0/6,FastEthernet0/7,FastEthernet0/8,FastEthernet0/9,FastEthernet0/10,FastEthernet0/11,FastEthernet0/12,FastEthernet0/13,FastEthernet0/14,FastEthernet0/15,FastEthernet0/16,FastEthernet0/17,FastEthernet0/18,FastEthernet0/19,FastEthernet0/20,FastEthernet0/21,FastEthernet0/22,FastEthernet0/23,FastEthernet0/24,GigabitEthernet0/1,GigabitEthernet0/2)
  Switch17 SEGURIDAD   [2960-24TT]  (Vlan1,FastEthernet0/1,FastEthernet0/2,FastEthernet0/3,FastEthernet0/4,FastEthernet0/5,FastEthernet0/6,FastEthernet0/7,FastEthernet0/8,FastEthernet0/9,FastEthernet0/10,FastEthernet0/11,FastEthernet0/12,FastEthernet0/13,FastEthernet0/14,FastEthernet0/15,FastEthernet0/16,FastEthernet0/17,FastEthernet0/18,FastEthernet0/19,FastEthernet0/20,FastEthernet0/21,FastEthernet0/22,FastEthernet0/23,FastEthernet0/24,GigabitEthernet0/1,GigabitEthernet0/2)
  FOFI1                [PC-PT]  (FastEthernet0=172.16.10.6/255.255.255.240,Bluetooth)
  FOFI2                [PC-PT]  (FastEthernet0=172.16.10.7/255
  FOFI3                [PC-PT]  (FastEthernet0=172.16.10.4/255.255.255.240,Bluetooth)
  FOFI4                [PC-PT]  (FastEthernet0=172.16.10.2/255.255.255.240,Bluetooth)
  FOFI5                [PC-PT]  (FastEthernet0=172.16.10.5/255.255.255.240,Bluetooth)
  FOFI6                [PC-PT]  (FastEthernet0=172.16.10.3/255.255.255.240,Bluetooth)
  FENF1                [PC-PT]  (FastEthernet0=172.16.10.19/255.255.255.240,Bluetooth)
  FBOD1                [PC-PT]  (FastEthernet0=172.16.10.21/25
  FSEC1                [PC-PT]  (FastEthernet0=172.16.10.18/255.255.255.240,Bluetooth)
  IP Phone47           [7960]  (Vlan1,Switch,PC,Vlan51=172.16.10.38/255.255.255.224)
  IP Phone48           [7960]  (Vlan1,Switch,PC,Vlan51=172.16.
  IP Phone49           [7960]  (Vlan1,Switch,PC,Vlan51=172.16.10.34/255.255.255.224)
  IP Phone50           [7960]  (Vlan1,Switch,PC,Vlan51=172.16.10.40/255.255.255.224)
  IP Phone51           [7960]  (Vlan1,Switch,PC,Vlan51=172.16.
  IP Phone52           [7960]  (Vlan1,Switch,PC,Vlan51=172.16.10.41/255.255.255.224)
  IP Phone53           [7960]  (Vlan1,Switch,PC,Vlan51=172.16.10.37/255.255.255.224)
  IP Phone54           [7960]  (Vlan1,Switch,PC,Vlan51=172.16.10.35/255.255.255.224)
  I1OFI                [Printer-PT]  (FastEthernet0=172.16.10.14/255.255.255.240)
  FAP1EMPL             [AccessPoint-PT]  (Port 1,Port 0)
  FAP2EMPLE            [AccessPoint-PT]  (Port 1,Port 0)
  FAPINV1              [AccessPoint-PT]  (Port 1,Port 0)
(2)(5)           [Smoke Detector]  (FastEthernet0=172.16.10.66/255.255.255.192,Bluetooth)
  IoT110               [RFID Reader]  (FastEthernet0=172.16.10.74/255.255.255.192)
  IoT111               [RFID Reader]  (FastEthernet0=172.16.10.73/255.255.255.192)
  IoT112               [Webcam]  (FastEthernet0=172.16.10.94/255.255.255.192,Bluetooth)
  IoT113               [Webcam]  (FastEthernet0=172.16.10.90/255.255.255.192,Bluetooth)
  APSEC1               [AccessPoint-PT]  (Port 1,Port 0)
  IoT0(2)(5)(1)        [Smoke Detector]  (FastEthernet0=172.16.10.87/255.255.255.192,Bluetooth)
  IoT0(2)(5)(2)        [Smoke Detector]  (FastEthernet0=172.16.10.85/255.255.255.192,Bluetooth)
  IoT0(2)(5)(2)(1)     [Smoke Detector]  (FastEthernet0=172.16.10.84/255.255.255.192,Bluetooth)
  IoT0(2)(5)(2)(2)     [Smoke Detector]  (FastEthernet0=172.16.10.83/255.255.255.192,Bluetooth)
  IoT0(2)(5)(2)(3)     [Smoke Detector]  (FastEthernet0=172.16.10.82/255.255.255.192,Bluetooth)
  IoT0(2)(5)(2)(4)     [Smoke Detector]  (FastEthernet0=172.16.10.81/255.255.255.192,Bluetooth)
  IoT0(2)(5)(2)(5)     [Smoke Detector]  (FastEthernet0=172.16.10.80/255.255.255.192,Bluetooth)
  IoT0(2)(5)(2)(6)     [Smoke Detector]  (FastEthernet0=172.16.10.79/255.255.255.192,Bluetooth)
  IoT0(2)(5)(2)(7)     [Smoke Detector]  (FastEthernet0=172.16.10.78/255.255.255.192,Bluetooth)
  IoT0(2)(5)(2)(8)     [Smoke Detector]  (FastEthernet0=172.16.10.77/255.255.255.192,Bluetooth)
  IoT33(1)(1)          [Humidity Monitor]  (FastEthernet0=172.16.10.72/255.255.255.192,Bluetooth)
  R-Fabrica            [2811]  (Vlan1,FastEthernet0/0,FastEthernet0/1,Serial0/3/0=172.16.250.2/255.255.255.252,Serial0/3/1=172.16.250.9/255.255.255.252,FastEthernet1/0,FastEthernet0/0.11=172.16.10.1/255.255.255.240,FastEthernet0/0.12,FastEthernet0/0.21=172.16.10.17/255.255.255.240,FastEthernet0/0.22,FastEthernet0/0.51=172.16.10.33/255.255.255.224,FastEthernet0/0.52,FastEthernet0/0.61=172.16.10.65/255.255.255.192,FastEthernet0/0.71=172.16.10.129/255.255.255.240,FastEthernet0/0.72,FastEthernet0/0.81=172.16.10.145/255.255.255.240,FastEthernet0/0.299=172.16.10.161/255.255.255.240)
  IoT24(2)             [Motion Detector]  (FastEthernet0=172.16.3.20/255.255.255.128,Bluetooth)
  IoT56                [RFID Reader]  (FastEthernet0=172.16.3.
  IoT58                [Temperature Monitor]  (FastEthernet0=172.16.3.21/255.255.255.128,Bluetooth)
  IoT61                [RFID Reader]  (FastEthernet0=172.16.3.9/255.255.255.128)
  IoT63                [RFID Reader]  (FastEthernet0=172.16.3.10/255.255.255.128)
  IoT64                [RFID Reader]  (FastEthernet0=172.16.3.11/255.255.255.128)
  IoT65                [Humiture Monitor]  (FastEthernet0=172.16.3.8/255.255.255.128,Bluetooth)
  IoT66                [Motion Detector]  (FastEthernet0=172.16.3.36/255.255.255.128,Bluetooth)
  IoT68                [Temperature Monitor]  (FastEthernet0=172.16.3.37/255.255.255.128,Bluetooth)
  IoT69                [RFID Reader]  (FastEthernet0=172.16.3.
l-Server         [Server-PT]  (FastEthernet0=172.16.100.4/255.255.255.240)
  Servidor DB          [Server-PT]  (FastEthernet0=172.16.100.8/255.255.255.240)
  IoT-server           [Server-PT]  (FastEthernet0=172.16.100.5/255.255.255.240)
  Servidor-Apps        [Server-PT]  (FastEthernet0=172.16.100.7/255.255.255.240)
  Power Distribution Device5 [Power Distribution Device]
  IoT41(1)             [Temperature Sensor]  (FastEthernet0=172.16.10.76/255.255.255.192)
  IoT0(2)(5)(2)(9)     [Smoke Detector]  (FastEthernet0=172.16.10.86/255.255.255.192,Bluetooth)
  AP1EMPL1             [AccessPoint-PT]  (Port 1,Port 0)
  APCON1               [AccessPoint-PT]  (Port 1,Port 0)
  AP2EMPLE2            [AccessPoint-PT]  (Port 1,Port 0)
  AP2EMPLE1            [AccessPoint-PT]  (Port 1,Port 0)
  IoT113(1)            [Webcam]  (FastEthernet0=172.16.10.93/255.255.255.192,Bluetooth)
  IoT113(2)            [Webcam]  (FastEthernet0=172.16.10.92/255.255.255.192,Bluetooth)
  IoT113(3)            [Webcam]  (FastEthernet0=172.16.10.88/255.255.255.192,Bluetooth)
  IoT113(4)            [Webcam]  (FastEthernet0=172.16.10.89/255.255.255.192,Bluetooth)
  IoT113(5)            [Webcam]  (FastEthernet0=172.16.10.91/255.255.255.192,Bluetooth)
  IoT113(6)            [Webcam]  (FastEthernet0=172.16.10.98/255.255.255.192,Bluetooth)
  IoT113(7)            [Webcam]  (FastEthernet0=172.16.10.97/255.255.255.192,Bluetooth)
  IoT113(8)            [Webcam]  (FastEthernet0=172.16.10.96/255.255.255.192,Bluetooth)
  IoT113(9)            [Webcam]  (FastEthernet0=172.16.10.95/255.255.255.192,Bluetooth)
  Server VOZ           [2811]  (Vlan1,FastEthernet0/0=172.16.2.33/255.255.255.224,FastEthernet0/1,FastEthernet0/0.55)
  IoT41(2)             [Temperature Sensor]  (FastEthernet0=172.16.20.86/255.255.255.224)

3. pt_export_topology (complete, 1,404 lines)

=== Topology Export: 323 devices, 333 links ===

  SW1-P1 [2960-24TT] @ (1042, 1153)
    FastEthernet0/1 [linked]
    FastEthernet0/2 [linked]
    FastEthernet0/3 [linked]
    FastEthernet0/4 [linked]
    FastEthernet0/5 [linked]
    FastEthernet0/6 [linked]
    FastEthernet0/7 [linked]
    FastEthernet0/8 [linked]
    FastEthernet0/9 [linked]
    FastEthernet0/10 [linked]
    FastEthernet0/11 [linked]
    FastEthernet0/12 [linked]
    FastEthernet0/13 [linked]
    FastEthernet0/14 [linked]
    FastEthernet0/15 [linked]
    FastEthernet0/16 [linked]
    FastEthernet0/17 [linked]
    FastEthernet0/18 [linked]
    FastEthernet0/19 [linked]
    FastEthernet0/20 [linked]
    FastEthernet0/21 [linked]
    FastEthernet0/22 [linked]
    FastEthernet0/23 [linked]
    FastEthernet0/24 [linked]
    GigabitEthernet0/1 [linked]
  Power Distribution Device0 [Power Distribution Device] @ (3892, 3885)
  P1AT11 [PC-PT] @ (1008, 997)
    FastEthernet0 IP=172.16.1.73/255.255.255.224 [linked]
  P1AT9 [PC-PT] @ (1301, 1229)
    FastEthernet0 IP=172.16.1.81/255.255.255.224 [linked]
  P1AT7 [PC-PT] @ (1242, 1297)
    FastEthernet0 IP=172.16.1.85/255.255.255.224 [linked]
  P1AT5 [PC-PT] @ (1066, 1292)
    FastEthernet0 IP=172.16.1.88/255.255.255.224 [linked]
  P1AT4 [PC-PT] @ (1007, 1293)
    FastEthernet0 IP=172.16.1.77/255.255.255.224 [linked]
  P1TICs3 [PC-PT] @ (764, 1293)
    FastEthernet0 IP=172.16.1.147/255.255.255.192 [linked]
  P1AT13 [PC-PT] @ (1069, 1002)
    FastEthernet0 IP=172.16.1.83/255.255.255.224 [linked]
  P1CREDITO1 [PC-PT] @ (769, 995)
    FastEthernet0 IP=172.16.1.175/255.255.255.192 [linked]
  P1AT10 [PC-PT] @ (1298, 1301)
    FastEthernet0 [linked]
  P1AT8 [PC-PT] @ (1184, 1297)
    FastEthernet0 IP=172.16.1.89/255.255.255.224 [linked]
  P1AT6 [PC-PT] @ (1123, 1292)
    FastEthernet0 IP=172.16.1.74/255.255.255.224 [linked]
  P1AT1 [PC-PT] @ (829, 1291)
    FastEthernet0 IP=172.16.1.90/255.255.255.224 [linked]
  P1TICs1 [PC-PT] @ (761, 1218)
    FastEthernet0 IP=172.16.1.171/255.255.255.192 [linked]
  P1CREDITO2 [PC-PT] @ (932, 994)
    FastEthernet0 IP=172.16.1.152/255.255.255.192 [linked]
  P1AT12 [PC-PT] @ (1298, 1151)
    FastEthernet0 IP=172.16.1.86/255.255.255.224 [linked]
  P1TICs4 [PC-PT] @ (765, 1070)
    FastEthernet0 IP=172.16.1.159/255.255.255.192 [linked]
  P1AT3 [PC-PT] @ (886, 1292)
    FastEthernet0 IP=172.16.1.87/255.255.255.224 [linked]
  PT1AT2 [PC-PT] @ (946, 1292)
    FastEthernet0 IP=172.16.1.80/255.255.255.224 [linked]
  P1AT14 [PC-PT] @ (1299, 1082)
    FastEthernet0 IP=172.16.1.84/255.255.255.224 [linked]
  P1GERENCIA [PC-PT] @ (851, 992)
    FastEthernet0 IP=172.16.1.8/255.255.255.240 [linked]
  P1TICs2 [PC-PT] @ (767, 1147)
    FastEthernet0 IP=172.16.1.179/255.255.255.192 [linked]
  I1AT1 [Printer-PT] @ (1215, 1012)
    FastEthernet0 IP=172.16.1.93/255.255.255.224 [linked]
  SW2-P1 [2960-24TT] @ (1379, 657)
    FastEthernet0/1 [linked]
tEthernet0/4 [linked]
    FastEthernet0/5 [linked]
    FastEthernet0/6 [linked]
    FastEthernet0/7 [linked]
    FastEthernet0/8 [linked]
    FastEthernet0/9 [linked]
    FastEthernet0/10 [linked]
    FastEthernet0/11 [linked]
    FastEthernet0/12 [linked]
    FastEthernet0/13 [linked]
    FastEthernet0/14 [linked]
    FastEthernet0/15 [linked]
    FastEthernet0/16 [linked]
    FastEthernet0/17 [linked]
    FastEthernet0/18 [linked]
    FastEthernet0/20 [linked]
    FastEthernet0/21 [linked]
    FastEthernet0/22 [linked]
    FastEthernet0/23 [linked]
    FastEthernet0/24 [linked]
    GigabitEthernet0/2 [linked]
  IP Phone0 [7960] @ (1613, 659)
    Switch [linked]
    Vlan50 IP=172.16.2.9/255.255.255.224
  IP Phone1 [7960] @ (1620, 586)
    Switch [linked]
    Vlan50 IP=172.16.2.12/255.255.255.224
  IP Phone2 [7960] @ (1621, 509)
    Switch [linked]
n50 IP=172.16.2.8/255.255.255.224
  IP Phone4 [7960] @ (1553, 428)
    Switch [linked]
    Vlan50 IP=172.16.2.19/255.255.255.224
  IP Phone5 [7960] @ (1486, 429)
    Switch [linked]
    Vlan50 IP=172.16.2.17/255.255.255.224
  IP Phone6 [7960] @ (1426, 427)
    Switch [linked]
    Vlan50 IP=172.16.2.7/255.255.255.224
  IP Phone7 [7960] @ (1361, 426)
    Switch [linked]
    Vlan50 IP=172.16.2.3/255.255.255.224
  IP Phone8 [7960] @ (1453, 872)
    Switch [linked]
    Vlan50 IP=172.16.2.13/255.255.255.224
  IP Phone9 [7960] @ (1141, 572)
    Switch [linked]
    Vlan50 IP=172.16.2.11/255.255.255.224
  IP Phone10 [7960] @ (1294, 426)
    Switch [linked]
    Vlan50 IP=172.16.2.5/255.255.255.224
  IP Phone11 [7960] @ (1146, 499)
    Switch [linked]
    Vlan50 IP=172.16.2.15/255.255.255.224
  IP Phone12 [7960] @ (1599, 874)
    Switch [linked]
    Vlan50 IP=172.16.2.14/255.255.255.224
  IP Phone13 [7960] @ (1224, 425)
    Switch [linked]
    Vlan50 IP=172.16.2.30/255.255.255.224
  IP Phone14 [7960] @ (1608, 740)
    Switch [linked]
    Vlan55 IP=172.16.2.38/255.255.255.224
  IP Phone15 [7960] @ (1525, 873)
    Switch [linked]
    Vlan50 IP=172.16.2.25/255.255.255.224
  IP Phone16 [7960] @ (1155, 424)
    Switch [linked]
    Vlan50 IP=172.16.2.16/255.255.255.224
  I1AT2 [Printer-PT] @ (1607, 819)
    FastEthernet0 IP=172.16.1.94/255.255.255.224 [linked]
  P1APAT1 [AccessPoint-PT] @ (1108, 1011)
    Port 1 [linked]
    Port 0 [linked]
  AP1Cl [AccessPoint-PT] @ (1271, 1018)
    Port 1 [linked]
    Port 0 [linked]
  IoT5 [Smoke Detector] @ (1341, 851)
    FastEthernet0 IP=172.16.3.16/255.255.255.128 [linked]
  IoT6 [Smoke Detector] @ (1119, 853)
    FastEthernet0 IP=172.16.3.15/255.255.255.128 [linked]
  IoT7 [Smoke Detector] @ (1231, 851)
    FastEthernet0 IP=172.16.3.14/255.255.255.128 [linked]
  IoT8 [Smoke Detector] @ (697, 415)
    FastEthernet0 IP=172.16.3.7/255.255.255.128 [linked]
  IoT9 [Smoke Detector] @ (1121, 645)
    FastEthernet0 IP=172.16.3.12/255.255.255.128 [linked]
  IoT10 [Smoke Detector] @ (1121, 749)
    FastEthernet0 IP=172.16.3.13/255.255.255.128 [linked]
  IoT11 [Smoke Detector] @ (1008, 417)
    FastEthernet0 IP=172.16.3.3/255.255.255.128 [linked]
  IoT12 [Smoke Detector] @ (903, 417)
    FastEthernet0 IP=172.16.3.5/255.255.255.128 [linked]
  IoT13 [Smoke Detector] @ (1005, 628)
    FastEthernet0 IP=172.16.3.4/255.255.255.128 [linked]
  IoT14 [Smoke Detector] @ (800, 417)
    FastEthernet0 IP=172.16.3.6/255.255.255.128 [linked]
  IoT15 [Smoke Detector] @ (1006, 524)
    FastEthernet0 IP=172.16.3.2/255.255.255.128 [linked]
  SW3-P1 [2960-24TT] @ (814, 634)
    FastEthernet0/1 [linked]
    FastEthernet0/2 [linked]
    FastEthernet0/3 [linked]
    FastEthernet0/4 [linked]
    FastEthernet0/5 [linked]
Ethernet0/13 [linked]
    FastEthernet0/14 [linked]
    FastEthernet0/15 [linked]
    FastEthernet0/16 [linked]
    FastEthernet0/17 [linked]
    FastEthernet0/24 [linked]
    GigabitEthernet0/1 [linked]
  IoT16 [Webcam] @ (604, 813)
    FastEthernet0 IP=172.16.3.46/255.255.255.128 [linked]
  IoT17 [Webcam] @ (1019, 818)
    FastEthernet0 IP=172.16.3.45/255.255.255.128 [linked]
  IoT18 [Webcam] @ (951, 817)
    FastEthernet0 IP=172.16.3.44/255.255.255.128 [linked]
  IoT19 [Webcam] @ (676, 817)
    FastEthernet0 IP=172.16.3.43/255.255.255.128 [linked]
  IoT20 [Webcam] @ (746, 817)
    FastEthernet0 IP=172.16.3.42/255.255.255.128 [linked]
  IoT21 [Webcam] @ (816, 817)
    FastEthernet0 IP=172.16.3.41/255.255.255.128 [linked]
  IoT22 [Webcam] @ (886, 816)
    FastEthernet0 IP=172.16.3.40/255.255.255.128 [linked]
  SW1-P3 [2960-24TT] @ (1462, 2290)
    FastEthernet0/1 [linked]
Ethernet0/4 [linked]
    FastEthernet0/5 [linked]
    FastEthernet0/6 [linked]
    FastEthernet0/7 [linked]
    FastEthernet0/8 [linked]
    FastEthernet0/9 [linked]
    FastEthernet0/10 [linked]
    FastEthernet0/11 [linked]
    FastEthernet0/12 [linked]
    FastEthernet0/13 [linked]
    FastEthernet0/14 [linked]
    FastEthernet0/15 [linked]
    FastEthernet0/16 [linked]
    FastEthernet0/17 [linked]
    FastEthernet0/18 [linked]
    FastEthernet0/19 [linked]
    FastEthernet0/20 [linked]
    FastEthernet0/21 [linked]
    FastEthernet0/22 [linked]
    FastEthernet0/23 [linked]
    FastEthernet0/24 [linked]
    GigabitEthernet0/1 [linked]
  P3CON1 [PC-PT] @ (1751, 1980)
    FastEthernet0 IP=172.16.1.51/255.255.255.224 [linked]
  P3CON2 [PC-PT] @ (1748, 2089)
    FastEthernet0 IP=172.16.1.47/255.255.255.224 [linked]
  P3CON3 [PC-PT] @ (1666, 1974)
    FastEthernet0 IP=172.16.1.43/255.255.255.224 [linked]
  P3CON4 [PC-PT] @ (1578, 1968)
    FastEthernet0 IP=172.16.1.52/255.255.255.224 [linked]
  P3CON5 [PC-PT] @ (1489, 1972)
    FastEthernet0 IP=172.16.1.49/255.255.255.224 [linked]
  P3RRHH3 [PC-PT] @ (1189, 2190)
    FastEthernet0 IP=172.16.1.44/255.255.255.224 [linked]
  P3RRHH1 [PC-PT] @ (1191, 1972)
    FastEthernet0 IP=172.16.1.42/255.255.255.224 [linked]
  P3CON6 [PC-PT] @ (1404, 1970)
    FastEthernet0 IP=172.16.1.48/255.255.255.224 [linked]
  P3GER3 [PC-PT] @ (1371, 2639)
    FastEthernet0 IP=172.16.1.7/255.255.255.240 [linked]
  P3TICs2 [PC-PT] @ (1746, 2197)
    FastEthernet0 IP=172.16.1.165/255.255.255.192 [linked]
  P3TICs6 [PC-PT] @ (1630, 2639)
    FastEthernet0 IP=172.16.1.141/255.255.255.192 [linked]
  P3TICs1 [PC-PT] @ (1746, 2302)
    FastEthernet0 IP=172.16.1.174/255.255.255.192 [linked]
  P3RRHH4 [PC-PT] @ (1182, 2522)
    FastEthernet0 [linked]
  P3RRHH6 [PC-PT] @ (1192, 2078)
    FastEthernet0 IP=172.16.1.46/255.255.255.224 [linked]
  P3RRHH2 [PC-PT] @ (1186, 2414)
    FastEthernet0 IP=172.16.1.50/255.255.255.224 [linked]
  P3TICs4 [PC-PT] @ (1736, 2411)
    FastEthernet0 IP=172.16.1.150/255.255.255.192 [linked]
  P3TICs5 [PC-PT] @ (1721, 2638)
    FastEthernet0 IP=172.16.1.164/255.255.255.192 [linked]
  P3GER1 [PC-PT] @ (1546, 2638)
    FastEthernet0 IP=172.16.1.5/255.255.255.240 [linked]
  P3GER4 [PC-PT] @ (1279, 2640)
    FastEthernet0 IP=172.16.1.3/255.255.255.240 [linked]
  P3TICs3 [PC-PT] @ (1732, 2520)
    FastEthernet0 IP=172.16.1.173/255.255.255.192 [linked]
  P3RRHH5 [PC-PT] @ (1188, 2303)
    FastEthernet0 [linked]
  P3GER2 [PC-PT] @ (1459, 2639)
    FastEthernet0 IP=172.16.1.6/255.255.255.240 [linked]
  P3GER5 [PC-PT] @ (1188, 2639)
    FastEthernet0 IP=172.16.1.9/255.255.255.240 [linked]
  SW2-P3 [2960-24TT] @ (622, 2429)
    FastEthernet0/1 [linked]
    FastEthernet0/2 [linked]
    FastEthernet0/3 [linked]
    FastEthernet0/4 [linked]
    FastEthernet0/5 [linked]
    FastEthernet0/6 [linked]
    FastEthernet0/7 [linked]
thernet0/9 [linked]
    FastEthernet0/10 [linked]
    FastEthernet0/11 [linked]
    FastEthernet0/12 [linked]
    FastEthernet0/13 [linked]
    FastEthernet0/14 [linked]
    FastEthernet0/15 [linked]
    FastEthernet0/16 [linked]
    FastEthernet0/17 [linked]
    FastEthernet0/18 [linked]
    FastEthernet0/19 [linked]
    FastEthernet0/20 [linked]
    FastEthernet0/21 [linked]
    FastEthernet0/22 [linked]
    FastEthernet0/23 [linked]
    FastEthernet0/24 [linked]
    GigabitEthernet0/2 [linked]
  Proyector [LCD] @ (178, 1594)
    FastEthernet0 IP=172.16.3.35/255.255.255.128 [linked]
  IP Phone17 [7960] @ (849, 2185)
    Switch [linked]
    Vlan55 IP=172.16.2.36/255.255.255.224
  IP Phone18 [7960] @ (949, 2183)
    Switch [linked]
    Vlan55 IP=172.16.2.57/255.255.255.224
  IP Phone19 [7960] @ (1046, 2182)
    Switch [linked]
    Vlan55 IP=172.16.2.54/255.255.255.224
  IP Phone20 [7960] @ (912, 2649)
    Switch [linked]
    Vlan55 IP=172.16.2.45/255.255.255.224
  IP Phone21 [7960] @ (807, 2650)
    Switch [linked]
e24 [7960] @ (706, 2652)
    Switch [linked]
  IP Phone25 [7960] @ (500, 2656)
    Switch [linked]
    Vlan55 IP=172.16.2.49/255.255.255.224
  IP Phone26 [7960] @ (600, 2655)
    Switch [linked]
    Vlan55 IP=172.16.2.41/255.255.255.224
  IP Phone27 [7960] @ (1014, 2645)
    Switch [linked]
    Vlan55 IP=172.16.2.47/255.255.255.224
  IP Phone28 [7960] @ (749, 2185)
    Switch [linked]
    Vlan55 IP=172.16.2.50/255.255.255.224
  IP Phone29 [7960] @ (410, 2655)
    Switch [linked]
    Vlan55 IP=172.16.2.53/255.255.255.224
  IP Phone30 [7960] @ (233, 2533)
    Switch [linked]
    Vlan55 IP=172.16.2.44/255.255.255.224
  IP Phone31 [7960] @ (316, 2656)
    Switch [linked]
    Vlan55 IP=172.16.2.62/255.255.255.224
  IP Phone32 [7960] @ (235, 2299)
    Switch [linked]
    Vlan55 IP=172.16.2.60/255.255.255.224
  IP Phone33 [7960] @ (459, 2184)
    Switch [linked]
    Vlan55 IP=172.16.2.35/255.255.255.224
  IP Phone34 [7960] @ (225, 2654)
    Switch [linked]
    Vlan55 IP=172.16.2.48/255.255.255.224
  IP Phone35 [7960] @ (558, 2184)
    Switch [linked]
    Vlan55 IP=172.16.2.51/255.255.255.224
  IP Phone36 [7960] @ (654, 2186)
    Switch [linked]
    Vlan55 IP=172.16.2.42/255.255.255.224
  IP Phone37 [7960] @ (229, 2416)
    Switch [linked]
    Vlan55 IP=172.16.2.56/255.255.255.224
  IP Phone38 [7960] @ (246, 2182)
    Switch [linked]
    Vlan55 IP=172.16.2.39/255.255.255.224
  IP Phone39 [7960] @ (359, 2183)
    Switch [linked]
    Vlan55 IP=172.16.2.46/255.255.255.224
  SW3-P3 [2960-24TT] @ (577, 1834)
    FastEthernet0/1 [linked]
    FastEthernet0/2 [linked]
    FastEthernet0/3 [linked]
    FastEthernet0/4 [linked]
    FastEthernet0/5 [linked]
    FastEthernet0/6 [linked]
    FastEthernet0/7 [linked]
    FastEthernet0/8 [linked]
    FastEthernet0/9 [linked]
    FastEthernet0/10 [linked]
    FastEthernet0/11 [linked]
    FastEthernet0/12 [linked]
    FastEthernet0/13 [linked]
    FastEthernet0/14 [linked]
    FastEthernet0/15 [linked]
    FastEthernet0/16 [linked]
    FastEthernet0/17 [linked]
    FastEthernet0/18 [linked]
    FastEthernet0/19 [linked]
    FastEthernet0/20 [linked]
    FastEthernet0/21 [linked]
    FastEthernet0/22 [linked]
    FastEthernet0/23 [linked]
    GigabitEthernet0/1 [linked]
  I3CON1 [Printer-PT] @ (982, 2063)
    FastEthernet0 IP=172.16.1.61/255.255.255.224 [linked]
  AP3G1 [AccessPoint-PT] @ (958, 1911)
    Port 1 [linked]
    Port 0 [linked]
  AP3Cl1 [AccessPoint-PT] @ (1004, 2434)
    Port 1 [linked]
    Port 0 [linked]
  AP3Con1 [AccessPoint-PT] @ (1266, 1983)
    Port 1 [linked]
    Port 0 [linked]
  I3RRHH1 [Printer-PT] @ (987, 1987)
    FastEthernet0 IP=172.16.1.62/255.255.255.224 [linked]
  IoT1 [Smoke Detector] @ (974, 1798)
    FastEthernet0 IP=172.16.3.26/255.255.255.128 [linked]
  IoT2 [Smoke Detector] @ (977, 1696)
    FastEthernet0 IP=172.16.3.27/255.255.255.128 [linked]
  IoT3 [Smoke Detector] @ (975, 1590)
    FastEthernet0 IP=172.16.3.28/255.255.255.128 [linked]
  IoT4 [Smoke Detector] @ (868, 1588)
    FastEthernet0 IP=172.16.3.29/255.255.255.128 [linked]
  IoT23 [Smoke Detector] @ (759, 1587)
    FastEthernet0 IP=172.16.3.30/255.255.255.128 [linked]
  IoT24 [Smoke Detector] @ (641, 1587)
    FastEthernet0 IP=172.16.3.31/255.255.255.128 [linked]
  IoT25 [Smoke Detector] @ (533, 1590)
    FastEthernet0 IP=172.16.3.32/255.255.255.128 [linked]
  IoT26 [Webcam] @ (199, 2041)
Webcam] @ (203, 1707)
    FastEthernet0 IP=172.16.3.54/255.255.255.128 [linked]
  IoT28 [Webcam] @ (196, 1814)
    FastEthernet0 IP=172.16.3.55/255.255.255.128 [linked]
  IoT29 [Webcam] @ (197, 1922)
    FastEthernet0 IP=172.16.3.56/255.255.255.128 [linked]
  IoT30 [Webcam] @ (292, 2041)
    FastEthernet0 IP=172.16.3.58/255.255.255.128 [linked]
  IoT31 [Webcam] @ (389, 2039)
    FastEthernet0 IP=172.16.3.59/255.255.255.128 [linked]
  IoT32 [Webcam] @ (476, 2038)
    FastEthernet0 IP=172.16.3.60/255.255.255.128 [linked]
  IoT35 [Smoke Detector] @ (425, 1591)
    FastEthernet0 IP=172.16.3.33/255.255.255.128 [linked]
  IoT36 [Smoke Detector] @ (321, 1591)
    FastEthernet0 IP=172.16.3.34/255.255.255.128 [linked]
  R-Sucursal [2811] @ (2313, 2228)
    FastEthernet0/0 [linked]
    Serial0/3/0 IP=172.16.250.6/255.255.255.252 [linked]
    Serial0/3/1 IP=172.16.250.10/255.255.255.252 [linked]
    FastEthernet0/0.12 IP=172.16.20.1/255.255.255.240
    FastEthernet0/0.22 IP=172.16.20.17/255.255.255.240
    FastEthernet0/0.52 IP=172.16.20.33/255.255.255.240
    FastEthernet0/0.62 IP=172.16.20.65/255.255.255.224
    FastEthernet0/0.72 IP=172.16.20.97/255.255.255.240
    FastEthernet0/0.199 IP=172.16.20.113/255.255.255.240
  SW-SUC-1 [2960-24TT] @ (3030, 2221)
    FastEthernet0/1 [linked]
    FastEthernet0/2 [linked]
    FastEthernet0/3 [linked]
    FastEthernet0/4 [linked]
    FastEthernet0/5 [linked]
    FastEthernet0/6 [linked]
thernet0/14 [linked]
    FastEthernet0/15 [linked]
    FastEthernet0/16 [linked]
    FastEthernet0/17 [linked]
    FastEthernet0/18 [linked]
    FastEthernet0/19 [linked]
    FastEthernet0/20 [linked]
    FastEthernet0/21 [linked]
    FastEthernet0/22 [linked]
    FastEthernet0/23 [linked]
    FastEthernet0/24 [linked]
    GigabitEthernet0/1 [linked]
    GigabitEthernet0/2 [linked]
  Power Distribution Device1 [Power Distribution Device] @ (3895, 3885)
  SPCRE2 [PC-PT] @ (2782, 2000)
    FastEthernet0 IP=172.16.20.2/255.255.255.240 [linked]
  SPCAJ1 [PC-PT] @ (2872, 1886)
    FastEthernet0 IP=172.16.20.6/255.255.255.240 [linked]
  SPCAJ2 [PC-PT] @ (2959, 1884)
    FastEthernet0 IP=172.16.20.8/255.255.255.240 [linked]
  SPTICs1 [PC-PT] @ (3049, 1884)
    FastEthernet0 IP=172.16.20.18/255.255.255.240 [linked]
  SPTICs2 [PC-PT] @ (3140, 1886)
    FastEthernet0 IP=172.16.20.20/255.255.255.240 [linked]
  SBOD [PC-PT] @ (3232, 1886)
    FastEthernet0 IP=172.16.20.19/255.255.255.240 [linked]
  SPCRE1 [PC-PT] @ (2785, 1884)
    FastEthernet0 IP=172.16.20.7/255.255.255.240 [linked]
  IP Phone40 [7960] @ (3328, 1887)
    Switch [linked]
    Vlan52 IP=172.16.20.35/255.255.255.240
  IP Phone41 [7960] @ (3321, 2121)
    Switch [linked]
    Vlan52 IP=172.16.20.38/255.255.255.240
  IP Phone42 [7960] @ (3320, 2006)
    Switch [linked]
    Vlan52 IP=172.16.20.39/255.255.255.240
  IP Phone43 [7960] @ (3302, 2585)
    Switch [linked]
    Vlan52 IP=172.16.20.34/255.255.255.240
  IP Phone44 [7960] @ (3317, 2241)
    Switch [linked]
    Vlan52 IP=172.16.20.37/255.255.255.240
  IP Phone45 [7960] @ (3317, 2354)
    Switch [linked]
    Vlan52 IP=172.16.20.36/255.255.255.240
  IP Phone46 [7960] @ (3310, 2469)
    Switch [linked]
    Vlan52 IP=172.16.20.40/255.255.255.240
  IoT0 [Smoke Detector] @ (2752, 2351)
    FastEthernet0 IP=172.16.20.68/255.255.255.224 [linked]
  IoT33 [Smoke Detector] @ (2746, 2463)
    FastEthernet0 IP=172.16.20.69/255.255.255.224 [linked]
  IoT34 [Smoke Detector] @ (2741, 2574)
    FastEthernet0 IP=172.16.20.70/255.255.255.224 [linked]
  IoT37 [Smoke Detector] @ (2845, 2577)
    FastEthernet0 IP=172.16.20.71/255.255.255.224 [linked]
  IoT38 [Smoke Detector] @ (2948, 2575)
    FastEthernet0 IP=172.16.20.72/255.255.255.224 [linked]
  IoT39 [Motion Detector] @ (2751, 2093)
    FastEthernet0 IP=172.16.20.66/255.255.255.224 [linked]
  IoT41 [Temperature Sensor] @ (2734, 2196)
    FastEthernet0 IP=172.16.20.67/255.255.255.224 [linked]
  SAPCaj [AccessPoint-PT] @ (3052, 2610)
    Port 1 [linked]
    Port 0 [linked]
  SAPVIS [AccessPoint-PT] @ (3164, 2611)
    Port 1 [linked]
    Port 0 [linked]
  SW-SUC-2 [2960-24TT] @ (3658, 2214)
    FastEthernet0/2 [linked]
    FastEthernet0/3 [linked]
    FastEthernet0/4 [linked]
    FastEthernet0/5 [linked]
    FastEthernet0/6 [linked]
    FastEthernet0/7 [linked]
    FastEthernet0/8 [linked]
    FastEthernet0/9 [linked]
    FastEthernet0/10 [linked]
    FastEthernet0/11 [linked]
    FastEthernet0/12 [linked]
    FastEthernet0/24 [linked]
    GigabitEthernet0/2 [linked]
  SAPTICs [AccessPoint-PT] @ (3496, 2188)
    Port 1 [linked]
    Port 0 [linked]
  IoT42 [Webcam] @ (3518, 2038)
    FastEthernet0 IP=172.16.20.73/255.255.255.224 [linked]
  IoT43 [Webcam] @ (3611, 2037)
    FastEthernet0 IP=172.16.20.74/255.255.255.224 [linked]
  IoT44 [Webcam] @ (3521, 2269)
    FastEthernet0 IP=172.16.20.85/255.255.255.224 [linked]
  IoT45 [Webcam] @ (3527, 2377)
    FastEthernet0 IP=172.16.20.83/255.255.255.224 [linked]
  IoT46 [Webcam] @ (3622, 2379)
    FastEthernet0 IP=172.16.20.81/255.255.255.224 [linked]
  IoT47 [Webcam] @ (3714, 2380)
    FastEthernet0 IP=172.16.20.80/255.255.255.224 [linked]
  IoT48 [Webcam] @ (3701, 2039)
    FastEthernet0 IP=172.16.20.75/255.255.255.224 [linked]
  IoT49 [Webcam] @ (3793, 2039)
    FastEthernet0 IP=172.16.20.76/255.255.255.224 [linked]
  IoT51 [Webcam] @ (3797, 2159)
    FastEthernet0 IP=172.16.20.77/255.255.255.224 [linked]
  IoT52 [Webcam] @ (3805, 2377)
    FastEthernet0 IP=172.16.20.79/255.255.255.224 [linked]
  IoT50 [Webcam] @ (3800, 2273)
    FastEthernet0 IP=172.16.20.78/255.255.255.224 [linked]
  IoT1(2) [Smoke Detector] @ (2244, 406)
    FastEthernet0 IP=172.16.3.17/255.255.255.128 [linked]
  IoT0(1) [Webcam] @ (2097, 406)
    FastEthernet0 IP=172.16.3.48/255.255.255.128 [linked]
  IoT1(1) [Smoke Detector] @ (2352, 410)
    FastEthernet0 IP=172.16.3.18/255.255.255.128 [linked]
  P2TICs5 [PC-PT] @ (2184, 675)
    FastEthernet0 IP=172.16.1.176/255.255.255.192 [linked]
  P3INN8 [PC-PT] @ (2910, 853)
    FastEthernet0 IP=172.16.1.180/255.255.255.192 [linked]
  P3INN15 [PC-PT] @ (2534, 1231)
    FastEthernet0 IP=172.16.1.145/255.255.255.192 [linked]
  P3INN14 [PC-PT] @ (2533, 1346)
    FastEthernet0 IP=172.16.1.153/255.255.255.192 [linked]
  P3INN5 [PC-PT] @ (2808, 855)
    FastEthernet0 IP=172.16.1.148/255.255.255.192 [linked]
  P3INN16 [PC-PT] @ (2529, 1461)
    FastEthernet0 IP=172.16.1.144/255.255.255.192 [linked]
  P3INN18 [PC-PT] @ (2614, 1466)
    FastEthernet0 IP=172.16.1.170/255.255.255.192 [linked]
  P3INN13 [PC-PT] @ (2628, 1013)
    FastEthernet0 IP=172.16.1.166/255.255.255.192 [linked]
  P3INN17 [PC-PT] @ (2704, 1468)
    FastEthernet0 IP=172.16.1.169/255.255.255.192 [linked]
  P2TICs3 [PC-PT] @ (2056, 672)
    FastEthernet0 IP=172.16.1.146/255.255.255.192 [linked]
  IoT2(1) [Smoke Detector] @ (2849, 1005)
    FastEthernet0 IP=172.16.3.25/255.255.255.128 [linked]
  Power Distribution Device2 [Power Distribution Device] @ (3896, 3885)
  P2TICs4 [PC-PT] @ (2120, 673)
    FastEthernet0 IP=172.16.1.178/255.255.255.192 [linked]
  P3INN4 [PC-PT] @ (2378, 606)
    FastEthernet0 IP=172.16.1.135/255.255.255.192 [linked]
  P2MON2 [PC-PT] @ (1917, 596)
    FastEthernet0 IP=172.16.1.168/255.255.255.192 [linked]
  P2MON1 [PC-PT] @ (1918, 519)
    FastEthernet0 IP=172.16.1.160/255.255.255.192 [linked]
  P3INN1 [PC-PT] @ (2250, 676)
    FastEthernet0 IP=172.16.1.140/255.255.255.192 [linked]
  P3INN3 [PC-PT] @ (2370, 680)
    FastEthernet0 IP=172.16.1.133/255.255.255.192 [linked]
  P2TICs1 [PC-PT] @ (1915, 671)
    FastEthernet0 [linked]
  P3INN7 [PC-PT] @ (3122, 845)
    FastEthernet0 IP=172.16.1.143/255.255.255.192 [linked]
  P2TICs2 [PC-PT] @ (1989, 672)
    FastEthernet0 IP=172.16.1.138/255.255.255.192 [linked]
  P3INN20 [PC-PT] @ (2899, 1470)
    FastEthernet0 IP=172.16.1.177/255.255.255.192 [linked]
  P3INN2 [PC-PT] @ (2310, 681)
    FastEthernet0 IP=172.16.1.172/255.255.255.192 [linked]
  IP Phone24(1) [7960] @ (3169, 1016)
    Switch [linked]
    Vlan50 IP=172.16.2.23/255.255.255.224
  IP Phone19(1) [7960] @ (3074, 1012)
    Switch [linked]
    Vlan50 IP=172.16.2.22/255.255.255.224
  IP Phone22(1) [7960] @ (3050, 284)
    Switch [linked]
    Vlan55 IP=172.16.2.43/255.255.255.224
  IP Phone23(1) [7960] @ (3223, 625)
    Switch [linked]
    Vlan55 IP=172.16.2.55/255.255.255.224
  IP Phone30(1) [7960] @ (3227, 514)
    Switch [linked]
    Vlan50 IP=172.16.2.4/255.255.255.224
  IP Phone20(1) [7960] @ (3239, 289)
    Switch [linked]
1) [7960] @ (2956, 282)
    Switch [linked]
    Vlan55 IP=172.16.2.37/255.255.255.224
  IP Phone31(1) [7960] @ (3223, 400)
    Switch [linked]
    Vlan55 IP=172.16.2.52/255.255.255.224
  IP Phone32(1) [7960] @ (3147, 285)
    Switch [linked]
    Vlan50 IP=172.16.2.10/255.255.255.224
  IP Phone29(1) [7960] @ (3239, 1356)
    Switch [linked]
    Vlan50 IP=172.16.2.26/255.255.255.224
  IP Phone26(1) [7960] @ (3243, 1246)
    Switch [linked]
    Vlan50 IP=172.16.2.21/255.255.255.224
  IP Phone34(1) [7960] @ (2375, 527)
    Switch [linked]
    Vlan50 IP=172.16.2.6/255.255.255.224
  P3INN19 [PC-PT] @ (2799, 1470)
    FastEthernet0 IP=172.16.1.182/255.255.255.192 [linked]
  P3INN12 [PC-PT] @ (2537, 1010)
PT] @ (3232, 734)
    FastEthernet0 [linked]
  P3INN9 [PC-PT] @ (3230, 845)
    FastEthernet0 [linked]
  P3INN11 [PC-PT] @ (2538, 1120)
    FastEthernet0 IP=172.16.1.167/255.255.255.192 [linked]
  IoT29(1) [Smoke Detector] @ (2955, 1004)
    FastEthernet0 IP=172.16.3.24/255.255.255.128 [linked]
  IoT30(1) [Smoke Detector] @ (2584, 390)
    FastEthernet0 IP=172.16.3.23/255.255.255.128 [linked]
  IoT4(1) [Webcam] @ (2176, 406)
    FastEthernet0 IP=172.16.3.49/255.255.255.128 [linked]
  IoT3(1) [Webcam] @ (2015, 403)
    FastEthernet0 IP=172.16.3.47/255.255.255.128 [linked]
  IoT27(1) [Webcam] @ (2695, 835)
    FastEthernet0 IP=172.16.3.53/255.255.255.128 [linked]
  IoT24(1) [Webcam] @ (2604, 835)
    FastEthernet0 IP=172.16.3.52/255.255.255.128 [linked]
  IoT23(1) [Webcam] @ (2704, 999)
    FastEthernet0 IP=172.16.3.50/255.255.255.128 [linked]
  IoT25(1) [Webcam] @ (2785, 1003)
    FastEthernet0 IP=172.16.3.51/255.255.255.128 [linked]
  IoT28(1) [Smoke Detector] @ (2580, 510)
    FastEthernet0 IP=172.16.3.19/255.255.255.128 [linked]
  SW3-P2 [2960-24TT] @ (2141, 568)
    FastEthernet0/1 [linked]
    FastEthernet0/2 [linked]
    FastEthernet0/3 [linked]
    FastEthernet0/4 [linked]
    FastEthernet0/5 [linked]
    FastEthernet0/6 [linked]
    FastEthernet0/7 [linked]
    FastEthernet0/8 [linked]
    FastEthernet0/9 [linked]
    FastEthernet0/10 [linked]
    FastEthernet0/11 [linked]
    FastEthernet0/12 [linked]
    FastEthernet0/13 [linked]
    FastEthernet0/14 [linked]
    FastEthernet0/15 [linked]
    FastEthernet0/16 [linked]
    FastEthernet0/17 [linked]
    FastEthernet0/24 [linked]
    GigabitEthernet0/1 [linked]
  SW2-P2 [2960-24TT] @ (2911, 584)
    FastEthernet0/1 [linked]
    FastEthernet0/2 [linked]
    FastEthernet0/3 [linked]
    FastEthernet0/4 [linked]
    FastEthernet0/5 [linked]
    FastEthernet0/6 [linked]
    FastEthernet0/7 [linked]
    FastEthernet0/8 [linked]
    FastEthernet0/9 [linked]
    FastEthernet0/10 [linked]
    FastEthernet0/11 [linked]
    FastEthernet0/12 [linked]
    FastEthernet0/13 [linked]
    FastEthernet0/14 [linked]
    FastEthernet0/15 [linked]
    FastEthernet0/16 [linked]
    FastEthernet0/17 [linked]
    FastEthernet0/18 [linked]
    FastEthernet0/19 [linked]
    FastEthernet0/20 [linked]
    FastEthernet0/23 [linked]
    FastEthernet0/24 [linked]
    GigabitEthernet0/2 [linked]
  SW1-P2 [2960-24TT] @ (2881, 1250)
    FastEthernet0/1 [linked]
    FastEthernet0/2 [linked]
    FastEthernet0/3 [linked]
    FastEthernet0/4 [linked]
    FastEthernet0/5 [linked]
/11 [linked]
    FastEthernet0/12 [linked]
    FastEthernet0/13 [linked]
    FastEthernet0/14 [linked]
    FastEthernet0/15 [linked]
    FastEthernet0/16 [linked]
    FastEthernet0/17 [linked]
    FastEthernet0/18 [linked]
    FastEthernet0/19 [linked]
    FastEthernet0/20 [linked]
    FastEthernet0/21 [linked]
    FastEthernet0/22 [linked]
    FastEthernet0/23 [linked]
    GigabitEthernet0/1 [linked]
  SW-CORE [3650-24PS] @ (2133, 1679)
    GigabitEthernet1/0/1 [linked]
    GigabitEthernet1/0/2 [linked]
    GigabitEthernet1/0/3 [linked]
    GigabitEthernet1/0/4 [linked]
    GigabitEthernet1/0/5 [linked]
    GigabitEthernet1/0/6 [linked]
    GigabitEthernet1/0/7 [linked]
    GigabitEthernet1/0/8 [linked]
    GigabitEthernet1/0/9 [linked]
    GigabitEthernet1/0/10 [linked]
    GigabitEthernet1/0/11 [linked]
et1/0/14 [linked]
    GigabitEthernet1/0/15 [linked]
    GigabitEthernet1/0/16 [linked]
    GigabitEthernet1/0/23 [linked]
    GigabitEthernet1/0/24 [linked]
    Vlan55 IP=172.16.2.34/255.255.255.224
    Vlan99 IP=172.16.0.2/255.255.255.240
  R-Matriz [2811] @ (2141, 1858)
    FastEthernet0/0 [linked]
    Serial0/3/0 IP=172.16.250.1/255.255.255.252 [linked]
    Serial0/3/1 IP=172.16.250.5/255.255.255.252 [linked]
    FastEthernet0/0.10 IP=172.16.1.1/255.255.255.240
    FastEthernet0/0.20 IP=172.16.1.33/255.255.255.224
    FastEthernet0/0.30 IP=172.16.1.65/255.255.255.224
    FastEthernet0/0.40 IP=172.16.1.129/255.255.255.192
    FastEthernet0/0.50 IP=172.16.2.1/255.255.255.224
    FastEthernet0/0.60 IP=172.16.3.1/255.255.255.128
    FastEthernet0/0.70 IP=172.16.4.1/255.255.255.240
    FastEthernet0/0.99 IP=172.16.0.1/255.255.255.240
    FastEthernet0/0.100 IP=172.16.100.1/255.255.255.240
  SW-CORE-S [2960-24TT] @ (1880, 3396)
    FastEthernet0/1 [linked]
    FastEthernet0/2 [linked]
    FastEthernet0/3 [linked]
    GigabitEthernet0/1 [linked]
/1 [linked]
    FastEthernet0/2 [linked]
    FastEthernet0/3 [linked]
    FastEthernet0/4 [linked]
    FastEthernet0/5 [linked]
    FastEthernet0/6 [linked]
    FastEthernet0/7 [linked]
    FastEthernet0/8 [linked]
    FastEthernet0/9 [linked]
    FastEthernet0/10 [linked]
    FastEthernet0/11 [linked]
    FastEthernet0/12 [linked]
    FastEthernet0/13 [linked]
    FastEthernet0/14 [linked]
    FastEthernet0/15 [linked]
    FastEthernet0/16 [linked]
    FastEthernet0/17 [linked]
    FastEthernet0/18 [linked]
    FastEthernet0/24 [linked]
    GigabitEthernet0/1 [linked]
  Switch16 NAVE [2960-24TT] @ (1335, 3123)
    FastEthernet0/1 [linked]
    FastEthernet0/2 [linked]
    FastEthernet0/3 [linked]
    FastEthernet0/4 [linked]
    FastEthernet0/5 [linked]
    FastEthernet0/6 [linked]
    FastEthernet0/7 [linked]
    FastEthernet0/8 [linked]
    FastEthernet0/9 [linked]
    FastEthernet0/10 [linked]
    FastEthernet0/11 [linked]
    FastEthernet0/12 [linked]
    FastEthernet0/13 [linked]
    FastEthernet0/23 [linked]
    FastEthernet0/24 [linked]
    GigabitEthernet0/1 [linked]
  Switch17 SEGURIDAD [2960-24TT] @ (2326, 3367)
    FastEthernet0/1 [linked]
    FastEthernet0/2 [linked]
    FastEthernet0/3 [linked]
    FastEthernet0/4 [linked]
    FastEthernet0/5 [linked]
    FastEthernet0/6 [linked]
    FastEthernet0/7 [linked]
    FastEthernet0/8 [linked]
    FastEthernet0/9 [linked]
    FastEthernet0/10 [linked]
    FastEthernet0/11 [linked]
    FastEthernet0/12 [linked]
    FastEthernet0/13 [linked]
    FastEthernet0/14 [linked]
    FastEthernet0/15 [linked]
    FastEthernet0/16 [linked]
(1245, 3428)
    FastEthernet0 IP=172.16.10.5/255.255.255.240 [linked]
  FOFI6 [PC-PT] @ (1171, 3426)
    FastEthernet0 IP=172.16.10.3/255.255.255.240 [linked]
  FENF1 [PC-PT] @ (1167, 3582)
    FastEthernet0 IP=172.16.10.19/255.255.255.240 [linked]
  FBOD1 [PC-PT] @ (1169, 3511)
    FastEthernet0 IP=172.16.10.21/255.255.255.240 [linked]
  FSEC1 [PC-PT] @ (1166, 3658)
    FastEthernet0 IP=172.16.10.18/255.255.255.240 [linked]
  IP Phone47 [7960] @ (1156, 3730)
    Switch [linked]
    Vlan51 IP=172.16.10.38/255.255.255.224
  IP Phone48 [7960] @ (1160, 3814)
    Switch [linked]
    Vlan51 IP=172.16.10.39/255.255.255.224
  IP Phone49 [7960] @ (1241, 3816)
    Switch [linked]
    Vlan51 IP=172.16.10.34/255.255.255.224
]
    Vlan51 IP=172.16.10.41/255.255.255.224
  IP Phone53 [7960] @ (1509, 3818)
    Switch [linked]
    Vlan51 IP=172.16.10.37/255.255.255.224
  IP Phone54 [7960] @ (1519, 3578)
    Switch [linked]
    Vlan51 IP=172.16.10.35/255.255.255.224
  I1OFI [Printer-PT] @ (1525, 3508)
    FastEthernet0 IP=172.16.10.14/255.255.255.240 [linked]
  FAP1EMPL [AccessPoint-PT] @ (1493, 3667)
    Port 1 [linked]
    Port 0 [linked]
  FAP2EMPLE [AccessPoint-PT] @ (1360, 2913)
    Port 1 [linked]
    Port 0 [linked]
  FAPINV1 [AccessPoint-PT] @ (1471, 2916)
    Port 1 [linked]
    Port 0 [linked]
  Power Distribution Device3 [Power Distribution Device] @ (3897, 3885)
  IoT0(2) [Smoke Detector] @ (1586, 2886)
    FastEthernet0 IP=172.16.10.71/255.255.255.192 [linked]
  IoT0(2)(1) [Smoke Detector] @ (1585, 3013)
    FastEthernet0 IP=172.16.10.70/255.255.255.192 [linked]
  IoT0(2)(2) [Smoke Detector] @ (1582, 3131)
der] @ (1089, 3122)
    FastEthernet0 IP=172.16.10.74/255.255.255.192 [linked]
  IoT111 [RFID Reader] @ (1094, 3240)
    FastEthernet0 IP=172.16.10.73/255.255.255.192 [linked]
  IoT112 [Webcam] @ (2081, 3075)
    FastEthernet0 IP=172.16.10.94/255.255.255.192 [linked]
  IoT113 [Webcam] @ (2334, 3075)
    FastEthernet0 IP=172.16.10.90/255.255.255.192 [linked]
  APSEC1 [AccessPoint-PT] @ (2052, 3206)
    Port 1 [linked]
    Port 0 [linked]
  IoT0(2)(5)(1) [Smoke Detector] @ (2579, 3194)
    FastEthernet0 IP=172.16.10.87/255.255.255.192 [linked]
  IoT0(2)(5)(2) [Smoke Detector] @ (2578, 3297)
    FastEthernet0 IP=172.16.10.85/255.255.255.192 [linked]
  IoT0(2)(5)(2)(1) [Smoke Detector] @ (2576, 3401)
    FastEthernet0 IP=172.16.10.84/255.255.255.192 [linked]
  IoT0(2)(5)(2)(2) [Smoke Detector] @ (2574, 3614)
    FastEthernet0 IP=172.16.10.83/255.255.255.192 [linked]
 [Smoke Detector] @ (2353, 3615)
    FastEthernet0 IP=172.16.10.81/255.255.255.192 [linked]
  IoT0(2)(5)(2)(5) [Smoke Detector] @ (2256, 3616)
    FastEthernet0 IP=172.16.10.80/255.255.255.192 [linked]
  IoT0(2)(5)(2)(6) [Smoke Detector] @ (2157, 3615)
    FastEthernet0 IP=172.16.10.79/255.255.255.192 [linked]
  IoT0(2)(5)(2)(7) [Smoke Detector] @ (2056, 3615)
    FastEthernet0 IP=172.16.10.78/255.255.255.192 [linked]
  IoT0(2)(5)(2)(8) [Smoke Detector] @ (2055, 3488)
    FastEthernet0 IP=172.16.10.77/255.255.255.192 [linked]
  IoT33(1)(1) [Humidity Monitor] @ (1227, 3248)
    FastEthernet0 IP=172.16.10.72/255.255.255.192 [linked]
  R-Fabrica [2811] @ (2078, 2610)
    FastEthernet0/0 [linked]
    Serial0/3/0 IP=172.16.250.2/255.255.255.252 [linked]
    Serial0/3/1 IP=172.16.250.9/255.255.255.252 [linked]
    FastEthernet0/0.11 IP=172.16.10.1/255.255.255.240
    FastEthernet0/0.21 IP=172.16.10.17/255.255.255.240
    FastEthernet0/0.51 IP=172.16.10.33/255.255.255.224
    FastEthernet0/0.61 IP=172.16.10.65/255.255.255.192
    FastEthernet0/0.71 IP=172.16.10.129/255.255.255.240
    FastEthernet0/0.81 IP=172.16.10.145/255.255.255.240
    FastEthernet0/0.299 IP=172.16.10.161/255.255.255.240
  IoT24(2) [Motion Detector] @ (2841, 275)
    FastEthernet0 IP=172.16.3.20/255.255.255.128 [linked]
  IoT56 [RFID Reader] @ (2732, 278)
    FastEthernet0 IP=172.16.3.22/255.255.255.128 [linked]
  IoT58 [Temperature Monitor] @ (2587, 280)
    FastEthernet0 IP=172.16.3.21/255.255.255.128 [linked]
  IoT61 [RFID Reader] @ (586, 516)
    FastEthernet0 IP=172.16.3.9/255.255.255.128 [linked]
  IoT63 [RFID Reader] @ (584, 614)
    FastEthernet0 IP=172.16.3.10/255.255.255.128 [linked]
  IoT64 [RFID Reader] @ (583, 713)
    FastEthernet0 IP=172.16.3.11/255.255.255.128 [linked]
  IoT65 [Humiture Monitor] @ (577, 412)
    FastEthernet0 IP=172.16.3.8/255.255.255.128 [linked]
  IoT66 [Motion Detector] @ (555, 2041)
    FastEthernet0 IP=172.16.3.36/255.255.255.128 [linked]
  IoT68 [Temperature Monitor] @ (666, 2039)
    FastEthernet0 IP=172.16.3.37/255.255.255.128 [linked]
  IoT69 [RFID Reader] @ (820, 2040)
    FastEthernet0 IP=172.16.3.38/255.255.255.128 [linked]
  IP Phone55 [7960] @ (3010, 1472)
    Switch [linked]
    Vlan50 IP=172.16.2.20/255.255.255.224
  IP Phone56 [7960] @ (3126, 1473)
.16.2.18/255.255.255.224
  IoT57 [RFID Reader] @ (2057, 3290)
    FastEthernet0 IP=172.16.10.75/255.255.255.192 [linked]
  WEB-SERVER [Server-PT] @ (2056, 1464)
    FastEthernet0 IP=172.16.100.3/255.255.255.240 [linked]
  Power Distribution Device4 [Power Distribution Device] @ (3881, 3885)
  DHCP-Server [Server-PT] @ (2150, 1465)
    FastEthernet0 IP=172.16.100.6/255.255.255.240 [linked]
  DNS-SERVER [Server-PT] @ (1954, 1465)
    FastEthernet0 IP=172.16.100.2/255.255.255.240 [linked]
  Email-Server [Server-PT] @ (2242, 1467)
    FastEthernet0 IP=172.16.100.4/255.255.255.240 [linked]
  Servidor DB [Server-PT] @ (2324, 1576)
    FastEthernet0 IP=172.16.100.8/255.255.255.240 [linked]
  IoT-server [Server-PT] @ (2325, 1671)
    FastEthernet0 IP=172.16.100.5/255.255.255.240 [linked]
  Servidor-Apps [Server-PT] @ (2328, 1465)
    FastEthernet0 IP=172.16.100.7/255.255.255.240 [linked]
  Power Distribution Device5 [Power Distribution Device] @ (38
  IoT41(1) [Temperature Sensor] @ (2051, 3399)
    FastEthernet0 IP=172.16.10.76/255.255.255.192 [linked]
  IoT0(2)(5)(2)(9) [Smoke Detector] @ (2465, 3613)
    FastEthernet0 IP=172.16.10.86/255.255.255.192 [linked]
  AP1EMPL1 [AccessPoint-PT] @ (995, 742)
    Port 1 [linked]
    Port 0 [linked]
  APCON1 [AccessPoint-PT] @ (1887, 444)
    Port 1 [linked]
ssPoint-PT] @ (2574, 633)
    Port 1 [linked]
    Port 0 [linked]
  AP2EMPLE1 [AccessPoint-PT] @ (2576, 738)
    Port 1 [linked]
    Port 0 [linked]
  IoT113(1) [Webcam] @ (2168, 3075)
    FastEthernet0 IP=172.16.10.93/255.255.255.192 [linked]
  IoT113(2) [Webcam] @ (2253, 3076)
    FastEthernet0 IP=172.16.10.92/255.255.255.192 [linked]
  IoT113(3) [Webcam] @ (2506, 3079)
    FastEthernet0 IP=172.16.10.88/255.255.255.192 [linked]
  IoT113(4) [Webcam] @ (2590, 3081)
    FastEthernet0 IP=172.16.10.89/255.255.255.192 [linked]
  IoT113(5) [Webcam] @ (2418, 3078)
    FastEthernet0 IP=172.16.10.91/255.255.255.192 [linked]
  IoT113(6) [Webcam] @ (1119, 2890)
    FastEthernet0 IP=172.16.10.98/255.255.255.192 [linked]
  IoT113(7) [Webcam] @ (1115, 3006)
    FastEthernet0 IP=172.16.10.97/255.255.255.192 [linked]
  IoT113(8) [Webcam] @ (1213, 2891)
    FastEthernet0 IP=172.16.10.96/255.255.255.192 [linked]
  IoT113(9) [Webcam] @ (1292, 2892)
    FastEthernet0 IP=172.16.10.95/255.255.255.192 [linked]
  Server VOZ [2811] @ (1970, 1640)
    FastEthernet0/0 IP=172.16.2.33/255.255.255.224 [linked]
  IoT41(2) [Temperature Sensor] @ (2740, 2274)
    FastEthernet0 IP=172.16.20.86/255.255.255.224 [linked]

--- Links ---
  P1APAT1:Port 1  )))  [wireless signal]
  AP1Cl:Port 1  )))  [wireless signal]
  AP3G1:Port 1  )))  [wireless signal]
  AP3Cl1:Port 1  )))  [wireless signal]
  AP3Con1:Port 1  )))  [wireless signal]
  SAPCaj:Port 1  )))  [wireless signal]
  SAPVIS:Port 1  )))  [wireless signal]
  SAPTICs:Port 1  )))  [wireless signal]
  FAP1EMPL:Port 1  )))  [wireless signal]
  FAP2EMPLE:Port 1  )))  [wireless signal]
  FAPINV1:Port 1  )))  [wireless signal]
  APSEC1:Port 1  )))  [wireless signal]
  AP1EMPL1:Port 1  )))  [wireless signal]
  APCON1:Port 1  )))  [wireless signal]
  AP2EMPLE2:Port 1  )))  [wireless signal]
  AP2EMPLE1:Port 1  )))  [wireless signal]
  SW3-P1:FastEthernet0/1  <-->  IoT15:FastEthernet0
  SW3-P1:FastEthernet0/2  <-->  IoT11:FastEthernet0
  SW3-P1:FastEthernet0/3  <-->  IoT13:FastEthernet0
  SW3-P1:FastEthernet0/4  <-->  IoT12:FastEthernet0
  SW3-P1:FastEthernet0/5  <-->  IoT14:FastEthernet0
net0/2  <-->  I3RRHH1:FastEthernet0
  SW3-P3:FastEthernet0/4  <-->  IoT1:FastEthernet0
  SW3-P3:FastEthernet0/5  <-->  IoT2:FastEthernet0
  SW3-P3:FastEthernet0/6  <-->  IoT3:FastEthernet0
  SW3-P3:FastEthernet0/7  <-->  IoT4:FastEthernet0
  SW3-P3:FastEthernet0/8  <-->  IoT23:FastEthernet0
  SW3-P3:FastEthernet0/9  <-->  IoT24:FastEthernet0
  SW3-P3:FastEthernet0/10  <-->  IoT25:FastEthernet0
  SW3-P3:FastEthernet0/11  <-->  IoT35:FastEthernet0
  SW3-P3:FastEthernet0/12  <-->  IoT36:FastEthernet0
  SW3-P3:FastEthernet0/13  <-->  Proyector:FastEthernet0
  SW3-P3:FastEthernet0/14  <-->  IoT32:FastEthernet0
  SW3-P3:FastEthernet0/15  <-->  IoT31:FastEthernet0
  SW3-P3:FastEthernet0/16  <-->  IoT30:FastEthernet0
  SW3-P3:FastEthernet0/17  <-->  IoT26:FastEthernet0
  SW3-P3:FastEthernet0/18  <-->  IoT29:FastEthernet0
  SW3-P3:FastEthernet0/19  <-->  IoT28:FastEthernet0
  SW3-P3:FastEthernet0/20  <-->  IoT27:FastEthernet0
  SW-SUC-1:FastEthernet0/2  <-->  SPCRE2:FastEthernet0
  SW-SUC-1:FastEthernet0/3  <-->  SPCAJ1:FastEthernet0
  SW-SUC-1:FastEthernet0/4  <-->  SPCAJ2:FastEthernet0
  SW-SUC-1:FastEthernet0/5  <-->  SPTICs1:FastEthernet0
  SW-SUC-1:FastEthernet0/6  <-->  SPTICs2:FastEthernet0
  SW-SUC-1:FastEthernet0/7  <-->  SBOD:FastEthernet0
  SW-SUC-1:FastEthernet0/9  <-->  IP Phone40:Switch
  SW-SUC-1:FastEthernet0/10  <-->  IP Phone41:Switch
  SW-SUC-1:FastEthernet0/12  <-->  IP Phone42:Switch
ernet0/10  <-->  IoT46:FastEthernet0
  SW-SUC-2:FastEthernet0/11  <-->  IoT45:FastEthernet0
  SW-SUC-2:FastEthernet0/12  <-->  IoT44:FastEthernet0
  SW3-P1:FastEthernet0/7  <-->  IoT65:FastEthernet0
  SW3-P1:FastEthernet0/8  <-->  IoT61:FastEthernet0
  SW3-P1:FastEthernet0/9  <-->  IoT63:FastEthernet0
  SW3-P1:FastEthernet0/10  <-->  IoT64:FastEthernet0
  SW3-P3:FastEthernet0/21  <-->  IoT66:FastEthernet0
  SW3-P3:FastEthernet0/22  <-->  IoT68:FastEthernet0
  SW3-P3:FastEthernet0/23  <-->  IoT69:FastEthernet0
  SW1-P2:GigabitEthernet0/1  <-->  SW-CORE:GigabitEthernet1/0/2
  SW-CORE-S:GigabitEthernet0/1  <-->  R-Fabrica:FastEthernet0/0
  R-Matriz:FastEthernet0/0  <-->  SW-CORE:GigabitEthernet1/0/24
  SW1-P1:GigabitEthernet0/1  <-->  SW-CORE:GigabitEthernet1/0/1
  SW1-P3:GigabitEthernet0/1  <-->  SW-CORE:GigabitEthernet1/0/3
  SW-CORE-S:FastEthernet0/3  <-->  Switch17 SEGURIDAD:GigabitEthernet0/1
  SW-CORE-S:FastEthernet0/1  <-->  Switch15 ADMIN:GigabitEthernet0/1
  SW-CORE-S:FastEthernet0/2  <-->  Switch16 NAVE:GigabitEthern
thernet0  <-->  SW1-P1:FastEthernet0/7
  PT1AT2:FastEthernet0  <-->  SW1-P1:FastEthernet0/8
  P1AT1:FastEthernet0  <-->  SW1-P1:FastEthernet0/9
  P1AT3:FastEthernet0  <-->  SW1-P1:FastEthernet0/10
  P1AT4:FastEthernet0  <-->  SW1-P1:FastEthernet0/11
  P1AT5:FastEthernet0  <-->  SW1-P1:FastEthernet0/12
  P1AT6:FastEthernet0  <-->  SW1-P1:FastEthernet0/13
  P1AT8:FastEthernet0  <-->  SW1-P1:FastEthernet0/14
  P1AT7:FastEthernet0  <-->  SW1-P1:FastEthernet0/15
  P1AT10:FastEthernet0  <-->  SW1-P1:FastEthernet0/16
  P1AT9:FastEthernet0  <-->  SW1-P1:FastEthernet0/17
  P1AT11:FastEthernet0  <-->  SW1-P1:FastEthernet0/18
  P1AT12:FastEthernet0  <-->  SW1-P1:FastEthernet0/19
  P1AT13:FastEthernet0  <-->  SW1-P1:FastEthernet0/20
  P1AT14:FastEthernet0  <-->  SW1-P1:FastEthernet0/21
  I1AT1:FastEthernet0  <-->  SW1-P1:FastEthernet0/22
  P1APAT1:Port 0  <-->  SW1-P1:FastEthernet0/23
  AP1Cl:Port 0  <-->  SW1-P1:FastEthernet0/24
  <-->  SW2-P1:FastEthernet0/8
  IP Phone3:Switch  <-->  SW2-P1:FastEthernet0/9
  IP Phone4:Switch  <-->  SW2-P1:FastEthernet0/10
  IP Phone5:Switch  <-->  SW2-P1:FastEthernet0/11
  IP Phone6:Switch  <-->  SW2-P1:FastEthernet0/12
  IP Phone7:Switch  <-->  SW2-P1:FastEthernet0/13
  IP Phone10:Switch  <-->  SW2-P1:FastEthernet0/14
  IP Phone13:Switch  <-->  SW2-P1:FastEthernet0/15
  IP Phone16:Switch  <-->  SW2-P1:FastEthernet0/16
  IP Phone11:Switch  <-->  SW2-P1:FastEthernet0/17
  IP Phone14:Switch  <-->  SW2-P1:FastEthernet0/18
  IoT9:FastEthernet0  <-->  SW2-P1:FastEthernet0/20
  IoT10:FastEthernet0  <-->  SW2-P1:FastEthernet0/21
  IoT7:FastEthernet0  <-->  SW2-P1:FastEthernet0/22
  IoT6:FastEthernet0  <-->  SW2-P1:FastEthernet0/23
  IoT5:FastEthernet0  <-->  SW2-P1:FastEthernet0/24
  P3CON5:FastEthernet0  <-->  SW1-P3:FastEthernet0/1
  P3CON4:FastEthernet0  <-->  SW1-P3:FastEthernet0/2
net0  <-->  SW1-P3:FastEthernet0/5
  P3CON2:FastEthernet0  <-->  SW1-P3:FastEthernet0/6
  P3TICs2:FastEthernet0  <-->  SW1-P3:FastEthernet0/7
  P3TICs6:FastEthernet0  <-->  SW1-P3:FastEthernet0/8
  P3TICs4:FastEthernet0  <-->  SW1-P3:FastEthernet0/9
  P3TICs5:FastEthernet0  <-->  SW1-P3:FastEthernet0/10
  P3TICs3:FastEthernet0  <-->  SW1-P3:FastEthernet0/11
  P3TICs1:FastEthernet0  <-->  SW1-P3:FastEthernet0/12
  P3RRHH2:FastEthernet0  <-->  SW1-P3:FastEthernet0/13
  P3RRHH1:FastEthernet0  <-->  SW1-P3:FastEthernet0/14
  P3RRHH3:FastEthernet0  <-->  SW1-P3:FastEthernet0/15
  P3RRHH4:FastEthernet0  <-->  SW1-P3:FastEthernet0/16
  P3RRHH5:FastEthernet0  <-->  SW1-P3:FastEthernet0/17
  P3RRHH6:FastEthernet0  <-->  SW1-P3:FastEthernet0/18
  P3GER5:FastEthernet0  <-->  SW1-P3:FastEthernet0/19
  P3GER4:FastEthernet0  <-->  SW1-P3:FastEthernet0/20
  P3GER3:FastEthernet0  <-->  SW1-P3:FastEthernet0/21
  P3GER2:FastEthernet0  <-->  SW1-P3:FastEthernet0/22
  P3GER1:FastEthernet0  <-->  SW1-P3:FastEthernet0/23
  AP3Con1:Port 0  <-->  SW1-P3:FastEthernet0/24
  SW3-P1:FastEthernet0/24  <-->  AP1EMPL1:Port 0
  P2MON1:FastEthernet0  <-->  SW3-P2:FastEthernet0/1
  P2MON2:FastEthernet0  <-->  SW3-P2:FastEthernet0/2
  P2TICs1:FastEthernet0  <-->  SW3-P2:FastEthernet0/3
  P2TICs2:FastEthernet0  <-->  SW3-P2:FastEthernet0/4
  P2TICs3:FastEthernet0  <-->  SW3-P2:FastEthernet0/5
  P2TICs4:FastEthernet0  <-->  SW3-P2:FastEthernet0/6
  P2TICs5:FastEthernet0  <-->  SW3-P2:FastEthernet0/7
  P3INN1:FastEthernet0  <-->  SW3-P2:FastEthernet0/8
  P3INN2:FastEthernet0  <-->  SW3-P2:FastEthernet0/9
  P3INN3:FastEthernet0  <-->  SW3-P2:FastEthernet0/10
  P3INN4:FastEthernet0  <-->  SW3-P2:FastEthernet0/11
  IP Phone34(1):Switch  <-->  SW3-P2:FastEthernet0/12
  APCON1:Port 0  <-->  SW3-P2:FastEthernet0/24
  IoT1(1):FastEthernet0  <-->  SW3-P2:FastEthernet0/13
  IoT1(2):FastEthernet0  <-->  SW3-P2:FastEthernet0/14
  IoT4(1):FastEthernet0  <-->  SW3-P2:FastEthernet0/15
  SW3-P2:FastEthernet0/16  <-->  IoT0(1):FastEthernet0
  IoT3(1):FastEthernet0  <-->  SW3-P2:FastEthernet0/17
  P3INN5:FastEthernet0  <-->  SW2-P2:FastEthernet0/1
  P3INN8:FastEthernet0  <-->  SW2-P2:FastEthernet0/2
  SW2-P2:FastEthernet0/3  <-->  P3INN6:FastEthernet0
  P3INN7:FastEthernet0  <-->  SW2-P2:FastEthernet0/4
  P3INN9:FastEthernet0  <-->  SW2-P2:FastEthernet0/5
  P3INN10:FastEthernet0  <-->  SW2-P2:FastEthernet0/6
  IoT30(1):FastEthernet0  <-->  SW2-P2:FastEthernet0/14
  IoT58:FastEthernet0  <-->  SW2-P2:FastEthernet0/15
  IoT56:FastEthernet0  <-->  SW2-P2:FastEthernet0/16
  IoT24(2):FastEthernet0  <-->  SW2-P2:FastEthernet0/17
  IoT28(1):FastEthernet0  <-->  SW2-P2:FastEthernet0/18
 <-->  SW1-P2:FastEthernet0/5
  P3INN15:FastEthernet0  <-->  SW1-P2:FastEthernet0/6
  P3INN17:FastEthernet0  <-->  SW1-P2:FastEthernet0/7
  P3INN18:FastEthernet0  <-->  SW1-P2:FastEthernet0/8
  P3INN19:FastEthernet0  <-->  SW1-P2:FastEthernet0/9
  P3INN20:FastEthernet0  <-->  SW1-P2:FastEthernet0/10
  IP Phone55:Switch  <-->  SW1-P2:FastEthernet0/11
  SW1-P2:FastEthernet0/14  <-->  IP Phone21(1):Switch
  SW1-P2:FastEthernet0/13  <-->  IP Phone26(1):Switch
  SW1-P2:FastEthernet0/12  <-->  IP Phone56:Switch
  SW1-P2:FastEthernet0/15  <-->  IP Phone19(1):Switch
  SW1-P2:FastEthernet0/16  <-->  IP Phone24(1):Switch
  SW1-P2:FastEthernet0/17  <-->  IP Phone27(1):Switch
  SW1-P2:FastEthernet0/18  <-->  IP Phone29(1):Switch
  SW1-P2:FastEthernet0/19  <-->  IP Phone33(1):Switch
  IoT29(1):FastEthernet0  <-->  SW1-P2:FastEthernet0/20
  IoT2(1):FastEthernet0  <-->  SW1-P2:FastEthernet0/21
  IoT25(1):FastEthernet0  <-->  SW1-P2:FastEthernet0/22
  IoT23(1):FastEthernet0  <-->  SW1-P2:FastEthernet0/23
  SW2-P2:FastEthernet0/7  <-->  IP Phone30(1):Switch
  SW2-P2:FastEthernet0/8  <-->  IP Phone32(1):Switch
  SW2-P2:FastEthernet0/13  <-->  IP Phone23(1):Switch
  SW2-P2:FastEthernet0/12  <-->  IP Phone20(1):Switch
  SW2-P2:FastEthernet0/11  <-->  IP Phone31(1):Switch
  SW2-P2:FastEthernet0/10  <-->  IP Phone22(1):Switch
  SW2-P2:FastEthernet0/9  <-->  IP Phone25(1):Switch
  SW2-P3:FastEthernet0/12  <-->  IP Phone28:Switch
  <-->  IP Phone34:Switch
  SW2-P3:FastEthernet0/9  <-->  IP Phone31:Switch
  SW2-P3:FastEthernet0/10  <-->  IP Phone29:Switch
  SW2-P3:FastEthernet0/14  <-->  IP Phone25:Switch
  SW2-P3:FastEthernet0/13  <-->  IP Phone26:Switch
  SW2-P3:FastEthernet0/23  <-->  IP Phone24:Switch
  SW2-P3:FastEthernet0/22  <-->  IP Phone21:Switch
  SW2-P3:FastEthernet0/21  <-->  IP Phone20:Switch
  SW2-P3:FastEthernet0/19  <-->  IP Phone27:Switch
  SW2-P3:FastEthernet0/20  <-->  IP Phone22:Switch
  SW2-P3:FastEthernet0/18  <-->  IP Phone23:Switch
  SW2-P3:FastEthernet0/17  <-->  IP Phone19:Switch
  SW2-P3:FastEthernet0/16  <-->  IP Phone18:Switch
  SW2-P3:FastEthernet0/15  <-->  IP Phone17:Switch
  SPCRE1:FastEthernet0  <-->  SW-SUC-1:FastEthernet0/1
  IP Phone46:Switch  <-->  SW-SUC-1:FastEthernet0/8
  SAPVIS:Port 0  <-->  SW-SUC-1:FastEthernet0/24
  SW-SUC-1:GigabitEthernet0/2  <-->  SW-SUC-2:GigabitEthernet0
  SAPCaj:Port 0  <-->  SW-SUC-1:FastEthernet0/23
  SAPTICs:Port 0  <-->  SW-SUC-2:FastEthernet0/24
  IoT112:FastEthernet0  <-->  Switch17 SEGURIDAD:FastEthernet0/1
  IoT113(1):FastEthernet0  <-->  Switch17 SEGURIDAD:FastEthernet0/2
  IoT113:FastEthernet0  <-->  Switch17 SEGURIDAD:FastEthernet0/3
  IoT113(4):FastEthernet0  <-->  Switch17 SEGURIDAD:FastEthern
hernet0  <-->  Switch17 SEGURIDAD:FastEthernet0/11
  IoT0(2)(5)(2)(2):FastEthernet0  <-->  Switch17 SEGURIDAD:FastEthernet0/12
  IoT0(2)(5)(2)(3):FastEthernet0  <-->  Switch17 SEGURIDAD:FastEthernet0/13
  IoT0(2)(5)(2)(4):FastEthernet0  <-->  Switch17 SEGURIDAD:FastEthernet0/14
  IoT0(2)(5)(2)(5):FastEthernet0  <-->  Switch17 SEGURIDAD:FastEthernet0/15
  IoT0(2)(5)(2)(6):FastEthernet0  <-->  Switch17 SEGURIDAD:FastEthernet0/16
  IoT0(2)(5)(2)(7):FastEthernet0  <-->  Switch17 SEGURIDAD:FastEthernet0/17
  IoT0(2)(5)(2)(8):FastEthernet0  <-->  Switch17 SEGURIDAD:FastEthernet0/18
  IoT41(1):FastEthernet0  <-->  Switch17 SEGURIDAD:FastEthernet0/19
  IoT57:FastEthernet0  <-->  Switch17 SEGURIDAD:FastEthernet0/20
  FOFI1:FastEthernet0  <-->  Switch15 ADMIN:FastEthernet0/1
  FOFI3:FastEthernet0  <-->  Switch15 ADMIN:FastEthernet0/3
  FOFI4:FastEthernet0  <-->  Switch15 ADMIN:FastEthernet0/4
  FOFI5:FastEthernet0  <-->  Switch15 ADMIN:FastEthernet0/5
  FOFI6:FastEthernet0  <-->  Switch15 ADMIN:FastEthernet0/6
  FBOD1:FastEthernet0  <-->  Switch15 ADMIN:FastEthernet0/7
  FENF1:FastEthernet0  <-->  Switch15 ADMIN:FastEthernet0/8
  FSEC1:FastEthernet0  <-->  Switch15 ADMIN:FastEthernet0/9
  Switch15 ADMIN:FastEthernet0/11
  IP Phone49:Switch  <-->  Switch15 ADMIN:FastEthernet0/12
  IP Phone50:Switch  <-->  Switch15 ADMIN:FastEthernet0/13
  IP Phone51:Switch  <-->  Switch15 ADMIN:FastEthernet0/14
  IP Phone52:Switch  <-->  Switch15 ADMIN:FastEthernet0/15
  IP Phone53:Switch  <-->  Switch15 ADMIN:FastEthernet0/16
  IP Phone54:Switch  <-->  Switch15 ADMIN:FastEthernet0/17
  I1OFI:FastEthernet0  <-->  Switch15 ADMIN:FastEthernet0/18
  FAP1EMPL:Port 0  <-->  Switch15 ADMIN:FastEthernet0/24
  FAP2EMPLE:Port 0  <-->  Switch16 NAVE:FastEthernet0/24
  FAPINV1:Port 0  <-->  Switch16 NAVE:FastEthernet0/23
  IoT113(8):FastEthernet0  <-->  Switch16 NAVE:FastEthernet0/1
  IoT113(7):FastEthernet0  <-->  Switch16 NAVE:FastEthernet0/2
  IoT113(6):FastEthernet0  <-->  Switch16 NAVE:FastEthernet0/3
  IoT113(9):FastEthernet0  <-->  Switch16 NAVE:FastEthernet0/4
  IoT0(2):FastEthernet0  <-->  Switch16 NAVE:FastEthernet0/5
  IoT0(2)(1):FastEthernet0  <-->  Switch16 NAVE:FastEthernet0/6
  IoT0(2)(2):FastEthernet0  <-->  Switch16 NAVE:FastEthernet0/
  IoT0(2)(3):FastEthernet0  <-->  Switch16 NAVE:FastEthernet0/8
  IoT0(2)(4):FastEthernet0  <-->  Switch16 NAVE:FastEthernet0/9
  IoT0(2)(5):FastEthernet0  <-->  Switch16 NAVE:FastEthernet0/10
  IoT33(1)(1):FastEthernet0  <-->  Switch16 NAVE:FastEthernet0/11
  IoT111:FastEthernet0  <-->  Switch16 NAVE:FastEthernet0/12
  IoT110:FastEthernet0  <-->  Switch16 NAVE:FastEthernet0/13
  IoT39:FastEthernet0  <-->  SW-SUC-1:FastEthernet0/15
  Server VOZ:FastEthernet0/0  <-->  SW-CORE:GigabitEthernet1/0/23
  IoT41(2):FastEthernet0  <-->  SW-SUC-1:FastEthernet0/21
  R-Matriz:Serial0/3/0  <-->  R-Fabrica:Serial0/3/0
  R-Matriz:Serial0/3/1  <-->  R-Sucursal:Serial0/3/0
  R-Sucursal:Serial0/3/1  <-->  R-Fabrica:Serial0/3/1
  SW2-P3:GigabitEthernet0/2  <-->  SW-CORE:GigabitEthernet1/0/
  SW3-P3:GigabitEthernet0/1  <-->  SW-CORE:GigabitEthernet1/0/5
  SW2-P1:GigabitEthernet0/2  <-->  SW-CORE:GigabitEthernet1/0/6
  SW3-P2:GigabitEthernet0/1  <-->  SW-CORE:GigabitEthernet1/0/7
  SW3-P2:GigabitEthernet0/1  <-->  SW-CORE:GigabitEthernet1/0/8
  SW2-P2:GigabitEthernet0/2  <-->  SW-CORE:GigabitEthernet1/0/9
````
<!-- S1_LITERAL_END -->

</details>
