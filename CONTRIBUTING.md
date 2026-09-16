# Contributing

[`AGENTS.md`](AGENTS.md) is the shared repository authority. Its incorporated
[`engineering standard`](docs/engineering/standards.md) contains the normative
V-Model, risk, coding, architecture, security, evidence, and review rules. This
page is a non-normative quick start and does not duplicate those rules.

## Set up the checkout

```powershell
git clone https://github.com/andres18113/cisco-muejeje.git
cd cisco-muejeje
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[test,docs,quality]"
```

Use `.venv/bin/python` on Linux or macOS. Run commands from the repository root
with the interpreter owned by that checkout.

## Before opening a pull request

Create the proportional change brief required by the engineering standard, then
run the same entry points used by CI:

```powershell
.\.venv\Scripts\python.exe scripts\quality_gate.py --base cisco/main
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m mkdocs build --site-dir _site
git diff --check
```

Before delivery, commit the reviewed files, require a clean tree, and rerun the
gate with `--base cisco/main --delivery-commit HEAD`.

The offline suite must not require Packet Tracer. Report vulnerabilities through
the private process in [`SECURITY.md`](SECURITY.md), not a public issue. Use an
English conventional commit prefix such as `feat:`, `fix:`, `docs:`, or `chore:`
and explain why the change is needed.
