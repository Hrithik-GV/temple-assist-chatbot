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
│   │   └── v1/
│   │       ├── __init__.py
│   │       ├── router.py     # Aggregated v1 API router
│   │       └── endpoints/
│   │           ├── __init__.py
│   │           └── health.py # Health, liveness, and readiness endpoints
│   ├── core/                 # Core system configurations & foundations
│   │   ├── __init__.py
│   │   ├── config.py         # Pydantic Settings management (.env loader)
│   │   ├── database.py       # MongoDB Atlas connection manager & index initialization
│   │   ├── errors.py         # Exception hierarchy & centralized error handlers
│   │   └── logging.py        # Centralized formatted logging foundation
│   ├── models/               # Multi-Temple domain models and Pydantic schemas
│   │   ├── __init__.py
│   │   ├── base.py           # MongoBaseModel with ObjectId and camelCase serialization
│   │   ├── collections.py    # Canonical MongoDB collection names
│   │   ├── common.py         # Generic response & error schemas
│   │   ├── health.py         # Health check schemas & component models
│   │   ├── temple.py         # Temple profile, timings, location, and contact models
│   │   ├── knowledge.py      # KnowledgeDocument, KnowledgeChunk, VectorSearchResult, IngestionResult
│   │   ├── admin.py          # Admin model with role-based and temple scoping
│   │   ├── conversation.py   # Multi-turn chat session model (templeId-scoped)
│   │   └── message.py        # Dialogue message history model (templeId-scoped)
│   ├── services/             # Business logic service layer
│   │   ├── __init__.py
│   │   ├── base.py           # Abstract base service class
│   │   ├── database_service.py   # Reusable multi-temple repository service
│   │   ├── embedding_service.py  # Swappable embedding provider (FastEmbed, Mock, etc.)
│   │   ├── health_service.py     # Health inspection & MongoDB diagnostic service
│   │   ├── ingestion_service.py  # Document ingestion pipeline (PDF, DOCX, TXT)
│   │   └── vector_search_service.py # Isolated MongoDB Atlas Vector Search service
│   └── utils/                # Utility helpers & shared functions
│       ├── __init__.py
│       ├── helpers.py        # Date/time helpers and utilities
│       ├── text_cleaner.py   # Text normalization and formatting noise cleaner
│       ├── text_chunker.py   # Boundary-aware semantic chunker with token counter
│       └── text_extractor.py # Document parsers for PDF, DOCX, and TXT
└── tests/                    # Automated test suite
    ├── __init__.py
    ├── conftest.py           # Pytest fixtures and TestClient
    ├── test_database.py      # MongoDB models, manager, and multi-tenancy tests
    ├── test_health.py        # Health, probe, and database readiness tests
    ├── test_ingestion.py     # Document extraction, cleaning, chunking, and ingestion pipeline tests
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

All 47 unit and integration tests cover:
- FastAPI lifecycle and health check diagnostic endpoints.
- Multi-temple MongoDB data models, indexes, and tenancy scoping.
- Document text extraction for PDF, DOCX, and TXT files.
- Text normalization, control-character stripping, and whitespace collapse.
- Semantic boundary-aware chunking and token counting.
- SHA-256 content deduplication and duplicate skipping.
- End-to-end document ingestion pipeline and vector persistence.
- Rollback of partial chunks and FAILED status marking upon ingestion error.
- Local FastEmbed dense vector generation (384 dimensions).
- Swappable embedding provider interface and mock providers.
- Atlas `$vectorSearch` aggregation pipeline construction and multi-tenant filtering.

---

## Roadmap (Next Phases)

- **Phase 3: Web Ingestion Engine**: Website crawler and HTML parser for automated document ingestion from temple URLs.
- **Phase 4: RAG Pipeline Integration**: Context assembling, prompt formatting, and grounding citations.
- **Phase 5: Conversational Chat API**: Multi-turn dialogue management, streaming responses, and telemetry.
