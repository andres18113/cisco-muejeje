"""Execute the ACTUAL generated S2 mail scripts against a Node stub network.

Every script is the one `PacketTracerEnterpriseServiceRuntime` produces,
captured through its channel callable and evaluated by Node with the stub's
engine global as `this`, so claims written by one evaluation are there for the
next exactly as they would be in Packet Tracer. Nothing is rewritten for the
harness.

The oracle is the stub's own state and call log -- the accounts, the client
fields, the mailbox, every `sendMail` and every forbidden member call -- never
the row the runtime reports, because the row is what is being checked.

Skipped only when Node is missing locally; under `GITHUB_ACTIONS` it fails.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import threading
import time
from typing import Any

import pytest

from packet_tracer_mcp.domain.enterprise.models.configuration_runtime import (
    ActionExecutionStatus,
    MutationResidue,
    decide_mutation,
)
from packet_tracer_mcp.domain.enterprise.models.execution import (
    DispatchFact,
    FootprintFact,
    OperationSemantics,
    ResultFact,
)
from packet_tracer_mcp.domain.enterprise.models.service_plan import (
    ConfigureEmailClient,
    EnablePop3Service,
    EnableSmtpService,
    EnsureEmailAccount,
    SendMailMessage,
    ServiceEvidenceKind,
    ServicePhase,
    ServiceType,
    ServiceVerificationExpectation,
    ServiceVerificationKind,
    mail_message_text,
)
from packet_tracer_mcp.domain.enterprise.models.service_runtime import ObservationFact
from packet_tracer_mcp.infrastructure.execution.enterprise_service_runtime import (
    MAILBOX_SCAN_LIMIT,
    PacketTracerEnterpriseServiceRuntime,
)
from packet_tracer_mcp.infrastructure.execution.secret_resolver import (
    EnvironmentSecretResolver,
)
from packet_tracer_mcp.infrastructure.execution.transport_outcome import (
    BridgeDispatchOutcome,
)

SERVER = "__MCP_E6_SERVER"
PC1 = "__MCP_E6_PC1"
PC2 = "__MCP_E6_PC2"
SERVER_IP = "198.18.160.2"
DOMAIN = "lab.example"
#: Every character class a serialized credential has to survive.
PASSWORD = 'pa"ss\\w</script>%20 ñ'
SECRETS = {
    "PT_MCP_SECRET_MAIL_USER1": PASSWORD,
    "PT_MCP_SECRET_MAIL_USER2": "second-pw",
}
FORBIDDEN_MEMBERS = (
    "getPassword",
    "getAllEmailAcctAsStrings",
    "getMailIpc",
    "registerEvent",
    "deleteUser",
    "deleteMailAt",
    "changePassword",
    "updateAllAccounts",
)
_ALLOWED_PROCESSES = {"EmailServer", "SmtpServer", "Pop3Server", "EmailClient"}


def _needs_node():
    """Skip locally without Node; fail in CI, where Node must be present."""
    if shutil.which("node") is not None:
        return None
    if os.environ.get("GITHUB_ACTIONS"):
        pytest.fail("Node is required for the generated-script harness in CI.")
    return pytest.skip("Node is unavailable")


_STUB_JS = r"""
const S = __hState;
const log = [];
const forbid = (name) => {
  S.forbidden_calls.push(name);
  throw new Error('forbidden member called: ' + name);
};
const fails = (name) => {
  S.calls[name] = (S.calls[name] || 0) + 1;
  if (S.failing.indexOf(name) >= 0) { return true; }
  const before = S.fail_before[name];
  return before !== undefined && S.calls[name] <= before;
};
const guard = (name) => {
  if (fails(name)) { throw new Error('stub failure: ' + name + S.failure_detail); }
};
const serverUser = (dev, name) => {
  const account = dev.accounts[name];
  if (!account) { return null; }
  return {
    getUser: () => { log.push('getUser'); return name; },
    getPassword: () => forbid('getPassword'),
    getMailBox: () => ({
      getMails: () => {
        log.push('getMails:' + name);
        return account.mails.map((m) => ({from: m.from, rcpt: m.rcpt,
          subject: m.subject, content: m.content, dateTime: m.dateTime || ''}));
      },
      deleteMailAt: () => forbid('deleteMailAt'),
    }),
  };
};
const deliver = (to, mail) => {
  for (const name of Object.keys(S.devices)) {
    const dev = S.devices[name];
    if (dev.kind !== 'server') { continue; }
    const local = String(to).split('@')[0];
    if (dev.accounts[local]) { dev.accounts[local].mails.push(mail); }
  }
};
const serverProcess = (dev, name) => {
  if (name === 'SmtpServer') {
    return {
      isEnabled: () => { guard('smtp.isEnabled'); return dev.smtp.enabled; },
      setEnable: (v) => { guard('smtp.setEnable'); dev.smtp.enabled = !!v; },
      getServerDomainName: () => { guard('getServerDomainName'); return dev.smtp.domain; },
      setServerDomainName: (v) => {
        guard('setServerDomainName');
        dev.smtp.domain = S.stores_domain_instead === null ? String(v) : S.stores_domain_instead;
      },
    };
  }
  if (name === 'Pop3Server') {
    return {
      isEnabled: () => { guard('pop3.isEnabled'); return dev.pop3.enabled; },
      setEnable: (v) => { guard('pop3.setEnable'); dev.pop3.enabled = !!v; },
    };
  }
  if (name === 'EmailServer') {
    return {
      addUser: (n, p) => {
        guard('addUser');
        S.add_user_calls.push(String(n));
        if (!dev.accounts[n]) { dev.accounts[n] = {password: String(p), mails: []}; }
        return S.add_user_returns;
      },
      getEmailUser: (n) => { guard('getEmailUser'); return serverUser(dev, String(n)); },
      getAllEmailAcctAsStrings: () => forbid('getAllEmailAcctAsStrings'),
      deleteUser: () => forbid('deleteUser'),
      changePassword: () => forbid('changePassword'),
      updateAllAccounts: () => forbid('updateAllAccounts'),
    };
  }
  return null;
};
const clientProcess = (dev, name, receiver) => {
  if (name !== 'EmailClient') { return null; }
  const e = dev.email;
  const user = {
    getName: () => { guard('client.getName'); return e.name; },
    getUser: () => e.user,
    getMailId: () => e.mailId,
    getSmtpServer: () => e.smtp,
    getPop3Server: () => e.pop3,
    getPassword: () => forbid('getPassword'),
    setName: (v) => { guard('client.setName'); e.name = String(v); },
    setUser: (v) => { e.user = String(v); },
    setMailId: (v) => { e.mailId = String(v); },
    setSmtpServer: (v) => { e.smtp = String(v); },
    setPop3Server: (v) => { e.pop3 = String(v); },
    setPassword: (v) => { guard('client.setPassword'); e.password = String(v); },
  };
  return {
    getEmailUser: () => user,
    getSmtpClient: () => ({
      sendMail: (from, to, subject, body, password, server) => {
        guard('sendMail.before');
        const claims = receiver.__mcpE6Claims || {};
        const claim = claims['email_client:' + dev.name];
        S.sends.push({device: dev.name, from: String(from), to: String(to),
          subject: String(subject), body: String(body), password: String(password),
          server: String(server), claim_state_at_call: claim ? claim.state : null});
        if (S.deliver) {
          deliver(to, {from: String(from), rcpt: String(to), subject: String(subject),
            content: String(body)});
        }
        if (S.send_throws_after_effect) {
          throw new Error('stub failure after send: ' + String(password));
        }
        return true;
      },
      cancelSend: () => forbid('cancelSend'),
    }),
    getPop3Client: () => ({getMailIpc: () => forbid('getMailIpc')}),
  };
};
const deviceApi = (name) => {
  const dev = S.devices[name];
  if (!dev) { return null; }
  dev.name = name;
  return {
    getName: () => name,
    getProcess: (process) => {
      log.push('getProcess:' + process);
      return dev.kind === 'server'
        ? serverProcess(dev, String(process))
        : clientProcess(dev, String(process), S.globals);
    },
  };
};
global.ipc = {network: () => ({getDevice: (n) => deviceApi(String(n))})};
let reported = null;
try {
  (new Function('reportResult', __hScript)).call(S.globals,
    (value) => { reported = String(value); });
} catch (error) {
  reported = 'PT_ERROR: ' + error;
}
process.stdout.write(JSON.stringify({reported: reported, state: S, log: log}));
"""


def _client() -> dict[str, Any]:
    return {
        "kind": "client",
        "email": {
            "name": "",
            "user": "",
            "mailId": "",
            "smtp": "",
            "pop3": "",
            "password": "",
        },
    }


class _MailEngine:
    """A channel backed by the Node stub, recording every script it ran."""

    def __init__(self, **overrides: Any) -> None:
        """Seed one server and two clients, then apply per-scenario switches."""
        self.state: dict[str, Any] = {
            "globals": {},
            "devices": {
                SERVER: {
                    "kind": "server",
                    "smtp": {"enabled": False, "domain": ""},
                    "pop3": {"enabled": False},
                    "accounts": {},
                },
                PC1: _client(),
                PC2: _client(),
            },
            "sends": [],
            "add_user_calls": [],
            "forbidden_calls": [],
            "calls": {},
            "failing": [],
            "fail_before": {},
            "failure_detail": "",
            "deliver": True,
            "send_throws_after_effect": False,
            "add_user_returns": True,
            "stores_domain_instead": None,
        }
        self.state.update(overrides)
        self.scripts: list[str] = []
        self.reports: list[str | None] = []
        self.lose_answers = False
        #: Lose only the answers of scripts containing this text.
        self.lose_answers_for = ""
        self.active = 0
        self.max_active = 0
        self.lock = threading.Lock()

    def evaluate(self, script: str) -> str | None:
        """Run one script in Node and keep the stub state it left behind."""
        with self.lock:
            self.active += 1
            self.max_active = max(self.max_active, self.active)
        try:
            time.sleep(0.01)
            program = (
                "const __hState = "
                + json.dumps(self.state)
                + ";\nconst __hScript = "
                + json.dumps(script)
                + ";\n"
                + _STUB_JS
            )
            completed = subprocess.run(
                [shutil.which("node"), "-"],
                input=program,
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=True,
            )
            observed = json.loads(completed.stdout)
            self.state = observed["state"]
            self.scripts.append(script)
            self.reports.append(observed["reported"])
            return observed["reported"]
        finally:
            with self.lock:
                self.active -= 1

    def dispatch_and_wait(self, script: str, _timeout: float) -> BridgeDispatchOutcome:
        """Deliver the script; optionally lose the answer after it ran."""
        body = self.evaluate(script)
        lost = self.lose_answers or (
            bool(self.lose_answers_for) and self.lose_answers_for in script
        )
        if lost:
            return BridgeDispatchOutcome(
                dispatch=DispatchFact.ACCEPTED,
                result=ResultFact.NOT_OBSERVED,
                detail="result_not_observed",
            )
        return BridgeDispatchOutcome(
            dispatch=DispatchFact.ACCEPTED,
            result=ResultFact.CORRELATED,
            body=body,
        )

    @property
    def server(self) -> dict[str, Any]:
        """Return the stub server's state."""
        return self.state["devices"][SERVER]

    def client(self, name: str) -> dict[str, Any]:
        """Return one stub client's email fields."""
        return self.state["devices"][name]["email"]

    def claims(self) -> dict[str, Any]:
        """Return the production claims global as the engine holds it."""
        return self.state["globals"].get("__mcpE6Claims", {})


class _Clock:
    """A monotonic clock that advances only when the runtime sleeps."""

    def __init__(self) -> None:
        """Start at zero."""
        self.now = 0.0

    def __call__(self) -> float:
        """Return the current fake time."""
        return self.now

    def sleep(self, seconds: float) -> None:
        """Advance instead of waiting."""
        self.now += seconds


def _runtime(engine: _MailEngine, environ: dict[str, str] | None = None):
    clock = _Clock()
    return PacketTracerEnterpriseServiceRuntime(
        lambda: [],
        lambda script, timeout: None,
        dispatch_and_wait=engine.dispatch_and_wait,
        secret_resolver=EnvironmentSecretResolver(
            SECRETS if environ is None else environ
        ),
        clock=clock,
        sleeper=clock.sleep,
    )


def _common(host: str = SERVER, model: str = "Server-PT") -> dict[str, Any]:
    return dict(
        service_id="service/hq/lab-mail",
        service_type=ServiceType.SMTP,
        host_device_id=host,
        host_device_name=host,
        host_model=model,
        site_id="hq",
        required_capability="service_smtp_application",
    )


def _enable_smtp() -> EnableSmtpService:
    return EnableSmtpService(
        id="enable-smtp", phase=ServicePhase.ENABLE, domain_name=DOMAIN, **_common()
    )


def _account(username: str = "user1") -> EnsureEmailAccount:
    return EnsureEmailAccount(
        id=f"account-{username}",
        phase=ServicePhase.CONTENT,
        username=username,
        secret_ref=f"mail.{username}",
        **_common(),
    )


def _configure(host: str = PC1, username: str = "user1") -> ConfigureEmailClient:
    return ConfigureEmailClient(
        id=f"client-{host}",
        phase=ServicePhase.CLIENT,
        username=username,
        mail_id=f"{username}@{DOMAIN}",
        display_name=username.title(),
        smtp_server=SERVER_IP,
        pop3_server=SERVER_IP,
        secret_ref=f"mail.{username}",
        **_common(host, "PC-PT"),
    )


def _send(
    host: str = PC1, recipient: str = "user2", nonce: str = "n0nce1"
) -> SendMailMessage:
    return SendMailMessage(
        id=f"send-{host}-{recipient}",
        phase=ServicePhase.MESSAGE,
        message_ref=f"msg/{host}/{recipient}",
        sender_mail_id=f"user1@{DOMAIN}",
        recipient_mail_id=f"{recipient}@{DOMAIN}",
        recipient_username=recipient,
        smtp_server=SERVER_IP,
        secret_ref="mail.user1",
        nonce=nonce,
        **_common(host, "PC-PT"),
    )


def _expectation(kind: ServiceVerificationKind, **fields: Any):
    defaults: dict[str, Any] = dict(
        id=f"verify-{kind.value}",
        service_id="service/hq/lab-mail",
        action_id="send-x",
        kind=kind,
        evidence_kind=ServiceEvidenceKind.BEHAVIORAL,
        host_device_id=SERVER,
        host_device_name=SERVER,
        client_device_id=PC2,
        client_device_name=PC2,
        host_model="Server-PT",
        client_model="PC-PT",
    )
    defaults.update(fields)
    return ServiceVerificationExpectation(**defaults)


def _delivered(nonce: str = "n0nce1", **expected: Any):
    values = {
        "message_ref": "msg/pc1/user2",
        "nonce": nonce,
        "recipient_username": "user2",
        "sender_mail_id": f"user1@{DOMAIN}",
        "recipient_mail_id": f"user2@{DOMAIN}",
    }
    values.update(expected)
    return _expectation(ServiceVerificationKind.SMTP_DELIVERED, expected=values)


def _seed_account(engine: _MailEngine, name: str, mails=()) -> None:
    engine.server["accounts"][name] = {
        "password": "operator-owned",
        "mails": list(mails),
    }


def _mail(nonce: str, **fields: str) -> dict[str, str]:
    text = mail_message_text(nonce)
    mail = {
        "from": f"user1@{DOMAIN}",
        "rcpt": f"user2@{DOMAIN}",
        "subject": text,
        "content": text,
    }
    mail.update(fields)
    return mail


def _text_of(row) -> str:
    return json.dumps(row.model_dump(mode="json"), ensure_ascii=False)


# -- server configuration --------------------------------------------------------


def test_enabling_smtp_sets_and_reads_back_flag_and_domain():
    """R-MAIL-01: a changed success is APPLIED/CHANGED and fully covered."""
    _needs_node()
    engine = _MailEngine()
    [row] = _runtime(engine).apply_actions([_enable_smtp()])
    decision = decide_mutation(row)

    assert engine.server["smtp"] == {"enabled": True, "domain": DOMAIN}
    assert decision.row == "12"
    assert row.footprint is FootprintFact.COVERED


def test_a_domain_the_server_stored_differently_is_an_observed_residue():
    """The post-read, not the setter, decides: a wrong domain is unsatisfied."""
    _needs_node()
    engine = _MailEngine(stores_domain_instead="other.example")
    [row] = _runtime(engine).apply_actions([_enable_smtp()])
    decision = decide_mutation(row)

    assert engine.server["smtp"]["domain"] == "other.example"
    assert decision.row == "14"
    assert decision.residue is MutationResidue.CHANGED


def test_enabling_pop3_is_a_covered_flag_setter():
    """R-MAIL-01: POP3 has one flag, set and read back."""
    _needs_node()
    engine = _MailEngine()
    action = EnablePop3Service(
        id="enable-pop3",
        phase=ServicePhase.ENABLE,
        **{**_common(), "service_type": ServiceType.POP3},
    )
    [row] = _runtime(engine).apply_actions([action])

    assert engine.server["pop3"]["enabled"] is True
    assert decide_mutation(row).row == "12"


def test_a_missing_account_is_added_once_and_its_credential_stays_unverified():
    """R-MAIL-02: the add is attempted and PARTIAL; existence is not the password."""
    _needs_node()
    engine = _MailEngine()
    [row] = _runtime(engine).apply_actions([_account()])
    decision = decide_mutation(row)

    assert engine.state["add_user_calls"] == ["user1"]
    assert engine.server["accounts"]["user1"]["password"] == PASSWORD
    assert row.operation is OperationSemantics.ENSURE_PRESENT
    assert decision.row == "18"
    assert decision.residue is MutationResidue.UNKNOWN
    assert decision.cause == "footprint_partial:email_account_credential"


def test_an_existing_account_is_never_changed():
    """R-SEC-05: no add, no password change; the credential stays unverified."""
    _needs_node()
    engine = _MailEngine()
    _seed_account(engine, "user1")
    [row] = _runtime(engine).apply_actions([_account()])
    decision = decide_mutation(row)

    assert engine.state["add_user_calls"] == []
    assert engine.server["accounts"]["user1"]["password"] == "operator-owned"
    assert decision.row == "17"
    assert decision.status is ActionExecutionStatus.NO_OP
    assert "account_preexisting" in decision.cause
    assert "credential_unverified" in decision.cause


def test_an_unreadable_account_is_never_treated_as_absent():
    """A getter failure refuses the add instead of proving nonexistence."""
    _needs_node()
    engine = _MailEngine(failing=["getEmailUser"])
    [row] = _runtime(engine).apply_actions([_account()])
    decision = decide_mutation(row)

    assert engine.state["add_user_calls"] == []
    assert decision.row == "21"
    assert decision.cause == "not_attempted:refused:precondition_unobserved"
    assert decision.sticky is False


# -- client configuration ----------------------------------------------------------


def test_a_client_is_configured_and_read_back_except_its_password():
    """R-MAIL-03: every field but the password is compared after the setters."""
    _needs_node()
    engine = _MailEngine()
    before_other = json.dumps(engine.client(PC2))
    [row] = _runtime(engine).apply_actions([_configure()])
    decision = decide_mutation(row)

    assert engine.client(PC1) == {
        "name": "User1",
        "user": "user1",
        "mailId": f"user1@{DOMAIN}",
        "smtp": SERVER_IP,
        "pop3": SERVER_IP,
        "password": PASSWORD,
    }
    assert json.dumps(engine.client(PC2)) == before_other
    assert decision.row == "18"
    assert decision.cause == "footprint_partial:email_client_password"


def test_a_claimed_client_is_never_reconfigured():
    """R-OBS-04: an unresolved claim on the client refuses every setter."""
    _needs_node()
    engine = _MailEngine()
    engine.state["globals"]["__mcpE6Claims"] = {
        f"email_client:{PC1}": {"state": "unknown", "op_id": "other", "nonce": "x"}
    }
    [row] = _runtime(engine).apply_actions([_configure()])
    decision = decide_mutation(row)

    assert engine.client(PC1)["user"] == ""
    assert engine.state["calls"].get("client.setName") is None
    assert decision.row == "21"
    assert decision.cause == "not_attempted:refused:subject_claimed"


# -- the execute-once send ---------------------------------------------------------


def test_the_claim_is_written_before_the_single_send():
    """R-EVT-06: `in_progress` at the call, `completed` afterwards, one send."""
    _needs_node()
    engine = _MailEngine()
    [row] = _runtime(engine).apply_actions([_send()])
    decision = decide_mutation(row)
    [sent] = engine.state["sends"]
    claim = engine.claims()[f"email_client:{PC1}"]

    assert sent["claim_state_at_call"] == "in_progress"
    assert sent["subject"] == sent["body"] == mail_message_text("n0nce1")
    assert sent["password"] == PASSWORD
    assert sent["server"] == SERVER_IP
    assert claim["state"] == "completed"
    assert claim["op_id"] == "send-__MCP_E6_PC1-user2"
    assert decision.row == "22"
    assert decision.sticky is True
    assert decision.frontier is False


def test_a_send_that_throws_after_its_effect_leaves_an_unknown_claim():
    """The effect may have happened; the claim says so and quarantines."""
    _needs_node()
    engine = _MailEngine(send_throws_after_effect=True)
    [row] = _runtime(engine).apply_actions([_send()])
    decision = decide_mutation(row)

    assert len(engine.state["sends"]) == 1
    assert engine.claims()[f"email_client:{PC1}"]["state"] == "unknown"
    assert decision.row == "22"
    assert row.call_error
    assert PASSWORD not in _text_of(row)


def test_a_replayed_send_script_sends_nothing_more_and_stays_unknown():
    """A second evaluation of the same operation finds its own claim.

    Re-applying the same bound action produces the identical script, which is
    exactly what a channel re-delivery evaluates. The engine sends nothing
    more, and the second answer reports the earlier effect as unknown rather
    than as "not attempted".
    """
    _needs_node()
    engine = _MailEngine()
    runtime = _runtime(engine)
    runtime.apply_actions([_send()])
    [replayed] = runtime.apply_actions([_send()])
    decision = decide_mutation(replayed)

    assert engine.scripts[0] == engine.scripts[1]
    assert len(engine.state["sends"]) == 1
    assert decision.row == "22"
    assert replayed.attempted is None
    assert decision.cause == "effect_unobservable:own_claim_replayed"


def test_a_foreign_claim_refuses_the_send():
    """A claim held by another operation or run is never overridden."""
    _needs_node()
    engine = _MailEngine()
    engine.state["globals"]["__mcpE6Claims"] = {
        f"email_client:{PC1}": {
            "state": "completed",
            "op_id": "send-__MCP_E6_PC1-user2",
            "nonce": "an-earlier-run",
        }
    }
    [row] = _runtime(engine).apply_actions([_send()])

    assert engine.state["sends"] == []
    assert decide_mutation(row).row == "21"
    assert engine.claims()[f"email_client:{PC1}"]["nonce"] == "an-earlier-run"


def test_a_lost_answer_is_unknown_and_never_redispatched():
    """The send ran; the runtime does not learn it and does not try again."""
    _needs_node()
    engine = _MailEngine()
    engine.lose_answers = True
    [row] = _runtime(engine).apply_actions([_send()])
    decision = decide_mutation(row)

    assert len(engine.scripts) == 1
    assert len(engine.state["sends"]) == 1
    assert decision.status is ActionExecutionStatus.APPLIED
    assert decision.sticky is True
    assert decision.frontier is False


def test_a_send_without_a_bound_nonce_is_never_dispatched():
    """An unbound message cannot be correlated, so it is not sent."""
    _needs_node()
    engine = _MailEngine()
    [row] = _runtime(engine).apply_actions([_send(nonce="")])

    assert engine.scripts == []
    assert row.dispatch is DispatchFact.NOT_SUBMITTED
    assert decide_mutation(row).row == "1"


# -- supporting mailbox presence ---------------------------------------------------


def test_a_matching_message_is_mailbox_presence_and_nothing_more():
    """R-MAIL-04 supporting: presence is not `mailSent` and not POP3."""
    _needs_node()
    engine = _MailEngine()
    _seed_account(engine, "user2", [_mail("n0nce1")])
    row = _runtime(engine).verify(_delivered())

    assert row.observation is ObservationFact.OBSERVED
    # Observed presence, never verification of the mail service: VERIFIED
    # would roll up into service usability while the send stays unobserved.
    assert row.status is ActionExecutionStatus.PARTIAL
    assert row.claim_level == "server_mailbox_presence"
    assert {
        "not_a_mailsent_success_event",
        "not_pop3_retrieval_evidence",
        "supporting_evidence_only",
    } <= set(row.limitations)


def test_a_nonce_message_with_other_fields_contradicts_the_pair():
    """The nonce is present but from a different sender: a fresh negative."""
    _needs_node()
    engine = _MailEngine()
    _seed_account(engine, "user2", [_mail("n0nce1", **{"from": "intruder@x"})])
    row = _runtime(engine).verify(_delivered())

    assert row.observation is ObservationFact.CONTRADICTED
    assert row.cause == "nonce_message_fields_mismatch"


def test_a_missing_message_is_unknown_at_the_deadline_never_failed():
    """Absence within the window is not proof the message was not sent."""
    _needs_node()
    engine = _MailEngine()
    _seed_account(engine, "user2")
    row = _runtime(engine).verify(_delivered())

    assert row.observation is ObservationFact.INCONCLUSIVE
    assert row.status is ActionExecutionStatus.UNKNOWN
    assert row.cause == "message_not_observed_within_deadline"
    assert len(engine.scripts) > 1


def test_a_truncated_scan_cannot_establish_absence():
    """More mail than the bound: an unscanned message may still be there."""
    _needs_node()
    engine = _MailEngine()
    unrelated = [_mail(f"other{i}") for i in range(MAILBOX_SCAN_LIMIT + 5)]
    _seed_account(engine, "user2", [_mail("n0nce1"), *unrelated])
    row = _runtime(engine).verify(_delivered())

    assert row.observation is ObservationFact.INCONCLUSIVE
    assert row.cause == "mailbox_scan_truncated"


def test_unrelated_mailbox_content_never_leaves_the_engine():
    """The reader returns counts and flags, never another message's text."""
    _needs_node()
    engine = _MailEngine()
    private = _mail("zzz", subject="PRIVATE-SUBJECT", content="PRIVATE-BODY")
    _seed_account(engine, "user2", [private, _mail("n0nce1")])
    row = _runtime(engine).verify(_delivered())

    assert row.observation is ObservationFact.OBSERVED
    for report in engine.reports:
        assert "PRIVATE" not in str(report)
    assert "PRIVATE" not in _text_of(row)


def test_an_absent_recipient_account_is_unobservable():
    """A missing mailbox says nothing about delivery."""
    _needs_node()
    engine = _MailEngine()
    row = _runtime(engine).verify(_delivered())

    assert row.observation is ObservationFact.SUBJECT_NOT_FOUND
    assert row.status is ActionExecutionStatus.UNOBSERVABLE


# -- direct read-backs --------------------------------------------------------------


def _server_state(**expected: Any):
    values = {
        "enabled": True,
        "service_type": "smtp",
        "domain_name": DOMAIN,
        "accounts_json": json.dumps(["user1"]),
    }
    values.update(expected)
    return _expectation(
        ServiceVerificationKind.DIRECT_SERVICE_STATE,
        evidence_kind=ServiceEvidenceKind.DIRECT_STATE,
        client_device_id="",
        client_device_name="",
        expected=values,
    )


def test_the_smtp_direct_read_back_names_what_it_cannot_prove():
    """Flag, domain and existence match; the credential stays unverified."""
    _needs_node()
    engine = _MailEngine()
    engine.server["smtp"] = {"enabled": True, "domain": DOMAIN}
    _seed_account(engine, "user1")
    row = _runtime(engine).verify(_server_state())

    assert row.observation is ObservationFact.OBSERVED
    assert "credential_claim:unverified" in row.limitations


def test_a_wrong_domain_contradicts_the_server_state():
    """A readable, different domain is a fresh negative."""
    _needs_node()
    engine = _MailEngine()
    engine.server["smtp"] = {"enabled": True, "domain": "other.example"}
    _seed_account(engine, "user1")

    assert (
        _runtime(engine).verify(_server_state()).observation
        is ObservationFact.CONTRADICTED
    )


def test_an_unreadable_account_leaves_the_server_state_inconclusive():
    """A throwing getter is unobserved, not an absent account."""
    _needs_node()
    engine = _MailEngine(failing=["getEmailUser"])
    engine.server["smtp"] = {"enabled": True, "domain": DOMAIN}
    row = _runtime(engine).verify(_server_state())

    assert row.observation is ObservationFact.INCONCLUSIVE
    assert row.cause == "account_unreadable"


def test_the_client_read_back_compares_every_field_but_the_password():
    """EMAIL_CLIENT_STATE: a changed field contradicts; the password is never read."""
    _needs_node()
    engine = _MailEngine()
    engine.client(PC1).update(
        name="User1",
        user="user1",
        mailId=f"user1@{DOMAIN}",
        smtp=SERVER_IP,
        pop3=SERVER_IP,
    )
    expected = {
        "name": "User1",
        "user": "user1",
        "mail_id": f"user1@{DOMAIN}",
        "smtp_server": SERVER_IP,
        "pop3_server": SERVER_IP,
    }
    state = _expectation(
        ServiceVerificationKind.EMAIL_CLIENT_STATE,
        evidence_kind=ServiceEvidenceKind.DIRECT_STATE,
        client_device_id=PC1,
        client_device_name=PC1,
        expected=expected,
    )
    runtime = _runtime(engine)

    assert runtime.verify(state).observation is ObservationFact.OBSERVED
    engine.client(PC1)["smtp"] = "203.0.113.9"
    assert runtime.verify(state).observation is ObservationFact.CONTRADICTED
    assert engine.state["forbidden_calls"] == []


# -- gated event verification ------------------------------------------------------


@pytest.mark.parametrize(
    "kind",
    [
        ServiceVerificationKind.SMTP_SEND,
        ServiceVerificationKind.POP3_RETRIEVE,
        ServiceVerificationKind.EMAIL_END_TO_END,
    ],
)
def test_event_dependent_rows_dispatch_nothing_under_the_fallback(kind):
    """R-EVT-05: no observer is registered and no retrieval is attempted."""
    _needs_node()
    engine = _MailEngine()
    row = _runtime(engine).verify(_expectation(kind, expected={"nonce": "n0nce1"}))

    assert engine.scripts == []
    assert row.observation is ObservationFact.NOT_ATTEMPTED
    assert row.status is ActionExecutionStatus.UNOBSERVABLE
    assert row.cause == "event_observation_gated:r_evt_05_fallback"


# -- corpus, secrets and serialization ------------------------------------------------


def _corpus() -> tuple[list[str], _MailEngine]:
    engine = _MailEngine()
    _seed_account(engine, "user2", [_mail("n0nce1")])
    runtime = _runtime(engine)
    runtime.apply_actions([_enable_smtp()])
    runtime.apply_actions([_account()])
    runtime.apply_actions([_configure()])
    runtime.apply_actions([_send()])
    runtime.verify(_delivered())
    runtime.verify(_server_state(accounts_json=json.dumps(["user1", "user2"])))
    return list(engine.scripts), engine


def test_no_generated_mail_script_names_a_forbidden_member():
    """R-SEC-03 and R-ENTRY-07, over every script the scenarios produced."""
    _needs_node()
    scripts, engine = _corpus()

    assert len(scripts) >= 6
    for script in scripts:
        for member in FORBIDDEN_MEMBERS:
            assert member not in script, member
    assert engine.state["forbidden_calls"] == []


def test_mail_scripts_reach_only_the_allowlisted_processes():
    """R-SEC-03: the process names are a closed set."""
    import re

    _needs_node()
    scripts, _ = _corpus()
    names = {
        name
        for script in scripts
        for name in re.findall(r'getProcess\("([A-Za-z0-9]+)"\)', script)
    }

    assert names and names <= _ALLOWED_PROCESSES


def test_an_echoed_credential_is_redacted_from_every_row():
    """R-SEC-01: the value reaches the engine, never a row or snapshot."""
    _needs_node()
    engine = _MailEngine(failing=["client.setPassword"])
    engine.state["failure_detail"] = " while setting " + PASSWORD
    [row] = _runtime(engine).apply_actions([_configure()])

    assert row.call_error
    text = _text_of(row)
    for form in (
        PASSWORD,
        json.dumps(PASSWORD)[1:-1],
        json.dumps(PASSWORD, ensure_ascii=False)[1:-1],
    ):
        assert form not in text


def test_an_unresolvable_credential_dispatches_nothing():
    """A missing secret refuses before a script exists."""
    _needs_node()
    engine = _MailEngine()
    [row] = _runtime(engine, environ={}).apply_actions([_account()])

    assert engine.scripts == []
    assert row.dispatch is DispatchFact.NOT_SUBMITTED
    assert row.cause == "secret_unresolved:not_set"


def test_mail_batches_from_two_callers_never_overlap():
    """R-OBS-04: one mail operation at a time through one runtime process."""
    _needs_node()
    engine = _MailEngine()
    runtime = _runtime(engine)
    threads = [
        threading.Thread(
            target=runtime.apply_actions,
            args=(
                [
                    _configure(host),
                ],
            ),
        )
        for host in (PC1, PC2, PC1, PC2)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert len(engine.scripts) == 4
    assert engine.max_active == 1
