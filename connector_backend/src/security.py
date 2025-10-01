"""
Security utilities for credential encryption and token management.
"""
import secrets
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from passlib.context import CryptContext
from jose import JWTError, jwt
from cryptography.fernet import Fernet
import base64

from src.config import settings


# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Encryption for storing credentials
def get_encryption_key() -> bytes:
    """Get or generate encryption key for credentials."""
    # In production, this should be stored securely
    key_str = settings.secret_key + "credential_encryption"
    # Create a 32-byte key for Fernet
    key = base64.urlsafe_b64encode(key_str.encode()[:32].ljust(32, b'0'))
    return key


def encrypt_credential(credential: str) -> str:
    """Encrypt a credential string."""
    f = Fernet(get_encryption_key())
    encrypted = f.encrypt(credential.encode())
    return base64.urlsafe_b64encode(encrypted).decode()


def decrypt_credential(encrypted_credential: str) -> str:
    """Decrypt a credential string."""
    f = Fernet(get_encryption_key())
    encrypted_bytes = base64.urlsafe_b64decode(encrypted_credential.encode())
    decrypted = f.decrypt(encrypted_bytes)
    return decrypted.decode()


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash."""
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """Hash a password."""
    return pwd_context.hash(password)


def create_access_token(data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    """Create a JWT access token."""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=settings.access_token_expire_minutes)
    
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.secret_key, algorithm=settings.algorithm)
    return encoded_jwt


def verify_token(token: str) -> Optional[Dict[str, Any]]:
    """Verify and decode a JWT token."""
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
        return payload
    except JWTError:
        return None


def generate_session_id() -> str:
    """Generate a secure session ID."""
    return secrets.token_urlsafe(32)
