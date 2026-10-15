import React from 'react';
import { ChatMessage as ChatMessageType } from '../types/chat';

interface ChatMessageProps {
  message: ChatMessageType;
}

export const ChatMessage: React.FC<ChatMessageProps> = ({ message }) => {
  const isUser = message.sender === 'user';

  return (
    <div className={`ta-msg-row ${message.sender}`}>
      <div className="ta-msg-bubble">
        {message.text}

        {/* Citations from temple records if provided by assistant */}
        {!isUser && message.sources && message.sources.length > 0 && (
          <div className="ta-sources">
            <div className="ta-sources-title">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"></path>
                <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"></path>
              </svg>
              Temple Records & Citations ({message.sources.length})
            </div>
            {message.sources.map((src, idx) => (
              <div key={idx} className="ta-source-card">
                <div className="ta-source-name">
                  <span>{src.title || 'Verified Temple Record'}</span>
                  {src.url && (
                    <a
                      href={src.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="ta-source-url"
                    >
                      Visit ↗
                    </a>
                  )}
                </div>
                {src.snippet && <div className="ta-source-snippet">{src.snippet}</div>}
              </div>
            ))}
          </div>
        )}
      </div>

      {message.timestamp && <div className="ta-msg-time">{message.timestamp}</div>}
    </div>
  );
};

export default ChatMessage;
