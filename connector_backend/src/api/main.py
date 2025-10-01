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
    ConnectionStatus
)
from src.services import credential_service, jira_service, confluence_service

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
    description="Test connection to a previously configured service.",
    responses={
        200: {"description": "Connection test completed"},
        404: {"model": ErrorResponse, "description": "No credentials found"},
        400: {"model": ErrorResponse, "description": "Invalid request data"}
    }
)
def test_connection(request: ConnectionTestRequest):
    """
    Test connection to a configured service.
    
    Args:
        request: Connection test request
        
    Returns:
        ConnectionResponse: Connection test results
    """
    try:
        # Get stored credentials to determine base URL
        stored_services = credential_service.list_stored_services()
        service_configs = [s for s in stored_services if s["service_type"] == request.service_type.value]
        
        if not service_configs:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=ErrorResponse(
                    error="no_credentials_found",
                    message=f"No stored credentials found for {request.service_type.value}",
                    details={"service_type": request.service_type.value}
                ).dict()
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
    description="Get connection status for all configured services."
)
def get_all_connections_status():
    """
    Get connection status for all stored services.
    
    Returns:
        List of connection status for each configured service
    """
    try:
        stored_services = credential_service.list_stored_services()
        connections = []
        
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
                message=message,
                base_url=base_url,
                username=service["username"],
                connected_at=datetime.utcnow() if connection_status == ConnectionStatus.CONNECTED else None
            ))
        
        return {"connections": connections}
        
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
    description="Fetch list of JIRA projects for authenticated user.",
    responses={
        200: {"description": "Projects retrieved successfully"},
        404: {"model": ErrorResponse, "description": "No JIRA credentials found"},
        401: {"model": ErrorResponse, "description": "Authentication failed"}
    }
)
def get_jira_projects():
    """
    Fetch JIRA projects for the authenticated user.
    
    Returns:
        ProjectsResponse: List of JIRA projects
    """
    try:
        # Get stored JIRA services
        stored_services = credential_service.list_stored_services()
        jira_configs = [s for s in stored_services if s["service_type"] == "jira"]
        
        if not jira_configs:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=ErrorResponse(
                    error="no_jira_credentials",
                    message="No JIRA credentials found. Please configure JIRA connection first.",
                    details={"service_type": "jira"}
                ).dict()
            )
        
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
    description="Fetch list of Confluence spaces for authenticated user.",
    responses={
        200: {"description": "Spaces retrieved successfully"},
        404: {"model": ErrorResponse, "description": "No Confluence credentials found"},
        401: {"model": ErrorResponse, "description": "Authentication failed"}
    }
)
def get_confluence_spaces():
    """
    Fetch Confluence spaces for the authenticated user.
    
    Returns:
        ProjectsResponse: List of Confluence spaces
    """
    try:
        # Get stored Confluence services
        stored_services = credential_service.list_stored_services()
        confluence_configs = [s for s in stored_services if s["service_type"] == "confluence"]
        
        if not confluence_configs:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=ErrorResponse(
                    error="no_confluence_credentials",
                    message="No Confluence credentials found. Please configure Confluence connection first.",
                    details={"service_type": "confluence"}
                ).dict()
            )
        
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
