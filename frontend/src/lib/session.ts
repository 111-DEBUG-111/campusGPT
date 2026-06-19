/**
 * session.ts — Anonymous session token management
 *
 * CampusGPT uses anonymous persistent sessions:
 * - On first visit a UUID v4 is generated and stored in localStorage.
 * - On every subsequent visit the same token is read back.
 * - The token is sent with every chat API request as X-Session-Token.
 * - Conversations are scoped to this token on the backend.
 *
 * Clearing localStorage (or using a different browser/device) starts a fresh session.
 */

const STORAGE_KEY = 'campusgpt_session_token';

/** Minimal UUID v4 generator that works in all modern browsers. */
function generateUUID(): string {
  // Use crypto.randomUUID if available (Chrome 92+, Firefox 95+, Safari 15.4+)
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID();
  }

  // Polyfill for older environments
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    const v = c === 'x' ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
}

/**
 * Returns the persistent session token for this browser.
 * Creates and persists one on the very first call.
 */
export function getSessionToken(): string {
  try {
    let token = localStorage.getItem(STORAGE_KEY);
    if (!token || token.length < 8) {
      token = generateUUID();
      localStorage.setItem(STORAGE_KEY, token);
    }
    return token;
  } catch {
    // localStorage blocked (private browsing with strict settings, etc.)
    // Fall back to an in-memory token for this page load only.
    if (!(window as any).__campusgpt_fallback_token) {
      (window as any).__campusgpt_fallback_token = generateUUID();
    }
    return (window as any).__campusgpt_fallback_token;
  }
}

/**
 * Clears the current session token and generates a fresh one.
 * Call this if you want to "reset" the user's conversation history
 * (e.g., a "Start fresh" button).
 */
export function resetSession(): string {
  try {
    localStorage.removeItem(STORAGE_KEY);
  } catch {
    // ignore
  }
  return getSessionToken();
}
