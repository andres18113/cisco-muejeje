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
HTTPS, NTP, or TFTP; an optional explicit E4 host; client scope; and only the
service-specific data needed by that type. Host selection is deterministic:
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

The semantic hash is canonical SHA-256 over the complete plan excluding only
the hash field itself. It includes E4 and E5 source hashes, service placement,
actions, foundational requirements, protocol metadata, and verification
expectations. Timestamps, live session identifiers, and runtime output never
enter it.

## Apply, observe, and accept

`COMPILED`, `APPLIED`, and `VERIFIED` remain separate. The applicator requires
every referenced E5 endpoint-address action to have independent `VERIFIED`
status. A merely applied foundational action is insufficient, and E6 never
tries to repair it. Runtime target name/model identity and per-service
application capability are also checked before mutation.

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
