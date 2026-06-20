import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import type {
  Conversation,
  ConversationListItem,
  PendingConversation,
  PendingConversationStatus,
} from '../types';
import { chatApi } from '../api/chat';

/** Auto-decrementing counter for temp IDs (never clashes with positive DB IDs) */
let tempIdCounter = -1;
const nextTempId = () => tempIdCounter--;

interface CompletionToast {
  id: number;
  title: string;
  success: boolean;
  errorDetail?: string;
}

interface ChatState {
  // Conversation list (sidebar)
  conversations: ConversationListItem[];
  activeConversationId: number | null;
  activeConversation: Conversation | null;

  // Optimistic pending conversations (shown in sidebar while RAG runs)
  pendingConversations: PendingConversation[];

  // Streaming/loading state
  isLoading: boolean;
  error: string | null;

  // Input
  input: string;

  // Optimistic messages (shown while RAG runs in the active window)
  pendingUserMessage: string | null;

  // Completion toast notification
  completionToast: CompletionToast | null;

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
  dismissToast: () => void;

  // Internal helpers (kept in state so sidebar can read pendingConversations reactively)
  _updatePendingStatus: (tempId: number, status: PendingConversationStatus, error?: string) => void;
  _removePending: (tempId: number) => void;
}

export const useChatStore = create<ChatState>()(
  persist(
    (set, get) => ({
      conversations: [],
      activeConversationId: null,
      activeConversation: null,
      pendingConversations: [],
      isLoading: false,
      error: null,
      input: '',
      pendingUserMessage: null,
      completionToast: null,

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
        const { activeConversationId, activeConversation } = get();
        const isNewConversation = !activeConversationId;

        // ── Optimistic title derived from first 55 chars of the query ──────
        const optimisticTitle =
          query.length > 55 ? query.slice(0, 55) + '…' : query;

        // ── For new conversations: insert a pending entry into the sidebar ──
        let tempId: number | null = null;
        if (isNewConversation) {
          tempId = nextTempId();
          const pendingEntry: PendingConversation = {
            tempId,
            title: optimisticTitle,
            status: 'retrieving',
            startedAt: Date.now(),
          };
          set((s) => ({
            pendingConversations: [pendingEntry, ...s.pendingConversations],
          }));
        }

        set({ isLoading: true, error: null, pendingUserMessage: query, input: '' });

        // After ~500 ms bump status to 'generating' so the badge feels alive
        let generatingTimer: ReturnType<typeof setTimeout> | null = null;
        if (tempId !== null) {
          generatingTimer = setTimeout(() => {
            get()._updatePendingStatus(tempId!, 'generating');
          }, 500);
        }

        try {
          const response = await chatApi.sendMessage(query, activeConversationId || undefined);

          // Cancel the generating timer if response was super fast
          if (generatingTimer !== null) clearTimeout(generatingTimer);

          // Reload full conversation
          const conversation = await chatApi.getConversation(response.conversation_id);

          set({
            activeConversation: conversation,
            activeConversationId: response.conversation_id,
            pendingUserMessage: null,
          });

          // Refresh sidebar list (now has the real entry)
          await get().loadConversations();

          // Remove the pending optimistic entry and show a completion toast
          if (tempId !== null) {
            get()._removePending(tempId);
            set({
              completionToast: {
                id: response.conversation_id,
                title: optimisticTitle,
                success: true,
              },
            });
            // Auto-dismiss after 4 s
            setTimeout(() => get().dismissToast(), 4000);
          }
        } catch (error) {
          if (generatingTimer !== null) clearTimeout(generatingTimer);

          const message =
            error instanceof Error ? error.message : 'Failed to send message';

          // Restore failed message in the text input box so the user doesn't lose it
          set({ error: message, pendingUserMessage: null, input: query });

          // Mark the pending entry as failed instead of removing it
          if (tempId !== null) {
            get()._updatePendingStatus(tempId, 'failed', message);

            set({
              completionToast: {
                id: tempId,
                title: optimisticTitle,
                success: false,
                errorDetail: message,
              },
            });
          } else {
            // Existing conversation failed, show completion toast with failure
            set({
              completionToast: {
                id: activeConversationId!,
                title: activeConversation?.title || 'Chat',
                success: false,
                errorDetail: message,
              },
            });
          }

          // Auto-dismiss error toast after 6 seconds (longer for readability)
          setTimeout(() => get().dismissToast(), 6000);
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
      dismissToast: () => set({ completionToast: null }),

      _updatePendingStatus: (tempId, status, error) =>
        set((s) => ({
          pendingConversations: s.pendingConversations.map((p) =>
            p.tempId === tempId ? { ...p, status, error } : p
          ),
        })),

      _removePending: (tempId) =>
        set((s) => ({
          pendingConversations: s.pendingConversations.filter(
            (p) => p.tempId !== tempId
          ),
        })),
    }),
    {
      name: 'campusgpt-chat',
      partialize: (state) => ({
        activeConversationId: state.activeConversationId,
      }),
    }
  )
);
