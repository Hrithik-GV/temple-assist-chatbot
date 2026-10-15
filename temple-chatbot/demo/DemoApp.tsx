import { useState } from 'react';
import { TempleChatbot } from '../src/index';

export function DemoApp() {
  const [templeId, setTempleId] = useState<string>(
    (import.meta as any).env?.VITE_TEMPLE_ID || 'temple-001'
  );
  const [apiUrl, setApiUrl] = useState<string>(
    (import.meta as any).env?.VITE_CHAT_API_URL || 'http://localhost:8000'
  );
  const [theme, setTheme] = useState<'warm' | 'maroon' | 'saffron' | 'gold'>('warm');
  const [position, setPosition] = useState<'bottom-right' | 'bottom-left'>('bottom-right');

  return (
    <div style={{
      minHeight: '100vh',
      fontFamily: 'system-ui, -apple-system, sans-serif',
      backgroundColor: '#fafaf9',
      color: '#292524',
      padding: '40px 24px',
      boxSizing: 'border-box',
    }}>
      <div style={{
        maxWidth: '780px',
        margin: '0 auto',
        backgroundColor: '#ffffff',
        border: '1px solid #e7e5e4',
        borderRadius: '16px',
        padding: '32px',
        boxShadow: '0 4px 12px rgba(0,0,0,0.05)',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '8px' }}>
          <span style={{ fontSize: '28px' }}>🛕</span>
          <h1 style={{ margin: 0, fontSize: '24px', color: '#78350f' }}>
            Temple Assist — Widget Verification Playground
          </h1>
        </div>
        <p style={{ color: '#78716c', fontSize: '14px', lineHeight: 1.6, marginTop: '4px' }}>
          This playground is used strictly to test and verify the standalone <code>&lt;TempleChatbot /&gt;</code> widget.
          Adjust the props below to verify reactive configuration, then click the floating launcher in the bottom corner to test real RAG dialogues.
        </p>

        <div style={{
          marginTop: '24px',
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
          gap: '16px',
          backgroundColor: '#fffbeb',
          border: '1px solid #fef3c7',
          borderRadius: '12px',
          padding: '20px',
        }}>
          <div>
            <label style={{ display: 'block', fontSize: '12px', fontWeight: 700, color: '#92400e', marginBottom: '6px' }}>
              templeId
            </label>
            <input
              type="text"
              value={templeId}
              onChange={(e) => setTempleId(e.target.value)}
              style={{
                width: '100%',
                padding: '8px 12px',
                borderRadius: '6px',
                border: '1px solid #d6d3d1',
                boxSizing: 'border-box',
                fontFamily: 'inherit',
                fontSize: '13px',
              }}
            />
          </div>

          <div>
            <label style={{ display: 'block', fontSize: '12px', fontWeight: 700, color: '#92400e', marginBottom: '6px' }}>
              apiUrl
            </label>
            <input
              type="text"
              value={apiUrl}
              onChange={(e) => setApiUrl(e.target.value)}
              style={{
                width: '100%',
                padding: '8px 12px',
                borderRadius: '6px',
                border: '1px solid #d6d3d1',
                boxSizing: 'border-box',
                fontFamily: 'inherit',
                fontSize: '13px',
              }}
            />
          </div>

          <div>
            <label style={{ display: 'block', fontSize: '12px', fontWeight: 700, color: '#92400e', marginBottom: '6px' }}>
              theme
            </label>
            <select
              value={theme}
              onChange={(e) => setTheme(e.target.value as any)}
              style={{
                width: '100%',
                padding: '8px 12px',
                borderRadius: '6px',
                border: '1px solid #d6d3d1',
                boxSizing: 'border-box',
                fontFamily: 'inherit',
                fontSize: '13px',
                backgroundColor: '#ffffff',
              }}
            >
              <option value="warm">Warm Terracotta (Default)</option>
              <option value="maroon">Deep Maroon</option>
              <option value="saffron">Vibrant Saffron</option>
              <option value="gold">Temple Brass Gold</option>
            </select>
          </div>

          <div>
            <label style={{ display: 'block', fontSize: '12px', fontWeight: 700, color: '#92400e', marginBottom: '6px' }}>
              position
            </label>
            <select
              value={position}
              onChange={(e) => setPosition(e.target.value as any)}
              style={{
                width: '100%',
                padding: '8px 12px',
                borderRadius: '6px',
                border: '1px solid #d6d3d1',
                boxSizing: 'border-box',
                fontFamily: 'inherit',
                fontSize: '13px',
                backgroundColor: '#ffffff',
              }}
            >
              <option value="bottom-right">Bottom Right</option>
              <option value="bottom-left">Bottom Left</option>
            </select>
          </div>
        </div>

        <div style={{
          marginTop: '20px',
          fontSize: '12px',
          color: '#78716c',
          lineHeight: 1.5,
          borderLeft: '3px solid #b45309',
          paddingLeft: '12px',
        }}>
          Currently targeting: <code>{apiUrl}/api/chat</code> for temple <code>{templeId}</code>.
        </div>
      </div>

      {/* Floating Standalone Chatbot Widget */}
      <TempleChatbot
        apiUrl={apiUrl}
        templeId={templeId}
        position={position}
        theme={theme}
      />
    </div>
  );
}

export default DemoApp;
