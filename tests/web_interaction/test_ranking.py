"""Tests for web_interaction.ranking."""

from __future__ import annotations

from web_interaction.ranking import rank_and_trim, top_domains


def test_rank_prefers_apple_docs() -> None:
    snippets = [
        {"title": "Spam", "url": "https://random-blog.example/p", "body": "x"},
        {"title": "Apple", "url": "https://developer.apple.com/documentation/uikit/uiviewcontroller", "body": "official"},
    ]
    out = rank_and_trim(snippets, max_n=1, query="UIViewController lifecycle apple documentation")
    assert len(out) == 1
    assert "developer.apple.com" in (out[0].get("url") or "")


def test_rank_drops_blocklisted() -> None:
    snippets = [
        {"title": "P", "url": "https://pinterest.com/pin/1", "body": "a"},
        {"title": "G", "url": "https://github.com/a/b", "body": "b"},
    ]
    out = rank_and_trim(snippets, max_n=2)
    assert len(out) == 1
    assert "github.com" in (out[0].get("url") or "")


def test_rank_drops_flux_glasses_and_hidden_wiki() -> None:
    snippets = [
        {"title": "f.lux", "url": "https://justgetflux.com/", "body": "screen tint"},
        {"title": "wiki", "url": "https://thehiddenwiki.com/feed/", "body": "onion"},
        {"title": "GGUF", "url": "https://huggingface.co/unsloth/FLUX.2-klein-base-9B-GGUF", "body": "flux.2 klein 9B gguf"},
    ]
    out = rank_and_trim(snippets, max_n=3, query="flux.2 klein 9B gguf")
    assert out
    assert "huggingface.co" in (out[0].get("url") or "")


def test_rank_prefers_arxiv_over_homepage_noise() -> None:
    snippets = [
        {"title": "VS2015", "url": "https://jingyan.baidu.com/article/x", "body": "visual studio", "score": 1.0},
        {"title": "Paper", "url": "https://arxiv.org/abs/2309.06180", "body": "paged attention vllm", "score": 0.5},
        {"title": "Amazon", "url": "https://www.amazon.com/", "body": "shop", "score": 0.8},
    ]
    out = rank_and_trim(snippets, max_n=2, query="paged attention vllm paper")
    assert "arxiv.org" in (out[0].get("url") or "")


def test_rank_demotes_mdn_on_model_queries() -> None:
    snippets = [
        {"title": "Clear-Site-Data", "url": "https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Clear-Site-Data", "body": "site data", "score": 1.0},
        {"title": "GGUF", "url": "https://huggingface.co/unsloth/FLUX.2-klein-base-9B-GGUF", "body": "flux.2 klein 9B gguf", "score": 0.4},
    ]
    out = rank_and_trim(snippets, max_n=1, query="flux.2 klein 9B gguf")
    assert "huggingface.co" in (out[0].get("url") or "")


def test_top_domains() -> None:
    s = [
        {"url": "https://a.example/x"},
        {"url": "https://b.example/y"},
    ]
    assert top_domains(s, 2) == ["a.example", "b.example"]


def test_preferred_domains_env(monkeypatch) -> None:
    monkeypatch.setenv("WEB_INTERACTION_PREFERRED_DOMAINS", "swift.org,example.org")
    s = [
        {"title": "E", "url": "https://foo.example.org/z", "body": "x"},
        {"title": "S", "url": "https://swift.org/y", "body": "longer swift body wins tie-break"},
    ]
    out = rank_and_trim(s, max_n=1)
    assert "swift.org" in (out[0].get("url") or "")
