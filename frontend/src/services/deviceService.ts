import { apiClient } from './apiClient';
import type {
  DeviceOut,
  DeviceRegisterIn,
  DeviceRevokeResponse,
  MobileBootstrapOut,
  NativeExchangeRequest,
  NativeExchangeResponse,
} from '../types/devices';

/**
 * Client-platform endpoints (tag "Client Platforms" in the OpenAPI spec).
 *
 * Note: GET /devices is scoped to the *caller's own* devices within the current
 * organization — there is no org-wide device listing today.
 */
export const deviceService = {
  /** Lists the caller's registered devices, newest first. Bare array, not paginated. */
  list: async (): Promise<DeviceOut[]> => {
    const { data } = await apiClient.get<DeviceOut[]>('/devices');
    return data;
  },

  /**
   * Registers (or refreshes) the caller's own device. Upserts on
   * (organization, user, device_identifier); a revoked identifier cannot be re-registered.
   */
  register: async (body: DeviceRegisterIn): Promise<DeviceOut> => {
    const { data } = await apiClient.post<DeviceOut>('/devices', body);
    return data;
  },

  /** Soft-revokes a device: the record stays with trust_status "revoked" and its push token cleared. */
  revoke: async (deviceId: string): Promise<DeviceRevokeResponse> => {
    const { data } = await apiClient.delete<DeviceRevokeResponse>(`/devices/${deviceId}`);
    return data;
  },

  /** Compact org/user/membership context a native client loads on startup. */
  bootstrap: async (): Promise<MobileBootstrapOut> => {
    const { data } = await apiClient.get<MobileBootstrapOut>('/mobile/bootstrap');
    return data;
  },

  /**
   * OAuth-style credential exchange for native clients: authenticates like /auth/login and
   * registers the device in the same round trip. Rate-limited like login.
   */
  nativeExchange: async (body: NativeExchangeRequest): Promise<NativeExchangeResponse> => {
    const { data } = await apiClient.post<NativeExchangeResponse>('/auth/native/exchange', body);
    return data;
  },
};
