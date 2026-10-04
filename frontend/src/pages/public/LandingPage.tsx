import { useEffect, useState } from 'react';
import { useAuth } from '../../hooks/useAuth';
import { API_BASE_URL } from '../../services/apiClient';
import { LandingView } from './LandingView';
import { applySeo, fetchPublishedLanding } from './landing/content';
import type { LandingContent } from './landing/types';

/**
 * Public landing page. Renders the PUBLISHED website content managed in the platform console
 * (Website -> Landing page); falls back to the bundled original content if the API is unreachable.
 */
export function LandingPage() {
  const { isAuthenticated } = useAuth();
  const [content, setContent] = useState<LandingContent | null>(null);

  useEffect(() => {
    let cancelled = false;
    void fetchPublishedLanding(API_BASE_URL).then((published) => {
      if (cancelled) return;
      applySeo(published);
      setContent(published);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  if (!content) {
    return <div className="min-h-screen bg-[#F8F9FD]" aria-busy="true" />;
  }
  return <LandingView content={content} isAuthenticated={isAuthenticated} />;
}
