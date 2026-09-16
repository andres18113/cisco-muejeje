# tests/

Pytest suite. It runs **offline**: no test requires Packet Tracer. Bridge cases
start a `PTCommandBridge` on an ephemeral port or simulate the Script Engine in
a thread.

For the current count and per-file breakdown, use:

```bash
python -m pytest --collect-only -q     # avoids pinning a count that will age
```

## Running tests

```bash
# All tests, from the repository root. Use the checkout-local interpreter.
.venv/Scripts/python.exe -m pytest

# One file
.venv/Scripts/python.exe -m pytest tests/test_full_build.py -v

# One test
.venv/Scripts/python.exe -m pytest tests/test_full_build.py::TestFullBuild::test_basic_2_routers -v
```

## Coverage

- **Domain:** validation, planning, addressing, repair suggestions, and estimates.
- **Generation:** Script Engine JavaScript and IOS CLI, including adversarial
  injection regressions.
- **Bridge security:** authentication, request limits, DNS-rebinding defenses,
  polling, batching, and the file-mailbox protocol.
- **Integration:** classic build flows, comparison, health checks, and
  reconciliation, plus typed Enterprise contracts.
