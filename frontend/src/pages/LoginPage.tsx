import React, { useState } from 'react';
import { GraduationCap, Lock, Eye, EyeOff, Loader2, ArrowLeft } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { adminApi } from '../api/admin';

const LoginPage: React.FC = () => {
  const [key, setKey] = useState('');
  const [showKey, setShowKey] = useState(false);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!key.trim()) return;

    setLoading(true);
    setError('');

    try {
      // Send the key once to the backend; the server verifies it and sets an
      // HttpOnly session cookie. The key is never stored in JS after this call.
      await adminApi.login(key);
      navigate('/admin');
    } catch {
      setError('Invalid admin key. Please check and try again.');
    } finally {
      setLoading(false);
    }
  };


  return (
    <div
      className="flex items-center justify-center h-full"
      style={{ background: '#0a0b0f' }}
    >
      <div
        className="w-full max-w-sm p-8 rounded-3xl"
        style={{ background: '#111318', border: '1px solid #1f2330' }}
      >
        {/* Logo */}
        <div className="flex flex-col items-center mb-8">
          <div
            className="flex items-center justify-center w-16 h-16 rounded-2xl mb-4"
            style={{
              background: 'linear-gradient(135deg, #6366f1, #06b6d4)',
              boxShadow: '0 0 40px rgba(99,102,241,0.3)',
            }}
          >
            <GraduationCap size={32} color="white" />
          </div>
          <h1 className="text-xl font-bold" style={{ color: '#f1f5f9' }}>
            Admin Access
          </h1>
          <p className="text-sm mt-1" style={{ color: '#475569' }}>
            CampusGPT Dashboard
          </p>
        </div>

        <form onSubmit={handleLogin} className="space-y-4">
          <div>
            <label className="form-label" htmlFor="admin-key-input">
              Admin API Key
            </label>
            <div className="relative">
              <div className="absolute inset-y-0 left-3 flex items-center" style={{ color: '#475569' }}>
                <Lock size={16} />
              </div>
              <input
                id="admin-key-input"
                type={showKey ? 'text' : 'password'}
                className="form-input pl-10 pr-10"
                placeholder="Enter your admin key"
                value={key}
                onChange={(e) => setKey(e.target.value)}
                autoComplete="current-password"
              />
              <button
                type="button"
                className="absolute inset-y-0 right-3 flex items-center"
                style={{ color: '#475569' }}
                onClick={() => setShowKey(!showKey)}
                aria-label={showKey ? 'Hide key' : 'Show key'}
              >
                {showKey ? <EyeOff size={16} /> : <Eye size={16} />}
              </button>
            </div>
          </div>

          {error && (
            <div className="alert alert-error text-xs">
              ⚠️ {error}
            </div>
          )}

          <button
            id="admin-login-btn"
            type="submit"
            className="btn btn-primary w-full justify-center py-3"
            disabled={!key.trim() || loading}
          >
            {loading ? (
              <><Loader2 size={16} className="animate-spin" /> Verifying…</>
            ) : (
              'Access Dashboard'
            )}
          </button>

          <button
            id="admin-back-btn"
            type="button"
            className="btn btn-secondary w-full justify-center py-3"
            onClick={() => navigate('/')}
            disabled={loading}
          >
            <ArrowLeft size={16} /> Back to Home
          </button>
        </form>
      </div>
    </div>
  );
};

export default LoginPage;
