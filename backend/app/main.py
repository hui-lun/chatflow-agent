from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Optional
import logging
from .services.llm import get_llm
from .services.database import db_service

# 設置日誌
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create FastAPI app instance
app = FastAPI()

# 啟動時連接資料庫
@app.on_event("startup")
async def startup_event():
    """應用啟動時連接資料庫"""
    try:
        logger.info("Connecting to database...")
        db_service.connect()
        logger.info("Database connected successfully")
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

@app.post("/chat", response_model=ChatResponse)
def chat_endpoint(request: ChatRequest):
    """
    Receives a user message, sends it to the vLLM API, saves to database, and returns the response.
    """
    try:
        logger.info(f"Received chat request: {request.message[:50]}...")
        
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
                session_id=session_id
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
def get_chat_history(session_id: Optional[str] = None, limit: int = 50):
    """
    Get chat history for a specific session or all sessions.
    """
    try:
        logger.info(f"Getting chat history for session: {session_id}, limit: {limit}")
        history = db_service.get_chat_history(session_id=session_id, limit=limit)
        
        # 轉換為 Pydantic 模型
        history_items = [
            ChatHistoryItem(
                user_message=item["user_message"],
                bot_response=item["bot_response"],
                timestamp=item["timestamp"].isoformat(),
                session_id=item["session_id"]
            )
            for item in history
        ]
        
        logger.info(f"Retrieved {len(history_items)} chat history items")
        return ChatHistoryResponse(history=history_items)
    except Exception as e:
        logger.error(f"Error getting chat history: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/chat/sessions", response_model=SessionsResponse)
def get_all_sessions():
    """
    Get all available session IDs.
    """
    try:
        logger.info("Getting all sessions")
        sessions = db_service.get_all_sessions()
        logger.info(f"Retrieved {len(sessions)} sessions")
        return SessionsResponse(sessions=sessions)
    except Exception as e:
        logger.error(f"Error getting sessions: {e}")
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