import React from 'react';
import { ConversationSidebar } from '../components/chat/ConversationSidebar';
import { ChatWindow } from '../components/chat/ChatWindow';
import { useNavigate } from 'react-router-dom';

const ChatPage: React.FC = () => {
  const navigate = useNavigate();

  return (
    <div className="app-layout">
      <ConversationSidebar onAdminClick={() => navigate('/admin')} />
      <ChatWindow />
    </div>
  );
};

export default ChatPage;
