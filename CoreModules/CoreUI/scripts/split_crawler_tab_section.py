"""Generate MdPipelineSection.jsx for crawlerTab split."""
from pathlib import Path
import textwrap

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "components"
OUT = SRC / "crawlerTab"
lines = (SRC / "CrawlerTab.jsx").read_text(encoding="utf-8").splitlines(keepends=True)


def sl(a: int, b: int) -> str:
    return "".join(lines[a - 1 : b])


toolbar = sl(1697, 1803)
steps_outer = sl(1808, 1812)
step_map_start = sl(1813, 1816)
step_map_end = sl(2260, 2270)
add_step_btn = sl(2262, 2270)

content = textwrap.dedent(
    """\
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
    """
)
content += toolbar
content += """
          {pipelineLoading ? (
            <div className="loading">Loading pipeline…</div>
          ) : (
            <>
              <div
                className="md-pipeline-steps"
                role="list"
                aria-label="Pipeline steps"
              >
"""
content += step_map_start
content += """                {(pipelineData.steps || []).map((step, index) => {
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
"""
content += step_map_end
content += """
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
"""

replacements = {
    "handleCreatePipeline": "onCreatePipeline",
    "handleSaveMdPipeline": "onSavePipeline",
    "handlePreviewMdPipeline": "onPreviewPipeline",
    "handleDeletePipelineClick": "onDeletePipeline",
    "setShowAddStepMenu(true)": "setShowAddStepMenu(true)",
    "handleAddMdStep": "onAddStep",
    "toggleMdStepExpanded": "onToggleStepExpanded",
    "handleChangeMdStepType": "onChangeStepType",
    "handleMoveMdStep": "onMoveStep",
    "handleRemoveMdStep": "onRemoveStep",
    "handleUpdateMdStep": "onUpdateStep",
    "updateMdStepLine": "onUpdateLine",
    "addMdStepLine": "onAddLine",
    "removeMdStepLine": "onRemoveLine",
}
for old, new in replacements.items():
    content = content.replace(old, new)

(OUT / "MdPipelineSection.jsx").write_text(content, encoding="utf-8")
print(f"MdPipelineSection.jsx: {len(content.splitlines())} lines")
