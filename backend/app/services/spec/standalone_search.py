#!/usr/bin/env python3
# standalone_search.py - 機器型號規格搜尋腳本
import asyncio
import os
import json
import sys
import argparse
import logging
import re
import yaml
from typing import List, Dict, Any, Optional
from pymongo import MongoClient
from langchain_core.prompts import ChatPromptTemplate
from ..llm import get_llm
from ..database import db_service

# 設置日誌
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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

def load_system_prompts() -> Dict[str, Any]:
    """載入 system_prompts.yaml 檔案"""
    try:
        # 取得當前檔案的目錄路徑
        current_dir = os.path.dirname(os.path.abspath(__file__))
        yaml_path = os.path.join(current_dir, "system_prompts.yaml")

        with open(yaml_path, 'r', encoding='utf-8') as file:
            prompts = yaml.safe_load(file)
            logger.info("成功載入 system_prompts.yaml")
            return prompts
    except Exception as e:
        logger.error(f"載入 system_prompts.yaml 失敗: {e}")
        return {}

def parse_machine_model(user_query: str) -> Dict[str, Any]:
    """使用 LLM 分析用戶查詢，提取機器型號或 gbtSn"""
    try:
        llm = get_llm()
        analysis_prompt = f"""
請分析以下用戶查詢，提取機器型號或 gbtSn。請以 JSON 格式回覆：

用戶查詢："{user_query}"

請提取：
1. 機器型號，格式如：R283-Z90-AAD1-000、R283-Z90-AAD1、R283-Z90、R283-Z90-
2. gbtSn（訂購編號），格式如：6NR283Z90DR000AAD1、6NR283Z90DR000ABD1

{{
  "machine_model": "機器型號" 或 null,
  "gbt_sn": "gbtSn" 或 null,
  "query_type": "machine_model" 或 "gbt_sn" 或 "both",
  "is_complete": true/false,
  "is_prefix_search": true/false
}}

注意：
- 機器型號必須轉換為大寫
- gbtSn 通常以數字+字母組合開始，較長的編號
- 如果查詢中同時包含機器型號和 gbtSn，query_type 設為 "both"
請只回覆 JSON，不要包含其他文字。
"""
        response = llm.invoke(analysis_prompt).content.strip()
        logger.info(f"LLM 機器型號分析回應: {response}")
        try:
            return json.loads(response)
        except json.JSONDecodeError:
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                return json.loads(json_match.group())
            return {}
    except Exception as e:
        logger.error(f"機器型號分析失敗: {e}")
        return {}

async def spec_search(user_query: str) -> str:
    """
    執行 spec search 查詢並回傳結果
    """
    try:
        # 分析用戶查詢提取機器型號或 gbtSn
        model_info = parse_machine_model(user_query)
        machine_model = model_info.get("machine_model")
        gbt_sn = model_info.get("gbt_sn")
        query_type = model_info.get("query_type", "machine_model")

        # 連接資料庫
        collection = get_mongodb_connection()

        # 根據查詢類型選擇搜尋方式
        if query_type == "gbt_sn" and gbt_sn:
            # 直接根據 gbtSn 搜尋
            logger.info(f"根據 gbtSn 搜尋: {gbt_sn}")
            spec_result = search_by_gbt_sn(collection, gbt_sn)

        elif query_type == "both" and machine_model and gbt_sn:
            # 同時指定了機器型號和 gbtSn，進行精確搜尋
            machine_model = machine_model.upper()
            logger.info(f"精確搜尋 - 機器型號: {machine_model}, gbtSn: {gbt_sn}")

            result = collection.find_one({
                "ProjectModel": machine_model,
                "gbtSn": gbt_sn
            }, {"_id": 0})

            if result:
                spec_result = format_machine_spec(result)
            else:
                spec_result = f"❌ 未找到機器型號 '{machine_model}' 且 gbtSn 為 '{gbt_sn}' 的規格資訊。"

        elif machine_model:
            # 根據機器型號搜尋
            machine_model = machine_model.upper()
            logger.info(f"根據機器型號搜尋: {machine_model}")

            # 使用正則表達式檢查是否為完整機器型號
            # 完整型號格式：XXX-YYY-ZZZ 或 XXX-YYY-ZZZ-000
            # 修正邏輯：3段式和4段式都是完整型號
            complete_model_pattern = r'^[A-Z0-9]{3,4}-[A-Z0-9]{2,4}-[A-Z0-9]{3,4}(-[A-Z0-9]{1,3})?$'
            is_complete_model = re.match(complete_model_pattern, machine_model)

            if is_complete_model:
                # 完整機器型號，直接搜尋
                spec_result = search_complete_model(collection, machine_model)
            else:
                # 不完整機器型號，展示相關前綴
                spec_result = search_prefix_models(collection, machine_model)
        else:
            return "❓ 無法從查詢中識別出機器型號或 gbtSn，請提供正確的格式。"

        # 檢查是否為單一機器規格回應，只有這種情況才顯示 QVL 資料
        # 如果回應包含 "gbtSn 選項" 或 "相關型號清單"，表示是列表回應，不顯示 QVL
        if ("gbtSn 選項" not in spec_result and
            "相關型號清單" not in spec_result and
            "❌" not in spec_result):
            qvl_info = await check_and_get_qvl_data(spec_result, user_query)
            # 如果有 QVL 資料，附加到回應中
            if qvl_info:
                spec_result += f"\n\n{qvl_info}"

        return spec_result

    except Exception as e:
        return f"Spec search error: {str(e)}"

def search_complete_model(collection, machine_model: str) -> str:
    """搜尋完整機器型號的規格資訊"""
    try:
        # 搜尋完全匹配的 ProjectModel（可能有多個不同的 gbtSn）
        results = list(collection.find({"ProjectModel": machine_model}, {"_id": 0}))

        if not results:
            # 如果沒找到完全匹配，嘗試模糊搜尋（例如 G893-ZX1-AAX2 可能對應 G893-ZX1-AAX2-000）
            regex_pattern = f"^{re.escape(machine_model)}"
            results = list(collection.find({"ProjectModel": {"$regex": regex_pattern}}, {"_id": 0}))

            if not results:
                return f"❌ 未找到機器型號 {machine_model} 的規格資訊。"

            if len(results) == 1:
                # 只找到一個模糊匹配結果，直接返回詳細規格
                response = format_machine_spec(results[0])
                return response

            # 找到多個模糊匹配結果，顯示所有相關型號
            model_list = [result.get("ProjectModel", "未知型號") for result in results]
            model_list = list(set(model_list))  # 去重
            model_list.sort()

            response = f"🔍 **找到 {len(model_list)} 個與 {machine_model} 相關的機器型號**\n\n"
            response += "📋 **相關型號清單**：\n"

            # 分組顯示，每行最多5個型號
            for i in range(0, len(model_list), 5):
                group = model_list[i:i+5]
                response += "• " + ", ".join(group) + "\n"

            response += f"\n💡 **建議**：\n"
            response += "• 請使用完整的機器型號進行詳細規格查詢\n"
            response += f"• 例如：查詢 '{model_list[0]}' 的詳細規格\n"

            return response

        elif len(results) == 1:
            # 找到完全匹配的型號，只有一個 gbtSn，直接返回詳細規格
            response = format_machine_spec(results[0])
            return response

        else:
            # 找到完全匹配的型號，但有多個不同的 gbtSn，列出所有選項
            gbt_sn_list = []
            for result in results:
                gbt_sn = result.get("gbtSn", "未知")
                gbt_sn_list.append(gbt_sn)

            # 去重並排序
            gbt_sn_list = list(set(gbt_sn_list))
            gbt_sn_list.sort()

            response = f"🔍 **機器型號 {machine_model} 找到 {len(gbt_sn_list)} 個不同的 gbtSn 配置**\n\n"
            response += "📋 **可用的 gbtSn 選項**：\n"

            for i, gbt_sn in enumerate(gbt_sn_list, 1):
                response += f"{i}. {gbt_sn}\n"

            response += f"\n💡 **使用方式**：\n"
            response += f"• 請指定特定的 gbtSn 來查看詳細規格\n"
            response += f"• 例如：查詢 '{machine_model}' 且 gbtSn 為 '{gbt_sn_list[0]}' 的規格\n"
            

            return response

    except Exception as e:
        logger.error(f"搜尋完整機器型號失敗: {e}")
        return f"搜尋機器型號 {machine_model} 時發生錯誤: {str(e)}"

def search_by_gbt_sn(collection, gbt_sn: str) -> str:
    """根據 gbtSn 搜尋機器規格資訊"""
    try:
        # 搜尋指定的 gbtSn
        result = collection.find_one({"gbtSn": gbt_sn}, {"_id": 0})

        if not result:
            return f"❌ 未找到 gbtSn '{gbt_sn}' 的規格資訊。"

        # 找到匹配的結果，返回詳細規格
        response = format_machine_spec(result)
        return response

    except Exception as e:
        logger.error(f"搜尋 gbtSn 失敗: {e}")
        return f"搜尋 gbtSn {gbt_sn} 時發生錯誤: {str(e)}"

def search_prefix_models(collection, machine_prefix: str) -> str:
    """搜尋不完整機器型號的前綴，展示相關型號"""
    try:
        # 使用正則表達式搜尋以該前綴開頭的型號
        regex_pattern = f"^{re.escape(machine_prefix)}"
        results = list(collection.find({"ProjectModel": {"$regex": regex_pattern}}, {"ProjectModel": 1, "gbtSn": 1, "_id": 0}))

        if not results:
            return f"❌ 未找到以 {machine_prefix} 開頭的機器型號。"

        # 提取所有匹配的型號
        model_list = [result.get("ProjectModel", "未知型號") for result in results]
        model_list = list(set(model_list))  # 去重
        model_list.sort()  # 排序

        response = f"🔍 **找到 {len(model_list)} 個以 {machine_prefix} 開頭的機器型號**\n\n"
        response += "📋 **相關型號清單**：\n"

        # 分組顯示，每行最多5個型號
        for i in range(0, len(model_list), 5):
            group = model_list[i:i+5]
            response += "• " + ", ".join(group) + "\n"

        response += f"\n💡 **建議**：\n"
        response += "• 請使用完整的機器型號進行詳細規格查詢\n"
        response += f"• 例如：查詢 '{model_list[0]}' 的詳細規格\n"

        return response

    except Exception as e:
        logger.error(f"搜尋前綴機器型號失敗: {e}")
        return f"搜尋前綴 {machine_prefix} 時發生錯誤: {str(e)}"

def format_machine_spec(machine_data: Dict) -> str:
    """使用 system_prompts.yaml 和 ChatPromptTemplate 格式化機器規格資訊"""
    try:
        # 載入 system prompts
        prompts = load_system_prompts()

        # 如果載入失敗，直接回傳錯誤訊息
        if not prompts or 'bdm_assistant' not in prompts:
            logger.error("無法載入 system_prompts.yaml")
            model = machine_data.get("ProjectModel", "未知型號")
            return f"❌ 無法載入系統配置檔案，無法格式化機器型號 {model} 的規格資訊。"

        # 建立 ChatPromptTemplate
        prompt_template = ChatPromptTemplate.from_messages([
            ("system", prompts['bdm_assistant']['system_prompt']),
            ("human", "{user_query}")
        ])

        # 準備機器資料作為查詢內容
        machine_json = json.dumps(machine_data, ensure_ascii=False, indent=2)
        user_query = f"請根據以下機器資料，按照指定格式整理並回覆機器規格資訊：\n\n{machine_json}"

        # 使用 LLM 生成格式化回應
        llm = get_llm()
        messages = prompt_template.format_messages(user_query=user_query)
        response = llm.invoke(messages).content.strip()

        logger.info("成功使用 ChatPromptTemplate 格式化機器規格")
        return response

    except Exception as e:
        logger.error(f"使用 ChatPromptTemplate 格式化機器規格失敗: {e}")
        model = machine_data.get("ProjectModel", "未知型號")
        return f"❌ 格式化機器型號 {model} 的規格資訊時發生錯誤: {str(e)}"


async def check_and_get_qvl_data(spec_response: str, user_query: str) -> str:
    """
    檢查 spec 搜尋回應中是否包含完整機器型號，並查詢對應的 QVL 資料

    Args:
        spec_response: spec 搜尋的回應內容
        user_query: 使用者的原始查詢

    Returns:
        str: QVL 查詢結果的描述，如果沒有找到則回傳空字串
    """
    try:
        import re

        # 與 main.py 保持一致的正則表達式
        model_pattern = r'\b[A-Z0-9]{3,4}-[A-Z0-9]{2,4}-[A-Z0-9]{3,4}\b'

        # 先從 spec_response 中尋找機器型號（這會是正確格式的）
        spec_models = re.findall(model_pattern, spec_response)

        # 如果 spec_response 中沒有找到，則從 user_query 中尋找並轉換為大寫
        if not spec_models:
            # 使用不分大小寫的正則表達式尋找機器型號
            case_insensitive_pattern = r'\b[A-Za-z0-9]{3,4}-[A-Za-z0-9]{2,4}-[A-Za-z0-9]{3,4}\b'
            user_models = re.findall(case_insensitive_pattern, user_query)

            if not user_models:
                logger.info("未在查詢中找到完整機器型號格式")
                return ""

            # 轉換為大寫
            project_model = user_models[0].upper()
        else:
            project_model = spec_models[0]

        logger.info(f"找到機器型號: {project_model}")

        # 檢查是否在 spec_response 中包含 gbtSn 資訊
        gbt_sn_pattern = r'\b6[A-Z0-9]{15,20}\b'
        spec_gbt_sns = re.findall(gbt_sn_pattern, spec_response)
        user_gbt_sns = re.findall(gbt_sn_pattern, user_query)

        # 如果找到特定的 gbtSn，只顯示對應的 QVL 資料庫
        target_gbt_sn = None
        if spec_gbt_sns:
            target_gbt_sn = spec_gbt_sns[0]
        elif user_gbt_sns:
            target_gbt_sn = user_gbt_sns[0]

        # 如果機器型號不是完整格式（例如 G893-ZX1-AAX2），嘗試查找完整版本
        if not re.match(model_pattern, project_model):
            # 先從資料庫中查找以此為前綴的完整型號
            try:
                collection = get_mongodb_connection()
                regex_pattern = f"^{re.escape(project_model)}"
                results = list(collection.find({"ProjectModel": {"$regex": regex_pattern}}, {"ProjectModel": 1, "_id": 0}))

                if results:
                    # 使用第一個找到的完整型號
                    project_model = results[0]["ProjectModel"]
                    logger.info(f"找到對應的完整型號: {project_model}")
            except Exception as db_e:
                logger.warning(f"查找完整型號時發生錯誤: {db_e}")

        # 查詢 QVL 相關 collections
        matching_collections = db_service.find_matching_qvl_collections(project_model)

        if not matching_collections:
            logger.info(f"未找到與 {project_model} 相關的 QVL collections")
            return ""

        # 如果有指定 gbtSn，只保留包含該 gbtSn 的 collection
        if target_gbt_sn:
            filtered_collections = [col for col in matching_collections if target_gbt_sn in col]
            if filtered_collections:
                matching_collections = filtered_collections
                logger.info(f"根據 gbtSn {target_gbt_sn} 過濾後，找到 {len(matching_collections)} 個相關的 QVL collections")

        logger.info(f"找到 {len(matching_collections)} 個相關的 QVL collections: {matching_collections}")

        # 組成 QVL 資訊回應
        qvl_response = f"🔍 QVL 資料查詢結果：\n\n"
        if target_gbt_sn and len(matching_collections) == 1:
            qvl_response += f"為機器型號 {project_model} 和 gbtSn {target_gbt_sn} 找到對應的 QVL 資料庫：\n"
        else:
            qvl_response += f"為機器型號 {project_model} 找到 {len(matching_collections)} 個相關的 QVL 資料庫：\n"

        for i, collection_name in enumerate(matching_collections, 1):
            qvl_response += f"{i}. {collection_name}\n"

        qvl_response += f"\n📁 您可以下載這些 QVL 資料檔案。"

        return qvl_response

    except Exception as e:
        logger.error(f"檢查和獲取 QVL 資料時發生錯誤: {e}")
        return f"QVL 查詢過程中發生錯誤: {str(e)}"

async def main():
    """主函數"""
    parser = argparse.ArgumentParser(description='Spec Search Tool')
    parser.add_argument('--query', required=True, help='查詢內容')
    parser.add_argument('--output-json', action='store_true', help='輸出 JSON 格式')
    
    args = parser.parse_args()
    
    try:
        logger.info(f"執行 spec search 查詢: {args.query}")
        result = await spec_search(args.query)
        
        if args.output_json:
            # 輸出 JSON 格式給 FastAPI 使用
            output = {
                "success": True,
                "result": result,
                "query": args.query
            }
            print(json.dumps(output, ensure_ascii=False))
        else:
            # 普通輸出格式
            print(result)
            
    except Exception as e:
        if args.output_json:
            error_output = {
                "success": False,
                "error": str(e),
                "query": args.query
            }
            print(json.dumps(error_output, ensure_ascii=False))
        else:
            print(f"錯誤: {e}")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())