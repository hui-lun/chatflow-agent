#!/usr/bin/env python3
# genL10.py - L10表格生成功能
import logging
import re
import random
from typing import List, Dict, Any, Optional
from pymongo import MongoClient
from ..database import db_service
from ..llm import get_llm

logger = logging.getLogger(__name__)

def get_spec_mongodb_connection():
    """建立並回傳 MongoDB spec collection 連接"""
    try:
        uri = f"mongodb://admin:password@mongodb:27017/"
        client = MongoClient(uri)
        client.admin.command('ping')
        db = client["spec"]
        collection = db["spec-all"]
        return collection
    except Exception as e:
        raise RuntimeError(f"連接 MongoDB spec 失敗: {e}")

def check_multiple_gbt_sn_configs(machine_model: str) -> List[str]:
    """
    檢查指定機器型號是否有多個不同的 gbtSn 配置

    Args:
        machine_model: 機器型號（例如：R283-Z90-AAD1-000）

    Returns:
        List[str]: 所有可用的 gbtSn 列表，如果只有一個或沒有則返回空列表
    """
    try:
        collection = get_spec_mongodb_connection()

        # 搜尋完全匹配的 ProjectModel
        results = list(collection.find({"ProjectModel": machine_model}, {"gbtSn": 1, "_id": 0}))

        if not results:
            # 如果沒找到完全匹配，嘗試模糊搜尋
            regex_pattern = f"^{re.escape(machine_model)}"
            results = list(collection.find({"ProjectModel": {"$regex": regex_pattern}}, {"gbtSn": 1, "_id": 0}))

        if not results:
            logger.info(f"未找到機器型號 {machine_model} 的任何配置")
            return []

        # 提取所有不同的 gbtSn
        gbt_sn_list = []
        for result in results:
            gbt_sn = result.get("gbtSn")
            if gbt_sn and gbt_sn not in gbt_sn_list:
                gbt_sn_list.append(gbt_sn)

        # 如果只有一個 gbtSn，返回空列表（表示不需要用戶選擇）
        if len(gbt_sn_list) <= 1:
            return []

        # 排序並返回多個配置
        gbt_sn_list.sort()
        logger.info(f"機器型號 {machine_model} 找到 {len(gbt_sn_list)} 個不同的 gbtSn 配置")
        return gbt_sn_list

    except Exception as e:
        logger.error(f"檢查多個 gbtSn 配置時發生錯誤: {e}")
        return []

def format_multiple_gbt_sn_options(machine_model: str, gbt_sn_list: List[str]) -> str:
    """
    格式化多個 gbtSn 選項的顯示，使用與 standalone_search.py 相同的格式

    Args:
        machine_model: 機器型號
        gbt_sn_list: gbtSn 列表

    Returns:
        str: 格式化後的選項顯示
    """
    try:
        response = f"🔍 **機器型號 {machine_model} 找到 {len(gbt_sn_list)} 個不同的 gbtSn 配置**\n\n"
        response += "📋 **可用的 gbtSn 選項**：\n"

        for i, gbt_sn in enumerate(gbt_sn_list, 1):
            response += f"{i}. {gbt_sn}\n"

        response += f"\n💡 **使用方式**：\n"
        response += f"• 請指定特定的 gbtSn 來查看詳細規格\n"
        response += f"• 例如：我要 '{machine_model}' 且 gbtSn 為 '{gbt_sn_list[0]}' 的L10\n"

        return response

    except Exception as e:
        logger.error(f"格式化多個 gbtSn 選項時發生錯誤: {e}")
        return f"❌ 顯示 gbtSn 選項時發生錯誤: {str(e)}"

def parse_selected_machine(user_query: str) -> dict:
    """
    從用戶輸入中提取選擇的機器型號和可能的 gbtSn

    Args:
        user_query: 用戶查詢內容

    Returns:
        dict: 包含 'machine_model' 和 'gbt_sn' 的字典，如果找不到則對應值為 None
    """
    try:
        result = {"machine_model": None, "gbt_sn": None}

        # 使用正則表達式匹配機器型號格式
        # 支援格式：R283-Z90-AAD1-000, R283-Z90-AAD1, G4L3-ZX1-LAX2-000 等
        # 移除 word boundary \b 以支援緊接在中文字後的機器型號
        model_pattern = r'[A-Z0-9]{3,4}-[A-Z0-9]{2,4}-[A-Z0-9]{3,4}(?:-[A-Z0-9]{1,3})?'
        model_matches = re.findall(model_pattern, user_query.upper())

        # 匹配 gbtSn 格式 (通常以 6 開頭，長度 16-20 位)
        gbt_sn_pattern = r'\b6[A-Z0-9]{15,19}\b'
        gbt_sn_matches = re.findall(gbt_sn_pattern, user_query.upper())

        if model_matches:
            result["machine_model"] = model_matches[0]
            logger.info(f"找到機器型號: {result['machine_model']}")

        if gbt_sn_matches:
            result["gbt_sn"] = gbt_sn_matches[0]
            logger.info(f"找到 gbtSn: {result['gbt_sn']}")

        # 如果正則表達式找不到機器型號，使用 LLM 輔助分析
        if not result["machine_model"]:
            llm = get_llm()
            analysis_prompt = f"""
請從以下用戶輸入中提取機器型號和 gbtSn。用戶可能說「選擇 XXX」或「我要 XXX」等：

用戶輸入："{user_query}"

請以 JSON 格式回覆：
{{
  "machine_model": "機器型號" 或 null,
  "gbt_sn": "gbtSn" 或 null
}}

機器型號通常格式為：字母數字-字母數字-字母數字（-可選後綴）
gbtSn 通常以 6 開頭，長度為 16-20 位的字母數字組合

請只回覆 JSON，不要包含其他文字。
"""

            response = llm.invoke(analysis_prompt).content.strip()
            logger.info(f"LLM 分析結果: {response}")

            try:
                llm_result = re.search(r'\{.*\}', response, re.DOTALL)
                if llm_result:
                    import json
                    parsed = json.loads(llm_result.group())
                    if parsed.get("machine_model") and re.match(model_pattern, parsed["machine_model"].upper()):
                        result["machine_model"] = parsed["machine_model"].upper()
                    if parsed.get("gbt_sn") and re.match(gbt_sn_pattern, parsed["gbt_sn"].upper()):
                        result["gbt_sn"] = parsed["gbt_sn"].upper()
            except:
                logger.warning("無法解析 LLM JSON 回覆")

        return result

    except Exception as e:
        logger.error(f"解析選擇的機器型號時發生錯誤: {e}")
        return {"machine_model": None, "gbt_sn": None}

def get_qvl_collection_data(project_model: str, target_gbt_sn: Optional[str] = None) -> Optional[List[Dict]]:
    """
    根據機器型號獲取對應的 QVL collection 資料，可選擇指定特定的 gbtSn
    支援智能匹配：如果完整型號找不到，會嘗試移除數字後綴

    Args:
        project_model: 機器型號（例如：G4L3-ZX1-LAX2-000 或 G4L3-ZX1-LAX2）
        target_gbt_sn: 可選的特定 gbtSn，如果指定則只返回匹配該 gbtSn 的 collection 資料

    Returns:
        List[Dict]: QVL 資料列表，如果找不到則返回 None
    """
    try:
        logger.info(f"正在查找機器型號 {project_model} 的 QVL 資料")
        if target_gbt_sn:
            logger.info(f"目標 gbtSn: {target_gbt_sn}")

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

        # 3. 如果指定了特定的 gbtSn，過濾出包含該 gbtSn 的 collection
        selected_collection = None
        if target_gbt_sn:
            for collection_name in matching_collections:
                if target_gbt_sn in collection_name:
                    selected_collection = collection_name
                    logger.info(f"根據 gbtSn {target_gbt_sn} 選擇 collection: {selected_collection}")
                    break

            if not selected_collection:
                logger.warning(f"未找到包含 gbtSn {target_gbt_sn} 的 QVL collection")
                return None
        else:
            # 如果沒有指定 gbtSn，選擇第一個匹配的 collection（通常是最準確的）
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
        response = f"以下為您選擇的L10:\n\n{project_model}\n"

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
    支援多 gbtSn 配置的智能處理邏輯

    Args:
        user_query: 用戶查詢內容

    Returns:
        str: L10 表格回覆或錯誤訊息
    """
    try:
        logger.info(f"開始生成 L10 表格，用戶輸入: {user_query}")

        # 1. 解析用戶選擇的機器型號和可能的 gbtSn
        parsed_result = parse_selected_machine(user_query)
        machine_model = parsed_result.get("machine_model")
        target_gbt_sn = parsed_result.get("gbt_sn")

        if not machine_model:
            return "❌ 無法識別您選擇的機器型號，請提供完整的機器型號（例如：R283-Z90-AAD1-000）"

        logger.info(f"解析結果 - 機器型號: {machine_model}, gbtSn: {target_gbt_sn}")

        # 2. 如果沒有指定 gbtSn，檢查是否有多個 gbtSn 配置
        if not target_gbt_sn:
            available_gbt_sns = check_multiple_gbt_sn_configs(machine_model)
            if available_gbt_sns:
                # 有多個配置，顯示選項清單讓用戶選擇
                return format_multiple_gbt_sn_options(machine_model, available_gbt_sns)

        # 3. 獲取 QVL 資料（如果有指定 gbtSn 則過濾）
        qvl_data = get_qvl_collection_data(machine_model, target_gbt_sn)
        if not qvl_data:
            if target_gbt_sn:
                return f"❌ 未找到機器型號 {machine_model} 且 gbtSn 為 {target_gbt_sn} 對應的 QVL 資料"
            else:
                return f"❌ 未找到機器型號 {machine_model} 對應的 QVL 資料"

        # 4. 提取各類零件
        components = extract_components(qvl_data)

        # 5. 檢查是否至少找到一個零件
        if not any(components.values()):
            return f"❌ 在 QVL 資料中未找到任何有效的零件資訊"

        # 6. 格式化並返回結果
        result = format_l10_response(machine_model, components)
        logger.info("成功生成 L10 表格")
        return result

    except Exception as e:
        logger.error(f"生成 L10 表格時發生錯誤: {e}")
        return f"❌ 生成 L10 表格時發生錯誤: {str(e)}"