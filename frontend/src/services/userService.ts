import { apiClient } from './apiClient';
import type { MeUser } from '../types/api';

export const userService = {
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
