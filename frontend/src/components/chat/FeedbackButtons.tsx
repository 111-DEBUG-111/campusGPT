import React, { useState } from 'react';
import { ThumbsUp, ThumbsDown } from 'lucide-react';
import { useChatStore } from '../../stores/chatStore';
import type { Message } from '../../types';

interface FeedbackButtonsProps {
  message: Message;
}

export const FeedbackButtons: React.FC<FeedbackButtonsProps> = ({ message }) => {
  const [submitted, setSubmitted] = useState<'helpful' | 'not_helpful' | null>(
    message.feedback_given ? (message.feedback_type as 'helpful' | 'not_helpful' || null) : null
  );
  const submitFeedback = useChatStore((s) => s.submitFeedback);

  const handleFeedback = async (rating: 'helpful' | 'not_helpful') => {
    if (submitted) return;
    setSubmitted(rating);
    try {
      await submitFeedback(message.id, rating);
    } catch (error) {
      console.error('Feedback submission failed:', error);
      setSubmitted(null); // Rollback on failure
    }
  };

  if (submitted) {
    return (
      <div className="feedback-submitted">
        {submitted === 'helpful' ? (
          <span className="feedback-thanks feedback-helpful">
            <ThumbsUp size={12} /> Thanks for your feedback!
          </span>
        ) : (
          <span className="feedback-thanks feedback-not-helpful">
            <ThumbsDown size={12} /> We'll work on improving this.
          </span>
        )}
      </div>
    );
  }

  return (
    <div className="feedback-buttons">
      <span className="feedback-label">Was this helpful?</span>
      <button
        className="feedback-btn feedback-btn-helpful"
        onClick={() => handleFeedback('helpful')}
        title="Helpful"
        aria-label="Mark as helpful"
      >
        <ThumbsUp size={14} />
      </button>
      <button
        className="feedback-btn feedback-btn-not-helpful"
        onClick={() => handleFeedback('not_helpful')}
        title="Not Helpful"
        aria-label="Mark as not helpful"
      >
        <ThumbsDown size={14} />
      </button>
    </div>
  );
};
