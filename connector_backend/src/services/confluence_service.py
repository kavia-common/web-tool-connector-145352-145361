"""
Confluence integration service for authentication and space data retrieval.
"""
import requests
from typing import List, Dict, Any, Optional, Tuple
import base64
from urllib.parse import urljoin
import logging

from src.models import ProjectData, ConnectionStatus
from src.services.credential_service import credential_service

logger = logging.getLogger(__name__)


class ConfluenceService:
    """Service for Confluence API integration."""
    
    def __init__(self):
        self.timeout = 30
        self.session = requests.Session()
    
    def _get_auth_headers(self, credentials: Dict[str, str]) -> Dict[str, str]:
        """Generate authentication headers based on auth method."""
        auth_method = credentials.get("auth_method", "basic")
        username = credentials["username"]
        password = credentials["password"]
        
        if auth_method == "api_token":
            # For API token, use email:token as basic auth
            auth_string = f"{username}:{password}"
            encoded_auth = base64.b64encode(auth_string.encode()).decode()
            return {
                "Authorization": f"Basic {encoded_auth}",
                "Content-Type": "application/json",
                "Accept": "application/json"
            }
        else:
            # Basic authentication
            auth_string = f"{username}:{password}"
            encoded_auth = base64.b64encode(auth_string.encode()).decode()
            return {
                "Authorization": f"Basic {encoded_auth}",
                "Content-Type": "application/json",
                "Accept": "application/json"
            }
    
    def test_connection(self, base_url: str) -> Tuple[ConnectionStatus, str]:
        """Test connection to Confluence instance."""
        try:
            # Get stored credentials
            credentials = credential_service.get_decrypted_credentials("confluence", base_url)
            if not credentials:
                return ConnectionStatus.ERROR, "No credentials found for this Confluence instance"
            
            # Test connection with user info API call
            url = urljoin(base_url, "/rest/api/user/current")
            headers = self._get_auth_headers(credentials)
            
            response = self.session.get(url, headers=headers, timeout=self.timeout)
            
            if response.status_code == 200:
                credential_service.update_last_tested("confluence", base_url)
                user_info = response.json()
                return ConnectionStatus.CONNECTED, f"Connected as {user_info.get('displayName', 'Unknown User')}"
            elif response.status_code == 401:
                return ConnectionStatus.ERROR, "Authentication failed - invalid credentials"
            elif response.status_code == 403:
                return ConnectionStatus.ERROR, "Access forbidden - check permissions"
            else:
                return ConnectionStatus.ERROR, f"Connection failed with status {response.status_code}"
                
        except requests.exceptions.Timeout:
            return ConnectionStatus.ERROR, "Connection timeout - server not responding"
        except requests.exceptions.ConnectionError:
            return ConnectionStatus.ERROR, "Cannot connect to Confluence instance - check URL"
        except Exception as e:
            logger.error(f"Confluence connection test failed: {str(e)}")
            return ConnectionStatus.ERROR, f"Connection test failed: {str(e)}"
    
    def get_spaces(self, base_url: str) -> Tuple[List[ProjectData], Optional[str]]:
        """Fetch spaces from Confluence instance (treating spaces as 'projects')."""
        try:
            # Get stored credentials
            credentials = credential_service.get_decrypted_credentials("confluence", base_url)
            if not credentials:
                return [], "No credentials found for this Confluence instance"
            
            # Fetch spaces
            url = urljoin(base_url, "/rest/api/space")
            headers = self._get_auth_headers(credentials)
            params = {
                "expand": "description.plain,icon,homepage",
                "limit": 200
            }
            
            response = self.session.get(url, headers=headers, params=params, timeout=self.timeout)
            
            if response.status_code == 200:
                spaces_data = response.json()
                spaces = []
                
                for space in spaces_data.get("results", []):
                    space_data = ProjectData(
                        id=str(space.get("id", "")),
                        key=space.get("key", ""),
                        name=space.get("name", ""),
                        description=space.get("description", {}).get("plain", "") if space.get("description") else "",
                        project_type="confluence_space",
                        url=urljoin(base_url, f"/spaces/{space.get('key', '')}"),
                        avatar_url=space.get("icon", {}).get("path") if space.get("icon") else None,
                        lead=None  # Confluence spaces don't have a direct "lead" concept
                    )
                    spaces.append(space_data)
                
                return spaces, None
            elif response.status_code == 401:
                return [], "Authentication failed - invalid credentials"
            elif response.status_code == 403:
                return [], "Access forbidden - insufficient permissions"
            else:
                return [], f"Failed to fetch spaces: HTTP {response.status_code}"
                
        except requests.exceptions.Timeout:
            return [], "Request timeout - server not responding"
        except requests.exceptions.ConnectionError:
            return [], "Cannot connect to Confluence instance"
        except Exception as e:
            logger.error(f"Failed to fetch Confluence spaces: {str(e)}")
            return [], f"Failed to fetch spaces: {str(e)}"
    
    def get_space_details(self, base_url: str, space_key: str) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
        """Get detailed information about a specific space."""
        try:
            credentials = credential_service.get_decrypted_credentials("confluence", base_url)
            if not credentials:
                return None, "No credentials found for this Confluence instance"
            
            url = urljoin(base_url, f"/rest/api/space/{space_key}")
            headers = self._get_auth_headers(credentials)
            params = {
                "expand": "description.plain,icon,homepage,permissions"
            }
            
            response = self.session.get(url, headers=headers, params=params, timeout=self.timeout)
            
            if response.status_code == 200:
                return response.json(), None
            elif response.status_code == 404:
                return None, f"Space '{space_key}' not found"
            elif response.status_code == 401:
                return None, "Authentication failed"
            elif response.status_code == 403:
                return None, "Access forbidden"
            else:
                return None, f"Failed to fetch space details: HTTP {response.status_code}"
                
        except Exception as e:
            logger.error(f"Failed to fetch Confluence space details: {str(e)}")
            return None, f"Failed to fetch space details: {str(e)}"


# Global Confluence service instance
confluence_service = ConfluenceService()
