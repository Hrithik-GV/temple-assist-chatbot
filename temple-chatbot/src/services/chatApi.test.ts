import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { sendChatMessage } from './chatApi';

describe('sendChatMessage API Client', () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  it('sends the correct templeId and payload to /api/chat', async () => {
    const mockResponsePayload = {
      answer: 'The temple opens daily at 6:00 AM.',
      sources: [
        {
          title: 'Daily Darshan Timings',
          source: 'timings.pdf',
          url: 'https://temple.org/timings',
          snippet: 'Temple opens at 6:00 AM.',
          score: 0.92,
        },
      ],
      templeId: 'temple-001',
      conversationId: 'conv_12345',
      sessionId: 'sess_67890',
      hasRelevantContext: true,
    };

    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      headers: new Headers({ 'content-type': 'application/json' }),
      json: async () => mockResponsePayload,
    });
    globalThis.fetch = fetchMock as any;

    const result = await sendChatMessage({
      apiUrl: 'http://localhost:8000/',
      templeId: 'temple-001',
      message: 'What time does the temple open?',
      conversationId: 'conv_12345',
      sessionId: 'sess_67890',
    });

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, options] = fetchMock.mock.calls[0];

    expect(url).toBe('http://localhost:8000/api/chat');
    expect(options.method).toBe('POST');
    expect(options.headers).toEqual({
      'Content-Type': 'application/json',
      Accept: 'application/json',
    });

    const parsedBody = JSON.parse(options.body);
    expect(parsedBody.templeId).toBe('temple-001');
    expect(parsedBody.message).toBe('What time does the temple open?');
    expect(parsedBody.conversationId).toBe('conv_12345');
    expect(parsedBody.sessionId).toBe('sess_67890');

    expect(result.answer).toBe('The temple opens daily at 6:00 AM.');
    expect(result.templeId).toBe('temple-001');
    expect(result.hasRelevantContext).toBe(true);
    expect(result.sources).toHaveLength(1);
    expect(result.sources[0].title).toBe('Daily Darshan Timings');
  });

  it('rejects empty messages before network call', async () => {
    const fetchMock = vi.fn();
    globalThis.fetch = fetchMock as any;

    await expect(
      sendChatMessage({
        templeId: 'temple-001',
        message: '   ',
      })
    ).rejects.toThrow('Message cannot be empty.');

    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('rejects empty templeId before network call', async () => {
    const fetchMock = vi.fn();
    globalThis.fetch = fetchMock as any;

    await expect(
      sendChatMessage({
        templeId: '   ',
        message: 'Hello',
      })
    ).rejects.toThrow('templeId is required.');

    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('handles backend error responses gracefully', async () => {
    const errorPayload = {
      success: false,
      error: {
        code: 'BAD_REQUEST',
        message: 'This temple chatbot is currently inactive.',
      },
    };

    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 400,
      statusText: 'Bad Request',
      headers: new Headers({ 'content-type': 'application/json' }),
      json: async () => errorPayload,
    }) as any;

    await expect(
      sendChatMessage({
        templeId: 'temple-inactive',
        message: 'When is aarti?',
      })
    ).rejects.toThrow('This temple chatbot is currently inactive.');
  });

  it('handles request cancellation via AbortSignal', async () => {
    const controller = new AbortController();
    controller.abort();

    await expect(
      sendChatMessage({
        templeId: 'temple-001',
        message: 'Cancelled message',
        signal: controller.signal,
      })
    ).rejects.toThrow('Request was cancelled.');
  });

  it('handles timeout correctly', async () => {
    // Simulate a hung fetch that never resolves
    globalThis.fetch = vi.fn().mockImplementation((_url, opts) => {
      return new Promise((_resolve, reject) => {
        opts.signal?.addEventListener('abort', () => {
          reject(new DOMException('The operation was aborted.', 'AbortError'));
        });
      });
    }) as any;

    await expect(
      sendChatMessage({
        templeId: 'temple-001',
        message: 'Timing query',
        timeoutMs: 50, // Fast 50ms timeout for test
      })
    ).rejects.toThrow(/Request timed out/);
  });
});
