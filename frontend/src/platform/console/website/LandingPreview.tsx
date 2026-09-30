import type { MouseEvent } from 'react';
import { LandingView } from '../../../pages/public/LandingView';
import type { LandingContent } from '../../../pages/public/landing/types';

/**
 * Real preview: the SAME component the public site renders, fed the draft (or any version).
 * Links and buttons that would navigate are made inert so the console never leaves the page.
 * Rendered signed-out, exactly as visitors see it.
 */
export default function LandingPreview({ content }: { content: LandingContent }) {
  const stopNavigation = (e: MouseEvent<HTMLDivElement>) => {
    const target = e.target as HTMLElement;
    if (target.closest('a')) e.preventDefault();
  };
  return (
    <div className="overflow-hidden rounded-xl border border-slate-300 bg-white shadow-sm" onClickCapture={stopNavigation}
      data-testid="landing-preview">
      <div className="flex items-center gap-2 border-b border-slate-200 bg-slate-100 px-3 py-2 text-xs text-slate-500">
        <span className="h-2.5 w-2.5 rounded-full bg-rose-400" aria-hidden="true" />
        <span className="h-2.5 w-2.5 rounded-full bg-amber-400" aria-hidden="true" />
        <span className="h-2.5 w-2.5 rounded-full bg-emerald-400" aria-hidden="true" />
        <span className="ml-2 truncate">Preview - not visible to the public until published</span>
      </div>
      <div className="max-h-[75vh] overflow-y-auto">
        <LandingView content={content} isAuthenticated={false} />
      </div>
    </div>
  );
}
