/**
 * Statuses in which the customer can still accept or decline a quote from its public link.
 * Mirrors backend `quote_service.OPEN_FOR_CUSTOMER_STATUSES` (SENT, VIEWED): opening the link
 * itself moves a sent quote to "viewed".
 */
const OPEN_FOR_CUSTOMER = new Set(['sent', 'viewed']);

export function isQuoteOpenForCustomer(status: string | null | undefined): boolean {
  return OPEN_FOR_CUSTOMER.has((status ?? '').toLowerCase());
}
