import { LoadingSpinner } from './LoadingState';

/** Suspense fallback shown while a lazily-loaded route chunk downloads. */
export function PageLoader({ fullScreen = false }: { fullScreen?: boolean }) {
  return (
    <div
      role="status"
      aria-live="polite"
      className={
        fullScreen
          ? 'min-h-screen flex items-center justify-center bg-slate-50'
          : 'w-full py-24 flex items-center justify-center'
      }
    >
      <LoadingSpinner size="lg" />
      <span className="sr-only">Loading page…</span>
    </div>
  );
}
