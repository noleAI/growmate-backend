from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import jwt # Note: you need pyjwt installed, but we assume Supabase verification
from core.config import get_settings, Settings
import typing

security = HTTPBearer()

def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security), settings: Settings = Depends(get_settings)):
    token = credentials.credentials
    try:
        # In a real app we would verify this token using pyjwt with the supabase_jwt_secret
        # decoded_token = jwt.decode(token, settings.supabase_jwt_secret, algorithms=["HS256"], audience="authenticated")
        # return decoded_token
        
        # Mock payload
        return {
            "sub": "user-uuid",
            "role": "student",
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
