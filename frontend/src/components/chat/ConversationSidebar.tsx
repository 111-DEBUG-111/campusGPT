import React, { useEffect, useState } from 'react';
import { Plus, MessageSquare, Trash2, LayoutDashboard, GraduationCap, Menu, X, AlertTriangle } from 'lucide-react';
import { useChatStore } from '../../stores/chatStore';

interface ConversationSidebarProps {
  onAdminClick: () => void;
}

export const ConversationSidebar: React.FC<ConversationSidebarProps> = ({ onAdminClick }) => {
  const {
    conversations,
    activeConversationId,
    loadConversations,
    setActiveConversation,
    startNewChat,
    deleteConversation,
  } = useChatStore();

  const [mobileOpen, setMobileOpen] = useState(false);
  const [confirmDeleteId, setConfirmDeleteId] = useState<number | null>(null);
  const [deleting, setDeleting] = useState(false);

  useEffect(() => {
    loadConversations();
  }, []);

  const handleConvClick = async (id: number) => {
    if (confirmDeleteId !== null) return; // don't navigate while confirm is open
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
          {conversations.length > 0 && (
            <p className="sidebar-section-label">Recent Chats</p>
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
          {conversations.length === 0 && (
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
    </>
  );
};
