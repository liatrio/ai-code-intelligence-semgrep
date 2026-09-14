# Agent notes — Semgrep PoC

This is a **runnable PoC**, not the comparison matrix. Scores stay in
https://github.com/liatrio/ai-code-intelligence (`research/semgrep/`,
issues [#80](https://github.com/liatrio/ai-code-intelligence/issues/80) and
[#75](https://github.com/liatrio/ai-code-intelligence/issues/75)).

## First run

From a clean clone (Python `>=3.10`, git, uv or pipx):

```bash
python3 setup.py --check
python3 setup.py
```

That installs pinned `semgrep=={version}` (see
[`tools.lock.json`](tools.lock.json)) via `uv tool install` or `pipx
install`. No API key. No AppSec Platform login. No Docker required.

## Point at a checkout

```bash
python3 setup.py --scan /absolute/path/to/checkout --rules ./rules
```

Runs `semgrep scan --config ./rules --metrics=off --json --json-output
<state>/scans/<sha16>/<ts>.json <checkout>`. Semgrep is stateless: there
is no persistent index to inspect or reuse. Every scan re-parses the
target. `--metrics=off` is non-negotiable; `SEMGREP_APP_TOKEN` is
scrubbed from the environment; the harness (and `setup.py`) refuse to
run with it set.

## Reset

```bash
python3 setup.py --clean
```

Uninstalls semgrep and removes only the lab state directory (default
`~/.cache/ai-code-intelligence/semgrep/`). Nothing outside that
directory is touched.

## Prompt harness

Prompts are in [`prompts.md`](prompts.md); the harness in
[`run-prompts.py`](run-prompts.py) runs `baseline` + `semgrep` arms
(where `semgrep` wires the vendor `semgrep mcp` server into Claude Code)
and refuses to write transcripts into this repo or a sibling
`ai-code-intelligence` checkout.

## Do not

- `semgrep login`. Do not set `SEMGREP_APP_TOKEN`. Do not use `--config
  auto` or any `p/...` Registry ruleset. AppSec Platform paths upload
  findings — out of scope per #80, and one fixture is private.
- Commit anything to the fixture repositories.
- Put client-named private code or secrets in this repo, or in `fixtures/`.
- Bump `semgrep` past the pin in `tools.lock.json` without also updating
  `versions.env` and re-running Wave 1 + Wave 5 to check that the
  pinned rules still fire.
- Copy this tree into `ai-code-intelligence`. The main repo carries a
  pointer under `research/semgrep/README.md`; the reproducible bits
  live here.

## What Semgrep is *not*

Semgrep is a taint / SAST tool with a structural pattern engine, not a
code graph. It answers *does user input reach that sink?* well and
*where is this function defined and called?* poorly. When the lab
records a prompt failure, distinguish those two cases in the
`RESULTS.md` write-up — a taint-shape failure is a bug in the rules,
a graph-shape failure is a shape mismatch that the AGENTS snippet
already tells the agent to fall back on Read/Grep for.
