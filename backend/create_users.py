#!/usr/bin/env python3
"""
建立預設使用者帳號的腳本
使用方式: python create_users.py
"""

import os
import sys
from pymongo import MongoClient
from passlib.context import CryptContext

# 密碼雜湊設定
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def get_password_hash(password: str) -> str:
    """產生密碼雜湊"""
    return pwd_context.hash(password)

def create_default_users():
    """建立預設使用者"""
    # 資料庫連接設定
    mongo_username = os.getenv("MONGO_INITDB_ROOT_USERNAME", "admin")
    mongo_password = os.getenv("MONGO_INITDB_ROOT_PASSWORD", "password")
    mongo_host = os.getenv("MONGO_HOST", "localhost")
    mongo_port = os.getenv("MONGO_PORT", "27017")
    
    # 建立 MongoDB 連接
    connection_string = f"mongodb://{mongo_username}:{mongo_password}@{mongo_host}:{mongo_port}/"
    
    try:
        client = MongoClient(connection_string)
        db = client.internal_system
        users_collection = db.users
        
        # 預設使用者列表
        default_users = [
            {
                "username": "admin",
                "hashed_password": get_password_hash("admin123"),
                "created_at": "2024-01-01T00:00:00Z"
            },
            {
                "username": "user1",
                "hashed_password": get_password_hash("user123"),
                "created_at": "2024-01-01T00:00:00Z"
            },
            {
                "username": "user2", 
                "hashed_password": get_password_hash("user456"),
                "created_at": "2024-01-01T00:00:00Z"
            }
        ]
        
        # 檢查使用者是否已存在
        for user in default_users:
            existing_user = users_collection.find_one({"username": user["username"]})
            if existing_user:
                print(f"使用者 {user['username']} 已存在，跳過建立")
            else:
                users_collection.insert_one(user)
                print(f"成功建立使用者: {user['username']}")
        
        print("\n預設使用者帳號:")
        print("admin / admin123")
        print("user1 / user123") 
        print("user2 / user456")
        print("\n請在生產環境中更改這些密碼！")
        
    except Exception as e:
        print(f"建立使用者時發生錯誤: {e}")
        sys.exit(1)
    finally:
        client.close()

if __name__ == "__main__":
    create_default_users() 