#!/usr/bin/env python3
# recommend_search.py - 機器型號推薦搜尋功能
import os
import json
import logging
import re
import yaml
from typing import List, Dict, Any, Tuple
from pymongo import MongoClient
from ..llm import get_llm

# 設置日誌
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

HARD_CONSTRAINTS = ["cpu_brand", "cooling_type", "form_factor", "gpu_support"]

def get_mongodb_connection():
    """建立並回傳 MongoDB spec collection 連接"""
    try:
        uri = f"mongodb://admin:password@mongodb:27017/"
        client = MongoClient(uri)
        client.admin.command('ping')  # 測試連線
        db = client["spec"]
        collection = db["spec-all"]
        return collection
    except Exception as e:
        raise RuntimeError(f"連接 MongoDB 失敗: {e}")

def parse_user_requirements(user_query: str) -> Dict[str, Any]:
    """使用 LLM 分析用戶需求，提取關鍵硬體要求"""
    try:
        llm = get_llm()
        analysis_prompt = f"""
請分析以下用戶需求，提取具體的硬體要求。請以 JSON 格式回覆：

用戶需求："{user_query}"

請分析並提取以下資訊，如果某項目未提及則設為 null：
{{
  "cpu_brand": "AMD" 或 "Intel" 或 null,
  "cpu_requirements": "具體CPU需求描述" 或 null,
  "memory_requirements": "記憶體需求" 或 null,
  "storage_requirements": "儲存需求" 或 null,
  "cooling_type": "Air Cooling (氣冷)" 或 "Liquid Cooling (液冷)" 或 null,
  "gpu_support": true/false 或 null,
  "gpu_requirements": "GPU需求描述" 或 null,
  "form_factor": "機架規格需求" 或 null,
  "pcie_requirements": "PCIe需求" 或 null,
  "network_requirements": "網路需求" 或 null,
  "power_requirements": "電源需求" 或 null,
  "application_type": "應用類型" 或 null,
  "special_requirements": ["其他特殊需求"] 或 []
}}

請只回覆JSON，不要包含其他說明文字。
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
    """檢查是否符合硬性需求"""
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

    # 冷卻方式
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

    # 機架規格
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

    return True, reasons

def match_machine_to_requirements(machine_data: Dict[str, Any], requirements: Dict[str, Any]) -> Tuple[int, List[str]]:
    """比對單一機器資料與用戶需求，回傳匹配分數和匹配理由"""
    score = 0
    reasons = []
    try:
        # 先檢查硬性需求
        ok, hard_reasons = check_hard_constraints(machine_data, requirements)
        if not ok:
            return 0, []
        reasons.extend(hard_reasons)

        # 加分條件 (Soft Constraints)
        if requirements.get("memory_requirements"):
            memory_req = requirements["memory_requirements"].lower()
            memory_type = machine_data.get("MemoryType", "").lower()
            if "ddr5" in memory_req and "ddr5" in memory_type:
                score += 10
                reasons.append("支援 DDR5 記憶體")
            elif "ddr4" in memory_req and "ddr4" in memory_type:
                score += 10
                reasons.append("支援 DDR4 記憶體")

        if requirements.get("storage_requirements"):
            storage_req = requirements["storage_requirements"].lower()
            raw_storage_info = machine_data.get("RAWstorageInfo", "").lower()
            if raw_storage_info:
                storage_keywords = {
                    "nvme": "支援 NVMe 儲存",
                    "sata": "支援 SATA 儲存",
                    "m.2": "支援 M.2 儲存",
                    "u.2": "支援 U.2 儲存",
                }
                matched = [reason for key, reason in storage_keywords.items()
                           if key in storage_req and key in raw_storage_info]
                if matched:
                    score += 10
                    reasons.extend(matched)

        if requirements.get("application_type"):
            app_type_req = requirements["application_type"].lower()
            app_info = machine_data.get("appInfo", "").lower()
            if app_type_req in app_info or app_info in app_type_req:
                score += 10
                reasons.append(f"適合 {machine_data.get('appInfo', '')} 應用")

        # 基本分數 + 狀態
        if machine_data.get("ProjectModel", ""):
            score += 10
        status_stage = machine_data.get("statusStage", "").upper()
        if status_stage == "MP":
            score += 10
            reasons.append("量產階段產品")
        elif status_stage == ["DVT", "PVT"]:
            score += 5
            reasons.append(f"{status_stage} 階段產品")

    except Exception as e:
        logger.warning(f"匹配過程發生錯誤: {e}")

    return score, reasons

def search_recommended_machines(user_query: str) -> str:
    """根據用戶需求搜尋推薦的機器型號"""
    try:
        logger.info(f"開始處理推薦查詢: {user_query}")
        requirements = parse_user_requirements(user_query)
        logger.info(f"解析的需求: {requirements}")
        collection = get_mongodb_connection()
        all_machines = list(collection.find({}, {"_id": 0}))
        logger.info(f"從資料庫獲取 {len(all_machines)} 台機器資料")
        if not all_machines:
            return "❌ 資料庫中沒有找到機器資料"

        machine_scores = []
        for machine in all_machines:
            score, reasons = match_machine_to_requirements(machine, requirements)
            if score > 0 or reasons:  # 必須通過硬性需求
                machine_scores.append({
                    "machine": machine,
                    "score": score,
                    "reasons": reasons
                })

        if not machine_scores:
            return f"❌ 未找到符合硬性需求的機器：\n{user_query}\n\n建議您調整需求條件或聯繫技術支援。"

        machine_scores.sort(key=lambda x: x["score"], reverse=True)
        top_recommendations = machine_scores[:10]

        response = "🤖 **機器型號推薦結果**\n\n"
        response += f"根據您的需求：「{user_query}」\n\n"
        response += f"為您推薦以下 {len(top_recommendations)} 台機器：\n\n"
        for i, item in enumerate(top_recommendations, 1):
            m = item["machine"]
            reasons = item["reasons"]
            response += f"**{i}. {m.get('ProjectModel', '未知型號')}** (匹配分數: {item['score']})\n"
            if m.get("gbtSn"): response += f"   • GIGABYTE 序號: {m['gbtSn']}\n"
            sys = m.get("systemInfo", [{}])[0]
            if isinstance(sys, dict):
                if sys.get("densityFormFactor"): response += f"   • 機架規格: {sys['densityFormFactor']}\n"
                if sys.get("CPUInfo"): response += f"   • 處理器: {sys['CPUInfo']}\n"
                if sys.get("Cooling_Type"): response += f"   • 散熱方式: {sys['Cooling_Type']}\n"
            if m.get("appInfo"): response += f"   • 應用類別: {m['appInfo']}\n"
            if m.get("statusStage"): response += f"   • 開發階段: {m['statusStage']}\n"
            if reasons: response += f"   • 匹配原因: {', '.join(reasons)}\n"
            response += "\n"

        response += "💡 **後續建議**：\n"
        response += "• 您可以使用具體型號查詢詳細規格資訊\n"
        response += "• 建議根據實際預算和效能需求進行最終選擇\n"
        response += "• 如需更詳細的規格比較，請提供具體型號\n"
        return response

    except Exception as e:
        logger.error(f"推薦搜尋發生錯誤: {e}")
        return f"推薦搜尋發生錯誤: {str(e)}"

async def recommend_search(user_query: str) -> str:
    """異步版本的推薦搜尋功能"""
    return search_recommended_machines(user_query)
