import React from "react";
import ActionableError from "../ActionableError";
import MdPipelineAddStepModal from "./MdPipelineAddStepModal";
import MdPipelineStepCard from "./MdPipelineStepCard";
import { t } from "../../services/i18n.js";

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
  onRetryPipeline,
}) {
  return (
    <div className="md-pipeline-section">
      <h3>{t("crawler.md_pipeline.title")}</h3>
      {pipelineError && (
        <ActionableError error={pipelineError} onRetry={onRetryPipeline} />
      )}
          <div className="md-pipeline-toolbar" data-tour="crawler-pipeline-select">
            <label className="indexer-select-label">
              {t("crawler.md_pipeline.pipeline_label")}
              <select
                value={selectedPipelineName}
                onChange={(e) => setSelectedPipelineName(e.target.value)}
                aria-label={t("crawler.md_pipeline.select_pipeline_aria")}
                disabled={pipelineLoading}
                className="coreui-select coreui-select--dense"
              >
                {pipelineList.length === 0 && (
                  <option value="">{t("crawler.md_pipeline.no_pipelines")}</option>
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
              {t("crawler.md_pipeline.create_pipeline")}
            </button>
            <button
              type="button"
              className="crawler-button primary"
              onClick={onSavePipeline}
              disabled={
                pipelineSaving || !selectedPipelineName || pipelineLoading
              }
            >
              {pipelineSaving ? t("crawler.md_pipeline.saving") : t("common.save")}
            </button>
            {pipelineSaveToast && (
              <span className="md-pipeline-toast" role="status">
                {t("crawler.md_pipeline.saved_toast")}
              </span>
            )}
            <label className="indexer-select-label md-pipeline-preview-source">
              {t("crawler.md_pipeline.preview_source")}
              <select
                value={pipelinePreviewSourceId}
                onChange={(e) => setPipelinePreviewSourceId(e.target.value)}
                aria-label={t("crawler.md_pipeline.preview_source_aria")}
                disabled={pipelinePreviewSourcesLoading}
                className="coreui-select coreui-select--dense"
              >
                {pipelinePreviewSources.length === 0 &&
                  !pipelinePreviewSourcesLoading && (
                    <option value="">{t("crawler.md_pipeline.no_sources")}</option>
                  )}
                {pipelinePreviewSources.map((s) => (
                  <option key={s.id} value={s.id}>
                    {t("crawler.md_pipeline.source_option", {
                      id: s.id,
                      count: s.page_count,
                    })}
                  </option>
                ))}
              </select>
            </label>
            <label className="indexer-select-label md-pipeline-preview-file">
              {t("crawler.md_pipeline.preview_file")}
              <select
                value={pipelinePreviewFilename}
                onChange={(e) => setPipelinePreviewFilename(e.target.value)}
                aria-label={t("crawler.md_pipeline.preview_file_aria")}
                className="coreui-select coreui-select--dense"
                disabled={
                  pipelinePreviewFilesLoading || !pipelinePreviewSourceId
                }
              >
                {pipelinePreviewFiles.length === 0 &&
                  !pipelinePreviewFilesLoading && (
                    <option value="">{t("crawler.md_pipeline.no_files")}</option>
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
              title={t("crawler.md_pipeline.preview_hint")}
            >
              {previewLoading
                ? t("crawler.md_pipeline.preview_loading")
                : t("crawler.md_pipeline.preview_btn")}
            </button>
            <button
              type="button"
              className="crawler-button"
              onClick={onDeletePipeline}
              disabled={!selectedPipelineName || pipelineLoading}
              title={t("crawler.md_pipeline.delete_hint")}
            >
              {t("crawler.md_pipeline.delete_pipeline")}
            </button>
          </div>

          {pipelineLoading ? (
            <div className="loading">{t("crawler.md_pipeline.loading")}</div>
          ) : (
            <>
              <div
                className="md-pipeline-steps"
                role="list"
                aria-label={t("crawler.md_pipeline.steps_aria")}
                data-tour="crawler-pipeline-steps"
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
                  {t("crawler.md_pipeline.add_step")}
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
