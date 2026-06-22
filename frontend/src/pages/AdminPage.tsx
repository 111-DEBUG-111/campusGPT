import React, { useEffect, useState } from 'react';
import {
  GraduationCap, Upload, FileText, BarChart2,
  ArrowLeft, RefreshCw, Loader2, AlertCircle, CheckCircle, HelpCircle
} from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { DocumentUpload } from '../components/admin/DocumentUpload';
import { DocumentList } from '../components/admin/DocumentList';
import { AnalyticsDashboard } from '../components/admin/AnalyticsDashboard';
import { KnowledgeGapsList } from '../components/admin/KnowledgeGapsList';
import { useAdminStore } from '../stores/adminStore';

type Tab = 'upload' | 'documents' | 'gaps' | 'analytics';

const AdminPage: React.FC = () => {
  const navigate = useNavigate();
  const [activeTab, setActiveTab] = useState<Tab>('documents');
  const {
    loadDocuments,
    loadAnalytics,
    loadKnowledgeGaps,
    analytics,
    knowledgeGaps,
    isLoading,
    error,
    successMessage,
    clearMessages,
  } = useAdminStore();

  // Guard: attempt to load data; if cookie is missing/expired the backend
  // returns 401 and loadDocuments/loadAnalytics will surface the error.
  // We catch that here and redirect to login.
  useEffect(() => {
    (async () => {
      try {
        await Promise.all([loadDocuments(), loadAnalytics(), loadKnowledgeGaps()]);
      } catch (err: any) {
        if (err?.message?.includes('401') || err?.message?.toLowerCase().includes('session')) {
          navigate('/admin/login');
        }
      }
    })();
  }, []);

  // Auto-dismiss messages
  useEffect(() => {
    if (successMessage || error) {
      const t = setTimeout(clearMessages, 4000);
      return () => clearTimeout(t);
    }
  }, [successMessage, error]);

  const tabs: { id: Tab; label: string; icon: React.ReactNode }[] = [
    { id: 'documents', label: 'Documents', icon: <FileText size={15} /> },
    { id: 'upload', label: 'Upload', icon: <Upload size={15} /> },
    { id: 'gaps', label: 'Knowledge Gaps', icon: <HelpCircle size={15} /> },
    { id: 'analytics', label: 'Analytics', icon: <BarChart2 size={15} /> },
  ];

  return (
    <div className="admin-layout">
      {/* Topbar */}
      <div className="admin-topbar">
        <div className="flex items-center gap-3">
          <div
            className="flex items-center justify-center w-9 h-9 rounded-xl"
            style={{ background: 'linear-gradient(135deg, #6366f1, #06b6d4)' }}
          >
            <GraduationCap size={18} color="white" />
          </div>
          <div>
            <p className="font-semibold" style={{ color: '#f1f5f9' }}>CampusGPT Admin</p>
            <p className="text-xs" style={{ color: '#475569' }}>Knowledge Base Management</p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <button
            className="btn btn-secondary text-xs"
            onClick={() => { loadDocuments(); loadAnalytics(); loadKnowledgeGaps(); }}
            aria-label="Refresh data"
          >
            <RefreshCw size={12} />
            Refresh
          </button>
          <button
            id="back-to-chat-btn"
            className="btn btn-secondary text-xs"
            onClick={() => navigate('/')}
          >
            <ArrowLeft size={12} />
            Back to Chat
          </button>
        </div>
      </div>

      {/* Toast messages */}
      {(successMessage || error) && (
        <div className={`mx-6 mt-3 alert ${error ? 'alert-error' : 'alert-success'}`}>
          {error ? <AlertCircle size={14} /> : <CheckCircle size={14} />}
          {error || successMessage}
        </div>
      )}

      {/* Tabs */}
      <div className="admin-tabs">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            id={`admin-tab-${tab.id}`}
            className={`admin-tab ${activeTab === tab.id ? 'active' : ''}`}
            onClick={() => {
              setActiveTab(tab.id);
              if (tab.id === 'gaps') {
                loadKnowledgeGaps();
              }
            }}
          >
            {tab.icon}
            {tab.label}
          </button>
        ))}
      </div>

      {/* Content */}
      <div className="admin-content">
        {activeTab === 'upload' && (
          <div className="max-w-2xl mx-auto">
            <DocumentUpload />
          </div>
        )}

        {activeTab === 'documents' && (
          <DocumentList />
        )}

        {activeTab === 'gaps' && (
          <KnowledgeGapsList
            gaps={knowledgeGaps}
            isLoading={isLoading && knowledgeGaps.length === 0}
            onUploadClick={() => setActiveTab('upload')}
          />
        )}

        {activeTab === 'analytics' && (
          analytics ? (
            <AnalyticsDashboard analytics={analytics} />
          ) : (
            <div className="flex items-center justify-center h-64">
              <Loader2 size={24} className="animate-spin" style={{ color: '#6366f1' }} />
            </div>
          )
        )}
      </div>
    </div>
  );
};

export default AdminPage;
