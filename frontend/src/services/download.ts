import { tokenStorage, toApiError } from './apiClient';
import type { ApiError } from '../types/api';

/**
 * Fetches a protected file (PDF, CSV, JSON export) with the bearer token and
 * hands it to the browser as a download. Public URLs (e.g. /public/invoices/…)
 * do not need this — link to them directly.
 */
export async function downloadAuthenticated(url: string, filename: string): Promise<void> {
  const token = tokenStorage.getAccessToken();
  const headers: Record<string, string> = {};
  if (token) headers.Authorization = `Bearer ${token}`;

  let response: Response;
  try {
    response = await fetch(url, { headers, credentials: 'omit' });
  } catch (err) {
    throw toApiError(err);
  }

  if (!response.ok) {
    let apiError: ApiError = {
      code: `HTTP_${response.status}`,
      message: `Download failed (${response.status}).`,
      status: response.status,
    };
    try {
      const body = (await response.json()) as { error?: Partial<ApiError> };
      if (body.error?.message) {
        apiError = {
          code: body.error.code ?? apiError.code,
          message: body.error.message,
          details: body.error.details,
          status: response.status,
        };
      }
    } catch {
      // non-JSON error body; keep the generic message
    }
    throw apiError;
  }

  const blob = await response.blob();
  const resolvedName = filename || filenameFromDisposition(response.headers.get('Content-Disposition')) || 'download';
  triggerBlobDownload(blob, resolvedName);
}

export function triggerBlobDownload(blob: Blob, filename: string): void {
  const objectUrl = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = objectUrl;
  anchor.download = filename;
  anchor.rel = 'noopener';
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  // Give the browser a tick to start the download before revoking.
  window.setTimeout(() => URL.revokeObjectURL(objectUrl), 1000);
}

function filenameFromDisposition(header: string | null): string | null {
  if (!header) return null;
  const utf8 = /filename\*=UTF-8''([^;]+)/i.exec(header);
  if (utf8?.[1]) {
    try {
      return decodeURIComponent(utf8[1]);
    } catch {
      return utf8[1];
    }
  }
  const plain = /filename="?([^";]+)"?/i.exec(header);
  return plain?.[1] ?? null;
}
