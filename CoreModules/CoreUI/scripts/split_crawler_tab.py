"""Generate crawlerTab/ modules from CrawlerTab.jsx (one-off split helper)."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "components"
OUT = SRC / "crawlerTab"
lines = (SRC / "CrawlerTab.jsx").read_text(encoding="utf-8").splitlines(keepends=True)


def sl(a: int, b: int) -> str:
    return "".join(lines[a - 1 : b])


def w(name: str, content: str) -> None:
    (OUT / name).write_text(content, encoding="utf-8")
    print(f"{name}: {len(content.splitlines())} lines")


# --- constants.js ---
c = sl(41, 145)
c = c.replace("const MD_STEP_TYPES_META", "export const MD_STEP_TYPES_META", 1)
c = c.replace("const SECTION_TABS", "export const SECTION_TABS", 1)
c = c.replace("const CREATE_COLLECTION_LIVE_ID", "export const CREATE_COLLECTION_LIVE_ID", 1)
c = c.replace(
    "const CREATE_COLLECTION_POLL_INTERVAL_MS",
    "export const CREATE_COLLECTION_POLL_INTERVAL_MS",
    1,
)
w("constants.js", c)

# --- helpers.js ---
helpers = """export function formatDate(dateStr) {
  if (!dateStr) return "Never";
  try {
    const date = new Date(dateStr);
    return date.toLocaleString();
  } catch {
    return dateStr;
  }
}

"""
switch_block = sl(757, 777)
switch_block = switch_block.replace("  const getDefaultParamsForStepType = (type) => {\n", "")
switch_block = switch_block.replace("  };\n", "")
helpers += "export function getDefaultParamsForStepType(type) {\n" + switch_block + "}\n\n"
helpers += """export function getMdPreviewText(previewResult) {
  return previewResult?.processed_md || "";
}

export function getMdPreviewSize(previewResult) {
  return new Blob([getMdPreviewText(previewResult)]).size;
}

"""
fmt = sl(872, 876).replace(
    "  const formatMdPreviewSize = (bytes) => {",
    "export function formatMdPreviewSize(bytes) {",
)
helpers += fmt + "\n\n"
export_fn = sl(878, 893)
export_fn = export_fn.replace(
    "  const handleExportMdPreview = () => {",
    "export function exportMdPreview(previewResult, pipelinePreviewFilename) {",
)
export_fn = export_fn.replace(
    "    const text = getMdPreviewText();",
    "  const text = getMdPreviewText(previewResult);",
)
export_fn = export_fn.replace("    ", "  ")
helpers += export_fn
w("helpers.js", helpers)

print("Generated constants + helpers")
