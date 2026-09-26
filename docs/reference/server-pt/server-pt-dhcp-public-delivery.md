# Server-PT native DHCP and HTTP: public-path delivery

Status: **READY_FOR_REVIEW** on `feature/server-pt-goal-foundations`. This
feature-branch delivery does not merge to `main` or grant final independent
product acceptance.

## Supported public contract

The registered four-input `pt_apply_enterprise_services` tool admits an
unnamed `state_only` Server-PT DHCP request with dependent HTTP on Packet
Tracer **9.0.1.0858** over the **file** channel. The request's derived policy
is carried into the typed pool action and read back from the physical
`serverPool`; the clients are not given static addresses. The recorded
capability bounds are:

| Dimension | Admitted value |
| --- | --- |
| Topology | One wired segment; Server-PT `FastEthernet0`; one or two selected PC-PT clients on the actual access dependencies |
| Network | `192.0.2.0/24` |
| Server and DNS | `192.0.2.10` |
| Gateway | `192.0.2.1` |
| Exclusions | Exactly `.1` and `.10`, each a singleton |
| Requested allocation | Contiguous; `start_offset` 99–150 derives a start from `.100` through `.151`; the end is at or before `.152` |
| Capacity | One or two, at least the selected client count |

An exact policy/readback guard follows each native setter before process
enable. Every selected client requires two stable, fresh DHCP-on address,
mask and MAC samples joined to its exact IP/MAC/interface row on the effective
server/pool. The lease table is scanned once per group sample, and the full
group trace is retained once in the durable product record. A client-local
read failure blocks that client's dependent HTTP; duplicate selected
addresses or global server/pool ownership loss block all affected requests.
The actual plan determines selected and competing clients, so one selected
PC needs no invented inactive twin.

Generic or explicitly named pools, router substitution, explicit `dhcpRun`
acquisition, renewal, other network policies/builds/channels and native
capacity above two remain UNKNOWN or outside the admitted scope. A positive
state does not establish acquisition causality, renewal or lease-table end.
The default catalog does not promote the generic DHCP profile and exposes no
MCP capability override or strategy selector.

## Decisive LIVE evidence

| Episode | Executed source | Requested window / selected clients | Result | Primary archive |
| --- | --- | --- | --- | --- |
| 8 | `04c06adee4ac6a53299fc35556e8f31bac366ae5` | `.100`, one client | Maintained A1–E6 private candidate: DHCP state and first HTTP VERIFIED; public route untested | [Episode 8](evidence/dhcp-autonomy-02/e8/README.md) |
| 9 | `68680209eaaa5c88fd0f7cc30675232c645cc263` | `.100`–`.101`, two clients | Both distinct native rows, both cold HTTP requests VERIFIED; private candidate | [Episode 9](evidence/dhcp-autonomy-02/e9/README.md) |
| 10 | `e8c810192b44d75340ffa6ad81c16473eb060fd2` | `.151`–`.152`, two clients | Shifted policy, both distinct native rows and cold HTTP VERIFIED; private candidate | [Episode 10](evidence/dhcp-autonomy-02/e10/README.md) |
| 11 | `dda07fc03e0831af519e1ece373b9fc4851e5d1e` | `.125`–`.126`, two clients | **Registered four-input MCP handler with default catalog**; both DHCP and both cold HTTP checks VERIFIED | [Episode 11](evidence/dhcp-autonomy-02/e11/README.md) |

Episode 11 executed tree `08fbec4459cba4d2acd48bc1138e47d1c20c2227`,
attempt `a017dff41bb546d4b33bf495596bb265`, instance
`510bc23b6b0e4002979b7e963e7c1db2`, and file channel. Its qualification
record SHA-256 is
`a89301ea32038d7c5e8c930c1a0543a92f3749870fa5ae9a22d224154ee6a17c`;
its completed product record SHA-256 is
`cdff0155a22f44e115c002081906d3b7f27b8103b6429b1c165ec4c51af50f33`.
The 216-file archive manifest SHA-256 is
`05b7b85129a55f92801deb678e846c924ec402998e7b303ddb589281c618016b`.

In that public run, PC1 received `192.0.2.125` (MAC `0060.3E4A.C348`) and
PC2 `192.0.2.126` (MAC `00D0.FF01.07D7`). The three retained group samples
saw both unassigned, then both assigned with two physical rows, then the
same two assigned addresses and rows again. The requested physical policy
read back identically at all three samples. Both first HTTP-by-IP requests
to `http://192.0.2.10/` returned the marker, without preparatory ping, DNS,
warm-up request, PortFast, client static injection or clock acceleration.
The registered tool's JSON, typed result and stored product record agreed.

Episode 11 used 90 qualification operations and 162.61 active seconds.
The owned fixture was restored; maintained retirement exited PID 34644, and
the final census found zero Packet Tracer processes, an empty mailbox and no
campaign lock. The closed campaign ledger totals 698 operations and
3420.531649 seconds, leaving 8302 ordinary operations and 10379.468351
ordinary seconds outside the protected reserve. All four primary episodes
retain their original source and observation identities; no earlier run is
relabeled as the later code.

## Offline verification and limits

- Affected public, native, legacy-service and campaign tests: **229 passed**.
- Full Windows suite: **8163 passed, 6 skipped, 3 warnings**. The six skip
  reasons were retained: two require symlink privilege, two lack ignored
  historical raw artefacts, and two native-window tests require explicit
  Windows opt-in. Required native/public tests ran.
- The provisional quality gate, clean exact-commit quality gate for the LIVE
  source, MkDocs build and `git diff --check` passed. Independent read-only
  adversarial review found no pre-LIVE blocker; final audit remains separate.
- Public negative controls and pure scope checks reject outside-scope capacity,
  start, gateway, DNS, server address, exact exclusions, foreign build, named pool and HTTP
  transport before E5. Duplicate client addresses, one-client getter failure,
  unbound public callback and terminal persistence failure have focused
  failure-containment regressions. Static-client DNS/HTTP remains positive.

The 2/20/200/1000-client **offline** workload substitutes the backend
explicitly while exercising actual E6 group derivation, verification,
client-row assembly and durable record round trip. It makes one group
assembly, `N` verification calls and `N` check lookups. Measured group JSON
sizes were 245/2441/24401/122001 bytes; durable records were
4721/28572/267073/1327074 bytes. Verification took
0.333/0.597/5.025/47.079 ms, and persistence round trips took
4.817/4.546/8.287/23.617 ms on this Windows run. These measurements do
not qualify native capacity above two or predict LIVE latency.

The prior episode-8 delivery report's roughly-34-second readiness wording is
corrected in the active [engineering brief](../../engineering/change-briefs/server-pt-dhcp-fastloop.md):
53.639 seconds is the total observed elapsed value; 34.327 seconds is the
difference from its first retained sample. The historical report and raw
record remain unchanged. The optional `dhcp_lease_attributed` projection
that reported `lease_client_identity_invalid` in episodes 7–8 is omitted for
native `state_only`: the required grouped state reader carries the complete
attribution claim and remains fail-closed. The older optional reader remains
for other DHCP modes.
