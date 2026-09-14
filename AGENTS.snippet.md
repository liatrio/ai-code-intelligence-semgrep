<!-- Semgrep — drop this block into an AGENTS.md alongside sibling snippets.
     Designed to compose with the CodebaseMemory, GitNexus, and SocratiCode
     snippets rather than replace them. Semgrep answers one class of question
     the others do not (taint), and mishandles the rest — say so out loud. -->

## Semgrep (taint / reachability / pattern SAST)

**When to reach for Semgrep**, in order of comfort:

1. **Reachability from an untrusted source to a sensitive sink**, when the
   question is *does this input reach that write / query / exec?* not
   *what calls this function?*. Examples: HTTP request body → SQL
   `execute`, environment variable → `os.system`, Slack `message.text` →
   MongoDB `insertOne`. Semgrep's `mode: taint` answers with a real
   intraprocedural dataflow trace, source → propagator → sink, with
   file/line for every hop. **A code-graph tool cannot answer this
   correctly**, only whether the shape is present.
2. **Anti-pattern lint that plain text search cannot express** —
   `pattern-either`, `metavariable-comparison`, `pattern-not` with type
   info. Example: *find every `.exec($X)` where `$X` is derived from
   `req.body` but is not first passed through `validator.escape`*.
3. **One-off audit** where a targeted rule beats a full re-index.
   Semgrep is stateless: fresh parse on every scan, no warm-up cost, no
   graph to invalidate. If the question is *does this new rule flag
   anything in this checkout*, Semgrep answers in the time it takes to
   parse.

**When Semgrep is the wrong shape**, and the honest fallback:

- *Where is `foo` defined and what calls it?* — Semgrep's pattern engine
  can find direct call sites, but it will miss re-exports, framework
  registrations, and dynamic dispatch. Use an LSP (Serena / SCIP) or a
  code-graph tool (CodebaseMemory, GitNexus) for this.
- *End-to-end trace across five files.* — Community Edition taint is
  intraprocedural. It follows dataflow inside a function; it does not
  connect callers across files. If the chain crosses a module, the
  agent has to stitch traces together itself, or reach for a code graph.
- *What breaks if I change this signature?* — Semgrep can pattern-match
  call sites, but it does not know call-arity, generic-parameter, or
  overload semantics. This is a code-graph or LSP question.

**How to call it, safely**:

- The MCP wire is `semgrep mcp` (stdio). Wire it once in the client's
  MCP config; every subsequent scan is a tool call. Do **not**
  `semgrep login` and do not set `SEMGREP_APP_TOKEN` — those enable
  the AppSec Platform, which uploads findings.
- Always pass `--metrics=off`. Semgrep's default is to send anonymous
  telemetry to `metrics.semgrep.dev`; setting `SEMGREP_SEND_METRICS=off`
  in the environment or `--metrics=off` on the command line silences it.
- Pin the ruleset. Registry rules (`p/...`, `auto`) fetch from
  Semgrep's server at scan time; a local YAML directory is
  reproducible offline.
- For reachability questions, ask Semgrep to `--json --json-output
  findings.json` and read the `dataflow_trace` block in each finding —
  that is the source→sink chain you want to cite to the user.

**What to do when Semgrep returns nothing**, before assuming absence
is proof of safety:

- If the rule's `pattern-sources` or `pattern-sinks` didn't match your
  actual source or sink shape, Semgrep will silently produce zero
  findings without warning. Sanity-check the shape by writing a
  standalone `pattern:` that must match, running that first, and only
  then wrapping it in `mode: taint`.
- If the source and sink are in different files or the chain crosses a
  function boundary that the Community Edition engine won't follow,
  the finding will be missing even when the vulnerability is real.
  Say so — do not report the empty result as *no path exists*. The
  honest wording is *no intraprocedural path exists; the interprocedural
  path was not analysed*.
- If the target function is invoked indirectly (framework registration,
  method dispatch, decorator), Semgrep's structural patterns will find
  the *registration*, not the *invocation*. That is not the same as a
  caller. Cite the registration and note the indirection layer
  explicitly.
