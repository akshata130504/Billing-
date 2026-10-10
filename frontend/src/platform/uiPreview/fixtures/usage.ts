/**
 * Visual-editor preview sample data for Usage / Metering (/usage). All names are fictional.
 *
 * On mount the page lists `GET /meters`, the recent usage history (`GET /meters/events`) and the
 * per-meter totals (`GET /meters/usage-summary`). Finalised cycles exist only in the page's own
 * session state, so the preview shows that panel's empty state.
 */
import type { UsageEventOut, UsageMeterOut, UsageMeterSummaryOut } from '../../../types/meters';

export const previewMeters: UsageMeterOut[] = [
  {
    id: 'meter-api', code: 'api_calls', name: 'API Requests', unit_name: 'requests', aggregation_type: 'sum',
    description: 'Every authenticated call to the public REST API', is_active: true, unit_price: '0.05',
    created_at: '2026-08-04T10:00:00Z',
  },
  {
    id: 'meter-storage', code: 'storage_gb', name: 'Storage', unit_name: 'GB', aggregation_type: 'max',
    description: 'Peak storage used during the billing period', is_active: true, unit_price: '12.00',
    created_at: '2026-08-11T10:00:00Z',
  },
  {
    id: 'meter-seats', code: 'active_seats', name: 'Active Seats', unit_name: 'seats', aggregation_type: 'last',
    description: null, is_active: true, unit_price: '199.00', created_at: '2026-08-20T10:00:00Z',
  },
  {
    id: 'meter-sms', code: 'sms_sent', name: 'SMS Notifications', unit_name: 'messages', aggregation_type: 'count',
    description: 'Transactional SMS sent on behalf of the workspace', is_active: false, unit_price: null,
    created_at: '2026-09-02T10:00:00Z',
  },
];

export const previewEvents: UsageEventOut[] = [
  {
    id: 'evt-3', meter_id: 'meter-api', customer_id: 'cust-1', subscription_id: 'sub-1', quantity: '1250.0000',
    timestamp: '2026-09-28T11:30:00Z', idempotency_key: 'api-2026-09-28', status: 'accepted',
    created_at: '2026-09-28T11:30:02Z', customer_name: 'Nimbus Analytics', subscription_number: 'SUB-000014',
  },
  {
    id: 'evt-2', meter_id: 'meter-storage', customer_id: 'cust-1', subscription_id: 'sub-1', quantity: '42.0000',
    timestamp: '2026-09-27T09:00:00Z', idempotency_key: 'storage-2026-09-27', status: 'accepted',
    created_at: '2026-09-27T09:00:01Z', customer_name: 'Nimbus Analytics', subscription_number: 'SUB-000014',
  },
  {
    id: 'evt-1', meter_id: 'meter-api', customer_id: 'cust-2', subscription_id: null, quantity: '480.0000',
    timestamp: '2026-09-25T16:45:00Z', idempotency_key: 'api-2026-09-25', status: 'accepted',
    created_at: '2026-09-25T16:45:03Z', customer_name: 'Kestrel Logistics', subscription_number: null,
  },
];

function meterTotals(meterId: string | null): UsageMeterSummaryOut[] {
  return previewMeters
    .filter((m) => !meterId || m.id === meterId || m.code === meterId)
    .map((m) => {
      const events = previewEvents.filter((e) => e.meter_id === m.id);
      return {
        meter_id: m.id, meter_code: m.code, meter_name: m.name, unit_name: m.unit_name,
        aggregation_type: m.aggregation_type, event_count: events.length,
        total_quantity: events.reduce((sum, e) => sum + Number(e.quantity), 0).toFixed(4),
        last_event_at: events[0]?.timestamp ?? null,
      };
    });
}

export const routes: Record<string, (query: URLSearchParams) => unknown> = {
  '/meters': () => previewMeters,
  '/meters/events': (q) => {
    const meterId = q.get('meter_id');
    const meter = previewMeters.find((m) => m.id === meterId || m.code === meterId);
    const items = previewEvents.filter((e) => !meterId || e.meter_id === meter?.id);
    return { items, total: items.length, page: 1, page_size: Number(q.get('page_size') || 20), total_pages: items.length ? 1 : 0 };
  },
  '/meters/usage-summary': (q) => meterTotals(q.get('meter_id')),
};
