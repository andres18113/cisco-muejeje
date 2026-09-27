# SERVER-PT-SP1-ROUTED-01: exploratory episode 1

Immutable archive of the first SP-1 LIVE run: stage `SP1-ROUTED-W2` (all six
clients over the three-site static-routed composition) on Packet Tracer
9.0.1.0858, file channel, through the registered four-input
`pt_apply_enterprise_services` tool. Executed source `6e5e5277881d331106bad17f88048ba2b82b157c` (tree `4353b3a493f1ae5aafe99159eda8fc7dcb3800de`),
attempt `da4fd175b4524a3f8bb155d1de2b8bd4`, instance `360046098cff4a7f831be580501389ac`. Device evidence: named, unverified
candidate `supports_static_routes` for the 1941 and 2911 (the default catalog
did not support it).

What was measured:

- E4/E5 composed and applied the whole admitted closure, including Ethernet
  WAN transit /30s and static routes; E5 read-back passed.
- HQ-PC-01 (inter-VLAN, one gateway) and BR1-PC-01/02 (one transit hop)
  verified HTTP by address first, then DNS, the nonexistent-name negative and
  HTTP by host name. HQ-PC-02 verified HTTP by address; its DNS window lacked
  the ping statistics at the 5 s bound (UNKNOWN), so its negative and
  host-name rows were dependency-blocked.
- The BR2 routed group (three routers) was REFUSED at its 30 s deadline: one
  round over three routers took 32.4 s and the HQ read timed out. The
  terminal capture shows every router's `show ip route` complete and
  unpaged, with the full static chain installed (`S ... [1/0] via ...`, `C`
  and `L` rows parsed with no unparsed line).
- `getProcess('HostIp')` threw `invalid string position` on PC-PT, which
  also hid the resolver read in this probe version.

Product status PARTIAL; `M-SP1-ROUTED-PRODUCT` inconclusive,
`M-SP1-ROUTED-FINAL` supported. 367 operations. Fixture restoration proven;
maintained retirement exited the owned process; final census empty.

Qualification record SHA-256 `788b430ee53f700bedafc6581e868bb1f1bb5d202143426d1b27dd01d1f6f4f6`; product record SHA-256
`6029d56cb0c823994b0cbd0cb57ba02604e6cc5f52ee38ee9346b1d791dd3de7`. `store/` is the campaign store at archive time (after
episode 2 closed). `MANIFEST.sha256` pins every byte here; scripts are
`.py.txt` data. Nothing here claims default-catalog support, other builds or
channels, or independent acceptance.
