from __future__ import annotations

from webui_backend import apple_docs_extract
from webui_backend.apple_docs_markdown import render_apple_doc_to_markdown
from webui_backend.apple_docs_models import AppleDocBlock, AppleDocPage, AppleDocSection
from webui_backend.apple_docs_parser import build_apple_doc_page


def test_apple_docs_extract_facade_preserves_public_contract() -> None:
    assert apple_docs_extract.AppleDocBlock is AppleDocBlock
    assert apple_docs_extract.AppleDocPage is AppleDocPage
    assert apple_docs_extract.AppleDocSection is AppleDocSection
    assert apple_docs_extract.build_apple_doc_page is build_apple_doc_page
    assert apple_docs_extract.render_apple_doc_to_markdown is render_apple_doc_to_markdown

    exported = set(apple_docs_extract.__all__)
    assert {
        "AppleDocBlock",
        "AppleDocPage",
        "AppleDocSection",
        "build_apple_doc_page",
        "render_apple_doc_to_markdown",
    }.issubset(exported)
