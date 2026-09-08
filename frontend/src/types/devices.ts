import type { AuthTokens, MeMembership, MeOrganizationSummary, MeUser, OrganizationOut } from './api';

/** Mirrors backend `DevicePlatform` enum (backend/app/models/devices.py). */
export type DevicePlatform = 'windows' | 'macos' | 'android' | 'ios';

/** Mirrors backend `DeviceTrustStatus` enum. New devices are trusted immediately in the current MVP. */
export type DeviceTrustStatus = 'pending' | 'trusted' | 'revoked';

export type PlatformFamily = 'mobile' | 'desktop';

export const PLATFORM_FAMILIES: Record<PlatformFamily, DevicePlatform[]> = {
  mobile: ['ios', 'android'],
  desktop: ['windows', 'macos'],
};

export const PLATFORM_LABELS: Record<DevicePlatform, string> = {
  ios: 'iOS',
  android: 'Android',
  windows: 'Windows',
  macos: 'macOS',
};

export const TRUST_STATUS_LABELS: Record<DeviceTrustStatus, string> = {
  pending: 'Pending',
  trusted: 'Trusted',
  revoked: 'Revoked',
};

/** POST /devices body (backend `DeviceRegisterIn`). */
export interface DeviceRegisterIn {
  device_identifier: string;
  platform: DevicePlatform;
  device_name?: string | null;
  os_version?: string | null;
  app_version?: string | null;
  push_token?: string | null;
}

/** GET /devices item and POST /devices response (backend `DeviceOut`). */
export interface DeviceOut {
  id: string;
  user_id: string;
  device_identifier: string;
  device_name: string | null;
  platform: DevicePlatform;
  os_version: string | null;
  app_version: string | null;
  trust_status: DeviceTrustStatus;
  last_seen_at: string | null;
  trusted_at: string | null;
  revoked_at: string | null;
  created_at: string;
  updated_at: string;
}

/** DELETE /devices/{id} response. */
export interface DeviceRevokeResponse {
  status: string;
  message: string;
}

/** POST /auth/native/exchange body. */
export interface NativeExchangeRequest {
  email: string;
  password: string;
  device: DeviceRegisterIn;
}

/** POST /auth/native/exchange response: the normal token bundle plus the registered device. */
export interface NativeExchangeResponse extends AuthTokens {
  device: DeviceOut;
}

/** GET /mobile/bootstrap response (backend `MobileBootstrapOut`). */
export interface MobileBootstrapOut {
  user: MeUser;
  organization: OrganizationOut;
  membership: MeMembership;
  organizations: MeOrganizationSummary[];
  server_time: string;
}
