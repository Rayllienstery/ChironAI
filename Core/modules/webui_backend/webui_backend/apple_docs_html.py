"""Low-level HTML helpers for Apple Developer documentation extraction."""

from __future__ import annotations

try:
    from lxml import html as lxml_html  # type: ignore[import]

    _HAS_LXML = True
except ImportError:  # pragma: no cover - environment without lxml
    lxml_html = None  # type: ignore[assignment]
    _HAS_LXML = False


def _extract_text(el) -> str:
    return (el.text_content() or "").strip()


def _parse_table_to_markdown(table_el) -> str:
    """
    Parse an HTML <table> element into markdown table format.
    
    Returns markdown table string, or empty string if parsing fails.
    """
    if not _HAS_LXML:
        return ""
    
    try:
        rows = []
        # Get all rows (both thead and tbody)
        trs = table_el.xpath(".//tr")
        
        for tr in trs:
            cells = []
            # Get all cells (th or td)
            for cell in tr.xpath(".//th | .//td"):
                cell_text = _extract_text(cell)
                # Clean up whitespace and newlines
                cell_text = " ".join(cell_text.split())
                cells.append(cell_text)
            
            if cells:  # Only add non-empty rows
                rows.append(cells)
        
        if not rows:
            return ""
        
        # Determine column count (use max to handle irregular tables)
        max_cols = max(len(row) for row in rows) if rows else 0
        if max_cols == 0:
            return ""
        
        # Normalize all rows to have the same number of columns
        normalized_rows = []
        for row in rows:
            normalized = row + [""] * (max_cols - len(row))
            normalized_rows.append(normalized[:max_cols])
        
        # Build markdown table
        lines = []
        
        # Header row
        if normalized_rows:
            header = normalized_rows[0]
            lines.append("| " + " | ".join(header) + " |")
            # Separator row
            lines.append("| " + " | ".join(["---"] * max_cols) + " |")
            # Data rows
            for row in normalized_rows[1:]:
                lines.append("| " + " | ".join(row) + " |")
        
        md = "\n".join(lines)

        # Safety: some odd tables in Apple docs can end up flattened into a
        # single physical line with repeated "| --- |" and data rows. As a
        # last-resort fix, split such constructs back into one-row-per-line
        # form so markdown/table parsers see a proper structure.
        if "\n" not in md and "| --- " in md:
            import re
            md = re.sub(r"\|\s+\|", "|\n|", md)
        
        return md
    
    except Exception:  # noqa: BLE001
        return ""


# Blacklist patterns: any text matching these substrings is UI/navigation noise
# and should be filtered out before adding to RAG.
