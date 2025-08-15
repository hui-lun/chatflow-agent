from pydantic import BaseModel, Field
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
class RAGIndexRequest(BaseModel):
    """Request model for RAG index endpoint."""
    collection: str = Field(..., min_length=1, max_length=255, description="Name of the collection to index into")
    user_id: str = Field(..., min_length=1, max_length=255, description="ID of the user who owns these documents")
    chunk_size: int = Field(1000, gt=100, le=10000, description="Size of text chunks")
    chunk_overlap: int = Field(200, ge=0, le=1000, description="Overlap between chunks")


class RAGIndexResponse(BaseModel):
    """Response model for RAG index endpoint."""
    collection: str
    user_id: str
    chunks_indexed: int
    points_upserted: int
    documents_processed: Optional[int] = None


class RetrievedDoc(BaseModel):
    """Model for a single retrieved document with metadata and score."""
    text: str
    metadata: Dict[str, Any]
    score: float


class RAGQueryRequest(BaseModel):
    """Request model for RAG query endpoint."""
    message: str = Field(..., description="The query message to search for")
    collection: str = Field(..., min_length=1, max_length=255, description="Name of the collection to search in")
    user_id: str = Field(..., min_length=1, max_length=255, description="ID of the user making the query")
    limit: int = Field(5, gt=0, le=20, description="Maximum number of documents to retrieve")


class RAGQueryResponse(BaseModel):
    """Response model for RAG query endpoint."""
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