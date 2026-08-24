# CISCO-MCP — Topología física completa simplificada para IA

**Archivo de referencia:** `topologia_completa_IMP.md`  
**Propósito:** describir la topología física completa de Packet Tracer de forma directa y estructurada para que otra IA pueda reconstruir mentalmente la red, generar un prompt de implementación o correlacionar equipos físicos con el diseño lógico.

---

## 0. Regla de autoridad y correcciones

Este documento combina la descripción física original con las correcciones posteriores del levantamiento lógico final.

Correcciones que deben considerarse definitivas dentro de esta documentación:

```text
MLS3:
  teléfonos físicos = 2
  no 3

TOTAL ENDPOINTS:
  279
  no 280

RAMA ROUTER0:
  41 endpoints
  no 42
```

También se preservan los modelos observados posteriormente por CDP:

```text
MLS7 = Cisco 3650
MLS3 = Cisco 3650
MLS4 = Cisco 3650
MLS5 = Cisco 3560
MLS6 = Cisco 3560
```

No inferir conexiones exactas de puerto cuando el levantamiento solo confirmó el conjunto de dispositivos.

---

# 1. Topología física global

La red tiene tres routers Cisco 2811 formando un triángulo WAN y tres ramas LAN.

```text
                             Router4
                            Cisco 2811
                           /          \
                          /            \
                         /              \
               Router0 ---------------- Router3
              Cisco 2811              Cisco 2811
                  |                        |
                  |                        |
                 MLS7                   Switch3
          distribución Router0      acceso Router3

                  Router4
                     |
                  Switch10
             distribución Router4
          /        /       \        \
      Piso 1    Piso 2   Piso 3-A  Piso 3-B
```

Resumen por rama:

```text
Router4 → Switch10 → 4 bloques de acceso → 217 endpoints
Router0 → MLS7     → 4 switches secundarios → 41 endpoints
Router3 → Switch3  → acceso directo/APs → 21 endpoints

TOTAL = 279 endpoints
```

---

# 2. Núcleo WAN

```text
                         Router4
                       /         \
                      /           \
                   Router0 ----- Router3
```

Enlaces físicos seriales:

```text
Router4 S0/3/1 ↔ Router3 S0/3/1
Router3 S0/3/0 ↔ Router0 S0/3/1
Router4 S0/3/0 ↔ Router0 S0/3/0
```

El enlace físico R4-R0 existe, aunque su direccionamiento lógico está documentado como defectuoso en `diseno_logico_IMP.md`.

---

# 3. Rama física Router4

## 3.1 Distribución

```text
Router4 Fa0/0
      |
      |
Switch10 Gi0/1
```

Switch10 es el punto central de distribución de los Pisos 1, 2 y 3/Data Center.

```text
                              Router4
                                 |
                              Switch10
               ┌─────────┬───────┼───────┬─────────┐
               |         |               |         |
             Fa0/1     Fa0/2           Fa0/3     Fa0/4
               |         |               |         |
            Switch4   Switch6         Switch8   Switch0
            Piso 1    Piso 2          Piso 3-A  Piso 3-B
               |         |               |         |
            Switch5   Switch7         Switch9   Switch1
```

Enlaces:

| Origen | Destino |
|---|---|
| `Router4 Fa0/0` | `Switch10 Gi0/1` |
| `Switch10 Fa0/1` | `Switch4 Gi0/1` |
| `Switch10 Fa0/2` | `Switch6 Gi0/1` |
| `Switch10 Fa0/3` | `Switch8 Gi0/1` |
| `Switch10 Fa0/4` | `Switch0 Gi0/1` |
| `Switch4 Gi0/2` | `Switch5 Gi0/1` |
| `Switch6 Gi0/2` | `Switch7 Gi0/1` |
| `Switch8 Gi0/2` | `Switch9 Gi0/1` |
| `Switch0 Gi0/2` | `Switch1 Gi0/1` |

Los uplinks viven en los puertos Gigabit de cada switch de acceso, y los 24
puertos FastEthernet quedan integros para endpoints. `Switch10` conserva
`Fa0/1-Fa0/4` hacia abajo porque solo tiene dos puertos Gigabit y uno ya sube
a `Router4`; no alimenta ningun endpoint, asi que nada depende de ello.

---

# 4. Piso 1 — 65 endpoints

Equipos de infraestructura:

```text
Switch4
Switch5
Access Point4
Access Point5
Access Point6
```

Diagrama:

```text
                          Switch10
                             |
                           Switch4
              ┌──────────────┼──────────────┐
              |              |              |
           23 PCs           AP4          Switch5
                              |          /   |    \
                         4 Webcams  21 Phones AP5  AP6
                                             |    |
                                        11 Smoke 4 Motion

Switch5 además conecta 2 Printer-PT.
```

## Inventario Piso 1

| Tipo | Cantidad |
|---|---:|
| PC-PT | 23 |
| Cisco 7960 | 21 |
| Printer-PT | 2 |
| Webcam IoT | 4 |
| Smoke Detector | 11 |
| Motion Detector | 4 |
| **Total** | **65** |

### Puertos físicos relevantes

Switch4:

```text
Fa0/1-Fa0/22 → 22 PCs
Fa0/23        → AP4          (alimentado)
Fa0/24        → PC 23
Gi0/1         → uplink Switch10
Gi0/2         → Switch5
```

Switch5:

```text
Fa0/1-Fa0/21 → 21 teléfonos  (alimentados)
Gi0/1        → Switch4
```

Puertos físicos de acceso IoT/impresión conocidos como conjunto:

```text
Fa0/22   AP5    (alimentado)
Fa0/23   AP6    (alimentado)
Fa0/24   Printer-PT
Gi0/2    Printer-PT
```

Los 23 endpoints alimentados de `Switch5` -- 21 teléfonos y 2 access points --
caben en los 24 puertos de acceso que la evidencia mide como alimentados. Las
dos impresoras no requieren PoE, asi que una de ellas puede ocupar el segundo
puerto Gigabit sin reclamar energia que nadie observo.

Conectan:

```text
2 Printer-PT
AP5
AP6
```

No está determinada la correspondencia individual puerto↔dispositivo dentro de esos cuatro.

---

# 5. Piso 2 — 53 endpoints

Infraestructura:

```text
Switch6
Switch7
1 AP de webcams
Access Point2
Access Point3
```

Diagrama:

```text
                          Switch10
                             |
                           Switch6
                    ┌────────┼─────────┐
                    |        |         |
                 20 PCs     AP      Switch7
                             |      /   |    \
                        4 Webcams 14 Phones AP2 AP3
                                           |   |
                                      4 Motion 9 Smoke

Switch7 además conecta 2 Printer-PT.
```

Inventario:

| Tipo | Cantidad |
|---|---:|
| PC-PT | 20 |
| Cisco 7960 | 14 |
| Printer-PT | 2 |
| Webcam IoT | 4 |
| Motion Detector | 4 |
| Smoke Detector | 9 |
| **Total** | **53** |

Puertos principales:

Switch6:

```text
Fa0/1-Fa0/20 → 20 PCs
Fa0/21        → AP de 4 webcams  (alimentado)
Gi0/1         → Switch10
Gi0/2         → Switch7
```

Switch7:

```text
Fa0/1-Fa0/14 → 14 teléfonos  (alimentados)
Gi0/1        → Switch6
```

Puertos IoT/impresión como conjunto:

```text
Fa0/15   AP2    (alimentado)
Fa0/16   AP3    (alimentado)
Fa0/22   Printer-PT
Fa0/23   Printer-PT
```

Conectan:

```text
2 Printer-PT
AP2
AP3
```

La asociación individual puerto↔dispositivo no quedó determinada.

---

# 6. Piso 3 / Data Center — 99 endpoints

Tiene dos bloques físicos.

```text
                       Switch10
                      /        \
                     /          \
                 Switch8       Switch0
                    |             |
                 Switch9       Switch1
                Bloque A       Bloque B
```

---

## 6.1 Bloque A — 48 endpoints

Infraestructura:

```text
Switch8
Switch9
AP0
AP7
AP8
```

Diagrama:

```text
                           Switch8
                    ┌─────────┼─────────┐
                    |         |         |
                  23 PCs     AP0      Switch9
                              |       /  |   \
                         4 Webcams 3 Phones AP7 AP8
                                           |    |
                                      10 Smoke  ├─ 4 Motion
                                                └─ 2 Humiture

Switch9 además conecta 2 Printer-PT.
```

Inventario:

| Tipo | Cantidad |
|---|---:|
| PC-PT | 23 |
| Cisco 7960 | 3 |
| Printer-PT | 2 |
| Webcam IoT | 4 |
| Smoke Detector | 10 |
| Motion Detector | 4 |
| Humiture Monitor | 2 |
| **Total** | **48** |

Puertos:

Switch8:

```text
Fa0/1-Fa0/22 → 22 PCs
Fa0/23        → AP0          (alimentado)
Fa0/24        → PC 23
Gi0/1         → Switch10
Gi0/2         → Switch9
```

Switch9:

```text
Fa0/1-Fa0/3 → 3 teléfonos  (alimentados)
Gi0/1       → Switch8
```

IoT/impresión:

```text
Fa0/4    AP7    (alimentado)
Fa0/5    AP8    (alimentado)
Fa0/22   Printer-PT
Fa0/23   Printer-PT
```

corresponden al conjunto:

```text
2 Printer-PT
AP7
AP8
```

---

## 6.2 Bloque B — 51 endpoints

Infraestructura:

```text
Switch0
Switch1
AP12
AP13
AP14
```

Diagrama:

```text
                           Switch0
                    ┌─────────┼─────────┐
                    |         |         |
                  20 PCs     AP12     Switch1
                              |       /   |    \
                         4 Webcams 13 Phones AP13 AP14
                                             |    |
                                         8 Smoke 4 Motion

Switch1 además conecta 2 Printer-PT.
```

Inventario:

| Tipo | Cantidad |
|---|---:|
| PC-PT | 20 |
| Cisco 7960 | 13 |
| Printer-PT | 2 |
| Webcam IoT | 4 |
| Smoke Detector | 8 |
| Motion Detector | 4 |
| **Total** | **51** |

Puertos:

Switch0:

```text
Fa0/1-Fa0/20 → 20 PCs
Fa0/21        → AP12         (alimentado)
Gi0/1         → Switch10
Gi0/2         → Switch1
```

Switch1:

```text
Fa0/1-Fa0/13 → 13 teléfonos  (alimentados)
Gi0/1        → Switch0
```

IoT/impresión:

```text
Fa0/14   AP13   (alimentado)
Fa0/15   AP14   (alimentado)
Fa0/22   Printer-PT
Fa0/23   Printer-PT
```

corresponden al conjunto:

```text
2 Printer-PT
AP13
AP14
```

---

# 7. Resumen de rama Router4

```text
Piso 1  = 65
Piso 2  = 53
Piso 3  = 99
----------------
TOTAL   = 217 endpoints
```

Por tipo:

| Tipo | Cantidad |
|---|---:|
| PCs | 86 |
| Teléfonos | 51 |
| Impresoras | 8 |
| Webcams | 16 |
| Smoke Detectors | 38 |
| Motion Detectors | 16 |
| Humiture Monitors | 2 |
| **Total** | **217** |

---

# 8. Rama física Router0 — 41 endpoints

## 8.1 Distribución

```text
Router0 Fa0/0
      |
      |
MLS7 Gi1/0/5
```

MLS7 distribuye hacia cuatro switches:

```text
                         Router0
                            |
                           MLS7
             ┌──────────────┼──────────────┐
             |       |             |       |
            MLS3    MLS6          MLS5    MLS4
```

Enlaces exactos:

| Puerto MLS7 | Equipo remoto | Puerto remoto |
|---|---|---|
| `Gi1/0/1` | MLS3 | `Gi1/0/1` |
| `Gi1/0/2` | MLS6 | `Gi0/1` |
| `Gi1/0/3` | MLS5 | `Gi0/1` |
| `Gi1/0/4` | MLS4 | `Gi1/0/1` |
| `Gi1/0/5` | Router0 | `Fa0/0` |

Modelos observados:

```text
MLS7 → Cisco 3650
MLS3 → Cisco 3650
MLS4 → Cisco 3650
MLS5 → Cisco 3560
MLS6 → Cisco 3560
```

---

# 9. MLS3 — 8 endpoints

Inventario físico corregido:

```text
2 Cisco 7960
2 PC-PT
AP9
  ├── 2 Motion Detector
  ├── 1 Webcam
  └── 1 Temperature Monitor
```

Total:

```text
2 + 2 + 4 = 8 endpoints
```

Diagrama:

```text
                            MLS3
                    ┌────────┼────────┐
                    |        |        |
                Phone+PC Phone+PC    AP9
                                      |
                           ┌──────────┼──────────┐
                           |          |          |
                       2 Motion    1 Webcam   1 Temp
```

Los dos PCs están conectados a través de los dos teléfonos IP.

Puertos confirmados:

```text
Gi1/0/2 → teléfono + PC
Gi1/0/3 → teléfono + PC
Gi1/0/4 → AP9
Gi1/0/1 → MLS7
```

---

# 10. MLS4 — 10 endpoints

```text
MLS4
├── 1 Cisco 7960
└── AP10
    ├── 8 Webcam IoT
    └── 1 Temperature Monitor
```

Total:

```text
1 + 9 = 10 endpoints
```

Puertos:

```text
Gi1/0/1 → MLS7
Gi1/0/2 → teléfono
Gi1/0/3 → AP10
```

---

# 11. MLS5 — 8 endpoints

```text
MLS5
└── 8 Cisco 7960
```

Puertos:

```text
Fa0/1-Fa0/8 → 8 teléfonos
Gi0/1       → MLS7
```

No tiene endpoints IoT locales documentados.

Modelo observado:

```text
Cisco 3560
```

---

# 12. MLS6 — 15 endpoints

```text
MLS6
├── 10 PC-PT
├── 2 Laptop-PT
└── AP11
    ├── 1 Smoke Detector
    ├── 1 Webcam
    └── 1 Motion Detector
```

Total:

```text
12 DATA + 3 IoT = 15
```

Puertos:

```text
Fa0/1-Fa0/12 → 12 endpoints DATA
Fa0/13       → AP11
Gi0/1        → MLS7
```

Modelo observado:

```text
Cisco 3560
```

---

# 13. Resumen rama Router0

```text
MLS3 = 8
MLS4 = 10
MLS5 = 8
MLS6 = 15
-------------
TOTAL = 41
```

Por tipo:

| Tipo | Cantidad |
|---|---:|
| PC-PT | 12 |
| Laptop-PT | 2 |
| Cisco 7960 | 11 |
| Webcam | 10 |
| Motion Detector | 3 |
| Smoke Detector | 1 |
| Temperature Monitor | 2 |
| **Total** | **41** |

---

# 14. Rama física Router3 — 21 endpoints

Conexión:

```text
Router3 Fa0/0
      |
      |
Switch3 Fa0/15
```

Topología:

```text
                         Router3
                            |
                         Switch3
       ┌───────────┬────────┼────────┬──────────┐
       |           |        |        |          |
     6 PCs      1 Laptop 7 Phones  AP0(1)    AP2(1)
                                  |             |
                              3 Smoke     ┌─────┴─────┐
                                          |           |
                                      3 Motion     1 Temp
```

Inventario:

| Tipo | Cantidad |
|---|---:|
| PC-PT | 6 |
| Laptop-PT | 1 |
| Cisco 7960 | 7 |
| Smoke Detector | 3 |
| Motion Detector | 3 |
| Temperature Monitor | 1 |
| **Total** | **21** |

Puertos:

```text
Fa0/1-Fa0/6 → 6 PCs
Fa0/14      → 1 Laptop
Fa0/7-Fa0/13 → 7 teléfonos  (alimentados)
Fa0/15-Fa0/16 → AP0(1) y AP2(1)  (alimentados)
Gi0/1       → Router3
```

No se determinó:

```text
cuál AP usa Gi0/1
cuál AP usa Gi0/2
```

---

# 15. Inventario físico global corregido

## Endpoints

| Tipo | Cantidad |
|---|---:|
| PC-PT | 104 |
| Laptop-PT | 3 |
| Cisco 7960 | 69 |
| Printer-PT | 8 |
| Webcam IoT | 26 |
| Smoke Detector | 42 |
| Motion Detector | 22 |
| Humiture Monitor | 2 |
| Temperature Monitor | 3 |
| **TOTAL** | **279** |

Por rama:

```text
Router4 = 217
Router0 = 41
Router3 = 21
----------------
TOTAL   = 279
```

---

# 16. Infraestructura global

## Routers

```text
3 Cisco 2811
├── Router0
├── Router3
└── Router4
```

## Switches de acceso

```text
Switch10  → Cisco 2960-24TT   (distribucion, sin PoE)

Piso 1:
  Switch4 → Cisco 3560-24PS
  Switch5 → Cisco 3560-24PS

Piso 2:
  Switch6 → Cisco 3560-24PS
  Switch7 → Cisco 3560-24PS

Piso 3:
  Switch8 → Cisco 3560-24PS
  Switch9 → Cisco 3560-24PS
  Switch0 → Cisco 3560-24PS
  Switch1 → Cisco 3560-24PS

Rama Router3:
  Switch3 → Cisco 3560-24PS
```

Total:

```text
1 Cisco 2960-24TT
9 Cisco 3560-24PS
```

### Por que los switches de acceso son PoE

Estos nueve switches alimentan telefonos IP y access points. La medicion
exacta sobre Packet Tracer `9.0.1.0858` decide el modelo, no el nombre:

```text
2960-24TT → supports_poe = UNSUPPORTED (verificado)
             24 puertos de acceso con estado de energia administrativo y
             de runtime completo en OFF
3560-24PS → supports_poe = SUPPORTED,  24 puertos de acceso alimentados
3650-24PS → supports_poe = SUPPORTED,  24 puertos de acceso alimentados
```

El `2960-24TT` no entrega PoE, igual que el chasis real: las variantes con
PoE de esa familia son `-PC` y `-LT`, no `-TT`. Un diseño que colgara 21
telefonos de un `Switch5` 2960-24TT no era implementable, solo no verificado.

`Switch10` no alimenta ningun endpoint, asi que conserva su `2960-24TT`.

### Puertos de acceso y uplinks

Los uplinks de infraestructura usan los puertos Gigabit; los endpoints usan
los 24 puertos FastEthernet de acceso. Antes ocurria al reves -- los access
points colgaban de `GigabitEthernet0/1-0/2` mientras los uplinks ocupaban
`FastEthernet0/23-0/24` -- y esa inversion es la que dejaba dispositivos
alimentados en puertos que la evidencia de PoE no cubre: el presupuesto
medido es de 24 puertos **de acceso**, y un uplink no alimenta nada.

```text
uplink de distribucion  → GigabitEthernet0/1
uplink entre parejas    → GigabitEthernet0/2 (lado superior)
endpoints               → FastEthernet0/1..24
```

## Switches multicapa de rama Router0

```text
MLS7 → Cisco 3650
MLS3 → Cisco 3650
MLS4 → Cisco 3650
MLS5 → Cisco 3560
MLS6 → Cisco 3560
```

Total:

```text
5 multilayer switches
```

## Access Points

```text
Rama Router4 = 12
Rama Router0 = 3
Rama Router3 = 2

TOTAL = 17 AccessPoint-PT
```

---

# 17. Mapa físico completo compacto

```text
                                      Router4
                                    /         \
                                   /           \
                              Router0 -------- Router3
                                 |                |
                                MLS7            Switch3
                      ┌──────────┼──────────┐      |
                      |      |       |      |     ├─ 6 PCs
                    MLS3   MLS6    MLS5   MLS4    ├─ 1 Laptop
                      |      |       |      |     ├─ 7 Phones
                  8 ep.  15 ep.   8 ep. 10 ep.   ├─ AP0(1) → 3 Smoke
                                                 └─ AP2(1) → 3 Motion + 1 Temp

                                      Router4
                                         |
                                      Switch10
             ┌───────────────────────────┼───────────────────────────┐
             |                           |                           |
           Piso 1                      Piso 2                    Piso 3
             |                           |                    ┌──────┴──────┐
          Switch4                     Switch6               Switch8       Switch0
             |                           |                    |             |
          Switch5                     Switch7               Switch9       Switch1
             |                           |                    |             |
         65 endpoints                 53 endpoints        48 endpoints   51 endpoints
```

---

# 18. Relaciones físicas que una IA debe conservar

```text
Router4 owns physical branch:
  Switch10
  → Switch4/Switch5
  → Switch6/Switch7
  → Switch8/Switch9
  → Switch0/Switch1

Router0 owns physical branch:
  MLS7
  → MLS3
  → MLS4
  → MLS5
  → MLS6

Router3 owns physical branch:
  Switch3

Router4, Router0, Router3:
  form WAN triangle
```

No mover endpoints de una rama a otra al generar una configuración.

---

# 19. Conexiones no completamente resueltas

La topología está globalmente levantada, pero hay asociaciones puntuales que no se conocen con precisión.

## Piso 1 / Switch5

El conjunto:

```text
Fa0/22
Fa0/23
Gi0/1
Gi0/2
```

corresponde a:

```text
2 Printer-PT
AP5
AP6
```

No se conoce el mapeo uno-a-uno.

## Piso 2 / Switch7

El mismo conjunto lógico de cuatro puertos corresponde a:

```text
2 Printer-PT
AP2
AP3
```

Sin mapeo individual confirmado.

## Piso 3-A / Switch9

Cuatro puertos VLAN 30 corresponden a:

```text
2 Printer-PT
AP7
AP8
```

Sin mapeo individual confirmado.

## Piso 3-B / Switch1

Cuatro puertos VLAN 30 corresponden a:

```text
2 Printer-PT
AP13
AP14
```

Sin mapeo individual confirmado.

## Router3 / Switch3

```text
Gi0/1
Gi0/2
```

conectan:

```text
AP0(1)
AP2(1)
```

pero no se conoce qué AP usa qué puerto.

Una IA no debe inventar estas correspondencias si no las consulta en Packet Tracer.

---

# 20. Qué no representa este documento

Este archivo describe principalmente:

```text
equipos
jerarquía
enlaces
endpoints
cantidades
puertos físicos confirmados
```

Para:

```text
VLANs
direccionamiento
gateways
DHCP
CME
STP
WAN IP
routing
defectos lógicos
```

usar `diseno_logico_IMP.md`.

---

# 21. Resumen machine-friendly

```text
CORE:
  routers:
    - Router4
    - Router0
    - Router3
  topology: triangle

BRANCH_ROUTER4:
  distribution: Switch10
  blocks:
    Piso1:
      switches: [Switch4, Switch5]
      endpoints: 65
    Piso2:
      switches: [Switch6, Switch7]
      endpoints: 53
    Piso3A:
      switches: [Switch8, Switch9]
      endpoints: 48
    Piso3B:
      switches: [Switch0, Switch1]
      endpoints: 51
  total_endpoints: 217

BRANCH_ROUTER0:
  distribution: MLS7
  blocks:
    MLS3: 8
    MLS4: 10
    MLS5: 8
    MLS6: 15
  total_endpoints: 41

BRANCH_ROUTER3:
  distribution: Switch3
  total_endpoints: 21

TOTAL_ENDPOINTS: 279

ACCESS_POINTS:
  total: 17

SWITCHES_2960:
  total: 10

MULTILAYER_SWITCHES:
  total: 5
  observed_models:
    MLS7: 3650
    MLS3: 3650
    MLS4: 3650
    MLS5: 3560
    MLS6: 3560
```

---

# 22. Uso recomendado por otra IA

Una IA que vaya a generar un prompt de construcción/configuración debe:

1. leer primero este archivo para entender **qué dispositivos existen y cómo están conectados**;
2. leer después `diseno_logico_IMP.md` para asignar VLANs, IPs, gateways y servicios;
3. mantener los nombres exactos de routers/switches porque corresponden a la topología existente;
4. no inventar puertos individuales donde este archivo marque la asociación como no determinada;
5. conservar el total corregido de **279 endpoints**;
6. tratar cualquier cambio físico como una modificación explícita de la topología, no como una corrección implícita.
