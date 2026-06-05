import { apiClient, getAdminHeaders } from './client';
import type { Document, AnalyticsSummary } from '../types';

interface DocumentListResponse {
  documents: Document[];
  total: number;
}

export const adminApi = {
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
      headers: {
        ...getAdminHeaders(),
        'Content-Type': 'multipart/form-data',
      },
    });
    return data;
  },

  listDocuments: async (): Promise<DocumentListResponse> => {
    const { data } = await apiClient.get('/api/admin/documents', {
      headers: getAdminHeaders(),
    });
    return data;
  },

  deleteDocument: async (id: number): Promise<void> => {
    await apiClient.delete(`/api/admin/documents/${id}`, {
      headers: getAdminHeaders(),
    });
  },

  reindex: async (): Promise<{ message: string; documents_reindexed: number }> => {
    const { data } = await apiClient.post(
      '/api/admin/reindex',
      {},
      { headers: getAdminHeaders() }
    );
    return data;
  },

  getAnalytics: async (): Promise<AnalyticsSummary> => {
    const { data } = await apiClient.get('/api/admin/analytics', {
      headers: getAdminHeaders(),
    });
    return data;
  },
};
