# Notice and attribution

## Origin

Cisco-Muejeje started as a fork of
[Mats2208/MCP-Packet-Tracer](https://github.com/Mats2208/MCP-Packet-Tracer)
("Packet Tracer MCP Server"), written by Mateo
([@Mats2208](https://github.com/Mats2208)). The divergence point is upstream
commit `b075961191e266d28c13f6d5996069f4626f4f5e` (2026-07-31). The Git history
up to that commit is the upstream project's history and is kept unchanged.
Upstream commits made after it, including its later releases, are not merged
into this repository.

## License

The upstream project was distributed under the MIT License. Its license text and
copyright notice are kept unchanged in [`LICENSE`](LICENSE), as that license
requires for copies and substantial portions of the software.

## Later development

The work after the divergence point, starting at commit `aadbb94` (2026-08-02),
is Cisco-Muejeje's own development: the Enterprise planning, compilation,
configuration and runtime layers, Packet Tracer capability discovery, the
governed public MCP surface and Skills, and the governed CP-SCALE / CP-LIVE
qualification with its evidence under `docs/reference/cp-scale/`. The Git
history records who wrote each change.

## PTBuilder

[PTBuilder](https://github.com/kimmknight/PTBuilder), by Kim Knight
([@kimmknight](https://github.com/kimmknight)), was the historical reference for
the Packet Tracer Script Engine helper surface. That surface is the
`addDevice` / `addLink` / `configureIosDevice` style of helper that
`infrastructure/generator/ptbuilder_generator.py` emits and that
`EXTENSION/script-engine/main.js` installs. The PTBuilder repository carries no
license, so its files are not redistributed here: the `EXTENSION/script-engine/*.js`
files other than `main.js` are git-ignored local reference copies. Cisco-Muejeje
is not affiliated with PTBuilder.

## Cisco Packet Tracer

Cisco-Muejeje automates Cisco Packet Tracer, which is not included in this
repository. The project is not affiliated with or endorsed by Cisco.
