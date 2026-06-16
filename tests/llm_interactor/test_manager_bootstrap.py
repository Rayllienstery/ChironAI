from __future__ import annotations

from pathlib import Path

from llm_interactor.contracts import ProviderHostContext
from llm_interactor.install_state import ExtensionsRepository, InstalledExtensionRecord
from llm_interactor.manager_bootstrap import (
    RuntimeBootstrap,
    discover_runtime_extensions,
    ensure_required_bundled_enabled,
    source_dirs_for_records,
)


def test_source_dirs_for_records_skips_missing_directories(tmp_path: Path) -> None:
    installed_dir = tmp_path / "installed"
    present = installed_dir / "present-ext" / "1.0.0"
    present.mkdir(parents=True)
    records = [
        InstalledExtensionRecord(id="present-ext", version="1.0.0", enabled=True, installed=True),
        InstalledExtensionRecord(id="missing-ext", version="1.0.0", enabled=True, installed=True),
        InstalledExtensionRecord(id="disabled-ext", version="1.0.0", enabled=False, installed=True),
    ]
    dirs = source_dirs_for_records(records, installed_dir)
    assert dirs == [present]


def test_discover_runtime_extensions_returns_empty_bootstrap_for_no_sources(tmp_path: Path) -> None:
    blocked: list[object] = []

    bootstrap = discover_runtime_extensions(
        source_dirs=[],
        host_context=ProviderHostContext(project_root=tmp_path, get_settings_repository=lambda: None),
        enabled_extension_ids=set(),
        use_sandbox=False,
        default_provider_id=None,
        on_security_blocked=blocked.extend,
    )
    assert isinstance(bootstrap, RuntimeBootstrap)
    assert bootstrap.loaded == []
    assert bootstrap.failed == []
    assert blocked == []


def test_ensure_required_bundled_enabled_reenables_ollama_provider() -> None:
    class _Repo:
        def __init__(self) -> None:
            self.data: dict[str, str] = {}

        def get_app_setting(self, key: str):
            return self.data.get(key)

        def set_app_setting(self, key: str, value: str) -> None:
            self.data[key] = value

    repo = _Repo()
    ext_repo = ExtensionsRepository(repo)
    ext_repo.save_records(
        [
            InstalledExtensionRecord(
                id="ollama-provider",
                version="0.1.6",
                enabled=False,
                installed=True,
                source={"type": "bundled"},
            ),
            InstalledExtensionRecord(
                id="open-webui",
                version="0.1.2",
                enabled=False,
                installed=True,
                source={"type": "bundled"},
            ),
        ]
    )

    changed = ensure_required_bundled_enabled(
        repo=ext_repo,
        blocklist_match_for_record=lambda _record: {"matched": False},
    )

    assert changed is True
    records = {item.id: item for item in ext_repo.list_records()}
    assert records["ollama-provider"].enabled is True
    assert records["open-webui"].enabled is False
