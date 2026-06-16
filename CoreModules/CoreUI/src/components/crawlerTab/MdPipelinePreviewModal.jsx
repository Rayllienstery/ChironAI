import React from "react";
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
              <h3>Preview result</h3>
              <div className="md-pipeline-preview-actions">
                <button
                  type="button"
                  className="crawler-button small md-pipeline-preview-export"
                  onClick={() => exportMdPreview(previewResult, pipelinePreviewFilename)}
                >
                  <span className="material-symbols-outlined" aria-hidden="true">
                    download
                  </span>
                  Export MD
                </button>
                <button
                  type="button"
                  className="modal-close"
                  onClick={() => onClose()}
                  aria-label="Close"
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
                  processed length: {getMdPreviewText(previewResult).length} chars
                </span>
                <span>
                  result size: {formatMdPreviewSize(getMdPreviewSize(previewResult))}
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
