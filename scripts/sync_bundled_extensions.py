from __future__ import annotations

import argparse
import filecmp
import json
import shutil
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PAYLOAD_ITEMS = ("chironai-extension.json", "backend", "icons")


@dataclass(frozen=True)
class ExtensionSyncTarget:
    extension_id: str
    repo_dir: str
    bundled_dir: str


TARGETS = (
    ExtensionSyncTarget(
        extension_id="ollama-provider",
        repo_dir="chironai-extension-ollama-provider",
        bundled_dir="ollama-provider",
    ),
    ExtensionSyncTarget(
        extension_id="open-webui",
        repo_dir="chironai-extension-open-webui",
        bundled_dir="open-webui",
    ),
    ExtensionSyncTarget(
        extension_id="codex-launcher",
        repo_dir="chironai-extension-codex-launcher",
        bundled_dir="codex-launcher",
    ),
)


def _manifest_id(path: Path) -> str:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return ""
    return str(payload.get("id") or "").strip()


def _same_tree(left: Path, right: Path) -> bool:
    if left.is_file() and right.is_file():
        return filecmp.cmp(left, right, shallow=False)
    if left.is_dir() and right.is_dir():
        cmp = filecmp.dircmp(left, right)
        if cmp.left_only or cmp.right_only or cmp.funny_files:
            return False
        if any(not filecmp.cmp(left / name, right / name, shallow=False) for name in cmp.common_files):
            return False
        return all(_same_tree(left / name, right / name) for name in cmp.common_dirs)
    return False


def _copy_payload(source: Path, dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    for item in PAYLOAD_ITEMS:
        src = source / item
        dst = dest / item
        if not src.exists():
            raise FileNotFoundError(f"missing payload item: {src}")
        if dst.exists():
            if dst.is_dir():
                shutil.rmtree(dst)
            else:
                dst.unlink()
        if src.is_dir():
            shutil.copytree(src, dst)
        else:
            shutil.copy2(src, dst)
    filecmp.clear_cache()


def check_target(source_root: Path, target: ExtensionSyncTarget) -> list[str]:
    source = source_root / target.repo_dir
    dest = REPO_ROOT / "extensions" / "bundled" / target.bundled_dir
    issues: list[str] = []
    if not source.is_dir():
        return [f"{target.extension_id}: source clone not found at {source}"]
    if not dest.is_dir():
        return [f"{target.extension_id}: bundled copy not found at {dest}"]
    manifest_id = _manifest_id(source / "chironai-extension.json")
    if manifest_id != target.extension_id:
        issues.append(f"{target.extension_id}: source manifest id is {manifest_id or '<missing>'}")
    bundled_manifest_id = _manifest_id(dest / "chironai-extension.json")
    if bundled_manifest_id != target.extension_id:
        issues.append(f"{target.extension_id}: bundled manifest id is {bundled_manifest_id or '<missing>'}")
    for item in PAYLOAD_ITEMS:
        src = source / item
        dst = dest / item
        if not src.exists():
            issues.append(f"{target.extension_id}: missing source payload {item}")
        elif not dst.exists():
            issues.append(f"{target.extension_id}: missing bundled payload {item}")
        elif not _same_tree(src, dst):
            issues.append(f"{target.extension_id}: bundled payload differs for {item}")
    return issues


def sync_target(source_root: Path, target: ExtensionSyncTarget) -> None:
    source = source_root / target.repo_dir
    dest = REPO_ROOT / "extensions" / "bundled" / target.bundled_dir
    if not source.is_dir():
        raise FileNotFoundError(f"{target.extension_id}: source clone not found at {source}")
    manifest_id = _manifest_id(source / "chironai-extension.json")
    if manifest_id != target.extension_id:
        raise ValueError(f"{target.extension_id}: source manifest id is {manifest_id or '<missing>'}")
    _copy_payload(source, dest)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check or sync bundled bootstrap extension copies.")
    parser.add_argument("--source-root", default="tmp", help="Directory containing extension repository clones.")
    parser.add_argument("--sync", action="store_true", help="Copy runtime payloads from source clones into extensions/bundled.")
    parser.add_argument("--check", action="store_true", help="Check that bundled payloads match source clones.")
    args = parser.parse_args(argv)

    source_root = Path(args.source_root)
    if not source_root.is_absolute():
        source_root = (REPO_ROOT / source_root).resolve()

    if args.sync:
        for target in TARGETS:
            sync_target(source_root, target)

    issues: list[str] = []
    for target in TARGETS:
        issues.extend(check_target(source_root, target))
    if issues:
        for issue in issues:
            print(issue)
        return 1
    print("Bundled extension bootstrap copies are in sync.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
