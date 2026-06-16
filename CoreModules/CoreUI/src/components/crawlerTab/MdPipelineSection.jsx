import React from "react";
import MdPipelineAddStepModal from "./MdPipelineAddStepModal";
import MdPipelineStepCard from "./MdPipelineStepCard";

export default function MdPipelineSection({
  pipelineError,
  selectedPipelineName,
  setSelectedPipelineName,
  pipelineList,
  pipelineLoading,
  pipelineSaving,
  pipelineSaveToast,
  pipelinePreviewSourceId,
  setPipelinePreviewSourceId,
  pipelinePreviewSources,
  pipelinePreviewSourcesLoading,
  pipelinePreviewFilename,
  setPipelinePreviewFilename,
  pipelinePreviewFiles,
  pipelinePreviewFilesLoading,
  previewLoading,
  pipelineData,
  expandedMdSteps,
  showAddStepMenu,
  setShowAddStepMenu,
  onCreatePipeline,
  onSavePipeline,
  onPreviewPipeline,
  onDeletePipeline,
  onToggleStepExpanded,
  onChangeStepType,
  onMoveStep,
  onRemoveStep,
  onUpdateStep,
  onUpdateLine,
  onAddLine,
  onRemoveLine,
  onAddStep,
}) {
  return (
    <div className="md-pipeline-section">
      <h3>MD Pipeline</h3>
      {pipelineError && (
        <div className="crawler-error">{pipelineError}</div>
      )}
          <div className="md-pipeline-toolbar">
            <label className="indexer-select-label">
              Pipeline:
              <select
                value={selectedPipelineName}
                onChange={(e) => setSelectedPipelineName(e.target.value)}
                aria-label="Select pipeline"
                disabled={pipelineLoading}
                className="coreui-select coreui-select--dense"
              >
                {pipelineList.length === 0 && (
                  <option value="">— No pipelines —</option>
                )}
                {pipelineList.map((n) => (
                  <option key={n} value={n}>
                    {n}
                  </option>
                ))}
              </select>
            </label>
            <button
              type="button"
              className="crawler-button primary"
              onClick={onCreatePipeline}
            >
              Create a new pipeline
            </button>
            <button
              type="button"
              className="crawler-button primary"
              onClick={onSavePipeline}
              disabled={
                pipelineSaving || !selectedPipelineName || pipelineLoading
              }
            >
              {pipelineSaving ? "Saving…" : "Save"}
            </button>
            {pipelineSaveToast && (
              <span className="md-pipeline-toast" role="status">
                Saved.
              </span>
            )}
            <label className="indexer-select-label md-pipeline-preview-source">
              Preview source:
              <select
                value={pipelinePreviewSourceId}
                onChange={(e) => setPipelinePreviewSourceId(e.target.value)}
                aria-label="Source for pipeline preview"
                disabled={pipelinePreviewSourcesLoading}
                className="coreui-select coreui-select--dense"
              >
                {pipelinePreviewSources.length === 0 &&
                  !pipelinePreviewSourcesLoading && (
                    <option value="">— No sources —</option>
                  )}
                {pipelinePreviewSources.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.id} ({s.page_count} pages)
                  </option>
                ))}
              </select>
            </label>
            <label className="indexer-select-label md-pipeline-preview-file">
              Preview file:
              <select
                value={pipelinePreviewFilename}
                onChange={(e) => setPipelinePreviewFilename(e.target.value)}
                aria-label="File for pipeline preview"
                className="coreui-select coreui-select--dense"
                disabled={
                  pipelinePreviewFilesLoading || !pipelinePreviewSourceId
                }
              >
                {pipelinePreviewFiles.length === 0 &&
                  !pipelinePreviewFilesLoading && (
                    <option value="">— No files —</option>
                  )}
                {pipelinePreviewFiles.map((f) => (
                  <option key={f.filename} value={f.filename}>
                    {f.filename}
                  </option>
                ))}
              </select>
            </label>
            <button
              type="button"
              className="crawler-button"
              onClick={onPreviewPipeline}
              disabled={
                previewLoading ||
                !pipelinePreviewSourceId ||
                !pipelinePreviewFilename
              }
              title="Run this pipeline on the selected file"
            >
              {previewLoading ? "Preview…" : "Preview on file"}
            </button>
            <button
              type="button"
              className="crawler-button"
              onClick={onDeletePipeline}
              disabled={!selectedPipelineName || pipelineLoading}
              title="Delete this pipeline"
            >
              Delete this pipeline
            </button>
          </div>

          {pipelineLoading ? (
            <div className="loading">Loading pipeline…</div>
          ) : (
            <>
              <div
                className="md-pipeline-steps"
                role="list"
                aria-label="Pipeline steps"
              >
                {(pipelineData.steps || []).map((step, index) => {
                  const stepKey = step.id || `idx-${index}`;
                  const isExpanded = expandedMdSteps.has(stepKey);
                  return (
                    <MdPipelineStepCard
                      key={stepKey}
                      step={step}
                      index={index}
                      stepKey={stepKey}
                      isExpanded={isExpanded}
                      stepsLength={pipelineData.steps.length}
                      onToggleExpanded={onToggleStepExpanded}
                      onChangeStepType={onChangeStepType}
                      onMoveStep={onMoveStep}
                      onRemoveStep={onRemoveStep}
                      onUpdateStep={onUpdateStep}
                      onUpdateLine={onUpdateLine}
                      onAddLine={onAddLine}
                      onRemoveLine={onRemoveLine}
                    />
                  );
                })}
              </div>
              <div className="md-pipeline-add">
                <button
                  type="button"
                  className="crawler-button primary"
                  onClick={() => setShowAddStepMenu(true)}
                >
                  + Add step
                </button>
              </div>

              <MdPipelineAddStepModal
                open={showAddStepMenu}
                onClose={() => setShowAddStepMenu(false)}
                onAddStep={onAddStep}
              />
            </>
          )}
        </div>
      );
    }
