import { useState } from "react";
import "../styles/components/SwaggerTab.css";

const SWAGGER_UI_URL = "/api/webui/swagger/";
const OPENAPI_JSON_URL = "/api/webui/openapi.json";

export default function SwaggerTab() {
  const [loaded, setLoaded] = useState(false);
  const [failed, setFailed] = useState(false);

  return (
    <div className="swagger-tab tab-view">
      <div className="swagger-tab__header">
        <div>
          <h2>Swagger</h2>
          <p>OpenAPI documentation for ChironAI HTTP routes.</p>
        </div>
        <a className="swagger-tab__spec-link" href={OPENAPI_JSON_URL} target="_blank" rel="noreferrer">
          OpenAPI JSON
        </a>
      </div>

      <section className="swagger-tab__frame-shell" aria-label="Swagger UI">
        {!loaded && !failed ? (
          <div className="swagger-tab__status" role="status">
            Loading Swagger UI...
          </div>
        ) : null}
        {failed ? (
          <div className="swagger-tab__status swagger-tab__status--error" role="alert">
            Swagger UI could not be loaded. Open the JSON spec from the link above to inspect the API.
          </div>
        ) : null}
        <iframe
          title="ChironAI Swagger UI"
          className="swagger-tab__frame"
          src={SWAGGER_UI_URL}
          onLoad={() => {
            setLoaded(true);
            setFailed(false);
          }}
          onError={() => {
            setLoaded(false);
            setFailed(true);
          }}
        />
      </section>
    </div>
  );
}
