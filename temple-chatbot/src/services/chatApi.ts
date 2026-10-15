import { ChatRequestPayload, ChatResponsePayload } from '../types/chat';

export interface SendMessageOptions {
  apiUrl?: string;
  templeId: string;
  message: string;
  conversationId?: string | null;
  sessionId?: string | null;
  signal?: AbortSignal;
  timeoutMs?: number;
}

/**
 * Sends a devotee/visitor message to the FastAPI /api/chat endpoint.
 */
export async function sendChatMessage({
  apiUrl = 'http://localhost:8000',
  templeId,
  message,
  conversationId = null,
  sessionId = null,
  signal,
  timeoutMs = 30000,
}: SendMessageOptions): Promise<ChatResponsePayload> {
  const cleanMessage = (message || '').trim();
  if (!cleanMessage) {
    throw new Error('Message cannot be empty.');
  }

  const cleanTempleId = (templeId || '').trim();
  if (!cleanTempleId) {
    throw new Error('templeId is required.');
  }

  // Strip trailing slashes from API URL
  const baseUrl = apiUrl.replace(/\/+$/, '');
  const endpoint = `${baseUrl}/api/chat`;

  const payload: ChatRequestPayload = {
    templeId: cleanTempleId,
    message: cleanMessage,
    conversationId: conversationId || null,
    sessionId: sessionId || null,
  };

  // Internal abort controller combining caller signal + timeout
  const internalController = new AbortController();
  let isTimedOut = false;

  const timeoutTimer = setTimeout(() => {
    isTimedOut = true;
    internalController.abort();
  }, timeoutMs);

  const onCallerAbort = () => {
    internalController.abort();
  };

  if (signal) {
    if (signal.aborted) {
      clearTimeout(timeoutTimer);
      internalController.abort();
    } else {
      signal.addEventListener('abort', onCallerAbort, { once: true });
    }
  }

  let response: Response;
  try {
    response = await fetch(endpoint, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Accept: 'application/json',
      },
      body: JSON.stringify(payload),
      signal: internalController.signal,
    });
  } catch (err: unknown) {
    if (isTimedOut) {
      throw new Error(`Request timed out after ${Math.round(timeoutMs / 1000)} seconds. Please try again.`);
    }
    if (signal?.aborted || (err instanceof DOMException && err.name === 'AbortError')) {
      throw new Error('Request was cancelled.');
    }
    throw new Error('Unable to connect to Temple Assist. Please verify the backend service is running.');
  } finally {
    clearTimeout(timeoutTimer);
    if (signal) {
      signal.removeEventListener('abort', onCallerAbort);
    }
  }

  const contentType = response.headers.get('content-type') || '';
  let data: any = null;

  if (contentType.includes('application/json')) {
    try {
      data = await response.json();
    } catch {
      data = null;
    }
  }

  if (!response.ok) {
    // Extract standardized backend error envelope
    let detailMsg = '';
    if (Array.isArray(data?.error?.details) && data.error.details.length > 0) {
      detailMsg = data.error.details
        .map((d: any) => d.msg || (typeof d === 'string' ? d : JSON.stringify(d)))
        .join(', ');
    }

    const baseMsg = data?.error?.message || data?.detail || (typeof data?.error === 'string' ? data.error : null);
    const errorMsg =
      detailMsg && baseMsg
        ? `${baseMsg}: ${detailMsg}`
        : detailMsg || baseMsg || `Server error: ${response.status} (${response.statusText})`;

    throw new Error(errorMsg);
  }

  if (!data || typeof data.answer !== 'string') {
    throw new Error('Invalid response structure received from Temple Assist server.');
  }

  return {
    answer: data.answer,
    sources: Array.isArray(data.sources) ? data.sources : [],
    templeId: data.templeId || cleanTempleId,
    conversationId: data.conversationId || '',
    sessionId: data.sessionId || null,
    hasRelevantContext: Boolean(data.hasRelevantContext),
  };
}
