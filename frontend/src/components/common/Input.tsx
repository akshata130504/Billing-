import React, { forwardRef, useId } from 'react';
import { cn } from '../../utils/cn';

export interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  helperText?: string;
  error?: string;
  leadingIcon?: React.ReactNode;
  trailingIcon?: React.ReactNode;
}

export const Input = forwardRef<HTMLInputElement, InputProps>(
  (
    {
      className,
      label,
      helperText,
      error,
      leadingIcon,
      trailingIcon,
      id: customId,
      disabled,
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
          {leadingIcon && (
            <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none text-slate-400">
              {leadingIcon}
            </div>
          )}
          <input
            ref={ref}
            id={id}
            disabled={disabled}
            className={cn(
              'block w-full rounded-lg border bg-white px-3 py-2 text-sm text-slate-900 placeholder:text-slate-400 transition-colors',
              'focus:outline-none focus:ring-2 focus:ring-brand-500 focus:border-brand-500',
              'disabled:bg-slate-50 disabled:text-slate-400 disabled:cursor-not-allowed',
              leadingIcon ? 'pl-9' : 'pl-3',
              trailingIcon ? 'pr-9' : 'pr-3',
              error
                ? 'border-rose-300 text-rose-900 focus:ring-rose-500 focus:border-rose-500'
                : 'border-slate-300 hover:border-slate-400',
              className
            )}
            {...props}
          />
          {trailingIcon && (
            <div className="absolute inset-y-0 right-0 pr-3 flex items-center pointer-events-none text-slate-400">
              {trailingIcon}
            </div>
          )}
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

Input.displayName = 'Input';
