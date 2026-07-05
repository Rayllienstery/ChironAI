from __future__ import annotations

from pathlib import Path

from application.webui_help import (
    bundled_help_dir,
    load_help_article,
    load_help_index,
    search_help,
)

_ROOT = Path(__file__).resolve().parents[2]


def test_bundled_help_dir_points_at_repo_content() -> None:
    help_root = bundled_help_dir(_ROOT)
    assert help_root.is_dir()
    assert (help_root / "index.json").is_file()


def test_load_help_index_returns_seven_articles() -> None:
    articles = load_help_index(bundled_help_dir(_ROOT))
    slugs = {row["slug"] for row in articles}
    assert len(articles) == 7
    assert "getting-started" in slugs
    assert "troubleshooting" in slugs


def test_load_help_article_returns_markdown_body() -> None:
    article = load_help_article(bundled_help_dir(_ROOT), "getting-started")
    assert article is not None
    assert article["slug"] == "getting-started"
    assert "Welcome to ChironAI" in article["content"]


def test_load_help_article_rejects_invalid_slug() -> None:
    assert load_help_article(bundled_help_dir(_ROOT), "../secrets") is None
    assert load_help_article(bundled_help_dir(_ROOT), "Missing Article") is None
    assert load_help_article(bundled_help_dir(_ROOT), "does-not-exist") is None


def test_search_help_finds_keyword_in_body() -> None:
    results = search_help(bundled_help_dir(_ROOT), "qdrant")
    slugs = {row["slug"] for row in results}
    assert "rag-collections" in slugs or "indexing" in slugs
    assert all(row.get("snippet") for row in results)


def test_search_help_returns_empty_for_blank_query() -> None:
    assert search_help(bundled_help_dir(_ROOT), "") == []
    assert search_help(bundled_help_dir(_ROOT), "   ") == []


def test_load_help_index_empty_when_index_missing(tmp_path: Path) -> None:
    assert load_help_index(tmp_path / "help") == []


def test_load_help_index_skips_invalid_entries(tmp_path: Path) -> None:
    help_root = tmp_path / "help"
    help_root.mkdir()
    (help_root / "index.json").write_text(
        '{"articles":[{"slug":"valid","title":"Valid","file":"valid.md"},{"slug":"Bad Slug","title":"Bad"}]}',
        encoding="utf-8",
    )
    (help_root / "valid.md").write_text("# Valid", encoding="utf-8")
    rows = load_help_index(help_root)
    assert len(rows) == 1
    assert rows[0]["slug"] == "valid"
