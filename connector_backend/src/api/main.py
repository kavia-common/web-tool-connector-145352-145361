"""
FastAPI main application for JIRA/Confluence connector backend.
"""
from datetime import datetime
from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import logging

from src.config import settings
from src.models import (
    ServiceType, CredentialsRequest, ConnectionTestRequest,
    ConnectionResponse, ProjectsResponse, ErrorResponse, HealthResponse,
    ConnectionStatus, OAuthInitRequest, OAuthInitResponse, OAuthCallbackRequest
)
from src.services import credential_service, jira_service, confluence_service, oauth_service, session_service

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# FastAPI app with metadata for OpenAPI documentation
app = FastAPI(
    title="JIRA/Confluence Connector API",
    description="""
    **Ocean Professional** connector backend for JIRA and Confluence integration.
    
    This API provides endpoints for:
    - Authenticating with JIRA and Confluence instances
    - Testing connection status
    - Fetching project and space data
    - Managing stored credentials securely
    
    ## Authentication Methods
    - **Basic Authentication**: Username and password
    - **API Token**: Email and API token (recommended for Atlassian Cloud)
    
    ## Security
    - Credentials are encrypted and stored securely
    - All API endpoints use HTTPS in production
    - Token-based session management
    
    ## Support
    For questions or support, please refer to the API documentation.
    """,
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_tags=[
        {
            "name": "health",
            "description": "Health check and system status"
        },
        {
            "name": "authentication", 
            "description": "Credential management and authentication"
        },
        {
            "name": "connections",
            "description": "Connection testing and status checks"
        },
        {
            "name": "projects",
            "description": "Project and space data retrieval"
        },
        {
            "name": "oauth",
            "description": "OAuth 2.0 authentication flows"
        },
        {
            "name": "sessions",
            "description": "Session management"
        }
    ]
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.parse_cors_origins(),
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
)


# Exception handlers
@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """Global exception handler for unhandled errors."""
    logger.error(f"Unhandled error: {str(exc)}")
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=ErrorResponse(
            error="internal_server_error",
            message="An unexpected error occurred"
        ).dict()
    )


# PUBLIC_INTERFACE
@app.get(
    "/",
    response_model=HealthResponse,
    tags=["health"],
    summary="Health Check",
    description="Check if the connector backend service is running and healthy."
)
def health_check():
    """
    Health check endpoint to verify service status.
    
    Returns:
        HealthResponse: Service health status and metadata
    """
    return HealthResponse(
        status="healthy",
        message="JIRA/Confluence Connector Backend is running",
        timestamp=datetime.utcnow(),
        version="1.0.0"
    )


# PUBLIC_INTERFACE
@app.get(
    "/health",
    response_model=HealthResponse,
    tags=["health"],
    summary="Detailed Health Check",
    description="Detailed health check with service information."
)
def detailed_health_check():
    """
    Detailed health check endpoint.
    
    Returns:
        HealthResponse: Detailed service health information
    """
    return HealthResponse(
        status="healthy",
        message="All systems operational",
        timestamp=datetime.utcnow(),
        version="1.0.0"
    )


# PUBLIC_INTERFACE
@app.post(
    "/auth/credentials",
    response_model=ConnectionResponse,
    tags=["authentication"],
    summary="Store Credentials",
    description="Store encrypted credentials for JIRA or Confluence authentication.",
    responses={
        200: {"description": "Credentials stored successfully"},
        400: {"model": ErrorResponse, "description": "Invalid request data"},
        500: {"model": ErrorResponse, "description": "Internal server error"}
    }
)
def store_credentials(request: CredentialsRequest):
    """
    Store encrypted credentials for a service.
    
    Args:
        request: Credentials request containing service details and auth info
        
    Returns:
        ConnectionResponse: Status of credential storage operation
    """
    try:
        # Store credentials
        credential_service.store_credentials(request)
        
        # Test the connection immediately
        if request.service_type == ServiceType.JIRA:
            connection_status, message = jira_service.test_connection(str(request.base_url))
        else:
            connection_status, message = confluence_service.test_connection(str(request.base_url))
        
        return ConnectionResponse(
            service_type=request.service_type,
            status=connection_status,
            message=f"Credentials stored. {message}",
            base_url=str(request.base_url),
            username=request.username,
            connected_at=datetime.utcnow() if connection_status == ConnectionStatus.CONNECTED else None
        )
        
    except Exception as e:
        logger.error(f"Failed to store credentials: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ErrorResponse(
                error="credential_storage_failed",
                message="Failed to store credentials",
                details={"service_type": request.service_type.value}
            ).dict()
        )


# PUBLIC_INTERFACE
@app.post(
    "/connections/test",
    response_model=ConnectionResponse,
    tags=["connections"],
    summary="Test Connection",
    description="Test connection to a previously configured service using credentials or OAuth.",
    responses={
        200: {"description": "Connection test completed"},
        404: {"model": ErrorResponse, "description": "No credentials or OAuth tokens found"},
        400: {"model": ErrorResponse, "description": "Invalid request data"}
    }
)
def test_connection(request: ConnectionTestRequest, use_oauth: bool = False):
    """
    Test connection to a configured service.
    
    Args:
        request: Connection test request
        use_oauth: Whether to test OAuth connection instead of credentials
        
    Returns:
        ConnectionResponse: Connection test results
    """
    try:
        if use_oauth:
            # Test OAuth connection
            connection_status, message = oauth_service.test_oauth_connection(request.service_type)
            
            return ConnectionResponse(
                service_type=request.service_type,
                status=connection_status,
                message=message,
                base_url=None,  # OAuth doesn't use single base URL
                username=None,  # User info in OAuth tokens
                connected_at=datetime.utcnow() if connection_status == ConnectionStatus.CONNECTED else None
            )
        else:
            # Test credential-based connection
            stored_services = credential_service.list_stored_services()
            service_configs = [s for s in stored_services if s["service_type"] == request.service_type.value]
            
            if not service_configs:
                # Fallback to OAuth test if no credentials
                connection_status, message = oauth_service.test_oauth_connection(request.service_type)
                
                if connection_status == ConnectionStatus.ERROR:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail=ErrorResponse(
                            error="no_auth_found",
                            message=f"No stored credentials or OAuth tokens found for {request.service_type.value}",
                            details={"service_type": request.service_type.value}
                        ).dict()
                    )
                
                return ConnectionResponse(
                    service_type=request.service_type,
                    status=connection_status,
                    message=f"OAuth: {message}",
                    base_url=None,
                    username=None,
                    connected_at=datetime.utcnow() if connection_status == ConnectionStatus.CONNECTED else None
                )
            
            # Test connection for the first (or only) configuration
            base_url = service_configs[0]["base_url"]
            
            if request.service_type == ServiceType.JIRA:
                connection_status, message = jira_service.test_connection(base_url)
            else:
                connection_status, message = confluence_service.test_connection(base_url)
            
            return ConnectionResponse(
                service_type=request.service_type,
                status=connection_status,
                message=message,
                base_url=base_url,
                username=service_configs[0]["username"],
                connected_at=datetime.utcnow() if connection_status == ConnectionStatus.CONNECTED else None
            )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Connection test failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ErrorResponse(
                error="connection_test_failed",
                message="Connection test failed",
                details={"service_type": request.service_type.value}
            ).dict()
        )


# PUBLIC_INTERFACE
@app.get(
    "/connections/status",
    tags=["connections"],
    summary="Get All Connection Status",
    description="Get connection status for all configured services including OAuth connections."
)
def get_all_connections_status():
    """
    Get connection status for all stored services and OAuth connections.
    
    Returns:
        List of connection status for each configured service
    """
    try:
        connections = []
        
        # Check credential-based connections
        stored_services = credential_service.list_stored_services()
        for service in stored_services:
            service_type = ServiceType(service["service_type"])
            base_url = service["base_url"]
            
            if service_type == ServiceType.JIRA:
                connection_status, message = jira_service.test_connection(base_url)
            else:
                connection_status, message = confluence_service.test_connection(base_url)
            
            connections.append(ConnectionResponse(
                service_type=service_type,
                status=connection_status,
                message=f"Credentials: {message}",
                base_url=base_url,
                username=service["username"],
                connected_at=datetime.utcnow() if connection_status == ConnectionStatus.CONNECTED else None
            ))
        
        # Check OAuth connections
        oauth_connections = oauth_service.list_oauth_connections()
        for oauth_conn in oauth_connections:
            service_type = ServiceType(oauth_conn["service_type"])
            connection_status, message = oauth_service.test_oauth_connection(service_type)
            
            user_info = oauth_conn.get("user_info", {})
            connections.append(ConnectionResponse(
                service_type=service_type,
                status=connection_status,
                message=f"OAuth: {message}",
                base_url=None,  # OAuth doesn't use single base URL
                username=user_info.get("displayName") if user_info else None,
                connected_at=datetime.utcnow() if connection_status == ConnectionStatus.CONNECTED else None
            ))
        
        return {"connections": connections, "total_count": len(connections)}
        
    except Exception as e:
        logger.error(f"Failed to get connection status: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ErrorResponse(
                error="status_check_failed",
                message="Failed to check connection status"
            ).dict()
        )


# PUBLIC_INTERFACE
@app.get(
    "/projects/jira",
    response_model=ProjectsResponse,
    tags=["projects"],
    summary="Get JIRA Projects",
    description="Fetch list of JIRA projects for authenticated user using credentials or OAuth.",
    responses={
        200: {"description": "Projects retrieved successfully"},
        404: {"model": ErrorResponse, "description": "No JIRA credentials or OAuth tokens found"},
        401: {"model": ErrorResponse, "description": "Authentication failed"}
    }
)
def get_jira_projects(use_oauth: bool = False):
    """
    Fetch JIRA projects for the authenticated user.
    
    Args:
        use_oauth: Whether to use OAuth authentication instead of stored credentials
    
    Returns:
        ProjectsResponse: List of JIRA projects
    """
    try:
        if use_oauth:
            # Try OAuth first
            projects, error = jira_service.get_projects(oauth_mode=True)
            if error:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED if "Authentication" in error else status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=ErrorResponse(
                        error="oauth_project_fetch_failed",
                        message=error,
                        details={"service_type": "jira", "auth_method": "oauth"}
                    ).dict()
                )
        else:
            # Use stored credentials
            stored_services = credential_service.list_stored_services()
            jira_configs = [s for s in stored_services if s["service_type"] == "jira"]
            
            if not jira_configs:
                # Fallback to OAuth if no credentials
                projects, error = jira_service.get_projects(oauth_mode=True)
                if error:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail=ErrorResponse(
                            error="no_jira_auth",
                            message="No JIRA credentials or OAuth tokens found. Please authenticate first.",
                            details={"service_type": "jira"}
                        ).dict()
                    )
            else:
                # Use the first JIRA configuration
                base_url = jira_configs[0]["base_url"]
                projects, error = jira_service.get_projects(base_url)
                
                if error:
                    if "Authentication failed" in error:
                        raise HTTPException(
                            status_code=status.HTTP_401_UNAUTHORIZED,
                            detail=ErrorResponse(
                                error="authentication_failed",
                                message=error,
                                details={"service_type": "jira", "base_url": base_url}
                            ).dict()
                        )
                    else:
                        raise HTTPException(
                            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail=ErrorResponse(
                                error="project_fetch_failed",
                                message=error,
                                details={"service_type": "jira"}
                            ).dict()
                        )
        
        return ProjectsResponse(
            service_type=ServiceType.JIRA,
            projects=projects,
            total_count=len(projects)
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to fetch JIRA projects: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ErrorResponse(
                error="project_fetch_failed",
                message="Failed to fetch JIRA projects"
            ).dict()
        )


# PUBLIC_INTERFACE
@app.get(
    "/projects/confluence",
    response_model=ProjectsResponse,
    tags=["projects"],
    summary="Get Confluence Spaces",
    description="Fetch list of Confluence spaces for authenticated user using credentials or OAuth.",
    responses={
        200: {"description": "Spaces retrieved successfully"},
        404: {"model": ErrorResponse, "description": "No Confluence credentials or OAuth tokens found"},
        401: {"model": ErrorResponse, "description": "Authentication failed"}
    }
)
def get_confluence_spaces(use_oauth: bool = False):
    """
    Fetch Confluence spaces for the authenticated user.
    
    Args:
        use_oauth: Whether to use OAuth authentication instead of stored credentials
    
    Returns:
        ProjectsResponse: List of Confluence spaces
    """
    try:
        if use_oauth:
            # Try OAuth first
            spaces, error = confluence_service.get_spaces(oauth_mode=True)
            if error:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED if "Authentication" in error else status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=ErrorResponse(
                        error="oauth_space_fetch_failed",
                        message=error,
                        details={"service_type": "confluence", "auth_method": "oauth"}
                    ).dict()
                )
        else:
            # Use stored credentials
            stored_services = credential_service.list_stored_services()
            confluence_configs = [s for s in stored_services if s["service_type"] == "confluence"]
            
            if not confluence_configs:
                # Fallback to OAuth if no credentials
                spaces, error = confluence_service.get_spaces(oauth_mode=True)
                if error:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail=ErrorResponse(
                            error="no_confluence_auth",
                            message="No Confluence credentials or OAuth tokens found. Please authenticate first.",
                            details={"service_type": "confluence"}
                        ).dict()
                    )
            else:
                # Use the first Confluence configuration
                base_url = confluence_configs[0]["base_url"]
                spaces, error = confluence_service.get_spaces(base_url)
                
                if error:
                    if "Authentication failed" in error:
                        raise HTTPException(
                            status_code=status.HTTP_401_UNAUTHORIZED,
                            detail=ErrorResponse(
                                error="authentication_failed",
                                message=error,
                                details={"service_type": "confluence", "base_url": base_url}
                            ).dict()
                        )
                    else:
                        raise HTTPException(
                            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail=ErrorResponse(
                                error="space_fetch_failed",
                                message=error,
                                details={"service_type": "confluence"}
                            ).dict()
                        )
        
        return ProjectsResponse(
            service_type=ServiceType.CONFLUENCE,
            projects=spaces,  # Treating spaces as projects
            total_count=len(spaces)
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to fetch Confluence spaces: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ErrorResponse(
                error="space_fetch_failed",
                message="Failed to fetch Confluence spaces"
            ).dict()
        )


# PUBLIC_INTERFACE
@app.delete(
    "/auth/credentials/{service_type}",
    tags=["authentication"],
    summary="Delete Credentials",
    description="Delete stored credentials for a service."
)
def delete_credentials(service_type: ServiceType):
    """
    Delete stored credentials for a service.
    
    Args:
        service_type: Type of service to delete credentials for
        
    Returns:
        Success message
    """
    try:
        # Get stored services to find base URL
        stored_services = credential_service.list_stored_services()
        service_configs = [s for s in stored_services if s["service_type"] == service_type.value]
        
        if not service_configs:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=ErrorResponse(
                    error="no_credentials_found",
                    message=f"No stored credentials found for {service_type.value}"
                ).dict()
            )
        
        # Delete credentials for all configurations of this service type
        deleted_count = 0
        for config in service_configs:
            if credential_service.delete_credentials(service_type, config["base_url"]):
                deleted_count += 1
        
        return {
            "message": f"Successfully deleted {deleted_count} credential(s) for {service_type.value}",
            "deleted_count": deleted_count
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete credentials: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ErrorResponse(
                error="credential_deletion_failed",
                message="Failed to delete credentials"
            ).dict()
        )


# OAuth 2.0 Endpoints

# PUBLIC_INTERFACE
@app.post(
    "/auth/oauth/init",
    response_model=OAuthInitResponse,
    tags=["oauth"],
    summary="Initialize OAuth Flow",
    description="Initialize OAuth 2.0 authorization flow for Atlassian services.",
    responses={
        200: {"description": "OAuth flow initialized successfully"},
        400: {"model": ErrorResponse, "description": "Invalid request data"},
        500: {"model": ErrorResponse, "description": "Internal server error"}
    }
)
def init_oauth_flow(request: OAuthInitRequest):
    """
    Initialize OAuth 2.0 authorization flow.
    
    Args:
        request: OAuth initialization request
        
    Returns:
        OAuthInitResponse: Authorization URL and state parameter
    """
    try:
        response = oauth_service.initiate_oauth_flow(request)
        return response
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ErrorResponse(
                error="oauth_init_failed",
                message=str(e),
                details={"service_type": request.service_type.value}
            ).dict()
        )
    except Exception as e:
        logger.error(f"OAuth initialization failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ErrorResponse(
                error="oauth_init_failed",
                message="Failed to initialize OAuth flow"
            ).dict()
        )


# PUBLIC_INTERFACE
@app.post(
    "/auth/oauth/callback",
    response_model=ConnectionResponse,
    tags=["oauth"],
    summary="Handle OAuth Callback",
    description="Handle OAuth callback and complete authentication flow.",
    responses={
        200: {"description": "OAuth authentication completed successfully"},
        400: {"model": ErrorResponse, "description": "Invalid callback data"},
        500: {"model": ErrorResponse, "description": "Internal server error"}
    }
)
def handle_oauth_callback(request: OAuthCallbackRequest):
    """
    Handle OAuth callback and complete authentication.
    
    Args:
        request: OAuth callback request with code and state
        
    Returns:
        ConnectionResponse: Authentication result and connection status
    """
    try:
        # Handle OAuth callback
        token_response, service_type = oauth_service.handle_oauth_callback(
            request.code, request.state
        )
        
        # Test the connection
        connection_status, message = oauth_service.test_oauth_connection(service_type)
        
        # Create session if connection successful
        if connection_status == ConnectionStatus.CONNECTED:
            # Get user info for session
            tokens = oauth_service.get_oauth_tokens(service_type)
            user_info = tokens.get("user_info", {}) if tokens else {}
            session_service.create_session(service_type, user_info)
        
        return ConnectionResponse(
            service_type=service_type,
            status=connection_status,
            message=f"OAuth authentication completed. {message}",
            base_url=None,  # OAuth doesn't use a single base URL
            username=None,  # Will be in user_info
            connected_at=datetime.utcnow() if connection_status == ConnectionStatus.CONNECTED else None
        )
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ErrorResponse(
                error="oauth_callback_failed",
                message=str(e)
            ).dict()
        )
    except Exception as e:
        logger.error(f"OAuth callback failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ErrorResponse(
                error="oauth_callback_failed",
                message="OAuth callback processing failed"
            ).dict()
        )


# PUBLIC_INTERFACE
@app.get(
    "/auth/oauth/status",
    tags=["oauth"],
    summary="Get OAuth Status",
    description="Get OAuth authentication status for all services.",
)
def get_oauth_status():
    """
    Get OAuth authentication status for all services.
    
    Returns:
        List of OAuth connection statuses
    """
    try:
        connections = oauth_service.list_oauth_connections()
        return {"oauth_connections": connections}
        
    except Exception as e:
        logger.error(f"Failed to get OAuth status: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ErrorResponse(
                error="oauth_status_failed",
                message="Failed to get OAuth status"
            ).dict()
        )


# PUBLIC_INTERFACE
@app.delete(
    "/auth/oauth/{service_type}",
    tags=["oauth"],
    summary="Revoke OAuth Tokens",
    description="Revoke OAuth tokens for a service."
)
def revoke_oauth_tokens(service_type: ServiceType):
    """
    Revoke OAuth tokens for a service.
    
    Args:
        service_type: Type of service to revoke tokens for
        
    Returns:
        Success message
    """
    try:
        success = oauth_service.revoke_oauth_tokens(service_type)
        
        if success:
            return {
                "message": f"Successfully revoked OAuth tokens for {service_type.value}"
            }
        else:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=ErrorResponse(
                    error="no_oauth_tokens",
                    message=f"No OAuth tokens found for {service_type.value}"
                ).dict()
            )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to revoke OAuth tokens: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ErrorResponse(
                error="oauth_revoke_failed",
                message="Failed to revoke OAuth tokens"
            ).dict()
        )


# Session Management Endpoints

# PUBLIC_INTERFACE
@app.get(
    "/sessions/active",
    tags=["sessions"],
    summary="Get Active Sessions",
    description="Get all active user sessions."
)
def get_active_sessions():
    """
    Get all active user sessions.
    
    Returns:
        List of active sessions
    """
    try:
        sessions = session_service.get_active_sessions()
        return {
            "active_sessions": [
                {
                    "session_id": session_id,
                    "service_type": session.service_type.value,
                    "user_info": session.user_info,
                    "created_at": session.created_at.isoformat(),
                    "expires_at": session.expires_at.isoformat() if session.expires_at else None
                }
                for session_id, session in sessions.items()
            ],
            "total_count": len(sessions)
        }
        
    except Exception as e:
        logger.error(f"Failed to get active sessions: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ErrorResponse(
                error="session_fetch_failed",
                message="Failed to get active sessions"
            ).dict()
        )


# PUBLIC_INTERFACE
@app.delete(
    "/sessions/{session_id}",
    tags=["sessions"],
    summary="Invalidate Session",
    description="Invalidate a specific session."
)
def invalidate_session(session_id: str):
    """
    Invalidate a specific session.
    
    Args:
        session_id: Session ID to invalidate
        
    Returns:
        Success message
    """
    try:
        success = session_service.invalidate_session(session_id)
        
        if success:
            return {"message": f"Session {session_id} invalidated successfully"}
        else:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=ErrorResponse(
                    error="session_not_found",
                    message=f"Session {session_id} not found"
                ).dict()
            )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to invalidate session: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ErrorResponse(
                error="session_invalidation_failed",
                message="Failed to invalidate session"
            ).dict()
        )


# PUBLIC_INTERFACE
@app.post(
    "/sessions/cleanup",
    tags=["sessions"],
    summary="Cleanup Expired Sessions",
    description="Remove all expired sessions."
)
def cleanup_expired_sessions():
    """
    Remove all expired sessions.
    
    Returns:
        Cleanup result
    """
    try:
        session_service.cleanup_expired_sessions()
        return {"message": "Expired sessions cleaned up successfully"}
        
    except Exception as e:
        logger.error(f"Failed to cleanup sessions: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ErrorResponse(
                error="session_cleanup_failed",
                message="Failed to cleanup expired sessions"
            ).dict()
        )


# Startup event
@app.on_event("startup")
async def startup_event():
    """Initialize application on startup."""
    logger.info("Starting JIRA/Confluence Connector Backend")
    logger.info("API documentation available at: /docs")
    logger.info("Running in %s mode", 'DEBUG' if settings.debug else 'PRODUCTION')


# Shutdown event  
@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on application shutdown."""
    logger.info("Shutting down JIRA/Confluence Connector Backend")
