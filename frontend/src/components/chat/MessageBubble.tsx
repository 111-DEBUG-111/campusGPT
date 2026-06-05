import React, { useState } from 'react';
import ReactMarkdown from 'react-markdown';
import { User, Bot, ChevronDown, ChevronUp } from 'lucide-react';
import type { Message } from '../../types';
import { CitationCard } from './CitationCard';
import { FeedbackButtons } from './FeedbackButtons';

interface MessageBubbleProps {
  message: Message;
}

export const MessageBubble: React.FC<MessageBubbleProps> = ({ message }) => {
  const [showSources, setShowSources] = useState(false);
  const isUser = message.role === 'user';
  const hasSources = message.sources && message.sources.length > 0;

  return (
    <div className={`message-bubble-wrapper ${isUser ? 'message-user' : 'message-assistant'}`}>
      <div className="message-avatar">
        {isUser ? (
          <div className="avatar avatar-user">
            <User size={16} />
          </div>
        ) : (
          <div className="avatar avatar-bot">
            <Bot size={16} />
          </div>
        )}
      </div>

      <div className="message-content-wrapper">
        <div className={`message-bubble ${isUser ? 'bubble-user' : 'bubble-assistant'}`}>
          {isUser ? (
            <p className="message-text">{message.content}</p>
          ) : (
            <div className="message-markdown">
              <ReactMarkdown>{message.content}</ReactMarkdown>
            </div>
          )}
        </div>

        {/* Citations toggle */}
        {!isUser && hasSources && (
          <div className="message-sources-section">
            <button
              className="sources-toggle"
              onClick={() => setShowSources(!showSources)}
              aria-expanded={showSources}
            >
              <span className="sources-count">
                {message.sources.length} source{message.sources.length > 1 ? 's' : ''}
              </span>
              {showSources ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
            </button>

            {showSources && (
              <div className="sources-list">
                {message.sources.map((citation, idx) => (
                  <CitationCard
                    key={`${citation.document_id}-${idx}`}
                    citation={citation}
                    index={idx + 1}
                  />
                ))}
              </div>
            )}
          </div>
        )}

        {/* Feedback buttons (assistant only) */}
        {!isUser && <FeedbackButtons messageId={message.id} />}

        {/* Timestamp */}
        <span className="message-timestamp">
          {new Date(message.created_at).toLocaleTimeString([], {
            hour: '2-digit',
            minute: '2-digit',
          })}
        </span>
      </div>
    </div>
  );
};
