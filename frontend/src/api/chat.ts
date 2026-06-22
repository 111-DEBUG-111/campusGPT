import { apiClient } from './client';
import type { ChatResponse, ConversationListItem, Conversation } from '../types';
import type { KnowledgeMode } from '../types';

export const chatApi = {
  sendMessage: async (
    query: string,
    conversationId?: number,
    knowledgeMode?: KnowledgeMode,
  ): Promise<ChatResponse> => {
    const { data } = await apiClient.post('/api/chat', {
      query,
      conversation_id: conversationId,
      knowledge_mode: knowledgeMode,
    });
    return data;
  },

  listConversations: async (): Promise<ConversationListItem[]> => {
    const { data } = await apiClient.get('/api/conversations');
    return data;
  },

  getConversation: async (id: number): Promise<Conversation> => {
    const { data } = await apiClient.get(`/api/conversations/${id}`);
    return data;
  },

  deleteConversation: async (id: number): Promise<void> => {
    await apiClient.delete(`/api/conversations/${id}`);
  },

  recordVisit: async (): Promise<void> => {
    await apiClient.post('/api/visit');
  },

  submitFeedback: async (
    messageId: number,
    rating: 'helpful' | 'not_helpful',
    comment?: string
  ): Promise<void> => {
    await apiClient.post('/api/feedback', {
      message_id: messageId,
      rating,
      comment,
    });
  },
};
