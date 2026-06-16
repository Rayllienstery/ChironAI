import React from "react";
import { MD_STEP_TYPES_META } from "./constants";
import MdPipelineStepParams from "./MdPipelineStepParams";

export default function MdPipelineStepCard({
  step,
  index,
  stepKey,
  isExpanded,
  stepsLength,
  onToggleExpanded,
  onChangeStepType,
  onMoveStep,
  onRemoveStep,
  onUpdateStep,
  onUpdateLine,
  onAddLine,
  onRemoveLine,
}) {
  return (
    <div
      className={`md-pipeline-step-card${isExpanded ? "" : " md-pipeline-step-card-collapsed"}`}
      role="listitem"
    >
                      <div className="md-pipeline-step-header">
                        <button
                          type="button"
                          className="md-pipeline-step-toggle"
                          onClick={() => onToggleExpanded(stepKey)}
                          aria-label={
                            isExpanded ? "Collapse step" : "Expand step"
                          }
                        >
                          <span className="material-symbols-outlined" aria-hidden="true">
                            {isExpanded ? "expand_more" : "chevron_right"}
                          </span>
                        </button>
                        <label className="md-pipeline-step-type-label">
                          <span className="md-pipeline-step-type-caption">
                            Step type:
                          </span>
                          <select
                            value={step.type}
                            onChange={(e) =>
                              onChangeStepType(index, e.target.value)
                            }
                            className="coreui-select coreui-select--dense md-pipeline-step-type-select"
                            aria-label="Change step type"
                          >
                            {MD_STEP_TYPES_META.map((item) => (
                              <option key={item.type} value={item.type}>
                                {item.title}
                              </option>
                            ))}
                          </select>
                        </label>
                        <div className="md-pipeline-step-actions">
                          <button
                            type="button"
                            className="crawler-button small md-pipeline-icon-button"
                            onClick={() => onMoveStep(index, -1)}
                            disabled={index === 0}
                            aria-label="Move up"
                            title="Move up"
                          >
                            <span className="material-symbols-outlined" aria-hidden="true">
                              arrow_upward
                            </span>
                          </button>
                          <button
                            type="button"
                            className="crawler-button small md-pipeline-icon-button"
                            onClick={() => onMoveStep(index, 1)}
                            disabled={index === stepsLength - 1}
                            aria-label="Move down"
                            title="Move down"
                          >
                            <span className="material-symbols-outlined" aria-hidden="true">
                              arrow_downward
                            </span>
                          </button>
                          <button
                            type="button"
                            className="crawler-button small"
                            onClick={() => onRemoveStep(index)}
                            aria-label="Remove step"
                          >
                            Delete
                          </button>
                        </div>
                      </div>
                      {isExpanded && (
                        <div className="md-pipeline-step-params">
                          <MdPipelineStepParams
                            step={step}
                            index={index}
                            onUpdateStep={onUpdateStep}
                            onUpdateLine={onUpdateLine}
                            onAddLine={onAddLine}
                            onRemoveLine={onRemoveLine}
                          />
                        </div>
                      )}
    </div>
  );
}
