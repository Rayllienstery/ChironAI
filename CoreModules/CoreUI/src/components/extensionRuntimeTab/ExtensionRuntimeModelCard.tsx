import Card from '../Card';
import {
  formatBytesLoose,
  formatIsoShort,
  modelIsHidden,
  normalizeModelDetailsForModal,
  parseModelName,
} from './extensionRuntimeTabUtils';

export type ModelActionTemplates = {
  show?: Record<string, unknown> | null;
  hide?: Record<string, unknown> | null;
  unhide?: Record<string, unknown> | null;
  delete?: Record<string, unknown> | null;
};

type ExtensionRuntimeModelCardProps = {
  row: Record<string, unknown>;
  index: number;
  extensionId: string;
  payloadExtensionId?: string;
  menuOpen: boolean;
  menuPosition: { left: number; top: number } | null;
  busyModelActionKey: string;
  busyActionId: string;
  templates: ModelActionTemplates;
  onOpenMenu: (modelId: string, position: { left: number; top: number } | null) => void;
  onShowDetails: (row: Record<string, unknown>, modelId: string) => void;
  onModelMenuAction: (template: Record<string, unknown>, modelId: string) => void;
};

export default function ExtensionRuntimeModelCard({
  row,
  index,
  extensionId,
  payloadExtensionId,
  menuOpen,
  menuPosition,
  busyModelActionKey,
  busyActionId,
  templates,
  onOpenMenu,
  onShowDetails,
  onModelMenuAction,
}: ExtensionRuntimeModelCardProps) {
  const modelId = String(row?.id ?? row?.model ?? '').trim();
  const { displayName, quantization } = parseModelName(modelId);
  const sizeText = formatBytesLoose(row?.size);
  const modifiedText = formatIsoShort(row?.modified_at);
  const isHidden = modelIsHidden(row);
  const modelInfo = row?.model_info;
  const contextLengthKey = modelInfo && typeof modelInfo === 'object'
    ? Object.keys(modelInfo as Record<string, unknown>).find((k) => k.endsWith('context_length'))
    : null;
  const contextLength = contextLengthKey
    ? (modelInfo as Record<string, unknown>)[contextLengthKey]
    : null;
  const capabilities = Array.isArray(row?.capabilities) ? row.capabilities : [];
  const { show: showTpl, hide: hideTpl, unhide: unhideTpl, delete: delTpl } = templates;

  const busyShow = busyModelActionKey === `show_model:${modelId}`;
  const busyHide = busyModelActionKey === `hide_model:${modelId}`;
  const busyUnhide = busyModelActionKey === `unhide_model:${modelId}`;
  const busyDel = busyModelActionKey === `delete_model:${modelId}`;

  return (
    <Card
      key={`model-${modelId || index}`}
      className="extensions-runtime-model-card"
      interactive={Boolean(modelId && showTpl)}
      elevateOnHover={Boolean(modelId && showTpl)}
      onClick={() => {
        if (modelId && showTpl) {
          onShowDetails(row, modelId);
          void onModelMenuAction(showTpl, modelId);
        }
      }}
    >
      <div className="extensions-runtime-model-card__top">
        <div className="extensions-runtime-model-card__title-wrap">
          <div className="extensions-runtime-model-card__title" title={modelId || '—'}>
            {displayName || modelId || '—'}
          </div>
          {quantization ? (
            <div className="extensions-runtime-model-card__quant">
              <span className="extensions-runtime-model-meta-k">Quantization:</span>
              <span className="extensions-runtime-model-meta-v">{quantization}</span>
            </div>
          ) : null}
          {contextLength != null ? (
            <div className="extensions-runtime-model-card__quant">
              <span className="extensions-runtime-model-meta-k">Context:</span>
              <span className="extensions-runtime-model-meta-v">{Number(contextLength).toLocaleString()}</span>
            </div>
          ) : null}
        </div>
        <div className="extensions-runtime-model-card__menu">
          <button
            type="button"
            className="extensions-runtime-model-menu-btn"
            aria-haspopup="menu"
            aria-expanded={menuOpen ? 'true' : 'false'}
            aria-label="Model actions"
            onClick={(e) => {
              e.stopPropagation();
              const rect = e.currentTarget.getBoundingClientRect();
              const menuWidth = 200;
              const margin = 12;
              const left = Math.min(
                window.innerWidth - menuWidth - margin,
                Math.max(margin, rect.right - menuWidth),
              );
              const top = Math.min(window.innerHeight - margin, rect.bottom + 6);
              onOpenMenu(modelId, menuOpen ? null : { left, top });
            }}
            disabled={!modelId}
          >
            <span className="material-symbols-outlined" aria-hidden="true">more_vert</span>
          </button>
          {menuOpen && menuPosition ? (
            <div
              className="extensions-runtime-model-menu"
              role="menu"
              style={{ left: menuPosition.left, top: menuPosition.top }}
            >
              <button
                type="button"
                className="extensions-runtime-model-menu-item"
                role="menuitem"
                disabled={!modelId || busyShow || Boolean(busyActionId)}
                onClick={(e) => {
                  e.stopPropagation();
                  if (showTpl) {
                    onShowDetails(row, modelId);
                    void onModelMenuAction(showTpl, modelId);
                  }
                }}
              >
                {busyShow ? 'Working...' : 'Show details'}
              </button>
              {hideTpl ? (
                <button
                  type="button"
                  className="extensions-runtime-model-menu-item"
                  role="menuitem"
                  disabled={!modelId || isHidden || busyHide || Boolean(busyActionId)}
                  onClick={(e) => { e.stopPropagation(); void onModelMenuAction(hideTpl, modelId); }}
                >
                  {busyHide ? 'Working...' : 'Hide model'}
                </button>
              ) : null}
              {unhideTpl ? (
                <button
                  type="button"
                  className="extensions-runtime-model-menu-item"
                  role="menuitem"
                  disabled={!modelId || !isHidden || busyUnhide || Boolean(busyActionId)}
                  onClick={(e) => { e.stopPropagation(); void onModelMenuAction(unhideTpl, modelId); }}
                >
                  {busyUnhide ? 'Working...' : 'Unhide model'}
                </button>
              ) : null}
              {delTpl ? (
                <button
                  type="button"
                  className="extensions-runtime-model-menu-item extensions-runtime-model-menu-item--danger"
                  role="menuitem"
                  disabled={!modelId || busyDel || Boolean(busyActionId)}
                  onClick={(e) => { e.stopPropagation(); void onModelMenuAction(delTpl, modelId); }}
                >
                  {busyDel ? 'Working...' : 'Delete model'}
                </button>
              ) : null}
            </div>
          ) : null}
        </div>
      </div>

      <div className="extensions-runtime-model-card__provider">
        <span className="extensions-runtime-model-meta-k">Provider:</span>
        <span className="extensions-runtime-model-meta-v">
          {String(row?.provider_id || row?.provider || payloadExtensionId || extensionId || 'unknown')}
        </span>
      </div>

      <div className="extensions-runtime-model-card__meta">
        {sizeText && !modelId.toLowerCase().endsWith('cloud') ? (
          <div className="extensions-runtime-model-meta-row">
            <span className="extensions-runtime-model-meta-k">Size:</span>
            <span className="extensions-runtime-model-meta-v">{sizeText}</span>
          </div>
        ) : null}
        {modifiedText ? (
          <div className="extensions-runtime-model-meta-row">
            <span className="extensions-runtime-model-meta-k">Modified:</span>
            <span className="extensions-runtime-model-meta-v">{modifiedText}</span>
          </div>
        ) : null}
        {capabilities.length > 0 ? (
          <div className="extensions-runtime-model-card__caps">
            {capabilities.map((cap) => (
              <span key={String(cap)} className="extensions-runtime-model-card__cap-tag">{String(cap)}</span>
            ))}
          </div>
        ) : null}
      </div>
    </Card>
  );
}

export { normalizeModelDetailsForModal };
