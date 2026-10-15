/**
 * Type definitions for Temple Assist Chatbot API and component props
 */

export interface ChatSource {
  title: string;
  source?: string | null;
  url?: string | null;
  snippet?: string | null;
  score?: number | null;
}

export interface ChatRequestPayload {
  templeId: string;
  message: string;
  conversationId?: string | null;
  sessionId?: string | null;
}

export interface ChatResponsePayload {
  answer: string;
  sources: ChatSource[];
  templeId: string;
  conversationId: string;
  sessionId?: string | null;
  hasRelevantContext: boolean;
}

export interface ChatMessage {
  id: string;
  sender: 'user' | 'assistant';
  text: string;
  sources?: ChatSource[];
  hasContext?: boolean;
  timestamp?: string;
  isError?: boolean;
}

export type WidgetPosition = 'bottom-right' | 'bottom-left';

export type WidgetTheme = 'warm' | 'maroon' | 'saffron' | 'gold' | 'custom';

export interface TempleChatbotProps {
  /** Base URL of the Temple Chatbot backend API (e.g. "http://localhost:8000") */
  apiUrl?: string;
  /** Unique identifier for the temple (required, e.g. "temple-001") */
  templeId: string;
  /** Position of the floating launcher button on the screen */
  position?: WidgetPosition;
  /** Theme palette preset */
  theme?: WidgetTheme;
  /** Primary accent color override (e.g. "#b45309" or "#854d0e") */
  primaryColor?: string;
  /** Response or interface display language */
  language?: string;
  /** Custom welcome message heading */
  title?: string;
  /** Custom welcome greeting message */
  welcomeMessage?: string;
  /** Custom suggested questions */
  suggestedQuestions?: string[];
  /** Optional custom class name for root container */
  className?: string;
  /** Optional callback fired when widget opens or closes */
  onToggle?: (isOpen: boolean) => void;
}
