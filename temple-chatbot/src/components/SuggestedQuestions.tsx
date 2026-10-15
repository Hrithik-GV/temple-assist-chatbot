import React from 'react';

interface SuggestedQuestionsProps {
  questions: string[];
  onSelectQuestion: (question: string) => void;
  disabled?: boolean;
}

export const SuggestedQuestions: React.FC<SuggestedQuestionsProps> = ({
  questions,
  onSelectQuestion,
  disabled = false,
}) => {
  if (!questions || questions.length === 0) {
    return null;
  }

  return (
    <div className="ta-suggested-section">
      <div className="ta-suggested-label">Devotee Inquiries</div>
      <div className="ta-suggested-list">
        {questions.map((q, idx) => (
          <button
            key={idx}
            type="button"
            className="ta-suggested-btn"
            onClick={() => onSelectQuestion(q)}
            disabled={disabled}
            aria-label={`Ask: ${q}`}
          >
            <span>{q}</span>
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <polyline points="9 18 15 12 9 6"></polyline>
            </svg>
          </button>
        ))}
      </div>
    </div>
  );
};

export default SuggestedQuestions;
