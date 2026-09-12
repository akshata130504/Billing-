import { apiClient } from './apiClient';

export interface ChatMessage {
  role: 'user' | 'assistant' | 'system';
  content: string;
  timestamp?: string;
}

export interface RoomiNavigationHint {
  label: string;
  route: string;
  description?: string;
}

export interface RoomiSourceReference {
  source_type: string;
  source_id?: string;
  label: string;
  snippet?: string;
}

export interface RoomiChatRequest {
  message: string;
  conversation_id?: string;
  current_route?: string;
  history?: ChatMessage[];
}

export interface RoomiChatResponse {
  reply: string;
  conversation_id: string;
  suggested_chips?: string[];
  sources?: RoomiSourceReference[];
  navigation?: RoomiNavigationHint;
  data?: Record<string, unknown>;
}

export const roomiService = {
  /**
   * Send a chat message to the Roomi AI Assistant.
   * Requires internal authenticated session (Owner, Admin, Finance, Viewer).
   */
  sendMessage: async (request: RoomiChatRequest): Promise<RoomiChatResponse> => {
    const { data } = await apiClient.post<RoomiChatResponse>('/chat/roomi', request);
    return data;
  },
};
