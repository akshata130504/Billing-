/**
 * "Contact support by email" helpers. There is no in-app ticketing backend, so Help & Support
 * only ever drafts an email in the user's mail client - it never claims a ticket was created.
 */

/** Conservative address check so a misconfigured value can never inject `?`/`&` mailto params. */
const SUPPORT_EMAIL_RE = /^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$/;

/** Normalises the configured support mailbox (VITE_SUPPORT_EMAIL); '' when unset or invalid. */
export function resolveSupportEmail(raw: string | undefined | null): string {
  const value = (raw ?? '').trim();
  return SUPPORT_EMAIL_RE.test(value) ? value : '';
}

/**
 * Builds `mailto:<address>?subject=...&body=...` with subject and body URL-encoded
 * (RFC 6068: spaces as %20, line breaks as %0A). Returns null when no support address is
 * configured, so callers never render a broken `mailto:` link.
 */
export function buildSupportMailto(email: string, subject: string, body: string): string | null {
  const address = resolveSupportEmail(email);
  if (!address) return null;
  return `mailto:${address}?subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(body)}`;
}

export const SUPPORT_EMAIL: string = resolveSupportEmail(
  import.meta.env.VITE_SUPPORT_EMAIL as string | undefined
);
