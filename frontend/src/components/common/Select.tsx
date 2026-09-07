import React, { forwardRef, useId } from 'react';
import { cn } from '../../utils/cn';
import { ChevronDown } from 'lucide-react';

export interface SelectOption {
  value: string | number;
  label: string;
  disabled?: boolean;
}

export interface SelectProps extends React.SelectHTMLAttributes<HTMLSelectElement> {
  label?: string;
  helperText?: string;
  error?: string;
  options?: SelectOption[];
  placeholder?: string;
}

export const Select = forwardRef<HTMLSelectElement, SelectProps>(
  (
    {
      className,
      label,
      helperText,
      error,
      options,
      placeholder,
      id: customId,
      disabled,
      children,
      ...props
    },
    ref
  ) => {
    const generatedId = useId();
    const id = customId || generatedId;

    return (
      <div className="w-full">
        {label && (
          <label
            htmlFor={id}
            className="block text-xs font-medium text-slate-700 mb-1.5"
          >
            {label}
            {props.required && <span className="text-rose-500 ml-0.5">*</span>}
          </label>
        )}
        <div className="relative rounded-lg shadow-subtle">
          <select
            ref={ref}
            id={id}
            disabled={disabled}
            className={cn(
              'block w-full appearance-none rounded-lg border bg-white px-3 py-2 pr-9 text-sm text-slate-900 transition-colors',
              'focus:outline-none focus:ring-2 focus:ring-brand-500 focus:border-brand-500',
              'disabled:bg-slate-50 disabled:text-slate-400 disabled:cursor-not-allowed',
              error
                ? 'border-rose-300 text-rose-900 focus:ring-rose-500 focus:border-rose-500'
                : 'border-slate-300 hover:border-slate-400',
              className
            )}
            {...props}
          >
            {placeholder && (
              <option value="" disabled selected>
                {placeholder}
              </option>
            )}
            {options
              ? options.map((opt) => (
                  <option key={opt.value} value={opt.value} disabled={opt.disabled}>
                    {opt.label}
                  </option>
                ))
              : children}
          </select>
          <div className="absolute inset-y-0 right-0 pr-2.5 flex items-center pointer-events-none text-slate-400">
            <ChevronDown className="w-4 h-4" />
          </div>
        </div>
        {error ? (
          <p className="mt-1 text-xs text-rose-600 font-medium">{error}</p>
        ) : helperText ? (
          <p className="mt-1 text-xs text-slate-500">{helperText}</p>
        ) : null}
      </div>
    );
  }
);

Select.displayName = 'Select';
