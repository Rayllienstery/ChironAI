/**
 * Map Ollama model ids to bundled Lobe Icons (@lobehub/icons-static-svg) for provider logos.
 * Rules are ordered: first match wins; Hugging Face is a fallback when the id looks like an HF path.
 */
import anthropicUrl from '@lobehub/icons-static-svg/icons/anthropic.svg?url';
import ayaUrl from '@lobehub/icons-static-svg/icons/aya.svg?url';
import baichuanUrl from '@lobehub/icons-static-svg/icons/baichuan.svg?url';
import cohereUrl from '@lobehub/icons-static-svg/icons/cohere.svg?url';
import deepseekUrl from '@lobehub/icons-static-svg/icons/deepseek.svg?url';
import dolphinUrl from '@lobehub/icons-static-svg/icons/dolphin.svg?url';
import gemmaUrl from '@lobehub/icons-static-svg/icons/gemma.svg?url';
import googleUrl from '@lobehub/icons-static-svg/icons/google.svg?url';
import huggingfaceUrl from '@lobehub/icons-static-svg/icons/huggingface.svg?url';
import ibmUrl from '@lobehub/icons-static-svg/icons/ibm.svg?url';
import internlmUrl from '@lobehub/icons-static-svg/icons/internlm.svg?url';
import metaUrl from '@lobehub/icons-static-svg/icons/meta.svg?url';
import microsoftUrl from '@lobehub/icons-static-svg/icons/microsoft.svg?url';
import minimaxUrl from '@lobehub/icons-static-svg/icons/minimax.svg?url';
import mistralUrl from '@lobehub/icons-static-svg/icons/mistral.svg?url';
import moonshotUrl from '@lobehub/icons-static-svg/icons/moonshot.svg?url';
import nousresearchUrl from '@lobehub/icons-static-svg/icons/nousresearch.svg?url';
import nvidiaUrl from '@lobehub/icons-static-svg/icons/nvidia.svg?url';
import openaiUrl from '@lobehub/icons-static-svg/icons/openai.svg?url';
import perplexityUrl from '@lobehub/icons-static-svg/icons/perplexity.svg?url';
import phindUrl from '@lobehub/icons-static-svg/icons/phind.svg?url';
import qwenUrl from '@lobehub/icons-static-svg/icons/qwen.svg?url';
import rwkvUrl from '@lobehub/icons-static-svg/icons/rwkv.svg?url';
import snowflakeUrl from '@lobehub/icons-static-svg/icons/snowflake.svg?url';
import stabilityUrl from '@lobehub/icons-static-svg/icons/stability.svg?url';
import tiiUrl from '@lobehub/icons-static-svg/icons/tii.svg?url';
import upstageUrl from '@lobehub/icons-static-svg/icons/upstage.svg?url';
import voyageUrl from '@lobehub/icons-static-svg/icons/voyage.svg?url';
import yiUrl from '@lobehub/icons-static-svg/icons/yi.svg?url';
import zhipuUrl from '@lobehub/icons-static-svg/icons/zhipu.svg?url';

/** @type {Record<string, string>} */
export const OLLAMA_BRAND_ICON_URL = {
  anthropic: anthropicUrl,
  aya: ayaUrl,
  baichuan: baichuanUrl,
  cohere: cohereUrl,
  deepseek: deepseekUrl,
  dolphin: dolphinUrl,
  gemma: gemmaUrl,
  google: googleUrl,
  huggingface: huggingfaceUrl,
  ibm: ibmUrl,
  internlm: internlmUrl,
  meta: metaUrl,
  microsoft: microsoftUrl,
  minimax: minimaxUrl,
  mistral: mistralUrl,
  moonshot: moonshotUrl,
  nousresearch: nousresearchUrl,
  nvidia: nvidiaUrl,
  openai: openaiUrl,
  perplexity: perplexityUrl,
  phind: phindUrl,
  qwen: qwenUrl,
  rwkv: rwkvUrl,
  snowflake: snowflakeUrl,
  stability: stabilityUrl,
  tii: tiiUrl,
  upstage: upstageUrl,
  voyage: voyageUrl,
  yi: yiUrl,
  zhipu: zhipuUrl,
};

/** @type {Array<[RegExp, keyof typeof OLLAMA_BRAND_ICON_URL]>} */
const PRIMARY_BRAND_RULES = [
  [/deepseek/i, 'deepseek'],
  [/mixtral|mistral|devstral|codestral|magistral/i, 'mistral'],
  [/qwen/i, 'qwen'],
  [/gemma/i, 'gemma'],
  [/command[-_]?r|\bcohere\b/i, 'cohere'],
  [/\baya\b/i, 'aya'],
  [/granite|ibm\//i, 'ibm'],
  [/phi[-_]?[34]|(^|[-_/])orca\b|wizardlm/i, 'microsoft'],
  [/gpt-oss|openai|gpt-4|gpt-3/i, 'openai'],
  [/claude|anthropic/i, 'anthropic'],
  [/nous|hermes/i, 'nousresearch'],
  [/chatglm|glm[-._]?[0-9]|zhipu/i, 'zhipu'],
  [/baichuan/i, 'baichuan'],
  [/yi[-._]|01-ai|zeroone/i, 'yi'],
  [/internlm|internvl/i, 'internlm'],
  [/moonshot|kimi/i, 'moonshot'],
  [/minimax/i, 'minimax'],
  [/dolphin/i, 'dolphin'],
  [/falcon|tii\//i, 'tii'],
  [/rwkv/i, 'rwkv'],
  [/stablelm|stability/i, 'stability'],
  [/nemotron|nvidia/i, 'nvidia'],
  [/solar[-._]|upstage/i, 'upstage'],
  [/voyage/i, 'voyage'],
  [/perplexity/i, 'perplexity'],
  [/phind/i, 'phind'],
  [/arctic|snowflake/i, 'snowflake'],
  [/gemini|\/google\//i, 'google'],
  [/meta-llama|codellama|tinyllama|vicuna|(^|[-_/])llama\b/i, 'meta'],
];

/** @type {Array<[RegExp, keyof typeof OLLAMA_BRAND_ICON_URL]>} */
const FALLBACK_BRAND_RULES = [[/hf\.co\/|huggingface/i, 'huggingface']];

/**
 * @param {string | undefined | null} fullId
 * @returns {keyof typeof OLLAMA_BRAND_ICON_URL | null}
 */
export function getOllamaModelBrandKey(fullId) {
  const s = (fullId || '').trim();
  if (!s) return null;
  for (const [re, key] of PRIMARY_BRAND_RULES) {
    if (re.test(s)) return key;
  }
  for (const [re, key] of FALLBACK_BRAND_RULES) {
    if (re.test(s)) return key;
  }
  return null;
}

/**
 * Ollama POST /api/show JSON: `details` may contain `family` / `families`;
 * `model_info` may expose `general.architecture` (e.g. qwen35).
 * @param {unknown} payload
 * @returns {string | null}
 */
export function extractFamilyFromShowPayload(payload) {
  if (!payload || typeof payload !== 'object') return null;
  const o = /** @type {Record<string, unknown>} */ (payload);

  const nested = o.details;
  if (nested && typeof nested === 'object') {
    const d = /** @type {Record<string, unknown>} */ (nested);
    if (typeof d.family === 'string' && d.family.trim()) return d.family.trim();
    const fams = d.families;
    if (Array.isArray(fams) && fams.length > 0 && typeof fams[0] === 'string' && fams[0].trim()) {
      return fams[0].trim();
    }
  }

  if (typeof o.family === 'string' && o.family.trim()) return o.family.trim();
  const topFams = o.families;
  if (Array.isArray(topFams) && topFams.length > 0 && typeof topFams[0] === 'string' && topFams[0].trim()) {
    return topFams[0].trim();
  }

  const mi = o.model_info;
  if (mi && typeof mi === 'object') {
    const info = /** @type {Record<string, unknown>} */ (mi);
    const arch = info['general.architecture'];
    if (typeof arch === 'string' && arch.trim()) return arch.trim();
    for (const k of Object.keys(info)) {
      if (k.endsWith('.architecture')) {
        const v = info[k];
        if (typeof v === 'string' && v.trim()) return v.trim();
      }
    }
  }

  return null;
}

/** Map Ollama `family` / architecture strings (e.g. qwen35, llama) to Lobe slug keys. */
/** @type {Array<[RegExp, keyof typeof OLLAMA_BRAND_ICON_URL]>} */
const FAMILY_TO_BRAND_RULES = [
  [/qwen/i, 'qwen'],
  [/mistral|mixtral/i, 'mistral'],
  [/llama|meta\.?llama/i, 'meta'],
  [/gemma/i, 'gemma'],
  [/phi/i, 'microsoft'],
  [/deepseek/i, 'deepseek'],
  [/granite|ibm/i, 'ibm'],
  [/cohere/i, 'cohere'],
  [/falcon|tii/i, 'tii'],
  [/internlm/i, 'internlm'],
  [/baichuan/i, 'baichuan'],
  [/\byi\b|zeroone|01-ai/i, 'yi'],
  [/moonshot/i, 'moonshot'],
  [/minimax/i, 'minimax'],
  [/dolphin/i, 'dolphin'],
  [/rwkv/i, 'rwkv'],
  [/stablelm|stable[-_]diffusion/i, 'stability'],
  [/nemotron|nvidia/i, 'nvidia'],
  [/gpt-oss|gpt2|gptneo|openai/i, 'openai'],
  [/claude|anthropic/i, 'anthropic'],
  [/nous/i, 'nousresearch'],
  [/chatglm|glm/i, 'zhipu'],
  [/bert|roberta|distilbert/i, 'huggingface'],
];

/**
 * @param {string | undefined | null} family
 * @returns {keyof typeof OLLAMA_BRAND_ICON_URL | null}
 */
export function getOllamaModelBrandKeyFromFamily(family) {
  const s = (family || '').trim();
  if (!s) return null;
  for (const [re, key] of FAMILY_TO_BRAND_RULES) {
    if (re.test(s)) return key;
  }
  return null;
}
