import React from "react";
import { t } from "../../services/i18n.js";
import { getMdStepTypesMeta } from "./constants";

export default function MdPipelineAddStepModal({ open, onClose, onAddStep }) {
  if (!open) return null;
  return (
                <div
                  className="modal-overlay"
                  onClick={() => onClose()}
                >
                  <div
                    className="modal-content md-pipeline-add-modal"
                    onClick={(e) => e.stopPropagation()}
                  >
                    <div className="modal-header">
                      <h3>{t("crawler.md_pipeline.add_step_title")}</h3>
                      <button
                        type="button"
                        className="modal-close"
                        onClick={() => onClose()}
                        aria-label={t("common.close")}
                      >
                        ×
                      </button>
                    </div>
                    <div className="modal-body md-pipeline-add-modal-body">
                      <p className="md-pipeline-add-modal-intro">
                        {t("crawler.md_pipeline.add_step_intro")}
                      </p>
                      <div className="md-pipeline-add-modal-grid">
                        {getMdStepTypesMeta().map((item) => (
                          <div
                            key={item.type}
                            className="md-pipeline-step-option bordered-view"
                          >
                            <h4 className="md-pipeline-step-option-title">
                              {item.title}
                            </h4>
                            <p className="md-pipeline-step-option-desc">
                              {item.description}
                            </p>
                            <p className="md-pipeline-step-option-example">
                              <strong>{t("crawler.md_pipeline.add_step_example")}</strong>{" "}
                              {item.example}
                            </p>
                            <button
                              type="button"
                              className="crawler-button primary small"
                              onClick={() => onAddStep(item.type)}
                            >
                              {t("crawler.md_pipeline.add_this_step")}
                            </button>
                          </div>
                        ))}
                      </div>
                    </div>
                  </div>
                </div>
  );
}
