import React from "react";
import { MD_STEP_TYPES_META } from "./constants";

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
                      <h3>Add pipeline step</h3>
                      <button
                        type="button"
                        className="modal-close"
                        onClick={() => onClose()}
                        aria-label="Close"
                      >
                        ×
                      </button>
                    </div>
                    <div className="modal-body md-pipeline-add-modal-body">
                      <p className="md-pipeline-add-modal-intro">
                        Choose a step type. Each card shows a short description
                        and an example.
                      </p>
                      <div className="md-pipeline-add-modal-grid">
                        {MD_STEP_TYPES_META.map((item) => (
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
                              <strong>Example:</strong> {item.example}
                            </p>
                            <button
                              type="button"
                              className="crawler-button primary small"
                              onClick={() => onAddStep(item.type)}
                            >
                              Add this step
                            </button>
                          </div>
                        ))}
                      </div>
                    </div>
                  </div>
                </div>
  );
}
