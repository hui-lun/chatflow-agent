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

def get_mongodb_connection():
    """建立並回傳 MongoDB spec collection 連接"""
    try:
        uri = f"mongodb://admin:password@mongodb:27017/"
        client = MongoClient(uri)
        
        # 測試連線是否成功
        client.admin.command('ping')
        
        db = client["spec"]
        collection = db["spec-all"]
        return collection
    
    except Exception as e:
        raise RuntimeError(f"連接 MongoDB 失敗: {e}")

def parse_user_requirements(user_query: str) -> Dict[str, Any]:
    """
    使用 LLM 分析用戶需求，提取關鍵硬體要求
    
    Args:
        user_query: 用戶的需求描述
        
    Returns:
        Dict: 解析後的硬體需求
    """
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
  "cooling_type": "Air Cooling" 或 "Liquid Cooling" 或 null,
  "gpu_support": true/false (是否需要GPU支援),
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
        
        # 嘗試解析JSON回應
        try:
            requirements = json.loads(response)
            return requirements
        except json.JSONDecodeError:
            # 如果JSON解析失敗，嘗試從回應中提取JSON部分
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                requirements = json.loads(json_match.group())
                return requirements
            else:
                logger.warning("無法解析LLM回應為JSON，使用預設需求分析")
                return {}
                
    except Exception as e:
        logger.error(f"需求分析失敗: {e}")
        return {}

def match_machine_to_requirements(machine_data: Dict[str, Any], requirements: Dict[str, Any]) -> Tuple[int, List[str]]:
    """
    比對單一機器資料與用戶需求，回傳匹配分數和匹配理由
    
    Args:
        machine_data: 機器規格資料
        requirements: 用戶需求
        
    Returns:
        Tuple[int, List[str]]: (匹配分數, 匹配理由列表)
    """
    score = 0
    reasons = []
    
    try:
        # CPU 品牌匹配
        if requirements.get("cpu_brand"):
            cpu_brand_req = requirements["cpu_brand"].lower()
            machine_cpu_brand = machine_data.get("CPUBrand", "").lower()
            system_info = machine_data.get("systemInfo", [])
            
            # 檢查主要 CPUBrand 欄位
            if cpu_brand_req in machine_cpu_brand:
                score += 20
                reasons.append(f"支援 {requirements['cpu_brand']} CPU")
            
            # 檢查 systemInfo 中的 CPU 資訊
            elif isinstance(system_info, list) and system_info:
                for sys in system_info:
                    if isinstance(sys, dict):
                        sys_cpu_brand = sys.get("CPUBrand", "").lower()
                        if cpu_brand_req in sys_cpu_brand:
                            score += 20
                            reasons.append(f"支援 {requirements['cpu_brand']} CPU")
                            break
        
        # 冷卻方式匹配
        if requirements.get("cooling_type"):
            cooling_req = requirements["cooling_type"].lower()
            system_info = machine_data.get("systemInfo", [])
            
            if isinstance(system_info, list) and system_info:
                for sys in system_info:
                    if isinstance(sys, dict):
                        cooling_type = sys.get("Cooling_Type", "").lower()
                        if "liquid" in cooling_req and "liquid" in cooling_type:
                            score += 10
                            reasons.append("支援液冷散熱")
                            break
                        elif "air" in cooling_req and "air" in cooling_type:
                            score += 10
                            reasons.append("支援氣冷散熱")
                            break
        
        # GPU 支援匹配
        if requirements.get("gpu_support"):
            pcie_info = machine_data.get("pcieInfo", [])
            expansion_slot = machine_data.get("ExpansionSlot", "")
            system_info = machine_data.get("systemInfo", [])
            
            # 檢查 PCIe 插槽資訊
            gpu_support_found = False
            if isinstance(pcie_info, list):
                for pcie in pcie_info:
                    if isinstance(pcie, dict):
                        device_type = pcie.get("deviceType", "").lower()
                        if "pcie" in device_type:
                            score += 20
                            reasons.append("支援 PCIe GPU 擴充")
                            gpu_support_found = True
                            break
            
            # 檢查 systemInfo 中的 GPU 資訊
            if not gpu_support_found and isinstance(system_info, list) and system_info:
                for sys in system_info:
                    if isinstance(sys, dict):
                        gpu_module = sys.get("GPUModule", "").lower()
                        if "pcie" in gpu_module or "sxm" in gpu_module:
                            score += 20
                            reasons.append(f"支援 GPU ({sys.get('GPUModule', 'PCIe')})")
                            gpu_support_found = True
                            break
            
            # 檢查擴充插槽描述
            if not gpu_support_found and "pcie" in expansion_slot.lower():
                score += 20
                reasons.append("具備 PCIe 擴充插槽")
        
        # 記憶體類型匹配
        if requirements.get("memory_requirements"):
            memory_req = requirements["memory_requirements"].lower()
            memory_type = machine_data.get("MemoryType", "").lower()
            
            if "ddr5" in memory_req and "ddr5" in memory_type:
                score += 10
                reasons.append("支援 DDR5 記憶體")
            elif "ddr4" in memory_req and "ddr4" in memory_type:
                score += 10
                reasons.append("支援 DDR4 記憶體")
        
        # 儲存需求匹配
        if requirements.get("storage_requirements"):
            storage_req = requirements["storage_requirements"].lower()
            storage_info = machine_data.get("storageInfo", [])
            
            if isinstance(storage_info, list):
                for storage in storage_info:
                    if isinstance(storage, dict):
                        storage_type = storage.get("type", "").lower()
                        if "nvme" in storage_req and "nvme" in storage_type:
                            score += 10
                            reasons.append("支援 NVMe 儲存")
                            break
                        elif "sata" in storage_req and "sata" in storage_type:
                            score += 10
                            reasons.append("支援 SATA 儲存")
                            break
        
        # 機架規格匹配
        if requirements.get("form_factor"):
            form_factor_req = requirements["form_factor"].lower()
            system_info = machine_data.get("systemInfo", [])
            
            if isinstance(system_info, list) and system_info:
                for sys in system_info:
                    if isinstance(sys, dict):
                        density_form = sys.get("densityFormFactor", "").lower()
                        if form_factor_req in density_form or density_form in form_factor_req:
                            score += 10
                            reasons.append(f"符合 {sys.get('densityFormFactor', '')} 機架規格")
                            break
        
        # 應用類型匹配
        if requirements.get("application_type"):
            app_type_req = requirements["application_type"].lower()
            app_info = machine_data.get("appInfo", "").lower()
            
            if app_type_req in app_info or app_info in app_type_req:
                score += 5
                reasons.append(f"適合 {machine_data.get('appInfo', '')} 應用")
        
        # 基本可用性檢查
        project_model = machine_data.get("ProjectModel", "")
        if project_model:
            score += 5  # 基本分數
            
        # 狀態檢查 - 偏好 MP (量產) 階段的產品
        status_stage = machine_data.get("statusStage", "").upper()
        if status_stage == "MP":
            score += 5
            reasons.append("量產階段產品")
        elif status_stage == "DVT":
            score += 2
            reasons.append(f"{status_stage} 階段產品")
            
    except Exception as e:
        logger.warning(f"匹配過程發生錯誤: {e}")
    
    return score, reasons

def search_recommended_machines(user_query: str) -> str:
    """
    根據用戶需求搜尋推薦的機器型號
    
    Args:
        user_query: 用戶需求描述
        
    Returns:
        str: 格式化的推薦結果
    """
    try:
        logger.info(f"開始處理推薦查詢: {user_query}")
        
        # 1. 分析用戶需求
        requirements = parse_user_requirements(user_query)
        logger.info(f"解析的需求: {requirements}")
        
        # 2. 連接資料庫並獲取所有機器資料
        collection = get_mongodb_connection()
        all_machines = list(collection.find({}, {"_id": 0}))
        logger.info(f"從資料庫獲取 {len(all_machines)} 台機器資料")
        
        if not all_machines:
            return "❌ 資料庫中沒有找到機器資料"
        
        # 3. 計算每台機器的匹配分數
        machine_scores = []
        for machine in all_machines:
            score, reasons = match_machine_to_requirements(machine, requirements)
            if score > 0:  # 只保留有匹配分數的機器
                machine_scores.append({
                    "machine": machine,
                    "score": score,
                    "reasons": reasons
                })
        
        # 4. 按分數排序
        machine_scores.sort(key=lambda x: x["score"], reverse=True)
        
        # 5. 格式化回應
        if not machine_scores:
            return f"❌ 很抱歉，未找到符合以下需求的機器：\n{user_query}\n\n建議您調整需求條件或聯繫技術支援。"
        
        # 取前10個推薦結果
        top_recommendations = machine_scores[:10]
        
        response = "🤖 **機器型號推薦結果**\n\n"
        response += f"根據您的需求：「{user_query}」\n\n"
        response += f"為您推薦以下 {len(top_recommendations)} 台機器：\n\n"
        
        for i, item in enumerate(top_recommendations, 1):
            machine = item["machine"]
            score = item["score"]
            reasons = item["reasons"]
            
            project_model = machine.get("ProjectModel", "未知型號")
            gbt_sn = machine.get("gbtSn", "")
            app_info = machine.get("appInfo", "")
            status_stage = machine.get("statusStage", "")
            
            # 獲取系統資訊
            system_info = machine.get("systemInfo", [])
            form_factor = ""
            cpu_info = ""
            cooling_type = ""
            
            if isinstance(system_info, list) and system_info:
                sys = system_info[0]
                if isinstance(sys, dict):
                    form_factor = sys.get("densityFormFactor", "")
                    cpu_info = sys.get("CPUInfo", "")
                    cooling_type = sys.get("Cooling_Type", "")
            
            response += f"**{i}. {project_model}** (匹配分數: {score})\n"
            if gbt_sn:
                response += f"   • GIGABYTE 序號: {gbt_sn}\n"
            if form_factor:
                response += f"   • 機架規格: {form_factor}\n"
            if app_info:
                response += f"   • 應用類別: {app_info}\n"
            if status_stage:
                response += f"   • 開發階段: {status_stage}\n"
            if cpu_info:
                response += f"   • 處理器: {cpu_info}\n"
            if cooling_type:
                response += f"   • 散熱方式: {cooling_type}\n"
            
            if reasons:
                response += f"   • 匹配原因: {', '.join(reasons)}\n"
            
            response += "\n"
        
        # 添加後續建議
        response += "💡 **後續建議**：\n"
        response += "• 您可以使用具體型號查詢詳細規格資訊\n"
        response += "• 建議根據實際預算和效能需求進行最終選擇\n"
        response += "• 如需更詳細的規格比較，請提供具體型號\n"
        
        return response
        
    except Exception as e:
        error_msg = f"推薦搜尋發生錯誤: {str(e)}"
        logger.error(error_msg)
        return error_msg

async def recommend_search(user_query: str) -> str:
    """
    異步版本的推薦搜尋功能
    
    Args:
        user_query: 用戶需求描述
        
    Returns:
        str: 推薦結果
    """
    return search_recommended_machines(user_query)