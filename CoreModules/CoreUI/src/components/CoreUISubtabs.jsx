import "../styles/components/CoreUISubtabs.css";

function defaultGetKey(tab) {
  return tab.id;
}

function defaultGetLabel(tab) {
  return tab.label;
}

export default function CoreUISubtabs({
  tabs,
  value,
  onChange,
  ariaLabel,
  ariaLabelledBy,
  className = "",
  getKey = defaultGetKey,
  getLabel = defaultGetLabel,
  getButtonProps,
}) {
  const rootClassName = ["coreui-subtabs", className].filter(Boolean).join(" ");

  return (
    <div
      className={rootClassName}
      role="tablist"
      aria-label={ariaLabel}
      aria-labelledby={ariaLabelledBy}
    >
      {tabs.map((tab, index) => {
        const key = getKey(tab, index);
        const selected = value === key;
        const extraProps = getButtonProps ? getButtonProps(tab, index) || {} : {};
        const { className: buttonClassName = "", ...buttonProps } = extraProps;
        return (
          <button
            key={String(key)}
            type="button"
            role="tab"
            aria-selected={selected}
            className={[
              "coreui-subtab",
              selected && "coreui-subtab-active",
              buttonClassName,
            ]
              .filter(Boolean)
              .join(" ")}
            onClick={() => onChange?.(key, tab)}
            {...buttonProps}
          >
            {getLabel(tab, index)}
          </button>
        );
      })}
    </div>
  );
}
