"""
Application configuration settings
"""

from pydantic_settings import BaseSettings
from typing import List


class Settings(BaseSettings):
    """Application settings"""
    
    # Project information
    PROJECT_NAME: str = "FundFlow AI"
    PROJECT_DESCRIPTION: str = "Autonomous Career Intelligence Agent"
    VERSION: str = "0.1.0"
    
    # API configuration
    API_V1_PREFIX: str = "/api"
    
    # CORS configuration
    ALLOWED_ORIGINS: List[str] = [
        "http://localhost:3000",
        "http://localhost:3001",
        "http://localhost:3002",
        "http://localhost:3003",
        "http://localhost:3004",
        "http://localhost:3005",
        "http://localhost:3006",
        "http://localhost:3007",
        "http://localhost:3008",
        "http://localhost:3009",
        "http://localhost:3010",
        "http://localhost:5173",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",
    ]
    
    # Database configuration
    DATABASE_URL: str = "sqlite:///./fundflow.db"
    
    # OpenAI configuration
    OPENAI_API_KEY: str = ""

    # Tavily (web search) configuration
    TAVILY_API_KEY: str = ""

    # Firecrawl (web scraping) configuration
    FIRECRAWL_API_KEY: str = ""

    # Discovery cache TTL in hours
    DISCOVERY_CACHE_HOURS: int = 24

    # LLM provider selection (e.g. "openai", "openrouter").
    # Used by future tickets; declared here so unknown env vars don't
    # trip pydantic-settings strict mode.
    LLM_PROVIDER: str = "openai"

    # OpenRouter configuration
    OPENROUTER_API_KEY: str = ""
    OPENROUTER_BASE_URL: str = "https://openrouter.ai/api/v1"
    OPENROUTER_MODEL: str = "anthropic/claude-3.5-sonnet"

    # Environment
    ENVIRONMENT: str = "development"
    DEBUG: bool = True

    class Config:
        env_file = ".env"
        case_sensitive = True
        # Allow additional env vars in .env without raising
        # "Extra inputs are not permitted".
        extra = "ignore"


settings = Settings()
