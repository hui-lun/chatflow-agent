import os
import asyncio
from dotenv import load_dotenv
import httpx # 引入非同步 HTTP 客戶端函式庫

# RAG-Anything 和 LightRAG 核心元件
from raganything import RAGAnything
from lightrag import LightRAG
from lightrag.utils import EmbeddingFunc
from lightrag.llm.openai import openai_complete_if_cache
from lightrag.kg.shared_storage import initialize_pipeline_status
# Use the official Milvus implementation from LightRAG
# from lightrag.kg.milvus_impl import MilvusVectorDBStorage


# --- 1. 從你的 .env 檔案中取得 API 位址 ---
load_dotenv()
VLLM_API_BASE = os.getenv("VLLM_API_BASE")
EMBEDDING_API_BASE = os.getenv("EMBEDDING_API_BASE")
LOCAL_LLM_MODEL_NAME = os.getenv("LOCAL_LLM_MODEL_NAME", "local-llm")
LOCAL_EMBEDDING_MODEL_NAME = os.getenv("LOCAL_EMBEDDING_MODEL_NAME", "local-embedding")

# --- 2. 自訂 LLM 和 Embedding 函式 ---
# LLM 函式：一個專為你的 vLLM 服務器設計的自訂非同步函式
def llm_model_func(prompt, system_prompt=None, history_messages=[], **kwargs):
    return openai_complete_if_cache(
        "gemma-3-27b-it",
        prompt,
        system_prompt=system_prompt,
        history_messages=history_messages,
        api_key="EMPTY",
        base_url=f"{VLLM_API_BASE}",
        **kwargs,
    )

async def custom_llm_model_func(prompt, **kwargs):
    url = f"{VLLM_API_BASE}/chat/completions"
    data = {
        "messages": [{"role": "user", "content": prompt}]
    }
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, json=data)
            response.raise_for_status()
            return response.json()["choices"][0]["message"]["content"]
    except httpx.HTTPStatusError as e:
        print(f"呼叫 LLM 時發生 HTTP 錯誤: {e}")
        return f"無法從 LLM 取得回應: {e}"
    except Exception as e:
        print(f"呼叫 LLM 時發生其他錯誤: {e}")
        return f"從 LLM 獲取回應時發生錯誤: {e}"

# Embedding 函式：與上一版相同，因為這部分沒問題
async def custom_embed_func(texts, **kwargs):
    url = f"{EMBEDDING_API_BASE}/embed"
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(url, json={"texts": texts})
        response.raise_for_status()
        # The corrected line: directly return the list of vectors.
        return response.json()["embeddings"]

async def main():
    print("--- 正在初始化 RAG 系統 ---")

    # Set the MILVUS_URI environment variable to connect to your Docker container
    # The MilvusVectorDBStorage class will automatically pick this up.
    os.environ['MILVUS_URI'] = 'http://localhost:19530'
    print(f"Set MILVUS_URI to: {os.environ['MILVUS_URI']}")

    # Define the kwargs for the Milvus vector DB storage class
    # The official implementation requires `cosine_better_than_threshold`
    milvus_kwargs = {"cosine_better_than_threshold": 0.7}
    
    # 建立 LightRAG 實例，並將自訂的函式傳入
    lightrag_instance = LightRAG(
        llm_model_func=llm_model_func, # 傳入新的 LLM 
        embedding_func=EmbeddingFunc(embedding_dim=1024, func=custom_embed_func),
        vector_storage="MilvusVectorDBStorage",
        vector_db_storage_cls_kwargs=milvus_kwargs,
    )
    await lightrag_instance.initialize_storages()
    await initialize_pipeline_status()

    # 實例化 RAGAnything，並將 LightRAG 實例傳入
    # 這是官方推薦的做法，確保所有組件正確連接
    rag_system = RAGAnything(
        llm_model_func=llm_model_func,
        embedding_func=EmbeddingFunc(embedding_dim=1024, func=custom_embed_func),
    )
    
    print("LightRAG 和 RAG-Anything 初始化完成。")

    # --- 範例：處理文件並提問 ---
    # pdf_path = "./test.pdf"
    pdf_path = "./123.pdf"
    if not os.path.exists(pdf_path):
        print(f"\n錯誤: 找不到測試文件 '{pdf_path}'\n")
        print("請確保 test.pdf 檔案與此腳本位於同一目錄。")
        return # 找不到文件時直接結束

    print(f"\n正在處理文件: {pdf_path}")
    # 注意: ingest 是非同步方法，必須使用 await
    await rag_system.process_document_complete(
            file_path=pdf_path,
            parse_method="auto"
    )
    print("文件處理完成。")

    # 提出一個測試問題
    print("\n--- 執行測試查詢 ---")
    # question = "What are the AMD EPYC 9004 series CPUs with the Genoa Code Name?"
    question = "Which Module Supplier of the B85M-D3H-A DDR3 1333 supply?"
    print(f"問題: {question}")
    
    try:
        # 注意: query 也是非同步方法，必須使用 await
        response = await rag_system.aquery(question, mode="local")
        # response = await rag_system.query_with_multimodal(question, mode="local")
        
        print("\n模型回應:")
        if hasattr(response, 'answer'):
            print(response.answer)
        else:
            print(response)
    except Exception as e:
        print(f"查詢過程中發生錯誤: {e}")

if __name__ == "__main__":
    # 將 mineru 的路徑加到環境變數中，確保 subprocess 可以找到它
    mineru_path = '/home/test/.local/bin/mineru'
    mineru_dir = os.path.dirname(mineru_path)
    if 'PATH' in os.environ and mineru_dir not in os.environ['PATH']:
        os.environ['PATH'] = f"{mineru_dir}:{os.environ['PATH']}"
    else:
        os.environ['PATH'] = mineru_dir

    # 啟動非同步主函式
    asyncio.run(main())