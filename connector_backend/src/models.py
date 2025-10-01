"""
Pydantic models for API requests and responses.
"""
from datetime import datetime
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field, HttpUrl
from enum import Enum


class ServiceType(str, Enum):
    """Supported service types."""
    JIRA = "jira"
    CONFLUENCE = "confluence"


class AuthMethod(str, Enum):
    """Authentication methods."""
    BASIC = "basic"
    API_TOKEN = "api_token"
    OAUTH = "oauth"


class ConnectionStatus(str, Enum):
    """Connection status values."""
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    ERROR = "error"
    TESTING = "testing"


# Request Models
class CredentialsRequest(BaseModel):
    """Request model for storing credentials."""
    service_type: ServiceType = Field(..., description="Type of service (JIRA or Confluence)")
    base_url: HttpUrl = Field(..., description="Base URL of the service instance")
    auth_method: AuthMethod = Field(..., description="Authentication method")
    username: str = Field(..., description="Username or email")
    password: str = Field(..., description="Password or API token")
    
    class Config:
        schema_extra = {
            "example": {
                "service_type": "jira",
                "base_url": "https://your-domain.atlassian.net",
                "auth_method": "api_token",
                "username": "your-email@domain.com",
                "password": "your-api-token"
            }
        }


class ConnectionTestRequest(BaseModel):
    """Request model for testing connection."""
    service_type: ServiceType = Field(..., description="Type of service to test")
    
    class Config:
        schema_extra = {
            "example": {
                "service_type": "jira"
            }
        }


# Response Models
class ConnectionResponse(BaseModel):
    """Response model for connection operations."""
    service_type: ServiceType
    status: ConnectionStatus
    message: str
    base_url: Optional[str] = None
    username: Optional[str] = None
    connected_at: Optional[datetime] = None
    
    class Config:
        schema_extra = {
            "example": {
                "service_type": "jira",
                "status": "connected",
                "message": "Successfully connected to JIRA",
                "base_url": "https://your-domain.atlassian.net",
                "username": "your-email@domain.com",
                "connected_at": "2024-01-15T10:30:00Z"
            }
        }


class ProjectData(BaseModel):
    """Model for project information."""
    id: str = Field(..., description="Project ID")
    key: str = Field(..., description="Project key")
    name: str = Field(..., description="Project name")
    description: Optional[str] = Field(None, description="Project description")
    project_type: Optional[str] = Field(None, description="Type of project")
    url: Optional[str] = Field(None, description="Project URL")
    avatar_url: Optional[str] = Field(None, description="Project avatar URL")
    lead: Optional[Dict[str, Any]] = Field(None, description="Project lead information")
    
    class Config:
        schema_extra = {
            "example": {
                "id": "10001",
                "key": "DEMO",
                "name": "Demo Project",
                "description": "A demonstration project",
                "project_type": "software",
                "url": "https://your-domain.atlassian.net/browse/DEMO",
                "avatar_url": "https://your-domain.atlassian.net/secure/projectavatar?avatarId=10324",
                "lead": {
                    "displayName": "John Doe",
                    "emailAddress": "john.doe@domain.com"
                }
            }
        }


class ProjectsResponse(BaseModel):
    """Response model for projects list."""
    service_type: ServiceType
    projects: List[ProjectData]
    total_count: int
    
    class Config:
        schema_extra = {
            "example": {
                "service_type": "jira",
                "projects": [
                    {
                        "id": "10001",
                        "key": "DEMO",
                        "name": "Demo Project",
                        "description": "A demonstration project",
                        "project_type": "software",
                        "url": "https://your-domain.atlassian.net/browse/DEMO"
                    }
                ],
                "total_count": 1
            }
        }


class ErrorResponse(BaseModel):
    """Standard error response model."""
    error: str = Field(..., description="Error type")
    message: str = Field(..., description="Error message")
    details: Optional[Dict[str, Any]] = Field(None, description="Additional error details")
    
    class Config:
        schema_extra = {
            "example": {
                "error": "authentication_failed",
                "message": "Invalid credentials provided",
                "details": {
                    "service_type": "jira",
                    "base_url": "https://your-domain.atlassian.net"
                }
            }
        }


class HealthResponse(BaseModel):
    """Health check response model."""
    status: str = Field(..., description="Service status")
    message: str = Field(..., description="Status message")
    timestamp: datetime = Field(..., description="Response timestamp")
    version: str = Field(..., description="API version")
    
    class Config:
        schema_extra = {
            "example": {
                "status": "healthy",
                "message": "Connector backend is running",
                "timestamp": "2024-01-15T10:30:00Z",
                "version": "1.0.0"
            }
        }


# Internal Models for Credential Storage
class StoredCredentials(BaseModel):
    """Internal model for stored credentials."""
    service_type: ServiceType
    base_url: str
    auth_method: AuthMethod
    username: str
    encrypted_password: str
    created_at: datetime
    updated_at: datetime
    last_tested_at: Optional[datetime] = None
    is_active: bool = True
