import { apiClient } from './apiClient';
import type { MeUser } from '../types/api';

export interface UserProfileUpdate {
  full_name?: string;
  /** Empty string clears the stored number. */
  phone?: string;
}

export const userService = {
  /** Persists the signed-in user's own profile server-side. */
  updateMe: async (body: UserProfileUpdate): Promise<MeUser> => {
    const { data } = await apiClient.patch<MeUser>('/users/me', body);
    return data;
  },

  uploadAvatar: async (file: File): Promise<MeUser> => {
    const formData = new FormData();
    formData.append('file', file);
    const { data } = await apiClient.post<MeUser>('/users/me/avatar', formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    });
    return data;
  },

  deleteAvatar: async (): Promise<MeUser> => {
    const { data } = await apiClient.delete<MeUser>('/users/me/avatar');
    return data;
  },
};
