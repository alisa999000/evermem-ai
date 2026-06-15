type Props = {
  checked: boolean;
  onChange: (checked: boolean) => void;
  label?: string;
};

export function Switch({ checked, onChange, label }: Props) {
  return (
    <label className="inline-flex items-center gap-2 cursor-pointer select-none">
      {label && (
        <span className="text-xs text-em-muted dark:text-em-d-muted">{label}</span>
      )}
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        onClick={() => onChange(!checked)}
        className={`
          relative w-8 h-[18px] rounded-full transition-colors duration-200
          ${checked ? "bg-em-accent" : "bg-gray-300 dark:bg-gray-600"}
        `}
      >
        <span
          className={`
            absolute top-[2px] left-[2px] w-3.5 h-3.5 rounded-full bg-white shadow-sm
            transition-transform duration-200
            ${checked ? "translate-x-[14px]" : "translate-x-0"}
          `}
        />
      </button>
    </label>
  );
}
