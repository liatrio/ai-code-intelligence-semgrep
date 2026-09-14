# Results — Semgrep lab

Every wave records exact commands, wall-clock, and outcomes so the run
is reproducible. Section per fixture. Empty section = not yet run.

Populate this file wave by wave. Do not summarise the numbers here into
the research repo until the wave that produced them has landed here
first — the write-up in `research/semgrep/answers.md` cites this file.

## Fixtures in scope

- **[`liatrio/gratibot`](https://github.com/liatrio/gratibot)** — public,
  195 files, plain JavaScript, Node. The `message.text` → MongoDB
  `insertOne` chain (already documented by the CodebaseMemory lab, Wave 6
  Prompt 4) is the frozen oracle for Semgrep's taint mode.
- **[`liatrio-labs/liatrio-knowledge`](https://github.com/liatrio-labs/liatrio-knowledge)**
  — private, TypeScript-heavy Next.js + Mastra agent stack. In scope only
  under local-only rules: pinned CE, pinned local ruleset, `--metrics=off`,
  no `SEMGREP_APP_TOKEN`.

## Wave 1 — smoke on gratibot

Install and single-scan wall-clock. No reindex flow, because Semgrep has
no persistent index — every scan re-parses.

_Pending._

## Wave 2 — yes-cell confirmations on gratibot

Cells expected to confirm as `yes`:

- `traceable_results` — taint trace from `message.text` to
  `recognitionCollection.insertOne` reported with source, sink, and
  intermediate propagators.
- `agents_md_instructions` — `semgrep mcp` advertises structured tools
  usable by an MCP-capable client.
- `install_without_repo_writes` — `python3 setup.py` finishes without
  writing anywhere inside the fixture checkout.
- `commercial_use` — LGPL-2.1-or-later + local rules only, no
  Registry-license bind.

_Pending._

## Wave 3 — no-cell + defaults confirmations

Cells expected to confirm as `no` (or default-leak):

- `no_default_egress` — `lsof -a -c semgrep -iTCP -n -P` during install
  and during a scan; a Registry `--config auto` scan will show egress,
  a pinned local ruleset scan should not.
- `no_source_dependency` — populate `gratibot/node_modules` via
  `npm ci` and re-scan; findings and rule counts should be identical.
- `semantic_cache` — repeat the same scan back-to-back; wall-clock and
  findings match, but no similarity cache is claimed or advertised.
- `incremental_reindex` — n/a: no persistent index.
- `index_past_release` — n/a: no persistent index.
- `portable_index` — n/a: no persistent index.
- `vector_store_local` / `local_embeddings` — n/a: no vectors.

_Pending._

## Wave 4 — shared / gateway cells (docs-anchored)

Cells that the local-only scope can *observe on the vendor's public
surface* but cannot exercise end-to-end because AppSec Platform is
out of scope:

- `shared_dev_instance` / `shared_access_auth` / `gateway_compatible` —
  documented on the vendor site; the lab confirms the local MCP server
  is loopback-only.

_Pending._

## Wave 5 — 5-prompt harness on gratibot

`run-prompts.py` runs `baseline` and `semgrep` arms of each prompt in
`prompts.md`. Pass conditions are frozen and are not shown to the model.

_Pending._

## Wave 6 — 5-prompt harness on liatrio-knowledge

_Pending._
