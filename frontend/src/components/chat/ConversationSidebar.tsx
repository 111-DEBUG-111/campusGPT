import React, { useEffect, useState } from 'react';
import { Plus, MessageSquare, Trash2, LayoutDashboard, GraduationCap, Menu, X } from 'lucide-react';
import { useChatStore } from '../../stores/chatStore';
import { useNavigate, useLocation } from 'react-router-dom';

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

  useEffect(() => {
    loadConversations();
  }, []);

  const handleConvClick = async (id: number) => {
    await setActiveConversation(id);
    setMobileOpen(false);
  };

  const handleDelete = async (e: React.MouseEvent, id: number) => {
    e.stopPropagation();
    if (confirm('Delete this conversation?')) {
      await deleteConversation(id);
    }
  };

  const SidebarContent = () => (
    <>
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
          <div
            key={conv.id}
            className={`conv-item group ${activeConversationId === conv.id ? 'active' : ''}`}
            onClick={() => handleConvClick(conv.id)}
            role="button"
            tabIndex={0}
            aria-label={`Conversation: ${conv.title}`}
          >
            <MessageSquare size={14} className="flex-shrink-0" />
            <span className="conv-item-title">{conv.title}</span>
            <span className="conv-item-count">{conv.message_count}</span>
            <button
              className="conv-delete-btn"
              onClick={(e) => handleDelete(e, conv.id)}
              aria-label="Delete conversation"
            >
              <Trash2 size={12} />
            </button>
          </div>
        ))}
        {conversations.length === 0 && (
          <p style={{ color: '#2a2d3a', fontSize: '12px', textAlign: 'center', padding: '16px' }}>
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
    </>
  );

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
        <SidebarContent />
      </div>
    </>
  );
};
