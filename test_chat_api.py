#!/usr/bin/env python3
"""
測試聊天 API 和資料持久化功能
"""

import requests
import json
import time

# 使用 backend API 端口測試
BASE_URL = "http://localhost:8000"

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

def test_chat_api():
    """測試聊天 API"""
    print("\n💬 測試聊天 API...")
    
    # 測試發送訊息
    test_message = "Hello, this is a test message!"
    session_id = f"test_session_{int(time.time())}"
    
    try:
        response = requests.post(f"{BASE_URL}/chat", json={
            "message": test_message,
            "session_id": session_id
        })
        
        if response.status_code == 200:
            data = response.json()
            print(f"✅ 聊天 API 成功:")
            print(f"   - 用戶訊息: {test_message}")
            print(f"   - 機器人回應: {data['response']}")
            print(f"   - 會話 ID: {data['session_id']}")
            return session_id
        else:
            print(f"❌ 聊天 API 失敗: {response.status_code} - {response.text}")
            return None
    except Exception as e:
        print(f"❌ 聊天 API 錯誤: {e}")
        return None

def test_chat_history(session_id):
    """測試聊天歷史 API"""
    print(f"\n📚 測試聊天歷史 (會話: {session_id})...")
    
    try:
        response = requests.get(f"{BASE_URL}/chat/history", params={
            "session_id": session_id,
            "limit": 10
        })
        
        if response.status_code == 200:
            data = response.json()
            history = data['history']
            print(f"✅ 聊天歷史成功，共 {len(history)} 條記錄:")
            
            for i, item in enumerate(history, 1):
                print(f"   {i}. 用戶: {item['user_message']}")
                print(f"      機器人: {item['bot_response'][:50]}...")
                print(f"      時間: {item['timestamp']}")
                print()
        else:
            print(f"❌ 聊天歷史失敗: {response.status_code} - {response.text}")
    except Exception as e:
        print(f"❌ 聊天歷史錯誤: {e}")

def test_sessions_api():
    """測試會話列表 API"""
    print("\n📋 測試會話列表 API...")
    
    try:
        response = requests.get(f"{BASE_URL}/chat/sessions")
        
        if response.status_code == 200:
            data = response.json()
            sessions = data['sessions']
            print(f"✅ 會話列表成功，共 {len(sessions)} 個會話:")
            for session in sessions:
                print(f"   - {session}")
        else:
            print(f"❌ 會話列表失敗: {response.status_code} - {response.text}")
    except Exception as e:
        print(f"❌ 會話列表錯誤: {e}")

def main():
    """主測試函數"""
    print("🚀 開始測試 ChatFlow Agent API...")
    print("=" * 50)
    
    # 測試健康檢查
    if not test_health_check():
        print("❌ 健康檢查失敗，請確保服務正在運行")
        return
    
    # 測試聊天 API
    session_id = test_chat_api()
    if not session_id:
        print("❌ 聊天 API 測試失敗")
        return
    
    # 等待一下讓資料庫有時間處理
    time.sleep(1)
    
    # 測試聊天歷史
    test_chat_history(session_id)
    
    # 測試會話列表
    test_sessions_api()
    
    print("\n" + "=" * 50)
    print("✅ 所有測試完成！")

if __name__ == "__main__":
    main() 