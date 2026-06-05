import React, { useRef, useEffect, useState } from 'react';
import { useChatStore } from '../../stores/chatStore';
import { MessageBubble } from './MessageBubble';
import { ChatInput } from './ChatInput';
import { Bot, GraduationCap, BookOpen, Building2, Users, Briefcase } from 'lucide-react';

const SUGGESTIONS = [
  { icon: '🎓', text: 'What is the minimum attendance requirement?', category: 'academics' },
  { icon: '💼', text: 'How does the placement process work?', category: 'placements' },
  { icon: '🏠', text: 'Tell me about hostel facilities and rules', category: 'hostel' },
  { icon: '🎯', text: 'What clubs and societies can I join?', category: 'clubs' },
  { icon: '📋', text: 'What are the academic backlog policies?', category: 'policies' },
  { icon: '💻', text: 'How do I find internship opportunities?', category: 'internships' },
];

export const ChatWindow: React.FC = () => {
  const {
    activeConversation,
    isLoading,
    pendingUserMessage,
    sendMessage,
    error,
    clearError,
  } = useChatStore();

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const hasMessages =
    (activeConversation?.messages?.length ?? 0) > 0 || pendingUserMessage;

  // Auto-scroll on new messages
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [activeConversation?.messages, pendingUserMessage, isLoading]);

  const handleSuggestion = (text: string) => {
    sendMessage(text);
  };

  return (
    <div className="chat-main">
      {/* Topbar */}
      <div className="chat-topbar">
        <div>
          <p className="chat-topbar-title">
            {activeConversation?.title ?? 'CampusGPT'}
          </p>
          <p className="chat-topbar-subtitle">
            AI Assistant • Powered by Gemini 2.5 Flash
          </p>
        </div>
        <div className="flex items-center gap-2">
          <div className="w-2 h-2 rounded-full bg-green-500 animate-pulse" />
          <span style={{ color: '#475569', fontSize: '12px' }}>Online</span>
        </div>
      </div>

      {/* Messages */}
      <div className="chat-messages">
        {!hasMessages ? (
          <WelcomeScreen onSuggestion={handleSuggestion} />
        ) : (
          <>
            {activeConversation?.messages.map((message) => (
              <MessageBubble key={message.id} message={message} />
            ))}

            {/* Pending user message (optimistic) */}
            {pendingUserMessage && (
              <div className="message-bubble-wrapper message-user">
                <div className="avatar avatar-user">
                  <span style={{ fontSize: '14px' }}>👤</span>
                </div>
                <div className="message-content-wrapper">
                  <div className="message-bubble bubble-user">
                    <p className="message-text">{pendingUserMessage}</p>
                  </div>
                </div>
              </div>
            )}

            {/* Typing indicator */}
            {isLoading && (
              <div className="message-bubble-wrapper message-assistant">
                <div className="avatar avatar-bot">
                  <Bot size={16} />
                </div>
                <div className="message-content-wrapper">
                  <div className="typing-indicator">
                    <div className="typing-dot" />
                    <div className="typing-dot" />
                    <div className="typing-dot" />
                  </div>
                  <span style={{ color: '#475569', fontSize: '11px', marginTop: '4px' }}>
                    CampusGPT is thinking…
                  </span>
                </div>
              </div>
            )}
          </>
        )}

        {/* Error banner */}
        {error && (
          <div
            className="alert alert-error max-w-3xl mx-auto mt-2"
            onClick={clearError}
            style={{ cursor: 'pointer' }}
          >
            ⚠️ {error} — Click to dismiss
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <ChatInput />
    </div>
  );
};

const WelcomeScreen: React.FC<{ onSuggestion: (text: string) => void }> = ({
  onSuggestion,
}) => (
  <div className="welcome-screen">
    <div className="welcome-logo">
      <GraduationCap size={40} color="white" />
    </div>
    <h1 className="welcome-title">CampusGPT</h1>
    <p className="welcome-subtitle">
      Your AI-powered campus companion. Ask me anything about academics,
      placements, clubs, hostel life, or university policies.
    </p>
    <div className="suggestion-grid">
      {SUGGESTIONS.map((s, i) => (
        <button
          key={i}
          className="suggestion-chip"
          onClick={() => onSuggestion(s.text)}
        >
          <span className="suggestion-chip-icon">{s.icon}</span>
          <span className="suggestion-chip-text">{s.text}</span>
        </button>
      ))}
    </div>
  </div>
);
