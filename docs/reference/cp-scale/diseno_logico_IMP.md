# CISCO-MCP — Diseño lógico simplificado para IA

**Archivo de referencia:** `diseno_logico_IMP.md`  
**Propósito:** describir el diseño lógico real de la topología de forma compacta, inequívoca y suficiente para que otra IA pueda planificar, configurar o validar la red sin tener que reconstruir el levantamiento histórico.

---

## 0. Reglas de interpretación

1. Este documento describe el **estado lógico documentado**, no una propuesta ideal.
2. Las afirmaciones marcadas como `CONFIRMADO` provienen del levantamiento actual.
3. Las marcadas como `DEFECTO` son problemas observados y no deben corregirse silenciosamente al interpretar la topología.
4. Las marcadas como `NO OBSERVADO` o `NO DETERMINADO` no deben convertirse en hechos por inferencia.
5. Cuando el inventario físico antiguo y el levantamiento lógico corregido discrepan, se adopta la corrección explícita del levantamiento lógico final:
   - MLS3 tiene **2 teléfonos**, no 3.
   - la red tiene **279 endpoints**, no 280.
6. No asumir routing dinámico, rutas estáticas, SVIs, redundancia lógica o servicios que no estén explícitamente documentados.

---

# 1. Vista lógica global

La red tiene tres dominios LAN principales, uno por router:

```text
                           Router4
                        dominio 172.16
                         /       \
                        /         \
                       /           \
              Router0 ------------- Router3
           dominio 172.18        dominio 172.17
```

Los tres routers son Cisco 2811 y forman físicamente un triángulo WAN.

Cada dominio utiliza las mismas VLAN funcionales:

| VLAN | Función |
|---:|---|
| 10 | DATA / PCs / laptops |
| 20 | VOICE / teléfonos IP |
| 30 | IoT / impresoras / sensores |

El patrón de direccionamiento es:

```text
Router4 → 172.16.<VLAN>.0/24
Router3 → 172.17.<VLAN>.0/24
Router0 → 172.18.<VLAN>.0/24
```

El gateway de cada VLAN es siempre `.1`.

---

# 2. Plan de direccionamiento LAN

## 2.1 Rama Router4

| VLAN | Red | Gateway |
|---:|---|---|
| 10 | `172.16.10.0/24` | `172.16.10.1` |
| 20 | `172.16.20.0/24` | `172.16.20.1` |
| 30 | `172.16.30.0/24` | `172.16.30.1` |

Router-on-a-Stick:

```text
Router4 Fa0/0.10 → 172.16.10.1/24
Router4 Fa0/0.20 → 172.16.20.1/24
Router4 Fa0/0.30 → 172.16.30.1/24
```

## 2.2 Rama Router3

| VLAN | Red | Gateway |
|---:|---|---|
| 10 | `172.17.10.0/24` | `172.17.10.1` |
| 20 | `172.17.20.0/24` | `172.17.20.1` |
| 30 | `172.17.30.0/24` | `172.17.30.1` |

Router-on-a-Stick:

```text
Router3 Fa0/0.10 → 172.17.10.1/24
Router3 Fa0/0.20 → 172.17.20.1/24
Router3 Fa0/0.30 → 172.17.30.1/24
```

## 2.3 Rama Router0

| VLAN | Red | Gateway |
|---:|---|---|
| 10 | `172.18.10.0/24` | `172.18.10.1` |
| 20 | `172.18.20.0/24` | `172.18.20.1` |
| 30 | `172.18.30.0/24` | `172.18.30.1` |

Router-on-a-Stick:

```text
Router0 Fa0/0.10 → 172.18.10.1/24
Router0 Fa0/0.20 → 172.18.20.1/24
Router0 Fa0/0.30 → 172.18.30.1/24
```

---

# 3. VLANs y reglas funcionales

## VLAN 10 — DATA

Usada por:

- PC-PT;
- Laptop-PT;
- puerto de datos detrás de teléfonos IP cuando corresponde.

## VLAN 20 — VOICE

Usada por:

- Cisco 7960;
- señalización/registro de telefonía IP.

Los puertos con teléfono normalmente combinan:

```text
switchport access vlan 10
switchport voice vlan 20
```

Por tanto:

```text
PC detrás del teléfono → VLAN 10
Teléfono IP            → VLAN 20
```

## VLAN 30 — IOT / impresión

Usada por:

- AccessPoint-PT que concentran sensores;
- cámaras/webcams;
- detectores de humo;
- detectores de movimiento;
- Temperature Monitor;
- Humiture Monitor;
- impresoras Printer-PT.

---

# 4. DHCP

Los tres routers proveen DHCP para sus respectivas VLAN 10, 20 y 30 siguiendo el mismo patrón.

## Rama Router4

```text
DATA:
  pool: PCs
  network: 172.16.10.0/24
  gateway: 172.16.10.1

VOICE:
  pool: TELEFONOS
  network: 172.16.20.0/24
  gateway: 172.16.20.1
  option 150: 172.16.20.1

IOT:
  pool: IOT
  network: 172.16.30.0/24
  gateway: 172.16.30.1
```

## Rama Router3

Mismo patrón sobre:

```text
172.17.10.0/24
172.17.20.0/24
172.17.30.0/24
```

Option 150 de voz:

```text
172.17.20.1
```

## Rama Router0

Mismo patrón sobre:

```text
172.18.10.0/24
172.18.20.0/24
172.18.30.0/24
```

Option 150 de voz:

```text
172.18.20.1
```

En las redes documentadas se reservan las direcciones:

```text
.1 - .10
```

DNS documentado:

```text
8.8.8.8
```

---

# 5. Telefonía CME

## Router4

```text
CME address: 172.16.20.1:2000
max-ephones: 42
max-dn:      42
```

Inventario físico de su rama:

```text
42 teléfonos
```

Estado:

```text
CORREGIDO:
42 teléfonos físicos = 42 ephones configurables.
9 teléfonos reasignados a la rama Router0.
```

La capacidad y el inventario de Router4 ahora coinciden.

## Router3

```text
CME address: 172.17.20.1:2000
max-ephones: 7
max-dn:      7
extensiones: 801-807
```

Inventario físico:

```text
7 teléfonos
```

Estado:

```text
CONFIRMADO: capacidad e inventario coinciden.
```

## Router0

```text
CME address: 172.18.20.1:2000
max-ephones: 20
max-dn:      20
extensiones: 901-920
```

Inventario físico corregido:

```text
20 teléfonos
```

Nueve teléfonos proceden de la reasignación canónica de capacidad desde
Router4; todos permanecen dentro de la VLAN VOICE de su nueva rama.

---

# 6. Backbone WAN

## 6.1 Router4 ↔ Router3

```text
Red: 10.0.0.4/30

Router4 S0/3/1 = 10.0.0.5/30
Router3 S0/3/1 = 10.0.0.6/30
```

Estado:

```text
CONFIRMADO: direccionamiento consistente.
```

## 6.2 Router3 ↔ Router0

```text
Red: 10.0.0.8/30

Router3 S0/3/0 = 10.0.0.9/30
Router0 S0/3/1 = 10.0.0.10/30
```

Prueba documentada:

```text
Router0 → 10.0.0.9
5/5 respuestas
100 % éxito
```

Estado:

```text
CONFIRMADO: enlace funcional en la prueba documentada.
```

## 6.3 Router4 ↔ Router0

Configuración observada:

```text
Router4 S0/3/0 = 10.0.0.1/30
Router0 S0/3/0 = 10.0.0.5/30
```

Esto es inconsistente porque los extremos no están en la misma `/30`.

Prueba:

```text
Router0 → 10.0.0.1
0/5
0 % éxito
```

Asignación coherente con el esquema documentado:

```text
Red: 10.0.0.0/30
Router4 = 10.0.0.1/30
Router0 = 10.0.0.2/30
```

Estado:

```text
BACKBONE-IP-001 = DEFECTO CONFIRMADO
```

No tratar `10.0.0.2` como configuración actual; es la corrección esperada.

---

# 7. Routing entre dominios

Las tablas revisadas mostraron únicamente:

```text
C = Connected
L = Local
```

No se observaron:

```text
R = RIP
D = EIGRP
O = OSPF
S = Static
```

Tampoco quedó documentado un proceso de routing dinámico activo o rutas estáticas que conecten las tres ramas.

Por tanto:

```text
ROUTING-OBS-001

172.16.x.x
172.17.x.x
172.18.x.x

NO tienen routing inter-router confirmado en el estado documentado.
```

Importante para una IA:

- no asumir EIGRP/OSPF/RIP solo porque el backbone sea triangular;
- no asumir conectividad extremo a extremo entre las tres ramas;
- cualquier protocolo de routing futuro debe considerarse configuración por implementar/validar, no estado ya existente.

---

# 8. Trunks principales

Todos los enlaces siguientes transportan VLAN 10, 20 y 30 salvo donde se indique una observación especial.

## Rama Router4

```text
Router4 Fa0/0
 ↕ trunk 10/20/30
Switch10 Gi0/1
```

Distribución:

```text
Switch10 Fa0/1 ↔ Switch4 Fa0/23
Switch10 Fa0/2 ↔ Switch6 Fa0/23
Switch10 Fa0/3 ↔ Switch8 Fa0/23
Switch10 Fa0/4 ↔ Switch0 Fa0/23
```

Downlinks internos:

```text
Switch4 Fa0/24 ↔ Switch5 Fa0/24
Switch6 Fa0/24 ↔ Switch7 Fa0/24
Switch8 Fa0/24 ↔ Switch9 Fa0/24
Switch0 Fa0/24 ↔ Switch1 Fa0/24
```

## Rama Router0

```text
Router0 Fa0/0
 ↕ trunk 10/20/30
MLS7 Gi1/0/5
```

Distribución:

```text
MLS7 Gi1/0/1 ↔ MLS3 Gi1/0/1
MLS7 Gi1/0/2 ↔ MLS6 Gi0/1
MLS7 Gi1/0/3 ↔ MLS5 Gi0/1
MLS7 Gi1/0/4 ↔ MLS4 Gi1/0/1
```

### Observación MLS5 / MLS6

En MLS5 y MLS6:

```text
mode: auto
status: trunking
allowed local: 1-1005
```

En MLS7 los extremos están restringidos explícitamente a:

```text
10,20,30
```

Estado:

```text
TRUNK-OBS-001
El trunk funciona, pero la política/configuración no es simétrica.
```

## Rama Router3

```text
Router3 Fa0/0
 ↕ trunk 10/20/30
Switch3 Fa0/15
```

---

# 9. STP / PVST

Se utiliza PVST.

## Rama Router4

Root Bridge observado para VLAN 1, 10, 20 y 30:

```text
Switch8
MAC 0001.4342.3854
```

Costos observados:

| Switch | Root Cost |
|---|---:|
| Switch8 | 0 |
| Switch10 | 19 |
| Switch9 | 19 |
| Switch4 | 38 |
| Switch6 | 38 |
| Switch0 | 38 |
| Switch5 | 57 |
| Switch7 | 57 |
| Switch1 | 57 |

Árbol simplificado:

```text
                    Switch8
                    STP ROOT
                  /          \
             Switch10       Switch9
          /      |      \
      Switch4 Switch6 Switch0
         |       |       |
      Switch5 Switch7 Switch1
```

No se observó tuning explícito de prioridad STP en los running-config revisados.

## Rama Router0

Root Bridge:

```text
MLS3
MAC 0002.174B.2BBB
```

Costos:

| Equipo | Root Cost |
|---|---:|
| MLS3 | 0 |
| MLS7 | 4 |
| MLS4 | 8 |
| MLS5 | 8 |
| MLS6 | 8 |

Árbol:

```text
                MLS3
               STP ROOT
                  |
                 MLS7
             /     |     \
           MLS6   MLS5   MLS4
```

## Rama Router3

Root Bridge:

```text
Switch3
MAC 0060.4726.8C16
```

Switch3 es root observado para VLAN 1, 10, 20 y 30.

---

# 10. Función L3 de los switches multicapa

Aunque la rama Router0 contiene switches multicapa, no se observó routing L3 activo en ellos.

En MLS7:

```text
Vlan1 → sin IP / shutdown
SVI VLAN10 → no observada
SVI VLAN20 → no observada
SVI VLAN30 → no observada
show ip route → sin rutas
```

Por tanto, en el estado documentado:

```text
MLS7 / MLS3 / MLS4 / MLS5 / MLS6
→ switching/distribución L2

Router0
→ gateway/routing inter-VLAN mediante Router-on-a-Stick
```

No asumir SVIs o routing en los multilayer switches.

---

# 11. Mapa lógico por rama

## 11.1 Rama Router4

```text
                           Router4
                  gateways 172.16.x.1
                             |
                    trunk VLAN 10/20/30
                             |
                         Switch10
             ┌────────┬──────┼──────┬────────┐
             │        │             │        │
          Switch4   Switch6       Switch8   Switch0
             │        │             │        │
          Switch5   Switch7       Switch9   Switch1
             │        │             │        │
          Piso 1    Piso 2        Piso 3-A  Piso 3-B
```

Todo el dominio comparte:

```text
DATA  = 172.16.10.0/24
VOICE = 172.16.20.0/24
IOT   = 172.16.30.0/24
```

## 11.2 Rama Router0

```text
                           Router0
                  gateways 172.18.x.1
                             |
                    trunk VLAN 10/20/30
                             |
                            MLS7
              ┌────────┬─────┼─────┬────────┐
              │        │           │        │
             MLS3     MLS6        MLS5     MLS4
```

Todo el dominio comparte:

```text
DATA  = 172.18.10.0/24
VOICE = 172.18.20.0/24
IOT   = 172.18.30.0/24
```

## 11.3 Rama Router3

```text
                           Router3
                  gateways 172.17.x.1
                             |
                    trunk VLAN 10/20/30
                             |
                          Switch3
                  ┌──────────┼──────────┐
                  │          │          │
                DATA       VOICE       IOT
```

Todo el dominio comparte:

```text
DATA  = 172.17.10.0/24
VOICE = 172.17.20.0/24
IOT   = 172.17.30.0/24
```

---

# 12. Estado lógico que una IA debe preservar

## CONFIRMADO

```text
3 routers Cisco 2811
3 dominios LAN
VLAN 10 = DATA
VLAN 20 = VOICE
VLAN 30 = IOT/impresión

Router4 → 172.16.x.x
Router3 → 172.17.x.x
Router0 → 172.18.x.x

Router-on-a-Stick en los tres routers
DHCP en los tres routers
CME en los tres routers

PVST
Root Router4 branch = Switch8
Root Router0 branch = MLS3
Root Router3 branch = Switch3

RIPv2/OSPF/EIGRP NO deben asumirse como configuración actual.
```

## DEFECTOS / OBSERVACIONES

```text
BACKBONE-IP-001
R0-R4 tiene direccionamiento /30 incorrecto.

ROUTING-OBS-001
No hay routing inter-router confirmado entre 172.16/172.17/172.18.

CME-OBS-001 — CORREGIDO
Router4: 42 teléfonos / capacidad 42.
Router0: 20 teléfonos / capacidad 20.
Router3: 7 teléfonos / capacidad 7.

TRUNK-OBS-001
MLS5/MLS6 usan DTP auto y permiten localmente 1-1005;
MLS7 restringe sus extremos a 10,20,30.

STP-OBS-001
Los roots STP están observados, pero no se encontró tuning explícito
de prioridad en los running-config revisados.
```

---

# 13. Datos que NO deben inventarse

La documentación no determina de forma inequívoca:

- protocolo de routing inter-router actualmente activo, porque no se observó ninguno;
- asociación exacta dispositivo↔puerto para algunos grupos de impresoras/AP;
- AP exacto en `Gi0/1` vs `Gi0/2` en Switch3;
- puertos exactos individuales de ciertos grupos IoT;
- routing L3 activo en multilayer switches;
- un registro CME funcional fuera de las capacidades corregidas 42/20/7;
- servicios de Data Center distintos de los endpoints ya inventariados;
- QoS, ACL, Port Security o aislamiento IoT global, salvo donde exista evidencia específica fuera de este documento.

Una IA debe consultar source/runtime/configuración antes de afirmar cualquiera de esos puntos.

---

# 14. Resumen machine-friendly

```text
ROUTERS:
  Router4:
    LAN_PREFIX: 172.16
    DATA: 172.16.10.0/24
    VOICE: 172.16.20.0/24
    IOT: 172.16.30.0/24
    GATEWAYS: .1
    DISTRIBUTION: Switch10
    STP_ROOT: Switch8
    PHYSICAL_ENDPOINTS: 208

  Router3:
    LAN_PREFIX: 172.17
    DATA: 172.17.10.0/24
    VOICE: 172.17.20.0/24
    IOT: 172.17.30.0/24
    GATEWAYS: .1
    DISTRIBUTION: Switch3
    STP_ROOT: Switch3
    PHYSICAL_ENDPOINTS: 21

  Router0:
    LAN_PREFIX: 172.18
    DATA: 172.18.10.0/24
    VOICE: 172.18.20.0/24
    IOT: 172.18.30.0/24
    GATEWAYS: .1
    DISTRIBUTION: MLS7
    STP_ROOT: MLS3
    PHYSICAL_ENDPOINTS: 50

VLAN:
  10: DATA
  20: VOICE
  30: IOT_AND_PRINTERS

WAN:
  R4-R3: 10.0.0.4/30, .5 ↔ .6
  R3-R0: 10.0.0.8/30, .9 ↔ .10
  R4-R0:
    CURRENT: 10.0.0.1 ↔ 10.0.0.5
    STATUS: BROKEN
    EXPECTED_NETWORK: 10.0.0.0/30
    EXPECTED_R0: 10.0.0.2

INTER_ROUTER_ROUTING:
  STATUS: NOT_OBSERVED

TOTAL_ENDPOINTS:
  279
```

---

# 15. Uso recomendado por otra IA

Para crear o validar esta red:

1. utilizar este archivo para entender **qué debe existir lógicamente**;
2. utilizar `topologia_completa_IMP.md` para conocer **qué equipos y conexiones físicas existen**;
3. no reparar silenciosamente los defectos documentados;
4. consultar configuración/source/runtime antes de afirmar estados no observados;
5. mantener separadas:
   - topología deseada/documentada;
   - configuración actual;
   - evidencia observada;
   - correcciones pendientes.
