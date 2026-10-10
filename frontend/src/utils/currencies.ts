import { currencySymbol } from './format';

/**
 * The currencies the product supports. Every currency picker (customers, plans, quotes,
 * invoices, expenses, catalog offerings, price books, organization settings) offers exactly
 * this list, so a document can always be raised in a customer's or plan's currency.
 */
export const SUPPORTED_CURRENCIES = ['INR', 'USD', 'EUR', 'GBP', 'AED', 'SGD', 'AUD', 'CAD'] as const;

export type SupportedCurrency = (typeof SUPPORTED_CURRENCIES)[number];

/** Picker label: "INR (₹)", or just the code when it has no separate symbol ("AED"). */
export function currencyOptionLabel(code: string): string {
  const symbol = currencySymbol(code);
  return symbol && symbol !== code ? `${code} (${symbol})` : code;
}

/** The supported list, plus `current` when a stored record uses a currency outside it, so
 *  editing that record never silently switches its currency. */
export function currencyChoices(current?: string | null): string[] {
  const list: string[] = [...SUPPORTED_CURRENCIES];
  if (current && !list.includes(current)) list.push(current);
  return list;
}
