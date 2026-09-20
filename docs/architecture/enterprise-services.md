# E6 enterprise network services

E6 starts only after E4 and E5 have produced immutable plans:

```text
Concrete TopologyPlan       E4: physical devices, ports, links, layout
           |
ConfigurationPlan          E5: addressing, VLANs, trunks, L3, DHCP
           |
ServicePlan                E6: service hosts, service actions and acceptance
           |
   compile / apply / verify
```

The E6 compiler does not create devices, choose models, allocate addresses, or
run E5. A service host is an existing E4 device and its address is an existing
static endpoint action in E5. Every `ServicePlan` embeds both source semantic
hashes, so an applicator rejects stale topology or foundational configuration
before contacting a runtime.

## Intent and plan boundary

The existing `ServiceRequirement` is extended instead of introducing a second
intent hierarchy. It identifies one of the closed service types DNS, HTTP,
HTTPS, NTP, TFTP, SMTP, POP3 or DHCP; an optional explicit E4 host; client scope; and
only the service-specific data needed by that type. Host selection is deterministic:
an explicit device wins, then a matching service role, then a generic server,
all within the requested site and ordered by stable device identity. E6 never
reselects the concrete model chosen upstream.

`ServicePlan` is separate from `ConfigurationPlan` because application service
lifecycle and client acceptance are distinct from foundational network
configuration. The plans nevertheless share E5's issue representation,
execution states, failure taxonomy, and deterministic topological sorter.

The action set is closed and backend-neutral:

- `EnableDnsService` and `AddDnsRecord`
- `EnableHttpService`, `SetHttpContent`, and `EnableHttpsService`
- `ConfigureNtpService`
- `EnableTftpService` and `PublishTftpFile`
- `EnableSmtpService`, `EnablePop3Service`, `EnsureEmailAccount`,
  `ConfigureEmailClient` and `SendMailMessage` (see
  [Mail under the event fallback](#mail-under-the-event-fallback))
- `EnableServerDhcp`, `ConfigureServerDhcpPool` and `AcquireDhcpLease`
  (see [Server-PT DHCP under the event fallback](#server-pt-dhcp-under-the-event-fallback))

There is no raw server command, arbitrary JavaScript, host-file import, or
generic client shell command. DNS currently compiles only A records. HTTP test
content is bounded printable text. TFTP accepts only a safe server-local
filename and in-memory content, retaining a SHA-256 fingerprint rather than a
host filesystem path.

## Dependencies and identity

Service actions use the E5 Kahn/heap sorter with stable phase, target, type, and
action-ID tie breaking. Records and content depend on their service enable
action. Explicit service dependencies become graph edges and missing nodes or
cycles are compile errors. Identical DNS records and TFTP file requirements are
deduplicated; contradictory DNS answers are rejected.

HTTP and HTTPS on one Server-PT share one measured `index.html` store. The
compiled `SetHttpContent` therefore records every sharing service in
`shared_service_ids` and carries one payload. Product admission selects one
writer from the services that remain eligible, resolves that writer's exact
operation capability, and removes only dependencies owned by an excluded
sharing service. The source plan id/hash stay unchanged while the run record
stores the selected service/action ids and the source-to-selected writer
binding. No other service key can authorize the writer, and a projection with
a missing dependency refuses before E5.

The semantic hash is canonical SHA-256 over the complete plan excluding only
the hash field itself. It includes E4 and E5 source hashes, service placement,
actions, foundational requirements, protocol metadata, and verification
expectations. Timestamps, live session identifiers, and runtime output never
enter it.

## Apply, observe, and accept

`COMPILED`, `APPLIED`, and `VERIFIED` remain separate. The applicator requires
every referenced E5 foundation to have independent `VERIFIED` status. Static
endpoints use the attributable IPv4/netmask core; delegated DHCP clients use a
distinct mode-only foundation from a fresh `HostPort.isDhcpClientOn()` read on
the manifest-bound interface. A merely applied action is insufficient, an
address is not mode proof, and E6 never tries to repair either foundation.
Runtime target name/model identity and per-service application capability are
also checked before mutation.

The capability matrix records compile support, application support, direct
read-back, and behavioral verification independently. Unknown application
support is skipped rather than attempted. Missing direct observation can leave
direct state partial while strong client behavior establishes service
usability.

Verification evidence is classified as:

- `DIRECT_STATE`: structured service state read from the host;
- `BEHAVIORAL`: a client resolves, fetches, synchronizes, or retrieves;
- `COMPOSED_BEHAVIORAL`: a path such as HTTP by DNS hostname succeeds only
  after DNS resolution and HTTP-by-IP behavior are independently verified.

If DNS resolution fails, HTTP-by-hostname is `DEPENDENCY_BLOCKED`; it is not
misreported as an HTTP server failure. An accepted configuration request never
promotes a service to verified without fresh independent evidence.

## Mutation and observation vocabulary

These terms are the shared meaning of every E5/E6 runtime row. They are
implemented by the fact enums and the single `decide_mutation` rule in
`domain/enterprise/models/execution.py`, and no producer may collapse two of
them into one field.

- **Channel acceptance** (`dispatch`): the transport proved the request entered
  the channel — the local bridge answered 200 on `/queue`, or the request file
  was published. It never means Packet Tracer executed anything.
- **Attempt knowledge** (`result`): whether a correlated result came back and
  parsed (`CORRELATED`), the engine reported an error (`ENGINE_ERROR`), the body
  was not a valid response (`MALFORMED`), none arrived (`NOT_OBSERVED`), or the
  result slot was lost (`LOST`).
- **Observed transition** (`transition`): whether the bracketing reads around
  the setter differ (`CHANGED`), are equal (`UNCHANGED`), or could not both be
  read (`UNOBSERVED`). A transition is observed between two reads of one
  dispatch; it is never proof of an execution count or of sole causation.
- **Postcondition** (`postcondition`): whether the post-read equals the intended
  value (`SATISFIED`), differs (`UNSATISFIED`), or was not obtained
  (`UNOBSERVED`).
- **Effect footprint** (`footprint`): whether the observed scope covers
  everything the setter is documented to change. A partial footprint can never
  be reported CLEAN.
- **Residual change**: `transition is CHANGED and postcondition is UNSATISFIED`.
- **Fresh read**: a correlated result of a read dispatched in this run for this
  expectation, which parsed to its typed shape and located its subject.
  Freshness does not require a changed value, and a fresh read that contradicts
  the expectation is fresh *negative* evidence.
- **Inconclusive read**: a completed read whose predicate cannot decide — the
  marker was present before the request, the window was incomplete, the command
  was refused. It is evidence neither for nor against the service.

Two supersessions bind every family: the classifier reads the original runtime
input rather than a repaired copy (TD-12.1), and a missing list item never
synthesizes channel acceptance (TD-12.2). Digests of a read value are bounded
diagnostics only: equal digests, equal lengths and a truthy native return value
are never authority for `UNCHANGED`, `SATISFIED` or a clean footprint (RD-11).

Operations are classified by the effect they may leave behind, and that class —
not the caller — decides whether a repeat is admissible:

| Class | Examples | Repeat after an ambiguous outcome | Release obligation |
| --- | --- | --- | --- |
| read-only | getters, `getOutput`, `getLastPageContent`, mailbox listing, lease table | bounded polling inside the deadline | none |
| declarative setter | `setEnable`, `setPageContents`, `setServerDomainName`, pool setters | none after dispatch; the postcondition decides | none |
| ensure-present | `addARecordToNameServerDb`, `addUser`, `addPool` | none; pre-read, act, post-read | none |
| owned temporary | `createClient`/`deleteClient`, `registerEvent` | none | released on every exit path |
| user-state, execute-once | `sendMail`, `dhcpRelease`/`dhcpRun` | never after ambiguity; one claim per subject per session | none |
| disposable qualification fixture | device creation and removal in a Q stage | none | owned devices removed, then two fresh restoration observations |

## Mail under the event fallback

Mail is compiled from one SMTP requirement that owns its accounts, its email
clients and its message pairs, plus an optional POP3 requirement on the same
host that owns only its enable and direct read-back. Accounts carry an opaque
`secret_ref`; a password never enters an intent, plan, hash, record or
response.

| Step | Action or expectation | Contract |
| --- | --- | --- |
| server | `EnableSmtpService(domain_name)`, `EnablePop3Service` | enable flag and SMTP domain set and read back in one bracketed evaluation |
| server | `EnsureEmailAccount(username, secret_ref)` | ensure-present: `addUser` only after a completed pre-read proved absence; an existing account is never changed and its credential stays unverified; an unreadable pre-read refuses rather than adding |
| client | `ConfigureEmailClient` | every field except the password is read back; refused while any claim is held on that client |
| message | `SendMailMessage` (execute-once) | one `sendMail` per pair per run under a pre-effect claim; never reported successful, because no same-evaluation observation of `mailSent` is qualified |
| server read | `smtp_delivered` | bounded read-only scan of the intended recipient's mailbox for the pair's nonce; presence only, returned as counts and flags, and reported PARTIAL so it never makes the mail service VERIFIED |
| gated | `smtp_send`, `pop3_retrieve`, `email_end_to_end` | optional rows that register no observer and never call `getMailIpc` |

Pairs are explicit, else a ring over the sorted selected clients (a self-send
for one client), never all pairs. Each pair has one stable `message_ref`, and a
fresh nonce per run is bound into subject and body before application and kept
in the run record, so an earlier run's message can never satisfy a later one.

Dispatch, server-mailbox presence and client retrieval are three different
claims. Mailbox presence is not a `mailSent` success and not POP3 evidence, and
a read-only recovery read after the unresolved send never clears that send's
uncertainty. Under the measured fallback (no safe zero-event release on either
channel), event-dependent verification does not exist in production; its rows
report a typed blocked result instead.

Claims live in `__mcpE6Claims` under `email_client:<device>`. A claim is
written `in_progress` in the same evaluation before the effect and becomes
`completed` or `unknown`; a foreign claim refuses, this operation's own claim
reports the earlier effect as unknown, and product code never resets one. The
claim bounds duplicates only within one evaluation, an inference the HTTP
channel has not qualified, so every mail operation stays UNKNOWN in the
capability catalog and UNKNOWN/UNMEASURED in the replay registry until a Q2
record exists. Secret-bearing actions are admitted only on the authenticated
HTTP channel, after every reference resolved, and every resolved value is
redacted from runtime rows in raw, JSON-escaped and URL-encoded form.

## Server-PT DHCP under the event fallback

DHCP authority is decided once inside canonical composition, after site,
segment and device identities exist and before E5 compilation. A delegated
segment carries one explicit Server-PT owner. E5 emits no IOS pool for that
segment, records `DHCP_DELEGATED_TO_SERVICE`, and still emits each client's
`SetEndpointDhcp` with its access/VLAN prerequisite. An explicit IOS owner,
two Server-PT owners, a foreign-segment server/client or a remaining E5 IOS
pool is a typed refusal; product code disables no existing DHCP server.

`ServerDhcpPoolRequirement` carries only operator choices: interface, pool
name, start offset and maximum users. Empty/zero structural defaults are
derived from the resolved E5 allocation or refused. Pool arithmetic validates
the IPv4 network, mask, usable window and bounded capacity without
materializing the subnet. Server, gateway and static-client exclusions are
stored as compact ranges. The exact Server-PT interface comes from its static
E5 foundation.

| Step | Action or expectation | Contract |
| --- | --- | --- |
| E5 bootstrap | `endpoint_dhcp_mode` | nonfailed/nonuncertain `SetEndpointDhcp` plus a fresh true mode read on the exact interface; no address is required |
| server | `EnableServerDhcp(interface)` | `getDhcpServerProcessByPortName`, `isEnable` and `setEnable`; before/after reads are separate from setter return |
| server | `ConfigureServerDhcpPool(...)` | ensure-present; `addPool` is void and is followed by `getPool`; matching state is a no-op, conflicts/getter failures refuse, unrelated pools/exclusions are preserved |
| client effect | `AcquireDhcpLease(interface)` | one void `dhcpRun(port)` under `dhcp_client:<device>:<interface>`; any existing claim refuses and product code never releases, resets or deletes it |
| client read | `dhcp_lease` | exact-boolean mode plus fresh address/mask/MAC/lease-time; only an address inside the compiled lease window and outside its compact exclusions is compatible, and it remains UNKNOWN `acquisition_unattributed`; a subnet-compatible address outside that allocation contradicts |
| server read | `dhcp_lease_attributed` | bounded intended-pool scan with coherent metadata, usable client/row identities and finite lease-time numbers; an exact IP/MAC row supports only `attributed_to_intended_server`, survives a later scan limitation, and loses aggregate precedence to a valid same-IP foreign-MAC contradiction |

Acquisition and verification are deliberately different phases. The existing
applicator may evaluate a named verification prerequisite after its producing
action and before a dependent action. Every effect or behavior on a delegated
client waits for that client's `DHCP_LEASE` to be VERIFIED; mode and an
intended-pool row are insufficient. Server configuration and independent
static-client work do not wait on a lease. Each action is classified once,
uncertainty is never redispatched, and a mixed action/verification cycle closes
without a call.

The measured R-EVT-05 fallback registers no DHCP observer. `getLeaseTimeStr()`
has no qualified causality; `getLeaseAt(i)` has no documented count or end
condition; MAC representation equivalence and the pool setter interaction are
also unmeasured. A positive row may be retained, but a null, throw, repeated
row, timeout or reaching `max_users` never proves completion, absence or pool
exhaustion. `configure_only` emits no acquisition action and keeps a typed
NOT_ATTEMPTED acquisition row.

Every new DHCP boolean is accepted only when the native return is an actual
boolean; invalid truthy/falsy values never admit an effect. Server exclusion
enumeration validates a finite integral count and refuses above the internal
4096-row ceiling before iterating or setting anything. A failed post-effect
read preserves uncertainty, and missing subjects, engine errors and malformed
success payloads remain separate categories.

Every DHCP operation and reader is UNKNOWN/UNMEASURED in the default catalog,
including the separate mode-reader gate. Required DHCP therefore refuses
before E5, while optional DHCP is excluded with complete rows and cannot
reactivate IOS authority or admit a dependent service. Offline Node and
integration tests exercise candidate paths but promote nothing. Q3 is now an
executable, file-only qualification stage for build 9.0.1.0858; until a LIVE
record is interpreted independently it changes no product capability.

## Qualification boundary

Support for a Packet Tracer behavior that the bundled reference only documents
is established by a **Q stage**, never by this repository's offline tests. A Q
stage runs one authorized stage per invocation from a clean, published checkout,
counts every engine operation against a hard ceiling, keeps a finalization
reserve that experiments cannot borrow, writes its record ahead of each step,
and always finalizes what it created. Its contracts live in
`domain/enterprise/models/service_qualification.py` and its operator surface in
[`docs/qa/server-services-qualification.md`](../qa/server-services-qualification.md).

A stage record is promotion evidence only when it is a LIVE record completed at
the exact SHA, build, channel and stage it was authorized for. An offline
simulation is marked as one and can never promote a capability, and a completed
stage supports its bounded sample rather than universal behavior.

Q3 composes the exact one-segment DHCP product plan through the real compiler,
applies manifest-bound endpoint bootstrap and E6 scheduling through existing
application/runtime boundaries, and keeps native table, timing and event
probes explicitly qualification-only. Its capacity-one negative control does
not prove exhaustion without a qualified completed scan. Product acquisition
claims and observers without event identity are intentionally retained/inert;
workspace restoration and later dedicated-process retirement are different
cleanup facts.

## Packet Tracer runtime boundary

The domain and compiler import no Packet Tracer bridge, MCP adapter,
`TerminalLine`, IOS renderer, or JavaScript generator. Packet Tracer service
APIs and typed client operations belong to a separate infrastructure adapter.
Their exact support is established by controlled `__MCP_E6_*` probes, bounded
convergence, and cleanup. An absent getter remains unobservable; it is not
converted into unsupported.

Packet Tracer limitations are per service. DNS or HTTP success is not revoked
by an NTP, TFTP, or HTTPS limitation. Telephony, ACL/NAT, STP tuning,
EtherChannel, first-hop redundancy, dynamic routing, IPv6 routing,
redistribution, and QoS remain outside E6.

## Packet Tracer 9.0.1.0858 baseline

The bundled IpcAPI reference and controlled live probes establish this
conservative baseline for `Server-PT`:

| Service | Apply | Direct read-back | Behavioral verification |
| --- | --- | --- | --- |
| DNS A record | supported | supported | supported by fresh PC ping plus negative control |
| HTTP content | supported | supported | supported by a fresh background HTTP client |
| HTTPS enable | supported | supported | unknown |
| NTP enable | supported | supported | synchronization unobservable |
| TFTP enable | supported | supported | transfer unobservable |
| TFTP file publication | unknown | unknown | unobservable |
| SMTP/POP3 enable, accounts, clients | unknown | unknown | unknown; supporting mailbox presence only |
| SMTP send, POP3 retrieval | unknown | unknown | gated by the event fallback |
| Server-PT DHCP enable/pool | unknown | unknown | Q3 not run |
| DHCP acquisition/attribution | unknown | unknown | read-back at most UNKNOWN under R-EVT-05 |

DNS uses `addARecordToNameServerDb` and `getARecordWithAddress`. The older
`addIpAddress` path updates a legacy table but did not produce a wire-operational
record in the controlled runtime, so it is not used as DNS acceptance evidence.
HTTP clients are created per expectation and released after the fresh response
window is evaluated, preventing prior content from satisfying a later check.

Packet progression is paused while Packet Tracer is in Simulation mode. A
bounded behavioral probe may temporarily select Realtime mode, but it records
and restores the previous mode during cleanup. Controlled same-subnet and
routed PC-to-Server scenarios both verified DNS resolution, HTTP by address,
and composed HTTP by hostname. Cross-segment service compilation therefore
requires the already compiled E5 L3 actions for both endpoint segments; E6
references those actions but never recompiles or reapplies them.
