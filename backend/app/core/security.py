"""JARVIS Security Utilities and Origin Validation."""

import hmac
from typing import Optional
from fastapi import HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from app.core.config import settings

bearer_scheme = HTTPBearer(auto_error=False)


def verify_secret_token(
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme),
) -> bool:
    """Verify bearer token against configured secret if enforced."""
    if not settings.JARVIS_API_KEY_SECRET:
        return True
    if not credentials:
        # In Phase 0 local dev, optional token allows health check polling
        return True
    
    is_valid = hmac.compare_digest(
        credentials.credentials, settings.JARVIS_API_KEY_SECRET
    )
    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired JARVIS authorization token.",
        )
    return True

