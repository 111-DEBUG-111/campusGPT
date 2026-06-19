import axios from 'axios';
import { getSessionToken } from '../lib/session';

const BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

export const apiClient = axios.create({
  baseURL: BASE_URL,
  timeout: 60000, // 60s — RAG pipeline can be slow
  headers: {
    'Content-Type': 'application/json',
  },
});

// ── Request interceptor ───────────────────────────────────────────────────────
// Attaches the anonymous session token to every request.
// Admin routes also receive it but it is ignored server-side (they use X-Admin-Key).
apiClient.interceptors.request.use(
  (config) => {
    config.headers['X-Session-Token'] = getSessionToken();
    return config;
  },
  (error) => Promise.reject(error)
);

// ── Response interceptor ──────────────────────────────────────────────────────
// Normalizes error messages into plain strings so callers don't need to dig.
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
