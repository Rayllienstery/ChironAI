"""Generate crawlerTab hooks and MdPipelineSection from CrawlerTab.jsx."""
from pathlib import Path
import textwrap

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "components"
OUT = SRC / "crawlerTab"
lines = (SRC / "CrawlerTab.jsx").read_text(encoding="utf-8").splitlines(keepends=True)


def sl(a: int, b: int) -> str:
    return "".join(lines[a - 1 : b])


def w(name: str, content: str) -> None:
    (OUT / name).write_text(content, encoding="utf-8")
    print(f"{name}: {len(content.splitlines())} lines")


# --- useCrawlerSection.js ---
use_crawler = textwrap.dedent(
    """\
    import { useEffect, useRef, useState } from "react";
    import Card from "../Card";
    import {
      addCrawlerSource,
      crawlSource,
      getCrawlerSource,
      getCrawlerSourcePages,
      getCrawlerSources,
      getCrawlStatus,
      getRagCollections,
      updateCrawlerSource,
    } from "../../services/api";

    export function useCrawlerSection({ nc, activeSection }) {
    """
) + sl(149, 155) + sl(180, 183) + sl(203, 205) + sl(191, 201) + sl(181, 190)

# Fix: the above concatenation might duplicate - let me be more precise
use_crawler = textwrap.dedent(
    """\
    import { useEffect, useRef, useState } from "react";
    import Card from "../Card";
    import {
      addCrawlerSource,
      crawlSource,
      getCrawlerSource,
      getCrawlerSourcePages,
      getCrawlerSources,
      getCrawlStatus,
      getRagCollections,
      updateCrawlerSource,
    } from "../../services/api";

    export function useCrawlerSection({ nc, activeSection }) {
    """
)

# State blocks - manually specify line ranges for crawler-only state
state_lines = [
    sl(149, 155),  # loading, sources, selectedSource, sourcePages, collections, error, busy
    sl(180, 183),  # crawlingSources, crawlAllResults ref
    sl(203, 205),  # crawlPersistedCountRef, selectedSourceIds
    sl(181, 190),  # add source modal
    sl(191, 201),  # edit source modal
]
use_crawler += "".join(state_lines)

# Functions and effects
use_crawler += sl(234, 271)  # loadSources, loadCollections, initial effect
use_crawler += sl(527, 624)  # notification + crawl polling effects
use_crawler += sl(626, 648)  # handleSourceClick, handleRefresh
use_crawler += sl(1171, 1344)  # toggle, crawl handlers, add/edit source

use_crawler += textwrap.dedent(
    """
      return {
        loading,
        sources,
        selectedSource,
        sourcePages,
        collections,
        error,
        setError,
        busy,
        crawlingSources,
        crawlAllResults,
        setCrawlAllResults,
        selectedSourceIds,
        showAddSourceModal,
        setShowAddSourceModal,
        addSourceForm,
        setAddSourceForm,
        addingSource,
        showEditSourceModal,
        setShowEditSourceModal,
        editingSourceId,
        editSourceForm,
        setEditSourceForm,
        updatingSource,
        loadSources,
        loadCollections,
        handleSourceClick,
        handleRefresh,
        toggleSourceSelected,
        handleToggleSelectAll,
        handleCrawlSource,
        handleCrawlAll,
        handleCrawlSelected,
        handleAddSource,
        handleEditSource,
        handleUpdateSource,
      };
    }
    """
)
w("useCrawlerSection.js", use_crawler)

print("hooks part 1 done")
