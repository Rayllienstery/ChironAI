import React from 'react';
import { CUSTOM_PARAMETER_PREFAB_NOTE } from './constants';

export default function LlmProxyWizardSteps({
  wizardStep,
  draft,
  setDraft,
  editingId,
  chatProviders,
  filteredModels,
  previewBusy,
  previewMsg,
  runPreview,
  applySelectedModelDefaults,
  parameterPrefabNote,
  applyParameterPrefab,
  buildModalPipelineData,
  buildModalHybrid,
  buildModalRerank,
  proxyDefaults,
}) {
  return (
            <div className="llm-proxy-wizard-content" key={wizardStep}>
            {/* ── Step 0: Basic Info ── */}
            {wizardStep === 0 && (
              <div className="llm-proxy-wizard-step-panel">
                <div className="llm-proxy-info-card">
                  <h3 className="llm-proxy-info-card-title">
                    <span className="llm-proxy-info-card-title-icon material-symbols-outlined" aria-hidden="true">info</span>
                    Name your build
                  </h3>
                  <div className="llm-proxy-info-card-body">
                    A <strong>build</strong> is a named configuration that API clients reference by the <code>model</code> field.
                    Think of it as a profile — each build wires up a specific provider/model pair, RAG settings, and behaviour so
                    you can switch between them instantly without changing client code.
                  </div>
                </div>

                <label className="coreui-form-field">
                  Build id (API model name)
                  <input
                    className="coreui-input"
                    value={draft.id}
                    onChange={(e) => setDraft({ ...draft, id: e.target.value })}
                    disabled={!!editingId}
                    placeholder="e.g. my-dev-build"
                  />
                  <span className="llm-proxy-param-card-hint">This is the <code>model</code> value clients send in API requests. Must be unique. Lowercase, hyphens ok.</span>
                </label>

                <label className="coreui-form-field">
                  Display name
                  <input
                    className="coreui-input"
                    value={draft.display_name}
                    onChange={(e) => setDraft({ ...draft, display_name: e.target.value })}
                    placeholder="Human-friendly name shown in the UI"
                  />
                  <span className="llm-proxy-param-card-hint">Optional. A readable label for the builds list. Falls back to the build id if empty.</span>
                </label>

                <div className="llm-proxy-info-card">
                  <h3 className="llm-proxy-info-card-title">
                    <span className="llm-proxy-info-card-title-icon material-symbols-outlined" aria-hidden="true">smart_toy</span>
                    Choose the provider model
                  </h3>
                  <div className="llm-proxy-info-card-body">
                    The selected provider model is the LLM that actually generates responses. The proxy sends it the assembled
                    prompt (system + RAG context + conversation).
                  </div>
                </div>

                <label className="coreui-form-field">
                  Provider
                  <select
                    className="coreui-select"
                    value={draft.provider_id}
                    onChange={(e) => {
                      const providerId = e.target.value;
                      setDraft((prev) => ({ ...(prev || {}), provider_id: providerId, model: '' }));
                    }}
                  >
                    <option value="">Select...</option>
                    {chatProviders.map((provider) => (
                      <option key={provider.provider_id} value={provider.provider_id}>
                        {provider.title || provider.provider_id}
                      </option>
                    ))}
                  </select>
                </label>

                <label className="coreui-form-field">
                  Model
                  <select
                    className="coreui-select"
                    value={draft.model}
                    onChange={(e) => {
                      const v = e.target.value;
                      setDraft((prev) => ({ ...(prev || {}), model: v }));
                      void applySelectedModelDefaults(v, String(draft.provider_id || '').trim());
                    }}
                  >
                    <option value="">Select…</option>
                    {filteredModels.map((m) => (
                      <option key={m.id} value={m.id}>
                        {m.name || m.id}
                      </option>
                    ))}
                  </select>
                </label>

                <div className="dashboard-card-actions">
                  <CoreUIButton variant="primary" disabled={previewBusy} onClick={runPreview}>
                    Check model
                  </CoreUIButton>
                  {previewMsg && <span className="dashboard-card-muted">{previewMsg}</span>}
                </div>

                <div className="llm-proxy-toggle-with-explanation">
                  <div className="llm-proxy-toggle-row">
                    <span className="llm-proxy-toggle-label">
                      <span className="llm-proxy-toggle-icon material-symbols-outlined" aria-hidden="true">psychology</span>
                      Provider think mode
                    </span>
                    <label className="coreui-switch">
                      <input
                        type="checkbox"
                        checked={!!draft.chat_think}
                        onChange={(e) => setDraft({ ...draft, chat_think: e.target.checked })}
                      />
                      <span aria-hidden="true"></span>
                    </label>
                  </div>
                  <p className="llm-proxy-toggle-explanation">
                    Enables extended "thinking" output for models that support it (e.g. DeepSeek-R1, QwQ). The model
                    produces a hidden reasoning chain before the final answer, improving quality on complex tasks.
                  </p>
                </div>

                <div className="llm-proxy-toggle-with-explanation">
                  <div className="llm-proxy-toggle-row">
                    <span className="llm-proxy-toggle-label">
                      <span className="llm-proxy-toggle-icon material-symbols-outlined" aria-hidden="true">stream</span>
                      Token-by-token SSE streaming
                    </span>
                    <label className="coreui-switch">
                      <input
                        type="checkbox"
                        checked={draft.sse_streaming !== false}
                        onChange={(e) => setDraft({ ...draft, sse_streaming: e.target.checked })}
                      />
                      <span aria-hidden="true"></span>
                    </label>
                  </div>
                    <p className="llm-proxy-toggle-explanation">
                      When on, tokens stream from the provider to the client one-by-one in real time. When off, the proxy
                      collects the full response first, then sends it as a single SSE burst — useful if streaming causes
                      incomplete tool calls or flaky clients.
                    </p>
                </div>
              </div>
            )}

            {/* ── Step 1: RAG ── */}
            {wizardStep === 1 && (
              <div className="llm-proxy-wizard-step-panel">
                <div className="llm-proxy-info-card">
                  <h3 className="llm-proxy-info-card-title">
                    <span className="llm-proxy-info-card-title-icon material-symbols-outlined" aria-hidden="true">search</span>
                    What is RAG and why does it matter?
                  </h3>
                  <div className="llm-proxy-info-card-body">
                    <strong>RAG (Retrieval-Augmented Generation)</strong> supercharges the AI with your own documents.
                    Instead of relying solely on the model's training data, RAG searches a vector database (Qdrant)
                    for relevant passages <em>before</em> generating a response, then injects them into the prompt.
                    <ul>
                      <li><strong>Accurate answers</strong> — the model cites your docs, not just its memory</li>
                      <li><strong>Up-to-date</strong> — works with docs added or changed today, not last year's training cut-off</li>
                      <li><strong>Domain-specific</strong> — private codebases, internal wikis, API docs — anything you index</li>
                      <li><strong>Reduced hallucinations</strong> — grounded context keeps the model honest</li>
                    </ul>
                    Without RAG, the model answers from general knowledge only. With RAG, it answers from <em>your</em> knowledge base.
                  </div>
                </div>

                <div className="llm-proxy-toggle-with-explanation llm-proxy-toggle-with-explanation--primary">
                  <div className="llm-proxy-toggle-row">
                    <span className="llm-proxy-toggle-label">
                      <span className="llm-proxy-toggle-icon material-symbols-outlined" aria-hidden="true">search</span>
                      Enable RAG for this build
                    </span>
                    <label className="coreui-switch">
                      <input
                        type="checkbox"
                        checked={!!draft.rag_enabled}
                        onChange={(e) => setDraft({ ...draft, rag_enabled: e.target.checked })}
                      />
                      <span aria-hidden="true"></span>
                    </label>
                  </div>
                  <p className="llm-proxy-toggle-explanation">
                    When enabled, every chat request will search your Qdrant collections for relevant context before
                    calling the LLM. Disable if you want a pure passthrough to the selected provider model with no document retrieval.
                  </p>
                </div>

                {draft.rag_enabled && (
                  <>
                    <div className="llm-proxy-rag-features">
                      <div className="llm-proxy-rag-feature">
                        <span className="llm-proxy-rag-feature-icon material-symbols-outlined" aria-hidden="true">database</span>
                        <span className="llm-proxy-rag-feature-text"><strong>Vector search</strong> — embeds the query and finds the closest document chunks by semantic similarity</span>
                      </div>
                      <div className="llm-proxy-rag-feature">
                        <span className="llm-proxy-rag-feature-icon material-symbols-outlined" aria-hidden="true">merge_type</span>
                        <span className="llm-proxy-rag-feature-text"><strong>Hybrid fusion</strong> — combines dense + sparse vectors with RRF for better recall (config in RAG / Qdrant)</span>
                      </div>
                      <div className="llm-proxy-rag-feature">
                        <span className="llm-proxy-rag-feature-icon material-symbols-outlined" aria-hidden="true">filter_alt</span>
                        <span className="llm-proxy-rag-feature-text"><strong>Smart filtering</strong> — auto-skips RAG for greetings and small talk; uses keyword triggers for technical questions</span>
                      </div>
                      <div className="llm-proxy-rag-feature">
                        <span className="llm-proxy-rag-feature-icon material-symbols-outlined" aria-hidden="true">rank</span>
                        <span className="llm-proxy-rag-feature-text"><strong>Reranking</strong> — optional LLM-based rerank of top candidates for precision (config in RAG / Qdrant)</span>
                      </div>
                    </div>

                    <label className="coreui-form-field llm-proxy-section-gap-sm">
                      RAG collection override
                      <input
                        className="coreui-input"
                        value={draft.rag_collection}
                        onChange={(e) => setDraft({ ...draft, rag_collection: e.target.value })}
                        placeholder="empty = server default"
                      />
                      <span className="llm-proxy-param-card-hint">Leave empty to use the server's default collection. Set a name to search a specific Qdrant collection for this build.</span>
                    </label>

                    <div className="coreui-form-grid-3">
                      <label className="coreui-form-field">
                        Context chunk chars
                        <input
                          className="coreui-input"
                          inputMode="numeric"
                          value={draft.context_chunk_chars}
                          onChange={(e) => setDraft({ ...draft, context_chunk_chars: e.target.value })}
                          placeholder="YAML default"
                        />
                        <span className="llm-proxy-param-card-hint">Max characters per retrieved chunk sent to the model.</span>
                      </label>
                      <label className="coreui-form-field">
                        Context total chars
                        <input
                          className="coreui-input"
                          inputMode="numeric"
                          value={draft.context_total_chars}
                          onChange={(e) => setDraft({ ...draft, context_total_chars: e.target.value })}
                          placeholder="YAML default"
                        />
                        <span className="llm-proxy-param-card-hint">Total RAG context budget across all chunks.</span>
                      </label>
                      <label className="coreui-form-field">
                        RAG top_k
                        <input
                          className="coreui-input"
                          inputMode="numeric"
                          value={draft.rag_top_k}
                          onChange={(e) => setDraft({ ...draft, rag_top_k: e.target.value })}
                          placeholder="retrieval default"
                        />
                        <span className="llm-proxy-param-card-hint">Number of document chunks to retrieve from Qdrant.</span>
                      </label>
                    </div>

                    <div className="llm-proxy-toggle-with-explanation">
                      <div className="llm-proxy-toggle-row">
                        <span className="llm-proxy-toggle-label">
                          <span className="llm-proxy-toggle-icon material-symbols-outlined" aria-hidden="true">code</span>
                          Code only mode
                        </span>
                        <label className="coreui-switch">
                          <input
                            type="checkbox"
                            checked={!!draft.code_only}
                            onChange={(e) => setDraft({ ...draft, code_only: e.target.checked })}
                          />
                          <span aria-hidden="true"></span>
                        </label>
                      </div>
                      <p className="llm-proxy-toggle-explanation">
                        Restricts RAG retrieval to code documents only (snippets, source files). Useful for coding assistants that shouldn't pull prose docs.
                      </p>
                    </div>

                    <div className="llm-proxy-toggle-with-explanation">
                      <div className="llm-proxy-toggle-row">
                        <span className="llm-proxy-toggle-label">
                          <span className="llm-proxy-toggle-icon material-symbols-outlined" aria-hidden="true">metadata</span>
                          Include RAG metadata in response
                        </span>
                        <label className="coreui-switch">
                          <input
                            type="checkbox"
                            checked={!!draft.include_rag_metadata}
                            onChange={(e) => setDraft({ ...draft, include_rag_metadata: e.target.checked })}
                          />
                          <span aria-hidden="true"></span>
                        </label>
                      </div>
                      <p className="llm-proxy-toggle-explanation">
                        Appends citation metadata (source file, chunk id, score) to the API response so clients can show where the answer came from.
                      </p>
                    </div>
                  </>
                )}
              </div>
            )}

            {/* ── Step 2: Privacy ── */}
            {wizardStep === 2 && (
              <div className="llm-proxy-wizard-step-panel">
                <div className="llm-proxy-info-card">
                  <h3 className="llm-proxy-info-card-title">
                    <span className="llm-proxy-info-card-title-icon material-symbols-outlined" aria-hidden="true">lock</span>
                    Privacy &amp; logging
                  </h3>
                  <div className="llm-proxy-info-card-body">
                    By default, the proxy logs every request: it stores a row in the journal database, creates a live
                    trace snapshot, and may show notifications. <strong>Private mode</strong> turns all of that off for
                    this build — no database rows, no traces, no notifications.
                    <ul>
                      <li><strong>When to enable Private:</strong> sensitive prompts, personal data, confidential code reviews, or any workflow where you don't want a record</li>
                      <li><strong>When to keep it off:</strong> normal development, debugging, or when you want the <strong>Logs</strong> tab (Traces and RAG Fusion Journal) to show request history</li>
                    </ul>
                  </div>
                </div>

                <div className="llm-proxy-toggle-with-explanation llm-proxy-toggle-with-explanation--tertiary">
                  <div className="llm-proxy-toggle-row">
                    <span className="llm-proxy-toggle-label">
                      <span className="llm-proxy-toggle-icon material-symbols-outlined" aria-hidden="true">visibility_off</span>
                      Private mode
                    </span>
                    <label className="coreui-switch">
                      <input
                        type="checkbox"
                        checked={!!draft.private}
                        onChange={(e) => setDraft({ ...draft, private: e.target.checked })}
                      />
                      <span aria-hidden="true"></span>
                    </label>
                  </div>
                  <p className="llm-proxy-toggle-explanation">
                    No proxy rows in the logs database, no live trace snapshot for this request, and no live or history
                    entries in Notifications. Does not affect provider or OS-level logging.
                  </p>
                  {draft.private && (
                    <p className="llm-proxy-toggle-explanation llm-proxy-toggle-explanation--emphasis">
                      <strong>⚠ Cloud models:</strong> if your client or pipeline sends traffic to hosted or third-party model
                      APIs, read those providers' privacy policies and terms — they govern how your data is stored and
                      processed; Private here only limits traces and logs inside this app.
                    </p>
                  )}
                </div>

                <div className={`llm-proxy-info-card${draft.private ? ' llm-proxy-info-card--dimmed' : ''}`}>
                  <h3 className="llm-proxy-info-card-title llm-proxy-info-card-title--compact">
                    <span className="llm-proxy-info-card-title-icon material-symbols-outlined" aria-hidden="true">visibility</span>
                    What gets logged when Private is off
                  </h3>
                  <div className="llm-proxy-info-card-body">
                    <ul>
                      <li><strong>RAG Fusion Journal</strong> — full request/response stored in SQLite for the <strong>Logs</strong> tab</li>
                      <li><strong>Traces</strong> — live in-memory snapshot of the pipeline stages (RAG hits, timing, etc.)</li>
                      <li><strong>Notifications</strong> — completion alerts in the notification center</li>
                    </ul>
                    All of the above are disabled when Private is on.
                  </div>
                </div>
              </div>
            )}

            {/* ── Step 3: Agent Proxy Mode ── */}
            {wizardStep === 3 && (
              <div className="llm-proxy-wizard-step-panel">
                <div className="llm-proxy-info-card">
                  <h3 className="llm-proxy-info-card-title">
                    <span className="llm-proxy-info-card-title-icon material-symbols-outlined" aria-hidden="true">terminal</span>
                    Agent Proxy Mode
                  </h3>
                  <div className="llm-proxy-info-card-body">
                    Configure how the model handles system prompts. When Proxy Mode is enabled, the app will not inject its own system prompts, allowing the agent to manage them entirely.
                  </div>
                </div>

                <div className="llm-proxy-toggle-with-explanation">
                  <div className="llm-proxy-toggle-row">
                    <span className="llm-proxy-toggle-label">
                      <span className="llm-proxy-toggle-icon material-symbols-outlined" aria-hidden="true">code_blocks</span>
                      Enable Agent Proxy Mode
                    </span>
                    <label className="coreui-switch">
                      <input
                        type="checkbox"
                        checked={draft.use_prompt_template === false}
                        onChange={(e) => setDraft({ ...draft, use_prompt_template: !e.target.checked })}
                      />
                      <span aria-hidden="true"></span>
                    </label>
                  </div>
                  <p className="llm-proxy-toggle-explanation">
                    The app will not inject system prompts — the agent manages them entirely. Also makes this build available to <code>chironai codex</code> and the Codex tab.
                  </p>
                </div>

                {draft.use_prompt_template !== false && (
                  <label className="coreui-form-field">
                    Prompt template
                    <select
                      className="coreui-select"
                      value={draft.prompt_name}
                      onChange={(e) => setDraft({ ...draft, prompt_name: e.target.value })}
                    >
                      <option value="">Select…</option>
                      {prompts.map((p) => (
                        <option key={p.id || p.name} value={p.name || p.id}>
                          {p.name || p.id}
                        </option>
                      ))}
                    </select>
                  </label>
                )}
              </div>
            )}

            {/* ── Step 4: Parameters ── */}
            {wizardStep === 4 && (
              <div className="llm-proxy-wizard-step-panel">
                <div className="llm-proxy-info-card">
                  <h3 className="llm-proxy-info-card-title">
                    <span className="llm-proxy-info-card-title-icon material-symbols-outlined" aria-hidden="true">tune</span>
                    Fine-tune the model
                  </h3>
                  <div className="llm-proxy-info-card-body">
                    These parameters control how the LLM generates text. Leave a field empty to inherit the server's
                    default value. Each one is explained below — no PhD required.
                  </div>
                </div>

                <div className="llm-proxy-param-card">
                  <div className="llm-proxy-param-card-header">
                    <span className="llm-proxy-param-card-icon material-symbols-outlined" aria-hidden="true">thermostat</span>
                    <h4 className="llm-proxy-param-card-title">Temperature</h4>
                  </div>
                  <p className="llm-proxy-param-card-description">
                    Controls <strong>creativity vs. consistency</strong>. Low values (0.0–0.3) make the model focused and
                    deterministic — great for code, facts, and precise answers. High values (0.7–1.5) make it more
                    creative and varied — better for brainstorming and storytelling. Think of it as a dial between
                    "robot" and "poet".
                  </p>
                  <input
                    className="coreui-input llm-proxy-param-card-field"
                    value={draft.temperature}
                    onChange={(e) => setDraft({ ...draft, temperature: e.target.value })}
                    placeholder="inherit (server default)"
                    inputMode="decimal"
                  />
                  <p className="llm-proxy-param-card-hint">Range: 0.0 – 2.0. Typical: 0.1 for code, 0.7 for chat, 1.0+ for creative writing.</p>
                </div>

                <div className="llm-proxy-param-card">
                  <div className="llm-proxy-param-card-header">
                    <span className="llm-proxy-param-card-icon material-symbols-outlined" aria-hidden="true">filter_list</span>
                    <h4 className="llm-proxy-param-card-title">Top P (nucleus sampling)</h4>
                  </div>
                  <p className="llm-proxy-param-card-description">
                    Another way to control randomness. Instead of cutting off low-probability tokens entirely (like
                    Temperature), <strong>Top P</strong> keeps the smallest set of tokens whose cumulative probability
                    exceeds P. Low P (0.1) = only the most likely tokens. High P (0.9+) = almost all tokens are
                    considered. In practice, you usually adjust <em>either</em> Temperature <em>or</em> Top P, not both.
                  </p>
                  <input
                    className="coreui-input llm-proxy-param-card-field"
                    value={draft.top_p}
                    onChange={(e) => setDraft({ ...draft, top_p: e.target.value })}
                    placeholder="inherit (server default)"
                    inputMode="decimal"
                  />
                  <p className="llm-proxy-param-card-hint">Range: 0.0 – 1.0. Typical: 0.9 for general use, 0.1 for strict/focused output.</p>
                </div>

                <div className="llm-proxy-prefab-panel">
                  <div className="llm-proxy-param-card-header">
                    <span className="llm-proxy-param-card-icon material-symbols-outlined" aria-hidden="true">dashboard_customize</span>
                    <h4 className="llm-proxy-param-card-title">Prefabs</h4>
                  </div>
                  <div className="coreui-card-actions llm-proxy-prefab-actions" aria-label="Parameter prefabs">
                    {PARAMETER_PREFABS.map((prefab) => {
                      const active = matchingParameterPrefab?.id === prefab.id;
                      return (
                        <CoreUIButton
                          key={prefab.id}
                          variant={active ? 'primary' : 'default'}
                          className="llm-proxy-prefab-button"
                          onClick={() => applyParameterPrefab(prefab)}
                          aria-pressed={active}
                        >
                          <span className="material-symbols-outlined coreui-icon--sm" aria-hidden="true">{prefab.icon}</span>
                          <span>{prefab.label}</span>
                        </CoreUIButton>
                      );
                    })}
                  </div>
                  <section className="coreui-panel-note coreui-panel-note--info llm-proxy-prefab-note">
                    <div className="llm-proxy-prefab-note-title">{parameterPrefabNote.label}</div>
                    {parameterPrefabNote.values ? (
                      <div className="llm-proxy-prefab-note-values">
                        num_ctx {parameterPrefabNote.values.num_ctx} · num_predict {parameterPrefabNote.values.num_predict} · max steps {parameterPrefabNote.values.max_agent_steps}
                      </div>
                    ) : null}
                    <div className="llm-proxy-prefab-note-description">{parameterPrefabNote.description}</div>
                  </section>
                </div>

                <div className="llm-proxy-param-card">
                  <div className="llm-proxy-param-card-header">
                    <span className="llm-proxy-param-card-icon material-symbols-outlined" aria-hidden="true">memory</span>
                    <h4 className="llm-proxy-param-card-title">num_ctx (context window)</h4>
                  </div>
                  <p className="llm-proxy-param-card-description">
                    The <strong>total number of tokens</strong> the model can "see" at once — including the system prompt,
                    RAG context, conversation history, and the new question. A larger window means more context but
                    uses more memory and is slower. The model's maximum is set by the provider (shown when you click
                    "Check model"). Setting this lower than the max saves resources for short conversations.
                  </p>
                  <input
                    className="coreui-input llm-proxy-param-card-field"
                    value={draft.num_ctx}
                    onChange={(e) => setDraft({ ...draft, num_ctx: e.target.value })}
                    placeholder="inherit (model default)"
                    inputMode="numeric"
                  />
                  <p className="llm-proxy-param-card-hint">Example: 8192 for small models, 32768+ for large context models. Auto-filled when you select a provider model above.</p>
                </div>

                <div className="llm-proxy-param-card">
                  <div className="llm-proxy-param-card-header">
                    <span className="llm-proxy-param-card-icon material-symbols-outlined" aria-hidden="true">data_object</span>
                    <h4 className="llm-proxy-param-card-title">num_predict (max output tokens)</h4>
                  </div>
                  <p className="llm-proxy-param-card-description">
                    The <strong>maximum number of tokens</strong> the provider may generate for one answer. This is
                    also reserved inside num_ctx so long histories cannot crowd out the model's answer budget.
                  </p>
                  <input
                    className="coreui-input llm-proxy-param-card-field"
                    value={draft.num_predict}
                    onChange={(e) => setDraft({ ...draft, num_predict: e.target.value })}
                    placeholder="65536"
                    inputMode="numeric"
                  />
                  <p className="llm-proxy-param-card-hint">Request max_tokens can still override this for one call. Larger values leave less room for input history.</p>
                </div>

                <div className="llm-proxy-param-card">
                  <div className="llm-proxy-param-card-header">
                    <span className="llm-proxy-param-card-icon material-symbols-outlined" aria-hidden="true">route</span>
                    <h4 className="llm-proxy-param-card-title">Max agent steps</h4>
                  </div>
                  <p className="llm-proxy-param-card-description">
                    When the model uses <strong>tool calls</strong> (function calling), each round of "think → call tool →
                    read result → think again" is one agent step. This limit prevents infinite loops. A step count of 1
                    means no tool use at all (single-shot). Higher values allow multi-step reasoning chains.
                  </p>
                  <input
                    className="coreui-input llm-proxy-param-card-field"
                    value={draft.max_agent_steps}
                    onChange={(e) => setDraft({ ...draft, max_agent_steps: e.target.value })}
                    placeholder="inherit (1–256)"
                    inputMode="numeric"
                  />
                  <p className="llm-proxy-param-card-hint">Range: 1–256. Typical: 1 for simple chat, 5–10 for tool-using agents, 50+ for complex agentic workflows.</p>
                </div>


              </div>
            )}

            {/* ── Step 5: Web Knowledge ── */}
            {wizardStep === 5 && (
              <div className="llm-proxy-wizard-step-panel">
                <div className="llm-proxy-info-card">
                  <h3 className="llm-proxy-info-card-title">
                    <span className="llm-proxy-info-card-title-icon material-symbols-outlined" aria-hidden="true">language</span>
                    Web Knowledge — fresh info beyond your docs
                  </h3>
                  <div className="llm-proxy-info-card-body">
                    Your RAG database contains <em>your</em> indexed documents, but what about the latest library release,
                    a new API, or a recent changelog? <strong>Web Knowledge</strong> supplements RAG with live internet
                    data — search results, web pages, and GitHub-sourced documentation — so the model can answer
                    questions about things that happened <em>after</em> your last index run.
                  </div>
                </div>

                <div className="llm-proxy-toggle-with-explanation llm-proxy-toggle-with-explanation--tertiary">
                  <div className="llm-proxy-toggle-row">
                    <span className="llm-proxy-toggle-label">
                      <span className="llm-proxy-toggle-icon material-symbols-outlined" aria-hidden="true">public</span>
                      Web supplement enabled
                    </span>
                    <label className="coreui-switch">
                      <input
                        type="checkbox"
                        checked={!!draft.web_enabled}
                        onChange={(e) => setDraft({ ...draft, web_enabled: e.target.checked })}
                      />
                      <span aria-hidden="true"></span>
                    </label>
                  </div>
                  <p className="llm-proxy-toggle-explanation">
                    Master switch for all web-based features below. When off, no web data is fetched for this build —
                    only your local RAG collection is used.
                  </p>
                </div>

                {draft.web_enabled && (
                  <>
                    <div className="llm-proxy-web-features">
                      <div className="llm-proxy-web-feature-item">
                        <span className="llm-proxy-web-feature-title">
                          <span className="material-symbols-outlined coreui-icon--sm coreui-icon--tertiary" aria-hidden="true">travel_explore</span>
                          DuckDuckGo search snippets
                        </span>
                        <p className="llm-proxy-web-feature-desc">
                          Fetches short text snippets from DuckDuckGo search results. Free, no API key needed.
                          Great for quick facts, version numbers, and recent announcements.
                        </p>
                        <div className="llm-proxy-toggle-row llm-proxy-toggle-row--sub">
                          <span className="llm-proxy-toggle-label llm-proxy-toggle-label--sub">Enable DDG news</span>
                          <label className="coreui-switch">
                            <input
                              type="checkbox"
                              checked={!!draft.web_interaction_ddg_news}
                              onChange={(e) => setDraft({ ...draft, web_interaction_ddg_news: e.target.checked })}
                            />
                            <span aria-hidden="true"></span>
                          </label>
                        </div>
                      </div>

                      <div className="llm-proxy-web-feature-item">
                        <span className="llm-proxy-web-feature-title">
                          <span className="material-symbols-outlined coreui-icon--sm coreui-icon--tertiary" aria-hidden="true">web</span>
                          Fetch web pages
                        </span>
                        <p className="llm-proxy-web-feature-desc">
                          When a search result looks promising, the proxy can fetch and extract the full page content
                          for deeper context. Uses more tokens but provides much richer information.
                        </p>
                        <div className="llm-proxy-toggle-row llm-proxy-toggle-row--sub">
                          <span className="llm-proxy-toggle-label llm-proxy-toggle-label--sub">Enable page fetching</span>
                          <label className="coreui-switch">
                            <input
                              type="checkbox"
                              checked={!!draft.web_interaction_fetch_page}
                              onChange={(e) => setDraft({ ...draft, web_interaction_fetch_page: e.target.checked })}
                            />
                            <span aria-hidden="true"></span>
                          </label>
                        </div>
                      </div>

                      <div className="llm-proxy-web-feature-item">
                        <span className="llm-proxy-web-feature-title">
                          <span className="material-symbols-outlined coreui-icon--sm coreui-icon--tertiary" aria-hidden="true">menu_book</span>
                          Wikipedia lookup
                        </span>
                        <p className="llm-proxy-web-feature-desc">
                          Searches Wikipedia for encyclopedic background on topics. Useful for general knowledge,
                          definitions, and historical context.
                        </p>
                        <div className="llm-proxy-toggle-row llm-proxy-toggle-row--sub">
                          <span className="llm-proxy-toggle-label llm-proxy-toggle-label--sub">Enable Wikipedia</span>
                          <label className="coreui-switch">
                            <input
                              type="checkbox"
                              checked={!!draft.web_interaction_wikipedia}
                              onChange={(e) => setDraft({ ...draft, web_interaction_wikipedia: e.target.checked })}
                            />
                            <span aria-hidden="true"></span>
                          </label>
                        </div>
                      </div>
                    </div>

                    <div className="llm-proxy-toggle-with-explanation llm-proxy-section-gap-sm">
                      <div className="llm-proxy-toggle-row">
                        <span className="llm-proxy-toggle-label">
                          <span className="llm-proxy-toggle-icon material-symbols-outlined" aria-hidden="true">cloud_download</span>
                          Fetch web knowledge (GitHub docs)
                        </span>
                        <label className="coreui-switch">
                          <input
                            type="checkbox"
                            checked={!!draft.fetch_web_knowledge}
                            onChange={(e) => setDraft({ ...draft, fetch_web_knowledge: e.target.checked })}
                          />
                          <span aria-hidden="true"></span>
                        </label>
                      </div>
                      <p className="llm-proxy-toggle-explanation">
                        Enables merged multi-collection retrieval and background GitHub markdown refresh via
                        <code>external_docs_rag</code>. Pulls documentation from public GitHub repos (rate-limited via
                        the public API) and indexes them into a separate Qdrant collection. Ideal for framework docs,
                        SDK references, and open-source project wikis.
                      </p>
                    </div>

                    <div className="llm-proxy-toggle-with-explanation">
                      <div className="llm-proxy-toggle-row">
                        <span className="llm-proxy-toggle-label">
                          <span className="llm-proxy-toggle-icon material-symbols-outlined" aria-hidden="true">toggle_on</span>
                          Web on keyword triggers
                        </span>
                        <label className="coreui-switch">
                          <input
                            type="checkbox"
                            checked={draft.web_interaction_on_keywords !== false}
                            onChange={(e) => setDraft({ ...draft, web_interaction_on_keywords: e.target.checked })}
                          />
                          <span aria-hidden="true"></span>
                        </label>
                      </div>
                      <p className="llm-proxy-toggle-explanation">
                        Automatically triggers web search when the query contains keywords that suggest the user needs
                        fresh information (e.g. "latest", "new", "release", "changelog").
                      </p>
                    </div>

                    <div className="llm-proxy-toggle-with-explanation">
                      <div className="llm-proxy-toggle-row">
                        <span className="llm-proxy-toggle-label">
                          <span className="llm-proxy-toggle-icon material-symbols-outlined" aria-hidden="true">help</span>
                          Web on low-confidence framework questions
                        </span>
                        <label className="coreui-switch">
                          <input
                            type="checkbox"
                            checked={draft.web_interaction_on_low_confidence_framework !== false}
                            onChange={(e) => setDraft({ ...draft, web_interaction_on_low_confidence_framework: e.target.checked })}
                          />
                          <span aria-hidden="true"></span>
                        </label>
                      </div>
                      <p className="llm-proxy-toggle-explanation">
                        When RAG returns low-confidence results for framework-related questions, automatically supplements
                        with web search to fill the gap.
                      </p>
                    </div>
                  </>
                )}
              </div>
            )}

            </div>
  );
}
