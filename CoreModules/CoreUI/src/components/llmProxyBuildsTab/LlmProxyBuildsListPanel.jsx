import React from 'react';
import CoreUIButton from '../CoreUIButton';
import CoreUIModal from '../CoreUIModal';

export default function LlmProxyBuildsListPanel({
  urls,
  err,
  saving,
  load,
  openNew,
  draft,
  builds,
  rowBusy,
  detailId,
  openDetails,
  closeDetails,
  openEdit,
  openDetailModal,
  deleteBuild,
  setOpenMenuModel,
  openMenuModel,
  modelMenuRootRef,
  detailModalBuild,
  closeDetailModal,
}) {
  return (
    <>
      <p className="settings-intro">
        Each build is a stable <code>model</code> id for <code>POST /v1/chat/completions</code>. The same builds appear
        on <code>GET /v1/models</code> on the main server.
      </p>
      {urls.main && (
        <section className="app-default-card llm-proxy-section-gap">
          <div className="dashboard-card-header">
            <h3>OpenAI list endpoints</h3>
          </div>
          <ul className="settings-instructions llm-proxy-instructions-list">
            {urls.main && (
              <li>
                Main: <code>{urls.main}</code>
              </li>
            )}
          </ul>
        </section>
      )}

      {err && (
        <div className="dashboard-card-error llm-proxy-section-gap-sm" role="alert">
          {err}
        </div>
      )}

      <div className="dashboard-card-actions llm-proxy-section-gap">
        <CoreUIButton variant="primary" onClick={load} disabled={saving}>
          Refresh
        </CoreUIButton>
        <CoreUIButton variant="primary" onClick={openNew} disabled={saving || draft}>
          New build
        </CoreUIButton>
      </div>

      <section className="app-default-card">
        <div className="dashboard-card-header">
          <h3>Builds</h3>
        </div>
        {builds.length === 0 && <p className="dashboard-card-muted">No builds yet. Create one to use as API model id.</p>}
        {builds.length > 0 && (
          <div className="llm-proxy-builds-list" role="list" aria-label="LLM Proxy builds">
            {builds.map((b) => {
              const name = b.id || '';
              const busy = rowBusy[name];
              const hasIssues = Array.isArray(b.issues) && b.issues.length > 0;
              const det = detailId === name;
              return (
                <div
                  key={name}
                  className={`llm-proxy-build-row${hasIssues ? ' llm-proxy-build-row--has-issues' : ''}`}
                  role="listitem"
                >
                  <div className="llm-proxy-build-row-header">
<div className="llm-proxy-build-main">
                      <div className="llm-proxy-build-title">
                        <span
                          className={`llm-proxy-build-issue-icon material-symbols-outlined${hasIssues ? ' llm-proxy-build-issue-icon--on' : ''}`}
                          aria-hidden="true"
                          title={hasIssues ? b.issues.join('\n') : 'No issues'}
                        >
                          {hasIssues ? 'error' : 'check_circle'}
                        </span>
                        <code title={name}>{name}</code>
                        {b.display_name && b.display_name !== b.id ? (
                          <span className="llm-proxy-build-display-name">{b.display_name}</span>
                        ) : null}
                      </div>
                      <div className="llm-proxy-build-basic-info">
                        <span className="llm-proxy-build-basic-item">
                          <span className="material-symbols-outlined" aria-hidden="true">hub</span>
                          Provider: <code>{b.provider_id || '—'}</code>
                        </span>
                        <span className="llm-proxy-build-basic-item">
                          <span className="material-symbols-outlined" aria-hidden="true">smart_toy</span>
                          Model: <code>{b.model || b.ollama_model || '—'}</code>
                        </span>
                      </div>
                    </div>

                    <div className="llm-proxy-build-actions">
                      <button
                        type="button"
                        className="llm-proxy-build-details-btn"
                        disabled={busy}
                        onClick={() => openDetailModal(b)}
                      >
                        <span className="material-symbols-outlined" aria-hidden="true">description</span>
                        Details
                      </button>
                      <div
                        className="llm-proxy-build-menu-root"
                        ref={openMenuModel === name ? modelMenuRootRef : null}
                      >
                        <button
                          type="button"
                          className="llm-proxy-build-menu-trigger"
                          aria-haspopup="menu"
                          aria-expanded={openMenuModel === name}
                          aria-label={`Actions for ${name}`}
                          disabled={busy}
                          onClick={() =>
                            setOpenMenuModel((cur) => (cur === name ? null : name))
                          }
                        >
                          <span className="material-symbols-outlined" aria-hidden="true">
                            more_vert
                          </span>
                        </button>
                        {openMenuModel === name ? (
                          <div className="llm-proxy-build-menu" role="menu">
                            <button
                              type="button"
                              className="llm-proxy-build-menu-item"
                              role="menuitem"
                              disabled={busy}
                              onClick={() => {
                                setOpenMenuModel(null);
                                det ? closeDetails() : openDetails(name);
                              }}
                            >
                              <span className="material-symbols-outlined" aria-hidden="true">
                                {det ? 'expand_less' : 'description'}
                              </span>
                              <span>{det ? 'Hide details' : 'Show details'}</span>
                            </button>
                            <button
                              type="button"
                              className="llm-proxy-build-menu-item"
                              role="menuitem"
                              disabled={busy || !!draft}
                              onClick={() => {
                                setOpenMenuModel(null);
                                openEdit(b);
                              }}
                            >
                              <span className="material-symbols-outlined" aria-hidden="true">
                                edit
                              </span>
                              <span>Edit</span>
                            </button>
                            <button
                              type="button"
                              className="llm-proxy-build-menu-item llm-proxy-build-menu-item--danger"
                              role="menuitem"
                              disabled={busy || saving}
                              onClick={() => {
                                setOpenMenuModel(null);
                                deleteBuild(name);
                              }}
                            >
                              <span className="material-symbols-outlined" aria-hidden="true">
                                delete_forever
                              </span>
                              <span>Delete</span>
                            </button>
                          </div>
                        ) : null}
                      </div>
                    </div>
                  </div>

                  {det ? (
                    <div className="llm-proxy-build-details">
                      <div className="llm-proxy-build-details-header">
                        <span className="llm-proxy-build-details-title" id={`llm-proxy-details-title-${name}`}>
                          Details
                        </span>
                        <button
                          type="button"
                          className="llm-proxy-build-details-close"
                          onClick={() => closeDetails()}
                          aria-label="Close details"
                        >
                          <span className="material-symbols-outlined" aria-hidden="true">
                            close
                          </span>
                        </button>
                      </div>
                      <div
                        className="llm-proxy-build-details-body"
                        role="region"
                        aria-labelledby={`llm-proxy-details-title-${name}`}
                      >
                        {hasIssues && (
                          <div className="dashboard-card-error llm-proxy-section-gap-sm">
                            {b.issues.map((i) => (
                              <div key={i}>{i}</div>
                            ))}
                          </div>
                        )}
                        <pre>{JSON.stringify(b, null, 2)}</pre>
                      </div>
                    </div>
                  ) : null}
                </div>
              );
            })}
          </div>
        )}
      </section>

      {detailModalBuild && (
        <CoreUIModal
          title={`Build details: ${detailModalBuild.id}`}
          onClose={closeDetailModal}
        >
          <div className="llm-proxy-detail-modal-body">
            {Array.isArray(detailModalBuild.issues) && detailModalBuild.issues.length > 0 && (
              <div className="dashboard-card-error llm-proxy-section-gap-sm">
                {detailModalBuild.issues.map((i) => (
                  <div key={i}>{i}</div>
                ))}
              </div>
            )}
            <div className="llm-proxy-build-params-list">
              {[
                {
                  label: 'Basic',
                  items: [
                    { key: 'provider_id', label: 'Provider', icon: 'hub', val: v => v },
                    { key: 'model', label: 'Model', icon: 'smart_toy', val: v => v || detailModalBuild.ollama_model },
                  ]
                },
                {
                  label: 'RAG',
                  items: [
                    { key: 'rag_enabled', label: 'RAG', icon: 'search', val: v => v ? 'enabled' : 'disabled' },
                    { key: 'rag_collection', label: 'Coll', icon: 'database', val: v => v },
                    { key: 'code_only', label: 'Code', icon: 'code', val: v => v ? 'on' : 'off' },
                  ]
                },
                {
                  label: 'Parameters',
                  items: [
                    { key: 'temperature', label: 'Temp', icon: 'thermostat', val: v => v },
                    { key: 'top_p', label: 'TopP', icon: 'filter_list', val: v => v },
                    { key: 'num_ctx', label: 'Ctx', icon: 'memory', val: v => v },
                    { key: 'num_predict', label: 'Pred', icon: 'data_object', val: v => v },
                    { key: 'max_agent_steps', label: 'Steps', icon: 'route', val: v => v },
                    { key: 'se_streaming', label: 'Stream', icon: 'stream', val: v => v === false ? 'off' : 'on' },
                    { key: 'chat_think', label: 'Think', icon: 'psychology', val: v => v ? 'on' : 'off' },
                  ]
                },
                {
                  label: 'Web',
                  items: [
                    { key: 'web_enabled', label: 'Web', icon: 'public', val: v => v ? 'on' : 'off' },
                    { key: 'fetch_web_knowledge', label: 'WebDocs', icon: 'cloud_download', val: v => v ? 'on' : 'off' },
                    { key: 'web_interaction_ddg_news', label: 'DDG', icon: 'travel_explore', val: v => v ? 'on' : 'off' },
                    { key: 'web_interaction_fetch_page', label: 'Fetch', icon: 'web', val: v => v ? 'on' : 'off' },
                    { key: 'web_interaction_wikipedia', label: 'Wiki', icon: 'menu_book', val: v => v ? 'on' : 'off' },
                  ]
                },
                {
                  label: 'Agent & Privacy',
                  items: [
                    { key: 'prompt_name', label: 'Prompt', icon: 'description', val: v => v },
                    { key: 'use_prompt_template', label: 'Agent', icon: 'code_blocks', val: v => v === false ? 'on' : 'off' },
                    { key: 'private', label: 'Priv', icon: 'visibility_off', val: v => v ? 'on' : 'off' },
                  ]
                }
              ].map(cat => {
                const visibleItems = cat.items.filter(p => {
                  const v = detailModalBuild[p.key];
                  const display = p.val(v);
                  return display !== null && display !== undefined && display !== '';
                });

                if (visibleItems.length === 0) return null;

                return (
                  <div key={cat.label} className="llm-proxy-build-param-section">
                    <div className="llm-proxy-build-param-section-title">{cat.label}</div>
                    {visibleItems.map(p => (
                      <div key={p.key} className="llm-proxy-build-param-item">
                        <div className="llm-proxy-build-param-label">
                          <span className="material-symbols-outlined" aria-hidden="true">{p.icon}</span>
                          <span>{p.label}</span>
                        </div>
                        <code className="llm-proxy-build-param-value">{p.val(detailModalBuild[p.key])}</code>
                      </div>
                    ))}
                  </div>
                );
              })}
            </div>
          </div>
        </CoreUIModal>
      )}

    </>
  );
}
