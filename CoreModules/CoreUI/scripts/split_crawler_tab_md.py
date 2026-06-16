"""Generate MD pipeline components for crawlerTab split."""
from pathlib import Path
import textwrap

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "components"
OUT = SRC / "crawlerTab"
lines = (SRC / "CrawlerTab.jsx").read_text(encoding="utf-8").splitlines(keepends=True)


def sl(a: int, b: int) -> str:
    return "".join(lines[a - 1 : b])


def w(name: str, content: str) -> None:
    (OUT / name).write_text(content, encoding="utf-8")
    print(f"{name}: {len(content.splitlines())} lines")


# MdPipelineStepParams.jsx
params = textwrap.dedent(
    """\
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
    """
) + sl(1891, 2255)
params += "\n        </>\n      );\n    }\n"
params = params.replace("handleUpdateMdStep", "onUpdateStep")
params = params.replace("updateMdStepLine", "onUpdateLine")
params = params.replace("addMdStepLine", "onAddLine")
params = params.replace("removeMdStepLine", "onRemoveLine")
w("MdPipelineStepParams.jsx", params)

# MdPipelineStepCard.jsx
card = textwrap.dedent(
    """\
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
    """
) + sl(1817, 2259)
card += "\n      );\n    }\n"
card = card.replace("expandedMdSteps.has(stepKey)", "isExpanded")
card = card.replace("toggleMdStepExpanded(stepKey)", "onToggleExpanded(stepKey)")
card = card.replace("handleChangeMdStepType", "onChangeStepType")
card = card.replace("handleMoveMdStep", "onMoveStep")
card = card.replace("handleRemoveMdStep", "onRemoveStep")
# Replace inline params block with component
start_marker = "                      {isExpanded && (\n                        <div className=\"md-pipeline-step-params\">"
end_marker = "                        </div>\n                      )}"
start_idx = card.find(start_marker)
end_idx = card.find(end_marker)
if start_idx != -1 and end_idx != -1:
    before = card[: start_idx + len(start_marker)] + "\n"
    after = card[end_idx:]
    middle = """                          <MdPipelineStepParams
                            step={step}
                            index={index}
                            onUpdateStep={onUpdateStep}
                            onUpdateLine={onUpdateLine}
                            onAddLine={onAddLine}
                            onRemoveLine={onRemoveLine}
                          />
"""
    card = before + middle + after
card = card.replace("pipelineData.steps.length", "stepsLength")
w("MdPipelineStepCard.jsx", card)

# MdPipelineAddStepModal.jsx
add_modal = textwrap.dedent(
    """\
    import React from "react";
    import { MD_STEP_TYPES_META } from "./constants";

    export default function MdPipelineAddStepModal({ open, onClose, onAddStep }) {
      if (!open) return null;
      return (
    """
) + sl(2273, 2324)
add_modal += "\n      );\n    }\n"
add_modal = add_modal.replace("setShowAddStepMenu(false)", "onClose()")
add_modal = add_modal.replace("handleAddMdStep", "onAddStep")
w("MdPipelineAddStepModal.jsx", add_modal)

# MdPipelinePreviewModal.jsx
preview = textwrap.dedent(
    """\
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
    """
) + sl(2331, 2379)
preview += "\n      );\n    }\n"
preview = preview.replace("setPreviewResult(null)", "onClose()")
preview = preview.replace(
    "onClick={handleExportMdPreview}",
    "onClick={() => exportMdPreview(previewResult, pipelinePreviewFilename)}",
)
preview = preview.replace("getMdPreviewText()", "getMdPreviewText(previewResult)")
preview = preview.replace("getMdPreviewSize()", "getMdPreviewSize(previewResult)")
w("MdPipelinePreviewModal.jsx", preview)

print("Generated MD pipeline components")
