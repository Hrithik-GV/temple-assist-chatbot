# Temple Chatbot Platform - Backend

Backend API foundation for the Temple Chatbot Platform built with **Python 3.13+**, **FastAPI**, **MongoDB Atlas**, **MongoDB Atlas Vector Search**, and a **Document Ingestion Pipeline** supporting PDF, DOCX, and TXT documents.

This repository contains the production-ready backend architecture designed for multi-tenancy across multiple temples, scalable database integration, document ingestion, and high-performance vector search retrieval for the RAG pipeline.

---

## Architecture & Directory Structure

The backend follows a clean, decoupled modular layout separating routing, business logic, domain models, database management, ingestion, embeddings, and utilities:

```text
temple-assist-chatbot/
├── .env.example              # Environment variables template (includes MongoDB, Vector Search, Ingestion)
├── .env                      # Local environment configuration (git-ignored)
├── .gitignore                # Git ignore configuration
├── pyproject.toml            # Project metadata and pytest configuration
├── requirements.txt          # Python dependencies (FastAPI, Motor, FastEmbed, PyPDF, python-docx, etc.)
├── README.md                 # Project documentation
├── app/
│   ├── __init__.py           # Application package root
│   ├── main.py               # FastAPI application factory, lifespan & entrypoint
│   ├── api/                  # API layer (routers & endpoints)
│   │   ├── __init__.py
│   │   ├── endpoints/
│   │   │   ├── __init__.py
│   │   │   └── chat.py       # Public Chatbot API (POST /api/chat)
│   │   └── v1/
│   │       ├── __init__.py
│   │       ├── router.py     # Aggregated v1 API router
│   │       └── endpoints/
│   │           ├── __init__.py
│   │           ├── health.py # Health, liveness, and readiness endpoints
│   │           └── rag.py    # RAG question-answering query endpoint
│   ├── core/                 # Core system configurations & foundations
│   │   ├── __init__.py
│   │   ├── config.py         # Pydantic Settings management (.env loader)
│   │   ├── database.py       # MongoDB Atlas connection manager & index initialization
│   │   ├── errors.py         # Exception hierarchy & centralized error handlers
│   │   ├── logging.py        # Centralized formatted logging foundation
│   │   └── rate_limiter.py   # Rate limiting engine (sliding window / IP-based)
│   ├── models/               # Multi-Temple domain models and Pydantic schemas
│   │   ├── __init__.py
│   │   ├── base.py           # MongoBaseModel with ObjectId and camelCase serialization
│   │   ├── collections.py    # Canonical MongoDB collection names
│   │   ├── common.py         # Generic response & error schemas
│   │   ├── health.py         # Health check schemas & component models
│   │   ├── temple.py         # Temple profile, timings, location, and contact models
│   │   ├── knowledge.py      # KnowledgeDocument, KnowledgeChunk, VectorSearchResult, IngestionResult
│   │   ├── rag.py            # RAGQueryRequest, RAGAnswerResponse, RAGSourceCitation, LLMResponse
│   │   ├── chat.py           # ChatRequest, ChatResponse, ChatSource (public widget schemas)
│   │   ├── admin.py          # Admin model with role-based and temple scoping
│   │   ├── conversation.py   # Multi-turn chat session model (templeId-scoped)
│   │   └── message.py        # Dialogue message history model (templeId-scoped)
│   ├── services/             # Business logic service layer
│   │   ├── __init__.py
│   │   ├── base.py           # Abstract base service class
│   │   ├── crawler_service.py    # Playwright website crawler & content extractor
│   │   ├── database_service.py   # Reusable multi-temple repository service
│   │   ├── embedding_service.py  # Swappable embedding provider (FastEmbed, Mock, etc.)
│   │   ├── health_service.py     # Health inspection & MongoDB diagnostic service
│   │   ├── ingestion_service.py  # Document ingestion pipeline (PDF, DOCX, TXT)
│   │   ├── llm_service.py        # Swappable LLM completion provider (Gemini, OpenAI, Mock)
│   │   ├── rag_service.py        # Dedicated RAG orchestration & grounded QA pipeline
│   │   └── vector_search_service.py # Isolated MongoDB Atlas Vector Search service
│   └── utils/                # Utility helpers & shared functions
│       ├── __init__.py
│       ├── helpers.py        # Date/time helpers and utilities
│       ├── html_cleaner.py   # Rendered HTML noise stripping & link extractor
│       ├── text_cleaner.py   # Text normalization and formatting noise cleaner
│       ├── text_chunker.py   # Boundary-aware semantic chunker with token counter
│       ├── text_extractor.py # Document parsers for PDF, DOCX, and TXT
│       └── url_utils.py      # URL normalization, domain validation & link filters
└── tests/                    # Automated test suite
    ├── __init__.py
    ├── conftest.py           # Pytest fixtures and TestClient
    ├── test_chat.py          # Public chatbot API, rate limit, CORS, and validation tests
    ├── test_crawler.py       # URL filtering, HTML cleaning, and crawler tests
    ├── test_database.py      # MongoDB models, manager, and multi-tenancy tests
    ├── test_health.py        # Health, probe, and database readiness tests
    ├── test_ingestion.py     # Document extraction, cleaning, chunking, and ingestion tests
    ├── test_rag.py           # RAG retrieval, context, anti-hallucination, prompts & LLM tests
    └── test_vector_search.py # Embedding generation, chunk schema, and vector search tests
```

---

## Document Ingestion Pipeline

The ingestion service converts temple knowledge documents (PDF, DOCX, TXT) into searchable, embedded vector chunks in MongoDB:

```text
Document (PDF / DOCX / TXT)
  ├── 1. Text Extraction      (Extract text, table cells, pages via pypdf / python-docx)
  ├── 2. Text Cleaning        (NFKC Unicode normalize, strip control chars & formatting noise)
  ├── 3. Deduplication        (Compute SHA-256 fingerprint; skip if unchanged)
  ├── 4. Document Record      (Persist KnowledgeDocument record in MongoDB)
  ├── 5. Semantic Chunking    (Configurable chunk_size & overlap along natural boundaries)
  ├── 6. Dense Embeddings     (Generate 384-dim embeddings via FastEmbed)
  └── 7. Vector Storage       (Persist KnowledgeChunk records into knowledge_chunks)
```

### Supported Document Types

| Format | Extension | Parser | Features Supported |
| :--- | :--- | :--- | :--- |
| **PDF** | `.pdf` | `pypdf` | Multi-page text extraction, whitespace preservation, encryption detection |
| **DOCX** | `.docx`, `.doc` | `python-docx` | Headings, body paragraphs, and table cell extraction |
| **TXT** | `.txt`, `.md`, `.text` | Built-in | Automatic encoding detection (`utf-8`, `utf-16`, `latin-1`, `cp1252`) |

### Ingestion Usage Examples

#### 1. Ingesting a Document File (PDF / DOCX / TXT)

```python
from pathlib import Path
from app.services.ingestion_service import ingestion_service

result = await ingestion_service.ingest_file(
    file_path=Path("docs/tirumala_darshan_guidelines.pdf"),
    temple_id="temple_tirupati",
    title="Tirumala Darshan Guidelines",
    category="darshan",
    metadata={"uploadedBy": "admin_1", "official": True},
)

print(f"Document ID: {result.document_id}")
print(f"Chunks Indexed: {result.chunks_created}")
print(f"Status: {result.status}")  # DocumentStatus.PROCESSED
print(f"Content Hash: {result.content_hash}")
```

#### 2. Ingesting Raw Text (FAQs, Manual Guidelines)

```python
from app.services.ingestion_service import ingestion_service

faq_text = """
Q: What are the temple morning darshan hours?
A: General darshan is open from 6:00 AM to 12:30 PM.

Q: Is mobile phone allowed inside the sanctum?
A: No, electronic devices must be deposited at the cloak room.
"""

result = await ingestion_service.ingest_text(
    text=faq_text,
    temple_id="temple_tirupati",
    title="General Darshan FAQs",
    category="faq",
    source="manual_faq_entry",
)
```

#### 3. Ingesting Raw File Bytes (e.g. from File Uploads)

```python
from app.services.ingestion_service import ingestion_service
from app.models.knowledge import DocumentSourceType

result = await ingestion_service.ingest_document(
    temple_id="temple_madurai",
    source=file_bytes,
    title="Meenakshi Temple Architecture",
    source_type=DocumentSourceType.DOCX,
    filename="meenakshi_architecture.docx",
    category="history",
    chunk_size=500,
    chunk_overlap=50,
    force_reingest=False,  # Set True to overwrite existing duplicate
)
```

### Deduplication & Idempotency

- Every document computes a SHA-256 hash of its normalized text.
- If a document with identical `templeId` and `contentHash` already exists:
  - When `force_reingest=False`: skips ingestion and returns `is_duplicate=True` with existing document metadata, saving computation and vector storage costs.
  - When `force_reingest=True`: cleans up previous chunks and safely re-indexes.

### Failure Handling & Rollback

- If any step fails during ingestion (e.g., embedding model failure or database disconnection):
  1. Any partial/orphaned chunks stored for this document are automatically purged.
  2. The parent `KnowledgeDocument` status is set to `FAILED` with error details captured in `metadata["error"]`.
  3. A descriptive `AppException` is raised to inform the caller.

---

## Website Ingestion Engine (Playwright Crawler)

Temple websites often use modern JavaScript frameworks (React, Vue, Next.js). The platform includes an automated web crawler built on **Playwright** and **BeautifulSoup** to extract client-side rendered textual knowledge without copying raw code or CSS:

```text
Starting URL (https://temple.org)
  ├── 1. Playwright Browser Engine   (Executes JavaScript / renders React applications)
  ├── 2. Noise & Boilerplate Removal (Strips nav, headers, footers, scripts, styles, cookie notices)
  ├── 3. Internal Link Discovery     (Extracts & validates in-domain links, avoids loops)
  ├── 4. Text Normalization          (Cleans text and extracts page title)
  └── 5. RAG Pipeline Ingestion      (Deduplication → Chunking → FastEmbed → MongoDB)
```

### Key Features
* **JavaScript / React Rendering**: Headless Chromium executes client-side scripts to extract visible content after dynamic hydration.
* **Deep Content Cleaning**: Automatically strips boilerplate:
  - Navigation menus (`<nav>`, `.navbar`, `[role="navigation"]`)
  - Headers & footers (`<header>`, `<footer>`, repetitive copyright notices)
  - Scripts, styles, `<noscript>`, SVG icons, and forms
  - Cookie consent banners, GDPR notices, and modal overlays
* **Domain Guardrails**:
  - Restricts crawling strictly to the same domain (rejects external domains and social links).
  - Skips media, binary assets, and PDFs (`.png`, `.jpg`, `.pdf`, `.mp4`, `.css`, etc.).
  - Normalizes URLs (strips `#anchors`, drops `utm_*` marketing tags, unifies trailing slashes).
  - Prevents infinite loops using visited/enqueued URL sets.
* **Resilience & Timeout Handling**: Broken pages, 404s, or slow pages are logged and handled gracefully without halting the remaining crawl.
* **Integrated with RAG Storage**: Extracted content directly feeds into the `IngestionService` and is tagged with the target `templeId`.

### Prerequisites for Web Crawling
Playwright requires the Chromium browser binary:
```bash
playwright install chromium
```

### Crawling Usage Example

```python
import asyncio
from app.services.crawler_service import crawler_service

async def main():
    # Crawl a temple website and ingest its pages
    summary = await crawler_service.crawl_temple_website(
        temple_id="temple_somnath",
        start_url="https://somnath.org",
        max_pages=15,             # Maximum pages to visit (default: from settings)
        max_depth=3,              # Max link hop depth from entry page
        timeout_ms=30000,         # Per-page timeout in ms
        category="website",       # Domain category tag
        force_reingest=False,     # Skip unchanged pages via content hash
    )

    print(f"Crawl finished in {summary.duration_seconds}s:")
    print(f"  Pages visited: {summary.total_pages_visited}")
    print(f"  Pages ingested: {summary.pages_ingested}")
    print(f"  Chunks created: {summary.total_chunks_created}")

asyncio.run(main())
```

---

## Vector Search & Embedding Foundation

The platform uses **MongoDB Atlas Vector Search** as the semantic retrieval engine and an open-source, local embedding model running via **FastEmbed** (ONNX runtime, CPU-optimized).

### 1. Open-Source Local Embedding Model

- **Model**: `BAAI/bge-small-en-v1.5` (or `sentence-transformers/all-MiniLM-L6-v2`)
- **Dimensions**: `384`
- **Execution**: Runs locally via FastEmbed ONNX runtime without requiring GPU or PyTorch installations.
- **Swappable Architecture**: The `EmbeddingService` defines a `BaseEmbeddingProvider` interface, allowing hot-swapping providers (e.g. `FastEmbedProvider`, `MockEmbeddingProvider`, or cloud providers) without modifying pipeline code.

### 2. Knowledge Chunks Schema (`knowledge_chunks`)

```json
{
  "_id": "ObjectId('...')",
  "templeId": "temple_tirumala",
  "documentId": "doc_rituals_01",
  "content": "Suprabhata Seva is performed early in the morning to awaken the deity.",
  "embedding": [0.0125, -0.0432, 0.0891, ...],
  "title": "Daily Seva Schedule",
  "source": "tirumala_guidelines.pdf",
  "category": "rituals",
  "chunkIndex": 0,
  "tokenCount": 14,
  "metadata": {
    "contentLength": 75,
    "official": true
  },
  "createdAt": "2026-10-13T01:00:00Z",
  "updatedAt": "2026-10-13T01:00:00Z"
}
```

### 3. MongoDB Atlas Vector Search Index Configuration

Create a Search Index on the `knowledge_chunks` collection using the **JSON Editor**:

```json
{
  "fields": [
    {
      "type": "vector",
      "path": "embedding",
      "numDimensions": 384,
      "similarity": "cosine"
    },
    {
      "type": "filter",
      "path": "templeId"
    },
    {
      "type": "filter",
      "path": "category"
    }
  ]
}
```

- **Index Name**: `vector_index` (configured via `VECTOR_SEARCH_INDEX_NAME`).
- **Pre-filtering**: `templeId` is indexed as `filter` to enforce zero-leakage multi-tenancy.

---

## RAG Question-Answering Service

The RAG (Retrieval-Augmented Generation) pipeline connects the vector search foundation with LLM answer synthesis to provide grounded, hallucination-free answers to devotees.

```text
User Question ("What time is Morning Aarti?")
  ├── 1. Generate Query Vector   (FastEmbed 384-dimensional dense vector)
  ├── 2. Vector Search           (MongoDB Atlas $vectorSearch filtered strictly by templeId)
  ├── 3. Relevance Gate          (Filter candidate chunks by similarity threshold)
  ├── 4. Context Synthesis       (Assemble clean context blocks with citation provenance)
  ├── 5. Grounded Prompting      (Strict anti-hallucination system prompt)
  ├── 6. LLM Completion         (Swappable provider: Gemini, OpenAI, Mock)
  └── 7. Response Output         (Grounded answer, source citations, latency & metadata)
```

### Strict Grounding & Anti-Hallucination Policy
- **Verified Facts Only**: The LLM is strictly instructed to only answer using facts from the provided temple context and forbidden from guessing or extrapolating facts.
- **Authoritative Fallback**: If no chunks meet the relevance threshold, the system immediately returns a respectful refusal without invoking the LLM, eliminating hallucination and saving latency/cost:
  > *"I apologize, but this information is not available in the current temple records. Please consult the temple administration office or the official inquiry counter for assistance."*
- **Source Attribution**: Every response includes chunk-level citations (title, origin document/URL, category, similarity score, and content snippet).
- **API Key Security**: Backend communicates with the LLM provider directly; API keys are never exposed to clients.

### RAG API Query (`POST /api/v1/rag/query`)

#### Request:
```json
{
  "templeId": "temple_somnath",
  "question": "What are the morning darshan and aarti timings?",
  "topK": 5,
  "similarityThreshold": 0.4,
  "category": "timings"
}
```

#### Response:
```json
{
  "answer": "According to the temple records, the temple opens for devotees daily at 6:00 AM and Morning Aarti takes place at 7:00 AM.",
  "templeId": "temple_somnath",
  "question": "What are the morning darshan and aarti timings?",
  "sources": [
    {
      "title": "Somnath Darshan Timings",
      "source": "somnath_timings.pdf",
      "sourceUrl": "https://somnath.org/darshan-timings",
      "category": "timings",
      "chunkIndex": 0,
      "score": 0.8921,
      "contentSnippet": "The temple opens for devotees daily at 6:00 AM and closes at 10:00 PM. Morning Aarti is held at 7:00 AM...",
      "documentId": "doc_somnath_darshan"
    }
  ],
  "hasRelevantContext": true,
  "topScore": 0.8921,
  "latencyMs": 420.5,
  "metadata": {
    "chunksRetrieved": 1,
    "thresholdUsed": 0.4,
    "model": "gemini-1.5-flash"
  }
}
```

### Programmatic Python Usage

```python
import asyncio
from app.services.rag_service import rag_service

async def main():
    response = await rag_service.answer_question(
        temple_id="temple_somnath",
        question="When does the sound and light show start?",
        top_k=5,
        similarity_threshold=0.4,
    )

    print(f"Answer: {response.answer}")
    print(f"Grounded by {len(response.sources)} source(s):")
    for src in response.sources:
        print(f" - [{src.score:.2f}] {src.title} ({src.source})")

asyncio.run(main())
```

---

## Public Chatbot API (`POST /api/chat`)

A public-facing, widget-ready endpoint designed for website embedding, mobile applications, and devotee inquiry interfaces supporting multi-turn conversational dialogue.

```text
Visitor Question (Widget / Mobile App)
  ├── 1. Origin CORS Check          (Permissive regex allows widget embedding on any temple domain)
  ├── 2. Sliding Window Limiter     (Protects against abuse via IP rate limiting with Retry-After)
  ├── 3. templeId & Tenant Guard    (Validates templeId and verifies active status)
  ├── 4. Session & Tenancy Resolver (Validates/creates conversationId; blocks cross-temple leakage)
  ├── 5. History Context Retrieval  (Loads recent dialogue turns bounded by MAX_CONVERSATION_HISTORY_TURNS)
  ├── 6. RAG Pipeline Query         (Retrieves verified chunks & generates grounded answer)
  ├── 7. PII Redaction & Storage    (Scrubs phone numbers, emails, cards; sets TTL expiration)
  └── 8. Structured Response        (answer, attribution sources, templeId, conversationId, sessionId)
```

### Request Specification (`POST /api/chat`)

```json
{
  "templeId": "temple-001",
  "message": "What time is the morning pooja?",
  "conversationId": "conv_4f6d23038e914c3c",
  "sessionId": "sess_devotee_987"
}
```

| Field | Type | Required | Description |
| :--- | :--- | :--- | :--- |
| `templeId` | `string` | **Yes** | Identifier or slug of the temple (alphanumeric, dashes, underscores) |
| `message` | `string` | **Yes** | Devotee's question or message (1 to 2000 characters) |
| `conversationId`| `string` | No | Conversation session ID to continue an ongoing multi-turn dialogue (auto-generated if omitted) |
| `sessionId` | `string` | No | Client device/browser session identifier for analytics |

### Response Specification

```json
{
  "answer": "Morning pooja commences daily at 6:00 AM.",
  "sources": [
    {
      "title": "Pooja Timings Schedule",
      "source": "temple_pooja.pdf",
      "url": "https://temple.org/pooja",
      "snippet": "Morning pooja commences daily at 6:00 AM...",
      "score": 0.885
    }
  ],
  "templeId": "temple-001",
  "conversationId": "conv_4f6d23038e914c3c",
  "sessionId": "sess_devotee_987",
  "hasRelevantContext": true
}
```

### Multi-Turn Dialogue & Context Continuity

When a devotee sends an initial inquiry without `conversationId`, the backend creates a new conversational session and returns an active `conversationId` (e.g. `conv_4f6d...`). 

Subsequent client requests pass this `conversationId` back to the server:
1. **Context Loading**: The backend loads up to `MAX_CONVERSATION_HISTORY_TURNS` (default: 5 turns / 10 messages) in chronological order.
2. **Contextual Grounding**: Recent turns are injected into the LLM prompt under `RECENT CONVERSATION HISTORY:` so the model resolves anaphora (e.g. *"What about on weekends?"*, *"What does that ritual cost?"*).
3. **Follow-Up Search Expansion**: If a short follow-up query yields 0 vector search results, the RAG engine combines the prior user question with the current follow-up to retrieve relevant temple chunks.

### Strict Multi-Tenant Conversation Isolation

Conversations are strictly isolated by `templeId`:
- **Ownership Verification**: When a client provides a `conversationId`, the backend queries `{"templeId": temple_id, "conversationId": conversation_id}`.
- **Cross-Temple Protection**: If a client provides a valid `conversationId` belonging to Temple A while querying with `templeId: "Temple B"`, access is instantly blocked and returns `404 Not Found`. Temple B cannot read, append to, or leak dialogue from Temple A.
- **Physical Separation**: Chat conversations and messages are stored in separate MongoDB collections (`conversations` and `messages`), completely isolated from the temple knowledge base (`knowledge_chunks`).

### Privacy & PII Scrubbing

Devotees may inadvertently enter personal contact details or sensitive financial information in chat inquiries. Before saving any user dialogue to MongoDB:
- **Phone Numbers**: Local 10-digit, `+91`, US `(555) 123-4567`, and international formats are replaced with `[PHONE_REDACTED]`.
- **Email Addresses**: Scrubbed and replaced with `[EMAIL_REDACTED]`.
- **Payment Cards**: 13-19 digit card numbers are replaced with `[CARD_REDACTED]`.
- **National IDs**: Indian Aadhaar (`1234 5678 9012`) and US SSN (`123-45-6789`) are replaced with `[ID_REDACTED]`.
- **IP Anonymization**: Session telemetry anonymizes client IPs (zeroing the last octet: `203.0.113.0`) and strips authorization tokens/cookies.

### Configurable History Retention & TTL Expiration

- **Turns Bounding**: `MAX_CONVERSATION_HISTORY_TURNS` (default: 5) limits context window overhead and token costs.
- **Automatic Expiration**: `CONVERSATION_RETENTION_DAYS` (default: 30) computes `expiresAt = createdAt + retention_days`.
- **MongoDB TTL Index**: A native TTL index on `expiresAt` automatically purges expired conversation and message documents with zero manual maintenance.
- **Programmatic Cleanup**: The `conversation_service.cleanup_expired_history(temple_id)` method provides on-demand retention enforcement.

### Rate Limiting Architecture
- **In-Memory Sliding Window**: Configured via `RATE_LIMIT_REQUESTS_PER_MINUTE` (default: 60 rpm).
- **Standard Headers Attached**:
  - `X-RateLimit-Limit`: Maximum requests per minute window.
  - `X-RateLimit-Remaining`: Remaining request allowance in current window.
  - `Retry-After`: Seconds to wait before retrying when a `429 Too Many Requests` is returned.
- **Swappable Architecture**: The `RateLimiter` dependency accepts any implementation of `BaseRateLimiter`, allowing distributed Redis backends in high-traffic deployments.

### Embeddable Widget CORS
Cross-Origin Resource Sharing (CORS) is configured with `allow_origin_regex=r"^https?://.*$"` and credential support. This permits embeddable JavaScript/React widgets running on any official temple domain (`https://somnath.org`, `https://tirupatibalaji.ap.gov.in`, `http://localhost:3000`) to call `POST /api/chat` seamlessly.

---

## Multi-Temple Database Collections

| Collection | Model | Description | Mandatory Scope |
| :--- | :--- | :--- | :--- |
| `temples` | `Temple` | Distinct temple identity, location, darshan timings, languages, active status | Unique `slug` |
| `knowledge_documents` | `KnowledgeDocument` | Ingested source documents (PDF, DOCX, TXT) with content hash & status | `templeId`, `contentHash` |
| `knowledge_chunks` | `KnowledgeChunk` | Segmented text chunks with dense vector embeddings for RAG retrieval | `templeId`, `documentId` |
| `admins` | `Admin` | Administrative accounts (superadmin across platform or temple-specific admin) | Optional `templeId` |
| `conversations` | `Conversation` | Multi-turn user chat sessions associated with a specific temple | `templeId`, `sessionId` |
| `messages` | `Message` | Individual chat messages with citation and telemetry placeholders | `templeId`, `conversationId` |

---

## Getting Started

### 1. Prerequisites

- **Python 3.11+** installed (tested on Python 3.13)
- `pip` package manager
- MongoDB Atlas cluster URL (or a local MongoDB instance for development)

### 2. Setup Environment

```bash
# Clone the repository
git clone https://github.com/Hrithik-GV/temple-assist-chatbot.git
cd temple-assist-chatbot

# Create and activate virtual environment
python -m venv .venv

# Windows (PowerShell):
.\.venv\Scripts\Activate.ps1
# macOS / Linux:
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 3. Environment Variables Configuration

Copy `.env.example` to create `.env`:

```bash
# Windows:
copy .env.example .env
# macOS / Linux:
cp .env.example .env
```

| Variable | Description | Default |
| :--- | :--- | :--- |
| `PROJECT_NAME` | Name of the API application | `Temple Chatbot Platform API` |
| `ENVIRONMENT` | Running environment (`development`, `testing`, `production`) | `development` |
| `DEBUG` | Enable debug mode | `true` |
| `HOST` | Bind host address | `0.0.0.0` |
| `PORT` | Bind port number | `8000` |
| `LOG_LEVEL` | Logging level (`DEBUG`, `INFO`, `WARNING`, `ERROR`) | `INFO` |
| `CORS_ORIGINS` | Allowed CORS origins (comma-separated or JSON list) | `http://localhost:3000,http://localhost:5173,http://localhost:8000` |
| `API_V1_STR` | Prefix for version 1 API endpoints | `/api/v1` |
| `MONGODB_URI` | MongoDB Atlas connection string | `mongodb://localhost:27017` |
| `MONGODB_DB_NAME` | Target database name | `temple_chatbot_db` |
| `EMBEDDING_MODEL_NAME` | Open-source embedding model name | `BAAI/bge-small-en-v1.5` |
| `EMBEDDING_DIMENSION` | Dimension of embedding vectors | `384` |
| `VECTOR_SEARCH_INDEX_NAME` | Atlas Vector Search index identifier | `vector_index` |
| `DEFAULT_TOP_K` | Default number of retrieved search results | `5` |
| `DEFAULT_CHUNK_SIZE` | Default character length per knowledge chunk | `500` |
| `DEFAULT_CHUNK_OVERLAP` | Default character overlap between chunks | `50` |
| `CRAWLER_MAX_PAGES` | Default max pages to crawl per website | `15` |
| `CRAWLER_MAX_DEPTH` | Default max crawl depth from start URL | `3` |
| `CRAWLER_PAGE_TIMEOUT_MS` | Per-page navigation timeout in milliseconds | `30000` |
| `CRAWLER_WAIT_AFTER_LOAD_MS`| Wait time after load for dynamic JS/React render | `1000` |
| `CRAWLER_USER_AGENT` | Custom User-Agent header for Playwright crawler | `TempleAssistCrawler/1.0` |
| `LLM_PROVIDER` | Selected LLM provider (`gemini`, `openai`, `mock`) | `gemini` |
| `GEMINI_API_KEY` | Google Gemini API key | `None` |
| `GEMINI_MODEL` | Google Gemini model name | `gemini-1.5-flash` |
| `OPENAI_API_KEY` | OpenAI API key (if using OpenAI provider) | `None` |
| `OPENAI_MODEL` | OpenAI model name | `gpt-4o-mini` |
| `LLM_TEMPERATURE` | Generation temperature (lower = more grounded) | `0.2` |
| `RAG_DEFAULT_SIMILARITY_THRESHOLD` | Cosine similarity cutoff threshold for retrieval | `0.4` |
| `MAX_CONVERSATION_HISTORY_TURNS` | Recent dialogue turns loaded into prompt context | `5` |
| `CONVERSATION_RETENTION_DAYS` | Days before chat conversations/messages expire | `30` |

---

## Running the Backend

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Interactive documentation:
- Swagger Docs: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
- ReDoc: [http://127.0.0.1:8000/redoc](http://127.0.0.1:8000/redoc)

---

## Running Tests

Execute the automated test suite with `pytest`:

```bash
pytest -v
```

All 102 unit and integration tests cover:
- FastAPI lifecycle, CORS, and health check diagnostic endpoints.
- Multi-temple MongoDB data models, compound indexes, and tenancy scoping.
- Document text extraction for PDF, DOCX, and TXT files.
- Text normalization, control-character stripping, and whitespace collapse.
- Semantic boundary-aware chunking and token counting.
- SHA-256 content deduplication and duplicate skipping.
- End-to-end document ingestion pipeline and vector persistence.
- Rollback of partial chunks and FAILED status marking upon ingestion error.
- Playwright website crawler URL canonicalization and tracking tag removal.
- Domain guardrails (staying within the same domain, rejecting external/social links).
- Rendered HTML noise stripping (navigation, headers, footers, cookie banners, scripts, styles).
- Graceful crawler error resilience across broken pages and HTTP 4xx/5xx responses.
- Local FastEmbed dense vector generation (384 dimensions).
- Swappable embedding provider interface and mock providers.
- Atlas `$vectorSearch` aggregation pipeline construction and multi-tenant filtering.
- RAG question-answering retrieval filtered strictly by `templeId`.
- Relevance similarity threshold gating and custom `top_k` retrieval.
- Context synthesis, structured source citations, and snippet generation.
- Anti-hallucination system prompt construction and grounding guardrails.
- Authoritative no-context fallback responses when information is absent.
- Swappable LLM provider interface (`GeminiLLMProvider`, `OpenAILLMProvider`, `MockLLMProvider`).
- `/api/v1/rag/query` HTTP endpoint validation and execution.
- Public Chatbot API (`POST /api/chat`) and alias (`POST /api/v1/chat`).
- Request validation on `templeId` and empty/whitespace message content.
- Sliding window rate limiting enforcement with `429 Too Many Requests` and `Retry-After`.
- Permissive CORS preflight handling for embeddable widgets across any temple domain.
- Sensitive error masking ensuring database credentials and API keys are never exposed.
- Unique session and conversation ID generation (`conv_...`, `sess_...`).
- Multi-turn conversation history loading bounded by configurable `MAX_CONVERSATION_HISTORY_TURNS`.
- Strict cross-temple conversation isolation preventing access across different temples.
- PII sanitization (scrubbing emails, phone numbers, credit cards, and national IDs like Aadhaar/SSN).
- IP address anonymization and telemetry credential scrubbing.
- Configurable history retention with automatic TTL expiration timestamps and on-demand cleanup.

---

## Roadmap (Next Phases)

- **Phase 6: Multi-Turn Conversation History**: Multi-turn dialogue management, session storage in `conversations`/`messages`, and cross-temple isolation. *(Completed)*
- **Phase 7: Admin API & Authentication**: JWT authentication, temple admin management, and document upload endpoints.
- **Phase 8: Web Embeddable Chat Widget**: Lightweight devotee chat widget npm package.
