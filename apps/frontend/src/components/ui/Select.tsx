import { Fragment } from "react";
import { Listbox, Transition } from "@headlessui/react";
import { Check, ChevronDown } from "lucide-react";
import { useTranslation } from "react-i18next";

export interface SelectOption {
  value: string;
  label: string;
}

interface SelectProps {
  value: string | string[];
  onChange: (value: string | string[]) => void;
  options: SelectOption[];
  placeholder?: string;
  className?: string;
  direction?: "up" | "down";
  multiple?: boolean;
}

export const Select = ({
  value,
  onChange,
  options,
  placeholder,
  className = "",
  direction = "down",
  multiple = false,
}: SelectProps) => {
  const { t } = useTranslation();
  const resolvedPlaceholder = placeholder ?? t("common.select");
  const isMulti = multiple;
  const listboxValue = isMulti
    ? (Array.isArray(value) ? value : []).filter(Boolean)
    : typeof value === "string"
      ? value
      : "";
  const selectedOptions = isMulti
    ? options.filter((opt) => Array.isArray(value) && value.includes(opt.value))
    : [];
  const selectedOption =
    !isMulti && typeof value === "string"
      ? options.find((opt) => opt.value === value)
      : undefined;
  const displayLabel = isMulti
    ? selectedOptions.length
      ? selectedOptions
          .map((opt) => opt.label)
          .slice(0, 2)
          .join("、") +
        (selectedOptions.length > 2 ? ` 等${selectedOptions.length}个` : "")
      : resolvedPlaceholder
    : selectedOption?.label || resolvedPlaceholder;
  const isFilled = isMulti
    ? selectedOptions.length > 0
    : !!(selectedOption && value);

  const handleChange = (val: string | string[]) => {
    if (isMulti) {
      onChange(Array.isArray(val) ? val : []);
    } else {
      onChange(typeof val === "string" ? val : "");
    }
  };

  return (
    <Listbox value={listboxValue} onChange={handleChange} multiple={isMulti}>
      {({ open }) => (
        <div className={`relative ${className}`}>
          <Listbox.Button className="w-full theme-surface border theme-border rounded-xl px-4 py-3 text-sm font-medium theme-text outline-none transition-all shadow-sm hover:shadow-md cursor-pointer text-left flex items-center justify-between theme-accent-text-hover focus:ring-2 focus:ring-[var(--theme-primary)]/20 focus:border-[var(--theme-primary)]">
            <span
              className={
                isFilled ? "theme-text font-semibold" : "theme-text-muted"
              }
            >
              {displayLabel}
            </span>
            <ChevronDown
              size={16}
              className={`theme-text-muted transition-transform duration-200 ${open ? "rotate-180" : ""}`}
            />
          </Listbox.Button>

          <Transition
            as={Fragment}
            enter="transition ease-out duration-100"
            enterFrom="transform opacity-0 scale-95"
            enterTo="transform opacity-100 scale-100"
            leave="transition ease-in duration-75"
            leaveFrom="transform opacity-100 scale-100"
            leaveTo="transform opacity-0 scale-95"
          >
            <Listbox.Options
              className={`absolute w-full theme-surface border theme-border rounded-2xl shadow-2xl py-2 z-50 max-h-60 overflow-auto focus:outline-none custom-scrollbar ${
                direction === "up" ? "bottom-full mb-2" : "mt-2"
              }`}
            >
              {options.map((option) => (
                <Listbox.Option
                  key={option.value}
                  value={option.value}
                  disabled={option.value === ""}
                  className={({ active, disabled }) =>
                    `relative cursor-pointer select-none py-3 px-4 transition-colors theme-text ${
                      disabled ? "opacity-50 cursor-not-allowed" : ""
                    } ${active && !disabled ? "nav-active" : ""}`
                  }
                >
                  {({ selected, active }) => (
                    <div className="flex items-center justify-between">
                      <span
                        className={`block truncate ${selected ? "font-semibold" : "font-medium"}`}
                      >
                        {option.label}
                      </span>
                      {selected && option.value && (
                        <Check size={16} className="theme-accent-text" />
                      )}
                    </div>
                  )}
                </Listbox.Option>
              ))}
            </Listbox.Options>
          </Transition>
        </div>
      )}
    </Listbox>
  );
};
