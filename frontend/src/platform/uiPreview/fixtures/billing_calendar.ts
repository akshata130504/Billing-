/**
 * Visual-editor preview sample data for the Billing Calendar (/control-center/calendar). Fictional.
 * Events are dated inside whichever month the page asks for (`month=YYYY-MM`).
 */
import type { CalendarEvent, CalendarResponse, CustomerRef } from '../../../types/api';

const customer = (n: number, name: string): CustomerRef => ({
  id: `00000000-0000-4000-a000-00000000000${n}`,
  customer_number: `CUS-000${n}`,
  display_name: name,
  email: `billing@customer${n}.example.com`,
});

const SEEDS: Array<Omit<CalendarEvent, 'date'> & { day: number }> = [
  { id: 'cal-1', day: 3, type: 'invoice_due', title: 'INV-1046 due', customer: customer(1, 'Acme Traders'), amount: '18408.00', entity_type: 'invoice', entity_id: '00000000-0000-4000-b000-000000001046', status: 'sent' },
  { id: 'cal-2', day: 8, type: 'subscription_renewal', title: 'Growth plan renewal', customer: customer(5, 'Bluewave Logistics'), amount: '24999.00', entity_type: 'subscription', entity_id: '00000000-0000-4000-e000-000000000002', status: 'active' },
  { id: 'cal-3', day: 12, type: 'trial_ending', title: 'Trial ends', customer: customer(6, 'Saffron Studio'), amount: null, entity_type: 'subscription', entity_id: '00000000-0000-4000-e000-000000000001', status: 'trialing' },
  { id: 'cal-4', day: 15, type: 'quote_expiry', title: 'QT-0034 expires', customer: customer(3, 'Nimbus Analytics'), amount: '184000.00', entity_type: 'quote', entity_id: '00000000-0000-4000-d000-000000000034', status: 'sent' },
  { id: 'cal-5', day: 20, type: 'invoice_due', title: 'INV-1049 due', customer: customer(2, 'Kaveri Foods'), amount: '9440.00', entity_type: 'invoice', entity_id: '00000000-0000-4000-b000-000000001049', status: 'sent' },
  { id: 'cal-6', day: 28, type: 'subscription_renewal', title: 'Starter plan renewal', customer: customer(4, 'Lotus Wellness'), amount: '4999.00', entity_type: 'subscription', entity_id: '00000000-0000-4000-e000-000000000003', status: 'active' },
];

function calendar(query: URLSearchParams): CalendarResponse {
  const now = new Date();
  const fallback = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`;
  const month = /^\d{4}-\d{2}$/.test(query.get('month') || '') ? (query.get('month') as string) : fallback;
  return {
    events: SEEDS.map(({ day, ...event }) => ({ ...event, date: `${month}-${String(day).padStart(2, '0')}` })),
  };
}

export const routes: Record<string, (query: URLSearchParams) => unknown> = {
  '/calendar': calendar,
};
