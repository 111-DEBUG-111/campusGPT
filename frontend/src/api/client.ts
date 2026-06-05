import axios from 'axios';

const BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

export const apiClient = axios.create({
  baseURL: BASE_URL,
  timeout: 60000, // 60s — RAG pipeline can be slow
  headers: {
    'Content-Type': 'application/json',
  },
});

// Add request interceptor for logging
apiClient.interceptors.request.use(
  (config) => {
    return config;
  },
  (error) => Promise.reject(error)
);

// Add response interceptor for error normalization
apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    const message =
      error.response?.data?.detail ||
      error.message ||
      'An unexpected error occurred';
    return Promise.reject(new Error(message));
  }
);

export const getAdminHeaders = () => {
  // Check sessionStorage first (set at runtime by login page),
  // then fall back to build-time env var
  const key =
    sessionStorage.getItem('campusgpt_admin_key') ||
    import.meta.env.VITE_ADMIN_KEY ||
    '';
  return { 'x-admin-key': key };
};
