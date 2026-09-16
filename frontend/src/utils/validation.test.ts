import { describe, expect, it } from 'vitest';
import {
  parseStrictNumber,
  validateRequiredText,
  validateSensibleName,
  validateEmail,
  normalizeEmail,
  validatePhone,
  validateUrl,
  validateGstin,
  validatePan,
  validateHsnSac,
  validateSlug,
  validateSku,
  validateCountryCode,
  validatePostalCode,
  validatePercentage,
  validatePositiveMoney,
  validateNonNegativeMoney,
  validatePositiveQuantity,
  validatePositiveInteger,
  validateNonNegativeInteger,
  validateDescription,
  validateDateNotBefore,
} from './validation';

describe('parseStrictNumber', () => {
  it('parses clean numeric input', () => {
    expect(parseStrictNumber('100')).toBe(100);
    expect(parseStrictNumber('100.5')).toBe(100.5);
    expect(parseStrictNumber(42)).toBe(42);
  });

  it('rejects text with trailing garbage instead of truncating it', () => {
    expect(parseStrictNumber('100abc')).toBeNull();
    expect(parseStrictNumber('abc')).toBeNull();
  });

  it('rejects empty, nullish, NaN and non-finite input', () => {
    expect(parseStrictNumber('')).toBeNull();
    expect(parseStrictNumber('   ')).toBeNull();
    expect(parseStrictNumber(null)).toBeNull();
    expect(parseStrictNumber(undefined)).toBeNull();
    expect(parseStrictNumber('NaN')).toBeNull();
    expect(parseStrictNumber('Infinity')).toBeNull();
    expect(parseStrictNumber(Infinity)).toBeNull();
  });
});

describe('validateRequiredText', () => {
  it('rejects empty and whitespace-only values', () => {
    expect(validateRequiredText('', 'Name')).toMatch(/required/i);
    expect(validateRequiredText('   ', 'Name')).toMatch(/required/i);
    expect(validateRequiredText(null, 'Name')).toMatch(/required/i);
  });

  it('accepts non-empty text', () => {
    expect(validateRequiredText('hello', 'Name')).toBeNull();
  });
});

describe('validateSensibleName', () => {
  it('rejects empty/whitespace-only names', () => {
    expect(validateSensibleName('', 'Name')).not.toBeNull();
    expect(validateSensibleName('   ', 'Name')).not.toBeNull();
  });

  it('rejects purely numeric names', () => {
    expect(validateSensibleName('123456', 'Name')).not.toBeNull();
  });

  it('accepts legitimate business names containing numbers/symbols', () => {
    expect(validateSensibleName('Rooman Technologies 2.0', 'Name')).toBeNull();
    expect(validateSensibleName('A&B Enterprises', 'Name')).toBeNull();
    expect(validateSensibleName("St. John's Hospital", 'Name')).toBeNull();
    expect(validateSensibleName('Windows Server 2026', 'Name')).toBeNull();
    expect(validateSensibleName('Plan 360', 'Name')).toBeNull();
  });

  it('accepts short names/initials', () => {
    expect(validateSensibleName('A', 'Name')).toBeNull();
  });
});

describe('validateEmail', () => {
  it('rejects malformed emails', () => {
    expect(validateEmail('not-an-email')).not.toBeNull();
    expect(validateEmail('missing@domain')).not.toBeNull();
    expect(validateEmail('@nodomain.com')).not.toBeNull();
  });

  it('accepts valid emails and treats empty as valid when not required', () => {
    expect(validateEmail('user@example.com')).toBeNull();
    expect(validateEmail('')).toBeNull();
    expect(validateEmail('', { required: true })).not.toBeNull();
  });
});

describe('normalizeEmail', () => {
  it('trims and lowercases', () => {
    expect(normalizeEmail('  User@Example.COM  ')).toBe('user@example.com');
  });
});

describe('validatePhone', () => {
  it('rejects alphabetic garbage', () => {
    expect(validatePhone('abcdef')).not.toBeNull();
    expect(validatePhone('call-me-maybe')).not.toBeNull();
  });

  it('rejects too-short/too-long numbers', () => {
    expect(validatePhone('123')).not.toBeNull();
    expect(validatePhone('1'.repeat(20))).not.toBeNull();
  });

  it('accepts legitimate formats', () => {
    expect(validatePhone('+91 98765 43210')).toBeNull();
    expect(validatePhone('(022) 4567-8900')).toBeNull();
    expect(validatePhone('9876543210')).toBeNull();
  });
});

describe('validateUrl', () => {
  it('rejects arbitrary text', () => {
    expect(validateUrl('hello world')).not.toBeNull();
  });

  it('accepts http(s) URLs, adding a scheme when missing', () => {
    expect(validateUrl('https://example.com')).toBeNull();
    expect(validateUrl('example.com')).toBeNull();
  });
});

describe('validateGstin', () => {
  it('rejects malformed GSTIN', () => {
    expect(validateGstin('INVALIDGSTIN')).not.toBeNull();
    expect(validateGstin('29ABCDE1234F1Z')).not.toBeNull();
  });

  it('accepts a valid GSTIN', () => {
    expect(validateGstin('29ABCDE1234F1Z5')).toBeNull();
    expect(validateGstin('29abcde1234f1z5')).toBeNull();
  });
});

describe('validatePan', () => {
  it('rejects malformed PAN', () => {
    expect(validatePan('INVALID')).not.toBeNull();
    expect(validatePan('ABCDE12345')).not.toBeNull();
  });

  it('accepts a valid PAN', () => {
    expect(validatePan('ABCDE1234F')).toBeNull();
  });
});

describe('validateHsnSac', () => {
  it('rejects non-digit codes', () => {
    expect(validateHsnSac('ABCD')).not.toBeNull();
    expect(validateHsnSac('12-34')).not.toBeNull();
  });

  it('accepts 2-8 digit codes', () => {
    expect(validateHsnSac('9983')).toBeNull();
    expect(validateHsnSac('998314')).toBeNull();
  });
});

describe('validateSlug', () => {
  it('rejects spaces and symbols', () => {
    expect(validateSlug('not a slug!', 'Slug')).not.toBeNull();
  });

  it('accepts lowercase-hyphen slugs', () => {
    expect(validateSlug('acme-corp', 'Slug')).toBeNull();
  });
});

describe('validateSku', () => {
  it('rejects spaces', () => {
    expect(validateSku('bad sku with spaces')).not.toBeNull();
  });

  it('accepts mixed-case identifiers', () => {
    expect(validateSku('HOST-abc123')).toBeNull();
    expect(validateSku('STARTER-a1b2')).toBeNull();
  });
});

describe('validateCountryCode', () => {
  it('rejects non-2-letter codes', () => {
    expect(validateCountryCode('12')).not.toBeNull();
    expect(validateCountryCode('IND')).not.toBeNull();
  });

  it('accepts a 2-letter code', () => {
    expect(validateCountryCode('in')).toBeNull();
  });
});

describe('validatePostalCode', () => {
  it('rejects too-short/garbage values', () => {
    expect(validatePostalCode('a')).not.toBeNull();
  });

  it('accepts common formats', () => {
    expect(validatePostalCode('560001')).toBeNull();
    expect(validatePostalCode('SW1A 1AA')).toBeNull();
  });
});

describe('validatePercentage', () => {
  it('rejects negative and over-100 values', () => {
    expect(validatePercentage(-1, 'Tax rate')).not.toBeNull();
    expect(validatePercentage(101, 'Tax rate')).not.toBeNull();
  });

  it('rejects non-numeric text', () => {
    expect(validatePercentage('abc', 'Tax rate')).not.toBeNull();
  });

  it('accepts 0-100', () => {
    expect(validatePercentage(0, 'Tax rate')).toBeNull();
    expect(validatePercentage(100, 'Tax rate')).toBeNull();
    expect(validatePercentage(18, 'Tax rate')).toBeNull();
  });
});

describe('validatePositiveMoney', () => {
  it('rejects zero and negative amounts', () => {
    expect(validatePositiveMoney(0, 'Amount')).not.toBeNull();
    expect(validatePositiveMoney(-10, 'Amount')).not.toBeNull();
  });

  it('accepts positive amounts', () => {
    expect(validatePositiveMoney(0.01, 'Amount')).toBeNull();
  });
});

describe('validateNonNegativeMoney', () => {
  it('rejects negative amounts', () => {
    expect(validateNonNegativeMoney(-1, 'Amount')).not.toBeNull();
  });

  it('accepts zero and positive amounts', () => {
    expect(validateNonNegativeMoney(0, 'Amount')).toBeNull();
    expect(validateNonNegativeMoney(10, 'Amount')).toBeNull();
  });
});

describe('validatePositiveQuantity', () => {
  it('rejects zero and negative quantities', () => {
    expect(validatePositiveQuantity(0, 'Quantity')).not.toBeNull();
    expect(validatePositiveQuantity(-1, 'Quantity')).not.toBeNull();
  });

  it('accepts positive (including fractional) quantities', () => {
    expect(validatePositiveQuantity(1, 'Quantity')).toBeNull();
    expect(validatePositiveQuantity(1.5, 'Quantity')).toBeNull();
  });
});

describe('validatePositiveInteger', () => {
  it('rejects zero, negative and fractional values', () => {
    expect(validatePositiveInteger(0, 'Quantity')).not.toBeNull();
    expect(validatePositiveInteger(-1, 'Quantity')).not.toBeNull();
    expect(validatePositiveInteger(1.5, 'Quantity')).not.toBeNull();
  });

  it('accepts positive whole numbers', () => {
    expect(validatePositiveInteger(1, 'Quantity')).toBeNull();
  });
});

describe('validateNonNegativeInteger', () => {
  it('rejects negative values', () => {
    expect(validateNonNegativeInteger(-1, 'Trial days')).not.toBeNull();
  });

  it('accepts zero and positive whole numbers', () => {
    expect(validateNonNegativeInteger(0, 'Trial days')).toBeNull();
    expect(validateNonNegativeInteger(14, 'Trial days')).toBeNull();
  });
});

describe('validateDescription', () => {
  it('rejects empty/whitespace-only text', () => {
    expect(validateDescription('', 500, 'Description')).not.toBeNull();
    expect(validateDescription('   ', 500, 'Description')).not.toBeNull();
  });

  it('rejects text beyond the max length', () => {
    expect(validateDescription('x'.repeat(501), 500, 'Description')).not.toBeNull();
  });

  it('accepts legitimate descriptions containing numbers', () => {
    expect(validateDescription('Server Package 2', 500, 'Description')).toBeNull();
    expect(validateDescription('Migrated to Windows Server 2026', 500, 'Description')).toBeNull();
  });
});

describe('validateDateNotBefore', () => {
  it('rejects a due/end date before the issue/start date', () => {
    expect(validateDateNotBefore('2026-01-01', '2026-09-16', 'Due date', 'issue date')).not.toBeNull();
  });

  it('accepts a due/end date on or after the issue/start date', () => {
    expect(validateDateNotBefore('2026-09-16', '2026-09-16', 'Due date', 'issue date')).toBeNull();
    expect(validateDateNotBefore('2026-10-01', '2026-09-16', 'Due date', 'issue date')).toBeNull();
  });

  it('is a no-op when either date is missing', () => {
    expect(validateDateNotBefore(null, '2026-09-16', 'Due date', 'issue date')).toBeNull();
    expect(validateDateNotBefore('2026-09-16', null, 'Due date', 'issue date')).toBeNull();
  });
});
