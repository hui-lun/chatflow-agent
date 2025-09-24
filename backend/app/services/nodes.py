import json
import logging
import re
import asyncio
from typing_extensions import TypedDict
from .llm import get_llm
from .spec.standalone_search import spec_search
from .spec.recommend_search import recommend_search
from .spec.genL10 import generate_l10_table

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
    selected_machine: str  # 存儲用戶選擇的機器型號

def extract_model_names(query: str) -> list[str]:
    """
    Extract potential model names from the user query using regex pattern.
    支援多種機器型號格式，如：R283-Z90-AAD1-000, G4L3-ZX1-LAX2-000 等
    """
    # 統一使用與 genL10.py 相同的 pattern，支援更廣泛的機器型號格式
    pattern = r'\b[A-Z0-9]{3,4}-[A-Z0-9]{2,4}-[A-Z0-9]{3,4}(?:-[A-Z0-9]{1,3})?\b'

    matches = re.findall(pattern, query.upper())  # 轉為大寫確保匹配
    return matches

# Node definitions
def select_tool(state: AgentState) -> dict:
    """Determine which tool to use based on the user query (Regex + LLM fallback)."""
    query = state["agent_query"].strip()
    logger.info(f"[select_tool] Determining tool selection for query: {query}")

    # ---------- Step 1: 規則檢查 (檢查是否為機器選擇還是規格查詢) ----------
    found_models = extract_model_names(query)
    if found_models:
        # 檢查是否包含選擇意圖關鍵字
        selection_keywords = ["選擇", "選", "要", "用", "取", "pick", "choose", "select", "我選"]
        has_selection_intent = any(keyword in query for keyword in selection_keywords)

        if has_selection_intent:
            logger.info(f"[select_tool] Found model selection: {found_models[0]} → recommend_node")
            return {
                "next_node": "recommend_node",
                "model_name": found_models[0],
                "error": ""
            }
        else:
            logger.info(f"[select_tool] Found model spec query: {found_models[0]} → spec_search_node")
            return {
                "next_node": "spec_search_node",
                "model_name": found_models[0],
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

def recommend_node(state: AgentState) -> dict:
    """使用spec目錄裡面的recommend_search.py 進行機器型號推薦，或處理直接機器選擇"""
    query = state["agent_query"]
    logger.info(f"[recommend_node] Processing recommendation query: {query}")

    try:
        # 檢查是否為直接選擇機器的情況
        selection_keywords = ["選擇", "選", "要", "用", "取", "pick", "choose", "select", "我選"]
        model_pattern = r'\b[A-Z0-9]{3,4}-[A-Z0-9]{2,4}-[A-Z0-9]{3,4}(?:-[A-Z0-9]{1,3})?\b'

        has_selection = any(keyword in query for keyword in selection_keywords)
        model_matches = re.findall(model_pattern, query.upper())

        if has_selection and model_matches:
            # 直接選擇機器的情況，跳過推薦搜尋，直接進入 L10 生成
            selected_model = model_matches[0]
            logger.info(f"[recommend_node] Direct machine selection detected: {selected_model}, routing to gen_l10_node")

            return {
                "search_result": f"您選擇了機器型號: {selected_model}，正在生成 L10 表格...",
                "summary": f"直接選擇機器: {selected_model}",
                "next_node": "gen_l10_node",
                "error": ""
            }

        # 一般推薦流程
        result = asyncio.run(recommend_search(query))
        logger.info(f"[recommend_node] Machine recommendation completed successfully")

        return {
            "search_result": result,
            "summary": f"已完成機器推薦: {query[:50]}...",
            "next_node": "END",
            "error": ""
        }

    except Exception as e:
        error_msg = f"Machine recommendation error: {str(e)}"
        logger.error(f"[recommend_node] {error_msg}")

        return {
            "search_result": error_msg,
            "summary": f"機器推薦失敗: {str(e)}",
            "next_node": "END",
            "error": str(e)
        }

def gen_l10_node(state: AgentState) -> dict:
    """生成 L10 表格，根據用戶選擇的機器從 QVL 中隨機抓取零件"""
    query = state["agent_query"]
    logger.info(f"[gen_l10_node] Processing L10 generation query: {query}")

    try:
        # 使用 asyncio.run 來執行異步的 generate_l10_table 函數
        result = asyncio.run(generate_l10_table(query))
        logger.info(f"[gen_l10_node] L10 table generation completed successfully")

        return {
            "search_result": result,
            "summary": f"已完成 L10 表格生成: {query[:50]}...",
            "next_node": "END",
            "error": ""
        }

    except Exception as e:
        error_msg = f"L10 table generation error: {str(e)}"
        logger.error(f"[gen_l10_node] {error_msg}")

        return {
            "search_result": error_msg,
            "summary": f"L10 表格生成失敗: {str(e)}",
            "next_node": "END",
            "error": str(e)
        }


