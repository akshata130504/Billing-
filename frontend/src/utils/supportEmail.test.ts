import { describe, expect, it } from 'vitest';
import { buildSupportMailto, resolveSupportEmail } from './supportEmail';

describe('resolveSupportEmail', () => {
  it('returns the trimmed address when configured', () => {
    expect(resolveSupportEmail('  support@rooman.example ')).toBe('support@rooman.example');
  });

  it('returns an empty string when unset, blank or invalid', () => {
    expect(resolveSupportEmail(undefined)).toBe('');
    expect(resolveSupportEmail(null)).toBe('');
    expect(resolveSupportEmail('   ')).toBe('');
    expect(resolveSupportEmail('not-an-email')).toBe('');
    expect(resolveSupportEmail('a@b.com?cc=evil@x.com')).toBe('');
  });
});

describe('buildSupportMailto', () => {
  it('builds a mailto link with URL-encoded subject and body', () => {
    const url = buildSupportMailto(
      'support@rooman.example',
      'Rooman Billing support request',
      'Line 1 & more?\nLine 2: 100% done #1'
    );
    expect(url).toBe(
      'mailto:support@rooman.example' +
        '?subject=Rooman%20Billing%20support%20request' +
        '&body=Line%201%20%26%20more%3F%0ALine%202%3A%20100%25%20done%20%231'
    );
    const parsed = new URL(url as string);
    expect(parsed.protocol).toBe('mailto:');
    expect(parsed.searchParams.get('subject')).toBe('Rooman Billing support request');
    expect(parsed.searchParams.get('body')).toBe('Line 1 & more?\nLine 2: 100% done #1');
  });

  it('returns null (no broken link) when no support email is configured', () => {
    expect(buildSupportMailto('', 'Subject', 'Body')).toBeNull();
    expect(buildSupportMailto('   ', 'Subject', 'Body')).toBeNull();
    expect(buildSupportMailto('invalid', 'Subject', 'Body')).toBeNull();
  });
});
