# SERVER-PT-SP1-ROUTED-01: exploratory episode 2

Immutable archive of SP-1 LIVE episode 2: stage `SP1-ROUTED-W2` on Packet
Tracer 9.0.1.0858, file channel, through the registered four-input
`pt_apply_enterprise_services` tool. Executed source `710faca2aa69cf3556972062af3d53791c46bcd0` (tree `2c19872df5d3511fac4c90326ea34141389b7155`),
attempt `93faee2a5cff47de9a9522a4706737ab`, instance `066df952206242daa6fe2b22a3cf40be`. Device evidence: named, unverified
candidate `supports_static_routes` for the 1941 and 2911, recorded entry by
entry with its digest and matched by the product record's injected-catalog
limitation.

What was measured:

- Product VERIFIED, completed, persisted and cross-checked by the registered
  handler. All six selected clients (HQ inter-VLAN; BR1 over one transit
  hop; BR2 over two) verified, in rank order, HTTP by address first, the
  fresh resolver read (`DnsClient.getServerIp` equal to the planned DNS
  server), DNS resolution, the nonexistent-name negative qualified by the
  same client's positive, and HTTP by host name.
- All three routed groups admitted from fresh `show ip interface brief` and
  `show ip route` readings, including the three-router group under the
  per-router window; E5 static-route read-back verified on every router.
- Terminal binding probe: `getProcess('HostIp')` throws `invalid string
  position` on PC-PT; `getProcess('HostIpProcess').getDefaultGateway()`
  returned each client's planned gateway (10.126.0.1 / .17 / .25).
- Two terminal `show ip interface brief` captures exhausted their 6-call
  budget without converging, so `M-SP1-ROUTED-FINAL` is inconclusive; both
  route tables and every binding were captured.

`M-SP1-ROUTED-PRODUCT` supported_in_sample. 413 operations. Fixture
restoration proven; maintained retirement exited the owned process; final
census empty.

Qualification record SHA-256 `aa2d0f77d75d260f27399b21a4f1738df749e4114609fb9d42ecb4198536b90b`; product record SHA-256
`75d1b5ea318086be0fdded441a1931dac22a6d169a9057842ca4a30cbde88018`. `store/` is the campaign store at archive time.
`MANIFEST.sha256` pins every byte here; scripts are `.py.txt` data. Candidate
evidence is not default-catalog support; other builds, channels and
independent acceptance are not claimed.
