from fastapi import FastAPI, HTTPException, Depends, Request, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from typing import Optional, List, AsyncGenerator
import logging
import os
import tempfile
import json
import uuid
import asyncio
from datetime import datetime, timedelta
from pathlib import Path
from langchain_core.messages import HumanMessage, AIMessage
from .services.llm import get_llm
from .services.database import db_service
from .auth import AuthService, get_current_user, set_auth_service
from .models import (
    LoginRequest, LoginResponse, UserResponse,
    ChatRequest, ChatResponse, ChatHistoryItem, ChatHistoryResponse, SessionsResponse,
    WebSearchRequest, WebSearchResponse,
    FileUploadResponse, FileInfo, FileListResponse, RAGChatRequest, RAGChatResponse
)
from .services.graph import app as graph_app
from .services.rag.service import RAGService

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

# 全域RAG服務實例
rag_service = None

# KB檔案上傳目錄
UPLOAD_DIR = Path("kb_uploads")
UPLOAD_DIR.mkdir(exist_ok=True)

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
        
        # 初始化RAG服務
        global rag_service
        rag_service = RAGService()
        logger.info("RAG service initialized")
            
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
@app.post("/chat")
async def chat_endpoint(request: ChatRequest, current_user: dict = Depends(get_current_user)):
    """
    Receives a user message, sends it to the vLLM API, and streams the response character by character.
    """
    async def generate() -> AsyncGenerator[str, None]:
        try:
            logger.info(f"Received chat request from {current_user['username']}: {request.message[:50]}...")
            
            llm = get_llm()
            session_id = request.session_id or "default"

            # 1️⃣ 載入聊天歷史（從 MongoDB 或其他 DB）
            try:
                history = db_service.get_chat_history(
                    session_id=session_id,
                    username=current_user["username"]
                )  # 應回傳 List[Dict]，每個 dict 至少有 user_message / bot_response
                logger.info(f"Loaded {len(history)} historical messages")
            except Exception as history_error:
                logger.warning(f"Could not load chat history: {history_error}")
                history = []

            # 2️⃣ 組成對話上下文 messages 給 LLM
            messages = []
            for entry in history:
                messages.append(HumanMessage(content=entry["user_message"]))
                messages.append(AIMessage(content=entry["bot_response"]))
            messages.append(HumanMessage(content=request.message))

            # 3️⃣ 呼叫 LLM
            result = llm.invoke(messages)
            bot_response = result.content
            logger.info("LLM response received, starting streaming...")
            
            # Stream each character with a small delay
            for char in bot_response:
                yield json.dumps({"token": char}) + "\n"
                await asyncio.sleep(0.01)  # Small delay to make streaming visible
            
            # 4️⃣ 儲存對話記錄（可選擇只儲存這一輪，也可合併存整包）
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
                
        except Exception as e:
            error_msg = f"Error generating response: {str(e)}"
            logger.error(error_msg)
            yield json.dumps({"error": error_msg}) + "\n"
    
    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )

@app.post("/chat/web-search")
async def web_search_chat_endpoint(request: WebSearchRequest, current_user: dict = Depends(get_current_user)):
    """
    Handles chat with web search functionality using SearxNG with streaming response.
    """
    async def generate() -> AsyncGenerator[str, None]:
        try:
            from .services.web.analyze import analyze_web_search
            
            logger.info(f"Received web search chat request from {current_user['username']}: {request.message[:50]}...")
            
            llm = get_llm()
            session_id = request.session_id or "default"

            # 1️⃣ 載入聊天歷史
            try:
                history = db_service.get_chat_history(
                    session_id=session_id,
                    username=current_user["username"]
                )
                logger.info(f"Loaded {len(history)} historical messages")
            except Exception as history_error:
                logger.warning(f"Could not load chat history: {history_error}")
                history = []

            # 2️⃣ 執行網路搜索
            try:
                logger.info("Performing web search...")
                search_results = analyze_web_search(request.message)
                logger.info("Web search completed")
            except Exception as search_error:
                logger.error(f"Web search failed: {search_error}")
                search_results = f"Web search failed: {search_error}"

            # 3️⃣ 組成對話上下文，包含搜索結果
            messages = []
            for entry in history:
                messages.append(HumanMessage(content=entry["user_message"]))
                messages.append(AIMessage(content=entry["bot_response"]))
            
            # 將搜索結果和用戶問題結合
            enhanced_prompt = f"""User question: {request.message}

Web search results:
{search_results}

Please answer the user's question based on the web search results above. If the search results don't contain relevant information, acknowledge this and provide a general response."""
            
            messages.append(HumanMessage(content=enhanced_prompt))

            # 4️⃣ 呼叫 LLM
            result = llm.invoke(messages)
            bot_response = result.content
            logger.info("LLM response received, starting streaming...")

            # Stream each character with a small delay
            for char in bot_response:
                yield json.dumps({"token": char}) + "\n"
                await asyncio.sleep(0.01)  # Small delay to make streaming visible

            # 5️⃣ 儲存對話記錄
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

            # 提取搜索來源（從搜索結果中解析URL）並發送
            search_sources = []
            if "URL:" in search_results:
                import re
                urls = re.findall(r'URL: (https?://[^\s]+)', search_results)
                search_sources = urls[:5]  # 最多5個來源
            
            # 發送搜索來源
            if search_sources:
                yield json.dumps({"search_sources": search_sources}) + "\n"
            
        except Exception as e:
            error_msg = f"Error generating web search response: {str(e)}"
            logger.error(error_msg)
            yield json.dumps({"error": error_msg}) + "\n"
    
    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )

@app.post("/chat/spec-search")
async def spec_search_chat_endpoint(request: Request, current_user: dict = Depends(get_current_user)):
    """
    Handles chat with spec search functionality using LangGraph workflow with streaming response.
    """
    # 手動解析 JSON 請求 (必須在外部進行，因為request body只能讀一次)
    try:
        request_data = await request.json()
        message = request_data.get("message", "")
        session_id = request_data.get("session_id") or "default"
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid request format: {str(e)}")
    
    async def generate() -> AsyncGenerator[str, None]:
        try:
            
            logger.info(f"Received spec search chat request from {current_user['username']}: {message[:50]}...")

            # 1️⃣ 載入聊天歷史
            try:
                history = db_service.get_chat_history(
                    session_id=session_id,
                    username=current_user["username"]
                )
                logger.info(f"Loaded {len(history)} historical messages")
            except Exception as history_error:
                logger.warning(f"Could not load chat history: {history_error}")
                history = []

            # 2️⃣ 使用 LangGraph 執行搜索流程
            try:
                logger.info("Performing spec search via LangGraph...")
                
                # 準備初始狀態
                initial_state = {
                    "agent_query": message,
                    "summary": "",
                    "next_node": "",
                    "needs_streaming": False,
                    "model_name": "",
                    "search_result": "",
                    "error": ""
                }
                
                # 執行 graph
                result = await graph_app.ainvoke(initial_state)
                
                # 從結果中取得最終回應
                bot_response = result.get("search_result", "未找到搜索結果")
                
                logger.info("LangGraph spec search completed successfully")
            except Exception as search_error:
                logger.error(f"LangGraph spec search failed: {search_error}")
                bot_response = f"Spec search failed: {search_error}"
            logger.info("Spec search response received, starting streaming...")

            # Stream each character with a small delay
            for char in bot_response:
                yield json.dumps({"token": char}) + "\n"
                await asyncio.sleep(0.01)  # Small delay to make streaming visible

            # 4️⃣ 儲存對話記錄
            try:
                db_service.save_chat_message(
                    user_message=message,
                    bot_response=bot_response,
                    session_id=session_id,
                    username=current_user["username"]
                )
                logger.info("Chat message saved to database")
            except Exception as db_error:
                logger.error(f"Failed to save chat message: {db_error}")
            
            # 檢查回應是否包含 QVL 資訊，並生成下載連結
            qvl_downloads = []
            if "QVL 資料查詢結果" in bot_response:
                try:
                    # 從 user query 中提取型號
                    import re
                    model_pattern = r'[A-Z]\d{3}-[A-Z0-9]{3}-[A-Z]{3}\d'
                    user_models = re.findall(model_pattern, message)
                    
                    if user_models:
                        project_model = user_models[0]
                        matching_collections = db_service.find_matching_qvl_collections(project_model)
                        
                        for collection_name in matching_collections:
                            qvl_downloads.append({
                                "collection_name": collection_name,
                                "download_url": f"/download/qvl/{collection_name}.txt"
                            })
                            
                except Exception as e:
                    logger.error(f"生成 QVL 下載連結時發生錯誤: {e}")
            
            # 發送 QVL 下載連結
            if qvl_downloads:
                yield json.dumps({"qvl_downloads": qvl_downloads}) + "\n"
                
        except Exception as e:
            error_msg = f"Error generating spec search response: {str(e)}"
            logger.error(error_msg)
            yield json.dumps({"error": error_msg}) + "\n"
    
    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )

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

@app.get("/download/qvl/{collection_name}")
async def download_qvl_file(collection_name: str, current_user: dict = Depends(get_current_user)):
    """
    下載指定 QVL collection 的資料為 TXT 檔案
    """
    try:
        # 移除可能的 .txt 後綴
        if collection_name.endswith('.txt'):
            collection_name = collection_name[:-4]
        
        logger.info(f"Downloading QVL collection: {collection_name} for user: {current_user['username']}")
        
        # 獲取 QVL 資料
        qvl_data = db_service.get_qvl_data(collection_name)
        
        if not qvl_data:
            raise HTTPException(status_code=404, detail=f"QVL collection '{collection_name}' not found or empty")
        
        # 創建臨時檔案
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt', encoding='utf-8') as temp_file:
            # 將資料寫入檔案
            temp_file.write(f"QVL 資料 - Collection: {collection_name}\n")
            temp_file.write("=" * 50 + "\n\n")
            
            for i, item in enumerate(qvl_data, 1):
                temp_file.write(f"項目 {i}:\n")
                temp_file.write(json.dumps(item, ensure_ascii=False, indent=2))
                temp_file.write("\n" + "-" * 30 + "\n\n")
            
            temp_file_path = temp_file.name
        
        # 設定檔案名稱
        filename = f"{collection_name}.txt"
        
        # 回傳檔案
        return FileResponse(
            path=temp_file_path,
            filename=filename,
            media_type='text/plain',
            headers={
                "Content-Disposition": f"attachment; filename*=UTF-8''{filename}"
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error downloading QVL file {collection_name}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to download QVL file: {str(e)}")

# Knowledge Base相關endpoints
@app.post("/kb/upload", response_model=FileUploadResponse)
async def upload_file(
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user)
):
    """
    上傳PDF檔案到使用者的知識庫
    """
    try:
        # 檢查檔案類型
        if not file.filename.lower().endswith('.pdf'):
            raise HTTPException(status_code=400, detail="僅支援PDF檔案")
        
        if file.size > 50 * 1024 * 1024:  # 50MB限制
            raise HTTPException(status_code=400, detail="檔案大小不能超過50MB")
        
        # 生成唯一檔案ID
        file_id = str(uuid.uuid4())
        username = current_user["username"]
        
        # 保存檔案到本地
        user_upload_dir = UPLOAD_DIR / username
        user_upload_dir.mkdir(exist_ok=True)
        
        file_path = user_upload_dir / f"{file_id}_{file.filename}"
        
        with open(file_path, "wb") as buffer:
            content = await file.read()
            buffer.write(content)
        
        # 獲取使用者專屬collection名稱
        collection_name = RAGService.get_user_collection_name(username)
        
        # 處理PDF並索引到向量資料庫
        try:
            result = rag_service.index_pdfs(
                pdf_paths=[str(file_path)],
                collection_name=collection_name,
                user_id=username,
                file_id=file_id
            )
            
            # 儲存檔案元資料到MongoDB
            file_metadata = {
                "file_id": file_id,
                "filename": file.filename,
                "file_size": file.size,
                "file_path": str(file_path),
                "username": username,
                "uploaded_at": datetime.now(),
                "status": "processed",
                "chunks_count": result.get("chunks_indexed", 0)
            }
            
            db_service.client.KB.kb_files.insert_one(file_metadata)
            
            return FileUploadResponse(
                file_id=file_id,
                filename=file.filename,
                file_size=file.size,
                status="processed",
                message=f"檔案已成功處理，共產生 {result.get('chunks_indexed', 0)} 個文本塊"
            )
            
        except Exception as e:
            logger.error(f"PDF處理失敗: {e}")
            # 清理已上傳的檔案
            if file_path.exists():
                file_path.unlink()
            raise HTTPException(status_code=500, detail=f"檔案處理失敗: {str(e)}")
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"檔案上傳錯誤: {e}")
        raise HTTPException(status_code=500, detail=f"檔案上傳失敗: {str(e)}")

@app.get("/kb/files", response_model=FileListResponse)
async def get_files(current_user: dict = Depends(get_current_user)):
    """
    取得使用者的檔案列表
    """
    try:
        username = current_user["username"]
        
        # 從MongoDB獲取檔案列表
        files_cursor = db_service.client.KB.kb_files.find(
            {"username": username}
        ).sort("uploaded_at", -1)
        
        files = []
        for file_doc in files_cursor:
            files.append(FileInfo(
                file_id=file_doc["file_id"],
                filename=file_doc["filename"],
                file_size=file_doc["file_size"],
                uploaded_at=file_doc["uploaded_at"].isoformat(),
                status=file_doc["status"],
                chunks_count=file_doc.get("chunks_count")
            ))
        
        return FileListResponse(files=files)
        
    except Exception as e:
        logger.error(f"取得檔案列表失敗: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/kb/files/{file_id}")
async def delete_file(file_id: str, current_user: dict = Depends(get_current_user)):
    """
    刪除使用者的檔案
    """
    try:
        username = current_user["username"]
        
        # 從MongoDB查找檔案
        file_doc = db_service.client.KB.kb_files.find_one({
            "file_id": file_id,
            "username": username
        })
        
        if not file_doc:
            raise HTTPException(status_code=404, detail="檔案不存在")
        
        # 刪除本地檔案
        file_path = Path(file_doc["file_path"])
        if file_path.exists():
            file_path.unlink()
        
        # 從Milvus中刪除對應的向量數據
        try:
            # 取得使用者專屬的 collection 名稱
            collection_name = RAGService.get_user_collection_name(username)
            
            # 初始化 RAG 服務並刪除向量數據
            rag_service = RAGService()
            if rag_service.has_collection(collection_name):
                deleted_count = rag_service.milvus_service.delete_by_file_id(
                    collection_name=collection_name,
                    file_id=file_id,
                    user_id=username
                )
                logger.info(f"已從 Milvus 刪除 {deleted_count} 個向量片段")
            else:
                logger.warning(f"Milvus 集合 {collection_name} 不存在，跳過向量刪除")
        except Exception as e:
            # 即使 Milvus 刪除失敗，也不影響其他刪除操作
            logger.error(f"從 Milvus 刪除向量數據失敗: {e}")
        
        # 從MongoDB刪除檔案記錄
        db_service.client.KB.kb_files.delete_one({
            "file_id": file_id,
            "username": username
        })
        
        return {"message": "檔案已刪除", "file_id": file_id}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"刪除檔案失敗: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/chat/rag")
async def rag_chat_endpoint(request: RAGChatRequest, current_user: dict = Depends(get_current_user)):
    """
    RAG聊天端點：基於使用者知識庫進行對話，支援 streaming 回應
    """
    async def generate() -> AsyncGenerator[str, None]:
        try:
            username = current_user["username"]
            session_id = request.session_id or "default"
            
            logger.info(f"Received RAG chat request from {username}: {request.message[:50]}...")
            
            # 檢查使用者是否有上傳的檔案
            file_count = db_service.client.KB.kb_files.count_documents({
                "username": username,
                "status": "processed"
            })
            
            if file_count == 0:
                error_msg = "尚未上傳任何檔案到知識庫，請先到 /kb 頁面上傳PDF檔案"
                yield json.dumps({"error": error_msg}) + "\n"
                return
            
            # 獲取使用者專屬collection名稱
            collection_name = RAGService.get_user_collection_name(username)
            
            # 檢查collection是否存在
            if not rag_service.has_collection(collection_name):
                error_msg = "知識庫尚未初始化，請重新上傳檔案"
                yield json.dumps({"error": error_msg}) + "\n"
                return
            
            # 載入聊天歷史
            try:
                history = db_service.get_chat_history(
                    session_id=session_id,
                    username=username
                )
                logger.info(f"Loaded {len(history)} historical messages")
            except Exception as history_error:
                logger.warning(f"Could not load chat history: {history_error}")
                history = []
            
            # 執行RAG檢索和生成
            try:
                logger.info("Performing RAG retrieval and generation...")
                rag_result = rag_service.rag(
                    query=request.message,
                    collection_name=collection_name,
                    user_id=username,
                    limit=5
                )
                
                bot_response = rag_result["response"]
                retrieved_docs = rag_result.get("retrieved_docs", [])
                
                logger.info(f"RAG completed with {len(retrieved_docs)} retrieved documents")
                
            except Exception as rag_error:
                logger.error(f"RAG processing failed: {rag_error}")
                bot_response = f"抱歉，處理您的問題時發生錯誤：{str(rag_error)}"
                retrieved_docs = []
            
            logger.info("RAG response received, starting streaming...")

            # Stream each character with a small delay
            for char in bot_response:
                yield json.dumps({"token": char}) + "\n"
                await asyncio.sleep(0.01)  # Small delay to make streaming visible
            
            # 儲存對話記錄
            try:
                db_service.save_chat_message(
                    user_message=request.message,
                    bot_response=bot_response,
                    session_id=session_id,
                    username=username
                )
                logger.info("RAG chat message saved to database")
            except Exception as db_error:
                logger.error(f"Failed to save RAG chat message: {db_error}")
            
            # 發送檢索到的文檔
            if retrieved_docs:
                yield json.dumps({"retrieved_docs": retrieved_docs}) + "\n"
            
        except Exception as e:
            error_msg = f"Error generating RAG response: {str(e)}"
            logger.error(error_msg)
            yield json.dumps({"error": error_msg}) + "\n"
    
    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )
 