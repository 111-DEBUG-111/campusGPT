import React, { useState } from 'react';
import { ThumbsUp, ThumbsDown } from 'lucide-react';
import { useChatStore } from '../../stores/chatStore';

interface FeedbackButtonsProps {
  messageId: number;
}

export const FeedbackButtons: React.FC<FeedbackButtonsProps> = ({ messageId }) => {
  const [submitted, setSubmitted] = useState<'helpful' | 'not_helpful' | null>(null);
  const submitFeedback = useChatStore((s) => s.submitFeedback);

  const handleFeedback = async (rating: 'helpful' | 'not_helpful') => {
    if (submitted) return;
    try {
      await submitFeedback(messageId, rating);
      setSubmitted(rating);
    } catch (error) {
      console.error('Feedback submission failed:', error);
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
