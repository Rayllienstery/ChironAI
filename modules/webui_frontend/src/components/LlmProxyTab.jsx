import React from 'react';
import ModelSettings from './ModelSettings';
import './SettingsTab.css';

function LlmProxyTab({ onOpenRagModels }) {
  return (
    <div className="settings-tab">
      <h2>LLM Proxy</h2>

      <div className="settings-form">
        <div className="settings-section">
          <h3>How to use the proxy</h3>
          <p className="settings-intro">
            This is an OpenAI-compatible RAG proxy backed by Ollama and Qdrant. Point your editor or tools to the
            proxy base URL and use the <code>rag-ollama</code> model for completions with context.
          </p>
          <ul className="settings-instructions">
            <li>
              <strong>Base URL</strong>: <code>http://localhost:&lt;port&gt;</code> on the machine where this proxy runs
              (or <code>http://&lt;PC_IP&gt;:&lt;port&gt;</code> from another device). The port comes from the server
              configuration.
            </li>
            <li>
              <strong>Zed</strong>: in AI settings choose <em>OpenAI API Compatible</em>, set the API URL to the base
              URL above, and select the <code>rag-ollama</code> model. API key can be left empty unless you add your own
              authentication.
            </li>
            <li>
              <strong>VSCode + Continue.dev</strong>: configure an OpenAI-compatible provider, set the base URL to this
              proxy, and use the <code>rag-ollama</code> model.
            </li>
            <li>
              The model and RAG behavior for the proxy are controlled by the settings below.
            </li>
          </ul>
        </div>

        <div className="settings-section">
          <h3>Model Settings</h3>
          <ModelSettings onOpenRagModels={onOpenRagModels} />
        </div>
      </div>
    </div>
  );
}

export default LlmProxyTab;

