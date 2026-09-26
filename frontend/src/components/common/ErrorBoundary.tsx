import { Component, type ErrorInfo, type ReactNode } from 'react';
import { AlertOctagon, RotateCw } from 'lucide-react';

export interface ErrorBoundaryProps {
  children: ReactNode;
  /**
   * When this value changes the boundary clears its error state, e.g. pass the
   * current pathname so navigating away from a crashed page recovers.
   */
  resetKey?: unknown;
  /** Render a full-screen fallback (top-level boundary) instead of an inline card. */
  fullScreen?: boolean;
}

interface ErrorBoundaryState {
  error: Error | null;
}

/**
 * Catches render/lifecycle errors in its subtree and shows a friendly fallback
 * with a reload button instead of a blank white screen.
 */
export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  state: ErrorBoundaryState = { error: null };

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    // Kept intentionally: this is the only record of an otherwise silent crash.
    console.error('Unhandled UI error', error, info.componentStack);
  }

  componentDidUpdate(prevProps: ErrorBoundaryProps): void {
    if (this.state.error && !Object.is(prevProps.resetKey, this.props.resetKey)) {
      this.setState({ error: null });
    }
  }

  private handleRetry = () => {
    this.setState({ error: null });
  };

  private handleReload = () => {
    window.location.reload();
  };

  render() {
    if (!this.state.error) return this.props.children;

    const card = (
      <div
        role="alert"
        className="w-full max-w-md mx-auto py-10 px-6 flex flex-col items-center text-center bg-white rounded-2xl border border-slate-200 shadow-card"
      >
        <div className="p-3 rounded-full bg-rose-100 text-rose-600 mb-3">
          <AlertOctagon className="w-6 h-6" />
        </div>
        <h2 className="text-base font-semibold text-slate-900">Something went wrong</h2>
        <p className="mt-1 text-xs text-slate-500 max-w-sm leading-relaxed">
          This part of the app hit an unexpected error. Your data is safe. Try again, or reload the
          page if the problem persists.
        </p>
        <div className="mt-5 flex items-center gap-2">
          {!this.props.fullScreen && (
            <button
              type="button"
              onClick={this.handleRetry}
              className="inline-flex items-center h-8 px-3 text-xs font-medium rounded-lg border border-slate-300 bg-white text-slate-700 hover:bg-slate-50"
            >
              Try again
            </button>
          )}
          <button
            type="button"
            onClick={this.handleReload}
            className="inline-flex items-center gap-1.5 h-8 px-3 text-xs font-medium rounded-lg bg-brand-600 text-white hover:bg-brand-700"
          >
            <RotateCw className="w-3.5 h-3.5" />
            Reload page
          </button>
        </div>
      </div>
    );

    if (this.props.fullScreen) {
      return (
        <div className="min-h-screen flex items-center justify-center bg-slate-50 p-4">{card}</div>
      );
    }
    return <div className="py-12">{card}</div>;
  }
}
