import type { ReactNode } from 'react';
import {
  formatBytesLoose,
  formatIsoShort,
} from './extensionRuntimeTabUtils';

type ModelRecord = Record<string, unknown>;

export function ExtensionRuntimeModelDetailsContent({ model }: { model: ModelRecord | null }) {
  if (!model) return null;

  const renderRow = (label: string, value: string, key: string) => (
    <div key={key || label} className="coreui-showcase-data-row" style={{ gridTemplateColumns: '1fr auto' }}>
      <div className="extensions-runtime-model-details-label">{label}</div>
      <div className="extensions-runtime-model-details-value">{value}</div>
    </div>
  );

  const renderSection = (title: string, data: Record<string, unknown> | null | undefined) => {
    if (!data || Object.keys(data).length === 0) return null;
    return (
      <div key={title} className="extensions-runtime-model-details-section">
        <div className="extensions-runtime-model-details-section-title">{title}</div>
        <div className="coreui-showcase-data-table">
          {Object.entries(data).map(([k, v]) => {
            if (v === null || v === undefined || v === '') return null;
            let displayValue = String(v);
            if (k === 'size' || k === 'parameter_size') displayValue = formatBytesLoose(v);
            if (k === 'modified_at') displayValue = formatIsoShort(v);
            return renderRow(k, displayValue, k);
          })}
        </div>
      </div>
    );
  };

  const sections: ReactNode[] = [];
  const details: Record<string, unknown> = {};
  ['id', 'model', 'size', 'modified_at', 'digest', 'format'].forEach((k) => {
    if (model[k]) details[k] = model[k];
  });
  if (model.details && typeof model.details === 'object') {
    Object.assign(details, model.details as Record<string, unknown>);
  }
  sections.push(renderSection('Details', details));
  sections.push(renderSection('Model Info', model.model_info as Record<string, unknown>));

  const capabilities = Array.isArray(model.capabilities) ? model.capabilities : [];
  if (capabilities.length > 0) {
    sections.push(
      <div key="capabilities" className="extensions-runtime-model-details-section">
        <div className="extensions-runtime-model-details-section-title">Capabilities</div>
        <div className="extensions-runtime-model-details-value--array">
          {capabilities.map((cap) => (
            <span key={String(cap)} className="extensions-runtime-model-details-tag">
              {String(cap)}
            </span>
          ))}
        </div>
      </div>,
    );
  }

  return <div className="extensions-runtime-model-details">{sections}</div>;
}
