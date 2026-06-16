import { useId } from "react";
import "../styles/components/CoreUISlider.css";

function joinClasses(parts) {
  return parts.filter(Boolean).join(" ");
}

/**
 * Slider field with a label and a displayed value.
 * Wraps a native `<input type="range">` and forwards all standard range input attributes.
 *
 * @param {Object} props
 * @param {string} [props.label] - Label text shown above the slider.
 * @param {string} [props.valueText] - Value text to display next to the label.
 * @param {string} [props.className] - Wrapper class.
 * @param {string} [props.inputClassName] - Class for the input element.
 * @param {string} [props.id] - Optional id; auto-generated if omitted.
 * @param {string} [props.min] - Minimum value for the range input.
 * @param {string} [props.max] - Maximum value for the range input.
 * @param {string} [props.step] - Step increment for the range input.
 * @param {string} [props.value] - Current slider value.
 * @param {Function} [props.onChange] - Change handler for the range input.
 * @param {string} [props.aria-label] - Accessible label for the range input.
 */
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
