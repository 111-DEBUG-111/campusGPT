import { create } from 'zustand';
import type { Document, AnalyticsSummary } from '../types';
import { adminApi } from '../api/admin';

interface AdminState {
  documents: Document[];
  totalDocuments: number;
  analytics: AnalyticsSummary | null;
  isLoading: boolean;
  isUploading: boolean;
  uploadProgress: number;
  error: string | null;
  successMessage: string | null;

  loadDocuments: () => Promise<void>;
  uploadDocument: (file: File, category: string, description: string) => Promise<void>;
  deleteDocument: (id: number) => Promise<void>;
  reindex: () => Promise<void>;
  loadAnalytics: () => Promise<void>;
  clearMessages: () => void;
}

export const useAdminStore = create<AdminState>((set, get) => ({
  documents: [],
  totalDocuments: 0,
  analytics: null,
  isLoading: false,
  isUploading: false,
  uploadProgress: 0,
  error: null,
  successMessage: null,

  loadDocuments: async () => {
    set({ isLoading: true, error: null });
    try {
      const response = await adminApi.listDocuments();
      set({ documents: response.documents, totalDocuments: response.total });
    } catch (error) {
      const msg = error instanceof Error ? error.message : 'Failed to load documents';
      set({ error: msg, isLoading: false });
      // Re-throw so callers (e.g. AdminPage) can redirect on 401
      throw error;
    } finally {
      set({ isLoading: false });
    }
  },

  uploadDocument: async (file, category, description) => {
    set({ isUploading: true, error: null, uploadProgress: 0 });
    try {
      await adminApi.uploadDocument(file, category, description);
      set({ successMessage: `"${file.name}" uploaded and queued for indexing`, uploadProgress: 100 });
      await get().loadDocuments();
    } catch (error) {
      set({ error: error instanceof Error ? error.message : 'Upload failed' });
    } finally {
      set({ isUploading: false });
    }
  },

  deleteDocument: async (id) => {
    set({ error: null });
    try {
      await adminApi.deleteDocument(id);
      set({ successMessage: 'Document deleted successfully' });
      await get().loadDocuments();
    } catch (error) {
      set({ error: error instanceof Error ? error.message : 'Delete failed' });
    }
  },

  reindex: async () => {
    set({ isLoading: true, error: null });
    try {
      const result = await adminApi.reindex();
      set({ successMessage: result.message });
    } catch (error) {
      set({ error: error instanceof Error ? error.message : 'Reindex failed' });
    } finally {
      set({ isLoading: false });
    }
  },

  loadAnalytics: async () => {
    set({ isLoading: true, error: null });
    try {
      const analytics = await adminApi.getAnalytics();
      set({ analytics });
    } catch (error) {
      const msg = error instanceof Error ? error.message : 'Failed to load analytics';
      set({ error: msg, isLoading: false });
      // Re-throw so callers (e.g. AdminPage) can redirect on 401
      throw error;
    } finally {
      set({ isLoading: false });
    }
  },

  clearMessages: () => set({ error: null, successMessage: null }),
}));
