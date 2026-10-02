"""
Configuration and settings management for the RFP Intelligence Platform.
All parameters, API keys, and model names are loaded from environment variables or .env file.
"""

import os
from pathlib import Path
from typing import Literal, Optional
from pydantic import BaseModel, Field
from dotenv import load_dotenv
import yaml

# Load environment variables from .env if present
PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")


class Settings(BaseModel):
    # Base Paths
    PROJECT_ROOT: Path = PROJECT_ROOT
    STORAGE_DIR: Path = PROJECT_ROOT / ".storage"
    OUTPUTS_DIR: Path = PROJECT_ROOT / "outputs"

    # LLM Configuration
    LLM_PROVIDER: Literal["openai", "gemini", "groq", "anthropic", "ollama", "mock"] = Field(
        default_factory=lambda: os.getenv("LLM_PROVIDER", "gemini").lower()
    )
    LLM_MODEL: str = Field(default_factory=lambda: os.getenv("LLM_MODEL", "gemini-1.5-flash"))
    LLM_TEMPERATURE: float = Field(
        default_factory=lambda: float(os.getenv("LLM_TEMPERATURE", "0.0"))
    )
    LLM_MAX_TOKENS: int = Field(default_factory=lambda: int(os.getenv("LLM_MAX_TOKENS", "2048")))

    # API Keys
    OPENAI_API_KEY: Optional[str] = Field(default_factory=lambda: os.getenv("OPENAI_API_KEY"))
    GEMINI_API_KEY: Optional[str] = Field(default_factory=lambda: os.getenv("GEMINI_API_KEY"))
    GROQ_API_KEY: Optional[str] = Field(default_factory=lambda: os.getenv("GROQ_API_KEY"))
    ANTHROPIC_API_KEY: Optional[str] = Field(default_factory=lambda: os.getenv("ANTHROPIC_API_KEY"))
    OLLAMA_BASE_URL: str = Field(
        default_factory=lambda: os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    )

    # Embedding & Retrieval Settings
    EMBEDDING_MODEL_NAME: str = Field(
        default_factory=lambda: os.getenv("EMBEDDING_MODEL_NAME", "sentence-transformers/all-MiniLM-L6-v2")
    )
    EMBEDDING_DEVICE: str = Field(default_factory=lambda: os.getenv("EMBEDDING_DEVICE", "cpu"))
    EMBEDDING_QUERY_PREFIX: str = Field(
        default_factory=lambda: os.getenv("EMBEDDING_QUERY_PREFIX", "")
    )

    RERANKER_MODEL_NAME: str = Field(
        default_factory=lambda: os.getenv("RERANKER_MODEL_NAME", "cross-encoder/ms-marco-MiniLM-L-6-v2")
    )
    RERANKER_TOP_K: int = Field(default_factory=lambda: int(os.getenv("RERANKER_TOP_K", "5")))
    RETRIEVAL_CANDIDATE_POOL: int = Field(
        default_factory=lambda: int(os.getenv("RETRIEVAL_CANDIDATE_POOL", "20"))
    )

    # Chunking Configuration (in tokens, matching plan ~500 / 75)
    CHUNK_SIZE: int = Field(default_factory=lambda: int(os.getenv("CHUNK_SIZE", "500")))
    CHUNK_OVERLAP: int = Field(default_factory=lambda: int(os.getenv("CHUNK_OVERLAP", "75")))
    TABLE_MAX_CHUNK_SIZE: int = Field(
        default_factory=lambda: int(os.getenv("TABLE_MAX_CHUNK_SIZE", "3500"))
    )

    # Agent & Validation Configuration
    MAX_VALIDATION_RETRIES: int = Field(
        default_factory=lambda: int(os.getenv("MAX_VALIDATION_RETRIES", "2"))
    )
    CONFIDENCE_PASS_THRESHOLD: float = Field(
        default_factory=lambda: float(os.getenv("CONFIDENCE_PASS_THRESHOLD", "0.70"))
    )
    DOC_TYPE_CONFIDENCE_THRESHOLD: float = Field(
        default_factory=lambda: float(os.getenv("DOC_TYPE_CONFIDENCE_THRESHOLD", "0.65"))
    )

    # Server / UI Configuration
    API_HOST: str = Field(default_factory=lambda: os.getenv("API_HOST", "0.0.0.0"))
    API_PORT: int = Field(default_factory=lambda: int(os.getenv("API_PORT", "8000")))


settings = Settings()

# Ensure required directories exist
settings.STORAGE_DIR.mkdir(parents=True, exist_ok=True)
settings.OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)


def load_fields_config() -> dict:
    """Load generic field definitions from config/fields.yaml."""
    yaml_path = settings.PROJECT_ROOT / "config" / "fields.yaml"
    if not yaml_path.exists():
        raise FileNotFoundError(f"Missing fields definition file: {yaml_path}")
    with open(yaml_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data.get("fields", {})
