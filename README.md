# Temple Chatbot Platform - Backend

Backend API foundation for the Temple Chatbot Platform built with **Python 3.13+**, **FastAPI**, **MongoDB Atlas**, and **MongoDB Atlas Vector Search** (using the official Motor / PyMongo asynchronous driver and FastEmbed local ONNX embedding models).

This repository contains the production-ready backend architecture designed for multi-tenancy across multiple temples, scalable database integration, and high-performance vector search retrieval for the RAG pipeline.

---

## Architecture & Directory Structure

The backend follows a clean, decoupled modular layout separating routing, business logic, domain models, database management, embeddings, and core utilities:

```text
temple-assist-chatbot/
├── .env.example              # Environment variables template (includes MongoDB & Vector Search)
├── .env                      # Local environment configuration (git-ignored)
├── .gitignore                # Git ignore configuration
├── pyproject.toml            # Project metadata and pytest configuration
├── requirements.txt          # Python dependencies (FastAPI, Motor, FastEmbed, PyMongo, Pydantic, etc.)
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
│   │   ├── knowledge.py      # KnowledgeDocument, KnowledgeChunk (embeddings, metadata), and VectorSearchResult
│   │   ├── admin.py          # Admin model with role-based and temple scoping
│   │   ├── conversation.py   # Multi-turn chat session model (templeId-scoped)
│   │   └── message.py        # Dialogue message history model (templeId-scoped)
│   ├── services/             # Business logic service layer
│   │   ├── __init__.py
│   │   ├── base.py           # Abstract base service class
│   │   ├── database_service.py   # Reusable multi-temple repository service
│   │   ├── embedding_service.py  # Swappable embedding provider (FastEmbed, Mock, etc.)
│   │   ├── health_service.py     # Health inspection & MongoDB diagnostic service
│   │   └── vector_search_service.py # Isolated MongoDB Atlas Vector Search service
│   └── utils/                # Utility helpers & shared functions
│       ├── __init__.py
│       └── helpers.py        # Date/time helpers and utilities
└── tests/                    # Automated test suite
    ├── __init__.py
    ├── conftest.py           # Pytest fixtures and TestClient
    ├── test_database.py      # MongoDB models, manager, and multi-tenancy tests
    ├── test_health.py        # Health, probe, and database readiness tests
    └── test_vector_search.py # Embedding generation, chunk schema, and vector search tests
```

---

## Vector Search & Embedding Foundation

The platform uses **MongoDB Atlas Vector Search** as the semantic retrieval engine and an open-source, local embedding model running via **FastEmbed** (ONNX runtime, CPU-optimized).

### 1. Open-Source Local Embedding Model

- **Model**: `BAAI/bge-small-en-v1.5` (or `sentence-transformers/all-MiniLM-L6-v2`)
- **Dimensions**: `384`
- **Execution**: Runs locally via FastEmbed ONNX runtime without requiring heavy GPU or PyTorch installations.
- **Swappable Architecture**: The `EmbeddingService` defines a `BaseEmbeddingProvider` interface, allowing hot-swapping providers (e.g. `FastEmbedProvider`, `MockEmbeddingProvider`, or future cloud providers like OpenAI/Voyage/Cohere) without changing business logic.

### 2. Knowledge Chunks Schema (`knowledge_chunks`)

Every chunk stored in the database adheres to the following multi-temple schema:

```json
{
  "_id": "ObjectId('...')",
  "templeId": "temple_tirumala",
  "documentId": "doc_rituals_01",
  "content": "Suprabhata Seva is performed early in the morning to awaken the deity.",
  "embedding": [0.0125, -0.0432, 0.0891, ...],
  "title": "Daily Seva Schedule",
  "source": "https://tirumala.org/rituals",
  "category": "rituals",
  "chunkIndex": 0,
  "tokenCount": 14,
  "metadata": {
    "section": "Morning Sevas",
    "verified": true
  },
  "createdAt": "2026-10-13T01:00:00Z",
  "updatedAt": "2026-10-13T01:00:00Z"
}
```

### 3. MongoDB Atlas Vector Search Index Configuration

To enable vector search in MongoDB Atlas, create a Search Index on the `knowledge_chunks` collection using the **JSON Editor**:

#### Index Definition JSON:

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

#### Step-by-Step Setup in Atlas UI:

1. Log in to [MongoDB Atlas](https://cloud.mongodb.com/).
2. Navigate to your cluster and click **Browse Collections**.
3. Select your database (e.g., `temple_chatbot_db`) and click on the `knowledge_chunks` collection.
4. Select the **Atlas Search** tab and click **Create Search Index**.
5. Choose **Atlas Vector Search** > **JSON Editor** and click **Next**.
6. Set the **Index Name** to `vector_index` (must match `VECTOR_SEARCH_INDEX_NAME` in `.env`).
7. Paste the JSON definition above.
8. Click **Next** and then **Create Search Index**. The index will build in a few seconds.

### 4. Vector Search Pipeline & Fallback

The `VectorSearchService` implements the native Atlas `$vectorSearch` aggregation stage:

```python
pipeline = [
    {
        "$vectorSearch": {
            "index": "vector_index",
            "path": "embedding",
            "queryVector": query_vector,
            "numCandidates": limit * 10,
            "limit": limit,
            "filter": {
                "templeId": { "$eq": temple_id }
            }
        }
    },
    {
        "$project": {
            "_id": 1,
            "templeId": 1,
            "documentId": 1,
            "content": 1,
            "title": 1,
            "source": 1,
            "category": 1,
            "metadata": 1,
            "score": { "$meta": "vectorSearchScore" }
        }
    }
]
```

- **Multi-Tenant Isolation**: The query is strictly filtered by `templeId` at the vector index level so no cross-temple data leakage occurs.
- **Configurable Results**: `top_k` controls the number of returned chunks (capped safely at 100).
- **Local Fallback**: If running on a local MongoDB deployment without Atlas Search, `VectorSearchService` automatically falls back to in-memory cosine similarity search so local developers and automated test suites can execute end-to-end without an active Atlas Search cluster.

---

## Multi-Temple Database Collections

| Collection | Model | Description | Mandatory Scope |
| :--- | :--- | :--- | :--- |
| `temples` | `Temple` | Distinct temple identity, location, darshan timings, languages, active status | Unique `slug` |
| `knowledge_documents` | `KnowledgeDocument` | Ingested source documents (website pages, FAQs, PDFs, texts) | `templeId` |
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

All 31 unit and integration tests cover:
- FastAPI lifecycle and health check diagnostic endpoints.
- Multi-temple MongoDB data models, indexes, and tenancy scoping.
- Local FastEmbed dense vector generation (384 dimensions).
- Swappable embedding provider interface and mock providers.
- Knowledge chunk embedding generation and batch persistence.
- Atlas `$vectorSearch` aggregation pipeline construction.
- Semantic similarity search filtering by `templeId` and `category`.
- In-memory cosine similarity ranking fallback for offline development.

---

## Roadmap (Next Phases)

- **Phase 3: Web Ingestion Engine**: Website crawler and HTML parser for automated document ingestion into `knowledge_documents` and chunking.
- **Phase 4: RAG Pipeline Integration**: Context assembling, prompt formatting, and grounding citations.
- **Phase 5: Conversational Chat API**: Multi-turn dialogue management, streaming responses, and telemetry.
