"""
Session management service for handling user sessions and authentication state.
"""
import threading
from datetime import datetime, timedelta
from typing import Dict, Optional, Any
import logging

from src.models import SessionInfo, ServiceType
from src.security import generate_session_id

logger = logging.getLogger(__name__)


class SessionService:
    """In-memory session management service."""
    
    def __init__(self):
        self._sessions: Dict[str, SessionInfo] = {}
        self._lock = threading.Lock()
        self.default_session_duration = timedelta(hours=24)
    
    def create_session(self, service_type: ServiceType, user_info: Dict[str, Any], 
                      duration: Optional[timedelta] = None) -> str:
        """Create a new user session."""
        with self._lock:
            session_id = generate_session_id()
            expires_at = datetime.utcnow() + (duration or self.default_session_duration)
            
            session = SessionInfo(
                session_id=session_id,
                service_type=service_type,
                user_info=user_info,
                created_at=datetime.utcnow(),
                expires_at=expires_at
            )
            
            self._sessions[session_id] = session
            logger.info(f"Created session {session_id} for {service_type.value}")
            return session_id
    
    def get_session(self, session_id: str) -> Optional[SessionInfo]:
        """Get session information by ID."""
        with self._lock:
            session = self._sessions.get(session_id)
            if not session:
                return None
            
            # Check if session is expired
            if session.expires_at and datetime.utcnow() > session.expires_at:
                del self._sessions[session_id]
                logger.info(f"Removed expired session {session_id}")
                return None
            
            return session
    
    def extend_session(self, session_id: str, duration: Optional[timedelta] = None) -> bool:
        """Extend session expiration time."""
        with self._lock:
            session = self._sessions.get(session_id)
            if not session:
                return False
            
            new_expires_at = datetime.utcnow() + (duration or self.default_session_duration)
            session.expires_at = new_expires_at
            logger.info(f"Extended session {session_id}")
            return True
    
    def invalidate_session(self, session_id: str) -> bool:
        """Invalidate and remove a session."""
        with self._lock:
            if session_id in self._sessions:
                del self._sessions[session_id]
                logger.info(f"Invalidated session {session_id}")
                return True
            return False
    
    def cleanup_expired_sessions(self):
        """Remove all expired sessions."""
        with self._lock:
            current_time = datetime.utcnow()
            expired_sessions = [
                session_id for session_id, session in self._sessions.items()
                if session.expires_at and current_time > session.expires_at
            ]
            
            for session_id in expired_sessions:
                del self._sessions[session_id]
                logger.info(f"Cleaned up expired session {session_id}")
            
            if expired_sessions:
                logger.info(f"Cleaned up {len(expired_sessions)} expired sessions")
    
    def get_active_sessions(self) -> Dict[str, SessionInfo]:
        """Get all active sessions."""
        with self._lock:
            # Clean up expired sessions first
            self.cleanup_expired_sessions()
            return self._sessions.copy()
    
    def get_sessions_by_service(self, service_type: ServiceType) -> Dict[str, SessionInfo]:
        """Get all active sessions for a specific service type."""
        with self._lock:
            self.cleanup_expired_sessions()
            return {
                session_id: session for session_id, session in self._sessions.items()
                if session.service_type == service_type
            }


# Global session service instance
session_service = SessionService()
