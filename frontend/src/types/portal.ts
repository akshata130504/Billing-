// ---------------------------------------------------------------------------
// Customer Portal — mirrors backend/app/schemas/portal.py
// ---------------------------------------------------------------------------

/** GET /portal/settings → CustomerPortalSettingsOut */
export interface CustomerPortalSettings {
  id: string;
  organization_id: string;
  portal_name: string;
  portal_url_slug: string | null;
  banner_message: string | null;
  auto_invite_enabled: boolean;
  mfa_enabled: boolean;
  prevent_duplicate_payments: boolean;
  allow_self_signup: boolean;
  allow_document_upload: boolean;
  allow_document_forwarding: boolean;
  allow_save_payment_methods: boolean;
  save_payment_method_default: boolean;
  prevent_deselecting_save_payment: boolean;
  enable_identity_verification_public_links: boolean;
  trials_allow_customer_extension: boolean;
  trials_max_extensions: number;
  trials_activate_immediately: boolean;
  created_at: string;
  updated_at: string;
}

/** PATCH /portal/settings → CustomerPortalSettingsUpdate (all optional; exclude_unset). */
export interface CustomerPortalSettingsUpdate {
  portal_name?: string;
  portal_url_slug?: string | null;
  banner_message?: string | null;
  auto_invite_enabled?: boolean;
  mfa_enabled?: boolean;
  prevent_duplicate_payments?: boolean;
  allow_self_signup?: boolean;
  allow_document_upload?: boolean;
  allow_document_forwarding?: boolean;
  allow_save_payment_methods?: boolean;
  save_payment_method_default?: boolean;
  prevent_deselecting_save_payment?: boolean;
  enable_identity_verification_public_links?: boolean;
  trials_allow_customer_extension?: boolean;
  /** 0–10 */
  trials_max_extensions?: number;
  trials_activate_immediately?: boolean;
}

/** Boolean-only keys of the settings object (used for toggle rows). */
export type CustomerPortalToggleKey = {
  [K in keyof CustomerPortalSettings]: CustomerPortalSettings[K] extends boolean ? K : never;
}[keyof CustomerPortalSettings];

/** POST /portal/auth/signup body (customer-facing; documented on the admin page). */
export interface PortalSignupIn {
  organization_id: string;
  email: string;
  /** min 8 chars */
  password: string;
  display_name: string;
  customer_id?: string | null;
}

/** POST /portal/auth/login body. */
export interface PortalLoginIn {
  organization_id: string;
  email: string;
  password: string;
  mfa_code?: string | null;
}

export interface PortalUserOut {
  id: string;
  organization_id: string;
  customer_id: string;
  email: string;
  display_name: string;
  is_active: boolean;
  mfa_enabled: boolean;
  last_login_at: string | null;
}

/** POST /portal/auth/login response. Token goes in the X-Portal-Token header. */
export interface PortalAuthOut {
  token: string;
  expires_at: string;
  user: PortalUserOut;
  customer_display_name: string;
}
