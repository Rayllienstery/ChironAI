import { t } from "../../services/i18n.js";

export const MD_STEP_TYPE_IDS = [
  "strip_meta_block",
  "delete_lines_exact",
  "delete_lines_containing",
  "delete_lines_regex",
  "delete_sentences_starting_with",
  "delete_range_regex",
  "delete_regex_match",
  "strip_sections_by_heading",
  "normalize_whitespace",
  "wrap_indented_code",
  "replace_regex",
  "reject_low_signal_body",
];

export function getMdStepTypeMeta(type) {
  return {
    type,
    title: t(`crawler.md_step.${type}.title`),
    description: t(`crawler.md_step.${type}.description`),
    example: t(`crawler.md_step.${type}.example`),
  };
}

export function getMdStepTypesMeta() {
  return MD_STEP_TYPE_IDS.map(getMdStepTypeMeta);
}

export const SECTION_TABS = [
  { id: "crawler", labelKey: "crawler.section.crawler" },
  { id: "md-pipeline", labelKey: "crawler.section.md_pipeline" },
];

export const CREATE_COLLECTION_LIVE_ID = "crawler-create-collection";
export const CREATE_COLLECTION_POLL_INTERVAL_MS = 333;
