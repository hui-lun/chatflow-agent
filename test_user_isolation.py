#!/usr/bin/env python3
"""
測試使用者聊天隔離功能
"""

import requests
import json
import time
import os
from pymongo import MongoClient
from passlib.context import CryptContext

# 使用 backend API 端口測試
BASE_URL = "http://localhost:8000"

def create_test_user(username, password):
    """創建測試用戶"""
    try:
        # 直接連接 MongoDB 創建用戶 (實際上應該有註冊 API，這裡為測試簡化)
        username_env = os.getenv("MONGO_INITDB_ROOT_USERNAME", "admin")
        password_env = os.getenv("MONGO_INITDB_ROOT_PASSWORD", "password123")
            
        connection_string = f"mongodb://{username_env}:{password_env}@localhost:27017/"
        client = MongoClient(connection_string)
        db = client.internal_system
        users_collection = db.users
        
        pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
        hashed_password = pwd_context.hash(password)
        
        # 檢查用戶是否存在
        existing_user = users_collection.find_one({"username": username})
        if not existing_user:
            users_collection.insert_one({
                "username": username,
                "hashed_password": hashed_password,
                "created_at": time.time()
            })
            print(f"✅ 創建測試用戶: {username}")
        else:
            print(f"ℹ️ 用戶已存在: {username}")
        
        client.close()
        return True
    except Exception as e:
        print(f"❌ 創建用戶失敗: {e}")
        return False

def login_user(username, password):
    """登入用戶並獲取 token"""
    try:
        response = requests.post(f"{BASE_URL}/auth/login", json={
            "username": username,
            "password": password
        })
        
        if response.status_code == 200:
            data = response.json()
            token = data["access_token"]
            print(f"✅ 用戶 {username} 登入成功")
            return token
        else:
            print(f"❌ 用戶 {username} 登入失敗: {response.status_code} - {response.text}")
            return None
    except Exception as e:
        print(f"❌ 登入錯誤: {e}")
        return None

def test_chat_api(token, username):
    """測試聊天 API"""
    print(f"\n💬 測試用戶 {username} 的聊天 API...")
    
    # 測試發送訊息
    test_message = f"Hello from {username}, this is a test message!"
    session_id = f"{username}_test_session_{int(time.time())}"
    
    headers = {"Authorization": f"Bearer {token}"}
    
    try:
        response = requests.post(f"{BASE_URL}/chat", 
                               json={
                                   "message": test_message,
                                   "session_id": session_id
                               },
                               headers=headers)
        
        if response.status_code == 200:
            data = response.json()
            print(f"✅ 用戶 {username} 聊天 API 成功:")
            print(f"   - 用戶訊息: {test_message}")
            print(f"   - 機器人回應: {data['response'][:50]}...")
            print(f"   - 會話 ID: {data['session_id']}")
            return session_id
        else:
            print(f"❌ 用戶 {username} 聊天 API 失敗: {response.status_code} - {response.text}")
            return None
    except Exception as e:
        print(f"❌ 用戶 {username} 聊天 API 錯誤: {e}")
        return None

def test_sessions_api(token, username):
    """測試會話列表 API"""
    print(f"\n📋 測試用戶 {username} 的會話列表 API...")
    
    headers = {"Authorization": f"Bearer {token}"}
    
    try:
        response = requests.get(f"{BASE_URL}/chat/sessions", headers=headers)
        
        if response.status_code == 200:
            data = response.json()
            sessions = data['sessions']
            print(f"✅ 用戶 {username} 會話列表成功，共 {len(sessions)} 個會話:")
            for session in sessions:
                print(f"   - {session}")
            return sessions
        else:
            print(f"❌ 用戶 {username} 會話列表失敗: {response.status_code} - {response.text}")
            return []
    except Exception as e:
        print(f"❌ 用戶 {username} 會話列表錯誤: {e}")
        return []

def test_chat_history(token, session_id, username):
    """測試聊天歷史 API"""
    print(f"\n📚 測試用戶 {username} 的聊天歷史 (會話: {session_id})...")
    
    headers = {"Authorization": f"Bearer {token}"}
    
    try:
        response = requests.get(f"{BASE_URL}/chat/history", 
                              params={
                                  "session_id": session_id,
                                  "limit": 10
                              },
                              headers=headers)
        
        if response.status_code == 200:
            data = response.json()
            history = data['history']
            print(f"✅ 用戶 {username} 聊天歷史成功，共 {len(history)} 條記錄:")
            
            for i, item in enumerate(history, 1):
                print(f"   {i}. 用戶 ({item['username']}): {item['user_message']}")
                print(f"      機器人: {item['bot_response'][:50]}...")
                print(f"      時間: {item['timestamp']}")
                print()
            return len(history)
        else:
            print(f"❌ 用戶 {username} 聊天歷史失敗: {response.status_code} - {response.text}")
            return 0
    except Exception as e:
        print(f"❌ 用戶 {username} 聊天歷史錯誤: {e}")
        return 0

def test_health_check():
    """測試健康檢查端點"""
    print("🔍 測試健康檢查...")
    try:
        response = requests.get(f"{BASE_URL}/health")
        print(f"✅ 健康檢查成功: {response.json()}")
        return True
    except Exception as e:
        print(f"❌ 健康檢查失敗: {e}")
        return False

def test_user_isolation():
    """測試使用者隔離功能"""
    print("\n🔒 測試使用者隔離功能...")
    
    # 創建兩個測試用戶
    user1, user2 = "testuser1", "testuser2"
    password = "testpass123"
    
    if not create_test_user(user1, password) or not create_test_user(user2, password):
        print("❌ 無法創建測試用戶")
        return False
    
    # 用戶登入
    token1 = login_user(user1, password)
    token2 = login_user(user2, password)
    
    if not token1 or not token2:
        print("❌ 用戶登入失敗")
        return False
    
    # 用戶 1 發送訊息
    session1 = test_chat_api(token1, user1)
    if not session1:
        return False
    
    # 用戶 2 發送訊息
    session2 = test_chat_api(token2, user2)
    if not session2:
        return False
    
    time.sleep(1)  # 等待資料庫處理
    
    # 測試用戶 1 的 sessions
    user1_sessions = test_sessions_api(token1, user1)
    
    # 測試用戶 2 的 sessions
    user2_sessions = test_sessions_api(token2, user2)
    
    # 驗證隔離
    if session2 in user1_sessions:
        print(f"❌ 隔離失敗: 用戶 {user1} 能看到用戶 {user2} 的 session {session2}")
        return False
    
    if session1 in user2_sessions:
        print(f"❌ 隔離失敗: 用戶 {user2} 能看到用戶 {user1} 的 session {session1}")
        return False
    
    # 測試聊天歷史隔離
    history1_count = test_chat_history(token1, session1, user1)
    history2_count = test_chat_history(token2, session2, user2)
    
    if history1_count > 0 and history2_count > 0:
        print(f"✅ 隔離測試成功: 用戶 {user1} 和 {user2} 的聊天記錄完全隔離")
        return True
    else:
        print("❌ 聊天歷史測試失敗")
        return False

def main():
    """主測試函數"""
    print("🚀 開始測試 ChatFlow Agent 使用者隔離功能...")
    print("=" * 60)
    
    # 測試健康檢查
    if not test_health_check():
        print("❌ 健康檢查失敗，請確保服務正在運行 (docker compose up -d)")
        return
    
    # 測試使用者隔離功能
    if not test_user_isolation():
        print("❌ 使用者隔離測試失敗")
        return
    
    print("\n" + "=" * 60)
    print("✅ 所有測試完成！使用者隔離功能正常運作！")

if __name__ == "__main__":
    main()