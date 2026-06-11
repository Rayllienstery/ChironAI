import React, { useEffect, useState } from "react";
import CoreUIBadge from "./CoreUIBadge";
import CoreUIButton from "./CoreUIButton";
import { formatElapsedMs } from "../utils/elapsedTime";
import "../styles/components/CoreUIDockerCard.css";

function joinClasses(parts) {
  return parts.filter(Boolean).join(" ");
}

function icon(name) {
  if (!name) return null;
  return <span className="material-symbols-outlined coreui-docker-card__icon-glyph" aria-hidden="true">{name}</span>;
}

function actionButtonVariant(variant) {
  if (variant === "primary") return "primary";
  if (variant === "danger") return "danger";
  if (variant === "ghost") return "ghost";
  return "default";
}

function MetaValue({ value }) {
  if (value === null || value === undefined || value === "") {
    return <span className="coreui-docker-card__meta-value-empty">—</span>;
  }
  if (typeof value === "object" && value.label) {
    return <CoreUIBadge tone={value.tone || "neutral"}>{value.label}</CoreUIBadge>;
  }
  return <span className="coreui-docker-card__meta-value">{value}</span>;
}

function ConfirmableAction({ action, idx, isLive, busy, activeAction, actionTimerNow, onClick }) {
  const actionId = isLive ? String(action?.id || `action-${idx}`) : `action-${idx}`;
  const label = isLive ? String(action?.label || action?.id || "") : String(action?.label || "");
  const variant = actionButtonVariant(action?.variant);
  const actionIcon = action?.icon;
  const disabled = isLive ? Boolean(action?.disabled) || busy : Boolean(action?.disabled);
  const timerVisible = busy && isLive && activeAction && activeAction.id === action?.id;

  return (
    <span key={actionId} className="coreui-docker-card__action-wrap">
      <CoreUIButton
        variant={variant}
        size={action?.size || "sm"}
        onClick={onClick}
        disabled={disabled}
      >
        {actionIcon ? icon(actionIcon) : null}
        {busy ? "Working..." : label}
      </CoreUIButton>
      {timerVisible ? (
        <span
          className="coreui-docker-card__action-timer"
          aria-label={`Elapsed ${formatElapsedMs(actionTimerNow - activeAction.startedAt)}`}
        >
          <span className="material-symbols-outlined" aria-hidden="true">timer</span>
          {formatElapsedMs(actionTimerNow - activeAction.startedAt)}
        </span>
      ) : null}
    </span>
  );
}

/**
 * Standardized Docker runtime card for CoreUI.
 *
 * Two operating modes:
 *
 * - **Read-only demo mode** (used by the CoreUI Showcase): pass `backendUrl`,
 *   `actions` as plain `{ label, variant, icon, onClick }` objects, and
 *   `meta` as plain `{ label, value }` tiles. The URL field is read-only and
 *   buttons fire `onClick` directly with no busy state.
 *
 * - **Live service_panel mode** (used by the Open WebUI extension runtime):
 *   pass a `service` descriptor (see below) and the card handles editable
 *   URL input + autosave, per-action busy state with elapsed timer chips,
 *   confirm dialogs, and `action.payload_keys` propagation.
 *
 * @param {Object} props
 * @param {string} [props.name] - Runtime name shown in the header.
 * @param {string} [props.description] - Short subtitle beneath the name.
 * @param {string} [props.icon] - Material Symbols icon name for the runtime mark.
 * @param {{ tone?: string, label: string }} [props.status] - Status badge in the header.
 * @param {string} [props.httpStatus] - HTTP status text rendered next to the status badge.
 * @param {string} [props.backendUrl] - (Demo mode) Current backend URL value.
 * @param {string} [props.backendUrlLabel='Chat backend URL'] - Label for the URL field.
 * @param {string} [props.backendUrlPlaceholder] - Placeholder for the URL field.
 * @param {Array<{ label: string, value?: any }>} [props.meta] - (Demo mode) Metadata tiles.
 * @param {Array<{ label: string, variant?: string, size?: string, icon?: string, onClick?: Function }>} [props.actions]
 *   (Demo mode) Action buttons rendered under the URL field.
 * @param {string} [props.className] - Additional CSS classes.
 * @param {React.ReactNode} [props.children] - Optional custom content appended to the body.
 * @param {Object} [props.style] - Inline style overrides.
 *
 * @param {Object} [props.service] - (Live mode) Backend payload descriptor:
 *   `{ backendUrl, backendUrlLabel?, backendUrlPlaceholder?, onBackendUrlChange,
 *      onBackendUrlBlur, actions: [...], meta: [...], httpStatus? }`.
 *   When provided, takes precedence over the demo-mode props.
 * @param {string} [props.busyActionId] - (Live mode) Currently busy action id.
 * @param {Object} [props.activeAction] - (Live mode) `{ id, label, startedAt }`.
 * @param {number} [props.actionTimerNow] - (Live mode) Timestamp ms for elapsed timer.
 * @param {string} [props.fieldKey='backend_url'] - (Live mode) Field key for the URL input.
 */
export default function CoreUIDockerCard({
  name = "Runtime",
  description,
  icon: iconName = "deployed_code",
  status,
  httpStatus,
  backendUrl,
  backendUrlLabel = "Chat backend URL",
  backendUrlPlaceholder,
  meta = [],
  actions = [],
  className,
  children,
  style,
  service,
  busyActionId,
  activeAction,
  actionTimerNow,
  fieldKey = "backend_url",
  ...rest
}) {
  const isLive = Boolean(service);

  const liveBackendUrl = isLive ? (service?.backendUrl ?? "") : (backendUrl ?? "");
  const liveBackendUrlLabel = isLive
    ? (service?.backendUrlLabel || backendUrlLabel)
    : backendUrlLabel;
  const liveBackendUrlPlaceholder = isLive
    ? (service?.backendUrlPlaceholder || backendUrlPlaceholder)
    : backendUrlPlaceholder;
  const liveMeta = isLive ? (Array.isArray(service?.meta) ? service.meta : []) : meta;
  const liveActions = isLive ? (Array.isArray(service?.actions) ? service.actions : []) : actions;
  const liveHttpStatus = isLive ? (service?.httpStatus || httpStatus) : httpStatus;

  const [localValue, setLocalValue] = useState(liveBackendUrl);
  useEffect(() => {
    setLocalValue(liveBackendUrl);
  }, [liveBackendUrl]);

  const handleBackendUrlChange = (e) => {
    const next = e.target.value;
    setLocalValue(next);
    if (isLive && typeof service?.onBackendUrlChange === "function") {
      service.onBackendUrlChange(next);
    }
  };

  const handleBackendUrlBlur = () => {
    if (!isLive) return;
    if (typeof service?.onBackendUrlBlur === "function") {
      void service.onBackendUrlBlur(localValue, fieldKey);
    }
  };

  const handleActionClick = (action) => {
    if (isLive) {
      if (typeof action?.onAction === "function") {
        void action.onAction(action);
      }
      return;
    }
    if (typeof action?.onClick === "function") {
      action.onClick(action);
    }
  };

  const wrapWithConfirm = (action, clickHandler) => () => {
    const confirmText = String(action?.confirm || "").trim();
    if (confirmText && !window.confirm(confirmText)) return;
    clickHandler();
  };

  return (
    <div
      className={joinClasses(["coreui-docker-card", className])}
      style={style}
      {...rest}
    >
      <header className="coreui-docker-card__header">
        <div className="coreui-docker-card__title">
          <div className="coreui-docker-card__mark" aria-hidden="true">
            {icon(iconName)}
          </div>
          <div className="coreui-docker-card__title-text">
            <h3 className="coreui-docker-card__name">{name}</h3>
            {description ? (
              <p className="coreui-docker-card__subtitle">{description}</p>
            ) : null}
          </div>
        </div>
        <div className="coreui-docker-card__status">
          {status ? (
            <CoreUIBadge tone={status.tone || "neutral"} className="coreui-docker-card__status-badge">
              <span className="coreui-docker-card__status-dot" aria-hidden="true" />
              {status.label}
            </CoreUIBadge>
          ) : null}
          {liveHttpStatus ? (
            <span className="coreui-docker-card__http-status">{liveHttpStatus}</span>
          ) : null}
        </div>
      </header>

      <div className="coreui-docker-card__body">
        <div className="coreui-docker-card__primary">
          <label className="coreui-docker-card__field">
            <span className="coreui-docker-card__field-label">{liveBackendUrlLabel}</span>
            <input
              type="text"
              className="coreui-docker-card__input"
              value={isLive ? localValue : (liveBackendUrl ?? "")}
              placeholder={liveBackendUrlPlaceholder}
              readOnly={!isLive}
              onChange={handleBackendUrlChange}
              onBlur={handleBackendUrlBlur}
              aria-label={liveBackendUrlLabel}
            />
          </label>

          {liveActions.length ? (
            <div className="coreui-docker-card__actions">
              {liveActions.map((action, idx) => {
                const busy = isLive ? busyActionId === action?.id : false;
                const click = () => handleActionClick(action);
                return (
                  <ConfirmableAction
                    key={isLive ? String(action?.id || idx) : `action-${idx}`}
                    action={action}
                    idx={idx}
                    isLive={isLive}
                    busy={busy}
                    activeAction={activeAction}
                    actionTimerNow={actionTimerNow}
                    onClick={isLive && action?.confirm ? wrapWithConfirm(action, click) : click}
                  />
                );
              })}
            </div>
          ) : null}

          {children}
        </div>

        {liveMeta.length ? (
          <div className="coreui-docker-card__meta-grid">
            {liveMeta.map((entry, idx) => (
              <div key={`${entry.label}-${idx}`} className="coreui-docker-card__meta-cell">
                <span className="coreui-docker-card__meta-label">{entry.label}</span>
                <MetaValue value={entry.value} />
              </div>
            ))}
          </div>
        ) : null}
      </div>
    </div>
  );
}
