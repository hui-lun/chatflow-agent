#!/usr/bin/env python3
# genL10.py - L10表格生成功能
import logging
import re
import random
from typing import List, Dict, Any, Optional
from ..database import db_service
from ..llm import get_llm

logger = logging.getLogger(__name__)

def parse_selected_machine(user_query: str) -> Optional[str]:
    """
    從用戶輸入中提取選擇的機器型號

    Args:
        user_query: 用戶查詢內容

    Returns:
        str: 機器型號，如果找不到則返回 None
    """
    try:
        # 使用正則表達式匹配機器型號格式
        # 支援格式：R283-Z90-AAD1-000, R283-Z90-AAD1 等
        model_pattern = r'\b[A-Z0-9]{3,4}-[A-Z0-9]{2,4}-[A-Z0-9]{3,4}(?:-[A-Z0-9]{1,3})?\b'
        matches = re.findall(model_pattern, user_query.upper())

        if matches:
            logger.info(f"找到機器型號: {matches[0]}")
            return matches[0]

        # 如果正則表達式找不到，使用 LLM 輔助分析
        llm = get_llm()
        analysis_prompt = f"""
請從以下用戶輸入中提取機器型號。用戶可能說「選擇 XXX」或「我要 XXX」等：

用戶輸入："{user_query}"

如果找到機器型號，請只回覆機器型號（例如：R283-Z90-AAD1-000）。
如果沒有找到，請回覆：NOT_FOUND

機器型號通常格式為：字母數字-字母數字-字母數字（-可選後綴）
"""

        response = llm.invoke(analysis_prompt).content.strip().upper()
        logger.info(f"LLM 分析結果: {response}")

        if response != "NOT_FOUND" and re.match(model_pattern, response):
            return response

        return None

    except Exception as e:
        logger.error(f"解析選擇的機器型號時發生錯誤: {e}")
        return None

def get_qvl_collection_data(project_model: str) -> Optional[List[Dict]]:
    """
    根據機器型號獲取對應的 QVL collection 資料
    支援智能匹配：如果完整型號找不到，會嘗試移除數字後綴

    Args:
        project_model: 機器型號（例如：G4L3-ZX1-LAX2-000 或 G4L3-ZX1-LAX2）

    Returns:
        List[Dict]: QVL 資料列表，如果找不到則返回 None
    """
    try:
        logger.info(f"正在查找機器型號 {project_model} 的 QVL 資料")

        # 1. 直接匹配完整型號
        matching_collections = db_service.find_matching_qvl_collections(project_model)

        if not matching_collections and '-' in project_model:
            logger.info(f"直接匹配 {project_model} 失敗，嘗試移除數字後綴")

            # 2. 移除最後的數字後綴（如 -000）再嘗試匹配
            parts = project_model.split('-')
            if len(parts) >= 4 and parts[-1].isdigit():
                shortened_model = '-'.join(parts[:-1])
                logger.info(f"嘗試匹配縮短型號: {shortened_model}")
                matching_collections = db_service.find_matching_qvl_collections(shortened_model)

        if not matching_collections:
            logger.warning(f"未找到與 {project_model} 相關的 QVL collections")
            return None

        # 選擇第一個匹配的 collection（通常是最準確的）
        selected_collection = matching_collections[0]
        logger.info(f"選擇 QVL collection: {selected_collection}")

        # 獲取 collection 資料
        qvl_data = db_service.get_qvl_data(selected_collection)

        if not qvl_data:
            logger.warning(f"QVL collection {selected_collection} 中沒有資料")
            return None

        logger.info(f"成功獲取 {len(qvl_data)} 筆 QVL 資料")
        return qvl_data

    except Exception as e:
        logger.error(f"獲取 QVL 資料時發生錯誤: {e}")
        return None

def extract_components(qvl_data: List[Dict]) -> Dict[str, Optional[Dict]]:
    """
    從 QVL 資料中隨機提取各類零件

    Args:
        qvl_data: QVL 資料列表

    Returns:
        Dict: 包含 barebone, cpu, memory, storage 的字典
    """
    try:
        components = {
            "barebone": None,
            "cpu": None,
            "memory": None,
            "storage": None
        }

        # 分類零件
        barebone_items = []
        cpu_items = []
        memory_items = []
        storage_items = []

        for item in qvl_data:
            if not isinstance(item, dict):
                continue

            group_name = item.get("groupName", "").upper()
            description = item.get("description", "").upper()

            # 分類邏輯
            if group_name == "BAREBONE":
                barebone_items.append(item)
            elif group_name == "CPU" or any(keyword in description for keyword in ["CPU", "PROCESSOR", "XEON", "CORE", "RYZEN"]):
                cpu_items.append(item)
            elif group_name == "MEMORY" or any(keyword in description for keyword in ["MEMORY", "RAM", "DDR", "DIMM"]):
                memory_items.append(item)
            elif group_name == "STORAGE" or any(keyword in description for keyword in ["SSD", "NVME", "SATA", "STORAGE", "DRIVE", "HDD"]):
                storage_items.append(item)

        # 隨機選擇各類零件
        if barebone_items:
            components["barebone"] = random.choice(barebone_items)
            logger.info(f"選擇 BAREBONE: {components['barebone'].get('gbtSn', 'Unknown')}")

        if cpu_items:
            components["cpu"] = random.choice(cpu_items)
            logger.info(f"選擇 CPU: {components['cpu'].get('gbtSn', 'Unknown')}")

        if memory_items:
            components["memory"] = random.choice(memory_items)
            logger.info(f"選擇 MEMORY: {components['memory'].get('gbtSn', 'Unknown')}")

        if storage_items:
            components["storage"] = random.choice(storage_items)
            logger.info(f"選擇 STORAGE: {components['storage'].get('gbtSn', 'Unknown')}")

        return components

    except Exception as e:
        logger.error(f"提取零件時發生錯誤: {e}")
        return {
            "barebone": None,
            "cpu": None,
            "memory": None,
            "storage": None
        }

def format_component_info(component: Optional[Dict]) -> str:
    """
    格式化單個零件資訊

    Args:
        component: 零件資訊字典

    Returns:
        str: 格式化後的零件資訊
    """
    if not component:
        return "未找到相關資料"

    try:
        gbt_sn = component.get("gbtSn", "未知編號")
        description = component.get("description", "無描述")
        specification = component.get("specification", "無規格資訊")
        power_consumption = component.get("powerConsumption", "未知功耗")

        return f"{gbt_sn} - {description} - {specification} - {power_consumption}"

    except Exception as e:
        logger.error(f"格式化零件資訊時發生錯誤: {e}")
        return "格式化失敗"

def format_l10_response(project_model: str, components: Dict[str, Optional[Dict]]) -> str:
    """
    格式化最終的 L10 表格回覆

    Args:
        project_model: 機器型號
        components: 零件字典

    Returns:
        str: 完整的 L10 表格回覆
    """
    try:
        response = f"以下為您選擇的L10表:\n\n{project_model}\n"

        barebone_info = format_component_info(components.get("barebone"))
        cpu_info = format_component_info(components.get("cpu"))
        memory_info = format_component_info(components.get("memory"))
        storage_info = format_component_info(components.get("storage"))

        response += f"Barebone: {barebone_info}\n"
        response += f"CPU： {cpu_info}\n"
        response += f"MEMORY： {memory_info}\n"
        response += f"STORAGE： {storage_info}\n"

        return response

    except Exception as e:
        logger.error(f"格式化 L10 回覆時發生錯誤: {e}")
        return f"❌ 生成 L10 表格時發生錯誤: {str(e)}"

async def generate_l10_table(user_query: str) -> str:
    """
    主要的 L10 表格生成函數

    Args:
        user_query: 用戶查詢內容

    Returns:
        str: L10 表格回覆或錯誤訊息
    """
    try:
        logger.info(f"開始生成 L10 表格，用戶輸入: {user_query}")

        # 1. 解析用戶選擇的機器型號
        project_model = parse_selected_machine(user_query)
        if not project_model:
            return "❌ 無法識別您選擇的機器型號，請提供完整的機器型號（例如：R283-Z90-AAD1-000）"

        # 2. 獲取 QVL 資料
        qvl_data = get_qvl_collection_data(project_model)
        if not qvl_data:
            return f"❌ 未找到機器型號 {project_model} 對應的 QVL 資料"

        # 3. 提取各類零件
        components = extract_components(qvl_data)

        # 4. 檢查是否至少找到一個零件
        if not any(components.values()):
            return f"❌ 在 QVL 資料中未找到任何有效的零件資訊"

        # 5. 格式化並返回結果
        result = format_l10_response(project_model, components)
        logger.info("成功生成 L10 表格")
        return result

    except Exception as e:
        logger.error(f"生成 L10 表格時發生錯誤: {e}")
        return f"❌ 生成 L10 表格時發生錯誤: {str(e)}"