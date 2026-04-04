#!/usr/bin/env python3
"""Analyze markdown files quality for RAG."""
import re
from pathlib import Path

script_dir = Path(__file__).parent if "__file__" in globals() else Path.cwd()
pages_dir = script_dir / "rag_sources" / "apple_documentation" / "pages"
if not pages_dir.exists():
    pages_dir = Path("rag_sources") / "apple_documentation" / "pages"
print(f"Scanning: {pages_dir.absolute()}", file=__import__("sys").stderr)

files = list(pages_dir.glob("*.md"))
total = len(files)

stats = {
    "total": total,
    "with_meta": 0,
    "with_code_blocks": 0,
    "with_headings": 0,
    "empty": 0,
    "code_outside_blocks": [],
    "very_short": [],  # < 200 chars
    "no_content_after_meta": [],
}

for f in files:
    try:
        content = f.read_text(encoding="utf-8")
        
        # Check meta
        if "<!--" in content and "meta:" in content:
            stats["with_meta"] += 1
        
        # Check code blocks
        if "```" in content:
            stats["with_code_blocks"] += 1
        
        # Check headings
        if re.search(r"^#\s+", content, re.MULTILINE):
            stats["with_headings"] += 1
        
        # Check empty
        if not content.strip():
            stats["empty"] += 1
        
        # Check very short
        if len(content.strip()) < 200:
            stats["very_short"].append(f.name)
        
        # Check code outside blocks (simple heuristic)
        lines = content.split("\n")
        in_code_block = False
        code_keywords_found = []
        for i, line in enumerate(lines):
            if line.strip().startswith("```"):
                in_code_block = not in_code_block
            elif not in_code_block:
                # Check for Swift keywords that should be in code blocks
                if re.match(r"^\s*(struct |func |var |let |extension |class |enum |protocol |import |// )", line):
                    # Check if this is actually in prose (not a heading or list)
                    if not line.strip().startswith("#") and not line.strip().startswith("-"):
                        code_keywords_found.append((i + 1, line.strip()[:60]))
        
        if code_keywords_found:
            stats["code_outside_blocks"].append((f.name, code_keywords_found[:3]))
        
        # Check if content after meta is minimal
        meta_end = content.find("-->")
        if meta_end > 0:
            after_meta = content[meta_end + 3:].strip()
            if len(after_meta) < 50:
                stats["no_content_after_meta"].append(f.name)
    
    except Exception as e:
        print(f"Error reading {f.name}: {e}")

print("=" * 60)
print("MARKDOWN FILES QUALITY ANALYSIS")
print("=" * 60)
print(f"\nTotal files: {stats['total']}")
print(f"With metadata: {stats['with_meta']} ({stats['with_meta']/stats['total']*100:.1f}%)")
print(f"With code blocks: {stats['with_code_blocks']} ({stats['with_code_blocks']/stats['total']*100:.1f}%)")
print(f"With headings: {stats['with_headings']} ({stats['with_headings']/stats['total']*100:.1f}%)")
print(f"Empty files: {stats['empty']}")

print(f"\n  Very short files (< 200 chars): {len(stats['very_short'])}")
for fname in stats['very_short'][:10]:
    print(f"   - {fname}")

print(f"\n  Files with code outside blocks: {len(stats['code_outside_blocks'])}")
for fname, examples in stats['code_outside_blocks'][:10]:
    print(f"   - {fname}")
    for line_num, snippet in examples:
        print(f"     Line {line_num}: {snippet}")

print(f"\n  Files with minimal content after meta: {len(stats['no_content_after_meta'])}")
for fname in stats['no_content_after_meta'][:10]:
    print(f"   - {fname}")

print("\n" + "=" * 60)
