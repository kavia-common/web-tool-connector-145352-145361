"""
JIRA integration service for authentication and project data retrieval.
"""
import requests
from typing import List, Dict, Any, Optional, Tuple
import base64
from urllib.parse import urljoin
import logging

from src.models import ProjectData, ConnectionStatus
from src.services.credential_service import credential_service

logger = logging.getLogger(__name__)


class JiraService:
    """Service for JIRA API integration."""
    
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
        """Test connection to JIRA instance."""
        try:
            # Get stored credentials
            credentials = credential_service.get_decrypted_credentials("jira", base_url)
            if not credentials:
                return ConnectionStatus.ERROR, "No credentials found for this JIRA instance"
            
            # Test connection with a simple API call
            url = urljoin(base_url, "/rest/api/3/myself")
            headers = self._get_auth_headers(credentials)
            
            response = self.session.get(url, headers=headers, timeout=self.timeout)
            
            if response.status_code == 200:
                credential_service.update_last_tested("jira", base_url)
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
            return ConnectionStatus.ERROR, "Cannot connect to JIRA instance - check URL"
        except Exception as e:
            logger.error(f"JIRA connection test failed: {str(e)}")
            return ConnectionStatus.ERROR, f"Connection test failed: {str(e)}"
    
    def get_projects(self, base_url: str) -> Tuple[List[ProjectData], Optional[str]]:
        """Fetch projects from JIRA instance."""
        try:
            # Get stored credentials
            credentials = credential_service.get_decrypted_credentials("jira", base_url)
            if not credentials:
                return [], "No credentials found for this JIRA instance"
            
            # Fetch projects
            url = urljoin(base_url, "/rest/api/3/project")
            headers = self._get_auth_headers(credentials)
            
            response = self.session.get(url, headers=headers, timeout=self.timeout)
            
            if response.status_code == 200:
                projects_data = response.json()
                projects = []
                
                for project in projects_data:
                    project_data = ProjectData(
                        id=str(project.get("id", "")),
                        key=project.get("key", ""),
                        name=project.get("name", ""),
                        description=project.get("description", ""),
                        project_type=project.get("projectTypeKey", ""),
                        url=urljoin(base_url, f"/browse/{project.get('key', '')}"),
                        avatar_url=project.get("avatarUrls", {}).get("48x48"),
                        lead={
                            "displayName": project.get("lead", {}).get("displayName", ""),
                            "emailAddress": project.get("lead", {}).get("emailAddress", "")
                        } if project.get("lead") else None
                    )
                    projects.append(project_data)
                
                return projects, None
            elif response.status_code == 401:
                return [], "Authentication failed - invalid credentials"
            elif response.status_code == 403:
                return [], "Access forbidden - insufficient permissions"
            else:
                return [], f"Failed to fetch projects: HTTP {response.status_code}"
                
        except requests.exceptions.Timeout:
            return [], "Request timeout - server not responding"
        except requests.exceptions.ConnectionError:
            return [], "Cannot connect to JIRA instance"
        except Exception as e:
            logger.error(f"Failed to fetch JIRA projects: {str(e)}")
            return [], f"Failed to fetch projects: {str(e)}"
    
    def get_project_details(self, base_url: str, project_key: str) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
        """Get detailed information about a specific project."""
        try:
            credentials = credential_service.get_decrypted_credentials("jira", base_url)
            if not credentials:
                return None, "No credentials found for this JIRA instance"
            
            url = urljoin(base_url, f"/rest/api/3/project/{project_key}")
            headers = self._get_auth_headers(credentials)
            
            response = self.session.get(url, headers=headers, timeout=self.timeout)
            
            if response.status_code == 200:
                return response.json(), None
            elif response.status_code == 404:
                return None, f"Project '{project_key}' not found"
            elif response.status_code == 401:
                return None, "Authentication failed"
            elif response.status_code == 403:
                return None, "Access forbidden"
            else:
                return None, f"Failed to fetch project details: HTTP {response.status_code}"
                
        except Exception as e:
            logger.error(f"Failed to fetch JIRA project details: {str(e)}")
            return None, f"Failed to fetch project details: {str(e)}"


# Global JIRA service instance
jira_service = JiraService()
