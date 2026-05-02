import CoreUIBadge from "./CoreUIBadge";
import "../styles/components/ExtensionsTab.css";

export default function DevDocumentationTab() {
  return (
    <div className="extensions-tab tab-view">
      <div className="extensions-tab__header">
        <div>
          <h2>Dev Documentation</h2>
          <p>Guide for integrating extensions with the project.</p>
        </div>
      </div>

      <div className="extensions-dev-doc">
        <section className="coreui-card-shell coreui-p-md extensions-schema-section">
          <div className="extensions-schema-section-header">
            <h4>Overview</h4>
          </div>
          <div className="extensions-schema-section-body">
            <p>
              Extensions allow you to add new functionality to the project, such as new LLM providers,
              UI tabs, or background services. They are discovered via a manifest file and can
              provide both backend logic (Python) and frontend UI (declarative schemas).
            </p>
          </div>
        </section>

        <section className="coreui-card-shell coreui-p-md extensions-schema-section">
          <div className="extensions-schema-section-header">
            <h4>Manifest (chironai-extension.json)</h4>
          </div>
          <div className="extensions-schema-section-body">
            <p>Every extension must have a <code>chironai-extension.json</code> in its root directory.</p>
            <pre className="extensions-schema-diagnostics">
{`{
  "id": "my-extension",
  "version": "0.1.0",
  "type": "ui_extension", // or "llm_provider"
  "title": "My Extension",
  "backend": {
    "entrypoint": "backend.provider:create_provider"
  },
  "capabilities": {
    "tab_ui": true,
    "iframe_tab": true
  }
}`}
            </pre>
          </div>
        </section>

        <section className="coreui-card-shell coreui-p-md extensions-schema-section">
          <div className="extensions-schema-section-header">
            <h4>Backend Provider (Python)</h4>
          </div>
          <div className="extensions-schema-section-body">
            <p>
              The backend provider implements the extension logic. It should define a 
              <code>create_provider(host_context, manifest)</code> function that returns an 
              instance of your provider class.
            </p>
            <pre className="extensions-schema-diagnostics">
{`class MyExtension:
    def __init__(self, host_context, manifest):
        self._host = host_context
        self._manifest = manifest

    def get_tab_descriptor(self, **kwargs):
        return {
            "id": "my-tab",
            "title": "My Tab",
            "icon": "web_asset"
        }

    def get_tab_payload(self, **kwargs):
        return {
            "title": "My Tab",
            "content": {
                "type": "iframe",
                "src": "http://localhost:3000"
            }
        }`}
            </pre>
          </div>
        </section>

        <section className="coreui-card-shell coreui-p-md extensions-schema-section">
          <div className="extensions-schema-section-header">
            <h4>CoreUI Schemas</h4>
          </div>
          <div className="extensions-schema-section-body">
            <p>
              Extensions can publish declarative UI schemas to render settings or status pages
              directly in the CoreUI. Supported components include <code>status</code>, 
              <code>text</code>, <code>table</code>, <code>input</code>, <code>select</code>, 
              and <code>action</code>.
            </p>
            <pre className="extensions-schema-diagnostics">
{`"ui_schema": {
  "pages": [
    {
      "id": "overview",
      "title": "Overview",
      "sections": [
        {
          "id": "status-section",
          "title": "Status",
          "components": [
            { "type": "status", "key": "health", "label": "Health" }
          ]
        }
      ]
    }
  ]
}`}
            </pre>
          </div>
        </section>
      </div>
    </div>
  );
}
