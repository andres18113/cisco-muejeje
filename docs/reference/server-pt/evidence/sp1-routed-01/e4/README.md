# SERVER-PT-SP1-ROUTED-01: final episode 4 (W2)

Immutable archive of the final SP-1 acceptance run for the multi-site
workload: stage `SP1-ROUTED-W2` on Packet Tracer 9.0.1.0858, file channel,
through the registered four-input `pt_apply_enterprise_services` tool with
the DEFAULT capability catalog (nothing injected). Executed source `a04369a88298d452ce5a9043e160d2c14fe83ca5`
(tree `d41ecc27d4fa92b846f43d06df37421c76fdca1a`), published with exact-SHA CI run 36306639618 successful.
Attempt `865184ae8e7644f18b7c7ede494de03a`, instance `1ee5966d68c04681a79a2938a165e9ce`; qualification run
`2026-09-27T09-02-05Z-7921f7e1`, product run `2026-09-27T09-03-44Z-8a4d07fb`.

What was measured:

- Three sites and three routers (HQ 1941, BR1 2911, BR2 1941) joined by two
  Ethernet crossover WAN links with static routes; separate DNS and web
  Server-PT at HQ; run-derived address space 10.114.0.0/16.
- All six selected clients verified, in rank order, their gateway read
  (`HostIpProcess`), HTTP by address first, their resolver read, DNS, the
  qualified nonexistent-name negative and HTTP by host name: HQ over one
  gateway, BR1 over one transit hop, BR2 over two (a path crossing three
  routing devices).
- The three routed groups the selection derives (hq-data, br1-data and
  br2-data to hq-servers) were each admitted once from fresh readings of
  every router on the path; E5 static-route read-back verified.
- Terminal capture: every router's interface table and routing table
  complete; every client binding read (`HostIp` threw, `HostIpProcess`
  answered).

Product VERIFIED; `M-SP1-ROUTED-PRODUCT` and `M-SP1-ROUTED-FINAL`
supported_in_sample. 423 operations. Fixture restoration proven; maintained
retirement exited owned PID 59720; final census empty.

Qualification record SHA-256 `6a275fbc3af569416b7b51ef841eb91de1573e4d21ac6288cfad83acc69c7d30`; product record SHA-256
`8426a284b19e533d7efa0fbe2329d1102576f757633161f601fddb67dff17b4d`. `store/` is the campaign store at archive time.
`MANIFEST.sha256` pins every byte here; scripts are `.py.txt` data. Other
builds, channels, dynamic routing, DHCP clients and independent acceptance
are not claimed.
