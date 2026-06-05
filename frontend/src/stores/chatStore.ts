import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import type { Conversation, ConversationListItem, Message, SourceCitation } from '../types';
import { chatApi } from '../api/chat';

interface ChatState {
  // Conversation list (sidebar)
  conversations: ConversationListItem[];
  activeConversationId: number | null;
  activeConversation: Conversation | null;

  // Streaming/loading state
  isLoading: boolean;
  error: string | null;

  // Input
  input: string;

  // Optimistic messages (shown while RAG runs)
  pendingUserMessage: string | null;

  // Actions
  setInput: (input: string) => void;
  setActiveConversation: (id: number | null) => void;
  loadConversations: () => Promise<void>;
  loadConversation: (id: number) => Promise<void>;
  sendMessage: (query: string) => Promise<void>;
  startNewChat: () => void;
  deleteConversation: (id: number) => Promise<void>;
  submitFeedback: (messageId: number, rating: 'helpful' | 'not_helpful') => Promise<void>;
  clearError: () => void;
}

export const useChatStore = create<ChatState>()(
  persist(
    (set, get) => ({
      conversations: [],
      activeConversationId: null,
      activeConversation: null,
      isLoading: false,
      error: null,
      input: '',
      pendingUserMessage: null,

      setInput: (input) => set({ input }),

      setActiveConversation: async (id) => {
        if (id === null) {
          set({ activeConversationId: null, activeConversation: null });
          return;
        }
        set({ activeConversationId: id });
        await get().loadConversation(id);
      },

      loadConversations: async () => {
        try {
          const conversations = await chatApi.listConversations();
          set({ conversations });
        } catch (error) {
          console.error('Failed to load conversations:', error);
        }
      },

      loadConversation: async (id) => {
        try {
          const conversation = await chatApi.getConversation(id);
          set({ activeConversation: conversation });
        } catch (error) {
          set({ error: 'Failed to load conversation' });
        }
      },

      sendMessage: async (query) => {
        const { activeConversationId } = get();
        set({ isLoading: true, error: null, pendingUserMessage: query, input: '' });

        try {
          const response = await chatApi.sendMessage(query, activeConversationId || undefined);

          // Reload conversation to get all messages
          const conversation = await chatApi.getConversation(response.conversation_id);
          set({
            activeConversation: conversation,
            activeConversationId: response.conversation_id,
            pendingUserMessage: null,
          });

          // Refresh sidebar
          await get().loadConversations();
        } catch (error) {
          set({
            error: error instanceof Error ? error.message : 'Failed to send message',
            pendingUserMessage: null,
          });
        } finally {
          set({ isLoading: false });
        }
      },

      startNewChat: () => {
        set({
          activeConversationId: null,
          activeConversation: null,
          input: '',
          error: null,
          pendingUserMessage: null,
        });
      },

      deleteConversation: async (id) => {
        await chatApi.deleteConversation(id);
        const { activeConversationId } = get();
        if (activeConversationId === id) {
          set({ activeConversationId: null, activeConversation: null });
        }
        await get().loadConversations();
      },

      submitFeedback: async (messageId, rating) => {
        await chatApi.submitFeedback(messageId, rating);
      },

      clearError: () => set({ error: null }),
    }),
    {
      name: 'campusgpt-chat',
      partialize: (state) => ({
        activeConversationId: state.activeConversationId,
      }),
    }
  )
);
