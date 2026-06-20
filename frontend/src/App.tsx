import React, { Suspense, lazy } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { Toaster } from 'react-hot-toast';
import { Loader2 } from 'lucide-react';
import { getSessionToken } from './lib/session';

// Eagerly initialize the session token before any component renders.
// This guarantees the UUID exists in localStorage before the first API call.
getSessionToken();

const ChatPage = lazy(() => import('./pages/ChatPage'));
const AdminPage = lazy(() => import('./pages/AdminPage'));
const LoginPage = lazy(() => import('./pages/LoginPage'));

const LoadingFallback = () => (
  <div
    className="flex items-center justify-center h-full"
    style={{ background: '#0a0b0f' }}
  >
    <div className="flex flex-col items-center gap-3">
      <Loader2 size={32} className="animate-spin" style={{ color: '#6366f1' }} />
      <p className="text-sm" style={{ color: '#475569' }}>Loading CampusGPT…</p>
    </div>
  </div>
);

function App() {
  return (
    <BrowserRouter>
      <Toaster
        position="top-right"
        toastOptions={{
          style: {
            background: '#1a1d25',
            color: '#f1f5f9',
            border: '1px solid #2a2d3a',
            borderRadius: '12px',
          },
        }}
      />
      <Suspense fallback={<LoadingFallback />}>
        <Routes>
          <Route path="/" element={<ChatPage />} />
          <Route path="/admin" element={<AdminPage />} />
          <Route path="/admin/login" element={<LoginPage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </Suspense>
    </BrowserRouter>
  );
}

export default App;
