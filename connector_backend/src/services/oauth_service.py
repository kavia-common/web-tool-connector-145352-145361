"""
OAuth 2.0 service for Atlassian (JIRA/Confluence) authentication.
Implements OAuth 2.0 Authorization Code Grant (3LO) flow.
"""
import secrets
import requests
from datetime import datetime, timedelta
from typing import Dict, Optional, List, Tuple, Any
from urllib.parse import urlencode, urljoin
import logging
import threading

from src.config import settings
from src.models import (
    ServiceType, OAuthTokenResponse, StoredOAuthTokens, 
    ConnectionStatus, OAuthInitRequest, OAuthInitResponse
)
from src.security import encrypt_credential, decrypt_credential

logger = logging.getLogger(__name__)


class OAuthService:
    """Service for handling OAuth 2.0 flows with Atlassian."""
    
    def __init__(self):
        self.timeout = 30
        self.session = requests.Session()
        self._oauth_tokens: Dict[str, StoredOAuthTokens] = {}
        self._oauth_states: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()
    
    def _get_client_credentials(self, service_type: ServiceType) -> Tuple[str, str]:
        """Get OAuth client credentials for a service type."""
        # Use main Atlassian app credentials or service-specific ones
        if service_type == ServiceType.JIRA:
            client_id = settings.jira_client_id or settings.atlassian_client_id
            client_secret = settings.jira_client_secret or settings.atlassian_client_secret
        elif service_type == ServiceType.CONFLUENCE:
            client_id = settings.confluence_client_id or settings.atlassian_client_id
            client_secret = settings.confluence_client_secret or settings.atlassian_client_secret
        else:
            client_id = settings.atlassian_client_id
            client_secret = settings.atlassian_client_secret
        
        if not client_id or not client_secret:
            raise ValueError(f"OAuth credentials not configured for {service_type.value}")
        
        return client_id, client_secret
    
    def initiate_oauth_flow(self, request: OAuthInitRequest) -> OAuthInitResponse:
        """Initiate OAuth 2.0 authorization flow."""
        try:
            client_id, _ = self._get_client_credentials(request.service_type)
            
            # Generate state for CSRF protection
            state = request.state or secrets.token_urlsafe(32)
            
            # Store state and service type for later verification
            with self._lock:
                self._oauth_states[state] = {
                    "service_type": request.service_type.value,
                    "created_at": datetime.utcnow(),
                    "expires_at": datetime.utcnow() + timedelta(minutes=10)
                }
            
            # Build authorization URL
            auth_params = {
                "audience": "api.atlassian.com",
                "client_id": client_id,
                "scope": "read:jira-user read:jira-work offline_access read:confluence-user read:confluence-space.summary",
                "redirect_uri": settings.redirect_uri,
                "state": state,
                "response_type": "code",
                "prompt": "consent"
            }
            
            auth_url = f"{settings.atlassian_auth_url}?{urlencode(auth_params)}"
            
            return OAuthInitResponse(auth_url=auth_url, state=state)
            
        except Exception as e:
            logger.error(f"Failed to initiate OAuth flow: {str(e)}")
            raise
    
    def handle_oauth_callback(self, code: str, state: str) -> Tuple[OAuthTokenResponse, ServiceType]:
        """Handle OAuth callback and exchange code for tokens."""
        try:
            # Verify state
            with self._lock:
                if state not in self._oauth_states:
                    raise ValueError("Invalid or expired OAuth state")
                
                state_info = self._oauth_states[state]
                if datetime.utcnow() > state_info["expires_at"]:
                    del self._oauth_states[state]
                    raise ValueError("OAuth state has expired")
                
                service_type = ServiceType(state_info["service_type"])
                del self._oauth_states[state]
            
            # Get client credentials
            client_id, client_secret = self._get_client_credentials(service_type)
            
            # Exchange code for tokens
            token_data = {
                "grant_type": "authorization_code",
                "client_id": client_id,
                "client_secret": client_secret,
                "code": code,
                "redirect_uri": settings.redirect_uri
            }
            
            response = self.session.post(
                settings.atlassian_token_url,
                data=token_data,
                timeout=self.timeout
            )
            
            if response.status_code != 200:
                logger.error(f"Token exchange failed: {response.text}")
                raise ValueError(f"Token exchange failed: {response.status_code}")
            
            token_response = response.json()
            oauth_token_response = OAuthTokenResponse(**token_response)
            
            # Store tokens
            self._store_oauth_tokens(service_type, oauth_token_response)
            
            return oauth_token_response, service_type
            
        except Exception as e:
            logger.error(f"OAuth callback failed: {str(e)}")
            raise
    
    def _store_oauth_tokens(self, service_type: ServiceType, token_response: OAuthTokenResponse):
        """Store OAuth tokens securely."""
        with self._lock:
            # Calculate expiration
            expires_at = None
            if token_response.expires_in:
                expires_at = datetime.utcnow() + timedelta(seconds=token_response.expires_in)
            
            # Encrypt tokens
            encrypted_access_token = encrypt_credential(token_response.access_token)
            encrypted_refresh_token = None
            if token_response.refresh_token:
                encrypted_refresh_token = encrypt_credential(token_response.refresh_token)
            
            stored_tokens = StoredOAuthTokens(
                service_type=service_type,
                access_token=encrypted_access_token,
                refresh_token=encrypted_refresh_token,
                expires_at=expires_at,
                scope=token_response.scope,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
                is_active=True
            )
            
            # Store with service type as key
            self._oauth_tokens[service_type.value] = stored_tokens
    
    def get_oauth_tokens(self, service_type: ServiceType) -> Optional[Dict[str, Any]]:
        """Get decrypted OAuth tokens for a service."""
        with self._lock:
            stored_tokens = self._oauth_tokens.get(service_type.value)
            if not stored_tokens or not stored_tokens.is_active:
                return None
            
            try:
                access_token = decrypt_credential(stored_tokens.access_token)
                refresh_token = None
                if stored_tokens.refresh_token:
                    refresh_token = decrypt_credential(stored_tokens.refresh_token)
                
                return {
                    "access_token": access_token,
                    "refresh_token": refresh_token,
                    "expires_at": stored_tokens.expires_at,
                    "scope": stored_tokens.scope,
                    "accessible_resources": stored_tokens.accessible_resources,
                    "user_info": stored_tokens.user_info
                }
            except Exception as e:
                logger.error(f"Failed to decrypt OAuth tokens: {str(e)}")
                return None
    
    def refresh_token(self, service_type: ServiceType) -> Optional[OAuthTokenResponse]:
        """Refresh OAuth access token using refresh token."""
        try:
            tokens = self.get_oauth_tokens(service_type)
            if not tokens or not tokens.get("refresh_token"):
                return None
            
            client_id, client_secret = self._get_client_credentials(service_type)
            
            refresh_data = {
                "grant_type": "refresh_token",
                "client_id": client_id,
                "client_secret": client_secret,
                "refresh_token": tokens["refresh_token"]
            }
            
            response = self.session.post(
                settings.atlassian_token_url,
                data=refresh_data,
                timeout=self.timeout
            )
            
            if response.status_code == 200:
                token_response = OAuthTokenResponse(**response.json())
                self._store_oauth_tokens(service_type, token_response)
                return token_response
            else:
                logger.error(f"Token refresh failed: {response.text}")
                return None
                
        except Exception as e:
            logger.error(f"Token refresh failed: {str(e)}")
            return None
    
    def get_accessible_resources(self, service_type: ServiceType) -> Tuple[List[Dict[str, Any]], Optional[str]]:
        """Get accessible resources (sites) for the authenticated user."""
        try:
            tokens = self.get_oauth_tokens(service_type)
            if not tokens:
                return [], "No OAuth tokens found"
            
            # Check if token is expired and try to refresh
            if tokens.get("expires_at") and datetime.utcnow() >= tokens["expires_at"]:
                refreshed = self.refresh_token(service_type)
                if refreshed:
                    tokens = self.get_oauth_tokens(service_type)
                else:
                    return [], "OAuth token expired and refresh failed"
            
            headers = {
                "Authorization": f"Bearer {tokens['access_token']}",
                "Accept": "application/json"
            }
            
            response = self.session.get(
                f"{settings.atlassian_api_url}/oauth/token/accessible-resources",
                headers=headers,
                timeout=self.timeout
            )
            
            if response.status_code == 200:
                resources = response.json()
                
                # Update stored tokens with accessible resources
                with self._lock:
                    if service_type.value in self._oauth_tokens:
                        self._oauth_tokens[service_type.value].accessible_resources = resources
                        self._oauth_tokens[service_type.value].updated_at = datetime.utcnow()
                
                return resources, None
            else:
                return [], f"Failed to fetch accessible resources: {response.status_code}"
                
        except Exception as e:
            logger.error(f"Failed to get accessible resources: {str(e)}")
            return [], f"Failed to get accessible resources: {str(e)}"
    
    def test_oauth_connection(self, service_type: ServiceType) -> Tuple[ConnectionStatus, str]:
        """Test OAuth connection by fetching user info."""
        try:
            resources, error = self.get_accessible_resources(service_type)
            if error:
                return ConnectionStatus.ERROR, error
            
            if not resources:
                return ConnectionStatus.ERROR, "No accessible resources found"
            
            # Try to get user info from the first accessible resource
            tokens = self.get_oauth_tokens(service_type)
            if not tokens:
                return ConnectionStatus.ERROR, "No OAuth tokens found"
            
            # Use the first accessible resource
            resource = resources[0]
            base_url = resource.get("url")
            
            if service_type == ServiceType.JIRA:
                url = urljoin(base_url, "/rest/api/3/myself")
            else:  # Confluence
                url = urljoin(base_url, "/rest/api/user/current")
            
            headers = {
                "Authorization": f"Bearer {tokens['access_token']}",
                "Accept": "application/json"
            }
            
            response = self.session.get(url, headers=headers, timeout=self.timeout)
            
            if response.status_code == 200:
                user_info = response.json()
                
                # Store user info
                with self._lock:
                    if service_type.value in self._oauth_tokens:
                        self._oauth_tokens[service_type.value].user_info = user_info
                        self._oauth_tokens[service_type.value].updated_at = datetime.utcnow()
                
                return ConnectionStatus.CONNECTED, f"Connected as {user_info.get('displayName', 'Unknown User')}"
            else:
                return ConnectionStatus.ERROR, f"Authentication failed: {response.status_code}"
                
        except Exception as e:
            logger.error(f"OAuth connection test failed: {str(e)}")
            return ConnectionStatus.ERROR, f"Connection test failed: {str(e)}"
    
    def revoke_oauth_tokens(self, service_type: ServiceType) -> bool:
        """Revoke and delete OAuth tokens."""
        try:
            with self._lock:
                if service_type.value in self._oauth_tokens:
                    del self._oauth_tokens[service_type.value]
                    return True
                return False
        except Exception as e:
            logger.error(f"Failed to revoke OAuth tokens: {str(e)}")
            return False
    
    def list_oauth_connections(self) -> List[Dict[str, Any]]:
        """List all active OAuth connections."""
        with self._lock:
            connections = []
            for service_type, tokens in self._oauth_tokens.items():
                if tokens.is_active:
                    connections.append({
                        "service_type": service_type,
                        "auth_method": "oauth",
                        "user_info": tokens.user_info,
                        "accessible_resources": tokens.accessible_resources,
                        "expires_at": tokens.expires_at.isoformat() if tokens.expires_at else None,
                        "created_at": tokens.created_at.isoformat(),
                        "scope": tokens.scope
                    })
            return connections


# Global OAuth service instance
oauth_service = OAuthService()
