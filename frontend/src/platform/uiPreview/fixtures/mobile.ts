/**
 * Visual-editor preview sample data for Platforms > Mobile and Platforms > Desktop
 * (/platforms/mobile, /platforms/desktop share GET /devices and GET /mobile/bootstrap).
 * Entirely fictional: made-up device names and identifiers, example.in addresses, no tokens.
 */
import type { DeviceOut } from '../../../types/devices';
import type { MobileBootstrapOut } from '../../../types/devices';
import type { OrganizationOut } from '../../../types/api';

const DAY = 24 * 60 * 60 * 1000;
/** Relative to "now" so the page's 30-day activity window always has active devices. */
const daysAgo = (days: number) => new Date(Date.now() - days * DAY).toISOString();

function devices(): DeviceOut[] {
  const base = { user_id: 'preview-user-1', trusted_at: daysAgo(60), revoked_at: null, updated_at: daysAgo(1) };
  return [
    { ...base, id: 'dev-preview-1', device_identifier: 'preview-ios-0001', device_name: "Asha's iPhone", platform: 'ios', os_version: '19.1', app_version: '2.4.0', trust_status: 'trusted', last_seen_at: daysAgo(0.1), created_at: daysAgo(60) },
    { ...base, id: 'dev-preview-2', device_identifier: 'preview-android-0002', device_name: 'Field tablet', platform: 'android', os_version: '16', app_version: '2.3.2', trust_status: 'trusted', last_seen_at: daysAgo(3), created_at: daysAgo(45) },
    { ...base, id: 'dev-preview-3', device_identifier: 'preview-android-0003', device_name: 'Old Pixel', platform: 'android', os_version: '14', app_version: '1.9.0', trust_status: 'revoked', last_seen_at: daysAgo(80), created_at: daysAgo(200), revoked_at: daysAgo(40) },
    { ...base, id: 'dev-preview-4', device_identifier: 'preview-win-0004', device_name: 'Finance workstation', platform: 'windows', os_version: '11 24H2', app_version: '1.2.0', trust_status: 'trusted', last_seen_at: daysAgo(0.5), created_at: daysAgo(30) },
    { ...base, id: 'dev-preview-5', device_identifier: 'preview-mac-0005', device_name: 'Design MacBook', platform: 'macos', os_version: '16.0', app_version: '1.1.4', trust_status: 'pending', last_seen_at: null, created_at: daysAgo(2) },
  ];
}

const organization = {
  id: 'preview-org', name: 'Acme Traders', slug: 'acme-traders', legal_name: 'Acme Traders Pvt Ltd',
  email: 'billing@acmetraders.example.in', phone: null, website: null,
  address_line1: null, address_line2: null, city: 'Bengaluru', state: 'Karnataka', postal_code: null, country: 'IN',
  gstin: null, pan: null, default_currency: 'INR', timezone: 'Asia/Kolkata',
  invoice_prefix: 'INV-', invoice_next_number: 1049, quote_prefix: 'QT-', quote_next_number: 218,
  payment_prefix: 'PAY-', payment_next_number: 312, subscription_prefix: 'SUB-', subscription_next_number: 40,
  customer_prefix: 'CUST-', customer_next_number: 9, default_payment_terms_days: 30, default_tax_rate_pct: '18.00',
  discount_approval_threshold_pct: '15.00', invoice_notes: null, invoice_terms: null, logo_url: null,
  created_at: '2026-01-05T09:00:00Z', updated_at: '2026-09-30T09:00:00Z',
} satisfies OrganizationOut;

function bootstrap(): MobileBootstrapOut {
  return {
    user: {
      id: 'preview-user-1', email: 'asha.rao@example.in', full_name: 'Asha Rao',
      last_login_at: daysAgo(0.1), created_at: '2026-01-05T09:00:00Z', two_factor_enabled: true,
    },
    organization,
    membership: { id: 'preview-membership-1', role: 'owner', status: 'active', joined_at: '2026-01-05T09:00:00Z' },
    organizations: [{ id: 'preview-org', name: 'Acme Traders', slug: 'acme-traders', role: 'owner' }],
    server_time: new Date().toISOString(),
  };
}

export const routes: Record<string, (query: URLSearchParams) => unknown> = {
  '/devices': devices,
  '/mobile/bootstrap': bootstrap,
};
