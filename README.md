# Temple Chatbot Platform - Backend

Backend API foundation for the Temple Chatbot Platform built with **Python 3.13+** and **FastAPI**.

This repository contains the production-ready foundational architecture designed for scalability, maintainability, and seamless extension into future phases (MongoDB integration, RAG vector retrieval, website crawling, and conversational chat endpoints).

---

## Architecture & Directory Structure

The backend follows a clean, decoupled modular layout separating routing, business logic, domain models, and core utilities:

```text
temple-assist-chatbot/
├── .env.example              # Environment variables template
├── .env                      # Local environment configuration (git-ignored)
├── .gitignore                # Git ignore configuration
├── pyproject.toml            # Project metadata and pytest configuration
├── requirements.txt          # Python dependencies
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
│   │   ├── errors.py         # Exception hierarchy & centralized error handlers
│   │   └── logging.py        # Centralized formatted logging foundation
│   ├── models/               # Domain models and Pydantic schemas
│   │   ├── __init__.py
│   │   ├── common.py         # Generic response & error schemas
│   │   └── health.py         # Health check schemas & component models
│   ├── services/             # Business logic service layer
│   │   ├── __init__.py
│   │   ├── base.py           # Abstract base service class
│   │   └── health_service.py # Health inspection & diagnostic service
│   └── utils/                # Utility helpers & shared functions
│       ├── __init__.py
│       └── helpers.py        # Date/time helpers and utilities
└── tests/                    # Automated test suite
    ├── __init__.py
    ├── conftest.py           # Pytest fixtures and TestClient
    └── test_health.py        # Health endpoint & error handling tests
```

---

## Features

- **FastAPI Framework**: High performance, type-safe API with automatic OpenAPI documentation.
- **Environment Configuration**: Powered by `pydantic-settings` to validate `.env` values at startup.
- **CORS Support**: Configurable allowed origins via comma-separated string or JSON array.
- **Centralized Error Handling**: Standardized error response envelope for application errors, validation errors, and unhandled server errors.
- **Structured Logging**: Unified format across modules with adjustable log levels.
- **System Health Checks**:
  - `/api/v1/health` (Overall system and future component health status)
  - `/api/v1/health/live` (Kubernetes/Docker liveness probe)
  - `/api/v1/health/ready` (Readiness probe)
- **Automated Testing**: Pytest suite using FastAPI's `TestClient`.

---

## Getting Started

### 1. Prerequisites

- **Python 3.11+** installed (tested on Python 3.13)
- `pip` package manager

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

To run with verbose output and test coverage:

```bash
pytest -v
```

---

## API Endpoints (Foundation)

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/` | Root informational status and documentation links |
| `GET` | `/api/v1/health` | Comprehensive application health status |
| `GET` | `/api/v1/health/live` | Liveness probe for container orchestration |
| `GET` | `/api/v1/health/ready` | Readiness probe for container orchestration |

---

## Roadmap (Next Phases)

- **Phase 2: Database Layer**: MongoDB integration (Motor / ODM) for temple details, FAQs, and conversation storage.
- **Phase 3: Web Ingestion Engine**: Website crawler and parser for indexing temple websites.
- **Phase 4: RAG Pipeline**: Vector embeddings, chunking, and similarity search for grounded temple answers.
- **Phase 5: Conversational Chat API**: Multi-turn dialogue management, streaming responses, and telemetry.
