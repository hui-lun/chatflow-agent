from pydantic import BaseModel
from typing import Optional, List, Dict, Any

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

# 聊天相關模型
class ChatRequest(BaseModel):
    """
    Request model for chat endpoint.
    """
    message: str
    session_id: Optional[str] = None

class ChatResponse(BaseModel):
    """
    Response model for chat endpoint.
    """
    response: str
    session_id: str

class ChatHistoryItem(BaseModel):
    """
    Model for chat history item.
    """
    user_message: str
    bot_response: str
    timestamp: str
    session_id: str
    username: str

class ChatHistoryResponse(BaseModel):
    """
    Response model for chat history endpoint.
    """
    history: List[ChatHistoryItem]

class SessionsResponse(BaseModel):
    """
    Response model for sessions endpoint.
    """
    sessions: List[str]

# ===== RAG Models =====
class RAGIndexResponse(BaseModel):
    collection: str
    user_id: str
    chunks_indexed: int
    points_upserted: int

class RetrievedDoc(BaseModel):
    text: str
    metadata: Dict[str, Any]
    score: float

class RAGQueryRequest(BaseModel):
    message: str
    collection: str
    user_id: str
    limit: int = 5

class RAGQueryResponse(BaseModel):
    response: str
    retrieved_docs: List[RetrievedDoc]

class WebSearchRequest(BaseModel):
    """
    Request model for web search chat endpoint.
    """
    message: str
    session_id: Optional[str] = None

class WebSearchResponse(BaseModel):
    """
    Response model for web search chat endpoint.
    """
    response: str
    session_id: str
    search_sources: Optional[List[str]] = None 