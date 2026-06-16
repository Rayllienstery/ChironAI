"""Generate crawlerTab hooks and presentation components from CrawlerTab.jsx."""
from pathlib import Path
import textwrap

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "components"
OUT = SRC / "crawlerTab"
ORIG = (SRC / "CrawlerTab.jsx").read_text(encoding="utf-8")
lines = ORIG.splitlines(keepends=True)


def sl(a: int, b: int) -> str:
    return "".join(lines[a - 1 : b])


def w(name: str, content: str) -> None:
    path = OUT / name
    path.write_text(content, encoding="utf-8")
    print(f"{name}: {len(content.splitlines())} lines")


# --- CrawlerResultModal.jsx ---
w(
    "CrawlerResultModal.jsx",
    textwrap.dedent(
        """\
        import React from "react";

        export default function CrawlerResultModal({ results, onClose }) {
          if (!results.length) return null;
          return (
        """
    )
    + sl(1421, 1485)
    + "\n  );\n}\n",
)

# Fix variable names in CrawlerResultModal - replace crawlAllResults with results
p = (OUT / "CrawlerResultModal.jsx").read_text(encoding="utf-8")
p = p.replace("crawlAllResults", "results")
p = p.replace("setCrawlAllResults([])", "onClose()")
(OUT / "CrawlerResultModal.jsx").write_text(p, encoding="utf-8")

# --- CrawlerTabHeader.jsx ---
header = textwrap.dedent(
    """\
    import React from "react";
    import CoreUIPillTabs from "../CoreUIPillTabs";
    import { SECTION_TABS } from "./constants";

    export default function CrawlerTabHeader({
      activeSection,
      onSectionChange,
      selectedSource,
      sources,
      selectedSourceIds,
      crawlingSources,
      busy,
      onCrawlSource,
      onCrawlAll,
      onCrawlSelected,
      onAddSource,
      onCreateCollection,
      onRefresh,
    }) {
      return (
    """
) + sl(1347, 1416) + "\n  );\n}\n"
header = header.replace("setActiveSection", "onSectionChange")
header = header.replace("() => handleCrawlSource(selectedSource)", "() => onCrawlSource(selectedSource)")
header = header.replace("onClick={handleCrawlAll}", "onClick={onCrawlAll}")
header = header.replace("onClick={handleCrawlSelected}", "onClick={onCrawlSelected}")
header = header.replace("() => setShowAddSourceModal(true)", "onAddSource")
header = header.replace("() => setShowCreateModal(true)", "onCreateCollection")
header = header.replace("onClick={handleRefresh}", "onClick={onRefresh}")
w("CrawlerTabHeader.jsx", header)

# --- CrawlerSourcesPanel.jsx ---
panel = textwrap.dedent(
    """\
    import React from "react";
    import EmptyState from "../EmptyState";
    import { formatDate } from "./helpers";

    export default function CrawlerSourcesPanel({
      loading,
      sources,
      selectedSource,
      sourcePages,
      selectedSourceIds,
      crawlingSources,
      onToggleSelectAll,
      onToggleSourceSelected,
      onSourceClick,
      onEditSource,
      onCrawlSource,
    }) {
      if (loading) {
        return <div className="loading">Loading sources...</div>;
      }
      if (!sources.length) {
        return (
          <EmptyState className="empty-state">
            No crawl sources found. Run crawler first.
          </EmptyState>
        );
      }
      return (
    """
) + sl(1501, 1687) + "\n  );\n}\n"
panel = panel.replace("handleToggleSelectAll", "onToggleSelectAll")
panel = panel.replace("toggleSourceSelected", "onToggleSourceSelected")
panel = panel.replace("handleSourceClick", "onSourceClick")
panel = panel.replace("handleEditSource", "onEditSource")
panel = panel.replace("handleCrawlSource", "onCrawlSource")
w("CrawlerSourcesPanel.jsx", panel)

print("Generated presentation components (partial)")
