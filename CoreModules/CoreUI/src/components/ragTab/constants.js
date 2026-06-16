export const ADVANCED_RETRIEVAL_OPTIONS = [
  {
    key: 'structured_rag_context_enabled',
    label: 'Structured RAG context (Concepts / Evidence)',
    cost: 'very_low',
    costLabel: 'Negligible cost',
    lines: [
      {
        tag: 'Pro',
        text: 'Clearer prompt layout for the model; good first toggle when answers feel “blobby”.',
      },
      {
        tag: 'Con',
        text: 'A few extra heading lines in the context; no extra Qdrant or embed calls.',
      },
    ],
  },
  {
    key: 'coverage_aware_selection',
    label: 'Coverage-aware chunk selection',
    cost: 'low',
    costLabel: 'Low cost',
    lines: [
      {
        tag: 'Pro',
        text: 'When the question implies several ideas, chunks span more distinct concepts instead of repeating one topic.',
      },
      {
        tag: 'Con',
        text: 'May swap in slightly lower-similarity snippets for breadth; tune with final_context_k in YAML.',
      },
    ],
  },
  {
    key: 'coverage_gate_enabled',
    label: 'Coverage gate (widen chunk budget)',
    cost: 'low',
    costLabel: 'Low when it runs',
    lines: [
      {
        tag: 'Pro',
        text: 'If inferred concepts are under-represented in the first cut, take more chunks from the same rerank pool—no second embed of the main query.',
      },
      {
        tag: 'Con',
        text: 'Larger context → more tokens and latency; only runs when heuristics find targets and coverage ratio is below the YAML threshold.',
      },
    ],
  },
  {
    key: 'concept_expansion_enabled',
    label: 'Concept expansion (second vector pass)',
    cost: 'medium',
    costLabel: 'Medium cost',
    lines: [
      {
        tag: 'Pro',
        text: 'Broadens recall for concurrency, APIs, and mapped synonyms (concept_expansion_map)—helps “near miss” queries.',
      },
      {
        tag: 'Con',
        text: 'Extra embed + Qdrant search per request when enabled; a loose map adds noise.',
      },
    ],
  },
  {
    key: 'coverage_retry_supplemental_search_enabled',
    label: 'Supplemental search for missing concepts',
    cost: 'high',
    costLabel: 'High cost',
    lines: [
      {
        tag: 'Pro',
        text: 'Last resort when coverage is still poor: another search biased with missing terms, then rerank again—fills holes the first pass missed.',
      },
      {
        tag: 'Con',
        text: 'Roughly doubles retrieval work when it fires (embed + search + rerank again). Use when quality gaps justify latency, not for every deployment.',
      },
    ],
  },
];

export const RAG_TABS = [
  { id: 'main', label: 'Main' },
  { id: 'collections', label: 'Collections' },
  { id: 'settings', label: 'Settings' },
];
