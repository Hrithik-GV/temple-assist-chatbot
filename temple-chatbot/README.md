# Temple Assist — React Chatbot Widget (`temple-chatbot`)

A standalone, embeddable React chatbot widget for the **Temple Assist Platform**. Powered by the FastAPI RAG backend, it provides devotees and visitors with immediate, verified answers about temple timings, rituals, sevas, festivals, and history.

---

## 🚀 Features

- **Floating Launcher**: Fixed circular button positioned at `bottom-right` or `bottom-left` with traditional temple diya/sanctum icon and smooth animation.
- **Indian Temple Aesthetic**: Warm visual palette inspired by terracotta, deep saffron, temple brass gold, and sandalwood accents.
- **Real Backend Contract**: Directly connects to FastAPI `/api/chat` with `{ templeId, message, conversationId, sessionId }`.
- **Attribution Citations**: Renders source document and web citations when returned by the RAG backend.
- **Devotee Suggested Inquiries**: Pre-configured common temple queries that populate or submit automatically.
- **Zero Global CSS Leaks**: Fully namespaced under `.ta-widget-root` to prevent conflicts with the host website.
- **Dual Build Output**: Production-ready npm package build with TypeScript definitions alongside a local development playground.
- **Safe & Secure**: Contains no LLM API keys, database credentials, or sensitive backend secrets.

---

## 📦 Installation & Usage

### 1. Install via npm (when published)
```bash
npm install temple-chatbot
```

### 2. Import and Mount in React
```tsx
import React from 'react';
import { TempleChatbot } from 'temple-chatbot';
import 'temple-chatbot/style.css';

export function App() {
  return (
    <div>
      {/* Host application content */}
      <h1>Sri Venkateswara Temple Portal</h1>

      {/* Embedded Standalone Chatbot Widget */}
      <TempleChatbot
        apiUrl="https://api.templeassist.org"
        templeId="temple-001"
        position="bottom-right"
        theme="warm"
        title="Temple Assist"
        welcomeMessage="Namaste! 🙏 Welcome to Sri Venkateswara Temple. How can I assist you with darshan or pooja timings today?"
      />
    </div>
  );
}
```

---

## ⚙️ Component Props

| Prop | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `templeId` | `string` | *(Required)* | Unique identifier for the temple (scoped multi-tenancy). |
| `apiUrl` | `string` | `"http://localhost:8000"` | Base URL of the Temple Assist backend API. |
| `position` | `"bottom-right" \| "bottom-left"` | `"bottom-right"` | Screen corner position for the floating launcher. |
| `theme` | `"warm" \| "maroon" \| "saffron" \| "gold"` | `"warm"` | Visual color theme preset. |
| `primaryColor` | `string` | `undefined` | Custom hex/rgb accent color override. |
| `language` | `string` | `"en"` | Display and response language. |
| `title` | `string` | `"Temple Assist"` | Header title. |
| `welcomeMessage`| `string` | `"Namaste! 🙏 Welcome to Temple Assist..."` | Initial welcome greeting. |
| `suggestedQuestions` | `string[]` | Default questions | Array of suggested inquiry prompt chips. |
| `className` | `string` | `""` | Optional custom CSS class for the root wrapper. |
| `onToggle` | `(isOpen: boolean) => void` | `undefined` | Callback fired when the chat window opens or closes. |

---

## 🛠️ Development & Testing

### Run Development Server
```bash
cd temple-chatbot
npm install
npm run dev
```
Open [http://localhost:5173](http://localhost:5173) to interact with the verification playground.

### Build Production Library
```bash
npm run build:lib
```
Generates the distributable bundles in `dist/`:
- `dist/temple-chatbot.es.js` (ES Module)
- `dist/temple-chatbot.umd.js` (UMD)
- `dist/temple-chatbot.css` (Namespaced styles)
- `dist/src/index.d.ts` (TypeScript declarations)

---

## 📋 Backend API Contract

The widget interacts with the FastAPI backend endpoint:

- **Endpoint**: `POST /api/chat`
- **Request Headers**: `Content-Type: application/json`
- **Request Payload**:
  ```json
  {
    "templeId": "temple-001",
    "message": "What are the morning pooja timings?",
    "conversationId": "optional-uuid-for-session",
    "sessionId": "optional-device-id"
  }
  ```
- **Response Payload**:
  ```json
  {
    "answer": "Suprabhata Seva starts at 5:00 AM followed by Thomala Seva...",
    "sources": [
      {
        "title": "Daily Pooja Schedule 2026",
        "url": "https://temple.org/timings",
        "snippet": "Morning pooja schedule and darshan slots..."
      }
    ],
    "templeId": "temple-001",
    "conversationId": "active-conversation-id",
    "hasRelevantContext": true
  }
  ```
