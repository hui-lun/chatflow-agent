from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import HTTPException, status, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pymongo import MongoClient
import os

# JWT 設定
SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key-change-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

# 密碼雜湊設定
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# JWT Bearer 認證
security = HTTPBearer()

class AuthService:
    def __init__(self, db_client: MongoClient):
        self.db = db_client.internal_system
        self.users_collection = self.db.users
    
    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        """驗證密碼"""
        return pwd_context.verify(plain_password, hashed_password)
    
    def get_password_hash(self, password: str) -> str:
        """產生密碼雜湊"""
        return pwd_context.hash(password)
    
    def authenticate_user(self, username: str, password: str) -> Optional[dict]:
        """驗證使用者"""
        user = self.users_collection.find_one({"username": username})
        if not user:
            return None
        if not self.verify_password(password, user["hashed_password"]):
            return None
        return user
    
    def create_access_token(self, data: dict, expires_delta: Optional[timedelta] = None):
        """建立 JWT token"""
        to_encode = data.copy()
        if expires_delta:
            expire = datetime.utcnow() + expires_delta
        else:
            expire = datetime.utcnow() + timedelta(minutes=15)
        to_encode.update({"exp": expire})
        encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
        return encoded_jwt
    
    def verify_token(self, token: str) -> Optional[dict]:
        """驗證 JWT token"""
        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            username: str = payload.get("sub")
            if username is None:
                return None
            return {"username": username}
        except JWTError:
            return None

# 全域認證服務實例
_auth_service = None

def get_auth_service() -> AuthService:
    """取得認證服務實例"""
    global _auth_service
    if _auth_service is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Auth service not initialized"
        )
    return _auth_service

def set_auth_service(auth_service_instance: AuthService):
    """設定認證服務實例"""
    global _auth_service
    _auth_service = auth_service_instance

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> dict:
    """取得當前使用者"""
    token = credentials.credentials
    auth_service = get_auth_service()
    payload = auth_service.verify_token(token)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return payload 