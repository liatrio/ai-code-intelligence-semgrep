# Semgrep PoC — reproducible lab for Liatrio AI Code Intelligence

This is the runnable PoC contract for issue
[#80](https://github.com/liatrio/ai-code-intelligence/issues/80). The comparison
matrix (scores, rationale, sources) lives in
[`liatrio/ai-code-intelligence`](https://github.com/liatrio/ai-code-intelligence)
under `research/semgrep/`; this repo is the runnable PoC that lets a client,
a developer, or a future evaluator reproduce those numbers on their own
machine.

Family: **Data flow** — specifically the *reachability / taint* piece the
other data-flow tools (CodebaseMemory, GitNexus, Joern, Graphify) do not
answer. Sits alongside those sibling PoCs and complements them; it does not
replace them for definition-and-callers or blast-radius questions.

The four [#75](https://github.com/liatrio/ai-code-intelligence/issues/75)
contract files live here:

- [`setup.py`](setup.py) — cross-platform installer + scan runner, JSON summary line.
- [`AGENTS.snippet.md`](AGENTS.snippet.md) — drop-in block for a repo's `AGENTS.md`.
- [`prompts.md`](prompts.md) — the five #80 data-flow prompts with frozen pass conditions.
- [`RESULTS.md`](RESULTS.md) — what actually happened per fixture.

Plus the harness ([`run-prompts.py`](run-prompts.py)) that measures baseline
vs `semgrep mcp` arms of a Claude Code session against the same prompts.

## Prerequisites

- **Python 3.10+** and **git**.
- Either **uv** (`brew install uv`) or **pipx** (`python3 -m pip install --user pipx`).
- ~120 MB of disk for the Semgrep Community Edition install (uv- or
  pipx-managed virtualenv).

No Docker. No AppSec Platform account. No `SEMGREP_APP_TOKEN`. No
`semgrep login`. Issue #80 is explicit: Community Edition with local rules
only, because one of the two fixtures (`liatrio-knowledge`) is private and
enabling the AppSec Platform uploads findings.

## First run

```bash
python3 setup.py --check
python3 setup.py
```

That verifies the prerequisites, then installs
`semgrep=={pinned version}` via `uv tool install` (or `pipx install` as a
fallback), and stops. No fixture writes, no network calls beyond the
PyPI package download.

## Point at a fixture

Clone the fixtures called out in
[#80](https://github.com/liatrio/ai-code-intelligence/issues/80) — see
[`fixtures/README.md`](fixtures/README.md) — into a disposable directory
of your choice, then:

```bash
python3 setup.py --scan /tmp/lab/gratibot          --rules ./rules
python3 setup.py --scan /tmp/lab/liatrio-knowledge --rules ./rules  # private; local-only
```

Each invocation runs `semgrep scan --config ./rules --metrics=off --json
--json-output <state>/scans/<sha16>/<timestamp>.json <repo>`. There is no
persistent index — Semgrep re-parses on every scan — and no reindex-on-merge
flow. The `--status` subcommand is present for parity with the sibling
PoCs and returns a structural `n/a`.

The private fixture (`liatrio-knowledge`) is only in scope when this lab
runs fully local — pinned Semgrep CE, pinned local ruleset, `--metrics=off`,
and no `SEMGREP_APP_TOKEN` in the environment. `setup.py` refuses to run
if any of that is violated.

## Reset

```bash
python3 setup.py --clean
```

Uninstalls `semgrep` from its uv/pipx location and removes the lab state
directory. Does not touch anything outside that directory.

## Repository layout

```
setup.py                 Cross-platform installer + scan runner.
run-prompts.py           Baseline vs Semgrep-MCP harness for prompts.md.
prompts.md               Five data-flow prompts + pass conditions (frozen before runs).
AGENTS.snippet.md        Composable snippet for a repo's AGENTS.md.
AGENTS.md                Notes about this PoC repo for future agents.
RESULTS.md               Measured outcomes per fixture (updated per wave).
tools.lock.json          Pin (semgrep + how `semgrep mcp` is wired).
versions.env             Human-readable pin.
.env.example             Optional overrides (SEMGREP_LAB_STATE, metrics knob).
rules/                   Pinned local ruleset — sufficient for the five prompts.
fixtures/README.md       How to point setup.py at fixture checkouts.
Makefile                 Convenience wrapper around setup.py.
```

## CI

`.github/workflows/ci.yml` installs the pinned tool, runs `python3 setup.py --check`,
runs a keyless smoke (validating `rules/` and scanning public `liatrio/gratibot` at a pinned commit), and always tears down. It runs on
pull requests, on pushes to `main`, by hand (`workflow_dispatch`), and weekly
(Mondays 06:31 UTC), so a pin that stops resolving upstream shows up even when
nobody is touching the repo.

When a scheduled run fails, the `notify-failure` job opens an issue labelled
`ci-failure`, or comments on the one already open. Close it once `main` is
green again.

## Licence

The lab code is Apache-2.0. Semgrep Community Edition is LGPL-2.1-or-later
(see the upstream [repository](https://github.com/semgrep/semgrep)).
Semgrep-maintained Registry rules ship under the Semgrep Rules License;
this lab's `rules/` directory is Apache-2.0 alongside the rest of this
repo.
