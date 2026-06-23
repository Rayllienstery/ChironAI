# RAG Behavior and Configuration

This document summarizes how the RAG layer builds retrieval queries and how to tune
its behavior without changing code.

## Query normalization

The function `domain.services.retrieval.query_for_retrieval`:

- Strips fenced code blocks from the question.
- Removes generic filler phrases using `RETRIEVAL_STOP_WORDS`.
- Detects explicit iOS/Swift versions and adds release-related tokens.
- Biases queries toward UIKit or SwiftUI when those frameworks are mentioned.
- Expands queries with API symbols (PascalCase types) so that embedding is closer
  to relevant API documentation.

## Concept aliases

Concept/topic-specific biasing is implemented via `CONCEPT_ALIASES` in
`domain.services.retrieval`:

- Backed by `config.get_retrieval_dict("concept_aliases", ...)`.
- Keys: lowercased phrases to detect in the normalized question.
- Values: additional tokens appended to the retrieval query.

Hosts can adjust or extend these aliases in configuration (for example, to steer
retrieval toward Observation/observation tracking documentation) without adding
technology-specific conditionals to the code.

## Query intent and metadata-aware retrieval

The RAG layer infers a `QueryIntent` (see `domain.entities.rag.QueryIntent`) from
the raw user question:

- `symbol`: API-like symbol names (e.g. `UIViewController`, `handleEvents`).
- `framework`: high-level framework/technology (`uikit`, `swiftui`, `combine`, `observation`).
- `section_hint`: optional section preference (`discussion`, `overview`, `example`).

The helper `infer_query_intent` in `domain.services.retrieval` builds this struct.
`application.rag.use_cases.build_rag_context` passes the inferred intent into
`search_rag`, which:

- builds additional Qdrant filters via `extra_filter_symbol_equals` and
  `extra_filter_framework_equals` so that only chunks for the requested symbol
  and framework are considered when possible;
- adjusts document priority with `intent_match_priority` on top of
  `combined_doc_priority`, preferring chunks whose `payload.symbol`,
  `payload.framework`, and `payload.section` match the intent.

This keeps RAG focused on the symbol and framework from the user’s question
without introducing ad-hoc, technology-specific branches in the code.

## Trigger logic

The module `domain.services.rag_trigger` decides when to run RAG:

- Computes a trigger score from:
  - presence of RAG keywords,
  - CamelCase API names,
  - snake_case identifiers,
  - code blocks and code keywords,
  - API signatures and file extensions,
  - strong/weak technical phrases.
- Skips obvious short greetings when there are no technical signals.

The threshold `RAG_TRIGGER_THRESHOLD` and phrase lists are loaded from
`config` so they can be tuned per deployment.

## Proxy Settings Contract

The canonical precedence logic for proxy/RAG settings is centralized in
`application.rag.proxy_settings_contract`.

Contract table:

- `rag_collection`:
  1. request `collection_name`
  2. app setting `rag_collection`
  3. legacy `proxy_settings.rag_collection`
  4. default wiring / caller fallback
- `rerank_for_rag`:
  1. `proxy_settings.rerank_for_rag` when key exists
  2. config/env fallback (`get_proxy_rerank_enabled`)
- `hybrid_sparse_enabled`:
  1. `proxy_settings.hybrid_sparse_enabled` when key exists
  2. `retrieval.yaml` (`hybrid_sparse_enabled`)
- Web interaction flags:
  - master + trigger flags (`web_interaction_enabled`,
    `web_interaction_on_keywords`,
    `web_interaction_on_low_confidence_framework`) are resolved from
    `proxy_settings` when keys exist, otherwise explicit defaults.
  - feature toggles (`web_interaction_ddg_news`,
    `web_interaction_fetch_page`,
    `web_interaction_wikipedia`) are resolved from `proxy_settings` when keys
    exist, otherwise from environment-derived gates.

Observability:

- `/v1/chat/completions` trace now includes explicit `*_source` fields for
  key decisions (`collection_source`, `fetch_web_knowledge_source`).
- Pipeline preview endpoints expose `contract_sources` to make precedence
  decisions visible in WebUI.

