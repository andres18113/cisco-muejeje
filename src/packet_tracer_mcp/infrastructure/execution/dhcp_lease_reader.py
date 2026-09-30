"""Decode a finite observed prefix, scoped to the exact native reader context.

The repeated index exception is empirical. It proves neither universal absence
nor renewal, and historical readers that merged field exceptions remain leads.
"""

import re
from collections.abc import Mapping
from dataclasses import dataclass
from ipaddress import IPv4Address
from math import isfinite

from ...domain.enterprise.services.dhcp_lease_evidence import normalized_mac

READER_CONTRACT = "getLeaseAt-index-and-fields-v2"
INDEX_END_SEMANTICS = "observed_native_index_end"
_NATIVE_END_ERROR = "invalid vector subscript"
_SHA = re.compile(r"[0-9a-f]{40}")


@dataclass(frozen=True)
class LeaseReaderContext:
    """Immutable observed execution scope; no unknown context inherits a rule."""

    source_sha: str
    source_tree: str
    build: str
    channel: str
    reader_contract: str = READER_CONTRACT

    @property
    def admitted(self) -> bool:
        """Whether this is the measured build/channel and maintained reader."""
        return bool(
            _SHA.fullmatch(self.source_sha)
            and _SHA.fullmatch(self.source_tree)
            and self.build == "9.0.1.0858"
            and self.channel == "file"
            and self.reader_contract == READER_CONTRACT
        )

    def as_facts(self) -> dict[str, str]:
        """Bind each current raw observation to its executed source and scope."""
        return {
            "backend": "packet_tracer",
            "source_sha": self.source_sha,
            "source_tree": self.source_tree,
            "build": self.build,
            "channel": self.channel,
            "reader_contract": self.reader_contract,
            "convention": "repeated_exact_index_exception_observed_prefix",
            "limitation": "not_universal_absence_exhaustion_or_renewal",
        }


def reader_context(observed: Mapping[str, object] | None) -> LeaseReaderContext | None:
    """Resolve only a clean, explicitly observed execution identity."""
    if (
        not isinstance(observed, Mapping)
        or observed.get("clean") is not True
        or observed.get("backend") != "packet_tracer"
    ):
        return None
    fields = [
        observed.get(k) for k in ("source_sha", "source_tree", "build", "channel")
    ]
    if not all(isinstance(value, str) for value in fields):
        return None
    context = LeaseReaderContext(*fields)
    return context if context.admitted else None


# Raw index and field observations are separate. Every bounded index is read,
# including indices following an apparent end. Inputs are serialized by callers.
LEASE_SCAN_SCRIPT = (
    "function __leaseScan(p,w){var entries=[];for(var j=0;j<w;j++){"
    "var e={index:j,return_kind:'',error:'',row:null},r=null,read=false;"
    "try{r=p.getLeaseAt(j);read=true;}catch(x){e.return_kind='throw';"
    "e.error=__leaseError(x);}if(read){if(r===null){e.return_kind='null';}"
    "else if(r===undefined){e.return_kind='undefined';}else{"
    "e.return_kind=typeof r;if(typeof r==='object'){try{var row={};"
    "var fields=['ipAddress','macAddress','leaseTime','port'];"
    "for(var k=0;k<fields.length;k++){var f=fields[k],v=r[f];"
    "row[f+'_type']=typeof v;row[f]=f==='leaseTime'?v:String(v);}e.row=row;"
    "}catch(x){e.return_kind='field_throw';e.error=__leaseError(x);}}}}"
    "entries.push(e);}return entries;}"
)


def decode_scan(scan: dict, context: LeaseReaderContext | None) -> dict:
    """Retain raw bytes' meaning and derive only a scoped finite-prefix end."""
    result = dict(scan)
    entries = scan.get("entries")
    window = scan.get("window")
    result.update(rows=[], termination="error", scan_error="scan_window_incoherent")
    result["reader_provenance"] = (
        context.as_facts() if context and context.admitted else {}
    )
    if (
        not isinstance(entries, list)
        or type(window) is not int
        or window < 2
        or len(entries) != window
    ):
        return result
    entries = [dict(e) if isinstance(e, Mapping) else e for e in entries]
    result["entries"] = entries
    rows, row_indices, addresses, macs = [], [], set(), set()
    tail_start = None
    invalid = str(scan.get("scan_error") or "")
    for index, entry in enumerate(entries):
        if (
            not isinstance(entry, dict)
            or type(entry.get("index")) is not int
            or entry["index"] != index
        ):
            invalid = invalid or "scan_index_incoherent"
            continue
        entry.pop("end_semantics", None)
        kind = entry.get("return_kind")
        if (
            not isinstance(kind, str)
            or not isinstance(entry.get("error"), str)
            or (kind != "object" and entry.get("row") is not None)
        ):
            invalid = invalid or "scan_return_incoherent"
        if kind == "object" and entry.get("error") == "":
            row = entry.get("row")
            if not isinstance(row, dict):
                invalid = invalid or "lease_row_malformed"
                continue
            clean = {
                key: row.get(key)
                for key in ("ipAddress", "macAddress", "leaseTime", "port")
            }
            try:
                IPv4Address(clean["ipAddress"])
                valid = (
                    all(
                        row.get(key + "_type") == "string"
                        and isinstance(clean[key], str)
                        for key in ("ipAddress", "macAddress", "port")
                    )
                    and len(normalized_mac(clean["macAddress"])) == 12
                    and bool(clean["port"])
                    and row.get("leaseTime_type") == "number"
                    and type(clean["leaseTime"]) in (int, float)
                    and isfinite(clean["leaseTime"])
                    and clean["leaseTime"] >= 0
                )
            except (TypeError, ValueError, OverflowError):
                valid = False
            if not valid:
                invalid = invalid or "lease_row_malformed"
            if valid:
                address, mac = (
                    str(clean["ipAddress"]),
                    normalized_mac(clean["macAddress"]),
                )
                if address in addresses or mac in macs:
                    invalid = invalid or "duplicate_or_conflicting_lease_identity"
                addresses.add(address)
                macs.add(mac)
                rows.append(clean)
                row_indices.append(index)
            if tail_start is not None:
                invalid = invalid or "row_after_alleged_end"
        else:
            if tail_start is None:
                tail_start = index
            native = (
                kind == "throw"
                and entry.get("error") == _NATIVE_END_ERROR
                and context is not None
                and context.admitted
            )
            if not native and (kind != "null" or entry.get("error") != ""):
                invalid = invalid or str(entry.get("error") or "lease_index_unreadable")
    result["rows"] = rows
    result["row_indices"] = row_indices
    result["first_end_index"] = tail_start
    result["confirming_index"] = None if tail_start is None else tail_start + 1
    if tail_start is None:
        invalid = invalid or "scan_bound_exhausted"
    elif window - tail_start < 2:
        invalid = invalid or "scan_end_unconfirmed"
    if tail_start is not None and not invalid:
        tail = entries[tail_start:]
        first_kind = tail[0]["return_kind"]
        if any(e.get("return_kind") != first_kind for e in tail):
            invalid = "scan_end_inconsistent"
        elif first_kind == "throw":
            for entry in tail:
                entry["end_semantics"] = INDEX_END_SEMANTICS
    result["scan_error"] = invalid
    if not invalid:
        result["termination"] = (
            "end_throw"
            if any(
                e.get("end_semantics") == INDEX_END_SEMANTICS
                for e in entries[tail_start:]
            )
            else "null"
        )
    return result
