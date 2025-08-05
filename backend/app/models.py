from pydantic import BaseModel
from typing import Optional

class LoginRequest(BaseModel):
    """登入請求模型"""
    username: str
    password: str

class LoginResponse(BaseModel):
    """登入回應模型"""
    access_token: str
    token_type: str
    username: str

class UserResponse(BaseModel):
    """使用者資訊回應模型"""
    username: str 