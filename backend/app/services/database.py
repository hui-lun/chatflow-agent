import os
from datetime import datetime
from typing import List, Optional
from pymongo import MongoClient
from pymongo.database import Database
from pymongo.collection import Collection

class DatabaseService:
    def __init__(self):
        self.client: Optional[MongoClient] = None
        self.db: Optional[Database] = None
        self.chat_collection: Optional[Collection] = None
        
    def connect(self):
        """建立 MongoDB 連接"""
        try:
            # 從環境變數獲取 MongoDB 配置
            username = os.getenv("MONGO_INITDB_ROOT_USERNAME")
            password = os.getenv("MONGO_INITDB_ROOT_PASSWORD")
            database = os.getenv("MONGO_INITDB_DATABASE", "chatflow")
            
            if not username or not password:
                raise RuntimeError("MongoDB credentials not found in environment variables")
            
            # 建立連接字串
            connection_string = f"mongodb://{username}:{password}@mongodb:27017/"
            
            # 建立客戶端連接
            self.client = MongoClient(connection_string)
            self.db = self.client[database]
            self.chat_collection = self.db.chat_messages
            
            # 測試連接
            self.client.admin.command('ping')
            print("Successfully connected to MongoDB")
            
        except Exception as e:
            print(f"Failed to connect to MongoDB: {e}")
            raise
    
    def disconnect(self):
        """關閉 MongoDB 連接"""
        if self.client:
            self.client.close()
    
    def _check_collection(self):
        """檢查集合是否可用"""
        return self.chat_collection is not None
    
    def save_chat_message(self, user_message: str, bot_response: str, session_id: str = None) -> str:
        """儲存聊天訊息到資料庫"""
        if not self._check_collection():
            raise RuntimeError("Database not connected")
        
        try:
            chat_record = {
                "user_message": user_message,
                "bot_response": bot_response,
                "session_id": session_id or "default",
                "timestamp": datetime.utcnow(),
                "created_at": datetime.utcnow()
            }
            
            result = self.chat_collection.insert_one(chat_record)
            return str(result.inserted_id)
        except Exception as e:
            print(f"Failed to save chat message: {e}")
            raise
    
    def get_chat_history(self, session_id: str = None, limit: int = 50) -> List[dict]:
        """獲取聊天歷史記錄"""
        if not self._check_collection():
            raise RuntimeError("Database not connected")
        
        try:
            filter_query = {}
            if session_id:
                filter_query["session_id"] = session_id
            
            # 保留所有必要欄位，只排除 MongoDB 的 _id
            projection = {
                "_id": 0,
                "user_message": 1,
                "bot_response": 1,
                "session_id": 1,
                "timestamp": 1,
                "created_at": 1
            }
            
            cursor = self.chat_collection.find(
                filter_query,
                projection
            ).sort("timestamp", -1).limit(limit)
            
            # 轉換為列表並反轉順序（最新的在最後）
            history = list(cursor)
            history.reverse()
            return history
        except Exception as e:
            print(f"Failed to get chat history: {e}")
            raise
    
    def get_all_sessions(self) -> List[str]:
        """獲取所有會話 ID"""
        if not self._check_collection():
            raise RuntimeError("Database not connected")
        
        try:
            sessions = self.chat_collection.distinct("session_id")
            return sessions
        except Exception as e:
            print(f"Failed to get sessions: {e}")
            raise

# 全域資料庫服務實例
db_service = DatabaseService() 