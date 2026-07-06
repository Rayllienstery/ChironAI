/** Contextual help slugs for LLM Proxy build fields (InfoButton / HelpPanel). */

export const BUILD_FIELD_HELP_REF = {
  provider_id: 'providers',
  model: 'providers',
  rag_enabled: 'rag-collections',
  rag_collection: 'rag-collections',
  code_only: 'rag-collections',
  context_chunk_chars: 'rag-collections#limits',
  context_total_chars: 'rag-collections#limits',
  rag_top_k: 'rag-collections#limits',
  temperature: 'builds#generation-params',
  top_p: 'builds#generation-params',
  num_ctx: 'builds#generation-params',
  num_predict: 'builds#generation-params',
  max_agent_steps: 'builds#capabilities',
  prompt_name: 'builds#prompts',
  use_prompt_template: 'builds#prompts',
  web_enabled: 'builds#web-interaction',
  fetch_web_knowledge: 'builds#capabilities',
  web_interaction_ddg_news: 'builds#web-interaction',
  web_interaction_fetch_page: 'builds#web-interaction',
  web_interaction_wikipedia: 'builds#web-interaction',
  private: 'builds',
  sse_streaming: 'builds',
  chat_think: 'builds#generation-params',
};

export const BUILD_SECTION_HELP_REF = {
  Basic: 'builds',
  RAG: 'rag-collections',
  Parameters: 'builds#generation-params',
  Web: 'builds#web-interaction',
  'Agent & Privacy': 'builds#prompts',
};

export function buildFieldHelpRef(fieldKey) {
  return BUILD_FIELD_HELP_REF[String(fieldKey || '')] || '';
}

export function buildSectionHelpRef(sectionLabel) {
  return BUILD_SECTION_HELP_REF[String(sectionLabel || '')] || '';
}
