import React from "react";
import { t } from "../../services/i18n.js";

export default function CrawlerResultModal({ results, onClose }) {
  if (!results.length) return null;
  return (
          <div className="modal-overlay" onClick={() => onClose()}>
            <div
              className="modal-content crawler-result-modal"
              onClick={(e) => e.stopPropagation()}
            >
              <div className="modal-header">
                <h3>
                  {results.length === 1
                    ? t("crawler.result.crawl_finished")
                    : t("crawler.result.crawl_all_finished")}
                </h3>
                <button
                  type="button"
                  className="modal-close"
                  onClick={() => onClose()}
                  aria-label={t("common.close")}
                >
                  ×
                </button>
              </div>
              <div className="modal-body">
                {results.length === 1 ? (
                  (() => {
                    const r = results[0];
                    return (
                      <p>
                        <strong>{r.sourceId}</strong>:{" "}
                        {r.success
                          ? t("crawler.result.completed")
                          : r.error ||
                            t("crawler.result.failed_return_code", {
                              code: r.returnCode ?? "—",
                            })}
                      </p>
                    );
                  })()
                ) : (
                  <>
                    <p className="crawler-result-summary">
                      {t("crawler.result.summary", {
                        success: results.filter((r) => r.success).length,
                        failed: results.filter((r) => !r.success).length,
                      })}
                    </p>
                    <ul className="crawler-result-list">
                      {results.map((r, i) => (
                        <li key={i}>
                          <strong>{r.sourceId}</strong>:{" "}
                          {r.success
                            ? t("crawler.result.ok")
                            : r.error ||
                              t("crawler.result.failed_code", {
                                code: r.returnCode ?? "—",
                              })}
                        </li>
                      ))}
                    </ul>
                  </>
                )}
              </div>
              <div className="modal-footer">
                <button
                  type="button"
                  className="crawler-button primary"
                  onClick={() => onClose()}
                >
                  {t("common.ok")}
                </button>
              </div>
            </div>
          </div>

  );
}
