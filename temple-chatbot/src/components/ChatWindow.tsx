import React, { useRef, useEffect } from 'react';
import { ChatMessage as ChatMessageType, WidgetPosition } from '../types/chat';
import { ChatMessage } from './ChatMessage';
import { SuggestedQuestions } from './SuggestedQuestions';
import { ChatInput } from './ChatInput';

interface ChatWindowProps {
  title: string;
  subtitle: string;
  welcomeMessage: string;
  suggestedQuestions: string[];
  messages: ChatMessageType[];
  inputValue: string;
  isLoading: boolean;
  errorMessage: string | null;
  position: WidgetPosition;
  onInputChange: (val: string) => void;
  onSendMessage: (text?: string) => void;
  onClearChat: () => void;
  onClose: () => void;
  onRetry?: () => void;
}

export const ChatWindow: React.FC<ChatWindowProps> = ({
  title,
  subtitle,
  welcomeMessage,
  suggestedQuestions,
  messages,
  inputValue,
  isLoading,
  errorMessage,
  position,
  onInputChange,
  onSendMessage,
  onClearChat,
  onClose,
  onRetry,
}) => {
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isLoading, errorMessage]);

  const posClass = position === 'bottom-left' ? 'pos-left' : 'pos-right';

  return (
    <div
      className={`ta-window ${posClass}`}
      role="dialog"
      aria-modal="true"
      aria-label={title}
    >
      {/* Header */}
      <div className="ta-header">
        <div className="ta-header-left">
          <div className="ta-header-icon">
            {/* Kalasha / Temple Sanctum Icon */}
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M12 2l2 4h4l-3 4 2 5-5-3-5 3 2-5-3-4h4l2-4z"></path>
              <path d="M5 22h14"></path>
              <path d="M8 18v4"></path>
              <path d="M16 18v4"></path>
            </svg>
          </div>
          <div className="ta-header-titles">
            <span className="ta-title">{title}</span>
            <span className="ta-subtitle">
              <span className="ta-status-dot"></span>
              {subtitle}
            </span>
          </div>
        </div>

        <div className="ta-header-actions">
          {/* Clear conversation button */}
          <button
            type="button"
            className="ta-action-btn"
            onClick={onClearChat}
            title="Clear dialogue"
            aria-label="Clear dialogue"
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M3 6h18"></path>
              <path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6"></path>
              <path d="M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2"></path>
            </svg>
          </button>

          {/* Close button */}
          <button
            type="button"
            className="ta-action-btn"
            onClick={onClose}
            title="Close Temple Guide"
            aria-label="Close Temple Guide"
          >
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <line x1="18" y1="6" x2="6" y2="18"></line>
              <line x1="6" y1="6" x2="18" y2="18"></line>
            </svg>
          </button>
        </div>
      </div>

      {/* Messages Scroll Area */}
      <div className="ta-messages">
        {/* Welcome Card & Initial Suggested Questions */}
        {messages.length === 0 && (
          <div className="ta-welcome-card">
            <div className="ta-welcome-badge">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <circle cx="12" cy="12" r="10"></circle>
                <path d="M12 16v-4"></path>
                <path d="M12 8h.01"></path>
              </svg>
              Temple Guide
            </div>
            <div className="ta-welcome-text">{welcomeMessage}</div>

            <SuggestedQuestions
              questions={suggestedQuestions}
              onSelectQuestion={(q) => onSendMessage(q)}
              disabled={isLoading}
            />
          </div>
        )}

        {/* Dialogue Stream */}
        {messages.map((msg) => (
          <ChatMessage key={msg.id} message={msg} />
        ))}

        {/* Loading Indicator */}
        {isLoading && (
          <div className="ta-msg-row assistant">
            <div className="ta-typing" aria-label="Seeking temple records...">
              <span className="ta-typing-dot"></span>
              <span className="ta-typing-dot"></span>
              <span className="ta-typing-dot"></span>
            </div>
          </div>
        )}

        {/* Error Alert with Optional Retry */}
        {errorMessage && (
          <div className="ta-error-alert" role="alert">
            <span>{errorMessage}</span>
            {onRetry && (
              <button type="button" className="ta-retry-btn" onClick={onRetry}>
                Retry
              </button>
            )}
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Footer / Input */}
      <div className="ta-footer">
        <ChatInput
          value={inputValue}
          onChange={onInputChange}
          onSend={() => onSendMessage()}
          isLoading={isLoading}
        />
        <div className="ta-branding">
          <span>Temple Assist AI • Verified Knowledge</span>
        </div>
      </div>
    </div>
  );
};

export default ChatWindow;
