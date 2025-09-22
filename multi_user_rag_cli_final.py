import os
import asyncio
import json
from pathlib import Path
from dotenv import load_dotenv
import httpx
from functools import partial
import atexit

# RAG-Anything 和 LightRAG 核心元件
from raganything import RAGAnything, RAGAnythingConfig
from lightrag import LightRAG
from lightrag.utils import EmbeddingFunc
from lightrag.llm.openai import openai_complete_if_cache
from lightrag.kg.shared_storage import initialize_pipeline_status

# --- Monkey Patching Setup ---
try:
    from lightrag.kg import milvus_impl, json_kv_impl
    from lightrag.kg.milvus_impl import MilvusVectorDBStorage as OriginalMilvusStorage
    from lightrag.kg.json_kv_impl import JsonKVStorage as OriginalJsonKVStorage
    from pymilvus import FieldSchema, CollectionSchema, DataType
except ImportError as e:
    print(f"錯誤：無法從 lightrag.kg 導入儲存類別。請確認 LightRAG 安裝路徑。錯誤: {e}")
    # 定義虛擬類別以避免腳本立即崩潰
    class OriginalMilvusStorage: pass
    class OriginalJsonKVStorage: pass
    class milvus_impl: MilvusVectorDBStorage = None
    class json_kv_impl: JsonKVStorage = None
    class FieldSchema: pass
    class CollectionSchema: pass
    class DataType: pass

# --- 狀態管理 (非同步) ---
STATE_FILE = Path("processing_state.json")

async def load_state_async():
    """非同步讀取狀態檔案"""
    if not await asyncio.to_thread(STATE_FILE.exists):
        return {}
    def read_json():
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    try:
        return await asyncio.to_thread(read_json)
    except json.JSONDecodeError:
        return {{}} # 如果檔案毀損或為空，返回一個空狀態

async def save_state_async(state):
    """非同步寫入狀態檔案"""
    def write_json():
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=4, ensure_ascii=False)
    await asyncio.to_thread(write_json)
def is_file_processed(user_id: str, file_path: str, state: dict) -> bool:
    abs_path = str(Path(file_path).resolve())
    return abs_path in state.get(user_id, [])
def mark_file_as_processed(user_id: str, file_path: str, state: dict):
    abs_path = str(Path(file_path).resolve())
    if user_id not in state: state[user_id] = []
    if abs_path not in state[user_id]: state[user_id].append(abs_path)
    return state

# --- API 設定 ---
load_dotenv()
VLLM_API_BASE = os.getenv("VLLM_API_BASE")
EMBEDDING_API_BASE = os.getenv("EMBEDDING_API_BASE")

# --- Embedding 函式 ---
async def custom_embed_func(texts, **kwargs):
    async with httpx.AsyncClient(timeout=30.0) as client:
        # response = await client.post(f"{EMBEDDING_API_BASE}/embed", json={{ "texts": texts }})
        response = await client.post(f"{EMBEDDING_API_BASE}/embed", json={"texts": texts})
        response.raise_for_status()
        return response.json()["embeddings"]

# --- RAG 系統建立函式 ---
async def create_user_rag_system(user_id: str) -> RAGAnything:
    print(f"--- 正在為使用者 '{user_id}' 建立並初始化 RAG 實例 ---")
    os.environ['MILVUS_URI'] = 'http://localhost:19530'

    # Set a common storage directory
    user_storage_dir = f"rag_storage_{user_id.replace('-', '_').replace(' ', '_').lower()}"
    os.makedirs(user_storage_dir, exist_ok=True)
    print(f"--- Common storage directory: {user_storage_dir} ---")
    print(f"--- User-specific workspace: {user_id} ---")

    # ===================================================================
    # The UserAwareLLM is kept as a defense-in-depth measure, but the primary
    # cache isolation is now handled by the `workspace` parameter.
    # ===================================================================
    class UserAwareLLM:
        def __init__(self, user_id: str):
            self.user_id = user_id
            print(f"UserAwareLLM: Initialized for user '{self.user_id}'")

        def __call__(self, prompt: str, **kwargs):
            # GUARANTEED FIX: Prepend user_id to the prompt to ensure a unique cache key.
            user_specific_prompt = f"Internal User ID: {self.user_id}\n---\n{prompt}"
            
            # We can keep the hashing_kv just in case it's used elsewhere.
            kwargs['hashing_kv'] = json.dumps({'user_id': self.user_id}, sort_keys=True)

            return openai_complete_if_cache(
                "gemma-3-27b-it",
                user_specific_prompt,  # <-- Use the modified, user-specific prompt
                api_key="EMPTY",
                base_url=f"{VLLM_API_BASE}",
                **kwargs
            )

    user_specific_llm_model_func = UserAwareLLM(user_id)

    # ===================================================================
    # NEW: Create a user-aware wrapper for the embedding function to handle caching
    # ===================================================================
    class UserAwareEmbeddingFunc:
        def __init__(self, user_id: str, embed_func):
            self.user_id = user_id
            self.embed_func = embed_func
            print(f"UserAwareEmbeddingFunc: Initialized for user '{self.user_id}'")

        async def __call__(self, texts, **kwargs):
            
            # Add user_id to hashing_kv for cache isolation, converted to JSON string
            kwargs['hashing_kv'] = json.dumps({'user_id': self.user_id}, sort_keys=True)
            return await self.embed_func(texts, **kwargs)

    user_specific_embed_func = UserAwareEmbeddingFunc(user_id, custom_embed_func)

    # ===================================================================
    # Milvus storage is already user-aware, no changes needed here.
    # ===================================================================
    class MultiTenantMilvusStorage(OriginalMilvusStorage):
        def __init__(self, **kwargs):
            self.user_id = user_id
            super().__init__(**kwargs)
            print(f"MultiTenantMilvusStorage: Initialized for user '{self.user_id}', collection: {self.final_namespace}")

        def _create_schema_for_namespace(self) -> CollectionSchema:
            original_schema = super()._create_schema_for_namespace()
            user_id_field = FieldSchema(name="user_id", dtype=DataType.VARCHAR, max_length=256, description="User ID for multi-tenancy filter")
            if "user_id" not in [field.name for field in original_schema.fields]:
                original_schema.fields.append(user_id_field)
                print(f"MultiTenantMilvusStorage ({self.final_namespace}): Added 'user_id' field to schema")
            return original_schema

        def _create_indexes_after_collection(self):
            super()._create_indexes_after_collection()
            try:
                print(f"MultiTenantMilvusStorage ({self.final_namespace}): Creating index for 'user_id' field...")
                self._client.create_index(collection_name=self.final_namespace, field_name="user_id", index_params={"index_type": "INVERTED"})
                print(f"MultiTenantMilvusStorage ({self.final_namespace}): Index for 'user_id' created successfully.")
            except Exception as e:
                if "index already exist" in str(e).lower():
                    print(f"MultiTenantMilvusStorage ({self.final_namespace}): Index on 'user_id' already exists.")
                else:
                    print(f"MultiTenantMilvusStorage ({self.final_namespace}): Error creating index for 'user_id': {e}")

        async def upsert(self, data: dict[str, dict[str, any]]) -> None:
            if not data: return
            print(f"MultiTenantMilvusStorage ({self.final_namespace}): Upserting {len(data)} records for user '{self.user_id}'")
            for key in data:
                data[key]["user_id"] = self.user_id
            original_meta_fields = self.meta_fields.copy()
            if "user_id" not in self.meta_fields:
                self.meta_fields.add("user_id")
            await super().upsert(data)
            self.meta_fields = original_meta_fields

        async def query(self, query: str, top_k: int, query_embedding: list[float] = None, expr: str = None, **kwargs) -> list[dict[str, any]]:
            print(f"MultiTenantMilvusStorage ({self.final_namespace}): Querying for user '{self.user_id}'")
            user_filter_expr = f"user_id == '{self.user_id}'"
            final_expr = f"({expr}) and {user_filter_expr}" if expr else user_filter_expr
            print(f"MultiTenantMilvusStorage ({self.final_namespace}): Using filter expression: \"{final_expr}\" " )
            if not query_embedding:
                if not query: raise ValueError("Either query or query_embedding must be provided.")
                query_embedding = (await custom_embed_func([query]))[0]
            output_fields = list(self.meta_fields)
            if "doc_id" not in output_fields: output_fields.append("doc_id")
            search_results = await asyncio.to_thread(
                self._client.search,
                collection_name=self.final_namespace,
                data=[query_embedding],
                filter=final_expr,
                limit=top_k,
                output_fields=output_fields
            )
            results = search_results[0] if search_results else []
            print(f"MultiTenantMilvusStorage ({self.final_namespace}): Query found {len(results)} results.")
            return results

    milvus_impl.MilvusVectorDBStorage = MultiTenantMilvusStorage
    print("--- Monkey Patch applied (MultiTenantMilvus) ---")

    milvus_kwargs = {"cosine_better_than_threshold": 0.7}

    lightrag_instance = LightRAG(
        # Use a common working directory
        working_dir=user_storage_dir,
        enable_llm_cache=True,
        llm_model_func=user_specific_llm_model_func,
        embedding_func=EmbeddingFunc(embedding_dim=1024, func=user_specific_embed_func),
        vector_storage="MilvusVectorDBStorage",
        vector_db_storage_cls_kwargs=milvus_kwargs,
    )
    await lightrag_instance.initialize_storages()
    await initialize_pipeline_status()

    rag_anything_config = RAGAnythingConfig(working_dir=user_storage_dir)

    original_atexit_register = atexit.register
    def dummy_atexit_register(func, *args, **kwargs):
        if hasattr(func, '__self__') and isinstance(func.__self__, RAGAnything):
            print("--- 已攔截並跳過對 RAGAnything.close 的 atexit 註冊 ---")
        else:
            original_atexit_register(func, *args, **kwargs)
    
    atexit.register = dummy_atexit_register

    rag_system = RAGAnything(
        lightrag=lightrag_instance,
        config=rag_anything_config,
        llm_model_func=user_specific_llm_model_func,
        embedding_func=user_specific_embed_func,
    )

    atexit.register = original_atexit_register
    print(f"--- 使用者 '{user_id}' 的 RAG 實例已準備就緒 ---")
        
    return rag_system




# --- 主 CLI 應用程式 ---
async def main():
    state = await load_state_async()
    current_user = None
    rag_system = None
    print("\n歡迎使用多使用者 RAG CLI 系統 (方案 A: 獨立 Collections)")
    print("="*50)
    print("  user <user_id>   - 切換到指定的使用者")
    print("  upload <file.pdf> - 為目前使用者上傳並處理 PDF 檔案")
    print("  query <question>   - 使用目前使用者的資料庫進行提問")
    print("  exit               - 離開程式")
    print("="*50)

    while True:
        prompt_str = f"({current_user}) > " if current_user else "> "
        command_line = input(prompt_str).strip()
        if not command_line: continue
        parts = command_line.split(" ", 1)
        command = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ""

        if command == "exit":
            print("正在離開程式...")
            break
        elif command == "user":
            if not args: print("錯誤: 請提供 user_id。"); continue
            if current_user != args:
                current_user = args
                print(f"已切換到使用者: {current_user}")
                rag_system = None
            else:
                print(f"已在使用者: {current_user} 的上下文中")
        elif command in ["upload", "query"]:
            if not current_user: print("錯誤: 請先使用 'user <user_id>' 指令設定使用者。"); continue
            if not args: print(f"錯誤: 請提供 {command} 內容。"); continue
            
            try:
                if rag_system is None:
                    rag_system = await create_user_rag_system(current_user)
                if not rag_system:
                    print("錯誤：RAG 系統未能成功初始化。")
                    continue

                if command == "upload":
                    pdf_path = args
                    if not Path(pdf_path).exists(): print(f"錯誤: 找不到檔案 '{pdf_path}'"); continue
                    if is_file_processed(current_user, pdf_path, state): print(f"檔案 '{pdf_path}' 已被處理過，跳過。"); continue
                    
                    print(f"正在為使用者 '{current_user}' 處理檔案: {pdf_path}")
                    await rag_system.process_document_complete(file_path=pdf_path, parse_method="auto")
                    print("文件處理完成。")
                    state = mark_file_as_processed(current_user, pdf_path, state)
                    await save_state_async(state)
                    print(f"已將 '{pdf_path}' 標記為已處理。")

                elif command == "query":
                    question = args
                    print(f"問題: {question}")

                    # 最終、唯一有效的修正：在呼叫 aquery 前，直接修改 question 字串
                    user_specific_question = f"Internal User ID: {current_user}\n---\n{question}"
                    response = await rag_system.aquery(user_specific_question, mode="hybrid")
                    
                    print("\n模型回應:")
                    print(getattr(response, 'answer', response))

            except Exception as e:
                print(f"處理指令 '{command}' 時發生錯誤: {e}")
        else:
            print(f"錯誤: 未知的指令 '{command}'")

if __name__ == "__main__":
    mineru_path = '/home/test/.local/bin/mineru'
    mineru_dir = os.path.dirname(mineru_path)
    if 'PATH' in os.environ and mineru_dir not in os.environ['PATH']:
        os.environ['PATH'] = f"{mineru_dir}:{os.environ['PATH']}"
    else:
        os.environ['PATH'] = mineru_dir
    asyncio.run(main())
