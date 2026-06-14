"""Dependency inventory and update routes for the CoreUI Dependencies tab."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import threading
import time
import uuid
from datetime import datetime, timezone
from importlib import metadata as importlib_metadata
from pathlib import Path
from typing import Any

from flask import Blueprint, jsonify

from error_manager.http import error_response as _error_response

REPO_ROOT = Path(__file__).resolve().parents[2]
COREUI_ROOT = REPO_ROOT / "CoreModules" / "CoreUI"

_REQ_NAME_RE = re.compile(r"^\s*([A-Za-z0-9_.-]+)(?:\[[^\]]+\])?")
_TOML_STRING_RE = re.compile(r'"([^"]+)"|\'([^\']+)\'')
_SECTION_RE = re.compile(r"^\s*\[([^\]]+)\]\s*$")
_KEY_ARRAY_RE = re.compile(r"^\s*([A-Za-z0-9_.-]+)\s*=\s*\[\s*$")
_DOCKER_IMAGE_RE = re.compile(r"^\s*image\s*:\s*[\"']?([^\"'\s#]+)")

_JOB_LOCK = threading.Lock()
_JOBS: dict[str, dict[str, Any]] = {}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _rel(path: Path) -> str:
    try:
        return path.resolve().relative_to(REPO_ROOT.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def _normalize_name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _extract_requirement_name(requirement: str) -> str | None:
    raw = requirement.strip()
    if not raw or raw.startswith("#"):
        return None
    if raw.startswith(("-e ", "--editable", "-r ", "--requirement")):
        return None
    raw = raw.split(";", 1)[0].strip()
    if " @ " in raw:
        raw = raw.split(" @ ", 1)[0].strip()
    match = _REQ_NAME_RE.match(raw)
    if not match:
        return None
    return match.group(1)


def _python_installed_version(name: str) -> str | None:
    try:
        return importlib_metadata.version(name)
    except importlib_metadata.PackageNotFoundError:
        return None
    except Exception:
        return None


def _add_dependency(
    deps: dict[str, dict[str, Any]],
    *,
    ecosystem: str,
    name: str,
    requested: str,
    source_path: str,
    group: str,
    manager: str,
    installed_version: str | None,
) -> None:
    dep_id = f"{ecosystem}:{_normalize_name(name)}"
    item = deps.get(dep_id)
    source = {"path": source_path, "group": group, "requested": requested}
    if item is None:
        deps[dep_id] = {
            "id": dep_id,
            "ecosystem": ecosystem,
            "name": name,
            "requested": requested,
            "installed_version": installed_version,
            "latest_version": None,
            "status": "installed" if installed_version else "missing",
            "manager": manager,
            "sources": [source],
        }
        return
    item["sources"].append(source)
    groups = {s.get("group") for s in item["sources"]}
    if "runtime" in groups and item.get("requested") != requested:
        item["requested"] = requested
    if not item.get("installed_version") and installed_version:
        item["installed_version"] = installed_version
        item["status"] = "installed"


def _collect_pyproject_dependencies(path: Path, deps: dict[str, dict[str, Any]]) -> None:
    if not path.exists():
        return
    section = ""
    pending_key: str | None = None
    pending_values: list[str] = []

    def flush_array() -> None:
        nonlocal pending_key, pending_values
        if pending_key is None:
            return
        group = "runtime" if section == "project" and pending_key == "dependencies" else pending_key
        for requirement in pending_values:
            name = _extract_requirement_name(requirement)
            if not name:
                continue
            _add_dependency(
                deps,
                ecosystem="python",
                name=name,
                requested=requirement,
                source_path=_rel(path),
                group=group,
                manager="pip",
                installed_version=_python_installed_version(name),
            )
        pending_key = None
        pending_values = []

    for line in _read_text(path).splitlines():
        section_match = _SECTION_RE.match(line)
        if section_match:
            flush_array()
            section = section_match.group(1).strip()
            continue
        if pending_key is not None:
            pending_values.extend(a or b for a, b in _TOML_STRING_RE.findall(line))
            if "]" in line:
                flush_array()
            continue
        key_match = _KEY_ARRAY_RE.match(line)
        if key_match and section in ("project", "project.optional-dependencies"):
            key = key_match.group(1)
            if section == "project" and key != "dependencies":
                continue
            pending_key = key
            pending_values.extend(a or b for a, b in _TOML_STRING_RE.findall(line))
            if "]" in line:
                flush_array()
    flush_array()


def _collect_requirements_dependencies(path: Path, deps: dict[str, dict[str, Any]]) -> None:
    if not path.exists():
        return
    for raw_line in _read_text(path).splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or line.startswith(("-e ", "-r ", "--")):
            continue
        line = line.split(" #", 1)[0].strip()
        name = _extract_requirement_name(line)
        if not name:
            continue
        _add_dependency(
            deps,
            ecosystem="python",
            name=name,
            requested=line,
            source_path=_rel(path),
            group="requirements",
            manager="pip",
            installed_version=_python_installed_version(name),
        )


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _collect_npm_dependencies(deps: dict[str, dict[str, Any]]) -> None:
    package_json = _load_json(COREUI_ROOT / "package.json")
    package_lock = _load_json(COREUI_ROOT / "package-lock.json")
    lock_packages = package_lock.get("packages") if isinstance(package_lock.get("packages"), dict) else {}
    root_lock = lock_packages.get("") if isinstance(lock_packages.get(""), dict) else {}

    installed_by_name: dict[str, str] = {}
    for key, value in lock_packages.items():
        if not key.startswith("node_modules/") or not isinstance(value, dict):
            continue
        name = key.removeprefix("node_modules/")
        version = value.get("version")
        if isinstance(version, str):
            installed_by_name[name] = version

    for group_key, group in (("dependencies", "runtime"), ("devDependencies", "dev")):
        declared = package_json.get(group_key)
        if not isinstance(declared, dict):
            declared = root_lock.get(group_key) if isinstance(root_lock.get(group_key), dict) else {}
        for name, requested in sorted(declared.items()):
            installed_version = installed_by_name.get(name)
            _add_dependency(
                deps,
                ecosystem="npm",
                name=name,
                requested=str(requested),
                source_path=_rel(COREUI_ROOT / "package.json"),
                group=group,
                manager="npm",
                installed_version=installed_version,
            )


def _collect_docker_dependencies(deps: dict[str, dict[str, Any]]) -> None:
    compose = REPO_ROOT / "docker-compose.yml"
    if not compose.exists():
        return
    for line in _read_text(compose).splitlines():
        match = _DOCKER_IMAGE_RE.match(line)
        if not match:
            continue
        image = match.group(1).strip()
        name = image.split(":", 1)[0]
        requested = image.split(":", 1)[1] if ":" in image else "latest"
        _add_dependency(
            deps,
            ecosystem="docker",
            name=name,
            requested=requested,
            source_path=_rel(compose),
            group="infrastructure",
            manager="docker",
            installed_version=None,
        )
        deps[f"docker:{_normalize_name(name)}"]["status"] = "declared"


def _dependency_files() -> list[str]:
    patterns = ("pyproject.toml", "requirements.txt", "requirements-dev.txt", "package.json", "package-lock.json")
    files: list[str] = []
    for pattern in patterns:
        for path in REPO_ROOT.rglob(pattern):
            parts = set(path.parts)
            if {".git", "node_modules", "dist", "tmp"} & parts:
                continue
            files.append(_rel(path))
    compose = REPO_ROOT / "docker-compose.yml"
    if compose.exists():
        files.append(_rel(compose))
    return sorted(set(files))


def build_dependency_inventory() -> dict[str, Any]:
    deps: dict[str, dict[str, Any]] = {}
    for path in sorted(REPO_ROOT.rglob("pyproject.toml")):
        if any(part in {".git", "node_modules", "dist", "tmp"} for part in path.parts):
            continue
        _collect_pyproject_dependencies(path, deps)
    for path in sorted(REPO_ROOT.rglob("requirements*.txt")):
        if any(part in {".git", "node_modules", "dist", "tmp"} for part in path.parts):
            continue
        _collect_requirements_dependencies(path, deps)
    _collect_npm_dependencies(deps)
    _collect_docker_dependencies(deps)

    items = sorted(deps.values(), key=lambda d: (str(d["ecosystem"]), str(d["name"]).lower()))
    counts = {
        "total": len(items),
        "installed": sum(1 for item in items if item.get("status") == "installed"),
        "missing": sum(1 for item in items if item.get("status") == "missing"),
        "declared": sum(1 for item in items if item.get("status") == "declared"),
        "python": sum(1 for item in items if item.get("ecosystem") == "python"),
        "npm": sum(1 for item in items if item.get("ecosystem") == "npm"),
        "docker": sum(1 for item in items if item.get("ecosystem") == "docker"),
    }
    return {
        "dependencies": items,
        "counts": counts,
        "files": _dependency_files(),
        "generated_at": _utc_now(),
        "update_capabilities": [
            {
                "id": "check",
                "label": "Check updates",
                "commands": ["python -m pip list --outdated --format=json", "npm outdated --json"],
            },
            {
                "id": "update_all",
                "label": "Update all",
                "commands": ["python -m pip install --upgrade -r requirements-dev.txt", "npm update"],
            },
        ],
    }


def _command_output_tail(text: str, limit: int = 6000) -> str:
    text = text or ""
    return text[-limit:] if len(text) > limit else text


def _npm_executable() -> str:
    return "npm.cmd" if os.name == "nt" else "npm"


def _classify_pip_line(line: str) -> tuple[str, str] | None:
    """Return (phase, package_name) when the line signals a progress transition.

    pip with ``-v`` / ``-vv`` prints lines like:
    - ``Downloading https://.../foo-1.2.3-...whl (120kB)``
    - ``Downloading foo-1.2.3-...whl (120kB)``
    - ``Downloaded foo-1.2.3-...whl (120kB)``
    - ``Installing collected packages: a, b, c``
    - ``Successfully installed foo-1.2.3 bar-4.5.6``
    - ``Attempting uninstall: foo``
    """
    text = line.strip()
    if not text:
        return None
    lowered = text.lower()
    if lowered.startswith("downloading ") or lowered.startswith("downloaded "):
        prefix_len = len("downloading ") if lowered.startswith("downloading ") else len("downloaded ")
        rest = text[prefix_len:].strip()
        if rest.startswith("http://") or rest.startswith("https://"):
            rest = rest.split("/", 1)[-1]
        name = rest.split("-", 1)[0]
        return (lowered.split(" ", 1)[0], name)
    if lowered.startswith("installing collected packages:"):
        return ("installing", "")
    if lowered.startswith("successfully installed "):
        names = text[len("Successfully installed "):].split()
        return ("done", names[0] if names else "")
    if lowered.startswith("attempting uninstall:"):
        match = re.search(r"attempting uninstall:\s*([A-Za-z0-9_.\-]+)", text, flags=re.IGNORECASE)
        if match:
            return ("uninstalling", match.group(1))
    if lowered.startswith("preparing metadata"):
        return ("preparing", "")
    if lowered.startswith("verifying"):
        return ("verifying", "")
    return None


def _classify_npm_line(line: str) -> tuple[str, str] | None:
    """Return (phase, package_name) for npm output.

    npm ``update --json`` (npm >= 9) emits JSON lines; legacy text output uses
    lines like ``changed 3 packages`` or ``+ pkg@1.2.3`` at the end.
    """
    text = line.strip()
    if not text:
        return None
    try:
        payload = json.loads(text)
    except Exception:
        payload = None
    if isinstance(payload, dict):
        event = str(payload.get("type") or payload.get("name") or "").lower()
        if event in {"idealTree", "reify", "add", "change", "remove"}:
            target = payload.get("package") or payload.get("name")
            return (event, str(target) if target else "")
    if text.startswith("+ ") or text.startswith("- "):
        return ("changed", text[2:].strip())
    if text.lower().startswith("changed "):
        return ("changed", "")
    return None


def _step_update_callback(job_id: str, ecosystem: str):
    """Return a callback that pushes per-line progress into the job state."""

    def _callback(phase: str, package: str, completed: list[dict[str, Any]]) -> None:
        with _JOB_LOCK:
            job = _JOBS.get(job_id)
            if job is None:
                return
            job["current_ecosystem"] = ecosystem
            job["current_phase"] = phase
            job["current_package"] = package or ""
            job["updated_packages"] = completed
            for step in job.get("steps") or []:
                if step.get("phase") in (None, ""):
                    step["phase"] = phase
                if completed:
                    step["completed_packages"] = [c.get("name") for c in completed if c.get("name")]

    return _callback


def _extract_pip_succeeded(output: str) -> list[dict[str, Any]]:
    text = output or ""
    for line in text.splitlines():
        if line.strip().lower().startswith("successfully installed "):
            names = line.strip()[len("Successfully installed "):].split()
            return [{"name": name, "status": "done"} for name in names if name]
    return []


def _run_subprocess(args: list[str], *, cwd: Path, timeout: int, ok_codes: set[int] | None = None) -> dict[str, Any]:
    started = time.monotonic()
    ok_codes = ok_codes or {0}
    label = " ".join(args)
    try:
        completed = subprocess.run(
            args,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        output = (completed.stdout or "") + ("\n" + completed.stderr if completed.stderr else "")
        return {
            "command": label,
            "cwd": _rel(cwd),
            "returncode": completed.returncode,
            "ok": completed.returncode in ok_codes,
            "duration_ms": round((time.monotonic() - started) * 1000, 1),
            "output": _command_output_tail(output.strip()),
            "phase": "done",
            "completed_packages": [],
        }
    except subprocess.TimeoutExpired as exc:
        output = (exc.stdout or "") + ("\n" + exc.stderr if exc.stderr else "")
        return {
            "command": label,
            "cwd": _rel(cwd),
            "returncode": None,
            "ok": False,
            "duration_ms": round((time.monotonic() - started) * 1000, 1),
            "output": _command_output_tail((output or "Command timed out").strip()),
            "phase": "timeout",
            "completed_packages": [],
        }
    except Exception as exc:
        return {
            "command": label,
            "cwd": _rel(cwd),
            "returncode": None,
            "ok": False,
            "duration_ms": round((time.monotonic() - started) * 1000, 1),
            "output": str(exc),
            "phase": "spawn-failed",
            "completed_packages": [],
        }


def _parse_update_results(steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    updates: list[dict[str, Any]] = []
    for step in steps:
        command = str(step.get("command") or "")
        output = str(step.get("output") or "").strip()
        if not output:
            continue
        if "pip list --outdated" in command:
            try:
                rows = json.loads(output)
            except Exception:
                rows = []
            if isinstance(rows, list):
                for row in rows:
                    if not isinstance(row, dict):
                        continue
                    updates.append(
                        {
                            "ecosystem": "python",
                            "name": row.get("name"),
                            "current": row.get("version"),
                            "latest": row.get("latest_version"),
                        }
                    )
        elif "npm outdated" in command:
            try:
                rows = json.loads(output)
            except Exception:
                rows = {}
            if isinstance(rows, dict):
                for name, row in rows.items():
                    if not isinstance(row, dict):
                        continue
                    updates.append(
                        {
                            "ecosystem": "npm",
                            "name": name,
                            "current": row.get("current"),
                            "wanted": row.get("wanted"),
                            "latest": row.get("latest"),
                        }
                    )
    return [u for u in updates if u.get("name")]


def _set_job(job_id: str, **updates: Any) -> dict[str, Any] | None:
    with _JOB_LOCK:
        job = _JOBS.get(job_id)
        if job is None:
            return None
        job.update(updates)
        return dict(job)


def _stream_pip_updates(
    args: list[str],
    *,
    cwd: Path,
    timeout: int,
    job_id: str,
    completed: list[dict[str, Any]],
) -> dict[str, Any]:
    """Run pip with line-level progress; mutates ``completed`` in place."""
    started = time.monotonic()
    label = " ".join(args)
    output_lines: list[str] = []
    current_phase = "starting"
    current_pkg = ""
    on_progress = _step_update_callback(job_id, "python")
    try:
        process = subprocess.Popen(
            args,
            cwd=str(cwd),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
    except Exception as exc:
        return {
            "command": label,
            "cwd": _rel(cwd),
            "returncode": None,
            "ok": False,
            "duration_ms": round((time.monotonic() - started) * 1000, 1),
            "output": str(exc),
            "phase": "spawn-failed",
            "completed_packages": [c.get("name") for c in completed],
        }
    assert process.stdout is not None
    try:
        for raw_line in process.stdout:
            line = raw_line.rstrip()
            output_lines.append(line)
            event = _classify_pip_line(line)
            if event is not None:
                phase, pkg = event
                current_phase = phase
                if pkg:
                    current_pkg = pkg
                on_progress(phase, current_pkg, list(completed))
            if time.monotonic() - started > timeout:
                process.kill()
                break
        try:
            returncode = process.wait(timeout=max(1, int(timeout) - int(time.monotonic() - started)))
        except subprocess.TimeoutExpired:
            process.kill()
            returncode = None
    except Exception as exc:
        return {
            "command": label,
            "cwd": _rel(cwd),
            "returncode": None,
            "ok": False,
            "duration_ms": round((time.monotonic() - started) * 1000, 1),
            "output": str(exc),
            "phase": current_phase,
            "completed_packages": [c.get("name") for c in completed],
        }
    output = "\n".join(output_lines)
    succeeded = [c for c in completed if c.get("status") == "done"]
    new_done = _extract_pip_succeeded(output)
    for entry in new_done:
        if not any(c.get("name") == entry["name"] for c in succeeded):
            succeeded.append(entry)
            completed.append(entry)
    ok = returncode == 0
    return {
        "command": label,
        "cwd": _rel(cwd),
        "returncode": returncode,
        "ok": ok,
        "duration_ms": round((time.monotonic() - started) * 1000, 1),
        "output": _command_output_tail(output.strip()),
        "phase": current_phase,
        "completed_packages": [c.get("name") for c in succeeded if c.get("name")],
    }


def _stream_npm_updates(
    args: list[str],
    *,
    cwd: Path,
    timeout: int,
    job_id: str,
    completed: list[dict[str, Any]],
) -> dict[str, Any]:
    """Run ``npm update`` with progress; mutates ``completed`` in place."""
    started = time.monotonic()
    label = " ".join(args)
    output_lines: list[str] = []
    current_phase = "starting"
    current_pkg = ""
    on_progress = _step_update_callback(job_id, "npm")
    try:
        process = subprocess.Popen(
            args,
            cwd=str(cwd),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
    except Exception as exc:
        return {
            "command": label,
            "cwd": _rel(cwd),
            "returncode": None,
            "ok": False,
            "duration_ms": round((time.monotonic() - started) * 1000, 1),
            "output": str(exc),
            "phase": "spawn-failed",
            "completed_packages": [c.get("name") for c in completed],
        }
    assert process.stdout is not None
    seen: set[str] = set()
    try:
        for raw_line in process.stdout:
            line = raw_line.rstrip()
            output_lines.append(line)
            event = _classify_npm_line(line)
            if event is not None:
                phase, pkg = event
                current_phase = phase or current_phase
                if pkg and not pkg.startswith("pkg@"):
                    entry_name = pkg.split("@", 1)[0]
                    if entry_name and entry_name not in seen:
                        seen.add(entry_name)
                        completed.append({"name": entry_name, "status": "done", "phase": phase})
                if pkg:
                    current_pkg = pkg
                on_progress(current_phase, current_pkg, list(completed))
            if time.monotonic() - started > timeout:
                process.kill()
                break
        try:
            returncode = process.wait(timeout=max(1, int(timeout) - int(time.monotonic() - started)))
        except subprocess.TimeoutExpired:
            process.kill()
            returncode = None
    except Exception as exc:
        return {
            "command": label,
            "cwd": _rel(cwd),
            "returncode": None,
            "ok": False,
            "duration_ms": round((time.monotonic() - started) * 1000, 1),
            "output": str(exc),
            "phase": current_phase,
            "completed_packages": [c.get("name") for c in completed],
        }
    output = "\n".join(output_lines)
    for line in output.splitlines():
        event = _classify_npm_line(line)
        if not event:
            continue
        phase, pkg = event
        if pkg and pkg.startswith(("+ ", "- ")):
            pkg = pkg[2:]
        if not pkg:
            continue
        entry_name = pkg.split("@", 1)[0]
        if entry_name and entry_name not in seen:
            seen.add(entry_name)
            completed.append({"name": entry_name, "status": "done", "phase": "installed"})
    ok = returncode in (0, 1)
    return {
        "command": label,
        "cwd": _rel(cwd),
        "returncode": returncode,
        "ok": ok,
        "duration_ms": round((time.monotonic() - started) * 1000, 1),
        "output": _command_output_tail(output.strip()),
        "phase": current_phase,
        "completed_packages": [c.get("name") for c in completed if c.get("name")],
    }


def _command_ecosystem(args: list[str]) -> str:
    if "-m" in args and "pip" in args:
        return "python"
    executable = Path(args[0]).name.lower() if args else ""
    if executable.startswith("pip") or executable.startswith("python"):
        return "python"
    return "npm"


def _run_job(job_id: str, mode: str) -> None:
    _set_job(
        job_id,
        status="running",
        started_at=_utc_now(),
        current_phase="starting",
        current_package="",
        current_ecosystem="",
        current_detail="",
        updated_packages=[],
    )
    steps: list[dict[str, Any]] = []
    updated_packages: list[dict[str, Any]] = []
    if mode == "check":
        commands = [
            ([sys.executable, "-m", "pip", "list", "--outdated", "--format=json"], REPO_ROOT, 180, {0}),
            ([_npm_executable(), "outdated", "--json"], COREUI_ROOT, 180, {0, 1}),
        ]
    else:
        commands = [
            ([sys.executable, "-m", "pip", "install", "--upgrade", "-r", "requirements-dev.txt", "-v"], REPO_ROOT, 1800, {0}),
            ([_npm_executable(), "update"], COREUI_ROOT, 1200, {0, 1}),
        ]

    ok = True
    for args, cwd, timeout, ok_codes in commands:
        ecosystem = _command_ecosystem(args)
        if mode == "check":
            step = _run_subprocess(args, cwd=cwd, timeout=timeout, ok_codes=ok_codes)
        elif ecosystem == "python":
            step = _stream_pip_updates(
                args, cwd=cwd, timeout=timeout, job_id=job_id, completed=updated_packages
            )
        else:
            step = _stream_npm_updates(
                args, cwd=cwd, timeout=timeout, job_id=job_id, completed=updated_packages
            )
        steps.append(step)
        _set_job(
            job_id,
            steps=steps,
            updated_packages=list(updated_packages),
            current_ecosystem=ecosystem,
            current_phase=step.get("phase") or "done",
        )
        ok = ok and bool(step.get("ok"))

    if mode == "check":
        result = {"updates": _parse_update_results(steps)}
    else:
        result = {
            "updates": _parse_update_results(steps),
            "updated_packages": list(updated_packages),
            "inventory": build_dependency_inventory(),
        }
    _set_job(
        job_id,
        status="succeeded" if ok else "failed",
        finished_at=_utc_now(),
        steps=steps,
        result=result,
        updated_packages=list(updated_packages),
        current_phase="done",
        current_package="",
        current_detail="completed" if ok else "failed",
    )


def _start_job(mode: str) -> dict[str, Any]:
    with _JOB_LOCK:
        for job in _JOBS.values():
            if job.get("status") in {"queued", "running"}:
                raise RuntimeError("A dependency job is already running")
        job_id = uuid.uuid4().hex
        job = {
            "id": job_id,
            "mode": mode,
            "status": "queued",
            "created_at": _utc_now(),
            "started_at": None,
            "finished_at": None,
            "steps": [],
            "result": None,
        }
        _JOBS[job_id] = job
        for old_id in list(_JOBS.keys())[:-20]:
            _JOBS.pop(old_id, None)
    thread = threading.Thread(target=_run_job, args=(job_id, mode), daemon=True)
    thread.start()
    return dict(job)


def register_dependencies_routes(bp: Blueprint, *, error_log: Any) -> None:
    @bp.route("/dependencies", methods=["GET"])
    def get_dependencies() -> Any:
        """Return direct third-party dependencies declared by the repository."""
        try:
            return jsonify(build_dependency_inventory())
        except Exception as exc:
            error_log.error("webui_dependencies_routes.get_dependencies", exc_info=True)
            return _error_response(exc)

    @bp.route("/dependencies/check-updates", methods=["POST"])
    def check_dependency_updates() -> Any:
        """Start an update-check job across Python and CoreUI npm dependencies."""
        try:
            return jsonify({"job": _start_job("check")})
        except RuntimeError as exc:
            return _error_response(str(exc), 409)
        except Exception as exc:
            error_log.error("webui_dependencies_routes.check_dependency_updates", exc_info=True)
            return _error_response(exc)

    @bp.route("/dependencies/update", methods=["POST"])
    def update_dependencies() -> Any:
        """Start an update job across Python and CoreUI npm dependencies."""
        try:
            return jsonify({"job": _start_job("update_all")})
        except RuntimeError as exc:
            return _error_response(str(exc), 409)
        except Exception as exc:
            error_log.error("webui_dependencies_routes.update_dependencies", exc_info=True)
            return _error_response(exc)

    @bp.route("/dependencies/jobs/<job_id>", methods=["GET"])
    def get_dependency_job(job_id: str) -> Any:
        """Return dependency job status for polling clients."""
        with _JOB_LOCK:
            job = _JOBS.get(job_id)
        if job is None:
            return _error_response("dependency job not found", 404)
        return jsonify({"job": job})


__all__ = ["build_dependency_inventory", "register_dependencies_routes"]
