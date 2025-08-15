#!/usr/bin/env python3
# standalone_search.py - 獨立的 spec search 腳本，避免 MRO 衝突
import asyncio
import os
import json
import sys
import argparse
import logging
from mcp.client.session import ClientSession
from mcp.client.stdio import stdio_client, StdioServerParameters
from langchain_mcp_adapters.tools import load_mcp_tools
from langgraph.prebuilt import create_react_agent
from langchain_core.messages import HumanMessage, SystemMessage
from ..llm import get_llm

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

                # System + User messages (agent will decide which tool to invoke)
                messages = [
                    SystemMessage(
                        content="""你是 BDM 專案資料助手。你必須使用 get_machine_info_by_model 工具來查詢機器型號資訊。

重要指示：
1. 對於任何型號查詢，你必須先調用 get_machine_info_by_model 工具
2. 從用戶問題中提取型號名稱（例如：R283-Z90-AAD1-000）
3. 使用該型號作為參數調用工具
4. 根據工具返回的結果來回答用戶問題
5. 如果工具返回錯誤，請如實報告錯誤信息
6. 絕對不要憑空猜測或給出沒有數據支持的回答

請現在使用工具查詢用戶提到的型號資訊。""" 
                    ),
                    HumanMessage(
                        content=user_query
                    )
                ]
                
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
                return final_response
                
    except Exception as e:
        return f"Spec search error: {str(e)}"

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