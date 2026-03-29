import React, { useState, useEffect, useCallback } from 'react';
import { getModelSettings, updateModelSettings } from '../services/api';
import './LlmProxyPipelinePanel.css';

const DEFAULTS = {
  proxy_tool_policy: 'normalize',
  proxy_stateful_guards: true,
  proxy_text_tool_retries: true,
};

/**
 * Standalone panel on the LLM Proxy tab: how much the proxy alters IDE ↔ Ollama behavior beyond RAG + template.
 * Persists the same keys as the backend expects in `proxy_settings` (merged on save).
 */
function LlmProxyPipelinePanel() {
  const [toolPolicy, setToolPolicy] = useState(DEFAULTS.proxy_tool_policy);
  const [statefulGuards, setStatefulGuards] = useState(DEFAULTS.proxy_stateful_guards);
  const [textRetries, setTextRetries] = useState(DEFAULTS.proxy_text_tool_retries);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [dirty, setDirty] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await getModelSettings();
      if (data) {
        const tp = data.proxy_tool_policy === 'passthrough' ? 'passthrough' : 'normalize';
        setToolPolicy(tp);
        setStatefulGuards(data.proxy_stateful_guards !== false);
        setTextRetries(data.proxy_text_tool_retries !== false);
      }
    } catch (e) {
      console.error('Failed to load proxy pipeline settings:', e);
    } finally {
      setLoading(false);
      setDirty(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const handleSave = async () => {
    setSaving(true);
    try {
      await updateModelSettings({
        proxy_tool_policy: toolPolicy,
        proxy_stateful_guards: statefulGuards,
        proxy_text_tool_retries: textRetries,
      });
      window.alert('Proxy pipeline settings saved.');
      await load();
    } catch (e) {
      console.error('Failed to save proxy pipeline settings:', e);
      window.alert('Failed to save proxy pipeline settings.');
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <div className="settings-section llm-proxy-pipeline-panel llm-proxy-pipeline-panel--loading">
        Loading proxy pipeline settings…
      </div>
    );
  }

  return (
    <section
      className="settings-section llm-proxy-pipeline-panel"
      aria-labelledby="llm-proxy-pipeline-heading"
    >
      <div className="llm-proxy-pipeline-panel__header">
        <h3 id="llm-proxy-pipeline-heading">IDE ↔ Ollama contract</h3>
        <p className="llm-proxy-pipeline-panel__lede">
          The proxy always builds the first <code>system</code> message from your prompt template, optional RAG context,
          and optional web supplement—those are intentional. The switches below control everything{' '}
          <em>else</em>: rewriting tool outputs, remembering edit outcomes between requests, extra hidden model calls,
          and overriding <code>tool_choice</code>. Upgrades default to <strong>Legacy</strong> so behavior does not
          change until you choose otherwise.
        </p>
        <p className="llm-proxy-pipeline-panel__lede">
          The three options below are separate levers (not the same choice under two names).{' '}
          <strong>Native tool output</strong> only affects native Ollama <code>tool_calls</code>; the checkboxes affect
          cross-request behavior and non-native / recovery paths. For a full pass-through profile closest to “what the
          model returned is what the IDE gets”: choose <strong>Passthrough</strong> and turn <strong>off</strong> both
          checkboxes. Defaults keep prior proxy behavior: Normalize + both on.
        </p>
        <p className="llm-proxy-pipeline-panel__lede">
          Each chat request records effective flags in <strong>Proxy Trace</strong> under{' '}
          <code>request.proxy_pipeline_policy</code>. Server env vars{' '}
          <code>LLM_PROXY_TOOL_POLICY</code>, <code>LLM_PROXY_STATEFUL_GUARDS</code>,{' '}
          <code>LLM_PROXY_TEXT_TOOL_RETRIES</code> override these saved values when set (for CI/automation).
        </p>
      </div>

      <div className="llm-proxy-pipeline-panel__controls">
        <div className="llm-proxy-pipeline-panel__field">
          <label htmlFor="proxy_tool_policy">Native tool output</label>
          <select
            id="proxy_tool_policy"
            value={toolPolicy}
            onChange={(e) => {
              setToolPolicy(e.target.value);
              setDirty(true);
            }}
          >
            <option value="normalize">Normalize edit tool arguments (legacy)</option>
            <option value="passthrough">Passthrough — arguments exactly as the model returned</option>
          </select>
          <p className="llm-proxy-pipeline-panel__help">
            <strong>Normalize</strong> post-processes edit-like native tool calls after Ollama: paths, ranges, merging
            content fields, multi-file heuristics—so what the IDE receives may differ from the raw model payload.{' '}
            <strong>Passthrough</strong> disables that rewrite and omits the extra multi-file append system hint before
            the last user message. Use passthrough when you want the IDE to see the same structure the model produced.
          </p>
        </div>

        <div className="llm-proxy-pipeline-panel__subcard">
          <label className="llm-proxy-pipeline-panel__checkbox-row">
            <input
              type="checkbox"
              checked={statefulGuards}
              onChange={(e) => {
                setStatefulGuards(e.target.checked);
                setDirty(true);
              }}
            />
            <span className="llm-proxy-pipeline-panel__checkbox-title">
              Stateful guards &amp; client contract tweaks
            </span>
          </label>
          <p className="llm-proxy-pipeline-panel__help">
            When <strong>on (legacy)</strong>, the proxy tracks recent successful applies and &quot;no edits&quot; loops,
            may short-circuit tool mode for duplicate user turns after success, can treat trailing noop tool results as
            completion, may promote Swift-related sessions from <code>tool_choice: none</code> to <code>auto</code>, and on
            the text-tool path injects a system line that discourages further edit tools after a success. When{' '}
            <strong>off</strong>, none of that runs—each request is evaluated without that cross-turn memory or{' '}
            <code>tool_choice</code> upgrade.
          </p>
        </div>

        <div className="llm-proxy-pipeline-panel__subcard">
          <label className="llm-proxy-pipeline-panel__checkbox-row">
            <input
              type="checkbox"
              checked={textRetries}
              onChange={(e) => {
                setTextRetries(e.target.checked);
                setDirty(true);
              }}
            />
            <span className="llm-proxy-pipeline-panel__checkbox-title">
              Text-tool / stream recovery retries (extra model calls)
            </span>
          </label>
          <p className="llm-proxy-pipeline-panel__help">
            Legacy path for tools-as-JSON-in-text (non-native or stream tool mode) may call the model again with stripped
            prompts to force valid edit JSON, run a full-file expansion retry, or send a minimal prompt when the first
            response was empty. Turning this <strong>off</strong> keeps only the first Ollama result for that branch
            (aside from compact error handling already in the proxy). Streaming tool mode still buffers the completion
            before emitting SSE chunks—that is a separate behavior, not removed here.
          </p>
        </div>
      </div>

      {dirty && (
        <p className="llm-proxy-pipeline-panel__dirty-hint" role="status">
          Unsaved changes — click Save pipeline settings.
        </p>
      )}

      <div className="llm-proxy-pipeline-panel__footer">
        <button type="button" className="save-button" onClick={handleSave} disabled={saving}>
          {saving ? 'Saving…' : 'Save pipeline settings'}
        </button>
        <p className="llm-proxy-pipeline-panel__footer-note">
          Model, prompt, RAG collection, and temperature are saved separately in <strong>Model Settings</strong> below.
        </p>
      </div>
    </section>
  );
}

export default LlmProxyPipelinePanel;
