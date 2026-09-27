/** Where to send a user after sign-in, taken from the router state ProtectedRoute left behind. */
export interface RedirectState {
  from?: { pathname?: string; search?: string };
}

/**
 * Only same-origin app paths: reject protocol-relative ("//x") and backslash ("/\x") forms
 * (react-router 6.x open-redirect advisory GHSA-wrjc-x8rr-h8h6).
 */
export function isSafeAppPath(path?: string): path is string {
  return !!path && path.startsWith('/') && !/^\/[\\/]/.test(path) && !path.includes('\\');
}

export function postLoginRedirect(state: unknown, fallback = '/dashboard'): string {
  const from = (state as RedirectState | null | undefined)?.from;
  if (!from || !isSafeAppPath(from.pathname)) return fallback;
  return `${from.pathname}${from.search ?? ''}`;
}
