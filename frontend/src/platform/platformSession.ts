import { PlatformApiError, PlatformMe, platformApi } from './platformApi';

/** GET /me, refreshing the session once if the short-lived access token has expired. */
export async function loadPlatformMe(): Promise<PlatformMe | null> {
  try {
    return await platformApi.me();
  } catch (err) {
    if (!(err instanceof PlatformApiError) || err.status !== 401) throw err;
  }
  try {
    return await platformApi.refresh();
  } catch (err) {
    if (err instanceof PlatformApiError && (err.status === 401 || err.status === 403)) return null;
    throw err;
  }
}
