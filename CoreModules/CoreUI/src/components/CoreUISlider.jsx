import { useId } from "react";
import "../styles/components/CoreUISlider.css";

function joinClasses(parts) {
  return parts.filter(Boolean).join(" ");
}

export default function CoreUISlider({
  label,
  valueText,
  className = "",
  inputClassName = "",
  id,
  ...inputProps
}) {
  const generatedId = useId();
  const controlId = id || generatedId;
  const displayValue = valueText ?? inputProps.value ?? "";

  return (
    <label className={joinClasses(["coreui-slider-field", className])} htmlFor={controlId}>
      <span className="coreui-slider-title">
        <span>{label}</span>
        <strong>{displayValue}</strong>
      </span>
      <input
        {...inputProps}
        id={controlId}
        type="range"
        className={joinClasses(["coreui-slider", inputClassName])}
        aria-label={inputProps["aria-label"] || label}
      />
    </label>
  );
}
