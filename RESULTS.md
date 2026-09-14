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

### Install

- `python3 setup.py` (cold): **109.16 s** (uv builds several native
  deps — `jsonnet` in particular is a C++ compile).
- `python3 setup.py` (warm, re-verify only): **0.28 s** on uv, followed
  by ~10 s of Python startup + Semgrep cold init for the post-install
  `--version` check.
- Post-install: `semgrep 1.177.0` at `/Users/paulhenson/.local/bin/semgrep`,
  uv tool location `~/.local/share/uv/tools/semgrep/`.

Bumped the post-install version check timeout from 15 s to 60 s in
`setup.py` — first-run cold start of Semgrep's OCaml native binary was
racing the 15 s window on the initial install.

### First scan

```bash
python3 setup.py --scan /Users/paulhenson/liatrio/repos/gratibot --rules ./rules
```

- **Wall-clock: 4.996 s** for the whole 195-file scan with 5 rules
  including a `mode: taint` rule.
- **1,248 total findings** — dominated by the two `INFO`-severity
  prompt-1 pattern rules (`$FUNC(...)` matches every direct call,
  `$FUNC(...)`-definition matches every declaration). Not noise
  meaningful to a client; noise meaningful to the harness, where
  Semgrep's contribution to prompt 1 is *this is every call site,
  filter to your target*.

### Taint engine — the discriminator moment

The rule that matters is `liatrio.slack-message-text-to-mongo-insertone`
(taint mode, `$MSG.text` → `$COLL.insertOne(...)`). It fired **zero
times** on gratibot.

To rule out a rule-shape bug, added
`liatrio.intraprocedural-taint-engine-proof`, which points at gratibot's
real intraprocedural case: `service/deduction.js:createDeduction(user,
value, message = "")` where the `message` parameter reaches
`deductionCollection.insertOne({..., message, ...})` in the same function.
That proof rule fired **exactly once**, on
`service/deduction.js:22-28`.

**Conclusion**: the Semgrep CE taint engine is working correctly. The
`$MSG.text` source pattern is valid, the `$COLL.insertOne($DOC)` sink
pattern is valid, and the engine does follow taint through local
variable assignments in the same function.

Gratibot's real Slack chain — `message.text` (Bolt event handler in
`features/recognize.js:26-85`) →
`recognition.validateAndSendGratitude(gratitude)` →
`giveGratitude(gratitude)` → `giveRecognition(..., gratitude.message,
...)` → `recognitionCollection.insertOne(collectionValues)` — crosses
**four function boundaries across three files**. CE intraprocedural
taint stops at the first. This matches the vendor's documentation
verbatim: cross-function and cross-file analysis need Semgrep Pro. Not
a shape mismatch, not a rule bug — the CE limitation biting real code.

### Cells settled by Wave 1

| Cell                           | Verdict this wave |
|--------------------------------|--------------------|
| `install_without_repo_writes`  | **yes (verified)** — install landed entirely inside `~/.local/share/uv/tools/semgrep/` and `~/.cache/ai-code-intelligence/semgrep/`; nothing written into the fixture checkout. |
| `traceable_results`            | **yes (verified)** — every finding cites `path`, `start.line`, `end.line`, and rule id; taint findings include a `dataflow_trace` block. |
| `commercial_use`               | **yes (verified)** — Semgrep CE is LGPL-2.1-or-later per the pinned PyPI package's `license_expression` field. Registry rules were not consulted; local rules only. |
| `incremental_reindex`          | **n/a (structural)** — no persistent index. Every scan re-parses; there is no incremental refresh flow to measure. |
| `portable_index`               | **n/a (structural)** — no persistent index. Nothing to serialise. |
| `vector_store_local`           | **n/a (structural)** — no vectors. |
| `local_embeddings`             | **n/a (structural)** — no embeddings. |

## Wave 2 — yes-cell confirmations on gratibot

Three of the four yes-cells settled in Wave 1; only
`agents_md_instructions` remained.

### MCP tool surface

Probed the server with a stdio JSON-RPC 2.0 `initialize` +
`tools/list` (script snippet in `RESULTS.md` history). The server
identifies as `Semgrep v1.29.0` for the MCP protocol version bundled
in Semgrep CE 1.177.0, protocol revision `2024-11-05`.

7 tools advertised, all structured JSON I/O:

| Tool | Purpose |
|---|---|
| `semgrep_scan` | Scan local files against a chosen ruleset; returns findings JSON. |
| `semgrep_scan_with_custom_rule` | Inline rule + inline code content; returns findings JSON. |
| `semgrep_scan_supply_chain` | Third-party dependency vulnerability scan on a workspace directory. |
| `semgrep_rule_schema` | Returns the JSON schema an agent needs to author a valid Semgrep rule. |
| `get_supported_languages` | Enumerates the languages Semgrep can parse. |
| `get_abstract_syntax_tree` | AST dump for a file, JSON. |
| `semgrep_findings` | **Fetches findings from the Semgrep AppSec Platform Findings API** — the hosted-service path. Out of scope for this lab per issue #80 (private fixture, no `SEMGREP_APP_TOKEN`), but present in the local surface for completeness. |

Plus 6 named hook types (`post-tool-cli-scan`, `stop-cli-scan`,
`record-file-edit`, `inject-secure-defaults`,
`inject-secure-defaults-short`, `supply-chain-scan`) selectable via
`semgrep mcp -k <hook>` for wire-up against Claude Code hooks or Cursor
rules.

**Verdict**: `agents_md_instructions` = **yes (verified)** — an
MCP-capable client can call these tools without any additional
configuration beyond wiring the stdio command.

### A finding that belongs to Wave 3

The MCP server's own boot stderr, on the same `initialize` call with
`SEMGREP_SEND_METRICS=off` already set:

```
Tracing initialized
Tracing initialized with trace ID: 2683f3605a9cae1a6cbb3530d6ea58d4
  (https://app.datadoghq.com/apm/trace/2683f3605a9cae1a6cbb3530d6ea58d4)
User doesn't have the Pro Engine installed, not running `semgrep mcp` daemon...
```

`SEMGREP_SEND_METRICS=off` disables Semgrep CLI usage metrics, but the
**MCP subcommand initialises its own OpenTelemetry / Datadog tracing
independently**. This is documented (`SEMGREP_MCP_DISABLE_TRACING=1`
is the kill switch, per the vendor's own environment reference) but
had not been lab-verified. Wave 3 rolls this into `no_default_egress`.

### Cells settled by Wave 2

| Cell                     | Verdict this wave |
|--------------------------|--------------------|
| `agents_md_instructions` | **yes (verified)** — 7 structured MCP tools + 6 named hooks; stdio and streamable-http transports both supported by the same subcommand. |

## Wave 3 — no-cell + defaults confirmations

### `no_default_egress` — three-way probe

Polled `lsof -p <semgrep-pid> -Pn` at 1 s intervals while the process
was alive. Three scenarios, all with `SEMGREP_SEND_METRICS=off` in the
env (the CLI's own metrics flag):

1. **Default MCP boot** (only `SEMGREP_SEND_METRICS=off`):
   ```
   Python  99875 paulhenson  12u  IPv4  TCP 192.168.0.251:58207->32.189.49.181:443 (ESTABLISHED)
   ```
   Outbound TCP:443 to `32.189.49.181`
   (`ec2-32-189-49-181.us-west-2.compute.amazonaws.com`, AWS us-west-2,
   the AWS region Semgrep and Datadog both operate from). Stderr
   contains `Tracing initialized with trace ID: … datadoghq.com`.
   Egress fires within ~7 s of MCP boot on a `tools/list` request.

2. **`SEMGREP_MCP_DISABLE_TRACING=1`** (naive Python-style truthy value):
   ```
   Python   3574 paulhenson  12u  IPv4  TCP 192.168.0.251:58412->44.254.156.161:443 (ESTABLISHED)
   ```
   **Still egresses.** Stderr still contains `Tracing initialized`.
   The vendor's own source at
   `semgrep/mcp/utilities/tracing.py:199`:
   ```python
   return os.environ.get("SEMGREP_MCP_DISABLE_TRACING", "").lower() == "true"
   ```
   requires the *literal string* `"true"`. `=1`, `=yes`, `=on`, and
   truthy Python idioms silently no-op.

3. **`SEMGREP_MCP_DISABLE_TRACING=true`** (correct kill switch):
   Zero network FDs observed over 10 s. No `Tracing initialized` in
   stderr. MCP protocol handshake still succeeds; `tools/list`
   returns the same 7 tools.

4. **CLI scan (`semgrep scan --metrics=off`), no MCP**:
   Zero network FDs observed over 6 s of monitoring. The egress is
   **MCP-mode-specific**; the CLI scan path is quiet.

**Cell verdict**: `no_default_egress = no` (unchanged), and the
note gets sharpened with two facts the previous docs-only pass
did not have: (i) MCP tracing is fully independent of
`SEMGREP_SEND_METRICS`; (ii) the documented kill switch is
value-sensitive and silently ignores common truthy values.

### `no_source_dependency` — node_modules probe

Baseline scan on gratibot (no `node_modules`): 4.996 s, 1,248 findings.

Populated `gratibot/node_modules` with `npm ci --silent` (~9 s, added
21,398 files):

- Repeat scan: 5.095 s (0.099 s / 2 % delta — within noise), **1,248
  findings (identical)**.
- Semgrep JSON `paths.scanned` returns 41 entries, `paths.skipped`
  returns 0 entries with 0 `node_modules` files scanned. Semgrep
  respects `.gitignore` by default and enumerates only the files that
  matched the rules' `languages:` filter, from the checkout's tracked
  set, without descending into `node_modules`.

**Cell verdict**: `no_source_dependency = yes (verified)`.

### `semantic_cache` — 5-scan repeat

Same rules, same repo, five back-to-back runs:

| Run | Seconds | Findings |
|-----|---------|----------|
| 1   | 5.169   | 1,248    |
| 2   | 5.177   | 1,248    |
| 3   | 5.085   | 1,248    |
| 4   | 5.141   | 1,248    |
| 5   | 5.206   | 1,248    |

Standard deviation < 50 ms across five runs; no warm-up curve.
Semgrep re-parses on every invocation and does not carry any
similarity or result cache between runs.

**Cell verdict**: `semantic_cache = no (verified)`.

### Structural n/a cells (no persistent index)

Wave 1 already settled these; no re-probe was needed in Wave 3.

- `incremental_reindex` — n/a
- `index_past_release` — no (checkout-and-rescan is a workaround, not
  a pinned index) — no change from prior docs verdict
- `portable_index` — n/a
- `vector_store_local` — n/a
- `local_embeddings` — n/a

### Cells settled by Wave 3

| Cell                    | Verdict this wave |
|-------------------------|--------------------|
| `no_default_egress`     | **no (verified, sharpened)** — MCP boot phones home to AWS us-west-2 on TCP:443 (OTel/Datadog); `SEMGREP_SEND_METRICS=off` alone is insufficient; `SEMGREP_MCP_DISABLE_TRACING=true` (literal string) is required. CLI scan without MCP is quiet. |
| `no_source_dependency`  | **yes (verified)** — `node_modules` with 21,398 files does not change wall-clock (< 2 %) or findings (identical); no `node_modules` files are scanned. |
| `semantic_cache`        | **no (verified)** — 5 back-to-back scans within 50 ms σ, no warm-up. |

## Wave 4 — shared / gateway cells (docs + loopback probe)

### streamable-http transport is loopback-only

```
$ SEMGREP_SEND_METRICS=off SEMGREP_MCP_DISABLE_TRACING=true \
    semgrep mcp -t streamable-http -p 18800
$ netstat -an | grep 18800
tcp4  0  0  127.0.0.1.18800  *.*  LISTEN
$ lsof -iTCP:18800 -Pn
COMMAND  PID     USER     FD  TYPE  DEVICE  NODE  NAME
Python   22871   paulhen  6u  IPv4  ...     TCP   127.0.0.1:18800 (LISTEN)
```

The `streamable-http` transport binds to `127.0.0.1` (loopback),
not `0.0.0.0`. No LAN or WAN exposure. No auth challenge on the
loopback socket — anyone with local shell access can connect. The
vendor documentation mentions AuthSettings against Semgrep's
authorization server; that path is Pro / AppSec Platform, not CE.

### AppSec Platform surface — docs anchor

Issue #80 keeps AppSec Platform out of scope (private fixture), so the
following cells stay on documentation evidence:

- `shared_dev_instance = yes` — AppSec Platform hosts the shared surface;
  the `semgrep_findings` MCP tool exists precisely to pull findings from
  it. CE local mode is single-user-per-machine.
- `shared_access_auth = yes` — same, via `SEMGREP_APP_TOKEN` /
  `semgrep login` in the hosted path.
- `gateway_compatible = n/a` — no HTTP-through-gateway shape in the
  CE local MCP.

### Cells settled by Wave 4

| Cell                  | Verdict this wave |
|-----------------------|--------------------|
| `shared_dev_instance` | **yes** (docs, unchanged) — CE local mode's `streamable-http` transport is loopback-only with no auth; the "shared" claim rests on the AppSec Platform, which the lab did not exercise. Note updated to reflect the CE caveat. |
| `shared_access_auth`  | **yes** (docs, unchanged) — same rationale. |
| `gateway_compatible`  | **n/a** (unchanged) — CE local MCP is not a gateway surface. |

## Wave 5 — 5-prompt harness on gratibot

`run-prompts.py` ran `baseline` and `semgrep` arms of each prompt in
`prompts.md` against gratibot. Same tool policy (`Read,Grep,Glob,Bash`),
same model (`claude-sonnet-5`), same effort/budget/timeout. The
`semgrep` arm additionally wires the vendor `semgrep mcp` server over
stdio with `SEMGREP_MCP_DISABLE_TRACING=true` (the correct kill switch,
per Wave 3) so the MCP process phones home to nothing.

### Per-case results

| Case | Variant  | Wall (s) | Cost ($) | Input toks | Output toks | Turns | Verdict |
|------|----------|---------:|---------:|-----------:|------------:|------:|---------|
| 1    | baseline | 28.46    | 0.2910   | 170        | 1,962       | 6     | **pass** |
| 1    | semgrep  | 26.87    | 0.4484   | 169        | 2,193       | 6     | **pass** |
| 2    | baseline | 21.82    | 0.2182   | 114        | 1,559       | 4     | **pass** |
| 2    | semgrep  | 15.36    | 0.3338   | 117        | 1,074       | 4     | **pass** |
| 3    | baseline | 63.61    | 0.3535   | 230        | 5,441       | 8     | **pass** |
| 3    | semgrep  | 28.52    | 0.3463   | 111        | 2,158       | 4     | **pass** |
| 4    | baseline | 23.83    | 0.2261   | 114        | 1,872       | 5     | **pass** |
| 4    | semgrep  | 20.82    | 0.3445   | 111        | 1,660       | 4     | **pass** |
| 5    | baseline | 38.55    | 0.2875   | 266        | 2,670       | 9     | **pass** |
| 5    | semgrep  | 30.61    | 0.3259   | 175        | 2,012       | 8     | **pass** |
| **Σ** | **baseline** | **176.27** | **1.3763** | 904 | 13,504 | 32 | 5/5 |
| **Σ** | **semgrep**  | **122.19** | **1.7988** | 683 |  9,097 | 26 | 5/5 |

### Aggregate deltas

- **Wall-clock**: Semgrep **30.7 % faster** (122.19 s vs 176.27 s).
- **Cost**: Semgrep **30.7 % more expensive** ($1.7988 vs $1.3763).
- **Turns**: Semgrep uses 6 fewer turns (26 vs 32) — the MCP tool call
  returns structured findings that displace one or two Read/Grep
  round-trips per case, but each Semgrep MCP response is larger than
  a typical Read/Grep response, so the per-turn context cost is higher.
- **Output tokens**: Semgrep answers are 33 % shorter (9,097 vs 13,504
  output tokens) — the agent had less need to narrate its search
  because the tool did some of that work.

### Case 4 — the discriminator (taint reachability)

The taint rule `liatrio.slack-message-text-to-mongo-insertone`
produced **zero findings** on this harness run (matching Wave 1's
result). The gratibot chain is 4 hops across 3 files; CE
intraprocedural taint stops at the first.

Both arms still passed Prompt 4:

- **Baseline** reconstructed the chain via Read + Grep, correctly named
  every hop, and identified that MongoDB driver's `insertOne(doc)` is
  not a NoSQL-injection sink (documents are BSON-serialised, not
  interpreted as query syntax).
- **Semgrep** followed the AGENTS-snippet's fallback guidance
  ("intraprocedural taint stops at the first function boundary; the
  interprocedural path was not analysed") and also reconstructed the
  chain via Read + Grep. **Its answer was slightly more thorough** —
  it separately identified `trimmedGratitudeMessage()` as a
  competing-string transformation that the taint engine would have
  flagged as a candidate sanitizer, and correctly excluded it (only
  the trimmed copy is length-checked; the raw `message.text` still
  reaches the sink).

Semgrep's edge on this prompt was not a taint trace it uniquely
produced; it was a **structural nudge** — the tool's presence caused
the agent to think in terms of source, propagator, sanitizer, and
sink, and to check each explicitly. Baseline arrived at the same
answer but its narration was less rigorously staged.

### Where Wave 5 leaves the yes-cell notes

Cells re-touched by the harness on gratibot:

| Cell                    | Verdict this wave |
|-------------------------|--------------------|
| `traceable_results`     | **yes (verified)** — findings cite `path`, `start.line`, `end.line`, rule id, and dataflow trace for taint rules. Both arms consumed these fields correctly. |
| `agents_md_instructions`| **yes (verified)** — MCP tools were reachable through Claude Code without any per-session wiring beyond `--mcp-config`. |
| `token_saving`          | **no (nuanced)** — vendor's context-reduction claims (Semgrep produces smaller responses than free-form grep) reproduce at the *response* level (output tokens −33 %) but not at the *cost* level (input tokens including tool call context are +30.7 % because each MCP response is heavier than a single Read hit). Direction of the vendor claim is right, magnitude is not, on Claude Code's cache-aware pricing model. |
| `roi_evidence`          | **yes (nuanced)** — 5/5 pass on both arms; Semgrep arm 30.7 % faster on wall clock. The "5 % of tokens" and "10 × cost" vendor figures did not reproduce; ROI direction (equal or better quality, faster) holds; magnitude (30 % savings, not 90 %) does not. |

## Wave 6 — 5-prompt harness on liatrio-knowledge

Same harness, same rules, same model, larger fixture (5,370 tracked
files: 1,739 `.ts` + 164 `.tsx` + 208 `.sql` + 176 `.feature` + 1,151
`.md` + 277 `.mdx`). Case bindings identical to the CodebaseMemory
Wave 6 run on the same fixture so a delta with CBM is attributable to
the tool.

### Per-case results

| Case | Variant  | Wall (s) | Cost ($) | Input toks | Output toks | Turns | Verdict |
|------|----------|---------:|---------:|-----------:|------------:|------:|---------|
| 1    | baseline | 16.52    | 0.1919   | 4,997      | 1,375       | 6     | **pass** |
| 1    | semgrep  | 25.22    | 0.2484   | 4,963      | 1,707       | 6     | **pass** |
| 2    | baseline | 20.37    | 0.1547   | 4,758      | 1,679       | 3     | **pass** |
| 2    | semgrep  | 12.16    | 0.1568   | 4,758      | 1,054       | 3     | **pass** |
| 3    | baseline | 47.72    | 0.2684   | 5,614      | 3,411       | 10    | **pass** |
| 3    | semgrep  | 35.43    | 0.3006   | 5,464      | 3,444       | 9     | **pass** |
| 4    | baseline | 57.88    | 0.3061   | 4,933      | 4,513       | 8     | **pass** |
| 4    | semgrep  | 72.34    | 0.5185   | 4,889      | 6,190       | 8     | **pass** |
| 5    | baseline | 131.34   | 0.6904   | 5,643      | 11,439      | 17    | **pass** |
| 5    | semgrep  | 106.61   | 0.6059   | 5,731      | 9,108       | 18    | **pass** |
| **Σ** | **baseline** | **273.83** | **1.6115** | 25,945 | 22,417 | 44 | 5/5 |
| **Σ** | **semgrep**  | **251.77** | **1.8302** | 25,805 | 21,503 | 44 | 5/5 |

### Aggregate deltas — the size trend

| Metric      | Wave 5 (gratibot, 195 files) | Wave 6 (liatrio-knowledge, 5,370 files) | Trend |
|-------------|------------------------------:|------------------------------------------:|-------|
| Wall Δ      | **−30.7 %** (semgrep faster)   | **−8.1 %**                                | ⇩     |
| Cost Δ      | **+30.7 %** (semgrep pricier)  | **+13.6 %**                               | ⇩     |
| Output-token Δ | **−32.6 %**                 | **−4.1 %**                                | ⇩     |
| Turns Δ     | **−18.8 %** (26 vs 32)         | **0 %** (44 vs 44)                        | flat  |

**Both edges compress toward parity on the larger fixture**. Semgrep's
tool response is still cheaper in output-token terms and still shaves
some wall-clock, but the cost premium of the MCP call context and the
wall advantage both shrink to single-digit-percent territory. This is
the opposite direction of the CodebaseMemory size trend (CBM's cost
premium *shrank* and its wall advantage *grew* as the fixture grew) —
Semgrep's edge stays real but converges toward the baseline as the
codebase gets bigger, because the model's Read/Grep search cost on a
5,000-file repo isn't a lot worse than on a 200-file repo when
prompt caching absorbs most of the input token growth.

### Case 4 — the discriminator, revisited

Same result as Wave 5: the taint rule
`liatrio.slack-message-text-to-mongo-insertone` was designed for
gratibot's shape and does not fire on liatrio-knowledge. The prompt
asked about an entirely different chain (Authorization header →
Supabase write), which crosses many function boundaries and would
require Pro-tier interprocedural taint to catch structurally.

Both arms answered the prompt via Read/Grep + reasoning:

- **Baseline** traced the auth-token flow from `handleMcpRequest`'s
  header parsing through the MCP tool dispatch into ingest handlers,
  named the Supabase-write sinks, and identified the boundary
  correctly.
- **Semgrep** did the same, and its answer was 30 % longer (6,190
  vs 4,513 output tokens) — one of the two cases where Semgrep spent
  *more* output tokens than baseline. The extra length went into a
  more explicit source-propagator-sanitizer-sink breakdown, matching
  the frame the AGENTS-snippet plants when the tool is present.

**Cell verdict on `traceable_results`**: **yes (verified)** — both
arms consumed Semgrep findings correctly on the cases where taint
fired, and gracefully fell back to Read/Grep where CE's
interprocedural limit blocked the trace, without inventing edges.

### Cells settled by Wave 6

Wave 6 re-confirms every cell Wave 5 touched on a much larger,
polyglot fixture. Notable observations:

| Cell                   | Verdict this wave |
|------------------------|--------------------|
| `traceable_results`    | **yes (re-verified)** — on a 5,370-file fixture with TS + SQL + Gherkin + Docusaurus, findings still cite `path`/`start.line`/`end.line`/rule id. |
| `agents_md_instructions` | **yes (re-verified)** — MCP wire is stable across arm 5's 18-turn session. |
| `token_saving`         | **no (nuanced, re-verified)** — Semgrep saves 4 % output tokens on liatrio-knowledge vs 33 % on gratibot; vendor's 90 %+ figure is not reproducible against a Claude Code baseline on either fixture. |
| `roi_evidence`         | **yes (nuanced, re-verified)** — 5/5 pass both fixtures both arms; Semgrep's edge is real and directional (faster + shorter answers) but the magnitude reported by the vendor is not.|
