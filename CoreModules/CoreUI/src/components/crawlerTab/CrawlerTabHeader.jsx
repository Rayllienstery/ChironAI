import React, { useMemo } from "react";
import CoreUIPillTabs from "../CoreUIPillTabs";
import { t } from "../../services/i18n.js";
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
  const sectionTabs = useMemo(
    () =>
      SECTION_TABS.map((tab) => ({
        ...tab,
        label:
          tab.id === "md-pipeline"
            ? t("crawler.section.md_pipeline")
            : t("crawler.section.crawler"),
      })),
    [],
  );

  return (
    <div className="crawler-header">
      <h2 data-tour="crawler-header">{t("crawler.header.title")}</h2>
      <div className="crawler-header-tabs-and-actions">
        <div data-tour="crawler-section-tabs">
          <CoreUIPillTabs
            tabs={sectionTabs}
            value={activeSection}
            onChange={onSectionChange}
            ariaLabel={t("crawler.section.aria_label")}
            getButtonProps={(tab) =>
              tab.id === "md-pipeline"
                ? { "data-tour": "crawler-md-pipeline-tab" }
                : {}
            }
          />
        </div>
        <div className="crawler-actions">
          <button
            type="button"
            className="coreui-btn coreui-btn-primary"
            data-tour="crawler-crawl-btn"
            onClick={() => onCrawlSource(selectedSource)}
            disabled={
              busy || !selectedSource || crawlingSources.has(selectedSource)
            }
            title={!selectedSource ? t("crawler.actions.crawl_select_hint") : ""}
          >
            {t("crawler.actions.crawl")}
          </button>
          <button
            type="button"
            className="coreui-btn coreui-btn-primary"
            onClick={onCrawlAll}
            disabled={
              busy || sources.length === 0 || crawlingSources.size > 0
            }
            title={t("crawler.actions.crawl_all_hint")}
          >
            {t("crawler.actions.crawl_all")}
          </button>
          <button
            type="button"
            className="coreui-btn coreui-btn-primary"
            data-tour="crawler-crawl-selected"
            onClick={onCrawlSelected}
            disabled={
              busy || selectedSourceIds.size === 0 || crawlingSources.size > 0
            }
            title={t("crawler.actions.crawl_selected_hint")}
          >
            {t("crawler.actions.crawl_selected")}
          </button>
          <button
            type="button"
            className="coreui-btn coreui-btn-primary"
            data-tour="crawler-add-source"
            onClick={onAddSource}
          >
            {t("crawler.actions.add_source")}
          </button>
          <button
            type="button"
            className="coreui-btn coreui-btn-primary"
            data-tour="crawler-create-collection"
            onClick={onCreateCollection}
            disabled={busy || sources.length === 0}
          >
            {t("crawler.actions.create_collection")}
          </button>
          <button
            type="button"
            className="coreui-btn coreui-btn-ghost"
            onClick={onRefresh}
            disabled={busy}
          >
            {t("crawler.actions.refresh")}
          </button>
        </div>
      </div>
    </div>
  );
}
