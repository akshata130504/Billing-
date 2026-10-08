/**
 * Visual-editor preview sample data for Usage / Metering (/usage). All names are fictional.
 *
 * On mount the page only lists `GET /meters`. Recorded events and finalised cycles exist only in
 * the page's own session state (the API has no list endpoint for them), so the preview shows
 * those panels' empty states.
 */
import type { UsageMeterOut } from '../../../types/meters';

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

export const routes: Record<string, (query: URLSearchParams) => unknown> = {
  '/meters': () => previewMeters,
};
