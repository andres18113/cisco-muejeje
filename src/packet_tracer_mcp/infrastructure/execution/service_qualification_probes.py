"""Generated Q0/Q1/Q3 qualification probes and their strict shape parsers.

Every script is one line, has no `//` comment and serializes every datum with
`json.dumps`, because Packet Tracer evaluates it with `new Function()` and a
pasted copy loses its newlines. Every script reports through `reportResult`
from inside its own `try`, so an engine exception becomes a typed reading
instead of a modal dialog.

Scope of what is written: all run state lives under the run-namespaced bag
`this.__mcpE6Q[<run_id>]`. No probe writes a production global
(`__mcpE6Claims`, `__mcpE6Inert`, `__mcpE6HttpClients`), and the Q1 probes
touch only the owned fixture devices they are handed.

Ownership of that bag is a fact established inside the engine, never inferred
from the run key's name. The claim writes only when the key is absent, and it
stamps `owner` with this invocation's nonce; every later write under the key,
and the release of the key itself, proves `owner` in the same evaluation that
would mutate. A pre-existing key is therefore rejected without writing
anything, so the refusal that follows has nothing to undo, and a lost claim
acknowledgement can never make the finalizer adopt or delete a foreign key.

Vendor surface, checked against Cisco's local reference
(`help/default/IpcAPI`, labelled 8.1.0) unless marked otherwise:

- `Device::getPort(string)`, `HostPort::setIpSubnetMask(ip, ip)` and the
  `ipChanged(ip, ip, ip, ip)` event; `registerEvent(name, obj, cb)` with
  `src.className/objectUuid/eventName` (`scriptModules_scriptEngine.htm`).
  The M-UNREG trigger re-addresses the owned PC's port instead of typing a
  terminal command: it needs no terminal-dispatch seam, and no pager or busy
  prompt can swallow it;
- `HttpServer::setEnable/isEnabled/setPageContents/getPage`,
  `HttpsServer::setHttpsEnable/isHttpsEnabled` (plus the inherited members).
  Cisco documents `setPageContents` as setting the contents of a page, not as
  creating one: the Q1 record at `0850de3` measured `File not exist` for two
  newly named pages. The page probes therefore only ever write `index.html`,
  a page both handles must first read back non-empty on the owned server;
- `Port::isPortUp/isProtocolUp/getLink` and
  `HostPort::getIpAddress/getSubnetMask` for endpoint readiness. No documented
  reader exposes a switch port's STP state or a readable light status;
- `DnsClient::getServerIp()`;
- `_ScriptModule.unregisterIpcEventByID(...)` is NOT documented: it is the
  maintained extension's existing usage (`EXTENSION/script-engine/main.js`).
  Its return value is recorded by type only and never interpreted.

A parser accepts a payload only when every key its step promises is present
with its exact type. A missing key is not a false or a zero: the reading is
then unobserved, and the rules decide nothing from it.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from typing import Any

from ...application.ports.service_qualification import DispatchOutcome
from ...domain.enterprise.models.execution import DispatchFact, ResultFact
from ...domain.enterprise.services.service_qualification_evidence import (
    ProbeReading,
    QueueReceipt,
)

DispatchAndWait = Callable[[str, float], DispatchOutcome]
Send = Callable[[str], bool]

#: The fixed, bounded loop that widens the window between a contender's check
#: and its claim. It exists only to make an interleaving observable if one can
#: happen; it proves nothing when none does.
ATOMICITY_SPIN = 50000
#: The observed event source: the owned PC's port, re-addressed within
#: TEST-NET-1 so that each trigger is a real change and routes nowhere.
TRIGGER_PORT = "FastEthernet0"
TRIGGER_MASK = "255.255.255.0"
TRIGGER_ADDRESSES = ("192.0.2.201", "192.0.2.202")
OBSERVED_EVENT = "ipChanged"
_MAX_CAUSE = 200
#: The one page the Q1 page probes write: it exists on a fresh Server-PT, and
#: Cisco documents no call that creates a page.
INDEX_PAGE = "index.html"
#: The bound on page text one cell returns. A longer page is reported as
#: truncated, and a truncated page can never prove "unchanged".
PAGE_CONTENT_LIMIT = 4096

_BOOL = (bool,)
_INT = (int,)
_STR = (str,)
_LIST = (list,)
_DICT = (dict,)
_OPTIONAL_BOOL = (bool, type(None))

_SPECS: dict[str, dict[str, tuple[type, ...]]] = {
    "eng_write": {
        "receiver_is_global": _BOOL,
        "run_bag_preexisting": _BOOL,
        "written": _BOOL,
        "owned": _BOOL,
    },
    "eng_read": {
        "receiver_is_global": _BOOL,
        "owned": _BOOL,
        "found": _BOOL,
        "nonce_matches": _BOOL,
        "released": _BOOL,
    },
    "atom_collect": {
        "present": _BOOL,
        "log": _LIST,
        "claim": _STR,
        "terminal_steps": _INT,
        "released": _BOOL,
    },
    "unreg_register": {
        "found": _BOOL,
        "event": _STR,
        "registered1": _BOOL,
        "register1_error": _STR,
        "trigger_x": _INT,
        "trigger_error": _STR,
        "cb1_calls": _INT,
    },
    "unreg_evidence": {
        "cb1_calls": _INT,
        "cb1_events": _LIST,
        "registered2": _BOOL,
        "register2_error": _STR,
        "cb2_calls": _INT,
    },
    "unreg_release": {
        "release1": _DICT,
        "cb2_calls_before_inert": _INT,
        "cb2_inert": _BOOL,
        "registered3": _BOOL,
        "register3_error": _STR,
        "cb1_calls_before_y": _INT,
        "cb2_calls_before_y": _INT,
        "cb3_calls_before_y": _INT,
        "trigger_y": _INT,
        "trigger_error": _STR,
    },
    "unreg_after": {
        "cb1_calls": _INT,
        "cb1_events_after_y": _INT,
        "cb2_calls": _INT,
        "cb2_events_after_inert": _INT,
        "cb3_calls": _INT,
        "cb3_events_after_y": _INT,
        "release2": _DICT,
        "release3": _DICT,
        "dropped": _BOOL,
    },
    "bag_release": {
        "had_run_bag": _BOOL,
        "owned": _BOOL,
        "keys": _LIST,
        "observers_marked_inert": _INT,
        "deleted": _BOOL,
        "present_after": _BOOL,
    },
    "page_write": {
        "http_found": _BOOL,
        "https_found": _BOOL,
        "reference_equal": _BOOL,
        "before": _DICT,
        "written": _BOOL,
        "write_error": _STR,
    },
    "page_read": {"cells": _DICT},
    "readiness": {"listeners": _DICT, "ports": _DICT},
    "port_readiness": {"ports": _DICT},
    "marker_page": {
        "error": _STR,
        "index_written": _DICT,
        "readback": _DICT,
        "http_enabled": _OPTIONAL_BOOL,
        "https_enabled": _OPTIONAL_BOOL,
        "https_process_enabled": _OPTIONAL_BOOL,
    },
    "http_disable": {
        "error": _STR,
        "http_enabled": _OPTIONAL_BOOL,
        "https_enabled": _OPTIONAL_BOOL,
        "https_process_enabled": _OPTIONAL_BOOL,
    },
    "https_disable": {
        "error": _STR,
        "http_enabled": _OPTIONAL_BOOL,
        "https_enabled": _OPTIONAL_BOOL,
        "https_process_enabled": _OPTIONAL_BOOL,
    },
    "client_resolvers": {"clients": _DICT},
    "dhcp_server_baseline": {
        "device": _STR,
        "found": _BOOL,
        "process_found": _BOOL,
        "interface": _STR,
        "enabled": _OPTIONAL_BOOL,
        "enabled_type": _STR,
        "pool_count": _INT,
        "pools": _LIST,
        "truncated": _BOOL,
        "error": _STR,
    },
    "dhcp_clients": {"clients": _LIST},
    "dhcp_table": {
        "found": _BOOL,
        "process_found": _BOOL,
        "pool_found": _BOOL,
        "pool_name": _STR,
        "rows": _LIST,
        "termination": _STR,
        "error": _STR,
    },
    "dhcp_events_register": {
        "owned": _BOOL,
        "registered": _INT,
        "errors": _LIST,
        "made_inert": _INT,
    },
    "dhcp_events_collect": {
        "owned": _BOOL,
        "events": _LIST,
        "releases": _LIST,
        "dropped": _BOOL,
    },
}

#: Bounded error text from inside the engine. It is defined once per script.
_ERR = (
    "var __er=function(x){var s='';try{s=String(x&&x.message?x.message:x);}"
    "catch(y){s='error';}return (s||'error').substring(0,200);};"
)
_OWN = "var __has=function(o,k){return Object.prototype.hasOwnProperty.call(o,k);};"


def _wrap(step: str, body: str) -> str:
    """Guard one probe body so an exception still reports a typed error."""
    return (
        "try{" + _ERR + _OWN + body + "}catch(__e){reportResult(JSON.stringify("
        "{step:" + json.dumps(step) + ",probe_error:String(__e).substring(0,200)"
        "}));}"
    )


def _type_error(payload: Mapping[str, Any], spec: Mapping[str, tuple]) -> str:
    for key, types in spec.items():
        if key not in payload:
            return f"missing:{key}"
        value = payload[key]
        if isinstance(value, bool) and bool not in types:
            return f"type:{key}"
        if not isinstance(value, types):
            return f"type:{key}"
    return ""


def parse_probe_reading(step: str, outcome: DispatchOutcome) -> ProbeReading:
    """Turn one dispatch outcome into a reading that the rules may trust."""
    if outcome.result is not ResultFact.CORRELATED:
        return ProbeReading(
            step,
            outcome.dispatch,
            outcome.result,
            False,
            cause=(outcome.detail or outcome.result.value)[:_MAX_CAUSE],
        )
    body = outcome.body
    if body is None or body.startswith(("PT_ERROR", "ERROR")):
        return ProbeReading(
            step,
            outcome.dispatch,
            ResultFact.ENGINE_ERROR,
            False,
            cause=("engine_error:" + str(body or ""))[:_MAX_CAUSE],
        )
    try:
        payload = json.loads(body)
    except (TypeError, ValueError):
        payload = None
    if not isinstance(payload, dict):
        return ProbeReading(
            step, outcome.dispatch, ResultFact.MALFORMED, False, cause="not_an_object"
        )
    if payload.get("probe_error"):
        return ProbeReading(
            step,
            outcome.dispatch,
            ResultFact.ENGINE_ERROR,
            False,
            cause=("probe_error:" + str(payload["probe_error"]))[:_MAX_CAUSE],
        )
    shape = _type_error(payload, _SPECS[step])
    if shape:
        return ProbeReading(
            step, outcome.dispatch, ResultFact.MALFORMED, False, cause="shape:" + shape
        )
    return ProbeReading(step, outcome.dispatch, ResultFact.CORRELATED, True, payload)


class PacketTracerQualificationProbes:
    """The Q0 engine and Q1/Q3 private probes for one run.

    The instance is bound to one run identity and to the invocation's counted
    callables; it has no channel of its own and never chooses one.
    """

    def __init__(
        self,
        *,
        run_id: str,
        nonce: str,
        dispatch_and_wait: DispatchAndWait,
        send: Send,
        timeout_seconds: float = 10.0,
    ) -> None:
        """Bind the probes to one run and one fixed, counted channel."""
        self._run = json.dumps(run_id)
        self._nonce = json.dumps(nonce)
        self._marker_root = "MCPQ-" + nonce[:16]
        self._dispatch_and_wait = dispatch_and_wait
        self._send = send
        self._timeout = timeout_seconds

    def _read(self, step: str, script: str) -> ProbeReading:
        return parse_probe_reading(
            step, self._dispatch_and_wait(_wrap(step, script), self._timeout)
        )

    def _owned_bag(self) -> str:
        """Bind `__r` to this run's bag and `__own` to proven ownership.

        It creates nothing. The run key's name proves nothing either: another
        invocation can hold it, so ownership is the `owner` field the claim
        wrote, compared with this invocation's nonce in the same evaluation
        that is about to write or delete.
        """
        run, nonce = self._run, self._nonce
        return (
            "var __q=this.__mcpE6Q;var __present=!!(__q&&Object.prototype"
            f".hasOwnProperty.call(__q,{run}));var __r=__present?__q[{run}]:null;"
            f"var __own=!!(__r&&__r.owner==={nonce});"
        )

    def _observer_bag(self) -> str:
        """Bind observer state only after proving this invocation owns the bag."""
        return self._owned_bag() + "var __B=__own&&__r.unreg;"

    @staticmethod
    def _source(device: str) -> str:
        return (
            f"var __d=ipc.network().getDevice({json.dumps(device)});"
            "var __t=(__d&&typeof __d.getPort==='function')"
            f"?__d.getPort({json.dumps(TRIGGER_PORT)}):null;"
        )

    @staticmethod
    def _trigger(address: str, guard: str) -> str:
        """Re-address the source port once, reporting a failed setter."""
        return (
            f"var __te='';if({guard}){{try{{__t.setIpSubnetMask("
            f"{json.dumps(address)},{json.dumps(TRIGGER_MASK)});}}"
            "catch(__x){__te=__er(__x);}}"
        )

    @staticmethod
    def _register(entry: str, flag: str, error: str) -> str:
        event = json.dumps(OBSERVED_EVENT)
        return (
            f"var {flag}=false,{error}='';if(__t){{try{{"
            f"__t.registerEvent({event},null,{entry}.fn);{flag}=true;}}"
            f"catch(__x){{{error}=__er(__x);}}}}else{{{error}='source_port_absent';}}"
        )

    # -- M-ENG-1 -----------------------------------------------------------

    def write_bag_sentinel(self) -> ProbeReading:
        """Claim the run key, or reject a pre-existing one without writing.

        The existence check and the write are one decision in one evaluation.
        When the key already exists nothing at all is written -- not the
        sentinel, not the container -- so the collision the reading reports is
        a refusal with nothing to undo. A successful claim stamps `owner` with
        this invocation's nonce, which is what every later write and the
        release prove.
        """
        run, nonce = self._run, self._nonce
        return self._read(
            "eng_write",
            "var __g=(function(){return this;})();var __q=this.__mcpE6Q;"
            f"var __pre=!!(__q&&__has(__q,{run}));var __w=false,__own=false;"
            "if(!__pre){__q=this.__mcpE6Q=__q||{};"
            f"var __r=__q[{run}]={{owner:{nonce}}};"
            f"__r.sentinel={{nonce:{nonce}}};__w=true;__own=true;}}"
            "reportResult(JSON.stringify({step:'eng_write',"
            "receiver_is_global:this===__g,run_bag_preexisting:__pre,"
            "written:__w,owned:__own}));",
        )

    def read_and_release_bag_sentinel(self) -> ProbeReading:
        """Read the nonce in a separate evaluation; release only what this run owns.

        A value under the run key is reported whoever wrote it, because a
        foreign one is exactly what the rules need to see. Only an owned,
        nonce-matching sentinel is deleted.
        """
        nonce = self._nonce
        return self._read(
            "eng_read",
            "var __g=(function(){return this;})();"
            + self._owned_bag()
            + "var __s=__r&&__r.sentinel;"
            f"var __m=!!(__s&&__s.nonce==={nonce});var __rel=false;"
            "if(__own&&__m){delete __r.sentinel;__rel=!__has(__r,'sentinel');}"
            "reportResult(JSON.stringify({step:'eng_read',"
            "receiver_is_global:this===__g,owned:__own,found:!!__s,"
            "nonce_matches:__m,released:__rel}));",
        )

    # -- ATOM-1 ------------------------------------------------------------

    def queue_atomicity_contender(self, contender: str) -> QueueReceipt:
        """Queue one contender for the run-owned claim without waiting."""
        name = json.dumps(contender)
        script = (
            "try{"
            + self._owned_bag()
            + "if(__own){var __a=__r.atom=__r.atom||{log:[],claim:'',seq:0};"
            f"__a.log.push({{c:{name},s:'check',n:++__a.seq}});"
            "var __free=(__a.claim==='');var __w=0;"
            f"for(var __i=0;__i<{ATOMICITY_SPIN};__i++){{__w=(__w+__i)%9973;}}"
            f"__a.spin=__w;if(__free){{__a.claim={name};}}"
            f"__a.log.push({{c:{name},s:(__free?'claimed':'refused'),n:++__a.seq}});"
            "}}catch(__e){}"
        )
        accepted = bool(self._send(script))
        return QueueReceipt(
            step=f"contender_{contender}",
            accepted=accepted,
            dispatch=(
                DispatchFact.ACCEPTED if accepted else DispatchFact.ACCEPTANCE_UNKNOWN
            ),
        )

    def collect_atomicity(self) -> ProbeReading:
        """Collect the ordered contender log; release it only when complete."""
        return self._read(
            "atom_collect",
            self._owned_bag()
            + "if(!__present){reportResult(JSON.stringify({step:'atom_collect',"
            "probe_error:'run_bag_absent'}));}else if(!__own){reportResult("
            "JSON.stringify({step:'atom_collect',probe_error:'run_bag_not_owned'}));}"
            "else{var __a=__r.atom;if(!__a){reportResult(JSON.stringify("
            "{present:false,log:[],claim:'',"
            "terminal_steps:0,released:false}));}else{var __log=[],__t=0;"
            "for(var __i=0;__i<__a.log.length;__i++){var __v=__a.log[__i];"
            "if(__v.s==='claimed'||__v.s==='refused'){__t++;}"
            "if(__log.length<16){__log.push({c:String(__v.c),s:String(__v.s),"
            "n:Number(__v.n)});}}var __rel=false;"
            "if(__t===2&&__a.log.length===4){delete __r.atom;"
            "__rel=!__has(__r,'atom');}"
            "reportResult(JSON.stringify({present:true,log:__log,"
            "claim:String(__a.claim),terminal_steps:__t,released:__rel}));}}",
        )

    # -- M-UNREG-1 / M-UNREG-2 ---------------------------------------------

    def register_observer_and_trigger(self, device: str) -> ProbeReading:
        """Register cb1 on the device's port and trigger X by re-addressing it."""
        event = json.dumps(OBSERVED_EVENT)
        return self._read(
            "unreg_register",
            self._source(device) + "if(!__t){reportResult(JSON.stringify({found:false,"
            f"event:{event},registered1:false,"
            "register1_error:'source_port_absent',trigger_x:0,trigger_error:'',"
            "cb1_calls:0}));}"
            "else{" + self._owned_bag() + "if(!__own){reportResult("
            f"JSON.stringify({{found:true,event:{event},registered1:false,"
            "register1_error:'run_bag_not_owned',trigger_x:0,"
            "trigger_error:'',cb1_calls:0}));}else{"
            "var __B=__r.unreg={seq:0};"
            "__B.mk=function(e){return function(src,args){e.calls++;"
            "try{if(!e.ident&&src){e.ident={className:String(src.className||''),"
            "uuid:String(src.objectUuid||'')};}}catch(__x){}"
            "if(e.released){return;}if(e.events.length<8){var k=[];"
            "try{for(var n in args){if(k.length<8){k.push(String(n));}}}catch(__y){}"
            "e.events.push({seq:++__B.seq,className:String(src&&src.className||''),"
            "uuid:String(src&&src.objectUuid||''),"
            "eventName:String(src&&src.eventName||''),arg_keys:k});}};};"
            "var __e1=__B.cb1={calls:0,events:[],released:false,ident:null};"
            "__e1.fn=__B.mk(__e1);"
            + self._register("__e1", "__ok", "__err")
            + "var __x0=++__B.seq;"
            + self._trigger(TRIGGER_ADDRESSES[0], "__ok")
            + f"reportResult(JSON.stringify({{found:true,event:{event},"
            "registered1:__ok,register1_error:__err,trigger_x:__x0,"
            "trigger_error:__te,cb1_calls:__e1.calls}));}}",
        )

    def read_observer_and_register_zero_event(self, device: str) -> ProbeReading:
        """Read cb1's evidence and register cb2, which has seen no event."""
        return self._read(
            "unreg_evidence",
            self._observer_bag()
            + "if(!__present){reportResult(JSON.stringify({step:'unreg_evidence',"
            "probe_error:'run_bag_absent'}));}else if(!__own){reportResult("
            "JSON.stringify({step:'unreg_evidence',"
            "probe_error:'run_bag_not_owned'}));}else if(!__B||!__B.cb1){"
            "reportResult(JSON.stringify({step:'unreg_evidence',"
            "probe_error:'observer_bookkeeping_absent'}));}else{"
            + self._source(device)
            + "var __ev=[];for(var __i=0;__i<__B.cb1.events.length;__i++){"
            "var __v=__B.cb1.events[__i];__ev.push({seq:__v.seq,"
            "className:__v.className,uuid:__v.uuid,eventName:__v.eventName,"
            "arg_keys:__v.arg_keys});}"
            "var __e2=__B.cb2={calls:0,events:[],released:false,ident:null};"
            "__e2.fn=__B.mk(__e2);"
            + self._register("__e2", "__ok", "__err")
            + "reportResult(JSON.stringify({cb1_calls:__B.cb1.calls,cb1_events:__ev,"
            "registered2:__ok,register2_error:__err,cb2_calls:__e2.calls}));}",
        )

    def release_observers_and_trigger(self, device: str) -> ProbeReading:
        """Release cb1 by its observed identity, mark cb2 inert, add cb3, trigger Y."""
        event = json.dumps(OBSERVED_EVENT)
        return self._read(
            "unreg_release",
            self._observer_bag()
            + "if(!__present){reportResult(JSON.stringify({step:'unreg_release',"
            "probe_error:'run_bag_absent'}));}else if(!__own){reportResult("
            "JSON.stringify({step:'unreg_release',"
            "probe_error:'run_bag_not_owned'}));}else if(!__B||!__B.cb1||!__B.cb2){"
            "reportResult(JSON.stringify("
            "{step:'unreg_release',probe_error:'observer_bookkeeping_absent'}));}"
            "else{var __e1=__B.cb1,__e2=__B.cb2,__id=null;"
            "for(var __i=0;__i<__e1.events.length;__i++){var __v=__e1.events[__i];"
            f"if(__v.eventName==={event}&&__v.className&&__v.uuid){{__id=__v;break;}}}}"
            "var __av=(typeof _ScriptModule!=='undefined'&&!!_ScriptModule&&"
            "typeof _ScriptModule.unregisterIpcEventByID==='function');"
            "var __rel={attempted:false,available:__av,threw:'',return_type:''};"
            "if(__id&&__av){__rel.attempted=true;try{var __rv=_ScriptModule"
            f".unregisterIpcEventByID(__id.className,__id.uuid,{event},null,__e1.fn);"
            "__rel.return_type=typeof __rv;}catch(__x){__rel.threw=__er(__x);}}"
            "var __c2=__e2.calls;__e2.released=true;"
            + self._source(device)
            + "var __e3=__B.cb3={calls:0,events:[],released:false,ident:null};"
            "__e3.fn=__B.mk(__e3);"
            + self._register("__e3", "__ok3", "__err3")
            + "var __b1=__e1.calls,__b2=__e2.calls,__b3=__e3.calls;"
            "var __y=++__B.seq;__B.trigger_y=__y;__B.cb2_at_inert=__e2.events.length;"
            + self._trigger(TRIGGER_ADDRESSES[1], "__t")
            + "reportResult(JSON.stringify({release1:__rel,"
            "cb2_calls_before_inert:__c2,"
            "cb2_inert:true,registered3:__ok3,register3_error:__err3,"
            "cb1_calls_before_y:__b1,cb2_calls_before_y:__b2,cb3_calls_before_y:__b3,"
            "trigger_y:__y,trigger_error:__te}));}",
        )

    def read_post_release_and_drop(self) -> ProbeReading:
        """Read every counter after Y and drop the run's observer bookkeeping."""
        event = json.dumps(OBSERVED_EVENT)
        return self._read(
            "unreg_after",
            self._observer_bag()
            + "if(!__present){reportResult(JSON.stringify({step:'unreg_after',"
            "probe_error:'run_bag_absent'}));}else if(!__own){reportResult("
            "JSON.stringify({step:'unreg_after',"
            "probe_error:'run_bag_not_owned'}));}else if(!__B||!__B.cb1||!__B.cb2||"
            "!__B.cb3){reportResult(JSON.stringify("
            "{step:'unreg_after',probe_error:'observer_bookkeeping_absent'}));}"
            "else{var __e1=__B.cb1,__e2=__B.cb2,__e3=__B.cb3,__y=__B.trigger_y||0;"
            "var __after=function(e){var c=0;for(var i=0;i<e.events.length;i++){"
            "if(e.events[i].seq>__y){c++;}}return c;};"
            "var __av=(typeof _ScriptModule!=='undefined'&&!!_ScriptModule&&"
            "typeof _ScriptModule.unregisterIpcEventByID==='function');"
            "var __out={cb1_calls:__e1.calls,cb1_events_after_y:__after(__e1),"
            "cb2_calls:__e2.calls,cb2_events_after_inert:"
            "__e2.events.length-(__B.cb2_at_inert||0),cb3_calls:__e3.calls,"
            "cb3_events_after_y:__after(__e3)};"
            "var __release=function(e){var o={attempted:false,threw:'',"
            "return_type:''};if(e.ident&&e.ident.className&&e.ident.uuid&&__av){"
            "o.attempted=true;try{var rv=_ScriptModule.unregisterIpcEventByID("
            f"e.ident.className,e.ident.uuid,{event},null,e.fn);"
            "o.return_type=typeof rv;}catch(__x){o.threw=__er(__x);}}"
            "e.released=true;return o;};"
            "__e1.released=true;__out.release2=__release(__e2);"
            "__out.release3=__release(__e3);delete __r.unreg;"
            "__out.dropped=!__has(__r,'unreg');reportResult(JSON.stringify(__out));}",
        )

    def release_run_bag(self) -> ProbeReading:
        """Release this run's own key, and never another invocation's (finalizer).

        Ownership is proven in the same evaluation that would delete, so a
        lost claim acknowledgement cannot make this adopt a foreign key: an
        unowned key is read and reported, never marked and never deleted.
        Marking an observer inert bounds what it records; it does not detach
        it, so the coordinator keeps reporting every observer it could not
        prove released.
        """
        run = self._run
        return self._read(
            "bag_release",
            self._owned_bag() + f"var __had=!!(__q&&__has(__q,{run}));"
            "var __keys=[],__inert=0,__del=false;if(__had&&__own){"
            "for(var __k in __r){if(__keys.length<16){__keys.push(String(__k));}}"
            "var __B=__r.unreg;if(__B){var __n=['cb1','cb2','cb3'];"
            "for(var __i=0;__i<3;__i++){if(__B[__n[__i]]){"
            "__B[__n[__i]].released=true;__inert++;}}}"
            "var __D=__r.dhcp;if(__D&&__D.entries){for(var __j=0;"
            "__j<__D.entries.length;__j++){if(!__D.entries[__j].released){"
            "__D.entries[__j].released=true;__inert++;}}}"
            f"delete __q[{run}];__del=!__has(__q,{run});}}"
            "reportResult(JSON.stringify({had_run_bag:__had,owned:__own,"
            "keys:__keys,observers_marked_inert:__inert,deleted:__del,"
            f"present_after:!!(__q&&__has(__q,{run}))}}));",
        )

    # -- Q1 private probes on owned fixtures --------------------------------

    def _marker(self, label: str) -> str:
        return f"{self._marker_root}-{label}"

    def page_marker_texts(self) -> dict[str, str]:
        """Return this run's page texts and markers for the two page writes.

        The run-specific part is the CONTENT. The page itself is always the
        existing `index.html`: writing a new name is exactly what failed LIVE.
        """
        http, https = self._marker("H"), self._marker("S")
        return {
            "http_marker": http,
            "https_marker": https,
            "http_page": f"<html><body>{http}</body></html>",
            "https_page": f"<html><body>{https}</body></html>",
        }

    @staticmethod
    def _server(server: str) -> str:
        return (
            f"var __d=ipc.network().getDevice({json.dumps(server)});"
            "var __h=__d?__d.getProcess('HttpServer'):null;"
            "var __s=__d?__d.getProcess('HttpsServer'):null;"
        )

    @staticmethod
    def _cell() -> str:
        """Define `__cell(p)`: one bounded, typed read of the index page.

        A throwing getter, an absent process or a null page is `read:false`
        with its cause -- unobserved, never an empty page.
        """
        page = json.dumps(INDEX_PAGE)
        return (
            "var __cell=function(p){var c={read:false,error:'',length:0,"
            "content:'',truncated:false};if(!p){c.error='process_absent';return c;}"
            f"try{{var v=p.getPage({page});if(v===null||v===undefined){{"
            "c.error='null_page';return c;}var t=String(v);c.read=true;"
            f"c.length=t.length;c.truncated=t.length>{PAGE_CONTENT_LIMIT};"
            f"c.content=t.substring(0,{PAGE_CONTENT_LIMIT});}}"
            "catch(x){c.error=__er(x);}return c;};"
        )

    def write_index_marker(self, server: str, handle: str) -> ProbeReading:
        """Bracket the index page through both handles, then write one marker.

        One evaluation reads the page through both handles and writes this
        run's marker page through `handle` only when both reads completed
        with non-empty, untruncated content. A failed or empty read is no
        evidence of a separate table, so nothing is written on it.
        """
        texts = self.page_marker_texts()
        target, page = (
            ("__h", texts["http_page"])
            if handle == "http"
            else (
                "__s",
                texts["https_page"],
            )
        )
        return self._read(
            "page_write",
            self._server(server)
            + self._cell()
            + "var __b={http:__cell(__h),https:__cell(__s)};var __w=false,__we='';"
            "var __ok=__b.http.read&&__b.https.read&&__b.http.length>0&&"
            "__b.https.length>0&&!__b.http.truncated&&!__b.https.truncated;"
            f"if(__h&&__s&&__ok){{try{{{target}.setPageContents("
            f"{json.dumps(INDEX_PAGE)},{json.dumps(page)});__w=true;}}"
            "catch(__x){__we=__er(__x);}}"
            "reportResult(JSON.stringify({http_found:!!__h,https_found:!!__s,"
            "reference_equal:(!!__h&&__h===__s),before:__b,written:__w,"
            "write_error:__we}));",
        )

    def read_index_cells(self, server: str) -> ProbeReading:
        """Read the index page through both handles, in its own evaluation."""
        return self._read(
            "page_read",
            self._server(server)
            + self._cell()
            + "reportResult(JSON.stringify({cells:{http:__cell(__h),"
            "https:__cell(__s)}}));",
        )

    @staticmethod
    def _listener_states() -> str:
        return (
            "var __he=null,__se=null,__sp=null;"
            "try{__he=__h?!!__h.isEnabled():null;}catch(__x){}"
            "try{__se=__s?!!__s.isHttpsEnabled():null;}catch(__x){}"
            "try{__sp=__s?!!__s.isEnabled():null;}catch(__x){}"
        )

    @staticmethod
    def _ports_block(endpoints: Sequence[tuple[str, str]]) -> str:
        """Return the typed readiness read of the exact named ports.

        Documented readers only: `isPortUp`, `isProtocolUp`, `getLink` on every
        named port and `getIpAddress/getSubnetMask` where the port has them.
        Every reader is guarded on its own, so one refusal is a named cause and
        never a missing port. A boolean is reported only when the engine
        returned `typeof "boolean"`: the companion `*_type` field keeps a
        missing reader, a non-boolean return and an actual `false` apart, which
        `!!` would have collapsed into one observation. The switch's STP state
        has no documented reader and is not read.
        """
        named = json.dumps([list(item) for item in endpoints])
        return (
            f"var __ports={{}};var __n={named};"
            "for(var __i=0;__i<__n.length;__i++){"
            "var __c={device:__n[__i][0],interface:__n[__i][1],found:false,"
            "port_up:null,port_up_type:'absent',protocol_up:null,"
            "protocol_up_type:'absent',linked:null,link_type:'absent',"
            "ip:null,mask:null,error:''};"
            "try{var __dv=ipc.network().getDevice(__n[__i][0]);"
            "var __pt=__dv?__dv.getPort(__n[__i][1]):null;if(__pt){__c.found=true;"
            "try{var __pu=__pt.isPortUp();__c.port_up_type=typeof __pu;"
            "if(__c.port_up_type==='boolean'){__c.port_up=__pu;}}"
            "catch(__x){__c.port_up_type='threw';__c.error='isPortUp:'+__er(__x);}"
            "try{var __ru=__pt.isProtocolUp();__c.protocol_up_type=typeof __ru;"
            "if(__c.protocol_up_type==='boolean'){__c.protocol_up=__ru;}}"
            "catch(__x){__c.protocol_up_type='threw';"
            "__c.error=__c.error||('isProtocolUp:'+__er(__x));}"
            "try{var __lk=__pt.getLink();"
            "var __no=(__lk===null||__lk===undefined);"
            "__c.link_type=__no?'absent':(typeof __lk);__c.linked=!__no;}"
            "catch(__x){__c.link_type='threw';"
            "__c.error=__c.error||('getLink:'+__er(__x));}"
            "if(typeof __pt.getIpAddress==='function'){try{"
            "__c.ip=String(__pt.getIpAddress()).substring(0,64);"
            "__c.mask=String(__pt.getSubnetMask()).substring(0,64);}"
            "catch(__x){__c.error=__c.error||('getIpAddress:'+__er(__x));}}}}"
            "catch(__x){__c.error=__er(__x);}"
            "__ports[__n[__i][0]+'/'+__n[__i][1]]=__c;}"
        )

    def read_listener_readiness(
        self, server: str, endpoints: Sequence[tuple[str, str]]
    ) -> ProbeReading:
        """Read listener flags and the fixture links' endpoint readiness."""
        return self._read(
            "readiness",
            self._server(server)
            + self._listener_states()
            + self._ports_block(endpoints)
            + "reportResult(JSON.stringify({listeners:{http_enabled:__he,"
            "https_enabled:__se,https_process_enabled:__sp},ports:__ports}));",
        )

    def read_port_readiness(self, endpoints: Sequence[tuple[str, str]]) -> ProbeReading:
        """Read the exact fixture endpoints where no server process is involved."""
        return self._read(
            "port_readiness",
            self._ports_block(endpoints)
            + "reportResult(JSON.stringify({ports:__ports}));",
        )

    def prepare_marker_page(self, server: str, marker: str) -> ProbeReading:
        """Write the marked index through both handles and read both back.

        Both listeners stay as E6 enabled them, so the first fetch is an
        HTTP-mode positive control. The read-back is what the listener would
        serve: whether each handle's page now contains the marker.
        """
        page = json.dumps(f"<html><body>{marker}</body></html>")
        index = json.dumps(INDEX_PAGE)
        mark = json.dumps(marker)
        return self._read(
            "marker_page",
            self._server(server) + "var __err='',__iw={http:false,https:false};"
            "if(!__h||!__s){__err='process_absent';}else{"
            f"try{{__h.setPageContents({index},{page});__iw.http=true;}}"
            "catch(__x){__err='index_http:'+__er(__x);}"
            f"try{{__s.setPageContents({index},{page});__iw.https=true;}}"
            "catch(__x){__err=__err||('index_https:'+__er(__x));}}"
            "var __mk=function(p){var c={read:false,contains_marker:false,length:0,"
            "error:''};if(!p){c.error='process_absent';return c;}"
            f"try{{var t=String(p.getPage({index}));c.read=true;c.length=t.length;"
            f"c.contains_marker=t.indexOf({mark})>=0;}}catch(__x){{c.error=__er(__x);}}"
            "return c;};var __rb={http:__mk(__h),https:__mk(__s)};"
            + self._listener_states()
            + "reportResult(JSON.stringify({error:__err,index_written:__iw,"
            "readback:__rb,http_enabled:__he,https_enabled:__se,"
            "https_process_enabled:__sp}));",
        )

    def disable_http(self, server: str) -> ProbeReading:
        """Disable the HTTP listener and read both states back."""
        return self._read(
            "http_disable",
            self._server(server) + "var __err='';"
            "if(!__h){__err='process_absent';}else{try{__h.setEnable(false);}"
            "catch(__x){__err='disable_http:'+__er(__x);}}"
            + self._listener_states()
            + "reportResult(JSON.stringify({error:__err,http_enabled:__he,"
            "https_enabled:__se,https_process_enabled:__sp}));",
        )

    def disable_https(self, server: str) -> ProbeReading:
        """Disable the HTTPS listener and read both states back."""
        return self._read(
            "https_disable",
            self._server(server) + "var __err='';"
            "if(!__s){__err='process_absent';}else{try{__s.setHttpsEnable(false);}"
            "catch(__x){__err='disable_https:'+__er(__x);}}"
            + self._listener_states()
            + "reportResult(JSON.stringify({error:__err,http_enabled:__he,"
            "https_enabled:__se,https_process_enabled:__sp}));",
        )

    def read_client_resolvers(self, clients: Sequence[str]) -> ProbeReading:
        """Read `DnsClient.getServerIp()` on the named clients."""
        return self._read(
            "client_resolvers",
            f"var __o={{}};var __n={json.dumps(list(clients))};"
            "for(var __i=0;__i<__n.length;__i++){"
            "var __c={found:false,value:null,error:''};"
            "try{var __d=ipc.network().getDevice(__n[__i]);"
            "var __p=__d?__d.getProcess('DnsClient'):null;if(__p){__c.found=true;"
            "var __v=__p.getServerIp();__c.value=(__v===null||__v===undefined)"
            "?null:String(__v).substring(0,64);}}catch(__x){__c.error=__er(__x);}"
            "__o[__n[__i]]=__c;}reportResult(JSON.stringify({clients:__o}));",
        )

    # -- Q3 private probes on owned DHCP fixtures --------------------------

    def read_dhcp_server_baseline(self, server: str, interface: str) -> ProbeReading:
        """Read the exact interface binding and a bounded pool inventory.

        The subject is echoed back as `device`, so the admission rule compares
        the reading against the server it asked about instead of trusting that
        the answer came from the right device.
        """
        return self._read(
            "dhcp_server_baseline",
            f"var __dn={json.dumps(server)};var __d=ipc.network().getDevice(__dn);"
            "var __m=__d?__d.getProcess('DhcpServerMain'):null;"
            f"var __if={json.dumps(interface)};"
            "var __p=__m&&__m.getDhcpServerProcessByPortName(__if);"
            "var __enabled=null,__etype='absent',__count=0,__pools=[],"
            "__tr=false,__error='';if(__p){try{var __ev=__p.isEnable();"
            "__etype=typeof __ev;if(__etype==='boolean'){__enabled=__ev;}"
            "var __n=__p.getPoolCount();if(typeof __n!=='number'||!isFinite(__n)||"
            "__n<0||Math.floor(__n)!==__n){throw new Error('pool_count');}"
            "__count=__n;__tr=__n>16;for(var __i=0;__i<Math.min(__n,16);__i++){"
            "var __q=__p.getPoolAt(__i);if(!__q){throw new Error('pool_row');}"
            "__pools.push({name:String(__q.getDhcpPoolName()).substring(0,64),"
            "network:String(__q.getNetworkAddress()).substring(0,64),"
            "mask:String(__q.getSubnetMask()).substring(0,64),"
            "gateway:String(__q.getDefaultRouter()).substring(0,64),"
            "dns:String(__q.getDnsServerIp()).substring(0,64),"
            "start:String(__q.getStartIp()).substring(0,64),"
            "end:String(__q.getEndIp()).substring(0,64),max:__q.getMaxUsers()});}}"
            "catch(__x){__error=__er(__x);}}"
            "reportResult(JSON.stringify({device:__dn,found:!!__d,"
            "process_found:!!__p,interface:__if,enabled:__enabled,"
            "enabled_type:__etype,pool_count:__count,pools:__pools,"
            "truncated:__tr,error:__error}));",
        )

    def read_dhcp_clients(self, clients: Sequence[tuple[str, str]]) -> ProbeReading:
        """Read exact client ports, preserving raw mode/MAC/address/lease text."""
        return self._read(
            "dhcp_clients",
            f"var __n={json.dumps([list(item) for item in clients])},__rows=[];"
            "for(var __i=0;__i<__n.length;__i++){var __name=__n[__i][0],"
            "__if=__n[__i][1],__d=null,__p=null,__mode=null,__mt='absent',"
            "__mac='',__ip='',__mask='',__lease='',__error='';try{"
            "__d=ipc.network().getDevice(__name);if(__d){for(var __j=0;"
            "__j<__d.getPortCount();__j++){var __c=__d.getPortAt(__j);"
            "if(__c&&String(__c.getName())===__if){__p=__c;break;}}}"
            "if(__p){var __mv=__p.isDhcpClientOn();__mt=typeof __mv;"
            "if(__mt==='boolean'){__mode=__mv;}__mac=String(__p.getMacAddress())"
            ".substring(0,64);__ip=String(__p.getIpAddress()).substring(0,64);"
            "__mask=String(__p.getSubnetMask()).substring(0,64);"
            "var __cp=__d.getProcess('DhcpClient');var __data=__cp&&"
            "__cp.getDataOfPort(__if);if(__data){__lease=String("
            "__data.getLeaseTimeStr()).substring(0,64);}}}catch(__x){"
            "__error=__er(__x);}__rows.push({device:__name,interface:__if,"
            "found:!!__d,port_found:!!__p,mode:__mode,mode_type:__mt,mac:__mac,"
            "ipv4:__ip,netmask:__mask,lease_time:__lease,error:__error});}"
            "reportResult(JSON.stringify({clients:__rows}));",
        )

    def read_dhcp_table(
        self, server: str, interface: str, pool_name: str
    ) -> ProbeReading:
        """Read at most four raw lease rows and name the observed termination."""
        return self._read(
            "dhcp_table",
            f"var __d=ipc.network().getDevice({json.dumps(server)});"
            "var __m=__d?__d.getProcess('DhcpServerMain'):null;"
            f"var __p=__m&&__m.getDhcpServerProcessByPortName({json.dumps(interface)});"
            f"var __q=__p&&__p.getPool({json.dumps(pool_name)});"
            "var __rows=[],__term='not_started',__error='';if(__q){"
            "__term='bound';for(var __i=0;__i<4;__i++){try{var __r="
            "__q.getLeaseAt(__i);if(!__r){__term='null';break;}__rows.push({"
            "ipAddress:String(__r.ipAddress).substring(0,64),macAddress:String("
            "__r.macAddress).substring(0,64),leaseTime:__r.leaseTime,port:String("
            "__r.port).substring(0,64)});}catch(__x){__term='throw';__error="
            "__er(__x);break;}}}reportResult(JSON.stringify({found:!!__d,"
            "process_found:!!__p,pool_found:!!__q,pool_name:__q?String("
            "__q.getDhcpPoolName()).substring(0,64):'',rows:__rows,"
            "termination:__term,error:__error}));",
        )

    def register_dhcp_observers(
        self, clients: Sequence[tuple[str, str]]
    ) -> ProbeReading:
        """Register two bounded event callbacks on each owned client port.

        Unreachable in the amended Q3 profile, which declares M-DHCP-3 OMITTED.
        The subscription is made on the port, while Cisco documents
        `dhcpSucceed`/`dhcpFailed` on `DhcpClientProcess`, so the event source
        identity is unqualified; the Node stub emits them as `HostPort`, which
        masks the mismatch rather than measuring it. Nothing calls this until a
        separately reviewed event change fixes source identity, correlation and
        release evidence.
        """
        return self._read(
            "dhcp_events_register",
            self._owned_bag()
            + f"var __n={json.dumps([list(item) for item in clients])},__ok=0,"
            "__errors=[],__inert=0;if(__own){var __B=__r.dhcp={seq:0,entries:[]};"
            "var __events=['dhcpSucceed','dhcpFailed'];for(var __i=0;"
            "__i<__n.length;__i++){var __d=ipc.network().getDevice(__n[__i][0]);"
            "var __p=__d?__d.getPort(__n[__i][1]):null;for(var __j=0;"
            "__j<__events.length;__j++){var __e={device:__n[__i][0],"
            "interface:__n[__i][1],event:__events[__j],calls:0,events:[],"
            "released:false,ident:null};__e.fn=(function(e){return function(src,args){"
            "e.calls++;if(e.released){return;}try{if(!e.ident&&src){e.ident={"
            "className:String(src.className||''),uuid:String(src.objectUuid||'')};}}"
            "catch(__z){}if(e.events.length<8){var __a={};try{for(var __k in args){"
            "if(Object.keys(__a).length<8){__a[String(__k).substring(0,32)]="
            "String(args[__k]).substring(0,64);}}}catch(__z){}e.events.push({"
            "seq:++__B.seq,event:e.event,args:__a});}};})(__e);__B.entries.push(__e);"
            "try{if(!__p){throw new Error('port_absent');}__p.registerEvent("
            "__e.event,null,__e.fn);__ok++;}catch(__x){__errors.push({device:"
            "__e.device,event:__e.event,error:__er(__x)});}}}if(__errors.length){"
            "for(var __x=0;__x<__B.entries.length;__x++){if(!__B.entries[__x].released){"
            "__B.entries[__x].released=true;__inert++;}}}}reportResult(JSON.stringify({"
            "owned:__own,registered:__ok,errors:__errors,made_inert:__inert}));",
        )

    def collect_dhcp_observers(self) -> ProbeReading:
        """Read bounded event rows, release by identity where possible, then drop.

        Unreachable in the amended Q3 profile for the reason recorded on
        `register_dhcp_observers`. An unregister attempt that did not throw is
        not observed detachment, so this reading cannot resolve the resources
        it releases.
        """
        return self._read(
            "dhcp_events_collect",
            self._owned_bag()
            + "var __events=[],__releases=[],__dropped=false;if(__own&&__r.dhcp){"
            "var __B=__r.dhcp;for(var __i=0;__i<__B.entries.length;__i++){"
            "var __e=__B.entries[__i];for(var __j=0;__j<__e.events.length;__j++){"
            "if(__events.length<32){__events.push({device:__e.device,interface:"
            "__e.interface,event:__e.events[__j].event,seq:__e.events[__j].seq,"
            "args:__e.events[__j].args});}}var __o={device:__e.device,event:"
            "__e.event,attempted:false,threw:'',return_type:'',inert:false};"
            "var __av=typeof _ScriptModule!=='undefined'&&_ScriptModule&&typeof "
            "_ScriptModule.unregisterIpcEventByID==='function';if(__e.ident&&"
            "__e.ident.className&&__e.ident.uuid&&__av){__o.attempted=true;try{"
            "var __rv=_ScriptModule.unregisterIpcEventByID(__e.ident.className,"
            "__e.ident.uuid,__e.event,null,__e.fn);__o.return_type=typeof __rv;}"
            "catch(__x){__o.threw=__er(__x);}}else{__o.inert=true;}__e.released=true;"
            "__releases.push(__o);}delete __r.dhcp;__dropped=!__has(__r,'dhcp');}"
            "reportResult(JSON.stringify({owned:__own,events:__events,releases:"
            "__releases,dropped:__dropped}));",
        )
