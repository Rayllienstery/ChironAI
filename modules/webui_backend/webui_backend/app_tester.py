import os

from webui_backend import app
from webui_backend.apple_docs_extract import build_apple_doc_page, render_apple_doc_to_markdown
from webui_backend.apple_docs_fetcher import fetch_apple_doc_raw

# Test problematic overview pages
DOC_URL = "https://developer.apple.com/documentation/swiftui/view"


def download_and_convert_single_page(url: str = DOC_URL) -> str:
    """
    Download a single Apple Developer documentation page and convert it to
    RAG-optimized markdown using the new Playwright+CDP pipeline.

    The resulting .md file is written into the rag_sources_for_testing folder
    in the same base directory as app.py.

    Returns the absolute path to the written markdown file.
    """
    print(f"[*] Fetching Apple doc: {url}")

    # Step 1: Fetch raw page data via Playwright + CDP.
    try:
        raw = fetch_apple_doc_raw(url)
    except Exception as e:
        raise RuntimeError(f"Failed to fetch Apple doc from {url}: {e}") from e

    print(f"[+] Fetched: title={raw.title}, breadcrumbs={raw.breadcrumbs}")

    # Step 2: Build structured page model.
    try:
        page = build_apple_doc_page(raw)
    except Exception as e:
        raise RuntimeError(f"Failed to build structured page model: {e}") from e

    # Step 3: Render to RAG-optimized markdown.
    try:
        md = render_apple_doc_to_markdown(page)
    except Exception as e:
        raise RuntimeError(f"Failed to render markdown: {e}") from e

    if not md.strip():
        raise RuntimeError(f"Markdown conversion produced empty content for {url}")

    # Diagnostics: print quality metrics.
    section_count = len(page.sections)
    code_block_count = sum(
        1 for s in page.sections for b in s.blocks if b.kind == "code"
    )
    paragraph_count = sum(
        1 for s in page.sections for b in s.blocks if b.kind == "paragraph"
    )
    print("[*] Quality metrics:")
    print(f"   - Doc kind: {page.doc_kind or 'unknown'}")
    print(f"   - Framework: {page.framework or 'unknown'}")
    print(f"   - Sections: {section_count}")
    print(f"   - Code blocks: {code_block_count}")
    print(f"   - Paragraphs: {paragraph_count}")
    print(f"   - Markdown length: {len(md)} chars")

    # Save to rag_sources_for_testing.
    base_dir = app.BASE_DIR
    out_dir = os.path.join(base_dir, "rag_sources_for_testing")
    os.makedirs(out_dir, exist_ok=True)

    # Use the same stable filename scheme as the main RAG pipeline.
    filename = app._page_filename_for_url(url)
    out_path = os.path.join(out_dir, filename)

    with open(out_path, "w", encoding="utf-8") as f:
        f.write(md)

    return out_path


if __name__ == "__main__":
    import sys
    url = sys.argv[1] if len(sys.argv) > 1 else DOC_URL
    output_path = download_and_convert_single_page(url)
    print(f"Markdown saved to: {output_path}")
