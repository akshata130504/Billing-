import { formatMoney } from '../../utils/format';

/** Money display used across this module's tables and cards: the shared formatter (digit
 *  grouping, always 2 decimals), in the expense's own currency when one is given. */
export function formatINR(amount: number, currency = 'INR'): string {
  return formatMoney(amount, currency);
}
