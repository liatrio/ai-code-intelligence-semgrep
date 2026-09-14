# Prompts

Five prompts, frozen before any run. Each has a pass condition graded
against oracles derived from source reading + Semgrep taint traces
(where applicable). Pass conditions are **never** shown to the model —
`run-prompts.py` splits each case at the `Pass:` line and only sends
the paragraph above it into the Claude Code session.

Convention: `FUNCTION`, `ACTION`, `SIGNATURE_CHANGE`, `INPUT_SINK_PAIR`,
`INDIRECT_TARGET` are placeholders resolved at run time from the input
JSON. The prompts stay repo-agnostic; the input JSON binds them to
gratibot for Wave 5 and liatrio-knowledge for Wave 6.

Every prompt is graded honestly: Semgrep is expected to lose prompts
1–3 and win prompt 4. Prompt 5 depends on the specific indirection
shape the input names.

---

## 1. Definition and callers of `FUNCTION`

Working in the checkout at `REPO`, find where `FUNCTION` is defined and
list every call site that invokes it — direct calls first, indirect
calls (method dispatch, re-exports, framework registrations) after,
labelled as indirect and with the indirection mechanism named. Cite
file and line for every entry. Do not invent entries and do not omit
real ones.

Pass: definition file and line correct within one line for the closing
brace; every direct caller present with correct file + line; no
invented entry; indirect callers either included with the mechanism
named, or explicitly excluded with a stated reason.

---

## 2. End-to-end trace of `ACTION`

Working in the checkout at `REPO`, trace the code path for `ACTION`
from its entry point to its terminal side effect (a persistence write,
an outbound HTTP call, a file write). Name each hop as
`file.js:startLine-endLine  functionName` and list them in execution
order. Do not skip a layer; do not invent a hop.

Pass: entry point identified correctly; every intervening function on
the real chain named with correct file + line range; terminal side
effect named and matches the actual code (not merely a plausible one);
order is the runtime execution order.

---

## 3. Blast radius of `SIGNATURE_CHANGE`

Working in the checkout at `REPO`, `SIGNATURE_CHANGE` describes a
proposed change to a function signature. Identify every call site that
would break, or need to be updated, if the change lands. For each,
give file + line, direct vs indirect, and the specific reason it
breaks (arity mismatch, type mismatch, default changed, etc.). Include
sites reached indirectly through wrapper functions; label them as
indirect and name the wrapper.

Pass: every direct call site listed with correct file + line; every
indirect site either included with the wrapper named, or explicitly
excluded because the wrapper's own signature is unchanged; no invented
site; the reason attached to each site is technically correct for the
proposed change.

---

## 4. Reachability from `INPUT_SINK_PAIR.source` to `INPUT_SINK_PAIR.sink`

Working in the checkout at `REPO`, `INPUT_SINK_PAIR` names an
untrusted source and a sensitive sink. Determine whether the source
can reach the sink and, if so, name the path — every function on it
with file + line, and every propagator or sanitizer on the way (or
the absence of a sanitizer). If the path does not exist, say so and
name the concrete boundary that blocks it (a hash step, a
parameterised query, a validation gate). Do not claim absence
without naming the boundary.

Pass: (a) path exists → chain is correct end to end, every hop cited,
no invented hop, sanitizer status honestly named; or (b) path does
not exist → the boundary named is real and actually blocks the flow.
An empty answer without a named boundary is a fail.

---

## 5. Callers of `INDIRECT_TARGET` (the discriminator)

Working in the checkout at `REPO`, `INDIRECT_TARGET` names a function
that is invoked indirectly — through a framework registration, a
handler map, a decorator, dynamic dispatch, or a re-export layer.
Find every place it is actually reached at runtime, distinguishing
the *registration* (where the function reference is passed as an
argument) from any real call site (which may not exist as text at
all). Do not conflate the two.

Pass: every registration site listed with file + line and the
indirection mechanism named (`app.event('reaction_added', …, target)`,
`app.on('someEvent', target)`, etc.); every direct-text call site
(if any) listed separately; the answer explicitly distinguishes the
two; grep noise (string literals, log-context tags, generated
artifacts) is filtered out. Zero invented entries.
