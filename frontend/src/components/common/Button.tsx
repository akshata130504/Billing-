import React, { forwardRef } from 'react';
import { cn } from '../../utils/cn';
import { Loader2 } from 'lucide-react';

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'secondary' | 'outline' | 'ghost' | 'danger';
  size?: 'sm' | 'md' | 'lg';
  isLoading?: boolean;
  leadingIcon?: React.ReactNode;
  trailingIcon?: React.ReactNode;
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  (
    {
      className,
      variant = 'primary',
      size = 'md',
      isLoading = false,
      leadingIcon,
      trailingIcon,
      disabled,
      children,
      ...props
    },
    ref
  ) => {
    const baseStyles =
      'inline-flex items-center justify-center font-medium rounded-lg transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2 disabled:opacity-50 disabled:pointer-events-none select-none';

    const variants = {
      primary:
        'bg-brand-600 text-white hover:bg-brand-700 active:bg-brand-800 shadow-sm',
      secondary:
        'bg-slate-100 text-slate-800 hover:bg-slate-200 active:bg-slate-300 border border-slate-200',
      outline:
        'border border-slate-300 text-slate-700 bg-white hover:bg-slate-50 hover:text-slate-900 active:bg-slate-100',
      ghost:
        'text-slate-600 hover:bg-slate-100 hover:text-slate-900 active:bg-slate-200',
      danger:
        'bg-rose-600 text-white hover:bg-rose-700 active:bg-rose-800 shadow-sm focus-visible:ring-rose-500',
    };

    const sizes = {
      sm: 'text-xs px-2.5 py-1.5 gap-1.5 h-8',
      md: 'text-sm px-3.5 py-2 gap-2 h-9',
      lg: 'text-base px-4 py-2.5 gap-2.5 h-11',
    };

    return (
      <button
        ref={ref}
        disabled={disabled || isLoading}
        aria-busy={isLoading}
        className={cn(baseStyles, variants[variant], sizes[size], 'flex flex-row items-center whitespace-nowrap', className)}
        {...props}
      >
        {isLoading ? (
          <Loader2 className="w-4 h-4 animate-spin text-current shrink-0" />
        ) : (
          leadingIcon && <span className="inline-flex shrink-0 items-center justify-center">{leadingIcon}</span>
        )}
        <span className="truncate">{children}</span>
        {!isLoading && trailingIcon && (
          <span className="inline-flex shrink-0 items-center justify-center">{trailingIcon}</span>
        )}
      </button>
    );
  }
);

Button.displayName = 'Button';
