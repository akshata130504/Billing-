/**
 * Visual-editor preview sample data for the tenant Customer Portal settings page (/customer-portal).
 * The page loads GET /portal/settings on mount. Fictional values only.
 */
import type { CustomerPortalSettings } from '../../../types/portal';

const settings: CustomerPortalSettings = {
  id: 'preview-portal-settings',
  organization_id: 'preview-org',
  portal_name: 'Acme Traders Billing Portal',
  portal_url_slug: 'acme-traders',
  banner_message: 'Our finance desk is closed on 2 October. Payments will be reconciled the next working day.',
  auto_invite_enabled: true,
  mfa_enabled: false,
  prevent_duplicate_payments: true,
  allow_self_signup: true,
  allow_document_upload: true,
  allow_document_forwarding: false,
  allow_save_payment_methods: true,
  save_payment_method_default: false,
  prevent_deselecting_save_payment: false,
  enable_identity_verification_public_links: false,
  trials_allow_customer_extension: true,
  trials_max_extensions: 2,
  trials_activate_immediately: true,
  created_at: '2026-06-01T09:00:00Z',
  updated_at: '2026-09-28T11:30:00Z',
};

export const routes: Record<string, (query: URLSearchParams) => unknown> = {
  '/portal/settings': () => settings,
};
