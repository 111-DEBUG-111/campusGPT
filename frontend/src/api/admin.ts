import { apiClient } from './client';
import type { Document, AnalyticsSummary, KnowledgeGap } from '../types';
import type { DocumentSourceType } from '../types';

interface DocumentListResponse {
  documents: Document[];
  total: number;
}

interface DocumentPatch {
  source_type?: DocumentSourceType;
  author?: string | null;
  category?: string;
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
    description: string,
    sourceType: DocumentSourceType = 'official',
    author?: string,
  ): Promise<Document> => {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('category', category);
    formData.append('description', description);
    formData.append('source_type', sourceType);
    if (author) formData.append('author', author);

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

  /** Update source classification (and optionally category/author) for a document. */
  updateDocument: async (id: number, patch: DocumentPatch): Promise<Document> => {
    const { data } = await apiClient.patch(`/api/admin/documents/${id}`, patch);
    return data;
  },

  reindex: async (): Promise<{ message: string; documents_reindexed: number }> => {
    const { data } = await apiClient.post('/api/admin/reindex', {});
    return data;
  },

  getAnalytics: async (): Promise<AnalyticsSummary> => {
    const { data } = await apiClient.get('/api/admin/analytics');
    return data;
  },

  getKnowledgeGaps: async (): Promise<KnowledgeGap[]> => {
    const { data } = await apiClient.get('/api/admin/knowledge-gaps');
    return data;
  },
};
