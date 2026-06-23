export function formatDate(dateStr) {
  if (!dateStr) return "Never";
  try {
    const date = new Date(dateStr);
    return date.toLocaleString();
  } catch {
    return dateStr;
  }
}

export function getDefaultParamsForStepType(type) {
    switch (type) {
      case "delete_lines_exact":
        return { lines: [], case_sensitive: false };
      case "delete_lines_containing":
        return { substrings: [], case_sensitive: false };
      case "delete_sentences_starting_with":
        return { prefixes: [] };
      case "delete_lines_regex":
      case "delete_regex_match":
        return { pattern: "" };
      case "delete_range_regex":
        return { start_regex: "", end_regex: "" };
      case "strip_sections_by_heading":
        return { headings: [] };
      case "wrap_indented_code":
        return { language: "swift", min_block_lines: 2 };
      case "replace_regex":
        return { pattern: "", replacement: "" };
      default:
        return {};
    }
}

export function getMdPreviewText(previewResult) {
  return previewResult?.processed_md || "";
}

export function getMdPreviewSize(previewResult) {
  return new Blob([getMdPreviewText(previewResult)]).size;
}

export function formatMdPreviewSize(bytes) {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
}

export function exportMdPreview(previewResult, pipelinePreviewFilename) {
  const text = getMdPreviewText(previewResult);
  const fallbackName = pipelinePreviewFilename || "pipeline-preview.md";
  const filename = fallbackName.toLowerCase().endsWith(".md")
    ? fallbackName
    : `${fallbackName}.md`;
  const blob = new Blob([text], { type: "text/markdown;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}
