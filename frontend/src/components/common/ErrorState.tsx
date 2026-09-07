import { cn } from '../../utils/cn';
import { AlertOctagon, RotateCw } from 'lucide-react';
import { Button } from './Button';

export interface ErrorStateProps {
  title?: string;
  message?: string;
  onRetry?: () => void;
  className?: string;
}

export function ErrorState({
  title = 'Something went wrong',
  message = 'We encountered an error loading this data. Please try again.',
  onRetry,
  className,
}: ErrorStateProps) {
  return (
    <div
      className={cn(
        'w-full py-10 px-6 flex flex-col items-center justify-center text-center bg-rose-50/50 rounded-xl border border-rose-200',
        className
      )}
    >
      <div className="p-3 rounded-full bg-rose-100 text-rose-600 mb-3">
        <AlertOctagon className="w-6 h-6" />
      </div>
      <h4 className="text-sm font-semibold text-rose-950">{title}</h4>
      <p className="mt-1 text-xs text-rose-700 max-w-sm leading-relaxed">
        {message}
      </p>
      {onRetry && (
        <div className="mt-4">
          <Button
            variant="outline"
            size="sm"
            onClick={onRetry}
            leadingIcon={<RotateCw className="w-3.5 h-3.5" />}
          >
            Retry
          </Button>
        </div>
      )}
    </div>
  );
}
