import json
import logging
import re
import asyncio
from typing_extensions import TypedDict
from .llm import get_llm
from .spec.standalone_search import spec_search

# Configure logging
logger = logging.getLogger(__name__)

# State structure
class AgentState(TypedDict):
    agent_query: str
    summary: str
    next_node: str
    needs_streaming: bool
    model_name: str
    search_result: str
    error: str

def extract_model_names(query: str) -> list[str]:
    """
    Extract potential model names from the user query using regex pattern.
    只要符合 Rxxx-... 命名規則的字串都會被抓出來。
    """
    # Regex: R + 3位數字 + - + 後綴（允許多段）
    pattern = r"[A-Z]{1,2}\d{3}(?:-[A-Z0-9]+)+"

    matches = re.findall(pattern, query)
    return matches  # 不需要比對字典，純粹抓 pattern

# Node definitions
def select_tool(state: AgentState) -> dict:
    """Determine which tool to use based on the user query (Regex + LLM fallback)."""
    query = state["agent_query"].strip()
    logger.info(f"[select_tool] Determining tool selection for query: {query}")

    # ---------- Step 1: 規則檢查 (只要有符合 pattern 的型號 → spec_search) ----------
    found_models = extract_model_names(query)
    if found_models:
        logger.info(f"[select_tool] Found model name(s): {found_models} → spec_search_node")
        return {
            "next_node": "spec_search_node",
            "model_name": found_models[0],  # 儲存第一個型號
            "error": ""
        }

    # ---------- Step 2: fallback 到 LLM ----------
    prompt = (
        f"Given the user input:'{query}', decide which tool to use:\n"
        "1. If the question is about retrieving spec data or QVL data, return 'spec_search_node'.\n"
        "2. If the question requires recommending machine models based on requirements, return 'recommend_node'.\n"
        "ONLY return the exact tool name without explanation."
    )

    try:
        llm = get_llm()
        predicted_label = llm.invoke(prompt).content.strip().lower()
        logger.info(f"[select_tool] LLM selected tool: {predicted_label}")
        
        # 確保返回有效的節點名稱
        if predicted_label not in ["spec_search_node", "recommend_node"]:
            predicted_label = "spec_search_node"  # 預設使用 spec_search_node
        
        return {
            "next_node": predicted_label,
            "model_name": "",
            "error": ""
        }
    except Exception as e:
        logger.error(f"[select_tool] Error in LLM classification: {e}")
        return {
            "next_node": "spec_search_node",  # 預設使用 spec_search_node
            "model_name": "",
            "error": str(e)
        }

def spec_search_node(state: AgentState) -> dict:
    """使用spec目錄裡面的standalone_search.py 進行 spec 和 QVL 搜尋"""
    query = state["agent_query"]
    logger.info(f"[spec_search_node] Processing query: {query}")
    
    try:
        # 使用 asyncio.run 來執行異步的 spec_search 函數
        result = asyncio.run(spec_search(query))
        logger.info(f"[spec_search_node] Spec search completed successfully")
        
        return {
            "search_result": result,
            "summary": f"已完成 spec 搜尋: {query[:50]}...",
            "next_node": "END",
            "error": ""
        }
        
    except Exception as e:
        error_msg = f"Spec search error: {str(e)}"
        logger.error(f"[spec_search_node] {error_msg}")
        
        return {
            "search_result": error_msg,
            "summary": f"Spec 搜尋失敗: {str(e)}",
            "next_node": "END",
            "error": str(e)
        }

def recommend_node(state: AgentState):
    pass


