import React, { useRef, useEffect } from 'react';
import { useChatStore } from '../../stores/chatStore';
import { MessageBubble } from './MessageBubble';
import { ChatInput } from './ChatInput';
import { KnowledgeModeSelector } from './KnowledgeModeSelector';
import { Bot, GraduationCap, RefreshCw } from 'lucide-react';

const SUGGESTIONS = [
  { icon: '🎓', text: 'What is the minimum attendance requirement?', category: 'academics' },
  { icon: '💼', text: 'How does the placement process work?', category: 'placements' },
  { icon: '🏠', text: 'Tell me about hostel facilities and rules', category: 'hostel' },
  { icon: '🎯', text: 'What clubs and societies can I join?', category: 'clubs' },
  { icon: '📋', text: 'What are the academic backlog policies?', category: 'policies' },
  { icon: '💻', text: 'How do I find internship opportunities?', category: 'internships' },
];

interface ProgressPanelProps {
  stageKey: string;
  status: string;
  errorMessage: string | null;
}

const RAG_STAGES = [
  { key: 'Rewriting Query', label: 'Rewriting query', icon: '🔄' },
  { key: 'Retrieving Documents', label: 'Retrieving relevant documents', icon: '🔍' },
  { key: 'Reranking Results', label: 'Reranking sources', icon: '🎯' },
  { key: 'Generating Response', label: 'Generating answer', icon: '✍️' },
];

const RAGProgressPanel: React.FC<ProgressPanelProps> = ({
  stageKey,
  status,
  errorMessage,
}) => {
  const currentStageIndex = RAG_STAGES.findIndex(s => s.key === stageKey);
  const activeIndex = stageKey === 'Complete' ? RAG_STAGES.length : (currentStageIndex === -1 ? 0 : currentStageIndex);

  return (
    <div className="rag-progress-panel">
      {RAG_STAGES.map((stage, idx) => {
        let state: 'completed' | 'active' | 'pending' | 'failed' = 'pending';
        if (idx < activeIndex) {
          state = 'completed';
        } else if (idx === activeIndex) {
          if (status === 'failed') {
            state = 'failed';
          } else {
            state = 'active';
          }
        }

        return (
          <div key={stage.key} className={`rag-progress-row rag-stage-${state}`}>
            <span className="rag-stage-icon">
              {state === 'completed' && <span className="rag-icon-completed">✅</span>}
              {state === 'failed' && <span className="rag-icon-failed">❌</span>}
              {state === 'active' && (
                <span className="rag-icon-active inline-block animate-pulse">
                  {stage.icon}
                </span>
              )}
              {state === 'pending' && <span className="rag-icon-pending opacity-35">{stage.icon}</span>}
            </span>
            <span className="rag-stage-label">
              {stage.label}
              {state === 'active' && '...'}
            </span>
            {state === 'failed' && errorMessage && (
              <span className="rag-stage-error-text">
                ({errorMessage})
              </span>
            )}
          </div>
        );
      })}
    </div>
  );
};

export const ChatWindow: React.FC = () => {
  const {
    activeConversation,
    activeConversationId,
    isLoading,
    isBackgroundRefreshing,
    pendingMessages,
    pendingRequests,
    progress,
    sendMessage,
    error,
    clearError,
  } = useChatStore();

  // The optimistic message for this specific conversation (survives chat switches).
  // Uses sentinel key 0 for the "new chat" pane where activeConversationId is null.
  const convKey = activeConversationId ?? 0;
  const pendingUserMessage = pendingMessages[convKey] ?? null;
  const isProcessing = pendingUserMessage !== null;

  // Retrieve current request ID and progress state
  const currentRequestId = pendingRequests[convKey] ?? null;
  const activeProgressState = currentRequestId
    ? Object.values(progress).find(p => p.request_id === currentRequestId)
    : null;

  console.log("[RAG Progress] ChatWindow state:", {
    currentRequestId,
    progress,
    activeProgressState,
    convKey
  });

  const currentStageKey = activeProgressState?.stage || 'Rewriting Query';
  const currentStatus = activeProgressState?.status || 'in_progress';
  const progressErrorMessage = activeProgressState?.error_message ?? null;

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const hasMessages =
    (activeConversation?.messages?.length ?? 0) > 0 || isProcessing;

  // Auto-scroll on new messages or when typing indicator appears/disappears
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [activeConversation?.messages, isProcessing]);

  const handleSuggestion = (text: string) => {
    sendMessage(text);
  };

  // ── Cold-start skeleton: a chat is selected but nothing is in cache yet ──
  const showSkeleton = isLoading && !activeConversation && activeConversationId !== null;

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
        <div className="flex items-center gap-3">
          {/* Knowledge Source Mode selector */}
          <KnowledgeModeSelector />
          {/* Background refresh pill — shown only during silent cache refresh */}
          {isBackgroundRefreshing && (
            <span className="bg-refresh-pill" aria-label="Refreshing in background">
              <RefreshCw size={10} className="animate-spin" />
              Refreshing…
            </span>
          )}
          <div className="w-2 h-2 rounded-full bg-green-500 animate-pulse" />
          <span style={{ color: '#475569', fontSize: '12px' }}>Online</span>
        </div>
      </div>

      {/* Messages */}
      <div className="chat-messages">
        {showSkeleton ? (
          /* ── Cold-start skeleton ─────────────────────────────── */
          <div className="skeleton-container">
            <MessageSkeleton align="right" widths={['60%']} />
            <MessageSkeleton align="left"  widths={['90%', '70%', '50%']} />
            <MessageSkeleton align="right" widths={['45%']} />
            <MessageSkeleton align="left"  widths={['80%', '55%']} />
          </div>
        ) : !hasMessages ? (
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

            {/* Progress Panel — shown while a response is processing */}
            {isProcessing && (
              <div className="message-bubble-wrapper message-assistant">
                <div className="avatar avatar-bot">
                  <Bot size={16} />
                </div>
                <div className="message-content-wrapper">
                  <RAGProgressPanel
                    stageKey={currentStageKey}
                    status={currentStatus}
                    errorMessage={progressErrorMessage}
                  />
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

// ── Skeleton loading rows ─────────────────────────────────────────────────────

interface SkeletonProps {
  align: 'left' | 'right';
  widths: string[];
}

const MessageSkeleton: React.FC<SkeletonProps> = ({ align, widths }) => (
  <div className={`skeleton-row-wrapper skeleton-${align}`}>
    <div className="skeleton-avatar" />
    <div className="skeleton-lines">
      {widths.map((w, i) => (
        <div key={i} className="skeleton-line" style={{ width: w }} />
      ))}
    </div>
  </div>
);

// ── Welcome screen ────────────────────────────────────────────────────────────

const WelcomeScreen: React.FC<{ onSuggestion: (text: string) => void }> = ({
  onSuggestion,
}) => (
  <div className="welcome-screen">
    <div className="welcome-logo">
      <GraduationCap size={40} color="white" />
    </div>
    <h1 className="welcome-title">CampusGPT</h1>
    <p className="welcome-subtitle">
      Your AI companion for life at NST & Rishihood University. Ask me anything about academics,
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
