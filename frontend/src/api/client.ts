import axios from 'axios';
import { getSessionToken } from '../lib/session';

const BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

export const apiClient = axios.create({
  baseURL: BASE_URL,
  timeout: 60000, // 60s — RAG pipeline can be slow
  withCredentials: true, // send the HttpOnly campusgpt_admin_session cookie automatically
  headers: {
    'Content-Type': 'application/json',
  },
});

// ── Request interceptor ───────────────────────────────────────────────────────
// Attaches the anonymous session token to every request.
// Admin session is carried by an HttpOnly cookie — no JS reads or sends the key.
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
