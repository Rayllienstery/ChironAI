from __future__ import annotations

import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
_WEBUI_BACKEND = _ROOT / "CoreModules" / "WebUIBackend"
if str(_WEBUI_BACKEND) not in sys.path:
    sys.path.insert(0, str(_WEBUI_BACKEND))
_ERROR_MANAGER = _ROOT / "CoreModules" / "ErrorManager"
if str(_ERROR_MANAGER) not in sys.path:
    sys.path.insert(0, str(_ERROR_MANAGER))


def test_local_markdown_ingest_embed_mismatch_reports_batch_size(monkeypatch: pytest.MonkeyPatch) -> None:
    from webui_backend import ingest_markdown_local

    monkeypatch.setattr(
        ingest_markdown_local,
        "invoke_embed",
        lambda *_a, **_k: {"embeddings": [[1.0, 2.0]]},
    )

    with pytest.raises(RuntimeError, match="1 embeddings for batch size 2"):
        ingest_markdown_local.get_embeddings(["one", "two"])


def test_local_markdown_ingest_embed_error_preserves_message(monkeypatch: pytest.MonkeyPatch) -> None:
    from webui_backend import ingest_markdown_local

    def fail_embed(*_a, **_k):
        raise ingest_markdown_local.OllamaProviderHttpError("provider embed failed")

    monkeypatch.setattr(ingest_markdown_local, "invoke_embed", fail_embed)

    with pytest.raises(RuntimeError, match="provider embed failed"):
        ingest_markdown_local.get_embeddings(["one"])
