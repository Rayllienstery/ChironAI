import "../styles/components/CoreUISubtabs.css";

function defaultGetKey(tab) {
  return tab.id;
}

function defaultGetLabel(tab) {
  return tab.label;
}

/**
 * Sub-navigation tab strip. Thinner visual style than CoreUIPillTabs.
 *
 * @param {Object} props
 * @param {Array<{id,label}>} props.tabs - Tab definitions.
 * @param {string} props.value - Currently selected tab id.
 * @param {Function} [props.onChange] - `(key, tab) => void` callback when a tab is clicked.
 * @param {string} [props.ariaLabel] - Aria label for the tablist.
 * @param {string} [props.ariaLabelledBy] - Aria labelledby for the tablist.
 * @param {string} [props.className] - Wrapper class.
 * @param {Function} [props.getKey] - Custom key extractor: `(tab, index) => string`.
 * @param {Function} [props.getLabel] - Custom label extractor: `(tab, index) => string`.
 * @param {Function} [props.getButtonProps] - Extra props injector: `(tab, index) => object`.
 */
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
