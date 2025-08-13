# server.py
import asyncio
from typing import List, Dict, Optional
from pymongo import MongoClient
from mcp.server.fastmcp import FastMCP, Context
import os
import logging

mcp = FastMCP("MongoAgent")

def get_mongodb_connection():
    """建立並回傳 MongoDB collection 連接"""
    try:
        # username = os.getenv("MONGO_INITDB_ROOT_USERNAME")
        # password = os.getenv("MONGO_INITDB_ROOT_PASSWORD")
        
        # if not username or not password:
        #     raise RuntimeError("缺少 MongoDB 使用者名稱或密碼")
        
        uri = f"mongodb://admin:password@mongodb:27017/"
        client = MongoClient(uri)
        
        # 測試連線是否成功
        client.admin.command('ping')
        
        db = client["spec"]
        collection = db["spec-all"]
        return collection
    
    except Exception as e:
        raise RuntimeError(f"連接 MongoDB 失敗: {e}")

@mcp.tool()
def get_machine_info_by_model(context: Context, model: str) -> dict:
    """
    根據指定的 ProjectModel 型號回傳機器資訊：
    - 若為完整型號，則精確比對並回傳單一筆 exact_match。
    - 若為前綴型號，則回傳所有前綴匹配 prefix_matches。
    """
    logger = logging.getLogger(__name__)
    model = model.strip()
    model_lower = model.lower()

    exact_match = None
    prefix_matches = []

    try:
        collection = get_mongodb_connection()
        
        # 從 MongoDB 查詢所有資料
        data = list(collection.find({}, {"_id": 0}))  # 排除 _id 欄位
        
        if not data:
            return {"error": "MongoDB 中沒有找到 spec 資料"}

        for item in data:
            if not isinstance(item, dict):
                continue

            # === 精確比對 ===
            if item.get("ProjectModel") == model:
                exact_match = item
                break

            system_info = item.get("systemInfo")
            if (
                isinstance(system_info, list) and system_info and
                isinstance(system_info[0], dict) and
                system_info[0].get("ProjectModel") == model
            ):
                exact_match = item
                break

        # === 前綴比對 ===（若沒找到精確結果或想補充多筆）
        for item in data:
            if not isinstance(item, dict):
                continue

            # 比對外層
            pm = item.get("ProjectModel", "")
            if pm.lower().startswith(model_lower):
                prefix_matches.append(item)
                continue

            # 比對 systemInfo[*]
            system_info = item.get("systemInfo")
            if isinstance(system_info, list):
                for sys in system_info:
                    if isinstance(sys, dict):
                        sys_pm = sys.get("ProjectModel", "")
                        if sys_pm.lower().startswith(model_lower):
                            prefix_matches.append(item)
                            break  # 一筆只加一次

        return {
            "exact_match": exact_match,
            "prefix_matches": prefix_matches
        }

    except Exception as e:
        logger.exception("查詢 MongoDB spec 資料發生錯誤")
        return {"error": f"查詢失敗：{str(e)}"}



if __name__ == "__main__":
    mcp.run()