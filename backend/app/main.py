from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
import logging
from .services.llm import get_llm
from .services.database import db_service
from .auth import AuthService, get_current_user, set_auth_service
from .models import LoginRequest, LoginResponse, UserResponse
from datetime import timedelta
import os

# 設置日誌
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create FastAPI app instance
app = FastAPI()

# 加入 CORS 中間件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://frontend:80", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 全域認證服務實例
auth_service = None

# 啟動時連接資料庫
@app.on_event("startup")
async def startup_event():
    """應用啟動時連接資料庫"""
    try:
        logger.info("Connecting to database...")
        db_service.connect()
        logger.info("Database connected successfully")
        
        # 初始化認證服務
        global auth_service
        auth_service = AuthService(db_service.client)
        set_auth_service(auth_service)
        logger.info("Auth service initialized")
    except Exception as e:
        logger.error(f"Failed to connect to database: {e}")
        # 不拋出異常，讓應用繼續運行

# 關閉時斷開資料庫連接
@app.on_event("shutdown")
async def shutdown_event():
    """應用關閉時斷開資料庫連接"""
    try:
        db_service.disconnect()
        logger.info("Database disconnected")
    except Exception as e:
        logger.error(f"Error disconnecting from database: {e}")

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

# 認證路由
@app.post("/auth/login", response_model=LoginResponse)
async def login(request: LoginRequest):
    """使用者登入"""
    try:
        if auth_service is None:
            raise HTTPException(status_code=500, detail="Auth service not initialized")
            
        user = auth_service.authenticate_user(request.username, request.password)
        if not user:
            raise HTTPException(
                status_code=401,
                detail="Incorrect username or password"
            )
        
        access_token_expires = timedelta(minutes=30)
        access_token = auth_service.create_access_token(
            data={"sub": user["username"]}, expires_delta=access_token_expires
        )
        
        return LoginResponse(
            access_token=access_token,
            token_type="bearer",
            username=user["username"]
        )
    except Exception as e:
        logger.error(f"Login error: {e}")
        raise HTTPException(status_code=500, detail="Login failed")

@app.get("/auth/me", response_model=UserResponse)
async def get_current_user_info(current_user: dict = Depends(get_current_user)):
    """取得當前使用者資訊"""
    return UserResponse(username=current_user["username"])

# 受保護的聊天路由
@app.post("/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest, current_user: dict = Depends(get_current_user)):
    """
    Receives a user message, sends it to the vLLM API, saves to database, and returns the response.
    """
    try:
        logger.info(f"Received chat request from {current_user['username']}: {request.message[:50]}...")
        
        llm = get_llm()
        # Send the message to the LLM and get the response
        result = llm.invoke(request.message)
        bot_response = result.content
        
        logger.info("LLM response received, saving to database...")
        
        # 儲存聊天記錄到資料庫
        session_id = request.session_id or "default"
        try:
            db_service.save_chat_message(
                user_message=request.message,
                bot_response=bot_response,
                session_id=session_id,
                username=current_user["username"]
            )
            logger.info("Chat message saved to database")
        except Exception as db_error:
            logger.error(f"Failed to save chat message: {db_error}")
            # 繼續執行，不因為資料庫錯誤而中斷聊天功能
        
        return ChatResponse(response=bot_response, session_id=session_id)
    except Exception as e:
        logger.error(f"Error in chat endpoint: {e}")
        # Return HTTP 500 if any error occurs
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/chat/history", response_model=ChatHistoryResponse)
async def get_chat_history(
    session_id: Optional[str] = None, 
    limit: int = 50,
    current_user: dict = Depends(get_current_user)
):
    """
    Get chat history for a specific session or all sessions.
    """
    try:
        logger.info(f"Getting chat history for user {current_user['username']}, session: {session_id}, limit: {limit}")
        history = db_service.get_chat_history(session_id=session_id, username=current_user["username"], limit=limit)
        
        # 轉換為 Pydantic 模型
        history_items = [
            ChatHistoryItem(
                user_message=item["user_message"],
                bot_response=item["bot_response"],
                timestamp=item["timestamp"].isoformat(),
                session_id=item["session_id"],
                username=item["username"]
            )
            for item in history
        ]
        
        logger.info(f"Retrieved {len(history_items)} chat history items")
        return ChatHistoryResponse(history=history_items)
    except Exception as e:
        logger.error(f"Error getting chat history: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/chat/sessions", response_model=SessionsResponse)
async def get_all_sessions(current_user: dict = Depends(get_current_user)):
    """
    Get all available session IDs.
    """
    try:
        logger.info(f"Getting all sessions for user {current_user['username']}")
        sessions = db_service.get_all_sessions(username=current_user["username"])
        logger.info(f"Retrieved {len(sessions)} sessions for user {current_user['username']}")
        return SessionsResponse(sessions=sessions)
    except Exception as e:
        logger.error(f"Error getting sessions: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/chat/sessions/{session_id}")
async def delete_session(session_id: str, current_user: dict = Depends(get_current_user)):
    """
    Delete a specific session and all its chat messages.
    """
    try:
        logger.info(f"Deleting session {session_id} for user {current_user['username']}")
        
        success = db_service.delete_session(session_id=session_id, username=current_user["username"])
        
        if success:
            logger.info(f"Successfully deleted session {session_id} for user {current_user['username']}")
            return {"message": f"Session {session_id} deleted successfully", "session_id": session_id}
        else:
            raise HTTPException(status_code=404, detail=f"Session {session_id} not found or no messages to delete")
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting session {session_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
def health_check():
    """
    Health check endpoint.
    """
    try:
        # 檢查資料庫連接
        db_status = "connected" if db_service.client else "disconnected"
        return {"status": "healthy", "database": db_status}
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return {"status": "unhealthy", "database": "error", "error": str(e)} 