import React, { useEffect, useState } from 'react';
import {
  Plus,
  MessageSquare,
  Trash2,
  LayoutDashboard,
  GraduationCap,
  Menu,
  X,
  AlertTriangle,
  Loader2,
  CheckCircle2,
  XCircle,
  Search,
} from 'lucide-react';
import { useChatStore } from '../../stores/chatStore';
import type { PendingConversationStatus } from '../../types';

interface ConversationSidebarProps {
  onAdminClick: () => void;
}

// ── Status badge helpers ──────────────────────────────────────────────────────

interface BadgeConfig {
  label: string;
  icon: React.ReactNode;
  className: string;
}

function getStatusBadge(status: PendingConversationStatus): BadgeConfig {
  switch (status) {
    case 'retrieving':
      return {
        label: 'Retrieving…',
        icon: <Search size={9} />,
        className: 'pending-badge pending-badge-retrieving',
      };
    case 'generating':
      return {
        label: 'Generating…',
        icon: <Loader2 size={9} className="animate-spin" />,
        className: 'pending-badge pending-badge-generating',
      };
    case 'failed':
      return {
        label: 'Failed',
        icon: <XCircle size={9} />,
        className: 'pending-badge pending-badge-failed',
      };
  }
}

// ── Component ─────────────────────────────────────────────────────────────────

export const ConversationSidebar: React.FC<ConversationSidebarProps> = ({ onAdminClick }) => {
  const {
    conversations,
    activeConversationId,
    pendingConversations,
    completionToast,
    loadConversations,
    setActiveConversation,
    startNewChat,
    deleteConversation,
    dismissToast,
    _removePending,
  } = useChatStore();

  const [mobileOpen, setMobileOpen] = useState(false);
  const [confirmDeleteId, setConfirmDeleteId] = useState<number | null>(null);
  const [deleting, setDeleting] = useState(false);

  useEffect(() => {
    loadConversations();
  }, []);

  const handleConvClick = async (id: number) => {
    if (confirmDeleteId !== null) return;
    await setActiveConversation(id);
    setMobileOpen(false);
  };

  const handleDeleteClick = (e: React.MouseEvent, id: number) => {
    e.stopPropagation();
    e.preventDefault();
    setConfirmDeleteId(id);
  };

  const handleConfirmDelete = async () => {
    if (confirmDeleteId === null) return;
    setDeleting(true);
    try {
      await deleteConversation(confirmDeleteId);
    } finally {
      setDeleting(false);
      setConfirmDeleteId(null);
    }
  };

  const handleCancelDelete = (e?: React.MouseEvent) => {
    e?.stopPropagation();
    setConfirmDeleteId(null);
  };

  const hasPending = pendingConversations.length > 0;

  return (
    <>
      {/* Mobile hamburger */}
      <button
        className="fixed top-4 left-4 z-50 md:hidden flex items-center justify-center w-9 h-9 rounded-xl"
        style={{ background: '#111318', border: '1px solid #1f2330', color: '#94a3b8' }}
        onClick={() => setMobileOpen(!mobileOpen)}
        aria-label="Toggle sidebar"
      >
        {mobileOpen ? <X size={18} /> : <Menu size={18} />}
      </button>

      {/* Mobile overlay */}
      {mobileOpen && (
        <div
          className="sidebar-overlay"
          onClick={() => setMobileOpen(false)}
        />
      )}

      {/* Sidebar */}
      <div className={`sidebar ${mobileOpen ? 'open' : ''}`}>
        {/* Header */}
        <div className="sidebar-header">
          <div className="sidebar-logo">
            <GraduationCap size={20} color="white" />
          </div>
          <div>
            <p className="sidebar-title">CampusGPT</p>
            <p className="sidebar-subtitle">Campus AI Assistant</p>
          </div>
        </div>

        {/* New Chat */}
        <button
          id="new-chat-btn"
          className="new-chat-btn"
          onClick={() => { startNewChat(); setMobileOpen(false); }}
        >
          <Plus size={16} />
          New Conversation
        </button>

        {/* Conversation list */}
        <div className="sidebar-nav">

          {/* ── Active / Pending chats ─── */}
          {hasPending && (
            <>
              <p className="sidebar-section-label">Active</p>
              {pendingConversations.map((pending) => {
                const badge = getStatusBadge(pending.status);
                return (
                  <div
                    key={pending.tempId}
                    className={`conv-item conv-item-pending ${pending.status === 'failed' ? 'conv-item-failed' : ''}`}
                    aria-label={`Processing: ${pending.title}`}
                    title={pending.error || undefined}
                  >
                    {/* Animated left accent */}
                    {pending.status !== 'failed' && (
                      <span className="pending-pulse-dot" />
                    )}
                    {pending.status === 'failed' && (
                      <XCircle size={14} style={{ color: '#ef4444', flexShrink: 0 }} />
                    )}
                    <span className="conv-item-title" style={{ color: pending.status === 'failed' ? '#fca5a5' : '#e2e8f0' }}>
                      {pending.title}
                    </span>
                    <span className={badge.className}>
                      {badge.icon}
                      {badge.label}
                    </span>
                    {pending.status === 'failed' && (
                      <button
                        className="conv-delete-btn"
                        style={{ opacity: 1 }}
                        onClick={(e) => {
                          e.stopPropagation();
                          _removePending(pending.tempId);
                        }}
                        aria-label="Dismiss failed chat"
                        type="button"
                      >
                        <X size={12} />
                      </button>
                    )}
                  </div>
                );
              })}
            </>
          )}

          {/* ── Past conversations ─── */}
          {conversations.length > 0 && (
            <p className="sidebar-section-label">{hasPending ? 'Recent Chats' : 'Recent Chats'}</p>
          )}
          {conversations.map((conv) => (
            <div key={conv.id}>
              {confirmDeleteId === conv.id ? (
                /* ── Inline delete confirmation ── */
                <div className="conv-delete-confirm">
                  <div className="conv-delete-confirm-inner">
                    <AlertTriangle size={13} style={{ color: '#f59e0b', flexShrink: 0 }} />
                    <span className="conv-delete-confirm-text">Delete this chat?</span>
                  </div>
                  <div className="conv-delete-confirm-actions">
                    <button
                      className="conv-delete-confirm-cancel"
                      onClick={handleCancelDelete}
                      disabled={deleting}
                    >
                      Cancel
                    </button>
                    <button
                      className="conv-delete-confirm-ok"
                      onClick={handleConfirmDelete}
                      disabled={deleting}
                    >
                      {deleting ? '…' : 'Delete'}
                    </button>
                  </div>
                </div>
              ) : (
                /* ── Normal conversation row ── */
                <div
                  className={`conv-item ${activeConversationId === conv.id ? 'active' : ''}`}
                  onClick={() => handleConvClick(conv.id)}
                  role="button"
                  tabIndex={0}
                  onKeyDown={(e) => e.key === 'Enter' && handleConvClick(conv.id)}
                  aria-label={`Conversation: ${conv.title}`}
                >
                  <MessageSquare size={14} className="flex-shrink-0" />
                  <span className="conv-item-title">{conv.title}</span>
                  <span className="conv-item-count">{conv.message_count}</span>
                  <button
                    className="conv-delete-btn"
                    onClick={(e) => handleDeleteClick(e, conv.id)}
                    aria-label="Delete conversation"
                    type="button"
                  >
                    <Trash2 size={12} />
                  </button>
                </div>
              )}
            </div>
          ))}

          {conversations.length === 0 && !hasPending && (
            <p style={{ color: '#475569', fontSize: '12px', textAlign: 'center', padding: '16px' }}>
              No conversations yet.<br />Start one above!
            </p>
          )}
        </div>

        {/* Footer */}
        <div className="sidebar-footer">
          <button
            id="admin-link"
            className="sidebar-footer-btn"
            onClick={() => { onAdminClick(); setMobileOpen(false); }}
          >
            <LayoutDashboard size={16} />
            Admin Dashboard
          </button>
        </div>
      </div>

      {/* ── Completion Toast ─────────────────────────────────────────────── */}
      {completionToast && (
        <div
          className={`completion-toast ${completionToast.success ? 'completion-toast-success' : 'completion-toast-error'}`}
          role="status"
          aria-live="polite"
        >
          <div className="completion-toast-icon">
            {completionToast.success
              ? <CheckCircle2 size={16} />
              : <XCircle size={16} />
            }
          </div>
          <div className="completion-toast-body">
            <p className="completion-toast-label">
              {completionToast.success ? 'Response ready' : 'Request failed'}
            </p>
            <p className="completion-toast-title">{completionToast.title}</p>
            {completionToast.errorDetail && (
              <p style={{ fontSize: '11px', color: '#fca5a5', marginTop: '2px', lineHeight: '1.3' }}>
                {completionToast.errorDetail}
              </p>
            )}
          </div>
          <button
            className="completion-toast-close"
            onClick={dismissToast}
            aria-label="Dismiss notification"
          >
            <X size={13} />
          </button>
        </div>
      )}
    </>
  );
};
