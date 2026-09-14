#!/usr/bin/env python3
"""
Reusable installer + scan wrapper for Semgrep Community Edition, pinned to
the version in `versions.env`. Contract per issue #75 / #80: `--check`
reports what is missing without installing anything; `--scan REPO --rules
DIR` runs a Semgrep scan against a sibling checkout with a pinned local
ruleset; `--clean` tears down the lab state directory this script owns.

Design constraints unique to Semgrep, straight from issue #80:

- Community Edition only. This script REFUSES to run if `SEMGREP_APP_TOKEN`
  is set in the environment or if `~/.semgrep/settings.yml` contains an
  `api_token` — those enable AppSec Platform / Pro paths that upload
  findings, and one of the two fixtures (liatrio-knowledge) is private.
- `--metrics=off` on every scan. Semgrep's default is to send anonymous
  usage metrics to metrics.semgrep.dev; the lab doesn't need that noise
  and it would confuse the `no_default_egress` measurement.
- No `semgrep login` call, ever.

Every top-level operation ends with one JSON summary line on stdout so
harnesses and CI can consume it without parsing prose. Non-zero exit code
if anything the script attempted to guarantee failed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent

# --- Configuration knobs -----------------------------------------------------

DEFAULT_STATE_DIR = Path.home() / ".cache" / "ai-code-intelligence" / "semgrep"


def load_versions_env() -> dict[str, str]:
    """Parse versions.env into a plain dict. Nothing exotic — KEY=VALUE only."""
    result: dict[str, str] = {}
    path = REPO_ROOT / "versions.env"
    if not path.exists():
        return result
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        result[key.strip()] = value.strip()
    return result


VERSIONS = load_versions_env()
PINNED_VERSION = VERSIONS.get("SEMGREP_VERSION", "1.177.0")
PYTHON_ENGINES = VERSIONS.get("PYTHON_ENGINES", ">=3.10")


# --- Prerequisite check ------------------------------------------------------


def check_python_version() -> str | None:
    """Return None if Python satisfies PYTHON_ENGINES, else a reason string."""
    major, minor = sys.version_info[:2]
    if (major, minor) < (3, 10):
        return f"Python {major}.{minor}.x is below required {PYTHON_ENGINES}"
    return None


def which(binary: str) -> str | None:
    return shutil.which(binary)


def check_installer_available() -> str | None:
    """uv preferred, pipx acceptable. Return None if one is present."""
    if which("uv"):
        return None
    if which("pipx"):
        return None
    return "neither `uv` nor `pipx` found on PATH; install one with `brew install uv` or `python3 -m pip install --user pipx`"


def check_git_available() -> str | None:
    if which("git"):
        return None
    return "`git` not found on PATH"


def refuse_if_appsec_configured() -> str | None:
    """The one Semgrep-specific hard refusal: never let this lab talk to the
    AppSec Platform. liatrio-knowledge is private and the issue is explicit.
    Return a reason string if the environment looks logged in, else None."""
    if os.environ.get("SEMGREP_APP_TOKEN"):
        return "SEMGREP_APP_TOKEN is set — unset it before running the lab (AppSec Platform is out of scope per issue #80)"
    settings = Path.home() / ".semgrep" / "settings.yml"
    if settings.exists():
        try:
            content = settings.read_text()
            if "api_token" in content:
                return f"{settings} contains `api_token` — run `semgrep logout` before running the lab"
        except Exception:
            pass
    return None


def installed_semgrep_version() -> str | None:
    """Return the installed semgrep version string, or None if not found."""
    binary = which("semgrep")
    if not binary:
        return None
    try:
        r = subprocess.run([binary, "--version"], capture_output=True, text=True, timeout=15)
        return r.stdout.strip() or None
    except Exception:
        return None


def state_dir(state: Path) -> Path:
    return state.resolve()


def do_check(state: Path) -> dict:
    missing: list[str] = []

    reason = check_python_version()
    if reason:
        missing.append(reason)

    reason = check_installer_available()
    if reason:
        missing.append(reason)

    reason = check_git_available()
    if reason:
        missing.append(reason)

    reason = refuse_if_appsec_configured()
    if reason:
        missing.append(reason)

    installed = installed_semgrep_version()
    if installed is None:
        missing.append(f"semgrep {PINNED_VERSION} not installed (run this script with no `--check` flag to install)")
    elif installed != PINNED_VERSION:
        missing.append(f"semgrep is installed but reports version {installed!r}, expected {PINNED_VERSION!r}")

    if not state.exists():
        missing.append(f"lab state dir not present at {state} (created on first install)")

    return {
        "ok": len(missing) == 0,
        "pinned": PINNED_VERSION,
        "python": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        "operation": "check",
        "state": str(state_dir(state)),
        "installed_version": installed,
        "missing": missing,
    }


# --- Install -----------------------------------------------------------------


def do_install(state: Path) -> dict:
    reason = refuse_if_appsec_configured()
    if reason:
        return {"ok": False, "operation": "install", "error": reason, "pinned": PINNED_VERSION}

    reason = check_installer_available()
    if reason:
        return {"ok": False, "operation": "install", "error": reason, "pinned": PINNED_VERSION}

    state.mkdir(parents=True, exist_ok=True)

    installer = "uv" if which("uv") else "pipx"

    started = time.time()
    if installer == "uv":
        cmd = ["uv", "tool", "install", "--force", f"semgrep=={PINNED_VERSION}"]
    else:
        cmd = ["pipx", "install", "--force", f"semgrep=={PINNED_VERSION}"]

    r = subprocess.run(cmd, capture_output=True, text=True)
    elapsed = time.time() - started

    if r.returncode != 0:
        return {
            "ok": False,
            "operation": "install",
            "installer": installer,
            "cmd": cmd,
            "returncode": r.returncode,
            "stderr": r.stderr[-2000:],
            "elapsed_seconds": round(elapsed, 3),
            "pinned": PINNED_VERSION,
        }

    installed = installed_semgrep_version()
    if installed != PINNED_VERSION:
        return {
            "ok": False,
            "operation": "install",
            "installer": installer,
            "error": f"installed reports {installed!r}, expected {PINNED_VERSION!r}",
            "elapsed_seconds": round(elapsed, 3),
            "pinned": PINNED_VERSION,
        }

    # Persist a small state artifact so `--check` can see when the install landed.
    state_file = state / "state.json"
    state_file.write_text(json.dumps({
        "pinned": PINNED_VERSION,
        "installer": installer,
        "installed_at": time.time(),
        "semgrep_binary": which("semgrep"),
    }, indent=2))

    return {
        "ok": True,
        "operation": "install",
        "installer": installer,
        "elapsed_seconds": round(elapsed, 3),
        "installed_version": installed,
        "state": str(state_dir(state)),
        "pinned": PINNED_VERSION,
    }


# --- Scan --------------------------------------------------------------------


def do_scan(state: Path, repo: Path, rules: Path) -> dict:
    reason = refuse_if_appsec_configured()
    if reason:
        return {"ok": False, "operation": "scan", "error": reason, "pinned": PINNED_VERSION}

    if not repo.exists():
        return {"ok": False, "operation": "scan", "error": f"repo not found: {repo}"}
    if not rules.exists():
        return {"ok": False, "operation": "scan", "error": f"rules path not found: {rules}"}

    installed = installed_semgrep_version()
    if installed != PINNED_VERSION:
        return {
            "ok": False,
            "operation": "scan",
            "error": f"semgrep version mismatch: installed {installed!r}, expected {PINNED_VERSION!r}",
        }

    binary = which("semgrep")
    if not binary:
        return {"ok": False, "operation": "scan", "error": "semgrep binary not on PATH"}

    # Deterministic scan invocation. `--metrics=off` is non-negotiable.
    # `--json` streams structured results to stdout; findings are captured
    # to disk under the state dir for reproducibility.
    findings_dir = state / "scans" / hashlib.sha256(str(repo.resolve()).encode()).hexdigest()[:16]
    findings_dir.mkdir(parents=True, exist_ok=True)
    findings_file = findings_dir / f"{int(time.time())}.json"

    cmd = [
        binary, "scan",
        "--config", str(rules.resolve()),
        "--metrics", "off",
        "--json", "--json-output", str(findings_file),
        "--quiet",
        str(repo.resolve()),
    ]

    env = os.environ.copy()
    env["SEMGREP_SEND_METRICS"] = "off"
    env.pop("SEMGREP_APP_TOKEN", None)

    started = time.time()
    r = subprocess.run(cmd, capture_output=True, text=True, env=env)
    elapsed = time.time() - started

    findings = {}
    findings_count = 0
    if findings_file.exists():
        try:
            findings = json.loads(findings_file.read_text())
            findings_count = len(findings.get("results", []))
        except Exception as e:
            findings = {"parse_error": str(e)}

    return {
        "ok": r.returncode in (0, 1),  # 0 = no findings, 1 = findings present (both are healthy scans)
        "operation": "scan",
        "repo": str(repo.resolve()),
        "rules": str(rules.resolve()),
        "cmd": cmd,
        "returncode": r.returncode,
        "seconds": round(elapsed, 3),
        "findings_count": findings_count,
        "findings_file": str(findings_file),
        "stderr_tail": r.stderr[-1000:] if r.stderr else "",
        "pinned": PINNED_VERSION,
    }


# --- Status ------------------------------------------------------------------


def do_status(repo: Path) -> dict:
    """Semgrep has no persistent index. This subcommand exists for parity
    with the sibling PoC repos and returns a structural n/a."""
    return {
        "ok": True,
        "operation": "status",
        "repo": str(repo.resolve()),
        "index": "n/a",
        "note": "Semgrep re-parses on every scan; there is no persistent per-repo index to report on. Use --scan to run a fresh scan.",
        "pinned": PINNED_VERSION,
    }


# --- Clean -------------------------------------------------------------------


def do_clean(state: Path) -> dict:
    installer = "uv" if which("uv") else ("pipx" if which("pipx") else None)
    uninstalled = False
    stderr_tail = ""
    if installer:
        if installer == "uv":
            cmd = ["uv", "tool", "uninstall", "semgrep"]
        else:
            cmd = ["pipx", "uninstall", "semgrep"]
        r = subprocess.run(cmd, capture_output=True, text=True)
        uninstalled = r.returncode == 0
        stderr_tail = (r.stderr or "")[-500:]

    removed_state = False
    if state.exists() and state.resolve() != Path.home().resolve():
        shutil.rmtree(state)
        removed_state = True

    return {
        "ok": True,
        "operation": "clean",
        "uninstalled": uninstalled,
        "removed_state": removed_state,
        "installer": installer,
        "stderr_tail": stderr_tail,
        "pinned": PINNED_VERSION,
    }


# --- CLI ---------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=f"Install pinned semgrep=={PINNED_VERSION} and run scans for the Semgrep lab.",
    )
    parser.add_argument("--check", action="store_true", help="Report what is missing (installs nothing).")
    parser.add_argument("--clean", action="store_true", help="Uninstall semgrep and remove the lab state directory.")
    parser.add_argument("--scan", metavar="REPO", type=Path, help="Run a semgrep scan against REPO with --rules.")
    parser.add_argument("--rules", metavar="DIR", type=Path, default=REPO_ROOT / "rules", help="Ruleset directory (default: ./rules).")
    parser.add_argument("--status", metavar="REPO", type=Path, help="Report scan status for REPO (n/a for Semgrep — no persistent index).")
    parser.add_argument("--state-dir", metavar="STATE", type=Path, default=Path(os.environ.get("SEMGREP_LAB_STATE", str(DEFAULT_STATE_DIR))),
                        help=f"Where the lab state artifact and scan outputs live. Default: {DEFAULT_STATE_DIR}")

    try:
        args = parser.parse_args(argv)
    except SystemExit as e:
        return int(e.code) if e.code is not None else 0

    state = args.state_dir

    if args.check:
        summary = do_check(state)
    elif args.clean:
        summary = do_clean(state)
    elif args.scan is not None:
        summary = do_scan(state, args.scan, args.rules)
    elif args.status is not None:
        summary = do_status(args.status)
    else:
        # Default action: ensure semgrep is installed at PINNED_VERSION.
        summary = do_install(state)

    print(json.dumps(summary))
    return 0 if summary.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
