import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import type {
  Conversation,
  ConversationListItem,
  PendingConversation,
  PendingConversationStatus,
} from '../types';
import { chatApi } from '../api/chat';

// ─────────────────────────────────────────────────────────────────────────────
// Module-level LRU conversation cache
// Lives outside Zustand so we don't trigger re-renders on every cache write,
// and so we avoid serialisation issues with Map/Set in the persist middleware.
// ─────────────────────────────────────────────────────────────────────────────

const MAX_CACHE_SIZE = 20;
const CACHE_TTL_MS   = 30_000; // 30 seconds

interface CacheEntry {
  data: Conversation;
  cachedAt: number;
}

const _cache     = new Map<number, CacheEntry>();
const _lruOrder  : number[] = [];           // index 0 = oldest access
const _prefetching = new Set<number>();    // in-flight prefetch IDs

/** Read from cache; updates LRU order on hit. Returns null on miss. */
function getCached(id: number): Conversation | null {
  const entry = _cache.get(id);
  if (!entry) return null;
  _touchLru(id);
  return entry.data;
}

/** Write to cache; evicts LRU entry when over capacity. */
function setCached(id: number, data: Conversation): void {
  if (!_cache.has(id) && _lruOrder.length >= MAX_CACHE_SIZE) {
    const evictId = _lruOrder.shift()!;
    _cache.delete(evictId);
  }
  _touchLru(id);
  _cache.set(id, { data, cachedAt: Date.now() });
}

/** Move id to the "most recently used" position. */
function _touchLru(id: number): void {
  const idx = _lruOrder.indexOf(id);
  if (idx !== -1) _lruOrder.splice(idx, 1);
  _lruOrder.push(id);
}

/** Returns true if there is no cache entry OR the entry is older than TTL. */
function isCacheStale(id: number): boolean {
  const entry = _cache.get(id);
  if (!entry) return true;
  return Date.now() - entry.cachedAt > CACHE_TTL_MS;
}

/** Removes a single entry from the cache (e.g. on delete). */
function evictCached(id: number): void {
  _cache.delete(id);
  const idx = _lruOrder.indexOf(id);
  if (idx !== -1) _lruOrder.splice(idx, 1);
}

// ─────────────────────────────────────────────────────────────────────────────
// Auto-decrementing counter for temporary IDs (never clashes with positive DB IDs)
// ─────────────────────────────────────────────────────────────────────────────

let tempIdCounter = -1;
const nextTempId = () => tempIdCounter--;

// ─────────────────────────────────────────────────────────────────────────────
// Store interface
// ─────────────────────────────────────────────────────────────────────────────

interface CompletionToast {
  id: number;
  title: string;
  success: boolean;
  errorDetail?: string;
}

interface ChatState {
  // Conversation list (sidebar)
  conversations: ConversationListItem[];
  /** Timestamp of the last successful listConversations fetch (persisted). */
  lastConversationsFetch: number | null;
  activeConversationId: number | null;
  activeConversation: Conversation | null;

  // Optimistic pending conversations (shown in sidebar while RAG runs)
  pendingConversations: PendingConversation[];

  // Loading state
  /** True only on a cold-start cache miss — blocks the full chat window. */
  isLoading: boolean;
  /** True when a background refresh is running for an already-displayed chat. */
  isBackgroundRefreshing: boolean;
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
  loadConversations: (force?: boolean) => Promise<void>;
  loadConversation: (id: number) => Promise<void>;
  prefetchConversation: (id: number) => void;
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

// ─────────────────────────────────────────────────────────────────────────────
// Store implementation
// ─────────────────────────────────────────────────────────────────────────────

export const useChatStore = create<ChatState>()(
  persist(
    (set, get) => ({
      conversations: [],
      lastConversationsFetch: null,
      activeConversationId: null,
      activeConversation: null,
      pendingConversations: [],
      isLoading: false,
      isBackgroundRefreshing: false,
      error: null,
      input: '',
      pendingUserMessage: null,
      completionToast: null,

      setInput: (input) => set({ input }),

      // ── Chat switching with instant cache render ────────────────────────────
      setActiveConversation: async (id) => {
        if (id === null) {
          set({
            activeConversationId: null,
            activeConversation: null,
            // Clear any in-flight state from a previous conversation
            pendingUserMessage: null,
            isLoading: false,
            error: null,
          });
          return;
        }

        const cached = getCached(id);

        if (cached) {
          // ⚡ Instant render from cache — clear any in-flight state from
          // whatever conversation was previously active so it never bleeds in.
          set({
            activeConversationId: id,
            activeConversation: cached,
            isLoading: false,
            pendingUserMessage: null,
            error: null,
          });

          // Background refresh only if the TTL has expired
          if (isCacheStale(id)) {
            set({ isBackgroundRefreshing: true });
            get()
              .loadConversation(id)
              .finally(() => {
                if (get().activeConversationId === id) {
                  set({ isBackgroundRefreshing: false });
                }
              });
          }
        } else {
          // Cold-start cache miss — show loading state, but still clear any
          // pending message/error that belonged to the previous conversation.
          set({
            activeConversationId: id,
            activeConversation: null,
            isLoading: true,
            pendingUserMessage: null,
            error: null,
          });
          await get().loadConversation(id);
          // Guard: only clear the spinner if we're still on this conversation
          if (get().activeConversationId === id) {
            set({ isLoading: false });
          }
        }
      },

      // ── Sidebar list with 30s TTL ──────────────────────────────────────────
      loadConversations: async (force = false) => {
        const { lastConversationsFetch } = get();
        if (
          !force &&
          lastConversationsFetch !== null &&
          Date.now() - lastConversationsFetch < CACHE_TTL_MS
        ) {
          return; // Still fresh — serve from persisted state
        }
        try {
          const conversations = await chatApi.listConversations();
          set({ conversations, lastConversationsFetch: Date.now() });
        } catch (error) {
          console.error('Failed to load conversations:', error);
        }
      },

      // ── Full conversation fetch (updates cache) ────────────────────────────
      loadConversation: async (id) => {
        try {
          const conversation = await chatApi.getConversation(id);
          setCached(id, conversation);
          // Only surface to UI if this is still the active chat
          if (get().activeConversationId === id) {
            set({ activeConversation: conversation });
          }
        } catch (error) {
          if (get().activeConversationId === id) {
            set({ error: 'Failed to load conversation' });
          }
        }
      },

      // ── Silent prefetch triggered on hover ────────────────────────────────
      prefetchConversation: (id) => {
        // Nothing to do if cache is still fresh
        if (!isCacheStale(id)) return;
        // Avoid duplicate in-flight requests
        if (_prefetching.has(id)) return;

        _prefetching.add(id);
        chatApi
          .getConversation(id)
          .then((conversation) => {
            setCached(id, conversation);
            // If this chat is currently active (cold-start race), surface immediately
            if (get().activeConversationId === id && !get().activeConversation) {
              set({ activeConversation: conversation, isLoading: false });
            }
          })
          .catch(() => { /* silent fail — prefetch is best-effort */ })
          .finally(() => {
            _prefetching.delete(id);
          });
      },

      // ── Send message with in-place cache update ───────────────────────────
      sendMessage: async (query) => {
        const { activeConversationId, activeConversation } = get();
        const isNewConversation = !activeConversationId;
        // Snapshot the originating conversation ID so we can guard against
        // the user switching to a different chat before the response arrives.
        const originatingConvId = activeConversationId;

        const optimisticTitle =
          query.length > 55 ? query.slice(0, 55) + '…' : query;

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

        let generatingTimer: ReturnType<typeof setTimeout> | null = null;
        if (tempId !== null) {
          generatingTimer = setTimeout(() => {
            get()._updatePendingStatus(tempId!, 'generating');
          }, 500);
        }

        try {
          const response = await chatApi.sendMessage(query, activeConversationId || undefined);

          if (generatingTimer !== null) clearTimeout(generatingTimer);

          // Reload full conversation
          const conversation = await chatApi.getConversation(response.conversation_id);

          // ── Update cache so the result is available for instant render ──────
          setCached(response.conversation_id, conversation);

          // Only surface the result into the UI if the user hasn't switched to
          // a different conversation while we were waiting for the response.
          // If they switched away, the completed message is safely in the LRU
          // cache and will appear when they navigate back.
          const stillOnOriginalConv =
            get().activeConversationId === originatingConvId ||
            get().activeConversationId === response.conversation_id ||
            // Also update if it was a new conversation (tempId path) —
            // in that case the response gives us the real ID for the first time.
            isNewConversation;

          if (stillOnOriginalConv) {
            set({
              activeConversation: conversation,
              activeConversationId: response.conversation_id,
              pendingUserMessage: null,
            });
          } else {
            // User has navigated away — just clean up the pending state that
            // belongs to *this* request without touching the current view.
            // pendingUserMessage was already cleared by setActiveConversation.
          }

          // Force-refresh the sidebar list so the new/updated entry appears
          await get().loadConversations(true);

          if (tempId !== null) {
            get()._removePending(tempId);
            set({
              completionToast: {
                id: response.conversation_id,
                title: optimisticTitle,
                success: true,
              },
            });
            setTimeout(() => get().dismissToast(), 4000);
          }
        } catch (error) {
          if (generatingTimer !== null) clearTimeout(generatingTimer);

          const message =
            error instanceof Error ? error.message : 'Failed to send message';

          set({ error: message, pendingUserMessage: null, input: query });

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
            set({
              completionToast: {
                id: activeConversationId!,
                title: activeConversation?.title || 'Chat',
                success: false,
                errorDetail: message,
              },
            });
          }

          setTimeout(() => get().dismissToast(), 6000);
        } finally {
          // Only clear the spinner for the conversation this request belongs to.
          // If the user has already switched away, leave the current view's
          // isLoading state untouched (it may be a cold-start fetch for the new chat).
          const currentId = get().activeConversationId;
          if (currentId === originatingConvId || isNewConversation) {
            set({ isLoading: false });
          }
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
        evictCached(id); // Remove from LRU cache immediately
        await chatApi.deleteConversation(id);
        const { activeConversationId } = get();
        if (activeConversationId === id) {
          set({ activeConversationId: null, activeConversation: null });
        }
        // Force sidebar refresh after delete
        await get().loadConversations(true);
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
      // Persist the sidebar list + its fetch timestamp so the sidebar renders
      // immediately on page load without waiting for the first API response.
      partialize: (state) => ({
        activeConversationId: state.activeConversationId,
        conversations: state.conversations,
        lastConversationsFetch: state.lastConversationsFetch,
      }),
    }
  )
);
