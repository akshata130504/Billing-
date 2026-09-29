import React, { useId } from 'react';
import RHFPhoneInput, { type Country } from 'react-phone-number-input';
import 'react-phone-number-input/style.css';
import { cn } from '../../utils/cn';
import { toE164Phone } from '../../utils/validation';

export interface PhoneInputProps {
  label?: string;
  helperText?: string;
  error?: string;
  required?: boolean;
  /** E.164 value, e.g. "+919876543210". */
  value?: string | null;
  onChange: (value: string) => void;
  placeholder?: string;
  disabled?: boolean;
  /** ISO 3166-1 alpha-2 country to preselect when the field is empty. */
  defaultCountry?: Country;
  id?: string;
  className?: string;
}

/**
 * Phone number field with a country flag / dial-code selector (like most billing
 * and checkout forms). Stores and emits the number in E.164 form (e.g.
 * "+919876543210"), which the existing backend phone validation already accepts.
 */
export const PhoneInput: React.FC<PhoneInputProps> = ({
  label,
  helperText,
  error,
  required,
  value,
  onChange,
  placeholder = 'Phone number',
  disabled,
  defaultCountry = 'IN',
  id: customId,
  className,
}) => {
  const generatedId = useId();
  const id = customId || generatedId;

  return (
    <div className="w-full">
      {label && (
        <label htmlFor={id} className="block text-xs font-medium text-slate-700 mb-1.5">
          {label}
          {required && <span className="text-rose-500 ml-0.5">*</span>}
        </label>
      )}
      <div
        className={cn(
          'rooman-phone-input flex items-center rounded-lg border bg-white px-3 shadow-subtle transition-colors',
          'focus-within:ring-2 focus-within:ring-brand-500 focus-within:border-brand-500',
          error
            ? 'border-rose-300 focus-within:ring-rose-500 focus-within:border-rose-500'
            : 'border-slate-300 hover:border-slate-400',
          disabled && 'bg-slate-50 cursor-not-allowed',
          className
        )}
      >
        <RHFPhoneInput
          id={id}
          international
          defaultCountry={defaultCountry}
          value={toE164Phone(value, defaultCountry)}
          onChange={(v) => onChange(v ?? '')}
          placeholder={placeholder}
          disabled={disabled}
          numberInputProps={{
            className:
              'flex-1 min-w-0 border-0 bg-transparent py-2 text-sm text-slate-900 placeholder:text-slate-400 focus:outline-none focus:ring-0 disabled:cursor-not-allowed',
          }}
        />
      </div>
      {error ? (
        <p className="mt-1 text-xs text-rose-600 font-medium">{error}</p>
      ) : helperText ? (
        <p className="mt-1 text-xs text-slate-500">{helperText}</p>
      ) : null}
    </div>
  );
};

PhoneInput.displayName = 'PhoneInput';
