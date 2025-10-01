"""
Service for managing credentials and connections.
In production, this should use a proper database or secure storage.
"""
from datetime import datetime
from typing import Dict, Optional, List
import threading
from src.models import (
    ServiceType, StoredCredentials, 
    CredentialsRequest
)
from src.security import encrypt_credential, decrypt_credential


class CredentialService:
    """In-memory credential storage service."""
    
    def __init__(self):
        self._credentials: Dict[str, StoredCredentials] = {}
        self._lock = threading.Lock()
    
    def _get_key(self, service_type: ServiceType, base_url: str) -> str:
        """Generate a unique key for storing credentials."""
        return f"{service_type.value}:{base_url}"
    
    def store_credentials(self, request: CredentialsRequest) -> StoredCredentials:
        """Store encrypted credentials."""
        with self._lock:
            key = self._get_key(request.service_type, str(request.base_url))
            
            # Encrypt the password/token
            encrypted_password = encrypt_credential(request.password)
            
            # Create stored credentials
            stored_creds = StoredCredentials(
                service_type=request.service_type,
                base_url=str(request.base_url),
                auth_method=request.auth_method,
                username=request.username,
                encrypted_password=encrypted_password,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
                is_active=True
            )
            
            self._credentials[key] = stored_creds
            return stored_creds
    
    def get_credentials(self, service_type: ServiceType, base_url: str) -> Optional[StoredCredentials]:
        """Retrieve stored credentials."""
        with self._lock:
            key = self._get_key(service_type, base_url)
            return self._credentials.get(key)
    
    def get_decrypted_credentials(self, service_type: ServiceType, base_url: str) -> Optional[Dict[str, str]]:
        """Get credentials with decrypted password."""
        stored_creds = self.get_credentials(service_type, base_url)
        if not stored_creds or not stored_creds.is_active:
            return None
        
        try:
            decrypted_password = decrypt_credential(stored_creds.encrypted_password)
            return {
                "username": stored_creds.username,
                "password": decrypted_password,
                "base_url": stored_creds.base_url,
                "auth_method": stored_creds.auth_method.value
            }
        except Exception:
            return None
    
    def update_last_tested(self, service_type: ServiceType, base_url: str) -> bool:
        """Update the last tested timestamp."""
        with self._lock:
            key = self._get_key(service_type, base_url)
            if key in self._credentials:
                self._credentials[key].last_tested_at = datetime.utcnow()
                return True
            return False
    
    def delete_credentials(self, service_type: ServiceType, base_url: str) -> bool:
        """Delete stored credentials."""
        with self._lock:
            key = self._get_key(service_type, base_url)
            if key in self._credentials:
                del self._credentials[key]
                return True
            return False
    
    def list_stored_services(self) -> List[Dict[str, str]]:
        """List all stored service connections."""
        with self._lock:
            services = []
            for stored_creds in self._credentials.values():
                if stored_creds.is_active:
                    services.append({
                        "service_type": stored_creds.service_type.value,
                        "base_url": stored_creds.base_url,
                        "username": stored_creds.username,
                        "auth_method": stored_creds.auth_method.value,
                        "created_at": stored_creds.created_at.isoformat(),
                        "last_tested_at": stored_creds.last_tested_at.isoformat() if stored_creds.last_tested_at else None
                    })
            return services


# Global credential service instance
credential_service = CredentialService()
