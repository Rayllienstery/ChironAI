import { mergePipelineSnapshot } from '../../hooks/useMergedPipelinePreview';
import { PARAMETER_PREFABS } from './constants';

export function mergeBuildDraftIntoPipelinePreview(snapshot, hybridSparse, rerankForRag, draft) {
  if (!snapshot || !draft) return null;
  const base = mergePipelineSnapshot(snapshot, hybridSparse, rerankForRag);
  const webOff = draft.web_enabled === false;
  const env = base.env && typeof base.env === 'object' ? { ...base.env } : {};
  if (webOff) {
    env.ddg_news = false;
    env.fetch_page = false;
    env.wikipedia = false;
  } else {
    env.ddg_news = Boolean(draft.web_interaction_ddg_news) || Boolean(env.ddg_news);
    env.fetch_page = Boolean(draft.web_interaction_fetch_page) || Boolean(env.fetch_page);
    env.wikipedia = Boolean(draft.web_interaction_wikipedia) || Boolean(env.wikipedia);
  }
  return {
    ...base,
    env,
    backend: 'rag_fusion',
    rag_collection_configured:
      Boolean(draft.rag_enabled) &&
      (Boolean(String(draft.rag_collection || '').trim()) || Boolean(base.rag_collection_configured)),
    fetch_web_knowledge: webOff ? false : Boolean(draft.fetch_web_knowledge),
    web_interaction_enabled: webOff ? false : Boolean(draft.web_interaction_enabled),
    web_interaction_on_keywords: draft.web_interaction_on_keywords !== false,
    web_interaction_on_low_confidence_framework:
      draft.web_interaction_on_low_confidence_framework !== false,
  };
}

export function getMatchingParameterPrefab(draft) {
  if (!draft) return null;
  return (
    PARAMETER_PREFABS.find((prefab) =>
      String(draft.num_ctx ?? '').trim() === String(prefab.values.num_ctx) &&
      String(draft.num_predict ?? '').trim() === String(prefab.values.num_predict) &&
      String(draft.max_agent_steps ?? '').trim() === String(prefab.values.max_agent_steps)
    ) || null
  );
}

export function emptyDraft() {
  return {
    id: '',
    display_name: '',
    backend: 'rag_fusion',
    provider_id: '',
    model: '',
    prompt_name: '',
    use_prompt_template: true,
    rag_enabled: true,
    skills_enabled: true,
    web_enabled: true,
    fetch_web_knowledge: false,
    web_interaction_enabled: false,
    web_interaction_on_keywords: true,
    web_interaction_on_low_confidence_framework: true,
    web_interaction_ddg_news: false,
    web_interaction_fetch_page: false,
    web_interaction_wikipedia: false,
    code_only: false,
    include_rag_metadata: true,
    reasoning_level: '',
    chat_think: false,
    sse_streaming: true,
    private: false,
    rag_collection: '',
    context_chunk_chars: '',
    context_total_chars: '',
    rag_top_k: '',
    temperature: '',
    top_p: '',
    num_predict: '65536',
    max_agent_steps: '',
    num_ctx: '',
  };
}

export function buildToDraft(b) {
  if (!b) return emptyDraft();
  const d = emptyDraft();
  Object.keys(d).forEach((k) => {
    if (b[k] !== undefined && b[k] !== null) {
      if (typeof b[k] === 'boolean') d[k] = b[k];
      else d[k] = String(b[k]);
    }
  });
  if (b.backend) d.backend = String(b.backend);
  if (!d.provider_id) d.provider_id = String(b.provider_id || '').trim();
  if (!d.model) d.model = String(b.model || b.ollama_model || '').trim();
  return d;
}

export function draftToPayload(draft) {
  const o = { ...draft };
  o.id = String(draft.id || '').trim();
  o.display_name = String(draft.display_name || '').trim() || o.id;
  o.backend = String(draft.backend || 'rag_fusion').toLowerCase();
  o.provider_id = String(draft.provider_id || '').trim();
  o.model = String(draft.model || '').trim();
  delete o.ollama_model;
  o.prompt_name = String(draft.prompt_name || '').trim();
  o.use_prompt_template = draft.use_prompt_template !== false;
  o.rag_enabled = Boolean(draft.rag_enabled);
  o.skills_enabled = Boolean(draft.skills_enabled);
  o.web_enabled = Boolean(draft.web_enabled);
  o.fetch_web_knowledge = Boolean(draft.fetch_web_knowledge);
  o.web_interaction_enabled = Boolean(draft.web_interaction_enabled);
  o.web_interaction_on_keywords = draft.web_interaction_on_keywords !== false;
  o.web_interaction_on_low_confidence_framework =
    draft.web_interaction_on_low_confidence_framework !== false;
  o.web_interaction_ddg_news = Boolean(draft.web_interaction_ddg_news);
  o.web_interaction_fetch_page = Boolean(draft.web_interaction_fetch_page);
  o.web_interaction_wikipedia = Boolean(draft.web_interaction_wikipedia);
  o.code_only = Boolean(draft.code_only);
  o.include_rag_metadata = Boolean(draft.include_rag_metadata);
  o.chat_think = Boolean(draft.chat_think);
  o.ide_mode = draft.use_prompt_template === false;
  o.sse_streaming = draft.sse_streaming !== false;
  o.private = Boolean(draft.private);
  o.reasoning_level = String(draft.reasoning_level || '').trim();
  o.rag_collection = String(draft.rag_collection || '').trim();
  [
    'temperature',
    'top_p',
    'num_predict',
    'max_agent_steps',
    'num_ctx',
    'context_chunk_chars',
    'context_total_chars',
    'rag_top_k',
  ].forEach((k) => {
    const s = String(draft[k] ?? '').trim();
    if (s === '') delete o[k];
    else if (
      k === 'max_agent_steps' ||
      k === 'num_predict' ||
      k === 'num_ctx' ||
      k === 'context_chunk_chars' ||
      k === 'context_total_chars' ||
      k === 'rag_top_k'
    )
      o[k] = parseInt(s, 10);
    else o[k] = parseFloat(s);
  });
  return o;
}
