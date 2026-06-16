import React from "react";

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
                    ? "Crawl finished"
                    : "Crawl ALL finished"}
                </h3>
                <button
                  type="button"
                  className="modal-close"
                  onClick={() => onClose()}
                  aria-label="Close"
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
                          ? "Completed successfully."
                          : r.error ||
                             `Failed (return code ${r.returnCode ?? "—"}).`}
                      </p>
                    );
                  })()
                ) : (
                  <>
                    <p className="crawler-result-summary">
                      Succeeded:{" "}
                      {results.filter((r) => r.success).length}, Failed:{" "}
                      {results.filter((r) => !r.success).length}
                    </p>
                    <ul className="crawler-result-list">
                      {results.map((r, i) => (
                        <li key={i}>
                          <strong>{r.sourceId}</strong>:{" "}
                          {r.success
                            ? "OK"
                             : r.error || `code ${r.returnCode ?? "—"}`}
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
                  OK
                </button>
              </div>
            </div>
          </div>

  );
}
