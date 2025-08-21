from pydantic import BaseModel
from typing import Optional, List

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

# Knowledge Base相關模型
class FileUploadResponse(BaseModel):
    """檔案上傳回應模型"""
    file_id: str
    filename: str
    file_size: int
    status: str
    message: str

class FileInfo(BaseModel):
    """檔案資訊模型"""
    file_id: str
    filename: str
    file_size: int
    uploaded_at: str
    status: str
    chunks_count: Optional[int] = None

class FileListResponse(BaseModel):
    """檔案列表回應模型"""
    files: List[FileInfo]

class RAGChatRequest(BaseModel):
    """RAG聊天請求模型"""
    message: str
    session_id: Optional[str] = None

class RAGChatResponse(BaseModel):
    """RAG聊天回應模型"""
    response: str
    session_id: str
    retrieved_docs: Optional[List[dict]] = None

