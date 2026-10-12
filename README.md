# Temple Chatbot Platform - Backend

Backend API foundation for the Temple Chatbot Platform built with **Python 3.13+**, **FastAPI**, and **MongoDB Atlas** (using the official Motor / PyMongo asynchronous driver).

This repository contains the production-ready backend architecture designed for multi-tenancy across multiple temples, scalable database integration, and seamless extension into future phases (RAG vector retrieval, website crawling, and conversational chat endpoints).

---

## Architecture & Directory Structure

The backend follows a clean, decoupled modular layout separating routing, business logic, domain models, database management, and core utilities:

```text
temple-assist-chatbot/
├── .env.example              # Environment variables template (includes MongoDB Atlas)
├── .env                      # Local environment configuration (git-ignored)
├── .gitignore                # Git ignore configuration
├── pyproject.toml            # Project metadata and pytest configuration
├── requirements.txt          # Python dependencies (FastAPI, Motor, PyMongo, Pydantic, etc.)
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
│   │   ├── knowledge.py      # KnowledgeDocument and KnowledgeChunk (templeId-scoped)
│   │   ├── admin.py          # Admin model with role-based and temple scoping
│   │   ├── conversation.py   # Multi-turn chat session model (templeId-scoped)
│   │   └── message.py        # Dialogue message history model (templeId-scoped)
│   ├── services/             # Business logic service layer
│   │   ├── __init__.py
│   │   ├── base.py           # Abstract base service class
│   │   ├── database_service.py # Reusable multi-temple repository service
│   │   └── health_service.py # Health inspection & MongoDB diagnostic service
│   └── utils/                # Utility helpers & shared functions
│       ├── __init__.py
│       └── helpers.py        # Date/time helpers and utilities
└── tests/                    # Automated test suite
    ├── __init__.py
    ├── conftest.py           # Pytest fixtures and TestClient
    ├── test_database.py      # MongoDB models, manager, and multi-tenancy tests
    └── test_health.py        # Health, probe, and database readiness tests
```

---

## Multi-Temple Database Design (MongoDB Atlas)

The system supports multi-tenancy out of the box. Every temple-specific knowledge record and dialogue entity strictly references a `templeId`.

### Collections & Schemas

| Collection | Model | Description | Mandatory Scope |
| :--- | :--- | :--- | :--- |
| `temples` | `Temple` | Distinct temple identity, location, darshan timings, languages, active status | Unique `slug` |
| `knowledge_documents` | `KnowledgeDocument` | Ingested source documents (website pages, FAQs, PDFs, texts) | `templeId` |
| `knowledge_chunks` | `KnowledgeChunk` | Segmented text chunks derived from documents for future retrieval | `templeId`, `documentId` |
| `admins` | `Admin` | Administrative accounts (superadmin across platform or temple-specific admin) | Optional `templeId` |
| `conversations` | `Conversation` | Multi-turn user chat sessions associated with a specific temple | `templeId`, `sessionId` |
| `messages` | `Message` | Individual chat messages (user, assistant, system) with citation placeholders | `templeId`, `conversationId` |

### Automatic Indexing
On application startup, the `MongoDBManager` ensures essential background indexes for query efficiency and multi-tenant isolation:
- `temples`: unique index on `slug`, index on `isActive`
- `knowledge_documents`: compound index on `("templeId", "createdAt")`, index on `("templeId", "status")`
- `knowledge_chunks`: compound index on `("templeId", "documentId", "chunkIndex")`
- `admins`: unique index on `email`, index on `("templeId", "role")`
- `conversations`: compound index on `("templeId", "sessionId")`
- `messages`: compound index on `("templeId", "conversationId", "createdAt")`

---

## Features

- **FastAPI Framework**: High performance, type-safe API with automatic OpenAPI documentation.
- **Official MongoDB Async Driver**: Powered by `motor` and `pymongo` with connection pooling (`minPoolSize`, `maxPoolSize`) and timeout controls.
- **Multi-Tenant Scoping**: All knowledge records and chat sessions strictly enforce `templeId` scoping.
- **Environment Configuration**: Powered by `pydantic-settings` to validate `.env` values at startup.
- **Startup & Shutdown Lifecycle**: Asynchronous connect and disconnect hooks integrated cleanly into FastAPI lifespan context.
- **Database Health Check**: Live ping verification and connection diagnostics included in `/api/v1/health` and `/api/v1/health/ready`.
- **Reusable Database Service**: `DatabaseService` abstraction providing high-level repository queries for multi-temple data.
- **FastAPI Dependency Injection**: `get_db()` dependency allows injecting active database handles into route endpoints.
- **Automated Testing**: 19 automated tests covering models, connections, and health checks without requiring real production credentials.

---

## Getting Started

### 1. Prerequisites

- **Python 3.11+** installed (tested on Python 3.13)
- `pip` package manager
- MongoDB Atlas cluster URL (or a local MongoDB instance for development)

### 2. Clone and Setup Environment

```bash
# Clone the repository (if not already in directory)
git clone https://github.com/Hrithik-GV/temple-assist-chatbot.git
cd temple-assist-chatbot

# Create a virtual environment
python -m venv .venv

# Activate the virtual environment:
# Windows (PowerShell):
.\.venv\Scripts\Activate.ps1
# Windows (cmd.exe):
.\.venv\Scripts\activate.bat
# macOS / Linux:
source .venv/bin/activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure Environment Variables

Copy `.env.example` to create `.env`:

```bash
# Windows:
copy .env.example .env

# macOS / Linux:
cp .env.example .env
```

Adjust any environment variables inside `.env` as needed:

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
| `MONGODB_URI` | MongoDB Atlas / Local connection string | `mongodb://localhost:27017` |
| `MONGODB_DB_NAME` | Target database name | `temple_chatbot_db` |
| `MONGODB_MIN_POOL_SIZE` | Minimum connection pool size | `10` |
| `MONGODB_MAX_POOL_SIZE` | Maximum connection pool size | `50` |
| `MONGODB_SERVER_SELECTION_TIMEOUT_MS` | Server selection timeout in milliseconds | `5000` |
| `MONGODB_CONNECT_TIMEOUT_MS` | Initial connection timeout in milliseconds | `5000` |

> **MongoDB Atlas Connection String**: For Atlas, format the URI as:
> ```text
> mongodb+srv://<username>:<password>@<cluster-url>/?retryWrites=true&w=majority
> ```

---

## Running the Backend

### Development Mode (with hot-reload)

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Alternatively, run the module directly:

```bash
python -m app.main
```

The application will be available at:
- **Root Info**: [http://127.0.0.1:8000/](http://127.0.0.1:8000/)
- **Interactive Swagger Docs**: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
- **ReDoc Documentation**: [http://127.0.0.1:8000/redoc](http://127.0.0.1:8000/redoc)
- **OpenAPI Schema**: [http://127.0.0.1:8000/api/v1/openapi.json](http://127.0.0.1:8000/api/v1/openapi.json)

---

## Running Tests

Execute the automated test suite with `pytest`:

```bash
pytest
```

To run with verbose output:

```bash
pytest -v
```

---

## API Endpoints

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/` | Root informational status and documentation links |
| `GET` | `/api/v1/health` | Comprehensive application and MongoDB health diagnostic |
| `GET` | `/api/v1/health/live` | Liveness probe for container orchestration |
| `GET` | `/api/v1/health/ready` | Readiness probe verifying database readiness |

### Health Check Response Example

```json
{
  "status": "healthy",
  "app_name": "Temple Chatbot Platform API",
  "version": "0.1.0",
  "environment": "development",
  "timestamp": "2026-10-12T19:05:59.685145Z",
  "components": {
    "mongodb": {
      "status": "healthy",
      "details": "Connected to MongoDB database 'temple_chatbot_db'"
    }
  }
}
```

---

## Roadmap (Next Phases)

- **Phase 3: Web Ingestion Engine**: Website crawler and parser for indexing temple websites into `knowledge_documents`.
- **Phase 4: RAG Pipeline**: Vector embeddings, chunking, and similarity search for grounded temple answers.
- **Phase 5: Conversational Chat API**: Multi-turn dialogue management, streaming responses, and telemetry.
