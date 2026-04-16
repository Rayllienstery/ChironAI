import React, { useMemo } from 'react';
import { computePipelineActive } from './PipelineCiDiagram';
import '../styles/components/PipelineVerticalDiagram.css';

const VERTICAL_STEPS = [
  {
    id: 'parse',
    icon: 'input',
    label: 'Parse / gate',
    description: 'Validates and prepares the user message for downstream retrieval and supplements.',
  },
  {
    id: 'rag',
    icon: 'database',
    label: 'Vector RAG',
    description: 'Searches Qdrant for semantically relevant document chunks from your indexed collections.',
  },
  {
    id: 'hybrid',
    icon: 'merge_type',
    label: 'Hybrid sparse fusion',
    description: 'Combines dense and sparse vectors with reciprocal rank fusion for better recall.',
  },
  {
    id: 'rerank',
    icon: 'swap_vert',
    label: 'LLM rerank',
    description: 'Re-orders retrieved chunks using an LLM-based reranker for higher precision.',
  },
  {
    id: 'context',
    icon: 'construction',
    label: 'Build context',
    description: 'Assembles the final system context from RAG hits, ready for the model prompt.',
  },
  {
    id: 'skills',
    icon: 'extension',
    label: 'Agent skills',
    description: 'Loads skill packs and tool definitions when skill packs are enabled.',
  },
  {
    id: 'github',
    icon: 'cloud_download',
    label: 'Merged docs (GitHub)',
    description: 'Merges external documentation from GitHub repos indexed via fetch web knowledge.',
  },
  {
    id: 'web',
    icon: 'travel_explore',
    label: 'Web search (DDG)',
    description: 'Fetches DuckDuckGo search snippets as a live web supplement.',
  },
  {
    id: 'kw_trigger',
    icon: 'key',
    label: 'Freshness keyword trigger',
    description: 'Activates web search when the query contains release or version-related keywords.',
  },
  {
    id: 'fw_trigger',
    icon: 'help',
    label: 'Framework low-confidence trigger',
    description: 'Activates web search when RAG returns low-confidence results for framework questions.',
  },
  {
    id: 'news',
    icon: 'newspaper',
    label: '+ DDG news',
    description: 'Merges DuckDuckGo news results into the supplement pool.',
  },
  {
    id: 'excerpt',
    icon: 'description',
    label: '+ Page excerpt',
    description: 'Fetches and extracts a full web page excerpt from an allowed host.',
  },
  {
    id: 'wiki',
    icon: 'menu_book',
    label: '+ Wikipedia',
    description: 'Falls back to Wikipedia lookup when DDG returns no results.',
  },
];

function PipelineVerticalDiagram({ data }) {
  const activeMap = useMemo(() => (data ? computePipelineActive(data) : null), [data]);

  if (!activeMap) return null;

  return (
    <div className="pipeline-vert" role="list" aria-label="LLM proxy pipeline stages">
      {VERTICAL_STEPS.map((step, i) => {
        const active = Boolean(activeMap[step.id]);
        const isLast = i === VERTICAL_STEPS.length - 1;
        return (
          <div
            key={step.id}
            className={`pipeline-vert__item${active ? ' pipeline-vert__item--active' : ''}`}
            role="listitem"
          >
            <div className="pipeline-vert__rail">
              <span className="pipeline-vert__icon-wrap" aria-hidden="true">
                <span className={`material-symbols-outlined pipeline-vert__icon${active ? ' pipeline-vert__icon--on' : ''}`}>
                  {step.icon}
                </span>
              </span>
              {!isLast && <span className="pipeline-vert__line" />}
            </div>
            <div className="pipeline-vert__content">
              <span className="pipeline-vert__label">{step.label}</span>
              <span className="pipeline-vert__desc">{step.description}</span>
            </div>
          </div>
        );
      })}
    </div>
  );
}

export default PipelineVerticalDiagram;