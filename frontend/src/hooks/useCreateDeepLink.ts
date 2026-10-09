import { useEffect } from 'react';
import { useSearchParams } from 'react-router-dom';

/** True when the URL asks a list page to start creating a record: `?action=new` or `?new=<kind>`. */
export function isCreateRequested(params: URLSearchParams): boolean {
  return params.get('action') === 'new' || Boolean(params.get('new'));
}

/**
 * Quick-action deep links (`/payments?new=1`, `/catalog?new=product`, `?action=new`): when the
 * page is opened with one, run `onCreate` (open the create form) once `enabled`, then drop the
 * parameter so closing the form or reloading does not open it again.
 */
export function useCreateDeepLink(onCreate: (kind: string) => void, enabled = true): void {
  const [searchParams, setSearchParams] = useSearchParams();
  const requested = isCreateRequested(searchParams);
  useEffect(() => {
    if (!requested || !enabled) return;
    onCreate(searchParams.get('new') || 'new');
    const next = new URLSearchParams(searchParams);
    next.delete('action');
    next.delete('new');
    setSearchParams(next, { replace: true });
    // Runs when a request appears (or becomes allowed), not on every render of onCreate.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [requested, enabled]);
}
