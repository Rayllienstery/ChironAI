import { useMemo } from 'react';
import '../styles/components/PipelineCiDiagram.css';

function getProxyPipelineSteps(data) {
  const defs = data?.pipeline_definition?.proxy?.steps;
  if (!Array.isArray(defs)) return [];
  return defs
    .filter((s) => s && typeof s === 'object' && s.id)
    .map((s) => ({
      id: String(s.id),
      label: String(s.title || s.label || s.id),
      hint: String(s.description || s.hint || ''),
    }));
}

/**
 * @param {Record<string, unknown>} data merged server snapshot + optional UI draft overrides
 */
export function computePipelineActive(data) {
  const env = data.env && typeof data.env === 'object' ? data.env : {};
  const globalWeb =
    env.web_interaction_globally_enabled === undefined ? true : Boolean(env.web_interaction_globally_enabled);
  const webMaster = Boolean(data.web_interaction_enabled) && globalWeb;
  const ragOn = Boolean(data.rag_collection_configured);
  const skillsActive = Boolean(data.skills_enabled !== false);
  const mergedDocs = Boolean(data.fetch_web_knowledge);

  return {
    parse: true,
    rag: ragOn,
    hybrid: ragOn && Boolean(data.hybrid_sparse_enabled),
    rerank: ragOn && Boolean(data.rerank_for_rag),
    context: ragOn,
    skills: skillsActive,
    merged_docs: mergedDocs,
    web_supplement: webMaster,
    github: mergedDocs,
    web: webMaster,
    kw_trigger: webMaster && data.web_interaction_on_keywords !== false,
    fw_trigger: webMaster && data.web_interaction_on_low_confidence_framework !== false,
    news: webMaster && Boolean(env.ddg_news),
    excerpt: webMaster && Boolean(env.fetch_page),
    wiki: webMaster && Boolean(env.wikipedia),
  };
}

function JobPill({ step, isActive }) {
  const className = isActive
    ? 'pipeline-ci__job pipeline-ci__job--catalog-active'
    : 'pipeline-ci__job pipeline-ci__job--catalog-inactive';

  return (
    <div className={className} title={step.hint || ''}>
      {step.label || step.id}
    </div>
  );
}

/**
 * @param {{
 *   data: Record<string, unknown> | null,
 *   title?: string,
 *   subtitle?: string,
 *   compact?: boolean,
 * }} props
 */
function PipelineCiDiagram({ data, title = 'LLM proxy pipeline', subtitle, compact }) {
  const activeMap = useMemo(() => (data ? computePipelineActive(data) : null), [data]);
  const visibleSteps = useMemo(() => getProxyPipelineSteps(data), [data]);

  const killSwitch =
    data &&
    Boolean(data.web_interaction_enabled) &&
    data.env &&
    data.env.web_interaction_globally_enabled === false;

  const envExtrasNeedSetup =
    data?.env &&
    (!data.env.ddg_news || !data.env.fetch_page || !data.env.wikipedia);

  const rootClass = compact ? 'pipeline-ci pipeline-ci--compact' : 'pipeline-ci';

  return (
    <section className={rootClass} aria-label={title}>
      <h3 className="pipeline-ci__title">{title}</h3>
      {subtitle ? <p className="pipeline-ci__subtitle">{subtitle}</p> : null}

      <div className="pipeline-ci__row-label">Pipeline stages</div>
      {!data || !activeMap ? (
        <p className="pipeline-ci__subtitle pipeline-ci__subtitle--inline">Loading pipeline...</p>
      ) : visibleSteps.length < 1 ? (
        <p className="pipeline-ci__subtitle pipeline-ci__subtitle--inline">Pipeline definition unavailable.</p>
      ) : (
        <div className="pipeline-ci__track">
          {visibleSteps.map((step, i) => (
            <div key={step.id} className="pipeline-ci__segment">
              {i > 0 ? <span className="pipeline-ci__connector" aria-hidden /> : null}
              <JobPill step={step} isActive={Boolean(activeMap[step.id])} />
            </div>
          ))}
        </div>
      )}

      {killSwitch ? (
        <div className="pipeline-ci__warn" role="status">
          Web interaction is enabled in settings but disabled on the server via{' '}
          <code>WEB_INTERACTION_ENABLED=0</code> (or off). The web stages stay inactive until the process env allows
          it.
        </div>
      ) : null}

      {data?.env ? (
        <>
          <div className="pipeline-ci__env">
            Global web (env): {data.env.web_interaction_globally_enabled === false ? 'off' : 'on'}. News / page excerpt /
            Wikipedia (saved UI <strong>or</strong> env): news {data.env.ddg_news ? 'on' : 'off'}, excerpt{' '}
            {data.env.fetch_page ? 'on' : 'off'}, Wikipedia {data.env.wikipedia ? 'on' : 'off'}.
          </div>
          {envExtrasNeedSetup ? (
            <p className="pipeline-ci__env-hint">
              Turn on <strong>+ DDG news</strong>, <strong>+ Page excerpt</strong>, or <strong>+ Wikipedia</strong>{' '}
              under <strong>Free web snippets</strong> below and save, or set{' '}
              <code>WEB_INTERACTION_DDG_NEWS=1</code>, <code>WEB_INTERACTION_FETCH_PAGE=1</code>,{' '}
              <code>WEB_INTERACTION_WIKIPEDIA=1</code> on the server process; either path enables the stage (restart only
              needed after env changes).
            </p>
          ) : null}
        </>
      ) : null}
    </section>
  );
}

export default PipelineCiDiagram;
