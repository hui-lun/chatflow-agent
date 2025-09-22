
import logging
import json
import os
import httpx
import asyncio
from lightrag.llm.openai import openai_complete_if_cache

try:
    from lightrag.kg.milvus_impl import MilvusVectorDBStorage as OriginalMilvusStorage
    from pymilvus import FieldSchema, CollectionSchema, DataType
except ImportError as e:
    logging.error(f"Could not import Milvus/PyMilvus classes: {e}")
    # Define dummy classes to allow application startup
    class OriginalMilvusStorage: pass
    class FieldSchema: pass
    class CollectionSchema: pass
    class DataType: pass

# Load environment variables once at the module level
VLLM_API_BASE = os.getenv("VLLM_API_BASE")
EMBEDDING_API_BASE = os.getenv("EMBEDDING_API_BASE")

async def custom_embed_func(texts: list[str], **kwargs) -> list[list[float]]:
    """Calls a remote embedding API endpoint."""
    if not EMBEDDING_API_BASE:
        raise ValueError("EMBEDDING_API_BASE environment variable is not set.")
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(f"{EMBEDDING_API_BASE}/embed", json={"texts": texts})
        response.raise_for_status()
        return response.json()["embeddings"]

class UserAwareLLM:
    """Ensures LLM cache is isolated per user."""
    def __init__(self, user_id: str):
        self.user_id = user_id
        if not VLLM_API_BASE:
            raise ValueError("VLLM_API_BASE environment variable is not set.")

    def __call__(self, prompt: str, **kwargs):
        # Prepend user_id to the prompt to ensure a unique cache key across users
        user_specific_prompt = f"Internal User ID: {self.user_id}\n---\n{prompt}"
        # Also add to hashing_kv for explicit cache key separation
        kwargs['hashing_kv'] = json.dumps({'user_id': self.user_id}, sort_keys=True)
        return openai_complete_if_cache(
            "gemma-3-27b-it",
            user_specific_prompt,
            api_key="EMPTY",
            base_url=VLLM_API_BASE,
            **kwargs
        )

class UserAwareEmbeddingFunc:
    """Ensures embedding cache is isolated per user."""
    def __init__(self, user_id: str):
        self.user_id = user_id
        self.embed_func = custom_embed_func

    async def __call__(self, texts: list[str], **kwargs) -> list[list[float]]:
        # Add user_id to hashing_kv for explicit cache key separation
        kwargs['hashing_kv'] = json.dumps({'user_id': self.user_id}, sort_keys=True)
        return await self.embed_func(texts, **kwargs)

class MultiTenantMilvusStorage(OriginalMilvusStorage):
    """
    Extends MilvusVectorDBStorage to enforce data isolation using a 'user_id' field
    in a single collection.
    """
    def __init__(self, user_id: str, **kwargs):
        self.user_id = user_id
        # The original class will be patched, so we call its parent's init
        super().__init__(**kwargs)
        logging.info(f"MultiTenantMilvusStorage initialized for user '{self.user_id}' on collection '{self.final_namespace}'")

    def _create_schema_for_namespace(self) -> CollectionSchema:
        """Adds a 'user_id' field to the Milvus collection schema if it doesn't exist."""
        original_schema = super()._create_schema_for_namespace()
        if "user_id" not in [field.name for field in original_schema.fields]:
            user_id_field = FieldSchema(name="user_id", dtype=DataType.VARCHAR, max_length=256, description="User ID for multi-tenancy filter")
            original_schema.fields.append(user_id_field)
            logging.info(f"Added 'user_id' field to schema for collection '{self.final_namespace}'")
        return original_schema

    def _create_indexes_after_collection(self):
        """Creates an index on the 'user_id' field for efficient filtering."""
        super()._create_indexes_after_collection()
        try:
            # Check if index already exists
            collection_info = self._client.describe_collection(self.final_namespace)
            user_id_indexed = any(
                index.field_name == "user_id" for index in collection_info['indexes']
            )
            if not user_id_indexed:
                logging.info(f"Creating 'INVERTED' index on 'user_id' field for collection '{self.final_namespace}'...")
                self._client.create_index(collection_name=self.final_namespace, field_name="user_id", index_params={"index_type": "INVERTED"})
                logging.info(f"Index on 'user_id' created successfully.")
            else:
                logging.info(f"Index on 'user_id' already exists.")
        except Exception as e:
            # Catching broad exception as pymilvus can raise various errors
            logging.warning(f"Failed to create or verify index on 'user_id': {e}")

    async def upsert(self, data: dict[str, dict[str, any]]) -> None:
        """Injects the user_id into each record before upserting."""
        if not data:
            return
        logging.debug(f"Upserting {len(data)} records for user '{self.user_id}'")
        for key in data:
            data[key]["user_id"] = self.user_id
        
        original_meta_fields = self.meta_fields.copy()
        if "user_id" not in self.meta_fields:
            self.meta_fields.add("user_id")
        
        await super().upsert(data)
        
        self.meta_fields = original_meta_fields

    async def query(self, query: str, top_k: int, query_embedding: list[float] = None, expr: str = None, **kwargs) -> list[dict[str, any]]:
        """Adds a 'user_id' filter to every query expression."""
        logging.debug(f"Querying for user '{self.user_id}' with query: '{query[:50]}...'" )
        user_filter_expr = f"user_id == '{self.user_id}'"
        final_expr = f"({expr}) and {user_filter_expr}" if expr else user_filter_expr
        
        logging.debug(f"Using Milvus filter expression: \"{final_expr}\"" )
        
        if not query_embedding:
            if not query:
                raise ValueError("Either query or query_embedding must be provided.")
            query_embedding = (await custom_embed_func([query]))[0]
        
        output_fields = list(self.meta_fields)
        if "doc_id" not in output_fields:
            output_fields.append("doc_id")
        
        search_results = await asyncio.to_thread(
            self._client.search,
            collection_name=self.final_namespace,
            data=[query_embedding],
            filter=final_expr,
            limit=top_k,
            output_fields=output_fields
        )
        results = search_results[0] if search_results else []
        logging.debug(f"Query found {len(results)} results for user '{self.user_id}'.")
        return results
