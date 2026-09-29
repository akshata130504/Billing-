import { describe, expect, it } from 'vitest';
import { isSafeAppPath, postLoginRedirect } from './redirect';

describe('postLoginRedirect', () => {
  it('returns the page the user was sent away from, with its query string', () => {
    expect(postLoginRedirect({ from: { pathname: '/invoices', search: '?status=overdue' } })).toBe(
      '/invoices?status=overdue'
    );
  });

  it('falls back to the dashboard without state', () => {
    expect(postLoginRedirect(null)).toBe('/dashboard');
    expect(postLoginRedirect(undefined)).toBe('/dashboard');
    expect(postLoginRedirect({})).toBe('/dashboard');
  });

  it('rejects open-redirect forms', () => {
    expect(postLoginRedirect({ from: { pathname: '//evil.example' } })).toBe('/dashboard');
    expect(postLoginRedirect({ from: { pathname: '/\\evil.example' } })).toBe('/dashboard');
    expect(postLoginRedirect({ from: { pathname: 'https://evil.example' } })).toBe('/dashboard');
    expect(isSafeAppPath('/customers/1')).toBe(true);
  });
});
