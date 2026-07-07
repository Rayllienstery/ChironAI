import React from "react";
import { t } from "../../services/i18n.js";
import {
  exportMdPreview,
  formatMdPreviewSize,
  getMdPreviewSize,
  getMdPreviewText,
} from "./helpers";

export default function MdPipelinePreviewModal({
  previewResult,
  pipelinePreviewFilename,
  onClose,
}) {
  if (!previewResult) return null;
  return (
        <div
          className="modal-overlay"
          onClick={() => onClose()}
        >
          <div
            className="modal-content md-pipeline-preview-modal"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="modal-header">
              <h3>{t("crawler.md_pipeline.preview.title")}</h3>
              <div className="md-pipeline-preview-actions">
                <button
                  type="button"
                  className="crawler-button small md-pipeline-preview-export"
                  onClick={() => exportMdPreview(previewResult, pipelinePreviewFilename)}
                >
                  <span className="material-symbols-outlined" aria-hidden="true">
                    download
                  </span>
                  {t("crawler.md_pipeline.preview.export")}
                </button>
                <button
                  type="button"
                  className="modal-close"
                  onClick={() => onClose()}
                  aria-label={t("common.close")}
                >
                  <span className="material-symbols-outlined" aria-hidden="true">
                    close
                  </span>
                </button>
              </div>
            </div>
            <div className="modal-body md-pipeline-preview-modal-body">
              <p className="md-pipeline-preview-meta">
                <span>{previewResult.filename}</span>
                <span>
                  {t("crawler.md_pipeline.preview.processed_length", {
                    count: getMdPreviewText(previewResult).length,
                  })}
                </span>
                <span>
                  {t("crawler.md_pipeline.preview.result_size", {
                    size: formatMdPreviewSize(getMdPreviewSize(previewResult)),
                  })}
                </span>
              </p>
              <pre className="coreui-card-shell md-pipeline-preview-code">
                {getMdPreviewText(previewResult)}
              </pre>
            </div>
          </div>
        </div>

      );
    }
