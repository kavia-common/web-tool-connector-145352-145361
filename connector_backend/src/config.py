"""
Configuration management for the connector backend.
"""
from typing import List
from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings with environment variable support."""
    
    # API Configuration
    api_host: str = Field(default="0.0.0.0", env="API_HOST")
    api_port: int = Field(default=8000, env="API_PORT")
    debug: bool = Field(default=False, env="DEBUG")
    
    # Security
    secret_key: str = Field(default="your-secret-key-change-in-production", env="SECRET_KEY")
    algorithm: str = Field(default="HS256", env="ALGORITHM")
    access_token_expire_minutes: int = Field(default=30, env="ACCESS_TOKEN_EXPIRE_MINUTES")
    
    # CORS
    cors_origins: List[str] = Field(
        default=["http://localhost:3000", "https://localhost:3000"],
        env="CORS_ORIGINS"
    )
    
    # Atlassian OAuth 2.0 (3LO) Configuration
    atlassian_client_id: str = Field(default="", env="ATLASSIAN_CLIENT_ID")
    atlassian_client_secret: str = Field(default="", env="ATLASSIAN_CLIENT_SECRET")
    redirect_uri: str = Field(default="http://localhost:8000/auth/callback", env="REDIRECT_URI")
    
    # Individual service OAuth (optional, fallback to main Atlassian app)
    jira_client_id: str = Field(default="", env="JIRA_CLIENT_ID")
    jira_client_secret: str = Field(default="", env="JIRA_CLIENT_SECRET")
    confluence_client_id: str = Field(default="", env="CONFLUENCE_CLIENT_ID")
    confluence_client_secret: str = Field(default="", env="CONFLUENCE_CLIENT_SECRET")
    oauth_redirect_uri: str = Field(default="http://localhost:8000/auth/callback", env="OAUTH_REDIRECT_URI")
    
    # OAuth URLs
    atlassian_auth_url: str = Field(default="https://auth.atlassian.com/authorize", env="ATLASSIAN_AUTH_URL")
    atlassian_token_url: str = Field(default="https://auth.atlassian.com/oauth/token", env="ATLASSIAN_TOKEN_URL")
    atlassian_api_url: str = Field(default="https://api.atlassian.com", env="ATLASSIAN_API_URL")
    
    class Config:
        env_file = ".env"
        case_sensitive = False

    def parse_cors_origins(self) -> List[str]:
        """Parse CORS origins from comma-separated string."""
        if isinstance(self.cors_origins, str):
            return [origin.strip() for origin in self.cors_origins.split(",")]
        return self.cors_origins


# Global settings instance
settings = Settings()
