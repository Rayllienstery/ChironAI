import type { FieldState } from './comparePayload';

type FieldInputProps = {
  fieldKey: string;
  label: string;
  value: string;
  secret?: boolean;
  placeholder?: string;
  autosaveActionId?: string;
  className?: string;
  onChange: (key: string, value: string) => void;
  onAutosave?: (actionId: string, key: string) => void;
};

export default function ExtensionRuntimeFieldInput({
  fieldKey,
  label,
  value,
  secret = false,
  placeholder = '',
  autosaveActionId = '',
  className = 'extensions-runtime-item',
  onChange,
  onAutosave,
}: FieldInputProps) {
  return (
    <label className={className}>
      <span>{label}</span>
      <input
        type={secret ? 'password' : 'text'}
        value={value}
        placeholder={placeholder}
        onChange={(e) => onChange(fieldKey, e.target.value)}
        onBlur={() => {
          const resolved = String(autosaveActionId || '').trim();
          if (!resolved || !onAutosave) return;
          onAutosave(resolved, fieldKey);
        }}
      />
    </label>
  );
}

export type { FieldState };
