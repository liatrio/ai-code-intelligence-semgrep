#!/usr/bin/env python3
"""
Usage: python3 run-prompts.py INPUT.json OUTPUT_DIRECTORY

INPUT is private, contains no oracle, and has this shape:
  {
    "repo": "/abs/path/to/checkout",
    "semgrepBin": "/abs/path/to/semgrep",          # `which semgrep` on the host
    "rulesDir": "/abs/path/to/rules",              # pinned ruleset
    "projectId": "semgrep-lab-<sha16>",            # informational; there is no persistent index
    "model": "claude-sonnet-5",                    # resolved ID, not "sonnet"
    "cases": [
      { "id": 1, "function": "…" },
      { "id": 2, "action": "…" },
      { "id": 3, "signatureChange": "…" },
      { "id": 4, "inputSinkPair": { "source": "…", "sink": "…" } },
      { "id": 5, "indirectTarget": "…" }
    ]
  }

Raw prompts and transcripts stay in OUTPUT_DIRECTORY, outside this repository
and outside the research repository. This harness mirrors the CodebaseMemory
harness shape so a delta between the two tools is attributable to the tool,
not to a harness policy difference.

Two arms per case: `baseline` (no MCP server) and `semgrep` (the vendor
`semgrep mcp` server wired in). Same tool policy, same effort, same budget,
same model, same prompt. `SEMGREP_SEND_METRICS=off` and any
`SEMGREP_APP_TOKEN` is scrubbed from the subprocess environment so no
scan uploads findings.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent


def physical_path(location: Path) -> Path:
    """Resolve symlinks; return the deepest realpath prefix that exists,
    then re-append any not-yet-existing suffix. Prevents a symlinked output
    directory from bypassing the 'outside this repo' guard."""
    suffix: list[str] = []
    cursor = Path(location).resolve()
    while not cursor.exists():
        suffix.insert(0, cursor.name)
        cursor = cursor.parent
    real = cursor.resolve()
    return real.joinpath(*suffix)


def load_template(protocol: str, case_id: int) -> str:
    """Read the case-N section out of prompts.md — the paragraph between
    '## N. ' and '\nPass:' — so pass conditions never reach the model."""
    marker = f"## {case_id}. "
    if marker not in protocol:
        raise SystemExit(f"No template for case {case_id}")
    section = protocol.split(marker, 1)[1].split("\n## ", 1)[0]
    body = section.split("\n", 1)[1] if "\n" in section else section
    return body.split("\nPass:", 1)[0].strip()


def render_case(template: str, item: dict[str, Any], repo: str) -> str:
    pair = item.get("inputSinkPair") or {}
    replacements = {
        "`REPO`": repo,
        "`FUNCTION`": item.get("function", ""),
        "`ACTION`": item.get("action", ""),
        "`SIGNATURE_CHANGE`": item.get("signatureChange", ""),
        "`INPUT_SINK_PAIR`": f"source={pair.get('source', '')}, sink={pair.get('sink', '')}",
        "`INPUT_SINK_PAIR.source`": pair.get("source", ""),
        "`INPUT_SINK_PAIR.sink`": pair.get("sink", ""),
        "`INDIRECT_TARGET`": item.get("indirectTarget", ""),
    }
    out = template
    for placeholder, value in replacements.items():
        out = out.replace(placeholder, value)
    return out


def claude_args(model: str, mcp_servers: dict[str, Any]) -> list[str]:
    """Both arms share the same tool policy; the only difference is the MCP
    server wired in for the Semgrep arm."""
    mcp = json.dumps({"mcpServers": mcp_servers})
    return [
        "-p",
        "--permission-mode", "bypassPermissions",
        "--strict-mcp-config",
        "--mcp-config", mcp,
        "--model", model,
        "--effort", "medium",
        "--tools", "Read,Grep,Glob,Bash",
        "--allowedTools", "Read,Grep,Glob,Bash",
        "--output-format", "stream-json",
        "--verbose",
        "--max-budget-usd", "3",
        "--no-session-persistence",
    ]


def main() -> int:
    if len(sys.argv) != 3:
        raise SystemExit("Usage: python3 run-prompts.py INPUT.json OUTPUT_DIRECTORY")

    input_file = Path(sys.argv[1])
    output_directory = Path(sys.argv[2])

    input_data = json.loads(input_file.read_text())
    out = physical_path(output_directory)
    repo_root = REPO_ROOT.resolve()
    if out == repo_root or str(out).startswith(str(repo_root) + os.sep):
        raise SystemExit("Keep transcripts outside this PoC repository")
    sibling_research = (repo_root.parent / "ai-code-intelligence").resolve() if (repo_root.parent / "ai-code-intelligence").exists() else None
    if sibling_research is not None:
        if out == sibling_research or str(out).startswith(str(sibling_research) + os.sep):
            raise SystemExit("Keep transcripts outside the research repository")

    cases = input_data.get("cases", [])
    if not isinstance(cases, list) or len(cases) != 5:
        raise SystemExit("Supply cases 1–5 exactly once")
    ids = {c.get("id") for c in cases}
    if ids != {1, 2, 3, 4, 5}:
        raise SystemExit("Case ids must be exactly 1..5")
    if any("oracle" in c for c in cases):
        raise SystemExit("Cases must not carry oracle answers")
    for required in ("model", "semgrepBin", "repo", "rulesDir"):
        if not input_data.get(required):
            raise SystemExit(f"Input must set {required}")
    if not Path(input_data["semgrepBin"]).exists():
        raise SystemExit(f"Semgrep binary not found: {input_data['semgrepBin']}")
    if not Path(input_data["repo"]).exists():
        raise SystemExit(f"Repository not found: {input_data['repo']}")
    if not Path(input_data["rulesDir"]).exists():
        raise SystemExit(f"Rules directory not found: {input_data['rulesDir']}")

    # Hard refusal — AppSec Platform is out of scope per issue #80.
    if os.environ.get("SEMGREP_APP_TOKEN"):
        raise SystemExit("Unset SEMGREP_APP_TOKEN before running the harness (AppSec Platform is out of scope per issue #80)")

    out.mkdir(parents=True, exist_ok=True)

    protocol = (REPO_ROOT / "prompts.md").read_text()
    snippet = (REPO_ROOT / "AGENTS.snippet.md").read_text()
    version_result = subprocess.run(["claude", "--version"], capture_output=True, text=True, check=False)
    if version_result.returncode != 0:
        raise SystemExit("Claude Code is unavailable")

    manifest_path = out / "manifest.json"
    if manifest_path.exists():
        raise SystemExit(f"Refusing to overwrite existing manifest at {manifest_path}")
    manifest = {
        "harness": version_result.stdout.strip(),
        "model": input_data["model"],
        "protocolSha256": hashlib.sha256(protocol.encode()).hexdigest(),
        "snippetSha256": hashlib.sha256(snippet.encode()).hexdigest(),
        "input": input_data,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2))

    templates = {i: load_template(protocol, i) for i in (1, 2, 3, 4, 5)}

    # Semgrep MCP server env: force metrics off and scrub any AppSec Platform
    # token from the subprocess environment. No `SEMGREP_LAB_STATE` because
    # Semgrep has no persistent per-repo index.
    semgrep_env: dict[str, str] = {
        "SEMGREP_SEND_METRICS": "off",
    }

    semgrep_mcp_server: dict[str, Any] = {
        "command": input_data["semgrepBin"],
        "args": ["mcp"],
        "env": semgrep_env,
    }

    any_failure = False
    for item in cases:
        template = templates[item["id"]]
        question = render_case(template, item, input_data["repo"])

        for variant in ("baseline", "semgrep"):
            prefix = out / f"{item['id']}-{variant}"

            controls = (
                f"This is a read-only navigation evaluation. Repository: {input_data['repo']}. "
                "Use only local source/dependency files and textual search"
                + (" plus the Semgrep MCP tools listed below." if variant == "semgrep" else ".")
                + " Do not edit files, use the network, invoke another agent, read other "
                "evaluation artifacts, or use language services or additional indexers. "
                "Do not read AGENTS.md, CLAUDE.md, skills, or project instructions from "
                "the fixture. The declared coverage is this repository's working tree; "
                "dependency directories are not reference sites for this evaluation. "
                "Return one final answer, including file/line lists when requested. "
                "Distinguish code sites from strings and comments. Do not read any oracle, "
                "case manifest, other transcript, or files outside the checkout except "
                "the Semgrep tool outputs explicitly supplied."
            )

            if variant == "semgrep":
                access = (
                    "You may additionally reach the local Semgrep MCP server through the "
                    "tools Claude Code exposes for it (semgrep_scan, semgrep_scan_with_custom_rule, "
                    "get_supported_languages, get_abstract_syntax_tree, security_check, "
                    "semgrep_rule_schema, and any other tools the server advertises). The "
                    "Semgrep engine is Community Edition; taint mode is intraprocedural. "
                    "A pinned local ruleset for this evaluation lives at:\n"
                    f"SEMGREP_RULES_DIR={input_data['rulesDir']}\n"
                    f"SEMGREP_REPO={input_data['repo']}\n"
                    "Do not run any Semgrep command with `--config auto` or without a "
                    "`--config <path>` argument, and do not `semgrep login`.\n"
                    f"{snippet}"
                )
            else:
                access = (
                    "You have no Semgrep access. Do not launch its binary or MCP server, "
                    "and do not read any `.semgrep/` directory or `semgrep-metrics.log` file."
                )

            prompt = f"{controls}\n\n{access}\n\nTask:\n{question}"
            prompt_path = Path(str(prefix) + ".prompt.txt")
            if prompt_path.exists():
                raise SystemExit(f"Refusing to overwrite existing prompt file at {prompt_path}")
            prompt_path.write_text(prompt)

            mcp_servers = {"semgrep": semgrep_mcp_server} if variant == "semgrep" else {}
            args = ["claude", *claude_args(input_data["model"], mcp_servers)]

            child_env = dict(os.environ)
            child_env["CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC"] = "1"
            # Scrub AppSec Platform state on every launch.
            child_env.pop("SEMGREP_APP_TOKEN", None)
            child_env["SEMGREP_SEND_METRICS"] = "off"
            if variant == "semgrep":
                child_env["SEMGREP_BIN"] = input_data["semgrepBin"]
                child_env["SEMGREP_REPO"] = input_data["repo"]
                child_env["SEMGREP_RULES_DIR"] = input_data["rulesDir"]

            started = time.time()
            jsonl_path = Path(str(prefix) + ".jsonl")
            stderr_path = Path(str(prefix) + ".stderr")
            if jsonl_path.exists() or stderr_path.exists():
                raise SystemExit(f"Refusing to overwrite existing transcripts at {jsonl_path}/{stderr_path}")

            with jsonl_path.open("w") as stdout_f, stderr_path.open("w") as stderr_f:
                try:
                    completed = subprocess.run(
                        args,
                        input=prompt,
                        stdout=stdout_f,
                        stderr=stderr_f,
                        text=True,
                        cwd=input_data["repo"],
                        env=child_env,
                        timeout=600,
                        check=False,
                    )
                    result: dict[str, Any] = {"code": completed.returncode, "timedOut": False}
                except subprocess.TimeoutExpired:
                    result = {"code": None, "timedOut": True}
                except OSError as error:
                    result = {"error": str(error)}

            terminal: dict[str, Any] | None = None
            try:
                for line in jsonl_path.read_text().splitlines():
                    try:
                        event = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if event.get("type") == "result":
                        terminal = event
            except OSError:
                pass

            ok = (
                result.get("code") == 0
                and not result.get("timedOut")
                and "error" not in result
                and (terminal or {}).get("subtype") == "success"
                and not (terminal or {}).get("is_error", False)
            )
            record: dict[str, Any] = {
                "id": item["id"],
                "variant": variant,
                "seconds": time.time() - started,
                "command": args,
                **result,
                "ok": ok,
                "outcome": (terminal or {}).get("subtype", "no-result"),
            }
            if not ok:
                any_failure = True
            Path(str(prefix) + ".run.json").write_text(json.dumps(record, indent=2))
            print(json.dumps(record))

    return 1 if any_failure else 0


if __name__ == "__main__":
    sys.exit(main())
