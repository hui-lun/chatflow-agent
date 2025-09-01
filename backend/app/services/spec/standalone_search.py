#!/usr/bin/env python3
# standalone_search.py - 獨立的 spec search 腳本，避免 MRO 衝突
import asyncio
import os
import json
import sys
import argparse
import logging
import yaml
from mcp.client.session import ClientSession
from mcp.client.stdio import stdio_client, StdioServerParameters
from langchain_mcp_adapters.tools import load_mcp_tools
from langgraph.prebuilt import create_react_agent
from langchain_core.prompts import ChatPromptTemplate
from ..llm import get_llm
from ..database import db_service

# 設置日誌
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def spec_search(user_query: str) -> str:
    """
    執行 spec search 查詢並回傳結果
    """
    try:
        # Start the MCP Server using stdio transport
        server_params = StdioServerParameters(
            command="python",
            args=[os.path.join(os.path.dirname(__file__), "server.py")]
        )

        async with stdio_client(server_params) as (reader, writer):
            async with ClientSession(reader, writer) as session:
                # Initialize the MCP session
                await session.initialize()

                # Load the tools provided by the MCP Server
                tools = await load_mcp_tools(session)
                logger.info(f"Loaded {len(tools)} MCP tools: {[tool.name for tool in tools]}")

                # Use the project's LLM configuration
                llm = get_llm()
                logger.info(f"LLM configured with base URL: {llm.openai_api_base}")

                # Create a ReAct agent with reasoning and tool usage capabilities
                agent = create_react_agent(llm, tools)
                logger.info("ReAct agent created successfully")

                # 載入系統提示詞
                prompts_file = os.path.join(os.path.dirname(__file__), "system_prompts.yaml")
                with open(prompts_file, 'r', encoding='utf-8') as f:
                    prompts = yaml.safe_load(f)
                
                # 建立 ChatPromptTemplate
                prompt_template = ChatPromptTemplate.from_messages([
                    ("system", prompts['bdm_assistant']['system_prompt']),
                    ("human", "{user_query}")
                ])
                
                # 格式化消息
                messages = prompt_template.format_messages(user_query=user_query)
                
                # Run agent reasoning + tool selection + response
                logger.info(f"Running agent with query: {user_query}")
                result = await agent.ainvoke({"messages": messages})
                
                # Log the result details
                logger.info(f"Agent completed. Result type: {type(result)}")
                if isinstance(result, dict):
                    messages_result = result.get("messages", [])
                    logger.info(f"Result contains {len(messages_result)} messages")
                    for i, msg in enumerate(messages_result):
                        logger.info(f"Message {i}: {type(msg).__name__} - {str(msg)[:100]}...")

                # Return the final AI response
                final_response = result.get("messages")[-1].content
                logger.info(f"Final response: {final_response[:200]}...")
                
                # 檢查是否找到完整機器型號，並查詢 QVL 資料
                qvl_info = await check_and_get_qvl_data(final_response, user_query)
                
                # 如果有 QVL 資料，附加到回應中
                if qvl_info:
                    final_response += f"\n\n{qvl_info}"
                
                return final_response
                
    except Exception as e:
        return f"Spec search error: {str(e)}"

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
        
        # 從用戶查詢中提取型號模式 (例如 R283-Z90-AAD1, R163-SG2-AAC1)
        # 匹配格式：字母+3位數字-字母數字組合(3位)-3個字母+1位數字
        model_pattern = r'[A-Z]\d{3}-[A-Z0-9]{3}-[A-Z]{3}\d'
        user_models = re.findall(model_pattern, user_query)
        
        if not user_models:
            logger.info("未在用戶查詢中找到完整機器型號格式")
            return ""
        
        project_model = user_models[0]  # 取第一個找到的型號
        logger.info(f"找到機器型號: {project_model}")
        
        # 查詢 QVL 相關 collections
        matching_collections = db_service.find_matching_qvl_collections(project_model)
        
        if not matching_collections:
            logger.info(f"未找到與 {project_model} 相關的 QVL collections")
            return ""
        
        logger.info(f"找到 {len(matching_collections)} 個相關的 QVL collections: {matching_collections}")
        
        # 組成 QVL 資訊回應
        qvl_response = f"🔍 QVL 資料查詢結果：\n\n"
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