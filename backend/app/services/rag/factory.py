import os
import atexit
import logging

from raganything import RAGAnything, RAGAnythingConfig
from lightrag import LightRAG
from lightrag.utils import EmbeddingFunc
from lightrag.kg.shared_storage import initialize_pipeline_status
from lightrag.kg import milvus_impl

# Import the tenancy-specific components
from .tenancy import UserAwareLLM, UserAwareEmbeddingFunc, MultiTenantMilvusStorage

async def create_and_initialize_rag_for_user(user_id: str) -> RAGAnything:
    """
    Factory function to async create and initialize a complete, user-specific RAG instance.
    This function encapsulates the complex setup and configuration process.
    """
    logging.info(f"Factory: Creating and initializing new RAG instance for user '{user_id}'")

    # 1. Configure environment and paths
    os.environ['MILVUS_URI'] = 'http://milvus-standalone:19530'
    user_storage_dir = f"/app/rag_storage/user_{user_id.replace('-', '_').replace(' ', '_').lower()}"
    os.makedirs(user_storage_dir, exist_ok=True)
    logging.info(f"Factory: User storage directory set to '{user_storage_dir}'")

    # 2. Create a dynamic storage class with the user_id "baked in".
    # This mimics the closure behavior of the original implementation, resolving the
    # TypeError from LightRAG's constructor, which does not pass the user_id argument.
    class TenantAwareMilvusStorage(MultiTenantMilvusStorage):
        def __init__(self, **kwargs):
            # Call the parent's __init__ with the user_id from the factory's scope
            super().__init__(user_id=user_id, **kwargs)

    # 3. Apply the multi-tenancy monkey-patch using the DYNAMIC class
    milvus_impl.MilvusVectorDBStorage = TenantAwareMilvusStorage

    # 4. Instantiate user-aware components
    user_llm = UserAwareLLM(user_id)
    user_embed_func = UserAwareEmbeddingFunc(user_id)

    # 5. Configure and initialize LightRAG
    # DO NOT pass user_id here, as it's now part of the TenantAwareMilvusStorage class definition
    vector_db_kwargs = {"cosine_better_than_threshold": 0.7}
    lightrag_instance = LightRAG(
        working_dir=user_storage_dir,
        llm_model_func=user_llm,
        embedding_func=EmbeddingFunc(embedding_dim=1024, func=user_embed_func),
        vector_storage="MilvusVectorDBStorage", # This string now points to our TenantAwareMilvusStorage
        vector_db_storage_cls_kwargs=vector_db_kwargs,
    )
    
    # Perform async initialization
    await lightrag_instance.initialize_storages()
    await initialize_pipeline_status()
    logging.info(f"Factory: LightRAG initialized for user '{user_id}'.")

    # 6. Configure and initialize RAGAnything
    rag_anything_config = RAGAnythingConfig(working_dir=user_storage_dir)

    # 7. Intercept atexit registration
    original_atexit_register = atexit.register
    def dummy_atexit_register(func, *args, **kwargs):
        if hasattr(func, '__self__') and isinstance(func.__self__, RAGAnything):
            logging.info("Factory: Intercepted and skipped atexit registration for RAGAnything.close")
        else:
            original_atexit_register(func, *args, **kwargs)
    
    atexit.register = dummy_atexit_register

    rag_system = RAGAnything(
        lightrag=lightrag_instance,
        config=rag_anything_config,
        llm_model_func=user_llm,
        embedding_func=user_embed_func,
    )

    atexit.register = original_atexit_register
    
    logging.info(f"Factory: RAG instance for user '{user_id}' is fully created and initialized.")
    return rag_system