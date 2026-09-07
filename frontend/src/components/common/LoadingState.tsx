import React from 'react';
import { cn } from '../../utils/cn';
import { Loader2 } from 'lucide-react';

export function LoadingSpinner({
  size = 'md',
  className,
}: {
  size?: 'sm' | 'md' | 'lg';
  className?: string;
}) {
  const sizes = {
    sm: 'w-4 h-4',
    md: 'w-6 h-6',
    lg: 'w-8 h-8',
  };

  return (
    <Loader2
      className={cn('animate-spin text-brand-600', sizes[size], className)}
    />
  );
}

export function Skeleton({
  className,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn('animate-pulse rounded-md bg-slate-200/80', className)}
      {...props}
    />
  );
}

export function LoadingCard() {
  return (
    <div className="bg-white p-5 rounded-xl border border-slate-200 shadow-card space-y-3">
      <Skeleton className="h-4 w-1/3" />
      <Skeleton className="h-8 w-1/2" />
      <Skeleton className="h-3 w-2/3" />
    </div>
  );
}

export function LoadingState({
  message = 'Loading data...',
  className,
}: {
  message?: string;
  className?: string;
}) {
  return (
    <div
      className={cn(
        'w-full py-16 flex flex-col items-center justify-center text-center',
        className
      )}
    >
      <LoadingSpinner size="lg" />
      <p className="mt-3 text-xs font-medium text-slate-500">{message}</p>
    </div>
  );
}
