"""HTML to Markdown: regex, DOM (lxml), and html2text backends."""

from __future__ import annotations

import re

try:
    from lxml import html as lxml_html

    _HAS_LXML = True
except ImportError:
    lxml_html = None  # type: ignore[assignment,misc]
    _HAS_LXML = False

try:
    import html2text

    _HAS_HTML2TEXT = True
except ImportError:
    html2text = None  # type: ignore[assignment,misc]
    _HAS_HTML2TEXT = False


def html_to_markdown_regex(html: str) -> str:
    """Fallback regex-based HTML→markdown when lxml is not available."""
    if not html:
        return ""
    html = re.sub(
        r"<(nav|header|footer|aside)[^>]*>.*?</\1>", "", html, flags=re.IGNORECASE | re.DOTALL
    )
    html = re.sub(
        r"<div[^>]+(nav|navigation|breadcrumb|breadcrumbs|sidebar|toc)[^>]*>.*?</div>",
        "",
        html,
        flags=re.IGNORECASE | re.DOTALL,
    )
    html = re.sub(
        r"<ul[^>]+(nav|navigation|breadcrumb|breadcrumbs)[^>]*>.*?</ul>",
        "",
        html,
        flags=re.IGNORECASE | re.DOTALL,
    )
    html = re.sub(
        r"<([a-zA-Z0-9]+)[^>]+role=\"navigation\"[^>]*>.*?</\1>",
        "",
        html,
        flags=re.IGNORECASE | re.DOTALL,
    )
    html = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", html, flags=re.IGNORECASE | re.DOTALL)

    def _replace_heading(match: re.Match[str]) -> str:
        level, text = match.group(1), match.group(2).strip()
        return f"\n\n{'#' * int(level)} {text}\n\n"

    html = re.sub(r"<h([1-3])[^>]*>(.*?)</h\1>", _replace_heading, html, flags=re.IGNORECASE | re.DOTALL)
    html = re.sub(r"<p[^>]*>(.*?)</p>", r"\1\n\n", html, flags=re.IGNORECASE | re.DOTALL)
    html = re.sub(r"<li[^>]*>(.*?)</li>", r"- \1\n", html, flags=re.IGNORECASE | re.DOTALL)
    html = re.sub(r"<br\s*/?>", "\n", html, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", html)
    text = text.replace("&nbsp;", " ").replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    lines = [ln.rstrip() for ln in text.splitlines()]
    text = re.sub(r"\n{3,}", "\n\n", "\n".join(lines).strip())
    return text


def html_to_markdown_dom(html: str) -> str:
    """
    DOM-based deterministic HTML → markdown.
    - Drops nav/header/footer/aside/script/style and role=navigation.
    - Preserves h1–h6, p, pre/code blocks, inline code, tables.
    """
    if not html:
        return ""
    if not _HAS_LXML or lxml_html is None:
        return html_to_markdown_regex(html)
    try:
        root = lxml_html.fromstring(html)
    except Exception:
        return html_to_markdown_regex(html)

    to_remove: list = []
    for tag in ("script", "style", "nav", "header", "footer", "aside"):
        to_remove.extend(root.iter(tag))
    to_remove.extend(root.xpath("//*[@role='navigation']"))
    for el in to_remove:
        parent = el.getparent()
        if parent is not None:
            parent.remove(el)

    blocks = root.xpath(
        "//*[self::h1 or self::h2 or self::h3 or self::h4 or self::h5 or self::h6 "
        "or self::p or self::pre or self::table or self::ul or self::ol or self::li "
        "or (self::div and (contains(concat(' ', normalize-space(@class), ' '), ' code ') "
        "or contains(concat(' ', normalize-space(@class), ' '), ' snippet ') "
        "or contains(concat(' ', normalize-space(@class), ' '), ' sample ') "
        "or .//pre or .//code))]"
    )

    ancestor_block_tags = {"h1", "h2", "h3", "h4", "h5", "h6", "p", "pre", "table", "li", "div"}

    top_level = []
    for b in blocks:
        parent = b.getparent()
        is_top = True
        while parent is not None:
            tag = (parent.tag or "").lower()
            if tag in ancestor_block_tags:
                is_top = False
                break
            parent = parent.getparent()
        if is_top:
            top_level.append(b)

    out: list[str] = []
    for el in top_level:
        tag = (el.tag or "").lower()
        if tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            level = int(tag[1])
            text = (el.text_content() or "").strip()
            if text:
                out.append("\n\n" + "#" * level + " " + text + "\n\n")
        elif tag == "p":
            text = (el.text_content() or "").strip()
            if text:
                out.append(text + "\n\n")
        elif tag == "pre":
            code_el = el.find(".//code")
            raw = (code_el.text_content() if code_el is not None else el.text_content()) or ""
            raw = raw.strip()
            if raw:
                lang = ""
                if code_el is not None:
                    code_class = code_el.get("class", "") or ""
                    if "swift" in code_class.lower():
                        lang = "swift"
                    elif "objective-c" in code_class.lower() or "objc" in code_class.lower():
                        lang = "objectivec"
                if not lang and (
                    "import " in raw or "func " in raw or "class " in raw or "let " in raw or "var " in raw
                ):
                    lang = "swift"
                lang_suffix = lang if lang else ""
                out.append(f"\n\n```{lang_suffix}\n{raw}\n```\n\n")
        elif tag == "div":
            raw = (el.text_content() or "").strip()
            if raw and len(raw) > 2:
                div_class = el.get("class", "") or ""
                is_code_div = any(
                    keyword in div_class.lower() for keyword in ["code", "snippet", "sample", "example"]
                )
                has_code_structure = any(
                    pattern in raw for pattern in ["import ", "func ", "class ", "let ", "var ", "{", "}", "()"]
                )

                if is_code_div or (has_code_structure and len(raw) < 5000):
                    lang = ""
                    if "swift" in div_class.lower():
                        lang = "swift"
                    elif "objective-c" in div_class.lower() or "objc" in div_class.lower():
                        lang = "objectivec"
                    elif not lang and has_code_structure:
                        lang = "swift"
                    lang_suffix = lang if lang else ""
                    out.append(f"\n\n```{lang_suffix}\n{raw}\n```\n\n")
                else:
                    out.append(raw + "\n\n")
        elif tag == "table":
            rows = el.findall(".//tr")
            if not rows:
                continue
            cells = []
            for tr in rows:
                row_cells = tr.findall("td") or tr.findall("th")
                cells.append([(c.text_content() or "").strip().replace("|", "\\|") for c in row_cells])
            if not cells:
                continue
            sep = "| " + " | ".join(["---"] * len(cells[0])) + " |"
            out.append("\n\n" + "| " + " | ".join(cells[0]) + " |\n" + sep + "\n")
            for row in cells[1:]:
                out.append("| " + " | ".join(row) + " |\n")
            out.append("\n")
        elif tag == "li":
            text = (el.text_content() or "").strip()
            if text:
                out.append("- " + text + "\n")
        elif tag in ("ul", "ol"):
            continue

    text = "".join(out)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text


def html_to_markdown_html2text(html: str) -> str:
    """
    HTML → markdown via html2text. Preserves code blocks (pre/code), lists, headings.
    """
    if not _HAS_HTML2TEXT or html2text is None or not html:
        return ""
    h = html2text.HTML2Text()
    h.ignore_links = False
    h.ignore_images = True
    h.body_width = 0
    h.ignore_emphasis = False
    h.single_line_break = False
    try:
        raw = h.handle(html)
    except Exception:
        return ""
    return re.sub(r"\n{3,}", "\n\n", raw.strip())


def html_to_markdown(html: str, prefer_code_preservation: bool = True) -> str:
    """
    Deterministic HTML → markdown. When html2text is available and prefer_code_preservation
    is True, uses it to preserve code blocks (pre/code) and structure. Otherwise uses
    DOM-based normalizer (lxml) or regex fallback.
    """
    if not html:
        return ""
    if prefer_code_preservation and _HAS_HTML2TEXT:
        md = html_to_markdown_html2text(html)
        if md and len(md.strip()) > 100:
            return md
    raw = html_to_markdown_dom(html) if _HAS_LXML else html_to_markdown_regex(html)
    return re.sub(r"\n{3,}", "\n\n", raw.strip())


__all__ = [
    "html_to_markdown",
    "html_to_markdown_regex",
    "html_to_markdown_dom",
    "html_to_markdown_html2text",
]
