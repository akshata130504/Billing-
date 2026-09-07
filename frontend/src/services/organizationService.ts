import { apiClient } from './apiClient';
import type {
  InviteRequest,
  InviteResponse,
  MemberRole,
  OrganizationOut,
  OrganizationUpdate,
  TeamMember,
} from '../types/api';

export const organizationService = {
  get: async (): Promise<OrganizationOut> => {
    const { data } = await apiClient.get<OrganizationOut>('/organization');
    return data;
  },

  update: async (body: OrganizationUpdate): Promise<OrganizationOut> => {
    const { data } = await apiClient.patch<OrganizationOut>('/organization', body);
    return data;
  },

  listTeam: async (): Promise<TeamMember[]> => {
    const { data } = await apiClient.get<TeamMember[]>('/team');
    return data;
  },

  invite: async (body: InviteRequest): Promise<InviteResponse> => {
    const { data } = await apiClient.post<InviteResponse>('/team/invitations', body);
    return data;
  },

  updateMemberRole: async (membershipId: string, role: MemberRole): Promise<TeamMember> => {
    const { data } = await apiClient.patch<TeamMember>(`/team/${membershipId}`, { role });
    return data;
  },

  deactivateMember: async (membershipId: string): Promise<void> => {
    await apiClient.delete(`/team/${membershipId}`);
  },
};
