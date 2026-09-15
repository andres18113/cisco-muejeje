# Supported Devices

The catalog lists device models with their exact port names. Call
`pt_list_devices` for the live list and its aliases, or read the
`pt://catalog/devices` resource.

Aliases are accepted wherever a model name is expected: `router` → `2911`,
`switch` → `2960-24TT`, `pc` → `PC-PT`, `firewall` → `5506-X`, `ap` →
`AccessPoint-PT`. `pt_list_devices` returns the full alias map.

Confirm a model's ports with `pt_get_device_details` before linking. The server
is instructed never to invent port names.

## Routers

`1841`, `1941`, `2620XM`, `2621XM`, `2811`, `2901`, `2911`, `ISR4321`, `ISR4331`,
`819HG-4G-IOX`, `819HGW`, `829`, `CGR1240`, `Router-PT`, `Router-PT-Empty`.

- **2911** — `GigabitEthernet0/0..0/2` (3 GigE). Common default router.
- **1941 / 2901** — 2× GigE. **ISR4321/4331** — `GigabitEthernet0/0/0…`.
- ISR G2 (1941/2901/2911) take **HWIC/WIC**; ISR4321/4331 take **NIM**. See
  [Expansion Modules](modules.md).

## Switches

`2950-24`, `2950T-24`, `2960-24TT`, `3560-24PS`, `3650-24PS`, `IE-2000`,
`Switch-PT`, `Switch-PT-Empty`.

- **2960-24TT** — 24× `FastEthernet0/1..0/24` + 2× GigE uplinks. Default switch.
- **3560-24PS / 3650-24PS** — L3-capable.

## End devices

`PC-PT`, `Laptop-PT`, `Server-PT`, `TabletPC-PT`, `SMARTPHONE-PT`, `Printer-PT`,
`TV-PT`, `Home-VoIP-PT`, `Analog-Phone-PT`, `WiredEndDevice-PT`,
`WirelessEndDevice-PT`, `Embedded-Server-PT`, `7960` (IP Phone), `MCU-PT`, `SBC-PT`,
`Thing` (IoT).

- PCs, laptops and servers expose `FastEthernet0`.

## Wireless

`AccessPoint-PT` (+ `-A`/`-N`/`-AC`), `LAP-PT`, `3702i`, `WLC-PT`, `WLC-2504`,
`WLC-3504`, `Linksys-WRT300N`, `HomeRouter-PT-AC`, `Cell-Tower`, `802`, `803`.

## Security & WAN

`5505`, `5506-X` (ASA firewalls), `Cloud-PT`, `DSL-Modem-PT`, `Cable-Modem-PT`,
`Central-Office-Server`, `DLC100`.

## Infrastructure & misc

`Hub-PT`, `Bridge-PT`, `Repeater-PT`, `CoAxialSplitter-PT`, `Copper/Fiber Patch
Panel`, `Copper/Fiber Wall Mount`, `Sniffer`, `Meraki-MX65W`, `Meraki-Server`,
`NetworkController`, `Power Distribution Device`.
