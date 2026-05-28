from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


def _load_sync_module(root: Path):
    module_path = root / "scripts" / "sync_bundled_extensions.py"
    spec = importlib.util.spec_from_file_location("sync_bundled_extensions_for_test", module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_sync_bundled_extensions_checks_and_copies_runtime_payload(tmp_path: Path, monkeypatch) -> None:
    root = Path(__file__).resolve().parents[2]
    module = _load_sync_module(root)
    monkeypatch.setattr(module, "REPO_ROOT", tmp_path)
    target = module.ExtensionSyncTarget(
        extension_id="sample-ext",
        repo_dir="sample-repo",
        bundled_dir="sample-ext",
    )
    monkeypatch.setattr(module, "TARGETS", (target,))

    source = tmp_path / "clones" / "sample-repo"
    bundled = tmp_path / "extensions" / "bundled" / "sample-ext"
    (source / "backend").mkdir(parents=True)
    (source / "icons").mkdir()
    (bundled / "backend").mkdir(parents=True)
    (bundled / "icons").mkdir()
    manifest = {"id": "sample-ext", "version": "1.0.0"}
    (source / "chironai-extension.json").write_text(json.dumps(manifest), encoding="utf-8")
    (source / "backend" / "provider.py").write_text("VALUE = 'new'\n", encoding="utf-8")
    (source / "icons" / "icon.svg").write_text("<svg />\n", encoding="utf-8")
    (bundled / "chironai-extension.json").write_text(json.dumps(manifest), encoding="utf-8")
    (bundled / "backend" / "provider.py").write_text("VALUE = 'old'\n", encoding="utf-8")
    (bundled / "icons" / "icon.svg").write_text("<svg />\n", encoding="utf-8")

    issues = module.check_target(tmp_path / "clones", target)
    assert "sample-ext: bundled payload differs for backend" in issues

    module.sync_target(tmp_path / "clones", target)

    assert module.check_target(tmp_path / "clones", target) == []
    assert (bundled / "backend" / "provider.py").read_text(encoding="utf-8") == "VALUE = 'new'\n"
