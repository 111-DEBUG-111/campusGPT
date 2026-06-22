import React, { useEffect } from 'react';
import { ConversationSidebar } from '../components/chat/ConversationSidebar';
import { ChatWindow } from '../components/chat/ChatWindow';
import { useNavigate } from 'react-router-dom';
import { chatApi } from '../api/chat';

const ChatPage: React.FC = () => {
  const navigate = useNavigate();

  useEffect(() => {
    chatApi.recordVisit().catch(() => {});
  }, []);

  return (
    <div className="app-layout">
      <ConversationSidebar onAdminClick={() => navigate('/admin')} />
      <ChatWindow />
    </div>
  );
};

export default ChatPage;
