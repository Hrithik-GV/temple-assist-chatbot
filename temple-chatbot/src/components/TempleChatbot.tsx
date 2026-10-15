import React, { useState, useEffect, useRef, useCallback } from 'react';
import {
  TempleChatbotProps,
  ChatMessage as ChatMessageType,
} from '../types/chat';
import { ChatWindow } from './ChatWindow';
import { sendChatMessage } from '../services/chatApi';
import '../styles/temple-chatbot.css';

const DEFAULT_SUGGESTED_QUESTIONS = [
  'What are the temple timings?',
  'What poojas and sevas are available?',
  'What is the history of this temple?',
  'When is the next festival?',
  'Where is the temple located?',
  'What facilities are available for devotees?',
];

export const TempleChatbot: React.FC<TempleChatbotProps> = ({
  apiUrl = 'http://localhost:8000',
  templeId,
  position = 'bottom-right',
  theme = 'warm',
  primaryColor,
  title = 'Temple Assist',
  welcomeMessage = 'Namaste! 🙏 Welcome to Temple Assist. How can I help you today?',
  suggestedQuestions = DEFAULT_SUGGESTED_QUESTIONS,
  className = '',
  onToggle,
}) => {
  const [isOpen, setIsOpen] = useState<boolean>(false);
  const [messages, setMessages] = useState<ChatMessageType[]>([]);
  const [inputValue, setInputValue] = useState<string>('');
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const lastFailedMessageRef = useRef<string | null>(null);

  const abortControllerRef = useRef<AbortController | null>(null);

  const storageKey = `temple_assist_${templeId || 'default'}`;

  // Initialize or restore session from localStorage
  useEffect(() => {
    try {
      const stored = localStorage.getItem(storageKey);
      if (stored) {
        const parsed = JSON.parse(stored);
        if (parsed.conversationId) setConversationId(parsed.conversationId);
        if (parsed.sessionId) setSessionId(parsed.sessionId);
        if (Array.isArray(parsed.messages) && parsed.messages.length > 0) {
          setMessages(parsed.messages);
        }
      } else {
        const newSessionId = `devotee_${Math.random().toString(36).substring(2, 10)}_${Date.now()}`;
        setSessionId(newSessionId);
      }
    } catch {
      // Ignore localStorage access restrictions
    }
  }, [storageKey]);

  // Persist conversation updates
  useEffect(() => {
    if (messages.length > 0 || conversationId) {
      try {
        localStorage.setItem(
          storageKey,
          JSON.stringify({
            conversationId,
            sessionId,
            messages,
          })
        );
      } catch {
        // Ignore quota limits
      }
    }
  }, [messages, conversationId, sessionId, storageKey]);

  // Abort any active request on unmount
  useEffect(() => {
    return () => {
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
      }
    };
  }, []);

  const toggleOpen = useCallback(() => {
    setIsOpen((prev) => {
      const next = !prev;
      if (onToggle) onToggle(next);
      return next;
    });
  }, [onToggle]);

  const handleSendMessage = async (textToSend?: string) => {
    const messageText = (textToSend || inputValue).trim();
    if (!messageText || isLoading) return;

    setErrorMessage(null);
    setInputValue('');
    lastFailedMessageRef.current = null;

    const userMessage: ChatMessageType = {
      id: `usr_${Date.now()}_${Math.random().toString(36).substring(2, 6)}`,
      sender: 'user',
      text: messageText,
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    };

    setMessages((prev) => [...prev, userMessage]);
    setIsLoading(true);

    abortControllerRef.current = new AbortController();

    try {
      const response = await sendChatMessage({
        apiUrl,
        templeId,
        message: messageText,
        conversationId,
        sessionId,
        signal: abortControllerRef.current.signal,
      });

      if (response.conversationId) {
        setConversationId(response.conversationId);
      }

      const assistantMessage: ChatMessageType = {
        id: `asst_${Date.now()}_${Math.random().toString(36).substring(2, 6)}`,
        sender: 'assistant',
        text: response.answer,
        sources: response.sources || [],
        hasContext: response.hasRelevantContext,
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      };

      setMessages((prev) => [...prev, assistantMessage]);
    } catch (err: unknown) {
      const errMsg = err instanceof Error ? err.message : 'An unexpected error occurred. Please try again.';
      if (errMsg !== 'Request was cancelled.') {
        lastFailedMessageRef.current = messageText;
        setErrorMessage(errMsg);
      }
    } finally {
      setIsLoading(false);
      abortControllerRef.current = null;
    }
  };

  const handleClearChat = () => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    setMessages([]);
    setConversationId(null);
    setErrorMessage(null);
    lastFailedMessageRef.current = null;
    try {
      localStorage.removeItem(storageKey);
    } catch {
      // Ignore
    }
  };

  const handleRetry = () => {
    if (lastFailedMessageRef.current) {
      handleSendMessage(lastFailedMessageRef.current);
    }
  };

  const rootStyle = primaryColor ? ({ '--ta-primary': primaryColor } as React.CSSProperties) : undefined;
  const launcherPosClass = position === 'bottom-left' ? 'pos-left' : 'pos-right';

  return (
    <div
      className={`ta-widget-root ${className}`.trim()}
      data-theme={theme}
      style={rootStyle}
    >
      {/* Floating Circular Launcher Button */}
      {!isOpen && (
        <button
          type="button"
          className={`ta-launcher ${launcherPosClass}`}
          onClick={toggleOpen}
          aria-label="Open Temple Assist Guide"
          title="Chat with Temple Assist"
        >
          {/* Temple Diya / Lamp / Sanctum Icon */}
          <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M12 2l2 4h4l-3 4 2 5-5-3-5 3 2-5-3-4h4l2-4z"></path>
            <path d="M5 22h14"></path>
            <path d="M8 18v4"></path>
            <path d="M16 18v4"></path>
          </svg>
          <span className="ta-launcher-badge"></span>
        </button>
      )}

      {/* Responsive Chat Window */}
      {isOpen && (
        <ChatWindow
          title={title}
          subtitle="Your temple guide"
          welcomeMessage={welcomeMessage}
          suggestedQuestions={suggestedQuestions}
          messages={messages}
          inputValue={inputValue}
          isLoading={isLoading}
          errorMessage={errorMessage}
          position={position}
          onInputChange={setInputValue}
          onSendMessage={handleSendMessage}
          onClearChat={handleClearChat}
          onClose={toggleOpen}
          onRetry={lastFailedMessageRef.current ? handleRetry : undefined}
        />
      )}
    </div>
  );
};

export default TempleChatbot;
