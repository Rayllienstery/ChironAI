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
    <div className="crawler-header">
      <h2 data-tour="crawler-header">Crawler / Indexer</h2>
      <div className="crawler-header-tabs-and-actions">
          <CoreUIPillTabs
            tabs={SECTION_TABS}
            value={activeSection}
            onChange={onSectionChange}
            ariaLabel="Crawler and indexer tools"
          />
          <div className="crawler-actions">
            <button
              type="button"
              className="coreui-btn coreui-btn-primary"
              onClick={() => onCrawlSource(selectedSource)}
              disabled={
                busy || !selectedSource || crawlingSources.has(selectedSource)
              }
              title={!selectedSource ? "Select a source to crawl" : ""}
            >
              Crawl
            </button>
            <button
              type="button"
              className="coreui-btn coreui-btn-primary"
              onClick={onCrawlAll}
              disabled={
                busy || sources.length === 0 || crawlingSources.size > 0
              }
              title="Crawl all configured sources"
            >
              Crawl ALL
            </button>
            <button
              type="button"
              className="coreui-btn coreui-btn-primary"
              onClick={onCrawlSelected}
              disabled={
                busy || selectedSourceIds.size === 0 || crawlingSources.size > 0
              }
              title="Crawl selected sources"
            >
              Crawl selected
            </button>
            <button
              type="button"
              className="coreui-btn coreui-btn-primary"
              onClick={onAddSource}
            >
              Add Source
            </button>
            <button
              type="button"
              className="coreui-btn coreui-btn-primary"
              onClick={onCreateCollection}
              disabled={busy || sources.length === 0}
            >
              Create Collection
            </button>
            <button
              type="button"
              className="coreui-btn coreui-btn-ghost"
              onClick={onRefresh}
              disabled={busy}
            >
              Refresh
            </button>
          </div>
        </div>
    </div>
  );
}
