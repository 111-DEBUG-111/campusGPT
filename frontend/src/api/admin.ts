import { apiClient } from './client';
import type { Document, AnalyticsSummary } from '../types';

interface DocumentListResponse {
  documents: Document[];
  total: number;
}

export const adminApi = {
  /**
   * Verify the admin key server-side and receive an HttpOnly session cookie.
   * The key is never stored in the browser after this call.
   */
  login: async (key: string): Promise<void> => {
    await apiClient.post('/api/admin/login', { key });
  },

  /** Clear the server-side session cookie. */
  logout: async (): Promise<void> => {
    await apiClient.post('/api/admin/logout');
  },

  uploadDocument: async (
    file: File,
    category: string,
    description: string
  ): Promise<Document> => {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('category', category);
    formData.append('description', description);

    const { data } = await apiClient.post('/api/admin/upload', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
    return data;
  },

  listDocuments: async (): Promise<DocumentListResponse> => {
    const { data } = await apiClient.get('/api/admin/documents');
    return data;
  },

  deleteDocument: async (id: number): Promise<void> => {
    await apiClient.delete(`/api/admin/documents/${id}`);
  },

  reindex: async (): Promise<{ message: string; documents_reindexed: number }> => {
    const { data } = await apiClient.post('/api/admin/reindex', {});
    return data;
  },

  getAnalytics: async (): Promise<AnalyticsSummary> => {
    const { data } = await apiClient.get('/api/admin/analytics');
    return data;
  },
};
