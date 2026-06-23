"""Run pip-audit and npm audit with documented exception allowlist."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
COREUI_ROOT = REPO_ROOT / "CoreModules" / "CoreUI"
EXCEPTIONS_PATH = REPO_ROOT / "Core" / "config" / "dependency_audit_exceptions.json"


def _load_exceptions() -> dict[str, list[dict[str, str]]]:
    data = json.loads(EXCEPTIONS_PATH.read_text(encoding="utf-8"))
    for key in ("pip", "npm"):
        if key not in data:
            raise SystemExit(f"Missing '{key}' section in {EXCEPTIONS_PATH}")
        for entry in data[key]:
            if not entry.get("id") or not entry.get("reason"):
                raise SystemExit(f"Each exception needs id + reason: {entry!r}")
    return data


def _pip_vuln_ids(stdout: str) -> set[str]:
    ids: set[str] = set()
    for line in stdout.splitlines():
        parts = line.split()
        for token in parts:
            if token.startswith(("CVE-", "PYSEC-", "GHSA-")):
                ids.add(token)
    return ids


def _npm_high_ids(stdout: str) -> set[str]:
    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError:
        return _npm_high_ids_from_text(stdout)
    ids: set[str] = set()
    for advisory in (payload.get("vulnerabilities") or {}).values():
        via = advisory.get("via") or []
        for item in via:
            if not isinstance(item, dict):
                continue
            severity = str(item.get("severity") or advisory.get("severity") or "").lower()
            if severity not in {"high", "critical"}:
                continue
            url = item.get("url")
            if url:
                match = re.search(r"(GHSA-[A-Za-z0-9-]+)", str(url))
                if match:
                    ids.add(match.group(1))
    return ids


def _npm_high_ids_from_text(stdout: str) -> set[str]:
    ids: set[str] = set()
    for match in re.finditer(r"https://github.com/advisories/(GHSA-[A-Za-z0-9-]+)", stdout):
        ids.add(match.group(1))
    return ids


def run_pip_audit(allowed: set[str]) -> list[str]:
    result = subprocess.run(
        [sys.executable, "-m", "pip_audit", "--desc", "off"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    combined = (result.stdout or "") + "\n" + (result.stderr or "")
    found = _pip_vuln_ids(combined)
    undocumented = sorted(found - allowed)
    if result.returncode == 0 and not undocumented:
        print("PASS: pip-audit (no undocumented vulnerabilities)")
        return []
    if result.returncode != 0 and not undocumented:
        print("PASS: pip-audit (all findings documented)")
        return []
    print(combined.strip())
    return [f"pip undocumented: {vuln_id}" for vuln_id in undocumented]


def run_npm_audit(allowed: set[str]) -> list[str]:
    npm = "npm.cmd" if sys.platform == "win32" else "npm"
    result = subprocess.run(
        [npm, "audit", "--audit-level=high", "--json"],
        cwd=COREUI_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    combined = (result.stdout or "") + "\n" + (result.stderr or "")
    found = _npm_high_ids(result.stdout or combined)
    undocumented = sorted(found - allowed)
    if result.returncode == 0:
        print("PASS: npm audit (no high/critical vulnerabilities)")
        return []
    if not undocumented:
        print("PASS: npm audit (all high findings documented)")
        return []
    print(combined.strip())
    return [f"npm undocumented: {vuln_id}" for vuln_id in undocumented]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Dependency audit with documented exceptions.")
    parser.add_argument("--pip-only", action="store_true")
    parser.add_argument("--npm-only", action="store_true")
    args = parser.parse_args(argv)

    exceptions = _load_exceptions()
    pip_allowed = {entry["id"] for entry in exceptions["pip"]}
    npm_allowed = {entry["id"] for entry in exceptions["npm"]}

    failures: list[str] = []
    if not args.npm_only:
        failures.extend(run_pip_audit(pip_allowed))
    if not args.pip_only:
        failures.extend(run_npm_audit(npm_allowed))

    if failures:
        print("\nUndocumented dependency vulnerabilities:")
        for item in failures:
            print(f"  - {item}")
        return 1
    print("\nDependency audit passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
