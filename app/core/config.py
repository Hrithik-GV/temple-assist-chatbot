"""Application configuration settings management using Pydantic Settings."""

import json
from typing import List, Optional, Union
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Core application settings loaded from environment variables and .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Project Information
    PROJECT_NAME: str = "Temple Chatbot Platform API"
    VERSION: str = "0.1.0"
    DESCRIPTION: str = "Backend API for Temple Chatbot Platform"
    API_V1_STR: str = "/api/v1"

    # Server Configuration
    ENVIRONMENT: str = "development"
    DEBUG: bool = True
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    # Logging
    LOG_LEVEL: str = "INFO"

    # MongoDB Atlas Configuration
    MONGODB_URI: str = "mongodb://localhost:27017"
    MONGODB_DB_NAME: str = "temple_chatbot_db"
    MONGODB_MIN_POOL_SIZE: int = 10
    MONGODB_MAX_POOL_SIZE: int = 50
    MONGODB_SERVER_SELECTION_TIMEOUT_MS: int = 5000
    MONGODB_CONNECT_TIMEOUT_MS: int = 5000

    # Embedding & Vector Search Configuration
    EMBEDDING_MODEL_NAME: str = "BAAI/bge-small-en-v1.5"
    EMBEDDING_DIMENSION: int = 384
    VECTOR_SEARCH_INDEX_NAME: str = "vector_index"
    DEFAULT_TOP_K: int = 5
    NUM_CANDIDATES_MULTIPLIER: int = 10

    # Ingestion Configuration
    DEFAULT_CHUNK_SIZE: int = 500
    DEFAULT_CHUNK_OVERLAP: int = 50

    # Crawler Configuration
    CRAWLER_MAX_PAGES: int = 15
    CRAWLER_MAX_DEPTH: int = 3
    CRAWLER_PAGE_TIMEOUT_MS: int = 30000
    CRAWLER_WAIT_AFTER_LOAD_MS: int = 1000
    CRAWLER_USER_AGENT: str = "TempleAssistCrawler/1.0"

    # LLM & RAG Configuration
    LLM_PROVIDER: str = "gemini"  # "gemini", "openai", or "mock"
    GEMINI_API_KEY: Optional[str] = None
    GEMINI_MODEL: str = "gemini-1.5-flash"
    OPENAI_API_KEY: Optional[str] = None
    OPENAI_MODEL: str = "gpt-4o-mini"
    OPENAI_BASE_URL: Optional[str] = None
    LLM_TEMPERATURE: float = 0.2
    LLM_MAX_OUTPUT_TOKENS: int = 1024
    LLM_REQUEST_TIMEOUT_SECONDS: float = 30.0
    RAG_DEFAULT_SIMILARITY_THRESHOLD: float = 0.4
    RAG_DEFAULT_TOP_K: int = 5
    RAG_MAX_CONTEXT_CHUNKS: int = 8

    # Conversation & Session History Configuration
    MAX_CONVERSATION_HISTORY_TURNS: int = 5  # Number of recent dialogue turns loaded into prompt context
    CONVERSATION_RETENTION_DAYS: int = 30  # Number of days before chat history expires (0 for indefinite)

    # Rate Limiting Configuration (for public chat endpoint)
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_REQUESTS_PER_MINUTE: int = 60

    # CORS & Public Widget Configuration
    CORS_ALLOW_ALL_ORIGINS: bool = True  # Allows embedding chat widget on any temple domain
    CORS_ORIGINS: Union[str, List[str]] = [
        "http://localhost:3000",
        "http://localhost:5173",
        "http://localhost:8000",
    ]

    @field_validator("CORS_ORIGINS")
    @classmethod
    def assemble_cors_origins(cls, value: Union[str, List[str]]) -> List[str]:
        """Parse CORS origins from a comma-separated string, JSON array, or list."""
        if isinstance(value, str):
            value = value.strip()
            if value.startswith("[") and value.endswith("]"):
                try:
                    parsed = json.loads(value)
                    if isinstance(parsed, list):
                        return [str(item).strip() for item in parsed if str(item).strip()]
                except json.JSONDecodeError:
                    pass
            # Comma-separated splitting
            return [item.strip() for item in value.split(",") if item.strip()]
        elif isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        return []

    @property
    def is_production(self) -> bool:
        """Check if application is running in production."""
        return self.ENVIRONMENT.lower() == "production"

    @property
    def is_development(self) -> bool:
        """Check if application is running in development."""
        return self.ENVIRONMENT.lower() == "development"


settings = Settings()
