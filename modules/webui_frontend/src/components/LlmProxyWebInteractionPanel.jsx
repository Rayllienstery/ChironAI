import React, { useState, useEffect, useMemo } from 'react';
import { getModelSettings, updateModelSettings, getPipelinePreview } from '../services/api';
import PipelineCiDiagram from './PipelineCiDiagram';
import './LlmProxyTab.css';

const defaults = {
  fetch_web_knowledge: false,
  web_interaction_enabled: false,
  web_interaction_on_keywords: true,
  web_interaction_on_low_confidence_framework: true,
  web_interaction_ddg_news: false,
  web_interaction_fetch_page: false,
  web_interaction_wikipedia: false,
};

function LlmProxyWebInteractionPanel() {
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [settings, setSettings] = useState(defaults);
  const [pipelineSnapshot, setPipelineSnapshot] = useState(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [modelRes, pipeRes] = await Promise.allSettled([
          getModelSettings(),
          getPipelinePreview(),
        ]);
        if (cancelled) return;
        if (modelRes.status === 'fulfilled' && modelRes.value) {
          const modelData = modelRes.value;
          setSettings((prev) => ({
            ...prev,
            fetch_web_knowledge: Boolean(modelData.fetch_web_knowledge),
            web_interaction_enabled: Boolean(modelData.web_interaction_enabled),
            web_interaction_on_keywords:
              modelData.web_interaction_on_keywords !== false,
            web_interaction_on_low_confidence_framework:
              modelData.web_interaction_on_low_confidence_framework !== false,
            web_interaction_ddg_news: Boolean(modelData.web_interaction_ddg_news),
            web_interaction_fetch_page: Boolean(modelData.web_interaction_fetch_page),
            web_interaction_wikipedia: Boolean(modelData.web_interaction_wikipedia),
          }));
        } else if (modelRes.status === 'rejected') {
          console.error('Failed to load model settings', modelRes.reason);
        }
        if (pipeRes.status === 'fulfilled') {
          setPipelineSnapshot(pipeRes.value);
        } else {
          console.error('Failed to load pipeline preview', pipeRes.reason);
        }
      } catch (e) {
        console.error('Failed to load web interaction settings', e);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const pipelineMerged = useMemo(() => {
    if (!pipelineSnapshot) return null;
    const raw = pipelineSnapshot.env_raw || {};
    const baseEnv = pipelineSnapshot.env || {};
    return {
      ...pipelineSnapshot,
      fetch_web_knowledge: settings.fetch_web_knowledge,
      web_interaction_enabled: settings.web_interaction_enabled,
      web_interaction_on_keywords: settings.web_interaction_on_keywords,
      web_interaction_on_low_confidence_framework: settings.web_interaction_on_low_confidence_framework,
      env: {
        ...baseEnv,
        ddg_news: Boolean(settings.web_interaction_ddg_news) || Boolean(raw.ddg_news),
        fetch_page: Boolean(settings.web_interaction_fetch_page) || Boolean(raw.fetch_page),
        wikipedia: Boolean(settings.web_interaction_wikipedia) || Boolean(raw.wikipedia),
      },
    };
  }, [pipelineSnapshot, settings]);

  const handleChange = (field, value) => {
    setSettings((prev) => ({ ...prev, [field]: value }));
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      await updateModelSettings({
        fetch_web_knowledge: settings.fetch_web_knowledge,
        web_interaction_enabled: settings.web_interaction_enabled,
        web_interaction_on_keywords: settings.web_interaction_on_keywords,
        web_interaction_on_low_confidence_framework:
          settings.web_interaction_on_low_confidence_framework,
        web_interaction_ddg_news: settings.web_interaction_ddg_news,
        web_interaction_fetch_page: settings.web_interaction_fetch_page,
        web_interaction_wikipedia: settings.web_interaction_wikipedia,
      });
      try {
        setPipelineSnapshot(await getPipelinePreview());
      } catch (err) {
        console.error(err);
      }
      window.alert('Web interaction settings saved');
    } catch (e) {
      console.error(e);
      window.alert('Failed to save settings');
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return <div className="loading">Loading web interaction settings…</div>;
  }

  return (
    <div className="llm-proxy-web-panel settings-form">
      <PipelineCiDiagram
        data={pipelineMerged}
        title="Proxy request pipeline"
        subtitle="Top row: every stage the stack supports. Bottom row: what is armed now (green = on, gray = off). RAG hybrid/rerank follow the RAG tab unless you change them there."
      />
      <div className="settings-section">
        <h3>GitHub and merged RAG</h3>
        <p className="settings-intro">
          When enabled, the proxy resolves framework names in the user question, searches configured external
          collections, and can refresh markdown from public GitHub repos (unauthenticated API, about 60
          requests/hour per IP). This is separate from the snippet search below.
        </p>
        <div className="form-group checkbox-group">
          <label>
            <input
              type="checkbox"
              checked={settings.fetch_web_knowledge}
              onChange={(e) => handleChange('fetch_web_knowledge', e.target.checked)}
            />
            Fetch Web knowledge
          </label>
          <p className="setting-hint">
            Merge framework docs from the web (e.g. indexed GitHub markdown) with RAG context when triggers match your{' '}
            <code>external_docs_rag</code> configuration.
          </p>
        </div>
      </div>

      <div className="settings-section">
        <h3>Free web snippets (DuckDuckGo)</h3>
        <p className="settings-intro">
          Optional second block in the system prompt with search snippets—no API keys. Queries are cleaned and ranked
          (official docs preferred); results are cached briefly server-side. Use for release dates and freshness; RAG
          stays primary for APIs and code. Disable globally with <code>WEB_INTERACTION_ENABLED=0</code>, tune counts with{' '}
          <code>WEB_INTERACTION_MAX_RESULTS</code> (1–5), cache with <code>WEB_INTERACTION_CACHE_TTL_S</code>.
        </p>
        <p className="setting-hint">
          Optional env overrides (same effect as the checkboxes below if set to <code>1</code>):{' '}
          <code>WEB_INTERACTION_DDG_NEWS</code>, <code>WEB_INTERACTION_FETCH_PAGE</code>, <code>WEB_INTERACTION_WIKIPEDIA</code>.
          Region: <code>WEB_INTERACTION_DDG_REGION</code> or Cyrillic → <code>ru-ru</code>. See{' '}
          <code>CoreModules/WebInteraction/README.md</code>.
        </p>
        <div className="form-group checkbox-group">
          <label>
            <input
              type="checkbox"
              checked={settings.web_interaction_enabled}
              onChange={(e) => handleChange('web_interaction_enabled', e.target.checked)}
            />
            Enable web snippet supplement
          </label>
        </div>
        <div className="form-group checkbox-group">
          <label>
            <input
              type="checkbox"
              checked={settings.web_interaction_on_keywords}
              onChange={(e) => handleChange('web_interaction_on_keywords', e.target.checked)}
              disabled={!settings.web_interaction_enabled}
            />
            Run when the question looks like a release / version question (e.g. “latest”, “when was it released”,
            iOS N)
          </label>
        </div>
        <div className="form-group checkbox-group">
          <label>
            <input
              type="checkbox"
              checked={settings.web_interaction_on_low_confidence_framework}
              onChange={(e) =>
                handleChange('web_interaction_on_low_confidence_framework', e.target.checked)
              }
              disabled={!settings.web_interaction_enabled}
            />
            When the question names a framework (SwiftUI, UIKit, …) and RAG best score is below the confidence
            threshold
          </label>
        </div>

        <h4 className="settings-subsection-title">Optional web extras</h4>
        <p className="setting-hint">
          These extend the DDG snippet block. Page excerpt uses a strict allowlist (<code>developer.apple.com</code>,{' '}
          <code>swift.org</code>). Wikipedia runs only when DDG returns no snippets and the trigger is the freshness
          (keywords) path.
        </p>
        <div className="form-group checkbox-group">
          <label>
            <input
              type="checkbox"
              checked={settings.web_interaction_ddg_news}
              onChange={(e) => handleChange('web_interaction_ddg_news', e.target.checked)}
              disabled={!settings.web_interaction_enabled}
            />
            Merge DDG news (freshness-style questions)
          </label>
        </div>
        <div className="form-group checkbox-group">
          <label>
            <input
              type="checkbox"
              checked={settings.web_interaction_fetch_page}
              onChange={(e) => handleChange('web_interaction_fetch_page', e.target.checked)}
              disabled={!settings.web_interaction_enabled}
            />
            Fetch one allowed-host page excerpt for the top result
          </label>
        </div>
        <div className="form-group checkbox-group">
          <label>
            <input
              type="checkbox"
              checked={settings.web_interaction_wikipedia}
              onChange={(e) => handleChange('web_interaction_wikipedia', e.target.checked)}
              disabled={!settings.web_interaction_enabled}
            />
            Wikipedia fallback when DDG has no snippets
          </label>
        </div>
      </div>

      <div className="form-actions">
        <button type="button" className="btn-primary" onClick={handleSave} disabled={saving}>
          {saving ? 'Saving…' : 'Save web interaction settings'}
        </button>
      </div>
    </div>
  );
}

export default LlmProxyWebInteractionPanel;
