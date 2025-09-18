#!/usr/bin/env python3
# recommend_search.py - 嚴格 Hard Constraints 的機器型號推薦搜尋
import os
import json
import logging
import re
from typing import List, Dict, Any, Tuple
from pymongo import MongoClient
from ..llm import get_llm

# 設置日誌
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 所有 Hard Constraints
HARD_CONSTRAINTS = [
    "cpu_brand",
    "cooling_type",
    "form_factor",
    "gpu_support",
    "memory_type",
    "raw_storage_info",
    "application_type",
]

def get_mongodb_connection():
    """建立並回傳 MongoDB spec collection 連接"""
    try:
        uri = f"mongodb://admin:password@mongodb:27017/"
        client = MongoClient(uri)
        client.admin.command('ping')
        db = client["spec"]
        collection = db["spec-all"]
        return collection
    except Exception as e:
        raise RuntimeError(f"連接 MongoDB 失敗: {e}")

def parse_user_requirements(user_query: str) -> Dict[str, Any]:
    """使用 LLM 分析用戶需求，提取硬體需求"""
    try:
        llm = get_llm()
        analysis_prompt = f"""
請分析以下用戶需求，提取具體的硬體要求。請以 JSON 格式回覆：

用戶需求："{user_query}"

請分析並提取以下資訊，如果未提及則設為 null：
{{
  "cpu_brand": "AMD" 或 "Intel" 或 null,
  "cooling_type": "Air Cooling (氣冷)" 或 "Liquid Cooling (液冷)" 或 null,
  "form_factor": "機架規格需求" 或 null,
  "gpu_support": true/false 或 null,
  "memory_type": "DDR4/DDR5" 或 null,
  "raw_storage_info": "NVMe / SATA / U.2 / M.2" 或 null,
  "application_type": "應用類型" 或 null
}}
請只回覆 JSON，不要包含其他文字。
"""
        response = llm.invoke(analysis_prompt).content.strip()
        logger.info(f"LLM 需求分析回應: {response}")
        try:
            return json.loads(response)
        except json.JSONDecodeError:
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                return json.loads(json_match.group())
            return {}
    except Exception as e:
        logger.error(f"需求分析失敗: {e}")
        return {}

def check_hard_constraints(machine: Dict[str, Any], requirements: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """檢查是否完全符合 Hard Constraints"""
    reasons = []

    # CPU 品牌
    if requirements.get("cpu_brand"):
        cpu_brand_req = requirements["cpu_brand"].lower()
        cpu_brand = machine.get("CPUBrand", "").lower()
        system_info = machine.get("systemInfo", [])
        if cpu_brand_req not in cpu_brand:
            if not any(cpu_brand_req in str(sys.get("CPUBrand", "")).lower() for sys in system_info if isinstance(sys, dict)):
                return False, []
        reasons.append(f"支援 {requirements['cpu_brand']} CPU")

    # 散熱方式
    if requirements.get("cooling_type"):
        cooling_req = requirements["cooling_type"].lower()
        system_info = machine.get("systemInfo", [])
        matched = False
        for sys in system_info:
            if isinstance(sys, dict):
                cooling_type = sys.get("Cooling_Type", "").lower()
                if "liquid" in cooling_req and "liquid" in cooling_type:
                    matched, _reason = True, "支援液冷散熱"
                    reasons.append(_reason)
                    break
                elif "air" in cooling_req and "air" in cooling_type:
                    matched, _reason = True, "支援氣冷散熱"
                    reasons.append(_reason)
                    break
        if not matched:
            return False, []

    # 機架規格（保留指定寫法）
    if requirements.get("form_factor"):
        form_factor_req = requirements["form_factor"].lower()
        system_info = machine.get("systemInfo", [])
        matched = False
        for sys in system_info:
            if isinstance(sys, dict):
                density_form = sys.get("densityFormFactor", "").lower()
                if form_factor_req in density_form or density_form in form_factor_req:
                    matched = True
                    reasons.append(f"符合 {sys.get('densityFormFactor', '')} 機架規格")
                    break
        if not matched:
            return False, []

    # GPU 支援
    if requirements.get("gpu_support"):
        pcie_info = machine.get("pcieInfo", [])
        expansion_slot = machine.get("ExpansionSlot", "")
        system_info = machine.get("systemInfo", [])
        gpu_support_found = False
        for pcie in pcie_info:
            if isinstance(pcie, dict) and "pcie" in pcie.get("deviceType", "").lower():
                gpu_support_found = True
                reasons.append("支援 PCIe GPU 擴充")
                break
        if not gpu_support_found:
            for sys in system_info:
                if isinstance(sys, dict):
                    gpu_module = sys.get("GPUModule", "").lower()
                    if "pcie" in gpu_module or "sxm" in gpu_module:
                        gpu_support_found = True
                        reasons.append(f"支援 GPU ({sys.get('GPUModule', 'PCIe')})")
                        break
        if not gpu_support_found and "pcie" in expansion_slot.lower():
            gpu_support_found = True
            reasons.append("具備 PCIe 擴充插槽")
        if not gpu_support_found:
            return False, []

    # 記憶體類型
    if requirements.get("memory_type"):
        req = requirements["memory_type"].lower()
        mem = machine.get("MemoryType", "").lower()
        if req not in mem:
            return False, []
        reasons.append(f"支援 {requirements['memory_type']} 記憶體")

    # 儲存類型
    if requirements.get("raw_storage_info"):
        req = requirements["raw_storage_info"].lower()
        raw = machine.get("RAWstorageInfo", "").lower()
        if req not in raw:
            return False, []
        reasons.append(f"支援 {requirements['raw_storage_info']} 儲存")

    # 應用類型
    if requirements.get("application_type"):
        req = requirements["application_type"].lower()
        app = str(machine.get("appInfo", "")).lower()
        if req not in app and app not in req:
            return False, []
        reasons.append(f"適合 {machine.get('appInfo', '')} 應用")

    return True, reasons

def search_recommended_machines(user_query: str) -> str:
    """根據用戶需求搜尋推薦的機器型號"""
    try:
        requirements = parse_user_requirements(user_query)
        collection = get_mongodb_connection()
        all_machines = list(collection.find({}, {"_id": 0}))

        results = []
        for machine in all_machines:
            ok, reasons = check_hard_constraints(machine, requirements)
            if ok:
                results.append({"machine": machine, "reasons": reasons})

        if not results:
            return f"❌ 未找到符合需求的機器：\n{user_query}\n\n建議您調整需求條件或聯繫技術支援。"

        # 只取前 10 台
        top_recommendations = results[:10]

        model_list = [item["machine"].get("ProjectModel", "未知型號") for item in top_recommendations]

        response = f"🤖 **機器型號推薦結果**\n\n根據您的需求：「{user_query}」\n\n"
        response += f"為您找到 {len(top_recommendations)} 台符合需求的機器：\n\n"
        response += "📋 **符合需求的型號清單**：\n" + ", ".join(model_list) + "\n\n"
        for i, item in enumerate(top_recommendations, 1):
            m = item["machine"]
            response += f"**{i}. {m.get('ProjectModel', '未知型號')}**\n"
            if m.get("gbtSn"): response += f"   • GIGABYTE 序號: {m['gbtSn']}\n"
            sys = m.get("systemInfo", [{}])[0]
            if isinstance(sys, dict):
                if sys.get("densityFormFactor"): response += f"   • 機架規格: {sys['densityFormFactor']}\n"
                if sys.get("CPUInfo"): response += f"   • 處理器: {sys['CPUInfo']}\n"
                if sys.get("Cooling_Type"): response += f"   • 散熱方式: {sys['Cooling_Type']}\n"
            if m.get("appInfo"): response += f"   • 應用類別: {m['appInfo']}\n"
            if item["reasons"]: response += f"   • 匹配原因: {', '.join(item['reasons'])}\n"
            response += "\n"
        
        response += "💡 **後續建議**：\n"
        response += "• 您可以使用具體型號查詢詳細規格資訊\n"
        response += "• 如需更詳細的規格比較，請提供具體型號\n"

        return response

    except Exception as e:
        logger.error(f"推薦搜尋發生錯誤: {e}")
        return f"推薦搜尋發生錯誤: {str(e)}"

async def recommend_search(user_query: str) -> str:
    """異步版本的推薦搜尋功能"""
    return search_recommended_machines(user_query)
