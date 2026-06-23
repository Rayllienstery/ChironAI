import React from "react";
import { MD_STEP_TYPES_META } from "./constants";

export default function MdPipelineStepParams({
  step,
  index,
  onUpdateStep,
  onUpdateLine,
  onAddLine,
  onRemoveLine,
}) {
  return (
    <>
                          {step.type === "delete_lines_exact" && (
                            <div className="md-pipeline-param-list">
                              <span className="md-pipeline-param-list-label">
                                Lines (add or remove):
                              </span>
                              {(step.params?.lines || []).map(
                                (line, lineIdx) => (
                                  <div
                                    key={lineIdx}
                                    className="md-pipeline-param-list-row"
                                  >
                                    <input
                                      type="text"
                                      value={line}
                                      onChange={(e) =>
                                        onUpdateLine(
                                          index,
                                          "lines",
                                          lineIdx,
                                          e.target.value,
                                        )
                                      }
                                      className="md-pipeline-param-input md-pipeline-param-list-input"
                                      placeholder="Line to delete (exact match)"
                                    />
                                    <button
                                      type="button"
                                      className="crawler-button small"
                                      onClick={() =>
                                        onRemoveLine(
                                          index,
                                          "lines",
                                          lineIdx,
                                        )
                                      }
                                      aria-label="Remove line"
                                    >
                                      Remove
                                    </button>
                                  </div>
                                ),
                              )}
                              <button
                                type="button"
                                className="crawler-button small"
                                onClick={() => onAddLine(index, "lines")}
                              >
                                + Add line
                              </button>
                            </div>
                          )}
                          {step.type === "delete_lines_containing" && (
                            <div className="md-pipeline-param-list">
                              <span className="md-pipeline-param-list-label">
                                Substrings (add or remove):
                              </span>
                              {(step.params?.substrings || []).map(
                                (sub, lineIdx) => (
                                  <div
                                    key={lineIdx}
                                    className="md-pipeline-param-list-row"
                                  >
                                    <input
                                      type="text"
                                      value={sub}
                                      onChange={(e) =>
                                        onUpdateLine(
                                          index,
                                          "substrings",
                                          lineIdx,
                                          e.target.value,
                                        )
                                      }
                                      className="md-pipeline-param-input md-pipeline-param-list-input"
                                      placeholder="Substring (line containing this will be deleted)"
                                    />
                                    <button
                                      type="button"
                                      className="crawler-button small"
                                      onClick={() =>
                                        onRemoveLine(
                                          index,
                                          "substrings",
                                          lineIdx,
                                        )
                                      }
                                      aria-label="Remove line"
                                    >
                                      Remove
                                    </button>
                                  </div>
                                ),
                              )}
                              <button
                                type="button"
                                className="crawler-button small"
                                onClick={() =>
                                  onAddLine(index, "substrings")
                                }
                              >
                                + Add line
                              </button>
                            </div>
                          )}
                          {(step.type === "delete_lines_regex" ||
                            step.type === "delete_regex_match") && (
                            <label>
                              Pattern:
                              <input
                                type="text"
                                value={step.params?.pattern || ""}
                                onChange={(e) =>
                                  onUpdateStep(index, {
                                    params: {
                                      ...step.params,
                                      pattern: e.target.value,
                                    },
                                  })
                                }
                                className="md-pipeline-param-input"
                                placeholder="Regex pattern"
                              />
                            </label>
                          )}
                          {step.type === "delete_sentences_starting_with" && (
                            <div className="md-pipeline-param-list">
                              <span className="md-pipeline-param-list-label">
                                Sentence prefixes (add or remove):
                              </span>
                              {(step.params?.prefixes || []).map(
                                (prefix, lineIdx) => (
                                  <div
                                    key={lineIdx}
                                    className="md-pipeline-param-list-row"
                                  >
                                    <input
                                      type="text"
                                      value={prefix}
                                      onChange={(e) =>
                                        onUpdateLine(
                                          index,
                                          "prefixes",
                                          lineIdx,
                                          e.target.value,
                                        )
                                      }
                                      className="md-pipeline-param-input md-pipeline-param-list-input"
                                      placeholder="Sentence starts with..."
                                    />
                                    <button
                                      type="button"
                                      className="crawler-button small"
                                      onClick={() =>
                                        onRemoveLine(
                                          index,
                                          "prefixes",
                                          lineIdx,
                                        )
                                      }
                                      aria-label="Remove prefix"
                                    >
                                      Remove
                                    </button>
                                  </div>
                                ),
                              )}
                              <button
                                type="button"
                                className="crawler-button small"
                                onClick={() => onAddLine(index, "prefixes")}
                              >
                                + Add prefix
                              </button>
                            </div>
                          )}
                          {step.type === "delete_range_regex" && (
                            <>
                              <label>
                                Start regex:
                                <input
                                  type="text"
                                  value={step.params?.start_regex || ""}
                                  onChange={(e) =>
                                    onUpdateStep(index, {
                                      params: {
                                        ...step.params,
                                        start_regex: e.target.value,
                                      },
                                    })
                                  }
                                  className="md-pipeline-param-input"
                                  placeholder="^## Section"
                                />
                              </label>
                              <label>
                                End regex:
                                <input
                                  type="text"
                                  value={step.params?.end_regex || ""}
                                  onChange={(e) =>
                                    onUpdateStep(index, {
                                      params: {
                                        ...step.params,
                                        end_regex: e.target.value,
                                      },
                                    })
                                  }
                                  className="md-pipeline-param-input"
                                  placeholder="^## "
                                />
                              </label>
                            </>
                          )}
                          {step.type === "strip_sections_by_heading" && (
                            <div className="md-pipeline-param-list">
                              <span className="md-pipeline-param-list-label">
                                Headings (add or remove, lower):
                              </span>
                              {(step.params?.headings || []).map(
                                (h, lineIdx) => (
                                  <div
                                    key={lineIdx}
                                    className="md-pipeline-param-list-row"
                                  >
                                    <input
                                      type="text"
                                      value={h}
                                      onChange={(e) =>
                                        onUpdateLine(
                                          index,
                                          "headings",
                                          lineIdx,
                                          e.target.value.trim().toLowerCase(),
                                        )
                                      }
                                      className="md-pipeline-param-input md-pipeline-param-list-input"
                                      placeholder="Section heading to strip"
                                    />
                                    <button
                                      type="button"
                                      className="crawler-button small"
                                      onClick={() =>
                                        onRemoveLine(
                                          index,
                                          "headings",
                                          lineIdx,
                                        )
                                      }
                                      aria-label="Remove line"
                                    >
                                      Remove
                                    </button>
                                  </div>
                                ),
                              )}
                              <button
                                type="button"
                                className="crawler-button small"
                                onClick={() => onAddLine(index, "headings")}
                              >
                                + Add line
                              </button>
                            </div>
                          )}
                          {step.type === "replace_regex" && (
                            <>
                              <label>
                                Pattern:
                                <input
                                  type="text"
                                  value={step.params?.pattern || ""}
                                  onChange={(e) =>
                                    onUpdateStep(index, {
                                      params: {
                                        ...step.params,
                                        pattern: e.target.value,
                                      },
                                    })
                                  }
                                  className="md-pipeline-param-input"
                                />
                              </label>
                              <label>
                                Replacement:
                                <input
                                  type="text"
                                  value={step.params?.replacement || ""}
                                  onChange={(e) =>
                                    onUpdateStep(index, {
                                      params: {
                                        ...step.params,
                                        replacement: e.target.value,
                                      },
                                    })
                                  }
                                  className="md-pipeline-param-input"
                                />
                              </label>
                            </>
                          )}
                          {step.type === "wrap_indented_code" && (
                            <>
                              <label>
                                Language (optional):
                                <input
                                  type="text"
                                  value={step.params?.language || ""}
                                  onChange={(e) =>
                                    onUpdateStep(index, {
                                      params: {
                                        ...step.params,
                                        language: e.target.value,
                                      },
                                    })
                                  }
                                  className="md-pipeline-param-input"
                                  placeholder="e.g. swift"
                                />
                              </label>
                              <label>
                                Min block lines:
                                <input
                                  type="number"
                                  min="1"
                                  value={step.params?.min_block_lines ?? 2}
                                  onChange={(e) =>
                                    onUpdateStep(index, {
                                      params: {
                                        ...step.params,
                                        min_block_lines: Number.isNaN(
                                          parseInt(e.target.value, 10),
                                        )
                                          ? 1
                                          : parseInt(e.target.value, 10),
                                      },
                                    })
                                  }
                                  className="md-pipeline-param-input"
                                />
                              </label>
                            </>
                          )}
                          {(step.type === "strip_meta_block" ||
                            step.type === "normalize_whitespace") &&
                            (() => {
                              const meta = MD_STEP_TYPES_META.find(
                                (m) => m.type === step.type,
                              );
                              if (!meta)
                                return (
                                  <span className="md-pipeline-step-no-params">
                                    No parameters
                                  </span>
                                );
                              return (
                                <div className="md-pipeline-step-desc-example">
                                  <p className="md-pipeline-step-desc-example-desc">
                                    {meta.description}
                                  </p>
                                  <p className="md-pipeline-step-desc-example-example">
                                    <strong>Example:</strong> {meta.example}
                                  </p>
                                </div>
                              );
                            })()}

        </>
      );
    }
