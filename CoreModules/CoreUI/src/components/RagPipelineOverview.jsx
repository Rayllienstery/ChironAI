import React, { useMemo } from 'react';
import RagTraceTimeline from './RagTraceTimeline';

/**
 * @typedef {'core' | 'option_on' | 'option_off'} OverviewBand
 * core — runs on every RAG request; option_on/off — toggles from Models / YAML.
 */

/**
 * Static pipeline map for the RAG / Qdrant tab: canonical order of stages,
 * not tied to a single request (see application/rag/use_cases.py + retrieval config).
 */
const RAG_PIPELINE_OVERVIEW_STEPS = [
  {
    id: 'query_prep',
    label: 'Query preparation',
    detail:
      'Turns the user message into a retrieval-ready form: optional query expansion / reformulations, noise trimming, and text shaped for the embedding model. Builds Qdrant filters from chunk metadata (e.g. doc_type, doc_scope) and, when intent is available, tighter filters such as symbol, framework, or section so search stays on relevant corpora.',
  },
  {
    id: 'embed_search_pass1',
    label: 'Embedding and first retrieval (pass 1)',
    detail:
      'Encodes the prepared query into a dense vector and runs the primary search against the bound Qdrant collection. When hybrid sparse retrieval is enabled (see RAG model settings and retrieval config), sparse keyword signals are combined with dense similarity—often fused with RRF—so lexical and semantic matches both contribute.',
  },
  {
    id: 'concept_expansion_pass2',
    label: 'Concept expansion and second pass (optional)',
    detail:
      'Runs only when concept_expansion_enabled is true in retrieval.yaml. Seeds are taken from the question and from top pass-1 hits; a configured concept_expansion_map expands those seeds into related terms. A secondary query is embedded and searched, then results are merged and deduplicated with pass 1 to broaden recall without losing the strongest initial hits.',
  },
  {
    id: 'metadata_rank',
    label: 'Metadata-aware ranking',
    detail:
      'Reorders the candidate chunk list using structured signals: document type priority, source scope, and alignment with detected intent (symbols, frameworks, headings). This is a deterministic layer on top of raw vector scores so API docs, guides, or framework-specific text surface in a sensible order before optional reranking.',
  },
  {
    id: 'rerank',
    label: 'Cross-encoder rerank (optional)',
    detail:
      'When rerank_for_rag is on in RAG model settings, a dedicated rerank model scores a capped set of top candidates against the full question and reorders them. This improves precision at the cost of an extra model call; the step is skipped entirely when reranking is disabled.',
  },
  {
    id: 'coverage_selection',
    label: 'Coverage-aware selection (optional)',
    detail:
      'Active when coverage_aware_selection is enabled. During finalize, instead of keeping only the top chunks by rerank score alone, the subset tries to span multiple extracted target concepts (symbols, concept aliases, coverage_extra_terms) so the context is less redundant—still bounded by final_context_k and later token limits.',
  },
  {
    id: 'coverage_metrics',
    label: 'Concept coverage report',
    detail:
      'After the candidate list is cut to final_k, the server compares heuristic target concepts from the question against the combined text of the selected hits (same notion as coverage-aware selection). It produces target_concepts, covered_concepts, missing_concepts, and coverage_ratio. No extra LLM call. These values feed optional gates, supplemental search, rag_quality and coverage_report in rag_metadata, and may add a short system note listing missing concepts.',
  },
  {
    id: 'coverage_gate',
    label: 'Coverage gate — widen chunk budget (optional)',
    detail:
      'When coverage_gate_enabled is true and there are target concepts, if coverage_ratio is below coverage_gate_min_percent the server increases final_k once—only by taking more chunks from the already reranked pool (up to coverage_gate_max_final_k). No second embedding of the main query.',
  },
  {
    id: 'coverage_supplemental',
    label: 'Supplemental retrieval for missing concepts (optional)',
    detail:
      'When coverage_retry_supplemental_search_enabled is true and coverage is still below the threshold with missing concepts, the server runs one additional embed+search using the question plus missing terms (limits: coverage_retry_top_k, coverage_retry_max_missing_terms), merges new hits into the pool, reranks again, and re-finalizes (chunk cap: coverage_retry_final_k or coverage_gate_max_final_k if unset).',
  },
  {
    id: 'context_assembly',
    label: 'Context assembly',
    detail:
      'Applies framework filtering (e.g. UIKit vs SwiftUI) when the question is explicit, then builds the RAG text block with per-chunk truncation to fit context_chunk_chars and context_total_chars. If structured_rag_context_enabled is on, the block gets ### Concepts / ### Evidence headings and numbered snippets [1], [2], …. The result is injected into the system message; response may also include rag_metadata.coverage_report and rag_metadata.rag_quality (e.g. failure_class: retrieval_gap when concepts are still missing).',
  },
  {
    id: 'answer_generation',
    label: 'Answer generation (downstream of Qdrant)',
    detail:
      'The LLM proxy assembles system + user messages (including the RAG block and any note about missing concepts), optional tools, and calls the chat model once per request. This stage is not Qdrant itself; it consumes retrieval output. Structured logs (e.g. rag_request_completed) can include rag_quality and coverage_ratio for observability.',
  },
];

/**
 * Merge static step defs with highlight band + sub-badges from saved model / retrieval flags
 * (same effective booleans as the server after load).
 * @param {Record<string, unknown>} s
 * @returns {Array<typeof RAG_PIPELINE_OVERVIEW_STEPS[0] & { overviewBand: OverviewBand, overviewBadges?: string[] }>}
 */
function buildOverviewStepsWithHighlights(s) {
  const hybrid = Boolean(s?.hybrid_sparse_enabled);
  const rerank = Boolean(s?.rerank_for_rag);
  const covSel = Boolean(s?.coverage_aware_selection);
  const concept = Boolean(s?.concept_expansion_enabled);
  const gate = Boolean(s?.coverage_gate_enabled);
  const retry = Boolean(s?.coverage_retry_supplemental_search_enabled);
  const structured = Boolean(s?.structured_rag_context_enabled);

  return RAG_PIPELINE_OVERVIEW_STEPS.map((step) => {
    /** @type {OverviewBand} */
    let overviewBand = 'core';
    /** @type {string[]} */
    const overviewBadges = [];

    switch (step.id) {
      case 'query_prep':
        overviewBand = 'core';
        break;
      case 'embed_search_pass1':
        overviewBand = 'core';
        if (hybrid) overviewBadges.push('Hybrid sparse on');
        break;
      case 'concept_expansion_pass2':
        overviewBand = concept ? 'option_on' : 'option_off';
        break;
      case 'metadata_rank':
        overviewBand = 'core';
        break;
      case 'rerank':
        overviewBand = rerank ? 'option_on' : 'option_off';
        break;
      case 'coverage_selection':
        overviewBand = covSel ? 'option_on' : 'option_off';
        break;
      case 'coverage_metrics':
        overviewBand = 'core';
        break;
      case 'coverage_gate':
        overviewBand = gate ? 'option_on' : 'option_off';
        break;
      case 'coverage_supplemental':
        overviewBand = retry ? 'option_on' : 'option_off';
        break;
      case 'context_assembly':
        overviewBand = 'core';
        if (structured) overviewBadges.push('Structured layout on');
        break;
      case 'answer_generation':
        overviewBand = 'core';
        break;
      default:
        overviewBand = 'core';
    }

    const out = { ...step, overviewBand };
    if (overviewBadges.length) out.overviewBadges = overviewBadges;
    return out;
  });
}

/**
 * @param {{ pipelineSettings?: Record<string, unknown> }} props
 */
export default function RagPipelineOverview({ pipelineSettings = {} }) {
  const steps = useMemo(() => buildOverviewStepsWithHighlights(pipelineSettings), [pipelineSettings]);
  return (
    <RagTraceTimeline
      steps={steps}
      title=""
      showDurations={false}
      overviewMode
    />
  );
}
