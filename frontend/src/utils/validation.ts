/**
 * Shared, reusable field validators for forms across the app.
 * Mirrors backend/app/schemas/validators.py so frontend and backend agree on
 * what "valid" means — the backend is still the source of truth and re-checks
 * everything on submit, but this gives users inline errors before they hit it.
 */

import { isValidPhoneNumber } from 'react-phone-number-input';

export type ValidationResult = string | null;

const NAME_CHARS_RE = /^[A-Za-z0-9\s.,'&\-()/]{1,200}$/;
const HAS_LETTER_RE = /[A-Za-zÀ-ɏ]/;
const PHONE_RE = /^\+?[0-9\s\-().]{7,20}$/;
const EMAIL_RE = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;
const URL_RE = /^https?:\/\/([a-zA-Z0-9]([a-zA-Z0-9\-]*[a-zA-Z0-9])?\.)+[a-zA-Z]{2,}(:\d+)?([/?#].*)?$/;
const GSTIN_RE = /^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$/;
const PAN_RE = /^[A-Z]{5}[0-9]{4}[A-Z]$/;
const HSN_SAC_RE = /^[0-9]{2,8}$/;
const SLUG_RE = /^[a-z0-9]+(?:[-_][a-z0-9]+)*$/;
const SKU_RE = /^[A-Za-z0-9_\-.]{1,64}$/;
const COUNTRY_CODE_RE = /^[A-Z]{2}$/;

/** Parses user input into a finite number, or null if it isn't one (rejects "100abc", "", NaN, Infinity). */
export function parseStrictNumber(value: string | number | null | undefined): number | null {
  if (value === null || value === undefined) return null;
  if (typeof value === 'number') return Number.isFinite(value) ? value : null;
  const trimmed = value.trim();
  if (trimmed === '') return null;
  // Number() rejects trailing garbage ("100abc") unlike parseFloat().
  const n = Number(trimmed);
  return Number.isFinite(n) ? n : null;
}

export function validateRequiredText(value: string | null | undefined, fieldLabel = 'This field'): ValidationResult {
  if (value === null || value === undefined || value.trim() === '') {
    return `${fieldLabel} is required.`;
  }
  return null;
}

/** Validates human-readable names/business text: letters+digits+common punctuation, not purely numeric. */
export function validateSensibleName(value: string | null | undefined, fieldLabel = 'Name'): ValidationResult {
  if (value === null || value === undefined || value.trim() === '') {
    return `${fieldLabel} is required.`;
  }
  const val = value.trim();
  if (val.length > 200) return `${fieldLabel} must be at most 200 characters.`;
  if (!HAS_LETTER_RE.test(val)) return `${fieldLabel} cannot be numeric-only and must contain at least one letter.`;
  if (!NAME_CHARS_RE.test(val)) return `${fieldLabel} contains invalid characters.`;
  return null;
}

export function validateEmail(value: string | null | undefined, options: { required?: boolean } = {}): ValidationResult {
  const val = (value ?? '').trim();
  if (val === '') return options.required ? 'Email is required.' : null;
  if (!EMAIL_RE.test(val)) return 'Enter a valid email address.';
  return null;
}

/** Normalizes an email for submission (trim + lowercase) without altering its structure. */
export function normalizeEmail(value: string | null | undefined): string {
  return (value ?? '').trim().toLowerCase();
}

export function validatePhone(value: string | null | undefined, options: { required?: boolean } = {}): ValidationResult {
  const val = (value ?? '').trim();
  if (val === '') return options.required ? 'Phone number is required.' : null;
  // Numbers entered via the country-code phone input arrive in E.164 form
  // (e.g. "+919876543210") - validate those precisely per-country.
  if (val.startsWith('+')) {
    return isValidPhoneNumber(val) ? null : 'Enter a valid phone number for the selected country.';
  }
  if (!PHONE_RE.test(val)) {
    return 'Enter a valid phone number (digits, spaces, hyphens, parentheses, optional leading +).';
  }
  const digits = val.replace(/\D/g, '');
  if (digits.length < 7 || digits.length > 15) {
    return 'Phone number must contain between 7 and 15 digits.';
  }
  return null;
}

export function validateUrl(value: string | null | undefined, options: { required?: boolean } = {}): ValidationResult {
  const val = (value ?? '').trim();
  if (val === '') return options.required ? 'Website URL is required.' : null;
  const withScheme = val.startsWith('http://') || val.startsWith('https://') ? val : `https://${val}`;
  if (!URL_RE.test(withScheme)) return 'Enter a valid http:// or https:// URL.';
  return null;
}

export function validateGstin(value: string | null | undefined, options: { required?: boolean } = {}): ValidationResult {
  const val = (value ?? '').trim().toUpperCase();
  if (val === '') return options.required ? 'GSTIN is required.' : null;
  if (!GSTIN_RE.test(val)) return 'Enter a valid 15-character GSTIN (e.g. 29ABCDE1234F1Z5).';
  return null;
}

export function validatePan(value: string | null | undefined, options: { required?: boolean } = {}): ValidationResult {
  const val = (value ?? '').trim().toUpperCase();
  if (val === '') return options.required ? 'PAN is required.' : null;
  if (!PAN_RE.test(val)) return 'Enter a valid 10-character PAN (e.g. ABCDE1234F).';
  return null;
}

export function validateHsnSac(value: string | null | undefined, options: { required?: boolean } = {}): ValidationResult {
  const val = (value ?? '').trim();
  if (val === '') return options.required ? 'HSN/SAC code is required.' : null;
  if (!HSN_SAC_RE.test(val)) return 'HSN/SAC code must contain only 2 to 8 numeric digits.';
  return null;
}

export function validateSlug(value: string | null | undefined, fieldLabel = 'Code', options: { required?: boolean } = {}): ValidationResult {
  const val = (value ?? '').trim().toLowerCase();
  if (val === '') return options.required ? `${fieldLabel} is required.` : null;
  if (!SLUG_RE.test(val)) return `${fieldLabel} must contain only lowercase letters, numbers, hyphens, or underscores.`;
  return null;
}

export function validateSku(value: string | null | undefined, options: { required?: boolean } = {}): ValidationResult {
  const val = (value ?? '').trim();
  if (val === '') return options.required ? 'SKU is required.' : null;
  if (!SKU_RE.test(val)) return 'SKU must contain only alphanumeric characters, dashes, dots, or underscores.';
  return null;
}

export function validateCountryCode(value: string | null | undefined, options: { required?: boolean } = {}): ValidationResult {
  const val = (value ?? '').trim().toUpperCase();
  if (val === '') return options.required ? 'Country is required.' : null;
  if (!COUNTRY_CODE_RE.test(val)) return 'Enter a valid 2-letter country code (e.g. IN, US).';
  return null;
}

export function validatePostalCode(value: string | null | undefined, options: { required?: boolean; country?: string } = {}): ValidationResult {
  const val = (value ?? '').trim();
  if (val === '') return options.required ? 'Postal code is required.' : null;
  const country = options.country ? options.country.trim().toUpperCase() : null;
  if (country === 'IN') {
    if (!/^[1-9][0-9]{5}$/.test(val)) {
      return 'Enter a valid 6-digit Indian PIN code (e.g. 560001).';
    }
    return null;
  }
  if (!/^[A-Za-z0-9\s-]{3,12}$/.test(val) || !/\d/.test(val)) {
    return 'Enter a valid postal code.';
  }
  return null;
}

/** Percentage in [0, 100]. */
export function validatePercentage(value: string | number | null | undefined, fieldLabel = 'Percentage', options: { required?: boolean } = {}): ValidationResult {
  const n = parseStrictNumber(value);
  if (n === null) return options.required ? `${fieldLabel} is required.` : (value ? `${fieldLabel} must be a number.` : null);
  if (n < 0 || n > 100) return `${fieldLabel} must be between 0 and 100.`;
  return null;
}

/** Money that must be strictly greater than zero (e.g. payment amount, quantity price paid). */
export function validatePositiveMoney(value: string | number | null | undefined, fieldLabel = 'Amount', options: { required?: boolean } = {}): ValidationResult {
  const n = parseStrictNumber(value);
  if (n === null) return options.required ? `${fieldLabel} is required.` : (value ? `${fieldLabel} must be a number.` : null);
  if (n <= 0) return `${fieldLabel} must be greater than 0.`;
  return null;
}

/** Money that must be zero or more (e.g. unit price, budget). */
export function validateNonNegativeMoney(value: string | number | null | undefined, fieldLabel = 'Amount', options: { required?: boolean } = {}): ValidationResult {
  const n = parseStrictNumber(value);
  if (n === null) return options.required ? `${fieldLabel} is required.` : (value ? `${fieldLabel} must be a number.` : null);
  if (n < 0) return `${fieldLabel} cannot be negative.`;
  return null;
}

/** Quantity that must be a positive number (fractional quantities like 1.5 hours are allowed). */
export function validatePositiveQuantity(value: string | number | null | undefined, fieldLabel = 'Quantity', options: { required?: boolean } = {}): ValidationResult {
  const n = parseStrictNumber(value);
  if (n === null) return options.required ? `${fieldLabel} is required.` : (value ? `${fieldLabel} must be a number.` : null);
  if (n <= 0) return `${fieldLabel} must be greater than 0.`;
  return null;
}

/** Positive integer count (e.g. subscription quantity, plan interval count). */
export function validatePositiveInteger(value: string | number | null | undefined, fieldLabel = 'Value', options: { required?: boolean } = {}): ValidationResult {
  const n = parseStrictNumber(value);
  if (n === null) return options.required ? `${fieldLabel} is required.` : (value ? `${fieldLabel} must be a number.` : null);
  if (!Number.isInteger(n) || n <= 0) return `${fieldLabel} must be a positive whole number.`;
  return null;
}

/** Non-negative integer count (e.g. trial days, payment terms days). */
export function validateNonNegativeInteger(value: string | number | null | undefined, fieldLabel = 'Value', options: { required?: boolean } = {}): ValidationResult {
  const n = parseStrictNumber(value);
  if (n === null) return options.required ? `${fieldLabel} is required.` : (value ? `${fieldLabel} must be a number.` : null);
  if (!Number.isInteger(n) || n < 0) return `${fieldLabel} must be a non-negative whole number.`;
  return null;
}

export function validateDescription(value: string | null | undefined, maxLength = 500, fieldLabel = 'Description'): ValidationResult {
  const val = (value ?? '').trim();
  if (val === '') return `${fieldLabel} cannot be empty or whitespace-only.`;
  if (val.length > maxLength) return `${fieldLabel} must be at most ${maxLength} characters.`;
  return null;
}

/** due/end date must not be before issue/start date (both YYYY-MM-DD or Date). */
export function validateDateNotBefore(
  laterValue: string | Date | null | undefined,
  earlierValue: string | Date | null | undefined,
  laterLabel: string,
  earlierLabel: string
): ValidationResult {
  if (!laterValue || !earlierValue) return null;
  const later = new Date(laterValue);
  const earlier = new Date(earlierValue);
  if (Number.isNaN(later.getTime()) || Number.isNaN(earlier.getTime())) return null;
  if (later.getTime() < earlier.getTime()) return `${laterLabel} cannot be before ${earlierLabel}.`;
  return null;
}

/** later date must be strictly after earlier date (rejects equal or before). */
export function validateDateAfter(
  laterValue: string | Date | null | undefined,
  earlierValue: string | Date | null | undefined,
  laterLabel: string,
  earlierLabel: string
): ValidationResult {
  if (!laterValue || !earlierValue) return null;
  const later = new Date(laterValue);
  const earlier = new Date(earlierValue);
  if (Number.isNaN(later.getTime()) || Number.isNaN(earlier.getTime())) return null;
  if (later.getTime() <= earlier.getTime()) return `${laterLabel} must be after the ${earlierLabel}.`;
  return null;
}

/** date must not be before today (rejects past dates). */
export function validateDateNotPast(
  value: string | Date | null | undefined,
  fieldLabel = 'Date',
  options: { required?: boolean } = {}
): ValidationResult {
  if (!value) return options.required ? `${fieldLabel} is required.` : null;
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return `${fieldLabel} is invalid.`;
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const target = new Date(d);
  target.setHours(0, 0, 0, 0);
  if (target.getTime() < today.getTime()) {
    return `${fieldLabel} cannot be in the past.`;
  }
  return null;
}

/** date must not be in the future (rejects later than today). */
export function validateDateNotFuture(
  value: string | Date | null | undefined,
  fieldLabel = 'Date',
  options: { required?: boolean } = {}
): ValidationResult {
  if (!value) return options.required ? `${fieldLabel} is required.` : null;
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return `${fieldLabel} is invalid.`;
  const today = new Date();
  today.setHours(23, 59, 59, 999);
  if (d.getTime() > today.getTime()) {
    return `${fieldLabel} cannot be later than today.`;
  }
  return null;
}
