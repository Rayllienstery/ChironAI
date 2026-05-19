"""Pre-import security audit for ChironAI extensions."""

from __future__ import annotations

import ast
import base64
import binascii
import json
import re
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any
from urllib.parse import urlparse


MANIFEST_FILENAME = "chironai-extension.json"
BLOCKING_SEVERITIES = {"critical"}

_DOCKER_BANNED_PATTERNS = [
    "class DockerRunner",
    "_docker_executable",
    "_resolved_" + "docker_executable",
    "DOCKER" + "_EXE",
    'shutil.which("' + "docker" + '")',
    "shutil.which('" + "docker" + "')",
    "docker.from_env",
    "docker compose",
    "docker-compose",
    "/api/webui/docker",
]
_SHELL_LAUNCHERS = {
    "cmd",
    "cmd.exe",
    "powershell",
    "powershell.exe",
    "pwsh",
    "pwsh.exe",
    "wscript",
    "wscript.exe",
    "cscript",
    "cscript.exe",
    "mshta",
    "mshta.exe",
    "regsvr32",
    "regsvr32.exe",
    "rundll32",
    "rundll32.exe",
    "bash",
    "bash.exe",
    "sh",
    "sh.exe",
}
_DOWNLOAD_EXEC_TERMS = {
    "curl",
    "wget",
    "iwr",
    "irm",
    "invoke-webrequest",
    "invoke-restmethod",
    "invoke-expression",
    "iex",
    "start-process",
}
_DANGEROUS_DECODED_TERMS = {
    "cmd.exe",
    "powershell",
    "pwsh",
    "invoke-expression",
    "iex",
    "start-process",
    "downloadstring",
    "frombase64string",
    "wscript",
    "cscript",
    "mshta",
    "regsvr32",
    "rundll32",
    "curl ",
    "wget ",
}
_BASE64_RE = re.compile(r"(?<![A-Za-z0-9+/=])(?:[A-Za-z0-9+/]{32,}={0,2})(?![A-Za-z0-9+/=])")
_POWERSHELL_ENCODED_RE = re.compile(r"(?i)(?:-|/)(?:enc|encodedcommand)\b")


@dataclass(frozen=True)
class SecurityFinding:
    severity: str
    code: str
    file: str
    line: int = 0
    message: str = ""
    evidence: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "severity": self.severity,
            "code": self.code,
            "file": self.file,
            "line": self.line,
            "message": self.message,
            "evidence": self.evidence,
        }


@dataclass(frozen=True)
class SecurityAuditReport:
    source_dir: Path
    findings: list[SecurityFinding] = field(default_factory=list)

    @property
    def blocked(self) -> bool:
        return any(item.severity in BLOCKING_SEVERITIES for item in self.findings)

    @property
    def blocking_findings(self) -> list[SecurityFinding]:
        return [item for item in self.findings if item.severity in BLOCKING_SEVERITIES]

    def to_dict(self) -> dict[str, Any]:
        return {
            "blocked": self.blocked,
            "findings": [item.to_dict() for item in self.findings],
        }


class ExtensionSecurityError(ValueError):
    """Raised when an extension has blocking security findings."""

    def __init__(self, report: SecurityAuditReport) -> None:
        self.report = report
        super().__init__(format_blocking_error(report))


def _rel(source_dir: Path, path: Path) -> str:
    try:
        return path.relative_to(source_dir).as_posix()
    except ValueError:
        return path.as_posix()


def backend_source_paths(source_dir: Path, entrypoint: str) -> list[Path]:
    module_name, _, attr_name = entrypoint.partition(":")
    if not module_name or not attr_name:
        raise ValueError("backend.entrypoint must be 'module:callable'")
    module_rel = module_name.replace(".", "/")
    py_path = source_dir / f"{module_rel}.py"
    package_init = source_dir / module_rel / "__init__.py"
    if py_path.is_file():
        return sorted(py_path.parent.rglob("*.py"))
    if package_init.is_file():
        return sorted(package_init.parent.rglob("*.py"))
    return []


def _call_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = _call_name(node.value)
        return f"{prefix}.{node.attr}" if prefix else node.attr
    return ""


def _string_constants(node: ast.AST) -> list[tuple[str, int]]:
    out: list[tuple[str, int]] = []
    for child in ast.walk(node):
        if isinstance(child, ast.Constant) and isinstance(child.value, str):
            out.append((child.value, getattr(child, "lineno", 0) or 0))
    return out


def _call_string_values(node: ast.Call) -> list[str]:
    values: list[str] = []

    def visit(value: ast.AST) -> None:
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            values.append(value.value)
        elif isinstance(value, (ast.List, ast.Tuple)):
            for item in value.elts:
                visit(item)
        elif isinstance(value, ast.JoinedStr):
            for item in value.values:
                if isinstance(item, ast.Constant) and isinstance(item.value, str):
                    values.append(item.value)

    for arg in node.args:
        visit(arg)
    return values


def _has_shell_true(node: ast.Call) -> bool:
    for kw in node.keywords:
        if kw.arg == "shell" and isinstance(kw.value, ast.Constant) and kw.value.value is True:
            return True
    return False


def _first_token(text: str) -> str:
    cleaned = text.strip().strip("\"'")
    if not cleaned:
        return ""
    return cleaned.split()[0].strip("\"'").lower()


def _contains_shell_launcher(values: list[str]) -> str:
    joined = " ".join(values).lower()
    for value in values:
        token = _first_token(value)
        if token in _SHELL_LAUNCHERS:
            return token
    for launcher in _SHELL_LAUNCHERS:
        if re.search(rf"(?<![\w.-]){re.escape(launcher)}(?![\w.-])", joined):
            return launcher
    return ""


def _contains_download_execute(values: list[str]) -> str:
    joined = " ".join(values).lower()
    for term in _DOWNLOAD_EXEC_TERMS:
        if re.search(rf"(?<![\w.-]){re.escape(term)}(?![\w.-])", joined):
            return term
    return ""


def _decode_base64_candidate(candidate: str) -> str | None:
    raw = candidate.strip()
    padding = "=" * ((4 - len(raw) % 4) % 4)
    try:
        blob = base64.b64decode(raw + padding, validate=True)
    except (binascii.Error, ValueError):
        return None
    if not blob:
        return None
    for encoding in ("utf-16-le", "utf-8"):
        try:
            text = blob.decode(encoding)
        except UnicodeDecodeError:
            continue
        printable = sum(1 for ch in text if ch.isprintable() or ch.isspace())
        if printable / max(1, len(text)) >= 0.85:
            return text
    return None


def _base64_findings(text: str, *, file: str, line: int) -> list[SecurityFinding]:
    out: list[SecurityFinding] = []
    for match in _BASE64_RE.finditer(text):
        decoded = _decode_base64_candidate(match.group(0))
        if decoded is None:
            continue
        lowered = decoded.lower()
        if any(term in lowered for term in _DANGEROUS_DECODED_TERMS):
            out.append(
                SecurityFinding(
                    severity="critical",
                    code="encoded_command_payload",
                    file=file,
                    line=line,
                    message="Base64 content decodes to shell-like commands",
                    evidence=decoded[:160],
                )
            )
        elif len(match.group(0)) >= 96:
            out.append(
                SecurityFinding(
                    severity="warning",
                    code="encoded_content",
                    file=file,
                    line=line,
                    message="Long base64-like content found",
                    evidence=match.group(0)[:80],
                )
            )
    return out


def _python_findings(source_dir: Path, path: Path) -> list[SecurityFinding]:
    rel = _rel(source_dir, path)
    text = path.read_text(encoding="utf-8", errors="replace")
    findings: list[SecurityFinding] = []
    lowered = text.lower()
    for pattern in _DOCKER_BANNED_PATTERNS:
        haystack = lowered if pattern in {"docker compose", "docker-compose"} else text
        needle = pattern.lower() if haystack is lowered else pattern
        if needle in haystack:
            findings.append(
                SecurityFinding(
                    severity="critical",
                    code="docker_contract_violation",
                    file=rel,
                    message=f"Extension backend bypasses Docker runtime contract: contains {pattern!r}",
                    evidence=pattern,
                )
            )

    try:
        tree = ast.parse(text, filename=str(path))
    except SyntaxError as e:
        findings.append(
            SecurityFinding(
                severity="critical",
                code="python_syntax_error",
                file=rel,
                line=e.lineno or 0,
                message="Extension backend Python cannot be parsed for security audit",
                evidence=e.msg,
            )
        )
        return findings

    for value, line in _string_constants(tree):
        if _POWERSHELL_ENCODED_RE.search(value):
            findings.append(
                SecurityFinding(
                    severity="critical",
                    code="powershell_encoded_command",
                    file=rel,
                    line=line,
                    message="PowerShell encoded command flag found",
                    evidence=value[:160],
                )
            )
        findings.extend(_base64_findings(value, file=rel, line=line))

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = _call_name(node.func)
        line = getattr(node, "lineno", 0) or 0
        if name in {"eval", "exec", "compile", "marshal.loads", "pickle.loads", "cPickle.loads"}:
            findings.append(
                SecurityFinding(
                    severity="critical",
                    code="dynamic_code_execution",
                    file=rel,
                    line=line,
                    message=f"Dynamic code execution API is not allowed: {name}",
                    evidence=name,
                )
            )
        if name in {"os.system", "os.popen"}:
            findings.append(
                SecurityFinding(
                    severity="critical",
                    code="direct_shell_execution",
                    file=rel,
                    line=line,
                    message=f"Direct shell execution is not allowed: {name}",
                    evidence=name,
                )
            )
        if name.startswith("subprocess."):
            values = _call_string_values(node)
            joined = " ".join(values)
            if _has_shell_true(node):
                findings.append(
                    SecurityFinding(
                        severity="critical",
                        code="subprocess_shell_true",
                        file=rel,
                        line=line,
                        message="subprocess shell=True is not allowed in extension backends",
                        evidence=joined[:160],
                    )
                )
            if re.search(r"(?:^|\s|[\"'])docker(?:\s|[\"']|$)", joined):
                findings.append(
                    SecurityFinding(
                        severity="critical",
                        code="docker_contract_violation",
                        file=rel,
                        line=line,
                        message="Extension backend calls Docker through subprocess",
                        evidence=joined[:160],
                    )
                )
            launcher = _contains_shell_launcher(values)
            if launcher:
                findings.append(
                    SecurityFinding(
                        severity="critical",
                        code="shell_launcher",
                        file=rel,
                        line=line,
                        message=f"subprocess launches a shell or script host: {launcher}",
                        evidence=joined[:160],
                    )
                )
            chain = _contains_download_execute(values)
            if chain:
                findings.append(
                    SecurityFinding(
                        severity="critical",
                        code="download_execute_chain",
                        file=rel,
                        line=line,
                        message=f"subprocess command includes download/execute term: {chain}",
                        evidence=joined[:160],
                    )
                )

    return findings


def _manifest_string_findings(value: str, *, key_path: str) -> list[SecurityFinding]:
    findings: list[SecurityFinding] = []
    text = value.strip()
    lower = text.lower()
    file = MANIFEST_FILENAME
    if lower.startswith("javascript:"):
        findings.append(
            SecurityFinding("critical", "manifest_unsafe_url", file, 0, "Manifest contains javascript: URL", text[:160])
        )
    if lower.startswith("data:"):
        findings.append(
            SecurityFinding("critical", "manifest_unsafe_url", file, 0, "Manifest contains data: URL", text[:160])
        )
    if lower.startswith(("file:", "vbscript:")):
        findings.append(
            SecurityFinding("critical", "manifest_unsafe_url", file, 0, "Manifest contains unsafe URL scheme", text[:160])
        )
    parsed = urlparse(text)
    is_url = bool(parsed.scheme)
    if is_url and parsed.scheme not in {"http", "https"} and key_path.endswith(("url", "src", "href")):
        findings.append(
            SecurityFinding("critical", "manifest_unsafe_url", file, 0, "Manifest frame/link URL must be http or https", text[:160])
        )
    looks_like_path = any(part in key_path for part in ("icon", "asset", "path", "file")) or "/" in text or "\\" in text
    if looks_like_path and not is_url:
        posix_parts = PurePosixPath(text.replace("\\", "/")).parts
        win = PureWindowsPath(text)
        if text.startswith(("/", "\\")) or win.is_absolute() or ".." in posix_parts:
            findings.append(
                SecurityFinding(
                    "critical",
                    "manifest_unsafe_path",
                    file,
                    0,
                    "Manifest contains absolute or parent-traversal path",
                    text[:160],
                )
            )
    findings.extend(_base64_findings(text, file=file, line=0))
    return findings


def _walk_manifest(value: Any, *, key_path: str = "") -> list[SecurityFinding]:
    findings: list[SecurityFinding] = []
    if isinstance(value, dict):
        for key, child in value.items():
            next_key = f"{key_path}.{key}" if key_path else str(key)
            findings.extend(_walk_manifest(child, key_path=next_key))
    elif isinstance(value, list):
        for idx, child in enumerate(value):
            findings.extend(_walk_manifest(child, key_path=f"{key_path}[{idx}]"))
    elif isinstance(value, str):
        findings.extend(_manifest_string_findings(value, key_path=key_path.lower()))
    return findings


def _manifest_findings(source_dir: Path) -> list[SecurityFinding]:
    path = source_dir / MANIFEST_FILENAME
    if not path.is_file():
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        return [
            SecurityFinding(
                severity="critical",
                code="manifest_parse_error",
                file=MANIFEST_FILENAME,
                message="Extension manifest cannot be parsed for security audit",
                evidence=str(e),
            )
        ]
    return _walk_manifest(raw)


def _entrypoint_from_manifest(manifest: Any) -> str:
    backend = getattr(manifest, "backend", None)
    return str(getattr(backend, "entrypoint", "") or "").strip()


def audit_extension(
    source_dir: Path,
    *,
    manifest: Any | None = None,
    entrypoint: str | None = None,
) -> SecurityAuditReport:
    src = Path(source_dir)
    ep = str(entrypoint or _entrypoint_from_manifest(manifest)).strip()
    findings: list[SecurityFinding] = []
    findings.extend(_manifest_findings(src))
    if ep:
        for path in backend_source_paths(src, ep):
            findings.extend(_python_findings(src, path))
    return SecurityAuditReport(source_dir=src, findings=findings)


def format_blocking_error(report: SecurityAuditReport) -> str:
    blocking = report.blocking_findings
    if not blocking:
        return "Extension security audit passed"
    details = "; ".join(
        f"{item.file}{':' + str(item.line) if item.line else ''} {item.code}: {item.message}"
        for item in blocking[:8]
    )
    if any(item.code == "docker_contract_violation" for item in blocking):
        return (
            "Extension backend violates Docker contract: use host_context.docker_runtime "
            f"and DockerContainerSpec instead of direct Docker access ({details})"
        )
    return f"Extension security audit blocked unsafe extension ({details})"


def audit_extension_or_raise(
    source_dir: Path,
    *,
    manifest: Any | None = None,
    entrypoint: str | None = None,
) -> SecurityAuditReport:
    report = audit_extension(source_dir, manifest=manifest, entrypoint=entrypoint)
    if report.blocked:
        raise ExtensionSecurityError(report)
    return report
