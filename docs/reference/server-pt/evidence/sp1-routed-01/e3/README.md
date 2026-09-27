# SERVER-PT-SP1-ROUTED-01: final episode 3 (W1)

Immutable archive of the final SP-1 acceptance run for the inter-VLAN,
single-gateway workload: stage `SP1-ROUTED-W1` on Packet Tracer 9.0.1.0858,
file channel, through the registered four-input
`pt_apply_enterprise_services` tool with the DEFAULT capability catalog
(nothing injected). Executed source `a04369a88298d452ce5a9043e160d2c14fe83ca5` (tree `d41ecc27d4fa92b846f43d06df37421c76fdca1a`), published as
`cisco/feature/server-pt-goal-foundations` with exact-SHA CI run 36306639618
successful (quality, pytest on Windows/Linux x Python 3.11/3.13, docs).
Attempt `d3f60b0a25944284a56a01fef9f7a4b6`, instance `e91cb675a32c4c049cdffc60e5325dbf`; qualification run
`2026-09-27T08-53-46Z-8692ab1a`, product run `2026-09-27T08-55-26Z-8bd8296d`.

What was measured:

- The whole three-site fixture was created; the product composed the SP-1
  intent (run-derived address space 10.68.0.0/16, marker and host name),
  admitted the HQ client-to-server paths and applied only their closure.
- Both HQ clients (data VLAN) reached the separate DNS and web Server-PT in
  the servers VLAN through one router-on-a-stick gateway. Each verified, in
  rank order: its gateway read (`HostIpProcess`, 10.68.0.1), HTTP by address
  first, its resolver read (`DnsClient`, 10.68.0.10), DNS resolution of the
  run's host name, the nonexistent-name negative qualified by its own
  positive, and HTTP by host name.
- The routed readiness group (hq-data to hq-servers) was admitted from fresh
  router readings before the first dependent request.
- Terminal capture: every router's `show ip interface brief` and
  `show ip route` complete; every client binding read.

Product VERIFIED; `M-SP1-ROUTED-PRODUCT` and `M-SP1-ROUTED-FINAL`
supported_in_sample. 228 operations. Fixture restoration proven; maintained
retirement exited owned PID 59376; final census empty.

Qualification record SHA-256 `cab9b7225d4520a519b9c51ba9c3489decb92936d77534e74fc700fb716cf321`; product record SHA-256
`7bf9f591e0a25e559ce2e0063576ba770a1808d4acd02a8ce408958ed15b21ae`. `store/` is the campaign store at archive time.
`MANIFEST.sha256` pins every byte here; scripts are `.py.txt` data. Other
builds, channels, dynamic routing, DHCP clients and independent acceptance
are not claimed.
